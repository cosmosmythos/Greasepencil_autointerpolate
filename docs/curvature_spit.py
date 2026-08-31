"""
Curvature-based polyline splitter for Blender
================================================

What this does
---------------
Given a mesh made of one or more "polylines" (open or closed chains of
edges, each interior vertex having exactly two edges), this script:

  1. Walks the mesh topology to recover the ORDERED point sequence of each
     chain (a mesh doesn't store point order on its own).
  2. Estimates the local curvature at every interior point using two
     well-defined, non-arbitrary measures:
       - turning angle: the angle between the incoming and outgoing
         direction of travel (0 deg = straight, up to 180 deg = full
         reversal).
       - discrete (Menger) curvature: 1 / R, where R is the radius of the
         circle that passes through the point and its two neighbours.
         This is the standard discrete-curve analogue of curvature from
         computational geometry, and gives units of 1/length rather than
         an angle, which makes it independent of how finely the curve is
         sampled if you pick the neighbours by arc-length distance instead
         of by vertex count.
     Both values are written to the mesh as float attributes ("curvature",
     "turn_angle_deg") so you can inspect them in the Spreadsheet editor
     (Object Data Properties > Attributes, or the Spreadsheet workspace)
     before trusting any threshold.
  3. Flags points whose metric exceeds a threshold as candidate corners,
     then performs non-maximum suppression so a single wide bend doesn't
     produce a cluster of split points.
  4. Optionally splits the mesh topology at each accepted corner (each
     corner vertex is duplicated in place, so the chain becomes two -- or
     more -- separate loose pieces that still touch at the same location).

How to use it
--------------
  1. Select your polyline object (make it the active object).
  2. Adjust the PARAMETERS block below.
  3. Paste into Blender's Text Editor and hit "Run Script"
     (or run via `blender --background --python curvature_split.py`).
  4. With MARK_ONLY = True, nothing is split -- only the "curvature" /
     "turn_angle_deg" attributes and a "CurvaturePoints" vertex group are
     written, so you can tune the threshold visually first. Set
     MARK_ONLY = False to actually perform the split once you're happy.

Limitations
-----------
  - Only meshes made of pure edge chains (wire polylines) are supported --
    if your object has faces, splitting a shared vertex can produce
    non-manifold results, since faces aren't rerouted.
  - Branch points (a vertex with more than 2 edges) are treated as chain
    boundaries; curvature is not evaluated there. Each branch becomes its
    own sub-chain.
"""

import bpy
import bmesh
import math


# ---------------------------------------------------------------------------
# PARAMETERS -- tune these for your data
# ---------------------------------------------------------------------------

# 'ANGLE'     - split where local direction change >= ANGLE_THRESHOLD_DEG
# 'CURVATURE' - split where 1/R >= CURVATURE_THRESHOLD
SPLIT_METRIC = 'ANGLE'

ANGLE_THRESHOLD_DEG = 10.0       # used when SPLIT_METRIC == 'ANGLE'
CURVATURE_THRESHOLD = 5.0        # used when SPLIT_METRIC == 'CURVATURE' (1/units)

# How the two "neighbour" points used for each curvature estimate are chosen:
#   'COUNT'    - step NEIGHBOR_COUNT vertices forward/back along the chain.
#                Simple, but if your polyline has many closely spaced
#                points, a single-vertex step barely turns at all even at a
#                sharp bend.
#   'DISTANCE' - walk forward/back until NEIGHBOR_DIST of arc length has
#                been covered. Robust to uneven / dense point spacing.
NEIGHBOR_MODE = 'DISTANCE'
NEIGHBOR_COUNT = 1                # used when NEIGHBOR_MODE == 'COUNT'
NEIGHBOR_DIST = 0.12              # used when NEIGHBOR_MODE == 'DISTANCE' (Blender units)

MIN_SEPARATION = 1               # minimum vertex-count gap between two accepted
                                 # corners (non-max suppression window)

MARK_ONLY = True                 # True: only write attributes / vertex group,
                                 # don't split anything yet. Flip to False once
                                 # you're happy with the threshold.

OPERATE_ON_COPY = False           # True: run on a duplicate of the active object
                                 # so the original is never touched.


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

def extract_chains(bm):
    """Return a list of (ordered_verts, is_closed) for every linear chain
    in the mesh. A vertex with exactly 2 edges is an interior chain point;
    anything else (0, 1, or 3+ edges) is treated as a chain boundary."""
    visited_edges = set()
    chains = []

    def walk(v_start, e_start):
        chain = [v_start]
        v_prev = v_start
        e_cur = e_start
        while True:
            visited_edges.add(e_cur.index)
            v_cur = e_cur.other_vert(v_prev)
            chain.append(v_cur)
            if v_cur == v_start:
                return chain[:-1], True  # closed loop, drop the repeated start
            if len(v_cur.link_edges) != 2:
                return chain, False
            next_edges = [e for e in v_cur.link_edges if e.index != e_cur.index]
            if not next_edges or next_edges[0].index in visited_edges:
                return chain, False
            v_prev, e_cur = v_cur, next_edges[0]

    # open chains / chains starting at a boundary or branch vertex
    for v in bm.verts:
        if len(v.link_edges) != 2:
            for e in v.link_edges:
                if e.index not in visited_edges:
                    chains.append(walk(v, e))

    # anything left over is a closed loop with no boundary at all
    for e in bm.edges:
        if e.index not in visited_edges:
            chains.append(walk(e.verts[0], e))

    return chains


def make_neighbor_fn(n, closed, coords, mode, count, dist):
    if closed:
        seg_len = [(coords[(k + 1) % n] - coords[k]).length for k in range(n)]
    else:
        seg_len = [(coords[k + 1] - coords[k]).length for k in range(max(n - 1, 0))]

    def by_count(i, forward):
        j = i + count if forward else i - count
        if closed:
            return j % n
        return j if 0 <= j < n else None

    def by_distance(i, forward):
        acc, j, steps = 0.0, i, 0
        while True:
            if forward:
                nxt = (j + 1) % n if closed else j + 1
                if not closed and nxt >= n:
                    return None
                edge_idx = j
            else:
                nxt = (j - 1) % n if closed else j - 1
                if not closed and nxt < 0:
                    return None
                edge_idx = nxt
            acc += seg_len[edge_idx]
            j = nxt
            steps += 1
            if closed and steps >= n:
                return None
            if acc >= dist:
                return j

    return by_count if mode == 'COUNT' else by_distance


def non_max_suppress(candidates, min_sep):
    """candidates: list of (index, metric), sorted by index ascending.
    Collapses runs of candidates within min_sep of each other down to the
    single strongest one in each run."""
    if not candidates:
        return []
    groups = [[candidates[0]]]
    for c in candidates[1:]:
        if c[0] - groups[-1][-1][0] <= min_sep:
            groups[-1].append(c)
        else:
            groups.append([c])
    return [max(g, key=lambda c: c[1]) for g in groups]


def split_chain_at(bm, v, keep_neighbor):
    """Duplicate v so that only the edge to keep_neighbor stays attached to
    the original vertex; every other edge of v is reattached to a new
    vertex at the same position. Returns the new vertex."""
    edges = list(v.link_edges)
    if len(edges) < 2:
        return v
    keep_edge = next((e for e in edges if e.other_vert(v) == keep_neighbor), edges[0])
    v_new = bm.verts.new(v.co)
    for e in edges:
        if e is keep_edge:
            continue
        other = e.other_vert(v)
        bm.edges.new((v_new, other))
        bm.edges.remove(e)
    return v_new


def main():
    if SPLIT_METRIC not in ('ANGLE', 'CURVATURE'):
        raise ValueError("SPLIT_METRIC must be 'ANGLE' or 'CURVATURE'")

    active = bpy.context.active_object
    if active is None or active.type != 'MESH':
        raise RuntimeError("Select a mesh (polyline) object first.")

    if OPERATE_ON_COPY:
        obj = active.copy()
        obj.data = active.data.copy()
        obj.name = active.name + "_split"
        bpy.context.collection.objects.link(obj)
        active.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    else:
        obj = active

    prev_mode = obj.mode
    if prev_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    curv_layer = bm.verts.layers.float.get("curvature")
    if curv_layer is None:
        curv_layer = bm.verts.layers.float.new("curvature")
    angle_layer = bm.verts.layers.float.get("turn_angle_deg")
    if angle_layer is None:
        angle_layer = bm.verts.layers.float.new("turn_angle_deg")
    deform_layer = bm.verts.layers.deform.verify()

    vg = obj.vertex_groups.get("CurvaturePoints")
    if vg is None:
        vg = obj.vertex_groups.new(name="CurvaturePoints")

    chains = extract_chains(bm)
    total_corners = 0
    total_splits = 0

    for chain, closed in chains:
        n = len(chain)
        if n < 3:
            continue

        coords = [v.co.copy() for v in chain]
        neighbor_fn = make_neighbor_fn(n, closed, coords, NEIGHBOR_MODE, NEIGHBOR_COUNT, NEIGHBOR_DIST)

        candidates = []
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                continue
            a_idx = neighbor_fn(i, forward=False)
            c_idx = neighbor_fn(i, forward=True)
            if a_idx is None or c_idx is None or a_idx == i or c_idx == i:
                continue

            A, B, C = coords[a_idx], coords[i], coords[c_idx]
            AB_vec, BC_vec = B - A, C - B
            AB, BC = AB_vec.length, BC_vec.length
            if AB < 1e-9 or BC < 1e-9:
                continue

            dot = max(-1.0, min(1.0, (AB_vec / AB).dot(BC_vec / BC)))
            angle_deg = math.degrees(math.acos(dot))

            CA = (C - A).length
            area2 = AB_vec.cross(C - A).length  # 2x triangle area
            curvature = (2.0 * area2 / (AB * BC * CA)) if AB * BC * CA > 1e-12 else 0.0

            chain[i][curv_layer] = curvature
            chain[i][angle_layer] = angle_deg

            metric = angle_deg if SPLIT_METRIC == 'ANGLE' else curvature
            threshold = ANGLE_THRESHOLD_DEG if SPLIT_METRIC == 'ANGLE' else CURVATURE_THRESHOLD
            if metric >= threshold:
                candidates.append((i, metric))

        chosen = non_max_suppress(candidates, MIN_SEPARATION)
        total_corners += len(chosen)

        for idx, _ in chosen:
            chain[idx][deform_layer][vg.index] = 1.0

        if not MARK_ONLY:
            verts = list(chain)
            for idx, _ in chosen:
                pred_pos = (idx - 1) % n if closed else idx - 1
                v_new = split_chain_at(bm, verts[idx], verts[pred_pos])
                verts[idx] = v_new
                total_splits += 1

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    if prev_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=prev_mode)

    print(f"[curvature-split] chains found: {len(chains)}")
    print(f"[curvature-split] corner points identified: {total_corners}")
    print(f"[curvature-split] splits performed: {total_splits}"
          + ("  (MARK_ONLY was True, so nothing was actually split)" if MARK_ONLY else ""))


main()
