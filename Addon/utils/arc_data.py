
import bpy
import json
from .easing import calculate_frame_signature, get_or_create_layer_id


ARC_DATA_KEY = "gp_arc_data"


def get_arc_params_from_frame(gp_data, layer_idx, frame_number, layer=None):
    defaults = (0.0, 0.0, 0.0, True)

    if ARC_DATA_KEY not in gp_data:
        return defaults

    try:
        all_arc_data = json.loads(gp_data[ARC_DATA_KEY])

        if layer:

            layer_id = get_or_create_layer_id(gp_data, layer_idx)
            layer_key = str(layer_id)


            if layer_key in all_arc_data:
                for uuid, data in all_arc_data[layer_key].items():
                    if data.get('frame') == frame_number:
                        return (
                            data.get('arc_amount', 0.0),
                            data.get('arc_direction', 0.0),
                            data.get('curvature_blend', 0.0),
                            data.get('use_spiral', True)
                        )


            signature = calculate_frame_signature(layer, frame_number)
            if signature:
                for stored_key, layer_data in all_arc_data.items():
                    for uuid, data in layer_data.items():
                        if data.get('signature') == signature:

                            data['frame'] = frame_number
                            gp_data[ARC_DATA_KEY] = json.dumps(all_arc_data)
                            return (
                                data.get('arc_amount', 0.0),
                                data.get('arc_direction', 0.0),
                                data.get('curvature_blend', 0.0),
                                data.get('use_spiral', True)
                            )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[GPAI] Warning: Failed to parse arc data: {e}")

    return defaults


def cleanup_stale_arc_data(gp_data):
    if ARC_DATA_KEY not in gp_data:
        return

    try:
        all_arc_data = json.loads(gp_data[ARC_DATA_KEY])
        if not all_arc_data:
            return


        existing_frames = {}
        for layer_idx, layer in enumerate(gp_data.layers):
            layer_id = str(get_or_create_layer_id(gp_data, layer_idx))
            existing_frames[layer_id] = set(f.frame_number for f in layer.frames)


        cleaned = {}
        removed_count = 0
        for layer_key, layer_data in all_arc_data.items():
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
            gp_data[ARC_DATA_KEY] = json.dumps(cleaned)
            print(f"[GPAI] Cleaned up {removed_count} stale arc entries")

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[GPAI] Warning: Failed to cleanup arc data: {e}")


def set_arc_params_to_frame(gp_data, layer, layer_idx, frame_number,
                            arc_amount, arc_direction, curvature_blend, use_spiral):

    cleanup_stale_arc_data(gp_data)

    if ARC_DATA_KEY in gp_data:
        try:
            all_arc_data = json.loads(gp_data[ARC_DATA_KEY])
        except json.JSONDecodeError:
            print("[GPAI] Warning: Invalid arc data, resetting")
            all_arc_data = {}
    else:
        all_arc_data = {}


    layer_id = get_or_create_layer_id(gp_data, layer_idx)
    layer_key = str(layer_id)
    if layer_key not in all_arc_data:
        all_arc_data[layer_key] = {}


    signature = calculate_frame_signature(layer, frame_number)



    uuids_to_remove = []
    for existing_uuid, data in all_arc_data[layer_key].items():
        if data.get('frame') == frame_number:
            uuids_to_remove.append(existing_uuid)
    for uuid_to_remove in uuids_to_remove:
        del all_arc_data[layer_key][uuid_to_remove]


    import uuid as uuid_module
    uuid = uuid_module.uuid4().hex[:12]

    # Store arc parameters
    all_arc_data[layer_key][uuid] = {
        'frame': frame_number,
        'signature': signature,
        'arc_amount': arc_amount,
        'arc_direction': arc_direction,
        'curvature_blend': curvature_blend,
        'use_spiral': use_spiral
    }

    gp_data[ARC_DATA_KEY] = json.dumps(all_arc_data)
    return True


def get_selected_keyframes(context):
    from .easing import get_selected_keyframes as _get_selected_keyframes
    return _get_selected_keyframes(context)
