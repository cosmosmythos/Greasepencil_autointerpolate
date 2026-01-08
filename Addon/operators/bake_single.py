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
        if not context.active_object or context.active_object.type != 'GREASEPENCIL':
            return False
        
        scene = context.scene
        current_frame = scene.frame_current
        
        if not scene.gp_interpolation_enabled:
            return False
        
        gp_obj = context.active_object
        target_name = scene.get("gp_interpolation_target", "")
        
        if not target_name or gp_obj.name != target_name:
            return False
        
        # Check if there's an active layer
        active_layer = gp_obj.data.layers.active
        if active_layer is None:
            return False
        
        # Check if current frame is already a keyframe in the ACTIVE layer
        for frame in active_layer.frames:
            if frame.frame_number == current_frame:
                return False
        
        # Find active layer index for range check
        layer_idx = None
        for idx, layer in enumerate(gp_obj.data.layers):
            if layer == active_layer:
                layer_idx = idx
                break
        
        if layer_idx is None:
            return False
        
        # Check if current frame is between keyframes in active layer
        start_frame, end_frame = find_interpolation_range_for_frame(gp_obj, layer_idx, current_frame)
        
        if start_frame is None or end_frame is None:
            return False
        
        return True
    
    def execute(self, context):
        """Execute the bake single frame operation using optimized baking system."""
        scene = context.scene
        gp_obj = context.active_object
        current_frame = scene.frame_current
        
        # Get active layer
        active_layer = gp_obj.data.layers.active
        if active_layer is None:
            self.report({'WARNING'}, "No active layer")
            return {'CANCELLED'}
        
        # Find layer index
        layer_idx = None
        for idx, layer in enumerate(gp_obj.data.layers):
            if layer == active_layer:
                layer_idx = idx
                break
        
        if layer_idx is None:
            self.report({'ERROR'}, "Could not find active layer index")
            return {'CANCELLED'}
        
        # Check if current frame is already a keyframe in active layer
        for frame in active_layer.frames:
            if frame.frame_number == current_frame:
                self.report({'INFO'}, f"Frame {current_frame} is already a keyframe in active layer")
                return {'CANCELLED'}
        
        # Find interpolation range for current frame in active layer
        start_frame, end_frame = find_interpolation_range_for_frame(gp_obj, layer_idx, current_frame)
        
        if start_frame is None or end_frame is None:
            self.report({'WARNING'}, f"Frame {current_frame} is not between keyframes in active layer")
            return {'CANCELLED'}
        
        # Temporarily disable interpolation to prevent cache rebuilds
        interpolation_was_enabled = scene.gp_interpolation_enabled
        
        if interpolation_was_enabled:
            scene.gp_interpolation_enabled = False
        
        # Create frame for current frame
        frame_created = duplicate_frame_safely(context, gp_obj, current_frame)
        
        # Re-enable interpolation
        if interpolation_was_enabled:
            scene.gp_interpolation_enabled = True
        
        if not frame_created:
            self.report({'WARNING'}, f"Failed to create frame {current_frame}")
            return {'CANCELLED'}
        
        # CRITICAL FIX: Force scene update to refresh layer.frames collection
        context.view_layer.update()
        
        # Apply interpolation using optimized system
        try:
            from ..core import cpp_module, cache
            from ..utils import easing
            
            if cpp_module.interpolator_module is None:
                self.report({'ERROR'}, "C++ module not loaded")
                return {'CANCELLED'}
            
            interpolator = cpp_module.get_interpolator()
            gpa_cache = cache.cache
            
            layer_cache = gpa_cache.get('layers', {}).get(layer_idx)
            
            if not layer_cache:
                self.report({'WARNING'}, "No cache data for layer")
                return {'CANCELLED'}
            
            keyframes = layer_cache.get('keyframes', {})
            
            if start_frame not in keyframes or end_frame not in keyframes:
                self.report({'WARNING'}, "Missing keyframe data in cache")
                return {'CANCELLED'}
            
            # Get cached stroke data
            prev_strokes = keyframes[start_frame]
            next_strokes = keyframes[end_frame]
            
            # Get easing curve
            easing_curve = layer_cache.get('easing_data', {}).get(start_frame)
            if easing_curve is None:
                easing_curve = easing.sample_easing_preset('LINEAR')
            easing_samples = np.array(easing_curve, dtype=np.float32)
            
            # Get arc parameters from cache
            from ..core.bake_utils import get_arc_params_for_baking, calculate_stroke_normal
            arc_amount, arc_direction, use_spiral = get_arc_params_for_baking(layer_cache, start_frame)
            
            # Interpolate all strokes
            all_positions = []
            all_opacities = []
            all_radii = []
            
            # Pair strokes using match_id
            # prev_stroke.match_id = index of the corresponding stroke in next_strokes
            for stroke_idx, prev_stroke in enumerate(prev_strokes):
                match_id = prev_stroke.get('match_id', stroke_idx)
                
                # match_id directly tells us which stroke in next_strokes to pair with
                if 0 <= match_id < len(next_strokes):
                    next_stroke = next_strokes[match_id]
                else:
                    continue  # No matching stroke (out of bounds)
                
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
            
            # Prepare combined data for final attributes
            combined_data = {0: {}}
            if all_positions:
                combined_data[0]['position'] = all_positions
            if all_opacities:
                combined_data[0]['opacity'] = all_opacities
            if all_radii:
                combined_data[0]['radius'] = all_radii
            
            # Apply to frame using optimized foreach_set
            apply_result = apply_interpolation_to_frame(gp_obj, layer_idx, current_frame, combined_data)
            
            if apply_result:
                # Set frame to JITTER style (like Local does) - use active_layer directly
                for frame in active_layer.frames:
                    if frame.frame_number == current_frame:
                        frame.keyframe_type = 'JITTER'
                        break
                self.report({'INFO'}, f"Baked frame {current_frame} in active layer")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "Failed to apply interpolation data")
                return {'CANCELLED'}
        
        except Exception as e:
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