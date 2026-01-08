"""
Bake System for GP Auto Interpolate
Creates real keyframes from interpolation data - ROBUST VERSION
"""

import bpy
from bpy.types import Operator


def get_selected_keyframe_ranges(gp_obj):
    """
    Get ranges of keyframes to bake for each layer.
    Returns: {layer_idx: [(start, end), (start, end), ...]}
    """
    ranges = {}
    
    for layer_idx, layer in enumerate(gp_obj.data.layers):
        frame_numbers = sorted([f.frame_number for f in layer.frames])
        
        if len(frame_numbers) < 2:
            continue
        
        layer_ranges = []
        
        for i in range(len(frame_numbers) - 1):
            start = frame_numbers[i]
            end = frame_numbers[i + 1]
            
            # Check if start frame is selected
            for frame in layer.frames:
                if frame.frame_number == start and frame.select:
                    if end - start > 1:
                        layer_ranges.append((start, end))
                    break
        
        if layer_ranges:
            ranges[layer_idx] = layer_ranges
    
    return ranges


def get_selected_keyframe_ranges_active_only(gp_obj, active_layer_idx):
    """
    Get ranges of keyframes to bake for ACTIVE layer only.
    Returns: [(start, end), (start, end), ...]
    """
    layer = gp_obj.data.layers[active_layer_idx]
    frame_numbers = sorted([f.frame_number for f in layer.frames])
    
    if len(frame_numbers) < 2:
        return []
    
    layer_ranges = []
    
    for i in range(len(frame_numbers) - 1):
        start = frame_numbers[i]
        end = frame_numbers[i + 1]
        
        # Check if start frame is selected
        for frame in layer.frames:
            if frame.frame_number == start and frame.select:
                if end - start > 1:
                    layer_ranges.append((start, end))
                break
    
    return layer_ranges


def deselect_all_frames(gp_obj):
    """Deselect all frames on all layers"""
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            frame.select = False


def duplicate_frame_safely(context, gp_obj, frame_num):
    """Safely duplicate frame - deselects all first to avoid crashes"""
    try:
        deselect_all_frames(gp_obj)
        context.scene.frame_set(frame_num)
        bpy.ops.grease_pencil.frame_duplicate()
        return True
    except (RuntimeError, Exception) as e:
        print(f"[GPAI] Frame duplication failed at {frame_num}: {e}")
        return False


def set_frame_to_jitter(layer, frame_num):
    """Set a frame's keyframe type to JITTER"""
    for frame in layer.frames:
        if frame.frame_number == frame_num:
            frame.keyframe_type = 'JITTER'
            return True
    return False


# Import shared baking utility
from ..core.bake_utils import apply_interpolation_to_frame


class GP_OT_BakeSelectedRange(Operator):
    """Bake interpolation for selected keyframe ranges"""
    bl_idname = "gp.bake_selected_range"
    bl_label = "Bake Selected Range"
    bl_description = "Bake interpolation between selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if not (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and
                context.scene.gp_interpolation_enabled):
            return False
        
        # Only allow if ACTIVE layer has selected keyframes
        gp_obj = context.active_object
        active_layer = gp_obj.data.layers.active
        
        if not active_layer:
            return False
            
        # Check if active layer has selected keyframes
        return any(f.select for f in active_layer.frames)
    
    def execute(self, context):
        gp_obj = context.active_object
        active_layer = gp_obj.data.layers.active
        
        if not active_layer:
            self.report({'ERROR'}, "No active layer")
            return {'CANCELLED'}
        
        # Find active layer index
        layer_idx = None
        for idx, layer in enumerate(gp_obj.data.layers):
            if layer == active_layer:
                layer_idx = idx
                break
                
        if layer_idx is None:
            self.report({'ERROR'}, "Could not find active layer index")
            return {'CANCELLED'}
        
        # Get selected ranges for ACTIVE layer only
        ranges = get_selected_keyframe_ranges_active_only(gp_obj, layer_idx)
        
        if not ranges:
            self.report({'WARNING'}, "No selected keyframe ranges found in active layer")
            return {'CANCELLED'}
        
        # Build complete list of frames to create with stepping
        work_list = []  # [(layer_idx, frame_num, start_frame, end_frame), ...]
        
        layer = gp_obj.data.layers[layer_idx]
        step = context.scene.gp_bake_step
        
        for start_frame, end_frame in ranges:
            # Generate frames based on step (Option B: even frame numbers)
            if step == 1:
                # Every frame
                target_frames = range(start_frame + 1, end_frame)
            else:
                # Step-based: find frames that align with step pattern
                target_frames = []
                for frame_num in range(start_frame + 1, end_frame):
                    if frame_num % step == 0:  # Even multiples (2s, 3s, etc.)
                        target_frames.append(frame_num)
            
            for frame_num in target_frames:
                # Check if frame exists
                exists = any(f.frame_number == frame_num for f in layer.frames)
                if not exists:
                    work_list.append((layer_idx, frame_num, start_frame, end_frame))
        
        print(f"[BAKE] Frames to create: {len(work_list)}")
        
        if not work_list:
            self.report({'WARNING'}, "No frames to create")
            return {'CANCELLED'}
        
        # STEP 2: Deselect everything to avoid crashes
        print("[BAKE] Deselecting all frames...")
        deselect_all_frames(gp_obj)
        
        # STEP 3: Batch frame creation (optimized)
        print("[BAKE] Creating frames in batch...")
        created_frames = []
        
        # CRITICAL FIX: Temporarily disable interpolation to prevent cache rebuilds
        interpolation_was_enabled = context.scene.gp_interpolation_enabled
        if interpolation_was_enabled:
            context.scene.gp_interpolation_enabled = False
        
        # Group frames by their source frame for more efficient duplication
        current_source = None
        for layer_idx, frame_num, start_frame, end_frame in work_list:
            # Only set frame if we need to switch source
            if current_source != start_frame:
                context.scene.frame_set(start_frame)
                current_source = start_frame
            
            # Quick frame duplication without repeated frame_set calls
            try:
                deselect_all_frames(gp_obj)
                context.scene.frame_set(frame_num)
                bpy.ops.grease_pencil.frame_duplicate()
                created_frames.append((layer_idx, frame_num, start_frame, end_frame))
            except Exception as e:
                print(f"[GPAI] Frame {frame_num} duplication failed: {e}")
        
        # Re-enable interpolation
        if interpolation_was_enabled:
            context.scene.gp_interpolation_enabled = True
        
        if not created_frames:
            self.report({'WARNING'}, "Failed to create frames")
            return {'CANCELLED'}
        
        # STEP 4: Batch interpolation processing (major optimization)
        from ..core import cpp_module, cache
        from ..utils import easing
        import numpy as np
        
        if cpp_module.interpolator_module is None:
            self.report({'ERROR'}, "C++ module not loaded")
            return {'CANCELLED'}
        
        interpolator = cpp_module.get_interpolator()
        gpa_cache = cache.cache
        
        # Group frames by their start/end pair to minimize cache lookups
        frame_groups = {}
        for layer_idx, frame_num, start_frame, end_frame in created_frames:
            key = (layer_idx, start_frame, end_frame)
            if key not in frame_groups:
                frame_groups[key] = []
            frame_groups[key].append(frame_num)
        
        interpolated_count = 0
        
        # Process each group (same start/end pair) together
        for (layer_idx, start_frame, end_frame), frame_list in frame_groups.items():
            layer = gp_obj.data.layers[layer_idx]
            layer_cache = gpa_cache.get('layers', {}).get(layer_idx)
            
            if not layer_cache:
                continue
            
            keyframes = layer_cache.get('keyframes', {})
            
            if start_frame not in keyframes or end_frame not in keyframes:
                continue
            
            # Cache these lookups once per group
            prev_strokes = keyframes[start_frame]
            next_strokes = keyframes[end_frame]
            easing_curve = layer_cache.get('easing_data', {}).get(start_frame)
            if easing_curve is None:
                easing_curve = easing.sample_easing_preset('LINEAR')
            easing_samples = np.array(easing_curve, dtype=np.float32)
            
            # Get arc parameters from cache
            from ..core.bake_utils import get_arc_params_for_baking, calculate_stroke_normal
            arc_amount, arc_direction, use_spiral = get_arc_params_for_baking(layer_cache, start_frame)
            
            # Pre-convert stroke data to numpy arrays once
            stroke_data_cache = []
            
            # Build Match_ID lookup for next_strokes
            next_by_match_id = {}
            for idx, stroke in enumerate(next_strokes):
                match_id = stroke.get('match_id', idx)
                next_by_match_id[match_id] = idx
            
            # Pair strokes using Match_ID (includes FTP-SC matches and position-based fallback)
            for stroke_idx, prev_stroke in enumerate(prev_strokes):
                match_id = prev_stroke.get('match_id', stroke_idx)
                
                # Find matching stroke by Match_ID
                if match_id in next_by_match_id:
                    next_stroke = next_strokes[next_by_match_id[match_id]]
                else:
                    continue  # No matching stroke (out of bounds)
                
                stroke_cache = {
                    'prev_pos': np.array(prev_stroke['position'], dtype=np.float32),
                    'next_pos': np.array(next_stroke['position'], dtype=np.float32)
                }
                
                # Calculate stroke normal for arc interpolation
                if arc_amount > 0.001:
                    stroke_cache['stroke_normal'] = calculate_stroke_normal(stroke_cache['prev_pos'])
                
                # Cache opacity if available
                if 'opacity' in prev_stroke and 'opacity' in next_stroke:
                    stroke_cache['prev_op'] = np.array(prev_stroke['opacity'], dtype=np.float32)
                    stroke_cache['next_op'] = np.array(next_stroke['opacity'], dtype=np.float32)
                
                # Cache radius if available
                if 'radius' in prev_stroke and 'radius' in next_stroke:
                    stroke_cache['prev_rad'] = np.array(prev_stroke['radius'], dtype=np.float32)
                    stroke_cache['next_rad'] = np.array(next_stroke['radius'], dtype=np.float32)
                
                stroke_data_cache.append(stroke_cache)
            
            # Process all frames in this group
            for frame_num in frame_list:
                # Combine all stroke data into single arrays for final attributes
                all_positions = []
                all_opacities = []
                all_radii = []
                
                # Interpolate all strokes for this frame and collect data
                for stroke_idx, stroke_cache in enumerate(stroke_data_cache):
                    
                    # Position (use advanced interpolation if arc is enabled)
                    if arc_amount > 0.001 and 'stroke_normal' in stroke_cache:
                        positions = interpolator.process_interpolation_advanced(
                            frame_num, start_frame, stroke_cache['prev_pos'], 
                            end_frame, stroke_cache['next_pos'],
                            stroke_idx, "position", easing_samples,
                            arc_amount, arc_direction, 0.0, use_spiral, stroke_cache['stroke_normal']
                        )
                    else:
                        positions = interpolator.process_interpolation(
                            frame_num, start_frame, stroke_cache['prev_pos'], 
                            end_frame, stroke_cache['next_pos'],
                            stroke_idx, "position", easing_samples
                        )
                    if positions is not None:
                        all_positions.extend(positions)
                    
                    # Opacity (if cached)
                    if 'prev_op' in stroke_cache and 'next_op' in stroke_cache:
                        opacities = interpolator.process_interpolation(
                            frame_num, start_frame, stroke_cache['prev_op'],
                            end_frame, stroke_cache['next_op'],
                            stroke_idx, "opacity", easing_samples
                        )
                        if opacities is not None:
                            all_opacities.extend(opacities)
                    
                    # Radius (if cached)
                    if 'prev_rad' in stroke_cache and 'next_rad' in stroke_cache:
                        radii = interpolator.process_interpolation(
                            frame_num, start_frame, stroke_cache['prev_rad'],
                            end_frame, stroke_cache['next_rad'],
                            stroke_idx, "radius", easing_samples
                        )
                        if radii is not None:
                            all_radii.extend(radii)
                
                # Prepare combined data for final attributes
                combined_data = {0: {}}  # Use index 0 for all combined data
                if all_positions:
                    combined_data[0]['position'] = all_positions
                if all_opacities:
                    combined_data[0]['opacity'] = all_opacities
                if all_radii:
                    combined_data[0]['radius'] = all_radii
                
                # Apply to frame using optimized foreach_set
                if apply_interpolation_to_frame(gp_obj, layer_idx, frame_num, combined_data):
                    interpolated_count += 1
        
        # Set frames to JITTER type
        for layer_idx, frame_num, _, _ in created_frames:
            layer = gp_obj.data.layers[layer_idx]
            set_frame_to_jitter(layer, frame_num)
        
        if interpolated_count > 0:
            self.report({'INFO'}, f"Baked {interpolated_count} interpolated frame(s)")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No frames were interpolated")
            return {'CANCELLED'}


def register():
    try:
        bpy.utils.unregister_class(GP_OT_BakeSelectedRange)
    except RuntimeError:
        pass
    bpy.utils.register_class(GP_OT_BakeSelectedRange)


def unregister():
    try:
        bpy.utils.unregister_class(GP_OT_BakeSelectedRange)
    except RuntimeError:
        pass
