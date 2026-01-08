"""
Correspondence Utilities
Handles keyframe detection, Match_ID storage/retrieval, and stroke collection
for the GP correspondence system.
"""

import bpy


# ============================================================================
# Keyframe Detection
# ============================================================================

def detect_keyframe_range(scene, layer):
    """Auto-detect keyframe range based on playhead position"""
    playhead = scene.frame_current
    frames = sorted([f.frame_number for f in layer.frames])
    
    if not frames:
        return (1, 24)  # Default fallback
    
    # Find adjacent keys around playhead
    prev_key = None
    next_key = None
    
    for f in frames:
        if f <= playhead:
            prev_key = f
        if f > playhead and next_key is None:
            next_key = f
    
    # If playhead is ON a keyframe
    if playhead in frames:
        idx = frames.index(playhead)
        if idx + 1 < len(frames):
            # Return current -> next
            return (playhead, frames[idx + 1])
        elif idx > 0:
            # Return prev -> current
            return (frames[idx - 1], playhead)
    
    # Playhead between keys
    if prev_key is not None and next_key is not None:
        return (prev_key, next_key)
    elif prev_key is not None:
        return (prev_key, prev_key + 10)
    elif next_key is not None:
        return (max(1, next_key - 10), next_key)
    
    # Absolute fallback
    return (1, 24)


def find_keyframe_pairs(layer, start_frame, end_frame):
    """
    Find all consecutive keyframe pairs in the given range.
    Returns list of (frame_a, frame_b) tuples.
    """
    frames = sorted([f.frame_number for f in layer.frames 
                    if start_frame <= f.frame_number <= end_frame])
    
    if len(frames) < 2:
        return []
    
    pairs = []
    for i in range(len(frames) - 1):
        pairs.append((frames[i], frames[i + 1]))
    
    return pairs


# ============================================================================
# Match_ID Attribute Management
# ============================================================================

def _get_existing_match_id_attr(drawing):
    """Get existing Match_ID attribute or None"""
    if drawing is None:
        return None
    for attr in drawing.attributes:
        if attr.name == "Match_ID" and attr.data_type == 'INT' and attr.domain == 'CURVE':
            return attr
    return None


def _ensure_match_id_attr(drawing):
    """
    Ensure the drawing has a 'Match_ID' attribute.
    Returns the attribute object.
    """
    if drawing is None:
        raise RuntimeError("Drawing is None")
    
    # Check if attribute already exists
    attr = _get_existing_match_id_attr(drawing)
    if attr is not None:
        return attr
    
    # Create new attribute
    # GPv3 API: attributes.new(name, type, domain)
    # type: 'FLOAT', 'INT', 'FLOAT_VECTOR', 'FLOAT_COLOR', 'BOOLEAN', 'FLOAT2', 'INT8', 'INT32_2D', 'QUATERNION', 'STRING'
    # domain: 'POINT', 'CURVE', etc.
    attr = drawing.attributes.new(
        name="Match_ID",
        type='INT',
        domain='CURVE'
    )
    
    # Initialize all values to -1 (unmatched)
    # GPv3: attribute.data is a sequence-like object
    for i in range(len(attr.data)):
        attr.data[i].value = -1
    
    return attr


def store_match_id_on_strokes(gp_obj, layer_idx, frame_num, stroke_indices, match_id):
    """
    Store a Match_ID on specified strokes.
    
    Args:
        gp_obj: GreasePencilv3 object
        layer_idx: Layer index
        frame_num: Frame number
        stroke_indices: List of stroke indices to mark
        match_id: Integer Match_ID to store
    """
    if gp_obj is None or gp_obj.data is None:
        raise ValueError("Invalid GP object")
    
    layer = gp_obj.data.layers[layer_idx]
    
    # Find frame
    frame = None
    for f in layer.frames:
        if f.frame_number == frame_num:
            frame = f
            break
    
    if frame is None:
        raise ValueError(f"Frame {frame_num} not found in layer {layer.name}")
    
    drawing = frame.drawing
    if drawing is None:
        raise ValueError(f"No drawing data on frame {frame_num}")
    
    # Ensure Match_ID attribute exists
    attr = _ensure_match_id_attr(drawing)
    
    # Set Match_ID for specified strokes
    for stroke_idx in stroke_indices:
        if 0 <= stroke_idx < len(drawing.strokes):
            attr.data[stroke_idx].value = match_id


def get_match_id_from_stroke(gp_obj, layer_idx, frame_num, stroke_idx):
    """
    Get the Match_ID from a specific stroke.
    Returns -1 if not set or not found.
    """
    try:
        layer = gp_obj.data.layers[layer_idx]
        
        # Find frame
        frame = None
        for f in layer.frames:
            if f.frame_number == frame_num:
                frame = f
                break
        
        if frame is None:
            return -1
        
        drawing = frame.drawing
        if drawing is None:
            return -1
        
        # Get Match_ID attribute
        attr = _get_existing_match_id_attr(drawing)
        if attr is None:
            return -1
        
        if 0 <= stroke_idx < len(attr.data):
            return attr.data[stroke_idx].value
        
        return -1
    except:
        return -1


def clear_match_ids_for_layer_frames(gp_obj, layer_idx, frame1, frame2):
    """Clear all Match_IDs for the specified frames in a layer"""
    layer = gp_obj.data.layers[layer_idx]
    
    for frame_num in [frame1, frame2]:
        # Find frame
        frame = None
        for f in layer.frames:
            if f.frame_number == frame_num:
                frame = f
                break
        
        if frame is None:
            continue
        
        drawing = frame.drawing
        if drawing is None:
            continue
        
        # Get Match_ID attribute if it exists
        attr = _get_existing_match_id_attr(drawing)
        if attr is None:
            continue
        
        # Reset all to -1
        for i in range(len(attr.data)):
            attr.data[i].value = -1


# ============================================================================
# Stroke Collection (delegates to gp_match_test)
# ============================================================================

def collect_strokes_2d(gp_obj, layer_idx, frame):
    """
    Collect 2D projected strokes from a GP object.
    Delegates to gp_match_test._collect_strokes_2d for consistency.
    
    Returns:
        (strokes_2d, original_indices) where original_indices[i] = drawing.strokes index
    """
    from ..gp_match_test import _collect_strokes_2d
    return _collect_strokes_2d(gp_obj, layer_idx, frame)


def to_cpp_strokes(strokes_2d):
    """
    Convert 2D stroke data to C++ format.
    Delegates to gp_match_test._to_ftpsc for consistency.
    
    Returns:
        List of gp_autointerpolate.Stroke objects
    """
    from ..gp_match_test import _to_ftpsc
    return _to_ftpsc(strokes_2d)
