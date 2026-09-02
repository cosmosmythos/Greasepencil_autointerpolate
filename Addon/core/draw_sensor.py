
import time
import traceback

import bpy
from bpy.app.handlers import persistent

_drawing_done_callbacks = []

_IDLE = 0.05
_last_burst = 0.0
_has_pending = False
_last_stable = None
_was_drawing = False
_release_seen = False
_release_time = 0.0

_PREF_ID = "bl_ext.user_default.gp_auto_interpolate"


def register_drawing_done_callback(callback):
    if callback not in _drawing_done_callbacks:
        _drawing_done_callbacks.append(callback)


def unregister_drawing_done_callback(callback):
    try:
        _drawing_done_callbacks.remove(callback)
    except ValueError:
        pass


def _notify_drawing_done():
    for callback in list(_drawing_done_callbacks):
        try:
            callback()
        except Exception as error:
            print(f"[GPAI draw_sensor] callback {callback!r} failed: {error}\n{traceback.format_exc()}")


def _gp_types():
    types = []
    for name in ("GreasePencil", "GreasePencilv3"):
        t = getattr(bpy.types, name, None)
        if t is not None:
            types.append(t)
    return tuple(types)


def _is_busy() -> bool:
    try:
        if bpy.context.screen and bpy.context.screen.is_animation_playing:
            return True
    except Exception:
        pass
    try:
        from ..utils import visibility
        return visibility._is_rendering()
    except Exception:
        return False


def _in_draw_mode() -> bool:
    try:
        obj = bpy.context.active_object
        return obj and obj.type == "GREASEPENCIL" and getattr(obj, "mode", "") in ("PAINT_GPENCIL", "PAINT_GREASE_PENCIL")
    except Exception:
        return False


def _sensor_enabled() -> bool:
    try:
        addon = bpy.context.preferences.addons.get(_PREF_ID)
        if addon is not None:
            return bool(addon.preferences.draw_sensor_enabled)
    except Exception:
        pass
    return True


def _is_mouse_down() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(0x01) & 0x8000)
    except Exception:
        return False


def _is_brush_stroke_running() -> bool:
    return _is_mouse_down() and _in_draw_mode()


def _has_gp_geometry_update(depsgraph) -> bool:
    gp_types = _gp_types()
    try:
        for update in depsgraph.updates:
            if not bool(getattr(update, "is_updated_geometry", False)):
                continue
            is_data = isinstance(update.id, gp_types) if gp_types else False
            is_object = isinstance(update.id, bpy.types.Object) and update.id.type == "GREASEPENCIL"
            if is_data or is_object:
                return True
    except Exception:
        pass
    return False


def _ensure_timer():
    try:
        if not bpy.app.timers.is_registered(_idle_check):
            bpy.app.timers.register(_idle_check, first_interval=_IDLE)
    except Exception:
        pass


def _get_total_counts() -> tuple[int, int]:
    total_strokes = total_points = 0
    try:
        for obj in bpy.data.objects:
            if obj.type != "GREASEPENCIL" or not obj.data:
                continue
            for layer in obj.data.layers:
                for frame in layer.frames:
                    drawing = getattr(frame, "drawing", None)
                    if drawing is None:
                        continue
                    try:
                        strokes = drawing.strokes
                        total_strokes += len(strokes)
                        for stroke in strokes:
                            try:
                                total_points += len(stroke.points)
                            except Exception:
                                pass
                    except Exception:
                        continue
    except Exception:
        pass
    return (total_strokes, total_points)


def _idle_check():
    global _has_pending, _last_stable, _release_seen, _was_drawing, _last_burst, _release_time
    try:
        if not _sensor_enabled():
            _has_pending = False
            _release_seen = False
            return None
        is_drawing = _is_brush_stroke_running()
        if is_drawing:
            _was_drawing = True
            return 0.03
        if _was_drawing:
            _was_drawing = False
            _release_seen = True
            _has_pending = True
            _last_burst = time.monotonic()
            _release_time = _last_burst
            return _IDLE
        if not _has_pending and not _release_seen:
            return None
        if _is_busy():
            return 0.15
        elapsed = time.monotonic() - _last_burst
        if elapsed < _IDLE:
            return 0.03
        current = _get_total_counts()
        previous = _last_stable if _last_stable is not None else current
        grew = current[0] > previous[0] or current[1] > previous[1]

        if _release_seen:
            _last_stable = current
            _release_seen = False
            _has_pending = False
            if grew:
                _notify_drawing_done()
            return None

        if grew:
            _last_stable = current
            _has_pending = False
            _notify_drawing_done()
            return None
        if current != previous:
            _last_stable = current
        _has_pending = False
        return None
    except Exception as error:
        print(f"[GPAI draw_sensor] {error}\n{traceback.format_exc()}")
        _has_pending = False
        _release_seen = False
        return None


@persistent
def on_depsgraph_update(scene, depsgraph):
    global _last_burst, _has_pending, _was_drawing, _release_seen, _release_time
    if not _sensor_enabled() or _is_busy() or not depsgraph:
        return
    is_drawing = _is_brush_stroke_running()
    if is_drawing:
        _was_drawing = True
        if _has_gp_geometry_update(depsgraph) and _in_draw_mode():
            _last_burst = time.monotonic()
            _has_pending = True
            _ensure_timer()
        return
    if _was_drawing:
        _was_drawing = False
        _release_seen = True
        _has_pending = True
        _last_burst = time.monotonic()
        _release_time = _last_burst
        _ensure_timer()
        return
    has_geo = _has_gp_geometry_update(depsgraph)
    if not has_geo or not _in_draw_mode():
        return
    if _release_seen:
        _last_burst = time.monotonic()
        _has_pending = True
        _ensure_timer()
        return
    _last_burst = time.monotonic()
    _has_pending = True
    _ensure_timer()


@persistent
def on_load_post(dummy):
    global _last_stable, _has_pending, _was_drawing, _release_seen
    _has_pending = False
    _was_drawing = False
    _release_seen = False
    try:
        if bpy.app.timers.is_registered(_idle_check):
            bpy.app.timers.unregister(_idle_check)
    except Exception:
        pass
    _last_stable = _get_total_counts()


def register():
    global _last_stable
    _last_stable = _get_total_counts()
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)


def unregister():
    global _has_pending, _was_drawing, _release_seen
    _has_pending = False
    _was_drawing = False
    _release_seen = False
    try:
        if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    except Exception:
        pass
    try:
        if on_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_load_post)
    except Exception:
        pass
    try:
        if bpy.app.timers.is_registered(_idle_check):
            bpy.app.timers.unregister(_idle_check)
    except Exception:
        pass
    _drawing_done_callbacks.clear()
