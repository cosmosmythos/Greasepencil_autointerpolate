
import bpy
from bpy.types import Operator


def get_selected_keyframe_ranges(gp_obj):
    ranges = {}

    for layer_idx, layer in enumerate(gp_obj.data.layers):
        frame_numbers = sorted([f.frame_number for f in layer.frames])

        if len(frame_numbers) < 2:
            continue

        layer_ranges = []

        for i in range(len(frame_numbers) - 1):
            start = frame_numbers[i]
            end = frame_numbers[i + 1]


            for frame in layer.frames:
                if frame.frame_number == start and frame.select:
                    if end - start > 1:
                        layer_ranges.append((start, end))
                    break

        if layer_ranges:
            ranges[layer_idx] = layer_ranges

    return ranges


def deselect_all_frames(gp_obj):
    for layer in gp_obj.data.layers:
        for frame in layer.frames:
            frame.select = False


def set_frame_to_BREAKDOWN(layer, frame_num):
    for frame in layer.frames:
        if frame.frame_number == frame_num:
            frame.keyframe_type = 'BREAKDOWN'
            return True
    return False



from ..core.bake_utils import apply_interpolation_to_frame


class GP_OT_BakeSelectedRange(Operator):
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


        gp_obj = context.active_object
        for layer in gp_obj.data.layers:
            if any(f.select for f in layer.frames):
                return True
        return False

    def execute(self, context):
        gp_obj = context.active_object


        original_active_layer = gp_obj.data.layers.active


        all_ranges = get_selected_keyframe_ranges(gp_obj)

        if not all_ranges:
            self.report({'WARNING'}, "No selected keyframe ranges found")
            return {'CANCELLED'}


        work_list = []
        step = context.scene.gp_bake_step

        for layer_idx, ranges in all_ranges.items():
            layer = gp_obj.data.layers[layer_idx]

            for start_frame, end_frame in ranges:

                if step == 1:
                    # Every frame
                    target_frames = range(start_frame + 1, end_frame)
                else:

                    target_frames = []
                    for frame_num in range(start_frame + 1, end_frame):
                        if frame_num % step == 0:
                            target_frames.append(frame_num)

                for frame_num in target_frames:

                    exists = any(f.frame_number == frame_num for f in layer.frames)
                    if not exists:
                        work_list.append((layer_idx, frame_num, start_frame, end_frame))

        if not work_list:
            self.report({'WARNING'}, "No frames to create")
            return {'CANCELLED'}


        deselect_all_frames(gp_obj)


        created_frames = []


        interpolation_was_enabled = context.scene.gp_interpolation_enabled
        if interpolation_was_enabled:
            context.scene.gp_interpolation_enabled = False


        current_source = None
        current_layer_idx = None
        for layer_idx, frame_num, start_frame, end_frame in work_list:

            if current_layer_idx != layer_idx:
                gp_obj.data.layers.active = gp_obj.data.layers[layer_idx]
                current_layer_idx = layer_idx
                current_source = None


            if current_source != start_frame:
                context.scene.frame_set(start_frame)
                current_source = start_frame


            try:
                deselect_all_frames(gp_obj)
                context.scene.frame_set(frame_num)
                bpy.ops.grease_pencil.frame_duplicate()
                created_frames.append((layer_idx, frame_num, start_frame, end_frame))
            except Exception as e:
                print(f"[GPAI] Frame {frame_num} duplication failed: {e}")


        if interpolation_was_enabled:
            context.scene.gp_interpolation_enabled = True

        if not created_frames:
            self.report({'WARNING'}, "Failed to create frames")
            return {'CANCELLED'}


        from ..core import cpp_module, cache
        from ..utils import easing
        import numpy as np

        if cpp_module.interpolator_module is None:
            self.report({'ERROR'}, "C++ module not loaded")
            return {'CANCELLED'}

        interpolator = cpp_module.get_interpolator()
        gpa_cache = cache.get_cache(gp_obj.name)


        frame_groups = {}
        for layer_idx, frame_num, start_frame, end_frame in created_frames:
            key = (layer_idx, start_frame, end_frame)
            if key not in frame_groups:
                frame_groups[key] = []
            frame_groups[key].append(frame_num)

        interpolated_count = 0


        for (layer_idx, start_frame, end_frame), frame_list in frame_groups.items():
            layer = gp_obj.data.layers[layer_idx]
            layer_cache = gpa_cache.get('layers', {}).get(layer_idx)

            if not layer_cache:
                continue

            keyframes = layer_cache.get('keyframes', {})

            if start_frame not in keyframes or end_frame not in keyframes:
                continue


            prev_strokes = keyframes[start_frame]
            next_strokes = keyframes[end_frame]
            easing_curve = layer_cache.get('easing_data', {}).get(start_frame)
            if easing_curve is None:
                easing_curve = easing.sample_easing_preset('LINEAR')
            easing_samples = np.array(easing_curve, dtype=np.float32)


            from ..core.bake_utils import get_arc_params_for_baking, calculate_stroke_normal
            arc_amount, arc_direction, use_spiral = get_arc_params_for_baking(layer_cache, start_frame)


            stroke_data_cache = []


            for stroke_idx, prev_stroke in enumerate(prev_strokes):

                if stroke_idx >= len(next_strokes):
                    continue

                next_stroke = next_strokes[stroke_idx]

                stroke_cache = {
                    'prev_pos': np.array(prev_stroke['position'], dtype=np.float32),
                    'next_pos': np.array(next_stroke['position'], dtype=np.float32)
                }


                if arc_amount > 0.001:
                    stroke_cache['stroke_normal'] = calculate_stroke_normal(stroke_cache['prev_pos'])


                if 'opacity' in prev_stroke and 'opacity' in next_stroke:
                    stroke_cache['prev_op'] = np.array(prev_stroke['opacity'], dtype=np.float32)
                    stroke_cache['next_op'] = np.array(next_stroke['opacity'], dtype=np.float32)


                if 'radius' in prev_stroke and 'radius' in next_stroke:
                    stroke_cache['prev_rad'] = np.array(prev_stroke['radius'], dtype=np.float32)
                    stroke_cache['next_rad'] = np.array(next_stroke['radius'], dtype=np.float32)


                if 'handle_left' in prev_stroke and 'handle_left' in next_stroke:
                    prev_hl = np.array(prev_stroke['handle_left'], dtype=np.float32)
                    next_hl = np.array(next_stroke['handle_left'], dtype=np.float32)
                    if len(prev_hl) == len(next_hl):
                        stroke_cache['prev_hl'] = prev_hl
                        stroke_cache['next_hl'] = next_hl


                if 'handle_right' in prev_stroke and 'handle_right' in next_stroke:
                    prev_hr = np.array(prev_stroke['handle_right'], dtype=np.float32)
                    next_hr = np.array(next_stroke['handle_right'], dtype=np.float32)
                    if len(prev_hr) == len(next_hr):
                        stroke_cache['prev_hr'] = prev_hr
                        stroke_cache['next_hr'] = next_hr

                stroke_data_cache.append(stroke_cache)


            for frame_num in frame_list:

                all_positions = []
                all_opacities = []
                all_radii = []
                all_handle_lefts = []
                all_handle_rights = []


                for stroke_idx, stroke_cache in enumerate(stroke_data_cache):


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


                    if 'prev_hl' in stroke_cache and 'next_hl' in stroke_cache:
                        handle_lefts = interpolator.process_interpolation(
                            frame_num, start_frame, stroke_cache['prev_hl'],
                            end_frame, stroke_cache['next_hl'],
                            stroke_idx, "handle_left", easing_samples
                        )
                        if handle_lefts is not None:
                            all_handle_lefts.extend(handle_lefts)


                    if 'prev_hr' in stroke_cache and 'next_hr' in stroke_cache:
                        handle_rights = interpolator.process_interpolation(
                            frame_num, start_frame, stroke_cache['prev_hr'],
                            end_frame, stroke_cache['next_hr'],
                            stroke_idx, "handle_right", easing_samples
                        )
                        if handle_rights is not None:
                            all_handle_rights.extend(handle_rights)


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


                if apply_interpolation_to_frame(gp_obj, layer_idx, frame_num, combined_data):
                    interpolated_count += 1


        for layer_idx, frame_num, _, _ in created_frames:
            layer = gp_obj.data.layers[layer_idx]
            set_frame_to_BREAKDOWN(layer, frame_num)


        if original_active_layer:
            gp_obj.data.layers.active = original_active_layer

        if interpolated_count > 0:
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
