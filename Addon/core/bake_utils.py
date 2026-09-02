
import numpy as np


def calculate_stroke_normal(positions):
    point_count = len(positions) // 3
    if point_count < 3:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up


    p0 = np.array([positions[0], positions[1], positions[2]])
    mid_idx = (point_count // 2) * 3
    p_mid = np.array([positions[mid_idx], positions[mid_idx+1], positions[mid_idx+2]])
    p_end = np.array([positions[-3], positions[-2], positions[-1]])


    v1 = p_mid - p0
    v2 = p_end - p0


    normal = np.cross(v1, v2)
    norm_len = np.linalg.norm(normal)

    if norm_len < 1e-6:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)  # Default: Z-up

    return (normal / norm_len).astype(np.float32)


def get_arc_params_for_baking(layer_cache, start_frame):
    if not layer_cache:
        return (0.0, 0.0, True)

    arc_data = layer_cache.get('arc_data', {})
    arc_params = arc_data.get(start_frame, (0.0, 0.0, 0.0, True))


    return (arc_params[0], arc_params[1], arc_params[3])


def apply_interpolation_to_frame(gp_obj, layer_idx, frame_num, interpolated_data):
    layer = gp_obj.data.layers[layer_idx]

    target_frame = None
    for frame in layer.frames:
        if frame.frame_number == frame_num:
            target_frame = frame
            break

    if not target_frame or not target_frame.drawing:
        return False

    drawing = target_frame.drawing
    attrs = drawing.attributes
    total_points = sum(len(stroke.points) for stroke in drawing.strokes)

    if total_points == 0:
        return False


    for stroke_idx, stroke_data in interpolated_data.items():
        if stroke_idx == 0:

            # Write positions
            if 'position' in stroke_data and 'position' in attrs:
                positions = stroke_data['position']
                if len(positions) == total_points * 3:
                    attrs['position'].data.foreach_set('vector', positions)

            # Write opacity
            if 'opacity' in stroke_data and 'opacity' in attrs:
                opacities = stroke_data['opacity']
                if len(opacities) == total_points:
                    attrs['opacity'].data.foreach_set('value', opacities)

            # Write radius
            if 'radius' in stroke_data and 'radius' in attrs:
                radii = stroke_data['radius']
                if len(radii) == total_points:
                    attrs['radius'].data.foreach_set('value', radii)

            # Write handle_left
            if 'handle_left' in stroke_data and 'handle_left' in attrs:
                handle_lefts = stroke_data['handle_left']
                if len(handle_lefts) == total_points * 3:
                    attrs['handle_left'].data.foreach_set('vector', handle_lefts)

            # Write handle_right
            if 'handle_right' in stroke_data and 'handle_right' in attrs:
                handle_rights = stroke_data['handle_right']
                if len(handle_rights) == total_points * 3:
                    attrs['handle_right'].data.foreach_set('vector', handle_rights)


            drawing.tag_positions_changed()

            break

    return True
