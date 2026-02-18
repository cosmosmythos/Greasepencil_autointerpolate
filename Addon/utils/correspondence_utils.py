"""
Correspondence Utilities
Handles keyframe detection and stroke collection for the GP correspondence system.
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


# Stroke Collection
def collect_strokes_2d(gp_obj, layer_idx, frame):
    """
    Collect 2D projected strokes from a GP object.
    Projects strokes orthographically using scene camera's view direction.
    
    This gives stable, consistent projection without frustum/clipping issues:
    - Uses camera's view direction (where it's looking)
    - Projects orthographically onto a plane perpendicular to that direction
    - No near/far clip, no FOV distortion, works with strokes anywhere in scene
    
    Returns:
        (strokes_2d, original_indices) where original_indices[i] = drawing.strokes index
    """
    import bpy
    from mathutils import Vector, Matrix
    
    if gp_obj is None or gp_obj.type != 'GREASEPENCIL':
        return [], []
    
    layer = gp_obj.data.layers[layer_idx]
    
    # Find frame
    frame_obj = None
    for f in layer.frames:
        if f.frame_number == frame:
            frame_obj = f
            break
    
    if frame_obj is None or frame_obj.drawing is None:
        return [], []
    
    drawing = frame_obj.drawing
    
    # Get scene camera for view direction
    scene = bpy.context.scene
    camera = scene.camera
    
    if camera is None:
        # Default: front view (looking down -Y axis)
        view_forward = Vector((0, -1, 0))
        view_up = Vector((0, 0, 1))
        view_right = Vector((1, 0, 0))
    else:
        # Get camera's view direction from its world matrix
        cam_matrix = camera.matrix_world
        # Camera looks down its local -Z axis
        view_forward = -cam_matrix.col[2].xyz.normalized()
        view_up = cam_matrix.col[1].xyz.normalized()
        view_right = cam_matrix.col[0].xyz.normalized()
    
    # Collect all world positions first to compute bounding box for normalization
    mw = gp_obj.matrix_world
    all_projected = []  # [(stroke_idx, [(x, y), ...])]
    
    for stroke_idx, stroke in enumerate(drawing.strokes):
        num_points = len(stroke.points)
        
        if num_points < 2:
            continue
        
        points_2d = []
        
        for point in stroke.points:
            pos_local = getattr(point, "position", None)
            if pos_local is None:
                pos_local = getattr(point, "co", None)
            if pos_local is None:
                continue
            
            pos_world = mw @ pos_local
            
            # Project onto plane perpendicular to view direction
            # x = dot(pos, right), y = dot(pos, up)
            x = pos_world.dot(view_right)
            y = pos_world.dot(view_up)
            
            points_2d.append((x, y))
        
        if len(points_2d) >= 2:
            all_projected.append((stroke_idx, points_2d))
    
    if not all_projected:
        return [], []
    
    # Compute bounding box of all projected points for normalization
    all_x = []
    all_y = []
    for _, points in all_projected:
        for x, y in points:
            all_x.append(x)
            all_y.append(y)
    
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    # Add small padding to avoid division by zero
    range_x = max_x - min_x
    range_y = max_y - min_y
    
    if range_x < 0.0001:
        range_x = 1.0
    if range_y < 0.0001:
        range_y = 1.0
    
    # Use uniform scale to preserve aspect ratio
    scale = max(range_x, range_y)
    
    # Normalize all points to [0, 1] range
    strokes_2d = []
    original_indices = []
    
    for stroke_idx, points in all_projected:
        normalized_points = []
        for x, y in points:
            # Center and scale uniformly
            nx = (x - min_x) / scale
            ny = (y - min_y) / scale
            normalized_points.append((nx, ny))
        
        strokes_2d.append(normalized_points)
        original_indices.append(stroke_idx)
    
    return strokes_2d, original_indices


def to_cpp_strokes(strokes_2d):
    """
    Convert 2D stroke data to C++ format.
    Flattens list of strokes into format expected by gp_autointerpolate.StrokeMatcher.
    
    Args:
        strokes_2d: List of strokes, each stroke is list of (x, y) tuples
    
    Returns:
        np.array in format [x0, y0, x1, y1, -1, -1, x0, y0, ...] where -1,-1 separates strokes
        (Two -1 values needed because C++ parser reads pairs and increments by 2)
    """
    import numpy as np
    
    flat_data = []
    
    for stroke in strokes_2d:
        for x, y in stroke:
            flat_data.append(x)
            flat_data.append(y)
        flat_data.append(-1.0)  # Separator (pair of -1s to maintain alignment)
        flat_data.append(-1.0)
    
    # Remove trailing separator pair
    if len(flat_data) >= 2 and flat_data[-1] == -1.0 and flat_data[-2] == -1.0:
        flat_data.pop()
        flat_data.pop()
    
    result = np.array(flat_data, dtype=np.float32)
    
    return result

