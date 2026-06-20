"""
Surgical recache triggers for user-intuitive moments.

Covers:
  - Mode switch on a GP object (DRAW / EDIT / SCULPT / OBJECT / WEIGHT / VERTEX)
  - Active object change

NOT covered here (handled elsewhere):
  - Geometry edits             -> core.npanel_handlers.on_depsgraph_update
  - Dopesheet key shift        -> deferred keyframe-signature check via
                                  npanel_handlers._deferred_sig_check() timer
  - Undo / Redo                -> same depsgraph path within 0.15 s

Subscriptions are owned by `_owner` and MUST be re-installed on every
file load (`subscribe_msgbus`); see Addon/__init__.py:on_load_post.
"""
import bpy
from . import cache
from .registry import get_targets

_owner = object()           # msgbus owner token
_last_mode = {}             # obj_name -> last seen mode string

_GP_TYPES = ('GREASEPENCIL', 'GPENCIL')


# --- Guards --------------------------------------------------------------
def _is_busy():
    """True during playback or render -- never recache then."""
    try:
        screen = bpy.context.screen
        if screen and screen.is_animation_playing:
            return True
    except Exception:
        pass
    try:
        from ..utils import visibility
        return visibility._is_rendering()
    except Exception:
        return False


def _prune_stale_mode_entries():
    """Drop _last_mode keys for objects that no longer exist."""
    if not _last_mode:
        return
    existing = bpy.data.objects
    dead = [n for n in _last_mode if n not in existing]
    for n in dead:
        _last_mode.pop(n, None)


# --- MSGBUS callbacks ----------------------------------------------------
def _on_mode_change():
    """Active GP object's mode changed via Tab / header / operator."""
    if _is_busy():
        return
    obj = bpy.context.active_object
    if not obj or obj.type not in _GP_TYPES:
        return
    prev = _last_mode.get(obj.name)
    cur = obj.mode
    if prev == cur:
        return
    _last_mode[obj.name] = cur

    scene = bpy.context.scene
    if not scene.gp_interpolation_enabled:
        return
    if obj.name in get_targets(scene):
        cache.mark_dirty(obj.name)


def _on_active_object_change():
    """Active object changed in the outliner / viewport."""
    if _is_busy():
        return
    obj = bpy.context.active_object
    if not obj or obj.type not in _GP_TYPES:
        return
    scene = bpy.context.scene
    if not scene.gp_interpolation_enabled:
        return
    if obj.name in get_targets(scene):
        cache.mark_dirty(obj.name)
    _prune_stale_mode_entries()


# --- Subscribe / unsubscribe --------------------------------------------
def subscribe_msgbus():
    """(Re)install all msgbus subscriptions. Idempotent -- safe to call
    repeatedly. MUST be called from both register() and on_load_post."""
    bpy.msgbus.clear_by_owner(_owner)

    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=_owner,
        args=(),
        notify=_on_mode_change,
        options={'PERSISTENT'},
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.LayerObjects, "active"),
        owner=_owner,
        args=(),
        notify=_on_active_object_change,
        options={'PERSISTENT'},
    )


def register():
    subscribe_msgbus()


def unregister():
    try:
        bpy.msgbus.clear_by_owner(_owner)
    except Exception:
        pass
    _last_mode.clear()
