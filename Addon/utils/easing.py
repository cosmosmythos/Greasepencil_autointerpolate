"""
Easing System for GP Auto Interpolate
Handles easing curve storage, UI, and application to keyframes
"""

import bpy
import json
import hashlib


# Easing presets - generate 64 samples on demand
def sample_easing_preset(preset_name, samples=64):
    """Generate easing curve samples for a preset"""
    result = []
    for i in range(samples):
        t = i / (samples - 1)
        
        if preset_name == 'LINEAR':
            value = t
        elif preset_name == 'EASE_IN':
            value = t * t
        elif preset_name == 'EASE_OUT':
            value = 1.0 - (1.0 - t) * (1.0 - t)
        elif preset_name == 'EASE_IN_OUT':
            if t < 0.5:
                value = 2.0 * t * t
            else:
                value = 1.0 - pow(-2.0 * t + 2.0, 2) / 2.0
        else:
            value = t  # Default to linear
        
        result.append(value)
    
    return result


def calculate_frame_signature(layer, frame_number):
    """Calculate a signature/fingerprint for a keyframe based on its stroke data"""
    try:
        for frame in layer.frames:
            if frame.frame_number == frame_number:
                if frame.drawing:
                    # Create signature from stroke count and first/last point positions
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


def get_easing_curve_from_frame(gp_data, layer_idx, frame_number, layer=None):
    """
    Retrieves easing curve data from a specific keyframe.
    Returns list of 64 samples based on stored preset.
    """
    if "gp_easing_data" in gp_data:
        try:
            all_easing = json.loads(gp_data["gp_easing_data"])
            
            if layer:
                # Get layer's permanent ID from attribute
                layer_id = get_or_create_layer_id(gp_data, layer_idx)
                layer_key = str(layer_id)
                
                # Try layer ID + frame number
                if layer_key in all_easing:
                    for uuid, data in all_easing[layer_key].items():
                        if data.get('frame') == frame_number:
                            return sample_easing_preset(data['preset'])
                
                # Fallback: Try signature match (for old data or moved frames)
                signature = calculate_frame_signature(layer, frame_number)
                if signature:
                    for stored_key, layer_data in all_easing.items():
                        for uuid, data in layer_data.items():
                            if data.get('signature') == signature:
                                # Update stored data with new layer key
                                data['frame'] = frame_number
                                gp_data["gp_easing_data"] = json.dumps(all_easing)
                                return sample_easing_preset(data['preset'])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[GPAI] Warning: Failed to parse easing data: {e}")
    
    # Default: linear
    return sample_easing_preset('LINEAR')


def get_or_create_layer_id(gp_data, layer_idx):
    """Get or create a permanent layer ID stored as attribute on GP data"""
    # Check if attribute exists
    if "gpai_layer_id" not in gp_data.attributes:
        # Create attribute for all layers
        gp_data.attributes.new(name="gpai_layer_id", type='INT', domain='LAYER')
    
    attr = gp_data.attributes["gpai_layer_id"]
    
    # Check if this layer already has an ID
    if attr.data[layer_idx].value == 0:
        # Generate new unique ID
        import random
        layer_id = random.randint(1000000, 9999999)
        
        # Make sure it's unique across all layers
        existing_ids = set(attr.data[i].value for i in range(len(attr.data)))
        while layer_id in existing_ids:
            layer_id = random.randint(1000000, 9999999)
        
        # Assign to this layer
        attr.data[layer_idx].value = layer_id
    
    return attr.data[layer_idx].value


def cleanup_stale_easing_data(gp_data):
    """
    Remove easing/arc entries for frames that no longer exist.
    Call this periodically to keep stored data clean.
    """
    if "gp_easing_data" not in gp_data:
        return
    
    try:
        all_easing = json.loads(gp_data["gp_easing_data"])
        if not all_easing:
            return
        
        # Get all existing frames per layer
        existing_frames = {}
        for layer_idx, layer in enumerate(gp_data.layers):
            layer_id = str(get_or_create_layer_id(gp_data, layer_idx))
            existing_frames[layer_id] = set(f.frame_number for f in layer.frames)
        
        # Remove entries for non-existent frames
        cleaned = {}
        removed_count = 0
        for layer_key, layer_data in all_easing.items():
            if layer_key not in existing_frames:
                removed_count += len(layer_data)
                continue  # Layer no longer exists
            
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


def set_easing_curve_to_frame(gp_data, layer, layer_idx, frame_number, preset_name):
    """
    Stores easing preset with UUID and signature for a specific keyframe.
    preset_name: 'LINEAR', 'EASE_IN', 'EASE_OUT', 'EASE_IN_OUT'
    """
    # Clean up stale entries first
    cleanup_stale_easing_data(gp_data)
    
    if "gp_easing_data" in gp_data:
        try:
            all_easing = json.loads(gp_data["gp_easing_data"])
        except json.JSONDecodeError:
            print("[GPAI] Warning: Invalid easing data, resetting")
            all_easing = {}
    else:
        all_easing = {}
    
    # Get permanent layer ID from attribute
    layer_id = get_or_create_layer_id(gp_data, layer_idx)
    layer_key = str(layer_id)
    if layer_key not in all_easing:
        all_easing[layer_key] = {}
    
    # Calculate signature for this frame
    signature = calculate_frame_signature(layer, frame_number)
    
    # IMPORTANT: Remove any existing entries for this frame number (not just by signature)
    # This prevents duplicate entries when signature changes
    uuids_to_remove = []
    for existing_uuid, data in all_easing[layer_key].items():
        if data.get('frame') == frame_number:
            uuids_to_remove.append(existing_uuid)
    for uuid_to_remove in uuids_to_remove:
        del all_easing[layer_key][uuid_to_remove]
    
    # Generate new UUID for this entry
    import uuid as uuid_module
    uuid = uuid_module.uuid4().hex[:12]
    
    # Store with UUID and signature (layer_id in attribute, not stored here)
    all_easing[layer_key][uuid] = {
        'preset': preset_name,
        'frame': frame_number,
        'signature': signature
    }
    
    gp_data["gp_easing_data"] = json.dumps(all_easing)
    return True


def get_selected_keyframes(context):
    """
    Returns list of (layer_idx, frame_number) tuples for all selected keyframes.
    """
    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return []
    
    selected_keys = []
    for layer_idx, layer in enumerate(gp_obj.data.layers):
        for frame in layer.frames:
            if frame.select:
                selected_keys.append((layer_idx, frame.frame_number))
    
    return selected_keys
