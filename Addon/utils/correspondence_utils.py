"""
Correspondence Utilities
Handles keyframe detection, Match_ID storage/retrieval, and stroke collection
for the GP correspondence system.
"""

import bpy
def detect_keyframe_range(scene, layer):
    """Auto-detect keyframe range based on playhead position."""
    playhead = scene.frame_current
    frames = sorted([f.frame_number for f in layer.frames])
    
    if not frames:
        return (1, 24)
    
    prev_key = None
    next_key = None
    
    for f in frames:
        if f <= playhead:
            prev_key = f
        if f > playhead and next_key is None:
            next_key = f
    
    if playhead in frames:
        idx = frames.index(playhead)
        if idx + 1 < len(frames):
            return (playhead, frames[idx + 1])
        elif idx > 0:
            return (frames[idx - 1], playhead)
    
    if prev_key is not None and next_key is not None:
        return (prev_key, next_key)
    elif prev_key is not None:
        return (prev_key, prev_key + 10)
    elif next_key is not None:
        return (max(1, next_key - 10), next_key)
    
    return (1, 24)


def find_keyframe_pairs(layer, start_frame, end_frame):
    """Find all consecutive keyframe pairs in range."""
    frames = sorted([f.frame_number for f in layer.frames 
                    if start_frame <= f.frame_number <= end_frame])
    
    if len(frames) < 2:
        return []
    
    return [(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
def _get_existing_match_id_attr(drawing):
    """Get existing Match_ID attribute or None."""
    if drawing is None:
        return None
    for attr in drawing.attributes:
        if attr.name == "Match_ID" and attr.data_type == 'INT' and attr.domain == 'CURVE':
            return attr
    return None


def _ensure_match_id_attr(drawing):
    """Ensure drawing has a Match_ID attribute."""
    if drawing is None:
        raise RuntimeError("Drawing is None")
    
    attr = _get_existing_match_id_attr(drawing)
    if attr is not None:
        return attr
    
    attr = drawing.attributes.new(name="Match_ID", type='INT', domain='CURVE')
    
    for i in range(len(attr.data)):
        attr.data[i].value = -1
    
    return attr


def store_match_id_on_strokes(gp_obj, layer_idx, frame_num, stroke_indices, match_id):
    """Store Match_ID on specified strokes."""
    if gp_obj is None or gp_obj.data is None:
        raise ValueError("Invalid GP object")
    
    layer = gp_obj.data.layers[layer_idx]
    
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
    
    attr = _ensure_match_id_attr(drawing)
    
    for stroke_idx in stroke_indices:
        if 0 <= stroke_idx < len(drawing.strokes):
            attr.data[stroke_idx].value = match_id


def get_match_id_from_stroke(gp_obj, layer_idx, frame_num, stroke_idx):
    """Get Match_ID from stroke. Returns -1 if not found."""
    try:
        layer = gp_obj.data.layers[layer_idx]
        
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
        
        attr = _get_existing_match_id_attr(drawing)
        if attr is None:
            return -1
        
        if 0 <= stroke_idx < len(attr.data):
            return attr.data[stroke_idx].value
        
        return -1
    except:
        return -1


def clear_match_ids_for_layer_frames(gp_obj, layer_idx, frame1, frame2):
    """Clear all Match_IDs for specified frames."""
    layer = gp_obj.data.layers[layer_idx]
    
    for frame_num in [frame1, frame2]:
        frame = None
        for f in layer.frames:
            if f.frame_number == frame_num:
                frame = f
                break
        
        if frame is None or frame.drawing is None:
            continue
        
        attr = _get_existing_match_id_attr(frame.drawing)
        if attr is None:
            continue
        
        for i in range(len(attr.data)):
            attr.data[i].value = -1


# Stroke Collection
def collect_strokes_2d(gp_obj, layer_idx, frame):
    """Collect 2D projected strokes. Returns (strokes_2d, original_indices)."""
    from ..gp_match_test import _collect_strokes_2d
    return _collect_strokes_2d(gp_obj, layer_idx, frame)


def to_cpp_strokes(strokes_2d):
    """Convert 2D stroke data to C++ format."""
    from ..gp_match_test import _to_ftpsc
    return _to_ftpsc(strokes_2d)
