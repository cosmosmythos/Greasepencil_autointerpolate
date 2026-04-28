"""
Interpolation Engine for GP Auto Interpolate
Handles real-time interpolation between keyframes.

v2: Multi-object support via process_object() / process_all().
    Numpy end-to-end in write path (no .tolist()).
    Normalized cache schema (no isinstance guards).
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


def write_interpolated_data_to_frame(gp_obj, target_frame_num,
                                     all_interpolated_data, target_layer_idx):
    """Writes interpolated data to frame *_i attributes.

    Phase 0B: uses np.concatenate end-to-end — no .tolist() conversions.
    Populates with original data first, then overwrites with interpolation.
    """
    try:
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
                # Phase 0B:
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
                        # Pad with original data
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


def process_object(gp_obj, current_frame):
    """Process interpolation for a single GP object.

    Uses cache_registry[obj_name].  Rebuilds if dirty flag is set.
    """
    obj_name = gp_obj.name

    try:
        # Dirty-flag invalidation (Phase 0A) — replaces per-frame signature scan
        if cache.is_dirty(obj_name):
            cache.build(gp_obj)
            # build() calls clear_dirty() internally

        obj_cache = cache.get_cache(obj_name)
        if not obj_cache or not obj_cache.get('layers'):
            return

        interpolator = cpp_module.get_interpolator()

        # Find layers that need interpolation
        layers_to_process = []

        for layer_idx, layer_cache in obj_cache['layers'].items():
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
                layers_to_process.append(
                    (layer_idx, layer_cache, prev_frame, next_frame))

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

            # Safety: replace NaN/Inf with safe defaults
            if np.any(np.isnan(easing_samples)) or np.any(np.isinf(easing_samples)):
                easing_samples = np.nan_to_num(easing_samples, nan=0.0,
                                                posinf=1.0, neginf=0.0)

            # Get arc parameters
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

            # Pair strokes by index
            for stroke_idx, prev_stroke in enumerate(prev_strokes):
                if stroke_idx >= len(next_strokes):
                    continue

                next_stroke = next_strokes[stroke_idx]

                # Normalised schema (Phase 0C) — no isinstance guards needed
                prev_positions = prev_stroke['position']
                next_positions = next_stroke['position']

                # Calculate stroke normal for 3D arc direction
                stroke_normal = calculate_stroke_normal(prev_positions)

                # Process position
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

                    # Process opacity
                    interpolated_opacity = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_stroke['opacity'],
                        next_frame, next_stroke['opacity'],
                        stroke_idx, "opacity", easing_samples)
                    if interpolated_opacity is not None and interpolated_opacity.size > 0:
                        all_interpolated_data['opacity'].append(interpolated_opacity)

                    # Process radius
                    interpolated_radius = interpolator.process_interpolation(
                        current_frame,
                        prev_frame, prev_stroke['radius'],
                        next_frame, next_stroke['radius'],
                        stroke_idx, "radius", easing_samples)
                    if interpolated_radius is not None and interpolated_radius.size > 0:
                        all_interpolated_data['radius'].append(interpolated_radius)

                    # Process handles (only when point counts match)
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
    """Process all registered GP objects with per-object error isolation.

    Each object is wrapped in try/except so one corrupt object does NOT
    block the rest of the rig.
    """
    from .registry import validate_targets

    targets = validate_targets(context.scene)
    current_frame = context.scene.frame_current

    for obj_name in targets:
        gp_obj = bpy.data.objects.get(obj_name)
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            continue
        try:
            process_object(gp_obj, current_frame)
        except Exception as e:
            print(f"[GPAI] Error processing '{obj_name}': {e}")


# Backward-compat alias — old code may still call process(context)
def process(context):
    """Legacy entry point. Delegates to process_all()."""
    process_all(context)
