"""
Interpolation Engine for GP Auto Interpolate
Handles real-time interpolation between keyframes
"""

import bpy
import numpy as np
from . import cpp_module
from . import cache


def calculate_stroke_normal(positions):
    """
    Calculate average normal for a stroke.
    Uses first, middle, and last points to define a plane.
    """
    point_count = len(positions) // 3
    if point_count < 3:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up
    
    # Get first, middle, and last points
    p0 = np.array([positions[0], positions[1], positions[2]])
    mid_idx = (point_count // 2) * 3
    p_mid = np.array([positions[mid_idx], positions[mid_idx+1], positions[mid_idx+2]])
    p_end = np.array([positions[-3], positions[-2], positions[-1]])
    
    # Two vectors in the stroke plane
    v1 = p_mid - p0
    v2 = p_end - p0
    
    # Cross product = normal
    normal = np.cross(v1, v2)
    norm_len = np.linalg.norm(normal)
    
    if norm_len < 1e-6:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up
    
    return (normal / norm_len).astype(np.float32)


def write_interpolated_data_to_frame(gp_obj, target_frame_num, all_interpolated_data, target_layer_idx):
    """
    Writes interpolated data to frame attributes.
    Populates with original data first, then overwrites with interpolation.
    """
    try:
        layer_cache = cache.cache['layers'].get(target_layer_idx)
        if not layer_cache or target_frame_num not in layer_cache['frame_lookup']:
            return
        
        frame = layer_cache['frame_lookup'][target_frame_num]
        if frame is None:
            return
        
        drawing = frame.drawing
        if drawing is None:
            return
        
        if not hasattr(drawing, 'strokes') or drawing.strokes is None:
            return
        
        actual_points = sum(len(s.points) for s in drawing.strokes)
        if actual_points == 0:
            return
        
        all_attrs = ['position', 'opacity', 'radius', 'handle_left', 'handle_right']
        write_operations = []
        
        for attr_type in all_attrs:
            attr_name = f"{attr_type}_i"
            original_attr_name = attr_type
            
            if attr_name not in drawing.attributes:
                continue
            
            attr = drawing.attributes[attr_name]
            
            has_interpolation = (all_interpolated_data and 
                               attr_type in all_interpolated_data and 
                               all_interpolated_data[attr_type])
            
            if has_interpolation:
                data_list = all_interpolated_data[attr_type]
                flat_list = [item for sublist in data_list for item in sublist]
            
                if attr_type == 'position' or attr_type.startswith('handle_'):
                    expected_size = actual_points * 3
                    set_method = 'vector'
                else:
                    expected_size = actual_points
                    set_method = 'value'
                
                if len(flat_list) == expected_size:
                    write_operations.append((attr, set_method, flat_list))
                elif len(flat_list) < expected_size:
                    if original_attr_name in drawing.attributes:
                        original_attr = drawing.attributes[original_attr_name]
                        if attr_type == 'position' or attr_type.startswith('handle_'):
                            original_data = np.empty(actual_points * 3, dtype=np.float32)
                            original_attr.data.foreach_get('vector', original_data)
                        else:
                            original_data = np.empty(actual_points, dtype=np.float32)
                            original_attr.data.foreach_get('value', original_data)
                        
                        padded_data = flat_list + original_data[len(flat_list):].tolist()
                        write_operations.append((attr, set_method, padded_data))
                else:
                    write_operations.append((attr, set_method, flat_list[:expected_size]))
            else:
                if original_attr_name in drawing.attributes:
                    original_attr = drawing.attributes[original_attr_name]
                    
                    if attr_type == 'position' or attr_type.startswith('handle_'):
                        original_data = np.empty(actual_points * 3, dtype=np.float32)
                        original_attr.data.foreach_get('vector', original_data)
                        write_operations.append((attr, 'vector', original_data.tolist()))
                    else:
                        original_data = np.empty(actual_points, dtype=np.float32)
                        original_attr.data.foreach_get('value', original_data)
                        write_operations.append((attr, 'value', original_data.tolist()))
        
        for attr, method, data in write_operations:
            attr.data.foreach_set(method, data)

    except Exception as e:
        print(f"[GPAI] ERROR Writing Attributes: {e}")


def process(context):
    """
    Main interpolation processing function.
    Only processes layers that need interpolation at current frame.
    """
    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return

    try:
        # Check cache validity
        if cache.cache.get('signature') != cache.get_signature(gp_obj):
            cache.build(gp_obj)

        if not cache.cache or not cache.cache.get('layers'):
            return

        interpolator = cpp_module.get_interpolator()
        current_frame = context.scene.frame_current
        
        # Find layers that need interpolation
        layers_to_process = []
        
        for layer_idx, layer_cache in cache.cache['layers'].items():
            if len(layer_cache['sorted_frames']) < 2:
                continue
            
            sorted_frames = layer_cache['sorted_frames']
            
            prev_frame = None
            next_frame = None
            
            for frame_num in sorted_frames:
                if frame_num <= current_frame:
                    prev_frame = frame_num
                elif frame_num > current_frame and next_frame is None:
                    next_frame = frame_num
                    break
            
            if prev_frame is not None and next_frame is not None:
                layers_to_process.append((layer_idx, layer_cache, prev_frame, next_frame))
        
        # Process each layer
        for layer_idx, layer_cache, prev_frame, next_frame in layers_to_process:
            keyframes = layer_cache['keyframes']
            prev_strokes = keyframes[prev_frame]
            next_strokes = keyframes[next_frame]
            
            # Get easing curve
            easing_curve = layer_cache['easing_data'].get(prev_frame, None)
            if easing_curve is None:
                from ..utils import easing
                easing_curve = easing.sample_easing_preset('LINEAR')
            
            easing_samples = np.array(easing_curve, dtype=np.float32)
            
            # Get arc parameters (arc_amount, arc_direction, curvature_blend, use_spiral)
            arc_params = layer_cache['arc_data'].get(prev_frame, (0.0, 0.0, 0.0, True))
            arc_amount = arc_params[0]
            arc_direction = arc_params[1]
            # curvature_blend removed - always 0.0
            use_spiral = arc_params[3]
            
            all_interpolated_data = {
                'position': [],
                'opacity': [],
                'radius': [],
                'handle_left': [],
                'handle_right': []
            }
            
            # Pair strokes using match_id
            # prev_stroke.match_id = index of the corresponding stroke in next_strokes
            for stroke_idx, prev_stroke in enumerate(prev_strokes):
                match_id = prev_stroke.get('match_id', stroke_idx)
                
                # match_id directly tells us which stroke in next_strokes to pair with
                if 0 <= match_id < len(next_strokes):
                    next_stroke = next_strokes[match_id]
                else:
                    continue  # No matching stroke (out of bounds)
                
                prev_positions = prev_stroke['position'] if isinstance(prev_stroke, dict) else prev_stroke
                next_positions = next_stroke['position'] if isinstance(next_stroke, dict) else next_stroke
                
                # Calculate stroke normal for 3D arc direction
                stroke_normal = calculate_stroke_normal(prev_positions)
                
                # Process position with advanced interpolation (arc)
                if arc_amount > 0.001:
                    # Use advanced interpolation with arc
                    interpolated_positions = interpolator.process_interpolation_advanced(
                        current_frame,
                        prev_frame, prev_positions,
                        next_frame, next_positions,
                        stroke_idx,
                        "position",
                        easing_samples,
                        arc_amount,
                        arc_direction,
                        0.0,  # curvature_blend always 0
                        use_spiral,
                        stroke_normal
                    )
                else:
                    # Use basic interpolation (backward compatible)
                    interpolated_positions = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_positions,
                        next_frame, next_positions,
                        stroke_idx,
                        "position",
                        easing_samples
                    )
                
                if interpolated_positions is not None and interpolated_positions.size > 0:
                    all_interpolated_data['position'].append(interpolated_positions)
                    
                    # Process opacity
                    if (isinstance(prev_stroke, dict) and 'opacity' in prev_stroke and 
                        isinstance(next_stroke, dict) and 'opacity' in next_stroke):
                        interpolated_opacity = interpolator.process_interpolation(
                            current_frame,
                            prev_frame, prev_stroke['opacity'],
                            next_frame, next_stroke['opacity'],
                            stroke_idx,
                            "opacity",
                            easing_samples
                        )
                        if interpolated_opacity is not None and interpolated_opacity.size > 0:
                            all_interpolated_data['opacity'].append(interpolated_opacity)
                    
                    # Process radius
                    if (isinstance(prev_stroke, dict) and 'radius' in prev_stroke and 
                        isinstance(next_stroke, dict) and 'radius' in next_stroke):
                        interpolated_radius = interpolator.process_interpolation(
                            current_frame,
                            prev_frame, prev_stroke['radius'],
                            next_frame, next_stroke['radius'],
                            stroke_idx,
                            "radius",
                            easing_samples
                        )
                        if interpolated_radius is not None and interpolated_radius.size > 0:
                            all_interpolated_data['radius'].append(interpolated_radius)
                    
                    # Process handles (simplified - no point count mismatch handling for now)
                    if (isinstance(prev_stroke, dict) and 'handle_left' in prev_stroke and 
                        isinstance(next_stroke, dict) and 'handle_left' in next_stroke):
                        
                        prev_points = len(prev_stroke['handle_left']) // 3
                        next_points = len(next_stroke['handle_left']) // 3
                        
                        if prev_points == next_points:
                            interpolated_handle_left = interpolator.process_interpolation(
                                current_frame,
                                prev_frame, prev_stroke['handle_left'],
                                next_frame, next_stroke['handle_left'],
                                stroke_idx,
                                "position",
                                easing_samples
                            )
                            if interpolated_handle_left is not None and interpolated_handle_left.size > 0:
                                all_interpolated_data['handle_left'].append(interpolated_handle_left)
                    
                    if (isinstance(prev_stroke, dict) and 'handle_right' in prev_stroke and 
                        isinstance(next_stroke, dict) and 'handle_right' in next_stroke):
                        
                        prev_points = len(prev_stroke['handle_right']) // 3
                        next_points = len(next_stroke['handle_right']) // 3
                        
                        if prev_points == next_points:
                            interpolated_handle_right = interpolator.process_interpolation(
                                current_frame,
                                prev_frame, prev_stroke['handle_right'],
                                next_frame, next_stroke['handle_right'],
                                stroke_idx,
                                "position",
                                easing_samples
                            )
                            if interpolated_handle_right is not None and interpolated_handle_right.size > 0:
                                all_interpolated_data['handle_right'].append(interpolated_handle_right)
            
            write_interpolated_data_to_frame(gp_obj, prev_frame, all_interpolated_data, layer_idx)
                        
    except Exception as e:
        import traceback
        print(f"Interpolation Failed: {e}")
        traceback.print_exc()
