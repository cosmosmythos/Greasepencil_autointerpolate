"""
Bake Single Frame Operator for GP Auto Interpolate (Optimized)
Uses the same high-performance system as bake_range for consistency and speed.
"""

import bpy
from bpy.types import Operator
import numpy as np


def find_interpolation_range_for_frame(gp_obj, layer_idx, target_frame):
    """Find the keyframe range that contains the target frame for interpolation."""
    layer = gp_obj.data.layers[layer_idx]
    frame_numbers = sorted([f.frame_number for f in layer.frames])
    
    # Find the range containing target_frame
    for i in range(len(frame_numbers) - 1):
        start_frame = frame_numbers[i]
        end_frame = frame_numbers[i + 1]
        
        if start_frame < target_frame < end_frame:
            return start_frame, end_frame
    
    return None, None


def duplicate_frame_safely(context, gp_obj, target_frame):
    """Safely duplicate a frame without triggering cache rebuilds."""
    try:
        # Check if frame already exists in ACTIVE layer only
        active_layer = gp_obj.data.layers.active
        if active_layer:
            for frame in active_layer.frames:
                if frame.frame_number == target_frame:
                    return True  # Frame already exists in active layer
        
        # Duplicate frame (uses current playhead position automatically)
        bpy.ops.grease_pencil.frame_duplicate()
        return True
    except Exception as e:
        print(f"[BAKE_SINGLE] Frame duplication failed: {e}")
        return False


# Import shared baking utility
from ..core.bake_utils import apply_interpolation_to_frame


class GP_OT_bake_single_frame(Operator):
    """Bake interpolation at current frame"""
    bl_idname = "gp.bake_single"
    bl_label = "Bake Single Frame"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        """Check if the operator can be executed."""
        # Simple poll - just check GP object and interpolation enabled
        # Detailed validation happens in execute()
        return (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and
                context.scene.gp_interpolation_enabled)
    
    def execute(self, context):
        """Execute the bake single frame operation using optimized baking system."""
        scene = context.scene
        gp_obj = context.active_object
        current_frame = scene.frame_current
        
        # Store original active layer to restore later
        original_active_layer = gp_obj.data.layers.active
        
        # Determine which layers to process:
        # - If any layers are selected, process those
        # - Otherwise, fallback to active layer only
        selected_layers = [(idx, layer) for idx, layer in enumerate(gp_obj.data.layers) if layer.select]
        
        if not selected_layers:
            # Fallback to active layer
            if original_active_layer is None:
                self.report({'WARNING'}, "No active layer and no layers selected")
                return {'CANCELLED'}
            
            for idx, layer in enumerate(gp_obj.data.layers):
                if layer == original_active_layer:
                    selected_layers = [(idx, layer)]
                    break
        
        # Build work list: layers that have current frame between keyframes
        # and where current frame is not already a keyframe
        work_list = []  # [(layer_idx, start_frame, end_frame), ...]
        
        for layer_idx, layer in selected_layers:
            # Check if current frame is already a keyframe in this layer
            is_keyframe = any(f.frame_number == current_frame for f in layer.frames)
            if is_keyframe:
                continue
            
            # Find interpolation range for current frame
            start_frame, end_frame = find_interpolation_range_for_frame(gp_obj, layer_idx, current_frame)
            
            if start_frame is not None and end_frame is not None:
                work_list.append((layer_idx, start_frame, end_frame))
        
        if not work_list:
            self.report({'WARNING'}, f"Frame {current_frame} is not between keyframes in any selected layer")
            return {'CANCELLED'}
        
        # Temporarily disable interpolation to prevent cache rebuilds
        interpolation_was_enabled = scene.gp_interpolation_enabled
        if interpolation_was_enabled:
            scene.gp_interpolation_enabled = False
        
        # Create frames for all layers in work list
        created_layers = []
        for layer_idx, start_frame, end_frame in work_list:
            # Switch active layer (frame_duplicate works on active layer)
            gp_obj.data.layers.active = gp_obj.data.layers[layer_idx]
            
            if duplicate_frame_safely(context, gp_obj, current_frame):
                created_layers.append((layer_idx, start_frame, end_frame))
        
        # Re-enable interpolation
        if interpolation_was_enabled:
            scene.gp_interpolation_enabled = True
        
        if not created_layers:
            # Restore active layer
            if original_active_layer:
                gp_obj.data.layers.active = original_active_layer
            self.report({'WARNING'}, f"Failed to create frame {current_frame} in any layer")
            return {'CANCELLED'}
        
        # CRITICAL FIX: Force scene update to refresh layer.frames collection
        context.view_layer.update()
        
        # Apply interpolation using optimized system
        try:
            from ..core import cpp_module, cache
            from ..utils import easing
            from ..core.bake_utils import get_arc_params_for_baking, calculate_stroke_normal
            
            if cpp_module.interpolator_module is None:
                if original_active_layer:
                    gp_obj.data.layers.active = original_active_layer
                self.report({'ERROR'}, "C++ module not loaded")
                return {'CANCELLED'}
            
            interpolator = cpp_module.get_interpolator()
            gpa_cache = cache.get_cache(gp_obj.name)
            
            baked_count = 0
            
            for layer_idx, start_frame, end_frame in created_layers:
                layer = gp_obj.data.layers[layer_idx]
                layer_cache = gpa_cache.get('layers', {}).get(layer_idx)
                
                if not layer_cache:
                    print(f"[BAKE_SINGLE] No cache data for layer {layer_idx}")
                    continue
                
                keyframes = layer_cache.get('keyframes', {})
                
                if start_frame not in keyframes or end_frame not in keyframes:
                    print(f"[BAKE_SINGLE] Missing keyframe data in cache for layer {layer_idx}")
                    continue
                
                # Get cached stroke data
                prev_strokes = keyframes[start_frame]
                next_strokes = keyframes[end_frame]
                
                # Get easing curve
                easing_curve = layer_cache.get('easing_data', {}).get(start_frame)
                if easing_curve is None:
                    easing_curve = easing.sample_easing_preset('LINEAR')
                easing_samples = np.array(easing_curve, dtype=np.float32)
                
                # Get arc parameters from cache
                arc_amount, arc_direction, use_spiral = get_arc_params_for_baking(layer_cache, start_frame)
                
                # Interpolate all strokes
                all_positions = []
                all_opacities = []
                all_radii = []
                all_handle_lefts = []
                all_handle_rights = []
                
                # Pair strokes by index (strokes are reordered by correspondence tool to align)
                for stroke_idx, prev_stroke in enumerate(prev_strokes):
                    # Index-based matching: stroke i pairs with stroke i
                    if stroke_idx >= len(next_strokes):
                        continue  # No matching stroke (mismatched stroke count)
                    
                    next_stroke = next_strokes[stroke_idx]
                    
                    # Position (always present)
                    prev_pos = np.array(prev_stroke['position'], dtype=np.float32)
                    next_pos = np.array(next_stroke['position'], dtype=np.float32)
                    
                    # Use advanced interpolation if arc is enabled
                    if arc_amount > 0.001:
                        stroke_normal = calculate_stroke_normal(prev_pos)
                        positions = interpolator.process_interpolation_advanced(
                            current_frame, start_frame, prev_pos,
                            end_frame, next_pos, stroke_idx, "position", easing_samples,
                            arc_amount, arc_direction, 0.0, use_spiral, stroke_normal
                        )
                    else:
                        positions = interpolator.process_interpolation(
                            current_frame, start_frame, prev_pos,
                            end_frame, next_pos, stroke_idx, "position", easing_samples
                        )
                    
                    if positions is not None:
                        all_positions.extend(positions)
                    
                    # Opacity (if available)
                    if 'opacity' in prev_stroke and 'opacity' in next_stroke:
                        prev_op = np.array(prev_stroke['opacity'], dtype=np.float32)
                        next_op = np.array(next_stroke['opacity'], dtype=np.float32)
                        opacities = interpolator.process_interpolation(
                            current_frame, start_frame, prev_op,
                            end_frame, next_op, stroke_idx, "opacity", easing_samples
                        )
                        if opacities is not None:
                            all_opacities.extend(opacities)
                    
                    # Radius (if available)
                    if 'radius' in prev_stroke and 'radius' in next_stroke:
                        prev_rad = np.array(prev_stroke['radius'], dtype=np.float32)
                        next_rad = np.array(next_stroke['radius'], dtype=np.float32)
                        radii = interpolator.process_interpolation(
                            current_frame, start_frame, prev_rad,
                            end_frame, next_rad, stroke_idx, "radius", easing_samples
                        )
                        if radii is not None:
                            all_radii.extend(radii)
                    
                    # Handle Left (if available)
                    if 'handle_left' in prev_stroke and 'handle_left' in next_stroke:
                        prev_hl = np.array(prev_stroke['handle_left'], dtype=np.float32)
                        next_hl = np.array(next_stroke['handle_left'], dtype=np.float32)
                        if len(prev_hl) == len(next_hl):
                            handle_lefts = interpolator.process_interpolation(
                                current_frame, start_frame, prev_hl,
                                end_frame, next_hl, stroke_idx, "handle_left", easing_samples
                            )
                            if handle_lefts is not None:
                                all_handle_lefts.extend(handle_lefts)
                    
                    # Handle Right (if available)
                    if 'handle_right' in prev_stroke and 'handle_right' in next_stroke:
                        prev_hr = np.array(prev_stroke['handle_right'], dtype=np.float32)
                        next_hr = np.array(next_stroke['handle_right'], dtype=np.float32)
                        if len(prev_hr) == len(next_hr):
                            handle_rights = interpolator.process_interpolation(
                                current_frame, start_frame, prev_hr,
                                end_frame, next_hr, stroke_idx, "handle_right", easing_samples
                            )
                            if handle_rights is not None:
                                all_handle_rights.extend(handle_rights)
                
                # Prepare combined data for final attributes
                combined_data = {0: {}}
                if all_positions:
                    combined_data[0]['position'] = all_positions
                if all_opacities:
                    combined_data[0]['opacity'] = all_opacities
                if all_radii:
                    combined_data[0]['radius'] = all_radii
                if all_handle_lefts:
                    combined_data[0]['handle_left'] = all_handle_lefts
                if all_handle_rights:
                    combined_data[0]['handle_right'] = all_handle_rights
                
                # Apply to frame using optimized foreach_set
                apply_result = apply_interpolation_to_frame(gp_obj, layer_idx, current_frame, combined_data)
                
                if apply_result:
                    # Set frame to BREAKDOWN style
                    for frame in layer.frames:
                        if frame.frame_number == current_frame:
                            frame.keyframe_type = 'BREAKDOWN'
                            break
                    baked_count += 1
            
            # Restore original active layer
            if original_active_layer:
                gp_obj.data.layers.active = original_active_layer
            
            if baked_count > 0:
                self.report({'INFO'}, f"Baked frame {current_frame} in {baked_count} layer(s)")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "Failed to apply interpolation data")
                return {'CANCELLED'}
        
        except Exception as e:
            # Restore original active layer on error
            if original_active_layer:
                gp_obj.data.layers.active = original_active_layer
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}


def register():
    try:
        bpy.utils.unregister_class(GP_OT_bake_single_frame)
    except RuntimeError:
        pass
    bpy.utils.register_class(GP_OT_bake_single_frame)


def unregister():
    try:
        bpy.utils.unregister_class(GP_OT_bake_single_frame)
    except RuntimeError:
        pass