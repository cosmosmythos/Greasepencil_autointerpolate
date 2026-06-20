"""
Cache System for GP Auto Interpolate
Manages keyframe data caching for fast interpolation.

Architecture (v2 — multi-object):
  cache_registry = {
      obj_name: {
          'signature': tuple,             # full structural signature
          '_keyframe_signature': tuple,   # lightweight: layer count + keyframe numbers
          'layers': {
                layer_idx: {
                    'keyframes': { frame_num: [stroke_dicts] },
                    'sorted_frames': [int],
                    'frame_lookup': { frame_num: frame_ref },
                    'easing_data': { frame_num: [samples] },
                    'easing_samples': { frame_num: np.float32[64] },
                    'arc_data': { frame_num: (amount, direction, blend, spiral) },
                }
            }
      }
  }

Dirty-flag invalidation:
  Instead of calling get_signature() every frame, depsgraph_update_post sets
  a dirty flag per-object.  The interpolation loop checks is_dirty() and only
  rebuilds when the flag is set.  Frame changes alone never invalidate.
"""

import bpy
import numpy as np


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

# Per-object cache: { obj_name: { 'signature': ..., 'layers': ... } }
cache_registry = {}

# Dirty flags: object names that need a cache rebuild
_dirty_objects = set()

# Suppress depsgraph invalidation caused by our own writes/rebuilds.
_runtime_update_depth = {}
_runtime_update_grace = {}

# ---------------------------------------------------------------------------
# Dirty-flag API
# ---------------------------------------------------------------------------

def mark_dirty(obj_name):
    """Mark an object's cache as needing rebuild.
    Called from depsgraph_update_post when geometry changes are detected.
    """
    _dirty_objects.add(obj_name)


def is_dirty(obj_name):
    """Check if an object needs a cache rebuild."""
    return obj_name in _dirty_objects


def clear_dirty(obj_name):
    """Clear the dirty flag after a successful rebuild."""
    _dirty_objects.discard(obj_name)


def begin_runtime_update(obj_name):
    """Mark an object as being updated internally by the addon."""
    _runtime_update_depth[obj_name] = _runtime_update_depth.get(obj_name, 0) + 1


def end_runtime_update(obj_name, grace_updates=2):
    """End an internal update and ignore the next few depsgraph updates."""
    depth = _runtime_update_depth.get(obj_name, 0)
    if depth <= 1:
        _runtime_update_depth.pop(obj_name, None)
        _runtime_update_grace[obj_name] = max(
            _runtime_update_grace.get(obj_name, 0),
            grace_updates,
        )
    else:
        _runtime_update_depth[obj_name] = depth - 1


def is_runtime_update_active(obj_name):
    """Return True while the addon is actively mutating this object."""
    return _runtime_update_depth.get(obj_name, 0) > 0


def has_runtime_update_grace(obj_name):
    """Return True when post-write depsgraph grace updates are still pending."""
    return _runtime_update_grace.get(obj_name, 0) > 0


def consume_runtime_update_grace(obj_name):
    """Consume one pending post-write grace update, if any."""
    grace = _runtime_update_grace.get(obj_name, 0)
    if grace <= 0:
        return False

    if grace == 1:
        _runtime_update_grace.pop(obj_name, None)
    else:
        _runtime_update_grace[obj_name] = grace - 1
    return True


def clear_runtime_update_grace(obj_name):
    """Clear any pending post-write grace updates."""
    _runtime_update_grace.pop(obj_name, None)


# ---------------------------------------------------------------------------
# Cache accessors
# ---------------------------------------------------------------------------

def get_cache(obj_name):
    """Get cache dict for a specific object.  Returns {} if not cached."""
    return cache_registry.get(obj_name, {})


def clear(obj_name=None):
    """Clear cache for one object, or all if obj_name is None."""
    global cache_registry
    if obj_name:
        cache_registry.pop(obj_name, None)
        _dirty_objects.discard(obj_name)
        _runtime_update_depth.pop(obj_name, None)
        _runtime_update_grace.pop(obj_name, None)
    else:
        cache_registry.clear()
        _dirty_objects.clear()
        _runtime_update_depth.clear()
        _runtime_update_grace.clear()


# ---------------------------------------------------------------------------
# Signature (used only inside build(), NOT every frame)
# ---------------------------------------------------------------------------

def get_signature(gp_obj):
    """Calculates a signature based on the GP object's structure."""
    if not gp_obj or not gp_obj.data:
        return None

    layer_count = len(gp_obj.data.layers)
    frame_counts = []
    stroke_counts = []
    point_counts = []
    keyframe_numbers = []

    for layer in gp_obj.data.layers:
        frame_counts.append(len(layer.frames))
        layer_keyframes = []
        for frame in layer.frames:
            layer_keyframes.append(frame.frame_number)
            stroke_counts.append(len(frame.drawing.strokes))
            for stroke in frame.drawing.strokes:
                point_counts.append(len(stroke.points))
        keyframe_numbers.append(tuple(sorted(layer_keyframes)))

    return (layer_count, tuple(frame_counts), tuple(stroke_counts),
            tuple(point_counts), tuple(keyframe_numbers))


def get_keyframe_signature(gp_obj):
    """Lightweight check: only layer count + keyframe numbers.

    Catches moved / added / removed keyframes without iterating strokes
    or points.  Used by the deferred sig check in npanel_handlers.py
    (timer-scheduled, NOT per-frame).
    """
    if not gp_obj or not gp_obj.data:
        return None
    keyframe_numbers = []
    for layer in gp_obj.data.layers:
        keyframe_numbers.append(
            tuple(sorted(f.frame_number for f in layer.frames)))
    return (len(gp_obj.data.layers), tuple(keyframe_numbers))


# ---------------------------------------------------------------------------
# Node group helpers
# ---------------------------------------------------------------------------

def append_nodegroup(nodegroup_name):
    import os
    filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "Auto-Interpolate (c).blend")
    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        if nodegroup_name in data_from.node_groups:
            data_to.node_groups = [nodegroup_name]


def check_and_update_nodegroup():
    """Check and update outdated node group. Returns True if updated."""
    from .constants import NODEGROUP_NAME, NODEGROUP_VERSION, MODIFIER_NAME

    existing = bpy.data.node_groups.get(NODEGROUP_NAME)
    if not existing:
        return False

    if (existing.description or "") == NODEGROUP_VERSION:
        return False

    print(f"[GPAI] Node group outdated: '{existing.description}' -> '{NODEGROUP_VERSION}'")

    objects_with_modifier = []
    for obj in bpy.data.objects:
        if obj.type == 'GREASEPENCIL':
            for mod in list(obj.modifiers):
                if mod.type == 'NODES' and mod.node_group == existing:
                    objects_with_modifier.append(obj)
                    obj.modifiers.remove(mod)

    bpy.data.node_groups.remove(existing)
    append_nodegroup(NODEGROUP_NAME)

    new_nodegroup = bpy.data.node_groups.get(NODEGROUP_NAME)
    if new_nodegroup:
        for obj in objects_with_modifier:
            modifier = obj.modifiers.new(name=MODIFIER_NAME, type='NODES')
            modifier.node_group = new_nodegroup

    print(f"[GPAI] Node group updated to {NODEGROUP_VERSION}")
    return True


def ensure_nodegroup():
    """Ensure node group exists. Call from operators only, not handlers."""
    nodegroup_name = "Auto-Interpolate (c)"
    check_and_update_nodegroup()
    if nodegroup_name not in bpy.data.node_groups:
        append_nodegroup(nodegroup_name)
    return bpy.data.node_groups.get(nodegroup_name)


def ensure_modifier(gp_obj):
    """Ensure modifier exists on object. Call from operators only."""
    nodegroup = ensure_nodegroup()
    if not nodegroup:
        return None
    modifier = gp_obj.modifiers.get("Auto-Interpolate (c)")
    if modifier is None:
        modifier = gp_obj.modifiers.new(name="Auto-Interpolate (c)", type='NODES')
        modifier.node_group = nodegroup
    return modifier


# ---------------------------------------------------------------------------
# Cache build  (per-object, never touches siblings)
# ---------------------------------------------------------------------------

def build(gp_obj):
    """Scans ONE Grease Pencil object and builds/rebuilds its cache entry.

    This writes to cache_registry[gp_obj.name] ONLY — never clears or
    touches cache entries for other objects.
    """
    global cache_registry

    obj_name = gp_obj.name
    begin_runtime_update(obj_name)
    try:
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            cache_registry.pop(obj_name, None)
            return

        old_entry = cache_registry.get(obj_name, {})
        old_easing_data = {}
        old_arc_data = {}
        if 'layers' in old_entry:
            for layer_idx, layer_cache in old_entry['layers'].items():
                if 'easing_data' in layer_cache:
                    old_easing_data[layer_idx] = layer_cache['easing_data'].copy()
                if 'arc_data' in layer_cache:
                    old_arc_data[layer_idx] = layer_cache['arc_data'].copy()

        new_entry = {
            'signature': get_signature(gp_obj),
            '_keyframe_signature': get_keyframe_signature(gp_obj),
            'layers': {},
        }

        nodegroup = "Auto-Interpolate (c)"
        modifier = gp_obj.modifiers.get("Auto-Interpolate (c)")
        if modifier is None:
            try:
                modifier = gp_obj.modifiers.new(name="Auto-Interpolate (c)", type='NODES')
                modifier.node_group = bpy.data.node_groups.get(nodegroup)
            except Exception:
                print("[GPAI]: Modifier not found during cache build")

        _ensure_interpolation_attributes(gp_obj)

        from ..operators.layer_filter import should_interpolate_layer

        for layer_idx, layer in enumerate(gp_obj.data.layers):
            if not should_interpolate_layer(layer):
                continue

            layer_cache = {
                'keyframes': {},
                'sorted_frames': [],
                'frame_lookup': {},
                'easing_data': {},
                'easing_samples': {},
                'arc_data': {},
            }

            if layer_idx in old_easing_data:
                layer_cache['easing_data'] = old_easing_data[layer_idx]
            if layer_idx in old_arc_data:
                layer_cache['arc_data'] = old_arc_data[layer_idx]

            keyframes_dict = {}
            for frame in layer.frames:
                layer_cache['frame_lookup'][frame.frame_number] = frame

                if (not hasattr(frame.drawing, 'attributes')
                        or 'position' not in frame.drawing.attributes):
                    continue

                attrs = frame.drawing.attributes
                pos_attr = attrs['position']

                if len(frame.drawing.strokes) == 0 or len(pos_attr.data) == 0:
                    continue

                all_positions = np.empty(len(pos_attr.data) * 3, dtype=np.float32)
                pos_attr.data.foreach_get('vector', all_positions)

                attr_data = {}
                for attr_name, attr_type, multiplier in [
                    ('opacity', 'value', 1),
                    ('radius', 'value', 1),
                    ('handle_left', 'vector', 3),
                    ('handle_right', 'vector', 3),
                ]:
                    if attr_name in attrs and len(attrs[attr_name].data) > 0:
                        buffer = np.empty(len(attrs[attr_name].data) * multiplier,
                                          dtype=np.float32)
                        attrs[attr_name].data.foreach_get(attr_type, buffer)
                        attr_data[attr_name] = buffer

                stroke_data = []
                pos_idx = 0
                attr_idx = 0
                for stroke in frame.drawing.strokes:
                    point_count = len(stroke.points)
                    stroke_dict = {
                        'position': all_positions[pos_idx:pos_idx + point_count * 3],
                        'opacity': (attr_data['opacity'][attr_idx:attr_idx + point_count]
                                    if 'opacity' in attr_data
                                    else np.ones(point_count, dtype=np.float32)),
                        'radius': (attr_data['radius'][attr_idx:attr_idx + point_count]
                                   if 'radius' in attr_data
                                   else np.zeros(point_count, dtype=np.float32)),
                        'handle_left': (attr_data['handle_left'][pos_idx:pos_idx + point_count * 3]
                                        if 'handle_left' in attr_data
                                        else np.zeros(point_count * 3, dtype=np.float32)),
                        'handle_right': (attr_data['handle_right'][pos_idx:pos_idx + point_count * 3]
                                         if 'handle_right' in attr_data
                                         else np.zeros(point_count * 3, dtype=np.float32)),
                    }
                    stroke_data.append(stroke_dict)
                    pos_idx += point_count * 3
                    attr_idx += point_count

                keyframes_dict[frame.frame_number] = stroke_data

            if keyframes_dict:
                layer_cache['keyframes'] = keyframes_dict
                layer_cache['sorted_frames'] = sorted(keyframes_dict.keys())

                from ..utils import easing
                from ..utils import arc_data
                for frame_num in keyframes_dict.keys():
                    easing_curve = easing.get_easing_curve_from_frame(
                        gp_obj.data, layer_idx, frame_num, layer)
                    layer_cache['easing_data'][frame_num] = easing_curve
                    layer_cache['easing_samples'][frame_num] = np.array(
                        easing_curve, dtype=np.float32)

                    arc_params = arc_data.get_arc_params_from_frame(
                        gp_obj.data, layer_idx, frame_num, layer)
                    layer_cache['arc_data'][frame_num] = arc_params

                for frame_num, frame in layer_cache['frame_lookup'].items():
                    if frame_num in keyframes_dict:
                        f_attrs = frame.drawing.attributes
                        if "key" in f_attrs:
                            key_attr = f_attrs["key"]
                            total_points = sum(len(s.points)
                                               for s in frame.drawing.strokes)
                            if total_points > 0 and len(key_attr.data) == total_points:
                                key_values = np.full(total_points, frame_num, dtype=np.int32)
                                existing_key_values = np.empty(total_points, dtype=np.int32)
                                key_attr.data.foreach_get('value', existing_key_values)
                                if not np.array_equal(existing_key_values, key_values):
                                    key_attr.data.foreach_set('value', key_values)

            new_entry['layers'][layer_idx] = layer_cache

        cache_registry[obj_name] = new_entry
        clear_dirty(obj_name)
    finally:
        end_runtime_update(obj_name)


# ---------------------------------------------------------------------------
# Internal: ensure _i attributes exist on every frame  (Phase 0D)
# ---------------------------------------------------------------------------

def _ensure_interpolation_attributes(gp_obj):
    """Create *_i mirror attributes on every frame of *gp_obj*.

    Phase 0D optimisation: only copy source → _i when the attribute is
    first created.  If it already exists (and has the right size) we skip
    the expensive foreach_get/foreach_set round-trip because the
    interpolation engine will overwrite it during processing anyway.
    """
    attr_defs = [
        ("position_i", 'FLOAT_VECTOR', 'POINT', "position", 'vector', 3),
        ("opacity_i",  'FLOAT',        'POINT', "opacity",  'value',  1),
        ("radius_i",   'FLOAT',        'POINT', "radius",   'value',  1),
        ("handle_left_i",  'FLOAT_VECTOR', 'POINT', "handle_left",  'vector', 3),
        ("handle_right_i", 'FLOAT_VECTOR', 'POINT', "handle_right", 'vector', 3),
    ]

    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            drawing = frame.drawing
            attrs = drawing.attributes
            total_points = sum(len(s.points) for s in drawing.strokes)

            if total_points == 0:
                continue

            for attr_name, attr_type, domain, source_name, access_type, multiplier in attr_defs:
                newly_created = False
                if attr_name not in attrs:
                    attrs.new(attr_name, attr_type, domain)
                    newly_created = True

                # Only copy source data into _i on first creation
                if newly_created and source_name in attrs:
                    source_attr = attrs[source_name]
                    target_attr = attrs[attr_name]
                    if len(source_attr.data) > 0:
                        data_size = total_points * multiplier
                        buffer = np.empty(data_size, dtype=np.float32)
                        source_attr.data.foreach_get(access_type, buffer)
                        target_attr.data.foreach_set(access_type, buffer)

            if "key" not in attrs:
                attrs.new("key", 'INT', 'POINT')
