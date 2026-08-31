"""draw_sensor — burst + silence + counts gate; 'finished drawing' via modal report."""

import time
import traceback

import bpy
from bpy.app.handlers import persistent
from bpy.props import StringProperty


# --- operators ---


class GP_OT_draw_sensor_report(bpy.types.Operator):
    bl_idname = "gp.draw_sensor_report"
    bl_label = "Draw Sensor Report"
    bl_options = {"REGISTER"}

    message: StringProperty(default="finished drawing")

    def execute(self, context):
        self.report({"INFO"}, self.message)
        return {"FINISHED"}


# Modal watcher — holds modal context so report appears in the Status Bar.
# Direct reports from handlers/timers are suppressed by Blender.
_pending_report_msg = None


class GP_OT_draw_sensor_watcher(bpy.types.Operator):
    bl_idname = "gp.draw_sensor_watcher"
    bl_label = "Draw Sensor Watcher"
    bl_options = {"REGISTER"}

    _timer = None

    def modal(self, context, event):
        global _pending_report_msg
        if event.type == "TIMER" and _pending_report_msg is not None:
            message = _pending_report_msg
            _pending_report_msg = None
            self.report({"INFO"}, message)
        return {"PASS_THROUGH"}

    def invoke(self, context, event):
        window_manager = context.window_manager
        self._timer = window_manager.event_timer_add(0.1, window=context.window)
        window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        window_manager = context.window_manager
        if self._timer is not None:
            window_manager.event_timer_remove(self._timer)
            self._timer = None


def _request_report(message: str) -> None:
    global _pending_report_msg
    _pending_report_msg = message


# --- detection logic ---

_IDLE = 0.45
_last_burst = 0.0
_has_pending = False
_last_stable = None


def _gp_types():
    types = []
    for name in ("GreasePencil", "GreasePencilv3"):
        grease_pencil_type = getattr(bpy.types, name, None)
        if grease_pencil_type is not None:
            types.append(grease_pencil_type)
    return tuple(types)


def _is_busy() -> bool:
    try:
        screen = getattr(bpy.context, "screen", None)
        if screen and screen.is_animation_playing:
            return True
    except Exception:
        pass

    try:
        from ..utils import visibility

        return visibility._is_rendering()
    except Exception:
        return False


def _in_draw_mode() -> bool:
    # Only arm while actually painting with a Grease Pencil brush.
    try:
        active = bpy.context.active_object
        if not active or active.type != "GREASEPENCIL":
            return False
        return getattr(active, "mode", "") in ("PAINT_GPENCIL", "PAINT_GREASE_PENCIL")
    except Exception:
        return False


def _get_total_counts() -> tuple[int, int]:
    total_strokes = 0
    total_points = 0
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
    global _has_pending, _last_stable
    try:
        if not _has_pending:
            return None

        if _is_busy():
            return 0.15

        elapsed = time.monotonic() - _last_burst
        if elapsed < _IDLE:
            return 0.12

        current = _get_total_counts()
        previous = _last_stable if _last_stable is not None else current

        grew = current[0] > previous[0] or current[1] > previous[1]
        if grew:
            _last_stable = current
            _request_report("finished drawing")
            _has_pending = False
            return None

        # Suppress false positives (mode switch, file load, undo) — only report real growth.
        if current != previous:
            _last_stable = current
        _has_pending = False
        return None

    except Exception as error:
        print(f"[GPAI draw_sensor][ERROR] {error}\n{traceback.format_exc()}")
        _has_pending = False
        return None


@persistent
def on_depsgraph_update(scene, depsgraph):
    global _last_burst, _has_pending

    if _is_busy() or not depsgraph:
        return

    gp_types = _gp_types()
    has_geometry_update = False

    try:
        for update in depsgraph.updates:
            try:
                if not bool(getattr(update, "is_updated_geometry", False)):
                    continue

                is_data = isinstance(update.id, gp_types) if gp_types else False

                is_object = False
                try:
                    if isinstance(update.id, bpy.types.Object) and update.id.type == "GREASEPENCIL":
                        is_object = True
                except Exception:
                    pass

                if is_data or is_object:
                    has_geometry_update = True
                    break
            except Exception:
                continue
    except Exception:
        return

    if not has_geometry_update or not _in_draw_mode():
        return

    _last_burst = time.monotonic()
    _has_pending = True

    try:
        already_registered = bpy.app.timers.is_registered(_idle_check)
    except Exception:
        already_registered = False

    if not already_registered:
        bpy.app.timers.register(_idle_check, first_interval=_IDLE)


@persistent
def on_load_post(dummy):
    # Re-baseline on file load — no time grace needed.
    global _last_stable, _has_pending, _pending_report_msg
    _has_pending = False
    _pending_report_msg = None

    try:
        if bpy.app.timers.is_registered(_idle_check):
            bpy.app.timers.unregister(_idle_check)
    except Exception:
        pass

    _last_stable = _get_total_counts()


def _ensure_watcher_running():
    try:
        bpy.ops.gp.draw_sensor_watcher("INVOKE_DEFAULT")
    except Exception as error:
        print(f"[GPAI draw_sensor][ERROR] watcher start failed: {error}")


def register():
    global _last_stable

    try:
        bpy.utils.register_class(GP_OT_draw_sensor_report)
    except Exception:
        pass

    try:
        bpy.utils.register_class(GP_OT_draw_sensor_watcher)
    except Exception:
        pass

    _last_stable = _get_total_counts()

    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)

    try:
        bpy.app.timers.register(_ensure_watcher_running, first_interval=0.5)
    except Exception:
        pass


def unregister():
    global _has_pending, _pending_report_msg
    _has_pending = False
    _pending_report_msg = None

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

    try:
        bpy.utils.unregister_class(GP_OT_draw_sensor_watcher)
    except Exception:
        pass

    try:
        bpy.utils.unregister_class(GP_OT_draw_sensor_report)
    except Exception:
        pass
