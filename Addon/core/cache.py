"""
Cache System for GP Auto Interpolate
Manages keyframe data caching for fast interpolation
"""

import bpy
import numpy as np

# Global cache
cache = {}


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

    return (layer_count, tuple(frame_counts), tuple(stroke_counts), tuple(point_counts), tuple(keyframe_numbers))


def append_nodegroup(nodegroup_name):
    import os
    filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Auto-Interpolate (c).blend")
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


def build(gp_obj):
    """Scans the Grease Pencil object and builds a cache of its keyframe data."""
    global cache
    
    # Preserve existing easing data and arc data
    old_easing_data = {}
    old_arc_data = {}
    if 'layers' in cache:
        for layer_idx, layer_cache in cache['layers'].items():
            if 'easing_data' in layer_cache:
                old_easing_data[layer_idx] = layer_cache['easing_data'].copy()
            if 'arc_data' in layer_cache:
                old_arc_data[layer_idx] = layer_cache['arc_data'].copy()
    
    cache.clear()
    
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return

    nodegroup = "Auto-Interpolate (c)"
    modifier = gp_obj.modifiers.get("Auto-Interpolate (c)")
    if modifier is None:
        try:
            modifier = gp_obj.modifiers.new(name="Auto-Interpolate (c)", type='NODES')
            modifier.node_group = bpy.data.node_groups.get(nodegroup)
        except:
            print("[GPAI]: Modifier not found during cache build")

    # Create attributes on all frames
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            attrs = frame.drawing.attributes
            drawing = frame.drawing
            total_points = sum(len(s.points) for s in drawing.strokes)
            
            if total_points == 0:
                continue
            
            attr_defs = [
                ("position_i", 'FLOAT_VECTOR', 'POINT', "position", 'vector', 3),
                ("opacity_i", 'FLOAT', 'POINT', "opacity", 'value', 1),
                ("radius_i", 'FLOAT', 'POINT', "radius", 'value', 1),
                ("handle_left_i", 'FLOAT_VECTOR', 'POINT', "handle_left", 'vector', 3),
                ("handle_right_i", 'FLOAT_VECTOR', 'POINT', "handle_right", 'vector', 3),
            ]
            
            for attr_name, attr_type, domain, source_name, access_type, multiplier in attr_defs:
                if attr_name not in attrs:
                    attrs.new(attr_name, attr_type, domain)
                
                if source_name in attrs:
                    source_attr = attrs[source_name]
                    target_attr = attrs[attr_name]
                    
                    if len(source_attr.data) > 0:
                        data_size = total_points * multiplier
                        buffer = np.empty(data_size, dtype=np.float32)
                        source_attr.data.foreach_get(access_type, buffer)
                        target_attr.data.foreach_set(access_type, buffer)
            
            if "key" not in attrs:
                attrs.new("key", 'INT', 'POINT')

    # Store signature
    cache['signature'] = get_signature(gp_obj)
    cache['layers'] = {}

    from ..operators.layer_filter import should_interpolate_layer
    
    for layer_idx, layer in enumerate(gp_obj.data.layers):
        if not should_interpolate_layer(layer):
            continue
        
        layer_cache = {
            'keyframes': {},
            'sorted_frames': [],
            'frame_lookup': {},
            'easing_data': {},
            'arc_data': {}  # NEW: arc trajectory data
        }
        
        # Restore old easing data
        if layer_idx in old_easing_data:
            layer_cache['easing_data'] = old_easing_data[layer_idx]
        
        # Restore old arc data
        if layer_idx in old_arc_data:
            layer_cache['arc_data'] = old_arc_data[layer_idx]
        
        keyframes_dict = {}
        for frame in layer.frames:
            layer_cache['frame_lookup'][frame.frame_number] = frame
            
            if not hasattr(frame.drawing, 'attributes') or 'position' not in frame.drawing.attributes:
                continue
                
            attrs = frame.drawing.attributes
            pos_attr = attrs['position']
            
            if len(frame.drawing.strokes) > 0 and len(pos_attr.data) > 0:
                pass  # Cache entry created
                all_positions = np.empty(len(pos_attr.data) * 3, dtype=np.float32)
                pos_attr.data.foreach_get('vector', all_positions)
                
                # Get all attributes
                attr_data = {}
                for attr_name, attr_type, multiplier in [
                    ('opacity', 'value', 1),
                    ('radius', 'value', 1),
                    ('handle_left', 'vector', 3),
                    ('handle_right', 'vector', 3)
                ]:
                    if attr_name in attrs and len(attrs[attr_name].data) > 0:
                        buffer = np.empty(len(attrs[attr_name].data) * multiplier, dtype=np.float32)
                        attrs[attr_name].data.foreach_get(attr_type, buffer)
                        attr_data[attr_name] = buffer
                
                stroke_data = []
                pos_idx = 0
                attr_idx = 0
                for stroke_idx, stroke in enumerate(frame.drawing.strokes):
                    point_count = len(stroke.points)
                    stroke_positions = all_positions[pos_idx : pos_idx + point_count * 3]
                    
                    stroke_attrs = {'position': stroke_positions}
                    
                    if 'opacity' in attr_data:
                        stroke_attrs['opacity'] = attr_data['opacity'][attr_idx : attr_idx + point_count]
                    if 'radius' in attr_data:
                        stroke_attrs['radius'] = attr_data['radius'][attr_idx : attr_idx + point_count]
                    if 'handle_left' in attr_data:
                        stroke_attrs['handle_left'] = attr_data['handle_left'][pos_idx : pos_idx + point_count * 3]
                    if 'handle_right' in attr_data:
                        stroke_attrs['handle_right'] = attr_data['handle_right'][pos_idx : pos_idx + point_count * 3]
                    
                    stroke_data.append(stroke_attrs)
                    pos_idx += point_count * 3
                    attr_idx += point_count
                
                keyframes_dict[frame.frame_number] = stroke_data
        
        if keyframes_dict:
            layer_cache['keyframes'] = keyframes_dict
            layer_cache['sorted_frames'] = sorted(keyframes_dict.keys())
            
            # Load easing data
            from ..utils import easing
            from ..utils import arc_data
            for frame_num in keyframes_dict.keys():
                easing_curve = easing.get_easing_curve_from_frame(gp_obj.data, layer_idx, frame_num, layer)
                layer_cache['easing_data'][frame_num] = easing_curve
                
                # Load arc data
                arc_params = arc_data.get_arc_params_from_frame(gp_obj.data, layer_idx, frame_num, layer)
                layer_cache['arc_data'][frame_num] = arc_params
            
            # Update key attribute
            for frame_num, frame in layer_cache['frame_lookup'].items():
                if frame_num in keyframes_dict:
                    attrs = frame.drawing.attributes
                    if "key" in attrs:
                        key_attr = attrs["key"]
                        total_points = sum(len(stroke.points) for stroke in frame.drawing.strokes)
                        if total_points > 0:
                            actual_attr_size = len(key_attr.data)
                            if actual_attr_size == total_points:
                                key_values = np.full(total_points, frame_num, dtype=np.int32)
                                key_attr.data.foreach_set('value', key_values)
        
        cache['layers'][layer_idx] = layer_cache


def clear():
    global cache
    cache.clear()
