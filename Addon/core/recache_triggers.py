import bpy
from . import cache
from .registry import get_targets

_owner = object()           # msgbus owner token
_last_mode = {}

_GP_TYPES = ('GREASEPENCIL', 'GPENCIL')



def _is_busy():
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
    if not _last_mode:
        return
    existing = bpy.data.objects
    dead = [n for n in _last_mode if n not in existing]
    for n in dead:
        _last_mode.pop(n, None)



def _on_mode_change():
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



def subscribe_msgbus():
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
