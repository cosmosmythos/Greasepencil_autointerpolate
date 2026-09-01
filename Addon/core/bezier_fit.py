import bisect
import math

import bpy
import numpy as np
from mathutils import Vector

from ..utils.curve_points import find_corners

_PREF_ID = "bl_ext.user_default.gp_auto_interpolate"
_MAX_POINTS = 4096


def _get_subdivs() -> int:
    try:
        return int(bpy.context.scene.gp_bezier_resample_subdiv)
    except Exception:
        return 2


def _should_run() -> bool:
    try:
        addon = bpy.context.preferences.addons.get(_PREF_ID)
        if addon is not None and not bool(addon.preferences.draw_sensor_enabled):
            return False
    except Exception:
        pass
    try:
        if not bool(bpy.context.scene.gp_bezier_fit_enabled):
            return False
    except Exception:
        return False
    return True


def _resample_points(positions, radii, opacities, subdivs):
    n = len(positions)
    if subdivs == 0 or n < 2:
        return positions, radii, opacities
    for v in positions:
        if not math.isfinite(v.x) or not math.isfinite(v.y) or not math.isfinite(v.z):
            return None
    cumul = [0.0]
    total = 0.0
    for i in range(1, n):
        seg = (positions[i] - positions[i - 1]).length
        if not math.isfinite(seg) or seg > 1e6:
            return None
        total += seg
        cumul.append(total)
    if not math.isfinite(total) or total < 1e-6:
        return None
    avg_edge = total / (n - 1)
    spacing = max(avg_edge / subdivs, 0.0001)
    if not math.isfinite(spacing) or spacing <= 0:
        return None
    count = int(total / spacing) + 1
    count = max(2, min(count, _MAX_POINTS))
    new_pos, new_rad, new_opa = [], [], []
    for j in range(count):
        target = total * j / (count - 1) if count > 1 else 0.0
        idx = bisect.bisect_left(cumul, target)
        if idx == 0:
            new_pos.append(positions[0].copy())
            new_rad.append(radii[0])
            new_opa.append(opacities[0])
        elif idx >= n:
            new_pos.append(positions[-1].copy())
            new_rad.append(radii[-1])
            new_opa.append(opacities[-1])
        else:
            prev = cumul[idx - 1]
            seg_len = cumul[idx] - prev
            t = (target - prev) / seg_len if seg_len > 1e-6 else 0.0
            new_pos.append(positions[idx - 1].lerp(positions[idx], t))
            new_rad.append(radii[idx - 1] + t * (radii[idx] - radii[idx - 1]))
            new_opa.append(opacities[idx - 1] + t * (opacities[idx] - opacities[idx - 1]))
    return new_pos, new_rad, new_opa


def _fit_piece(points, max_error=1e-4):
    if len(points) < 2:
        return []
    try:
        from .cpp_module import interpolator_module
        import gp_autointerpolate
        mod = interpolator_module if interpolator_module is not None else gp_autointerpolate
    except Exception:
        try:
            import gp_autointerpolate as mod
        except Exception:
            return []
    flat = np.array([c for p in points for c in (p.x, p.y, p.z)], dtype=np.float32)
    try:
        result = mod.fit_bezier_flat(flat, float(max_error))
    except Exception:
        try:
            result = mod.fit_bezier(flat, float(max_error))
            # fit_bezier returns list of 12-float arrays
            if isinstance(result, list):
                flat_list = []
                for arr in result:
                    flat_list.extend([float(v) for v in arr])
                result = np.array(flat_list, dtype=np.float32)
            else:
                result = np.array(result, dtype=np.float32)
        except Exception:
            return []
    if result is None or len(result) == 0:
        return []
    # result is flat [p0,c1,c2,p1, p0,c1,c2,p1, ...] 12 per curve
    curves = []
    for i in range(0, len(result), 12):
        if i + 11 >= len(result):
            break
        p0 = Vector((result[i], result[i+1], result[i+2]))
        c1 = Vector((result[i+3], result[i+4], result[i+5]))
        c2 = Vector((result[i+6], result[i+7], result[i+8]))
        p1 = Vector((result[i+9], result[i+10], result[i+11]))
        curves.append((p0, c1, c2, p1))
    return curves


def _curves_to_stroke_data(curves):
    if not curves:
        return None
    # Stitch G0: p0 of first curve, then each p1; handles per point
    positions = []
    handles_left = []
    handles_right = []
    # first point
    p0, c1, c2, p1 = curves[0]
    positions.append(p0)
    handles_left.append(p0)  # start has no left handle
    handles_right.append(c1)
    for idx, (p0, c1, c2, p1) in enumerate(curves):
        if idx == 0:
            continue
        # intermediate point is previous p1 == current p0 (should match)
        # Use previous curve's c2 as left, current c1 as right
        prev_c2 = curves[idx-1][2]
        positions.append(p0)
        handles_left.append(prev_c2)
        handles_right.append(c1)
    # last point
    last_p1 = curves[-1][3]
    last_c2 = curves[-1][2]
    # If only one curve, we already have first point, need last point
    if len(curves) == 1:
        positions.append(last_p1)
        handles_left.append(last_c2)
        handles_right.append(last_p1)
    else:
        # last point already added as p0 of last curve? No, loop added p0 of last curve as intermediate, need to add final p1
        positions.append(last_p1)
        handles_left.append(last_c2)
        handles_right.append(last_p1)
    # For G0 at piece boundaries, handles are kept as fitted (not smoothed)
    return positions, handles_left, handles_right


def _write_bezier_stroke(drawing, last_index, positions, handles_left, handles_right, radii, opacities):
    # delete old resampled stroke
    try:
        drawing.remove_strokes(indices=(last_index,))
    except Exception:
        return False
    n = len(positions)
    if n < 2:
        return False
    # ensure handle attributes exist
    for name in ('handle_left', 'handle_right'):
        if not drawing.attributes.get(name):
            try:
                drawing.attributes.new(name=name, type='FLOAT_VECTOR', domain='POINT')
            except Exception:
                pass
    drawing.add_strokes([n])
    # new stroke is at end
    new_index = len(drawing.strokes) - 1
    new_stroke = drawing.strokes[new_index]
    # Move it to original position if not at end (drawing.add_strokes appends)
    # If last_index was not at end, we need to keep order — for now we appended, which may be after other strokes.
    # For last drawn stroke, last_index was at end, so new stroke at same place is fine.
    for i, point in enumerate(new_stroke.points):
        point.position = positions[i]
        # radius/opacity: lerp or use original first values if mismatched length
        if i < len(radii):
            point.radius = radii[i]
            point.opacity = opacities[i]
        else:
            point.radius = radii[-1] if radii else 0.02
            point.opacity = opacities[-1] if opacities else 1.0
    # write handles via attributes (point.handle_left has no setter)
    try:
        total_points = sum(len(s.points) for s in drawing.strokes)
        # Build flat arrays for all points, but we only need to set for new stroke's points at the end
        # Find offset of new stroke's points in flat array
        offset = total_points - n
        # Prepare flat vectors for handles
        hl_flat = []
        hr_flat = []
        # Need to build for all points, but we can just set for new stroke's range via foreach_set with offset?
        # foreach_set sets all points, so we need to build full arrays
        # Simpler: get current handle data, replace tail, set all
        hl_attr = drawing.attributes.get('handle_left')
        hr_attr = drawing.attributes.get('handle_right')
        if hl_attr and hr_attr:
            # Read current
            cur_hl = [0.0] * (total_points * 3)
            cur_hr = [0.0] * (total_points * 3)
            try:
                hl_attr.data.foreach_get('vector', cur_hl)
                hr_attr.data.foreach_get('vector', cur_hr)
            except Exception:
                pass
            for i in range(n):
                base = (offset + i) * 3
                hl = handles_left[i]
                hr = handles_right[i]
                cur_hl[base] = hl.x; cur_hl[base+1] = hl.y; cur_hl[base+2] = hl.z
                cur_hr[base] = hr.x; cur_hr[base+1] = hr.y; cur_hr[base+2] = hr.z
            hl_attr.data.foreach_set('vector', cur_hl)
            hr_attr.data.foreach_set('vector', cur_hr)
    except Exception:
        pass
    try:
        drawing.tag_positions_changed()
    except Exception:
        pass
    return True


def _bezier_fit_last_stroke():
    try:
        if not _should_run():
            return None
        obj = bpy.context.active_object
        if not obj or obj.type != "GREASEPENCIL":
            return None
        scene = bpy.context.scene
        layer = getattr(obj.data.layers, "active", None)
        if layer is None:
            return None
        frame_number = scene.frame_current if scene else None
        drawing = None
        if frame_number is not None:
            for frame in layer.frames:
                if frame.frame_number == frame_number:
                    drawing = frame.drawing
                    break
        if drawing is None or len(drawing.strokes) == 0:
            return None
        last_index = len(drawing.strokes) - 1
        stroke = drawing.strokes[last_index]
        n = len(stroke.points)
        if n < 2:
            return None
        positions = [p.position.copy() for p in stroke.points]
        radii = [p.radius for p in stroke.points]
        opacities = [p.opacity for p in stroke.points]

        # 1. Resample
        subdivs = _get_subdivs()
        res = _resample_points(positions, radii, opacities, subdivs)
        if res is None:
            return None
        positions, radii, opacities = res

        # 2. Decide method
        method = getattr(scene, "gp_bezier_fit_method", "ANGLE")
        if method == 'ANGLE':
            span = int(getattr(scene, "gp_bezier_span", 3))
            angle = float(getattr(scene, "gp_bezier_angle", 10.0))
            corners = find_corners(positions, span=span, angle=angle)
            if not corners:
                pieces = [positions]
                piece_radii = [radii]
                piece_opac = [opacities]
            else:
                # split at corners
                indices = sorted(set(corners))
                pieces = []
                pr = []
                po = []
                start = 0
                for c in indices:
                    # include corner in both pieces for G0 continuity, then dedup via stitching
                    pieces.append(positions[start:c+1])
                    pr.append(radii[start:c+1])
                    po.append(opacities[start:c+1])
                    start = c
                pieces.append(positions[start:])
                pr.append(radii[start:])
                po.append(opacities[start:])
                # filter tiny pieces
                filtered = [(p, r, o) for p, r, o in zip(pieces, pr, po) if len(p) >= 2]
                if filtered:
                    pieces, pr, po = zip(*filtered)
                    pieces, pr, po = list(pieces), list(pr), list(po)
                else:
                    pieces = [positions]
                    pr = [radii]
                    po = [opacities]
            # fit each piece and stitch
            all_positions = []
            all_hl = []
            all_hr = []
            all_radii = []
            all_opac = []
            for piece, pradii, popac in zip(pieces, pr, po):
                curves = _fit_piece(piece)
                if not curves:
                    # fallback: keep piece as polyline
                    continue
                conv = _curves_to_stroke_data(curves)
                if conv is None:
                    continue
                pos, hl, hr = conv
                # need to stitch: if not first piece, drop duplicate first point (corner)
                if all_positions:
                    pos = pos[1:]
                    hl = hl[1:]
                    hr = hr[1:]
                    pradii = pradii[1:] if len(pradii) > len(pos) else pradii
                    popac = popac[1:] if len(popac) > len(pos) else popac
                # radii/opacities for fitted points: lerp from piece
                # For simplicity, sample radii linearly along piece
                if len(pos) != len(pradii):
                    # resample radii to match new point count
                    # simple: use start/end radii
                    pradii = [pradii[0]] * len(pos) if pradii else [0.02]*len(pos)
                    popac = [popac[0]] * len(pos) if popac else [1.0]*len(pos)
                all_positions.extend(pos)
                all_hl.extend(hl)
                all_hr.extend(hr)
                all_radii.extend(pradii[:len(pos)])
                all_opac.extend(popac[:len(pos)])
            if not all_positions:
                return None
            _write_bezier_stroke(drawing, last_index, all_positions, all_hl, all_hr, all_radii, all_opac)
        else:  # ERROR
            curves = _fit_piece(positions)
            if not curves:
                return None
            conv = _curves_to_stroke_data(curves)
            if conv is None:
                return None
            pos, hl, hr = conv
            # radii for error method: resampled radii
            if len(pos) != len(radii):
                # map radii
                radii = [radii[0]] * len(pos)
                opacities = [opacities[0]] * len(pos)
            _write_bezier_stroke(drawing, last_index, pos, hl, hr, radii, opacities)
        return None
    except Exception:
        return None
    finally:
        try:
            from . import draw_sensor
            draw_sensor._last_stable = draw_sensor._get_total_counts()
            draw_sensor._has_pending = False
        except Exception:
            pass


def _on_drawing_done():
    try:
        bpy.app.timers.register(_bezier_fit_last_stroke, first_interval=0.0)
    except Exception:
        _bezier_fit_last_stroke()


def register():
    from .draw_sensor import register_drawing_done_callback
    register_drawing_done_callback(_on_drawing_done)


def unregister():
    try:
        from .draw_sensor import unregister_drawing_done_callback
        unregister_drawing_done_callback(_on_drawing_done)
    except Exception:
        pass
