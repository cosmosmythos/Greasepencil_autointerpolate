
import bpy
from bisect import bisect_right
import numpy as np
from . import cpp_module
from . import cache


def calculate_stroke_normal(positions):
    point_count = len(positions) // 3
    if point_count < 3:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up

    mid_idx = (point_count // 2) * 3
    p0x, p0y, p0z = positions[0], positions[1], positions[2]
    pmx, pmy, pmz = positions[mid_idx], positions[mid_idx + 1], positions[mid_idx + 2]
    pex, pey, pez = positions[-3], positions[-2], positions[-1]

    v1x, v1y, v1z = pmx - p0x, pmy - p0y, pmz - p0z
    v2x, v2y, v2z = pex - p0x, pey - p0y, pez - p0z

    nx = v1y * v2z - v1z * v2y
    ny = v1z * v2x - v1x * v2z
    nz = v1x * v2y - v1y * v2x
    norm_len = (nx * nx + ny * ny + nz * nz) ** 0.5

    if norm_len < 1e-6:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up

    return np.array([nx / norm_len, ny / norm_len, nz / norm_len], dtype=np.float32)


def write_interpolated_data_to_frame(gp_obj, target_frame_num,
                                     all_interpolated_data, target_layer_idx):
    try:
        cache.begin_runtime_update(gp_obj.name)
        obj_cache = cache.get_cache(gp_obj.name)
        layer_cache = obj_cache.get('layers', {}).get(target_layer_idx)
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

            is_vector = (attr_type == 'position' or attr_type.startswith('handle_'))

            if has_interpolation:
                data_list = all_interpolated_data[attr_type]
                flat = np.concatenate(data_list).astype(np.float32)

                if is_vector:
                    expected_size = actual_points * 3
                    set_method = 'vector'
                else:
                    expected_size = actual_points
                    set_method = 'value'

                if len(flat) == expected_size:
                    write_operations.append((attr, set_method, flat))
                elif len(flat) < expected_size:
                    if original_attr_name in drawing.attributes:
                        original_attr = drawing.attributes[original_attr_name]
                        original_data = np.empty(expected_size, dtype=np.float32)
                        original_attr.data.foreach_get(set_method, original_data)
                        original_data[:len(flat)] = flat
                        write_operations.append((attr, set_method, original_data))
                else:
                    write_operations.append((attr, set_method, flat[:expected_size]))
            else:
                if original_attr_name in drawing.attributes:
                    original_attr = drawing.attributes[original_attr_name]
                    if is_vector:
                        original_data = np.empty(actual_points * 3, dtype=np.float32)
                        original_attr.data.foreach_get('vector', original_data)
                        write_operations.append((attr, 'vector', original_data))
                    else:
                        original_data = np.empty(actual_points, dtype=np.float32)
                        original_attr.data.foreach_get('value', original_data)
                        write_operations.append((attr, 'value', original_data))

        for attr, method, data in write_operations:
            attr.data.foreach_set(method, data)

    except Exception as e:
        print(f"[GPAI] ERROR Writing Attributes: {e}")
    finally:
        cache.end_runtime_update(gp_obj.name)


def process_object(gp_obj, current_frame):
    obj_name = gp_obj.name
    try:
        if cache.is_dirty(obj_name):
            cache.build(gp_obj)

        obj_cache = cache.get_cache(obj_name)
        if not obj_cache or not obj_cache.get('layers'):
            cache.build(gp_obj)
            obj_cache = cache.get_cache(obj_name)
            if not obj_cache or not obj_cache.get('layers'):
                return

        interpolator = cpp_module.get_interpolator()

        layers_to_process = []

        for layer_idx, layer_cache in obj_cache['layers'].items():
            if len(layer_cache['sorted_frames']) < 2:
                continue

            sorted_frames = layer_cache['sorted_frames']
            next_idx = bisect_right(sorted_frames, current_frame)
            prev_idx = next_idx - 1

            prev_frame = sorted_frames[prev_idx] if prev_idx >= 0 else None
            next_frame = sorted_frames[next_idx] if next_idx < len(sorted_frames) else None

            if prev_frame is not None and next_frame is not None:
                layers_to_process.append(
                    (layer_idx, layer_cache, prev_frame, next_frame))

        for layer_idx, layer_cache, prev_frame, next_frame in layers_to_process:
            if current_frame == prev_frame or current_frame == next_frame:
                continue
            keyframes = layer_cache['keyframes']
            prev_strokes = keyframes[prev_frame]
            next_strokes = keyframes[next_frame]

            easing_samples = layer_cache.get('easing_samples', {}).get(prev_frame)
            if easing_samples is None:
                easing_curve = layer_cache['easing_data'].get(prev_frame, None)
                if easing_curve is None:
                    from ..utils import easing
                    easing_curve = easing.sample_easing_preset('LINEAR')
                easing_samples = np.array(easing_curve, dtype=np.float32)
            else:
                easing_samples = easing_samples.copy()

            if np.any(np.isnan(easing_samples)) or np.any(np.isinf(easing_samples)):
                easing_samples = np.nan_to_num(easing_samples, nan=0.0,
                                                posinf=1.0, neginf=0.0)

            arc_params = layer_cache['arc_data'].get(
                prev_frame, (0.0, 0.0, 0.0, True))
            arc_amount = arc_params[0]
            arc_direction = arc_params[1]
            use_spiral = arc_params[3]

            all_interpolated_data = {
                'position': [],
                'opacity': [],
                'radius': [],
                'handle_left': [],
                'handle_right': [],
            }

            for stroke_idx, prev_stroke in enumerate(prev_strokes):
                if stroke_idx >= len(next_strokes):
                    continue

                next_stroke = next_strokes[stroke_idx]

                prev_positions = prev_stroke['position']
                next_positions = next_stroke['position']

                stroke_normal = calculate_stroke_normal(prev_positions)

                if arc_amount > 0.001:
                    interpolated_positions = interpolator.process_interpolation_advanced(
                        current_frame,
                        prev_frame, prev_positions,
                        next_frame, next_positions,
                        stroke_idx, "position", easing_samples,
                        arc_amount, arc_direction, 0.0,
                        use_spiral, stroke_normal)
                else:
                    interpolated_positions = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_positions,
                        next_frame, next_positions,
                        stroke_idx, "position", easing_samples)

                if interpolated_positions is not None and interpolated_positions.size > 0:
                    all_interpolated_data['position'].append(interpolated_positions)

                    interpolated_opacity = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_stroke['opacity'],
                        next_frame, next_stroke['opacity'],
                        stroke_idx, "opacity", easing_samples)
                    if interpolated_opacity is not None and interpolated_opacity.size > 0:
                        all_interpolated_data['opacity'].append(interpolated_opacity)

                    interpolated_radius = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_stroke['radius'],
                        next_frame, next_stroke['radius'],
                        stroke_idx, "radius", easing_samples)
                    if interpolated_radius is not None and interpolated_radius.size > 0:
                        all_interpolated_data['radius'].append(interpolated_radius)

                    prev_points = len(prev_stroke['handle_left']) // 3
                    next_points = len(next_stroke['handle_left']) // 3

                    if prev_points == next_points and prev_points > 0:
                        interpolated_hl = interpolator.process_interpolation(
                            current_frame,
                            prev_frame, prev_stroke['handle_left'],
                            next_frame, next_stroke['handle_left'],
                            stroke_idx, "position", easing_samples)
                        if interpolated_hl is not None and interpolated_hl.size > 0:
                            all_interpolated_data['handle_left'].append(interpolated_hl)

                    prev_points_r = len(prev_stroke['handle_right']) // 3
                    next_points_r = len(next_stroke['handle_right']) // 3

                    if prev_points_r == next_points_r and prev_points_r > 0:
                        interpolated_hr = interpolator.process_interpolation(
                            current_frame,
                            prev_frame, prev_stroke['handle_right'],
                            next_frame, next_stroke['handle_right'],
                            stroke_idx, "position", easing_samples)
                        if interpolated_hr is not None and interpolated_hr.size > 0:
                            all_interpolated_data['handle_right'].append(interpolated_hr)

            write_interpolated_data_to_frame(
                gp_obj, prev_frame, all_interpolated_data, layer_idx)

    except Exception as e:
        import traceback
        print(f"Interpolation Failed for '{gp_obj.name}': {e}")
        traceback.print_exc()


def process_all(context):
    process_scene(context.scene)


def process_scene(scene):
    from .registry import validate_targets

    targets = validate_targets(scene)
    current_frame = scene.frame_current

    for obj_name in targets:
        gp_obj = bpy.data.objects.get(obj_name)
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            continue
        try:
            process_object(gp_obj, current_frame)
        except Exception as e:
            print(f"[GPAI] Error processing '{obj_name}': {e}")


def process(context):
    process_all(context)
