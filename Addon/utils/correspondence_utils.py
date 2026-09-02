
import bpy
import numpy as np
from mathutils import Vector


def detect_keyframe_range(scene, layer):
    playhead = scene.frame_current
    frames = sorted(f.frame_number for f in layer.frames)

    if not frames:
        return (scene.frame_start, scene.frame_end)

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
        if idx > 0:
            return (frames[idx - 1], playhead)

    if prev_key is not None and next_key is not None:
        return (prev_key, next_key)
    if prev_key is not None:
        return (prev_key, min(prev_key + 10, scene.frame_end))
    if next_key is not None:
        return (max(scene.frame_start, next_key - 10), next_key)

    return (scene.frame_start, scene.frame_end)


def find_keyframe_pairs(layer, start_frame, end_frame):
    frames = sorted(
        f.frame_number for f in layer.frames
        if start_frame <= f.frame_number <= end_frame
    )
    if len(frames) < 2:
        return []
    return [(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]


def _viewport_axes():
    try:
        screen = bpy.context.screen
        if screen:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    region_3d = area.spaces.active.region_3d
                    if region_3d:
                        try:
                            inv = region_3d.view_matrix.inverted()
                            fwd = -inv.col[2].xyz.normalized()
                            up = inv.col[1].xyz.normalized()
                            right = inv.col[0].xyz.normalized()
                            tag = "viewport_view:ortho" if not region_3d.is_perspective else "viewport_view:persp"
                            return (fwd, up, right, tag)
                        except Exception:
                            pass
                        try:
                            quat = region_3d.view_rotation
                            fwd = quat @ Vector((0, 0, -1))
                            up = quat @ Vector((0, 1, 0))
                            right = quat @ Vector((1, 0, 0))
                            return (fwd.normalized(), up.normalized(), right.normalized(), "viewport_view:quat")
                        except Exception:
                            pass
                    break
    except Exception:
        pass
    return None


def _camera_axes_at_frame(scene, camera, frame):
    if camera is None:
        return None
    if frame is None or frame == scene.frame_current:
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            cam_eval = camera.evaluated_get(depsgraph)
            cm = cam_eval.matrix_world
        except Exception:
            cm = camera.matrix_world
        return (
            -cm.col[2].xyz.normalized(),
            cm.col[1].xyz.normalized(),
            cm.col[0].xyz.normalized(),
            f"camera:{camera.name}@{frame if frame is not None else scene.frame_current}",
        )
    old_frame = scene.frame_current
    try:
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        cam_eval = camera.evaluated_get(depsgraph)
        cm = cam_eval.matrix_world
        return (
            -cm.col[2].xyz.normalized(),
            cm.col[1].xyz.normalized(),
            cm.col[0].xyz.normalized(),
            f"camera:{camera.name}@{frame}",
        )
    finally:
        scene.frame_set(old_frame)


def _get_view_axes(scene, method="camera", frame=None):
    if method == "camera":
        camera = scene.camera if scene else None
        axes = _camera_axes_at_frame(scene, camera, frame)
        if axes is not None:
            return axes

        vp = _viewport_axes()
        if vp is not None:
            return vp
        raise RuntimeError("No scene camera and no viewport_view available for flattening")

    if method == "viewport_view":
        vp = _viewport_axes()
        if vp is not None:
            return vp

        camera = scene.camera if scene else None
        axes = _camera_axes_at_frame(scene, camera, frame)
        if axes is not None:
            return axes
        raise RuntimeError("No viewport_view and no scene camera available for flattening")

    return _get_view_axes(scene, method="camera", frame=frame)


def _find_drawing(gp_obj, layer_idx, frame_number):
    if gp_obj is None or gp_obj.type != "GREASEPENCIL":
        return None
    try:
        layer = gp_obj.data.layers[layer_idx]
    except IndexError:
        return None
    for frame in layer.frames:
        if frame.frame_number == frame_number:
            return frame.drawing
    return None


def collect_strokes_2d(gp_obj, layer_idx, frame, method="camera"):
    drawing = _find_drawing(gp_obj, layer_idx, frame)
    if drawing is None:
        return [], []

    scene = bpy.context.scene
    _forward, view_up, view_right, _label = _get_view_axes(scene, method=method, frame=frame)
    world_matrix = gp_obj.matrix_world

    all_projected = []
    for stroke_idx, stroke in enumerate(drawing.strokes):
        if len(stroke.points) < 2:
            continue
        points_2d = []
        for point in stroke.points:
            pos_local = getattr(point, "position", None) or getattr(point, "co", None)
            if pos_local is None:
                continue
            pos_world = world_matrix @ pos_local
            points_2d.append((pos_world.dot(view_right), pos_world.dot(view_up)))
        if len(points_2d) >= 2:
            all_projected.append((stroke_idx, points_2d))

    if not all_projected:
        return [], []

    all_x = [x for _, pts in all_projected for x, _ in pts]
    all_y = [y for _, pts in all_projected for _, y in pts]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    range_x = max_x - min_x
    range_y = max_y - min_y
    if range_x < 0.0001:
        range_x = 1.0
    if range_y < 0.0001:
        range_y = 1.0
    scale = max(range_x, range_y)

    strokes_2d = []
    original_indices = []
    for stroke_idx, points in all_projected:
        normalized = [((x - min_x) / scale * 10.0, (y - min_y) / scale * 10.0) for x, y in points]
        strokes_2d.append(normalized)
        original_indices.append(stroke_idx)

    return strokes_2d, original_indices


def to_cpp_strokes(strokes_2d):
    flat_data = []
    for stroke in strokes_2d:
        for x, y in stroke:
            flat_data.append(x)
            flat_data.append(y)
        flat_data.extend((-1.0, -1.0))

    if flat_data and flat_data[-2:] == [-1.0, -1.0]:
        flat_data = flat_data[:-2]

    return np.array(flat_data, dtype=np.float32)
