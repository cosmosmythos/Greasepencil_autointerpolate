
import bpy
import json
import hashlib

def get_layer_id_readonly(gp_data, layer_idx):
    attr = gp_data.attributes.get("gpai_layer_id")
    if attr is None:
        return None
    if layer_idx >= len(attr.data):
        return None
    val = attr.data[layer_idx].value
    return val if val != 0 else None


def apply_control_points_to_curve(curve, curve_mapping, control_points):
    if not control_points or len(control_points) < 2:
        curve_mapping.update()
        return False

    while len(curve.points) > 2:
        curve.points.remove(curve.points[1])

    curve.points[0].location = control_points[0]['loc']
    curve.points[0].handle_type = control_points[0].get('handle', 'AUTO')
    curve.points[-1].location = control_points[-1]['loc']
    curve.points[-1].handle_type = control_points[-1].get('handle', 'AUTO')
    for i in range(1, len(control_points) - 1):
        pt_data = control_points[i]
        new_pt = curve.points.new(pt_data['loc'][0], pt_data['loc'][1])
        new_pt.handle_type = pt_data.get('handle', 'AUTO_CLAMPED')

    curve_mapping.update()
    return True


def normalize_easing_curve(curve_samples):
    if not curve_samples or len(curve_samples) < 2:
        return curve_samples

    import math

    # Replace NaN/Inf first
    clean = []
    for v in curve_samples:
        if math.isnan(v) or math.isinf(v):
            clean.append(0.0)
        else:
            clean.append(v)


    val_min = min(clean)
    val_max = max(clean)
    val_range = val_max - val_min

    if val_range > 1e-10:
        result = [(v - val_min) / val_range for v in clean]
    else:

        n = len(clean)
        result = [i / (n - 1) for i in range(n)]

    # Force exact endpoints
    result[0] = 0.0
    result[-1] = 1.0




    for i in range(1, len(result)):
        if result[i] < result[i - 1]:
            result[i] = result[i - 1]

    return result


def get_easing_curve_node():
    from ..core.constants import NODEGROUP_NAME
    node_group = bpy.data.node_groups.get(NODEGROUP_NAME)
    if not node_group:
        return None
    for node in node_group.nodes:
        if node.name == "Easing" and node.type == 'CURVE_FLOAT':
            return node
    return None


def sample_easing_preset(preset_name, samples=64):
    from ..core.constants import NODEGROUP_NAME

    result = []


    curve_node = None
    if preset_name == 'CUSTOM':
        node_group = bpy.data.node_groups.get(NODEGROUP_NAME)
        if node_group:
            for node in node_group.nodes:
                if node.name == "Easing" and node.type == 'CURVE_FLOAT':
                    curve_node = node
                    break

    for i in range(samples):
        t = i / (samples - 1)

        if preset_name == 'LINEAR':
            value = t
        elif preset_name == 'EASE_IN':
            value = t * t / (t * t + 3.236 * pow(1.0 - t, 2.109))
        elif preset_name == 'EASE_OUT':
            value = t * t / (t * t + 0.402 * pow(1.0 - t, 2.27))
        elif preset_name == 'EASE_IN_OUT':
            if t < 0.5:
                value = 2.0 * t * t
            else:
                value = 1.0 - pow(-2.0 * t + 2.0, 2) / 2.0
        elif preset_name == 'CUSTOM':
            if curve_node:
                curve_mapping = curve_node.mapping
                curve = curve_mapping.curves[0]
                value = curve_mapping.evaluate(curve, t)
            else:
                value = t  # Fallback to linear
        else:
            value = t  # Default to linear

        result.append(value)

    return result


def calculate_frame_signature(layer, frame_number):
    try:
        for frame in layer.frames:
            if frame.frame_number == frame_number:
                if frame.drawing:

                    sig_parts = [str(len(frame.drawing.strokes))]
                    for stroke in frame.drawing.strokes[:3]:  # First 3 strokes
                        if len(stroke.points) > 0:
                            p = stroke.points[0]
                            sig_parts.append(f"{p.position.x:.3f},{p.position.y:.3f}")
                    signature = "|".join(sig_parts)
                    sig_hash = hashlib.md5(signature.encode()).hexdigest()[:16]
                    return sig_hash
    except (AttributeError, KeyError, TypeError) as e:
        print(f"[GPAI] Warning: Failed to calculate frame signature: {e}")
    return None


def sample_curve_from_control_points(control_points, samples=64):

    if not control_points or len(control_points) < 2:
        return None

    curve_node = get_easing_curve_node()
    if not curve_node:
        return None

    curve_mapping = curve_node.mapping
    curve = curve_mapping.curves[0]

    saved_points = []
    for pt in curve.points:
        saved_points.append({
            'loc': [pt.location.x, pt.location.y],
            'handle': pt.handle_type
        })

    result = None
    try:

        if not apply_control_points_to_curve(curve, curve_mapping, control_points):
            return None
        curve_mapping.initialize()

        # Sample the curve
        result = []
        for i in range(samples):
            t = i / (samples - 1)
            result.append(curve_mapping.evaluate(curve, t))
    except Exception as e:
        print(f"[GPAI]: Failed to sample curve: {e}")
        result = None
    finally:

        apply_control_points_to_curve(curve, curve_mapping, saved_points)

    return result


def deserialize_curve_control_points(control_points):
    curve_node = get_easing_curve_node()
    if not curve_node:
        return False

    curve_mapping = curve_node.mapping
    curve = curve_mapping.curves[0]
    return apply_control_points_to_curve(curve, curve_mapping, control_points)


def get_easing_curve_from_frame(gp_data, layer_idx, frame_number, layer=None):
    if "gp_easing_data" in gp_data:
        try:
            all_easing = json.loads(gp_data["gp_easing_data"])

            if layer:

                layer_id = get_or_create_layer_id(gp_data, layer_idx)
                layer_key = str(layer_id)


                if layer_key in all_easing:
                    for uuid, data in all_easing[layer_key].items():
                        if data.get('frame') == frame_number:
                            preset = data['preset']


                            preset = data['preset']
                            if preset == 'CUSTOM':
                                curve_samples = data.get('samples')
                                if not curve_samples and 'control_points' in data:
                                    curve_samples = sample_curve_from_control_points(data['control_points'])
                                return curve_samples if curve_samples else sample_easing_preset('LINEAR')
                            else:
                                return sample_easing_preset(preset)


                signature = calculate_frame_signature(layer, frame_number)
                if signature and layer_key in all_easing:
                    for uuid, data in all_easing[layer_key].items():
                        if data.get('signature') == signature:
                            data['frame'] = frame_number
                            gp_data["gp_easing_data"] = json.dumps(all_easing)

                            preset = data['preset']
                            if preset == 'CUSTOM':
                                curve_samples = data.get('samples')
                                if not curve_samples and 'control_points' in data:
                                    curve_samples = sample_curve_from_control_points(data['control_points'])
                                return curve_samples if curve_samples else sample_easing_preset('LINEAR')
                            else:
                                return sample_easing_preset(preset)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[GPAI] Warning: Failed to parse easing data: {e}")

    # Default: linear
    return sample_easing_preset('LINEAR')


def get_or_create_layer_id(gp_data, layer_idx):
    attr = gp_data.attributes.get("gpai_layer_id")
    if attr is None:
        attr = gp_data.attributes.new(name="gpai_layer_id", type='INT', domain='LAYER')


    if attr.data[layer_idx].value == 0:

        import random
        layer_id = random.randint(1000000, 9999999)


        existing_ids = set(attr.data[i].value for i in range(len(attr.data)))
        while layer_id in existing_ids:
            layer_id = random.randint(1000000, 9999999)


        attr.data[layer_idx].value = layer_id

    return attr.data[layer_idx].value


def cleanup_stale_easing_data(gp_data):
    if "gp_easing_data" not in gp_data:
        return

    try:
        all_easing = json.loads(gp_data["gp_easing_data"])
        if not all_easing:
            return


        existing_frames = {}
        for layer_idx, layer in enumerate(gp_data.layers):
            layer_id = str(get_or_create_layer_id(gp_data, layer_idx))
            existing_frames[layer_id] = set(f.frame_number for f in layer.frames)


        cleaned = {}
        removed_count = 0
        for layer_key, layer_data in all_easing.items():
            if layer_key not in existing_frames:
                removed_count += len(layer_data)
                continue

            cleaned[layer_key] = {}
            valid_frames = existing_frames[layer_key]
            for uuid, data in layer_data.items():
                if data.get('frame') in valid_frames:
                    cleaned[layer_key][uuid] = data
                else:
                    removed_count += 1

        if removed_count > 0:
            gp_data["gp_easing_data"] = json.dumps(cleaned)
            print(f"[GPAI] Cleaned up {removed_count} stale easing entries")

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[GPAI] Warning: Failed to cleanup easing data: {e}")


def serialize_curve_control_points():
    curve_node = get_easing_curve_node()
    if not curve_node:
        return None

    curve_mapping = curve_node.mapping
    curve = curve_mapping.curves[0]

    points = []
    for pt in curve.points:
        points.append({
            'loc': [round(pt.location.x, 4), round(pt.location.y, 4)],
            'handle': pt.handle_type
        })

    return points


def set_easing_curve_to_frame(gp_data, layer, layer_idx, frame_number, preset_name):

    cleanup_stale_easing_data(gp_data)

    if "gp_easing_data" in gp_data:
        try:
            all_easing = json.loads(gp_data["gp_easing_data"])
        except json.JSONDecodeError:
            print("[GPAI] Warning: Invalid easing data, resetting")
            all_easing = {}
    else:
        all_easing = {}


    layer_id = get_or_create_layer_id(gp_data, layer_idx)
    layer_key = str(layer_id)
    if layer_key not in all_easing:
        all_easing[layer_key] = {}


    signature = calculate_frame_signature(layer, frame_number)



    uuids_to_remove = []
    for existing_uuid, data in all_easing[layer_key].items():
        if data.get('frame') == frame_number:
            uuids_to_remove.append(existing_uuid)
    for uuid_to_remove in uuids_to_remove:
        del all_easing[layer_key][uuid_to_remove]


    import uuid as uuid_module
    uuid = uuid_module.uuid4().hex[:12]

    # Build entry data
    entry = {
        'preset': preset_name,
        'frame': frame_number,
        'signature': signature
    }


    if preset_name == 'CUSTOM':
        control_points = serialize_curve_control_points()
        if control_points:
            entry['control_points'] = control_points
        else:

            entry['samples'] = sample_easing_preset('CUSTOM')

    all_easing[layer_key][uuid] = entry

    gp_data["gp_easing_data"] = json.dumps(all_easing)
    return True


def get_selected_keyframes(context):
    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return []

    selected_keys = []
    for layer_idx, layer in enumerate(gp_obj.data.layers):
        for frame in layer.frames:
            if frame.select:
                selected_keys.append((layer_idx, frame.frame_number))

    return selected_keys
