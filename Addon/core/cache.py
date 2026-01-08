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
    bpy.ops.wm.append(
        filepath=os.path.join(filepath, "NodeTree", nodegroup_name),
        directory=os.path.join(filepath, "NodeTree"),
        filename=nodegroup_name
    )


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
    
    print("[GPAI] Building Cache...")
    
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return

    # Setup node group and modifier
    nodegroup = "Auto-Interpolate (c)"
    if nodegroup not in bpy.data.node_groups:
        current_mode = bpy.context.mode
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            append_nodegroup(nodegroup)
            if current_mode == 'EDIT_GREASE_PENCIL':
                bpy.ops.object.mode_set(mode='EDIT')
            else:
                bpy.ops.object.mode_set(mode=current_mode)
            gp_obj.select_set(True)
        except Exception as e:
            print(f"Failed to append node group: {e}")
            return              
        
    modifier = gp_obj.modifiers.get("Auto-Interpolate (c)")
    if modifier is None:
        modifier = gp_obj.modifiers.new(name="Auto-Interpolate (c)", type='NODES')
        modifier.node_group = bpy.data.node_groups.get(nodegroup)

    # Create attributes on all frames
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            attrs = frame.drawing.attributes
            drawing = frame.drawing
            total_points = sum(len(s.points) for s in drawing.strokes)
            
            if total_points == 0:
                continue
            
            # Create/initialize attributes
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

    # Collect keyframe data
    for layer_idx, layer in enumerate(gp_obj.data.layers):
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
                
                # Read Match_ID attribute if it exists
                match_ids = None
                if 'Match_ID' in attrs and len(attrs['Match_ID'].data) > 0:
                    match_ids = np.empty(len(attrs['Match_ID'].data), dtype=np.int32)
                    attrs['Match_ID'].data.foreach_get('value', match_ids)
                
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
                    
                    # Add Match_ID (default to stroke_idx for position-based pairing)
                    if match_ids is not None and stroke_idx < len(match_ids):
                        match_id = int(match_ids[stroke_idx])
                        # Use FTP-SC match_id if set, otherwise default to position-based
                        stroke_attrs['match_id'] = match_id if match_id >= 0 else stroke_idx
                    else:
                        # No Match_ID attribute exists - default to position-based
                        stroke_attrs['match_id'] = stroke_idx
                    
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
    
    print("[GPAI] Cache build complete.")


def clear():
    """Clear the cache"""
    global cache
    cache.clear()
