
import bpy
import time

from ..core.constants import MODIFIER_NAME
from ..core import cache

SCRUB_DETECTION_THRESHOLD = 0.1
SCRUB_TIMEOUT_DELAY = 0.05

visibility_state = {
    'last_frame': None,
    'last_frame_time': None,
    'is_scrubbing': False,
    'scrub_timer': None,
    'is_rendering': False,
}


def ensure_visibility_state():
    global visibility_state
    if not isinstance(visibility_state, dict):
        visibility_state = {}
    for key in ('last_frame', 'last_frame_time', 'is_scrubbing', 'scrub_timer', 'is_rendering'):
        if key not in visibility_state:
            visibility_state[key] = False if key in {'is_scrubbing', 'is_rendering'} else None


def _get_screen():
    try:
        return bpy.context.screen
    except Exception:
        return None


def _is_animation_playing():
    screen = _get_screen()
    return bool(screen and screen.is_animation_playing)


def _is_rendering():
    ensure_visibility_state()
    return visibility_state['is_rendering']


def detect_scrubbing(scene):
    global visibility_state
    ensure_visibility_state()
    current_time = time.time()
    current_frame = scene.frame_current

    last_frame = visibility_state['last_frame']
    last_time = visibility_state['last_frame_time']



    if last_time is None or last_frame is None:
        visibility_state['last_frame'] = current_frame
        visibility_state['last_frame_time'] = current_time

        visibility_state['is_scrubbing'] = False
        return False

    if current_frame == last_frame:
        return visibility_state['is_scrubbing']

    time_diff = current_time - last_time
    frame_diff = abs(current_frame - last_frame)
    is_scrubbing = (time_diff < SCRUB_DETECTION_THRESHOLD and frame_diff >= 1) or frame_diff > 1

    visibility_state['last_frame'] = current_frame
    visibility_state['last_frame_time'] = current_time
    visibility_state['is_scrubbing'] = is_scrubbing
    return is_scrubbing


def playback_watchdog():
    scene = bpy.context.scene

    if not scene.gp_interpolation_enabled:
        return None

    if _is_rendering():
        return 0.05

    if not _is_animation_playing():
        _set_all_modifiers_visible(False)
        return None

    return 0.05






def _get_target_objects():
    from ..core.registry import get_targets
    results = []
    targets = get_targets(bpy.context.scene)
    for obj_name in targets:
        gp_obj = bpy.data.objects.get(obj_name)
        if gp_obj and gp_obj.type == 'GREASEPENCIL':
            mod = gp_obj.modifiers.get(MODIFIER_NAME)
            if mod:
                results.append((gp_obj, mod))
    return results


def _set_all_modifiers_visible(visible: bool):
    for _obj, mod in _get_target_objects():
        if mod.show_viewport != visible:
            mod.show_viewport = visible


def _set_modifier_visible(visible: bool):
    _set_all_modifiers_visible(visible)


def update_modifier_visibility():
    scene = bpy.context.scene
    is_playing = _is_animation_playing()
    is_scrubbing = detect_scrubbing(scene)

    if _is_rendering() or is_playing or is_scrubbing:
        _set_all_modifiers_visible(True)
    else:
        force_all_modifiers_off()


def stop_scrub_timer():
    global visibility_state
    ensure_visibility_state()
    if bpy.app.timers.is_registered(scrub_timeout):
        bpy.app.timers.unregister(scrub_timeout)
    if bpy.app.timers.is_registered(playback_watchdog):
        bpy.app.timers.unregister(playback_watchdog)
    visibility_state['scrub_timer'] = None


def scrub_timeout():
    if not _is_animation_playing() and not _is_rendering():
        _set_all_modifiers_visible(False)
    return None


def on_frame_change(scene, depsgraph=None):
    if not scene.gp_interpolation_enabled:
        force_all_modifiers_off()
        return

    from ..core.registry import validate_targets
    targets = validate_targets(scene)
    if not targets:
        force_all_modifiers_off()
        return

    is_playing = _is_animation_playing()
    is_rendering = _is_rendering()
    is_scrubbing = False if is_rendering else detect_scrubbing(scene)

    if is_rendering or is_playing or is_scrubbing:


        # hitch on spacebar).
        _set_all_modifiers_visible(True)

        if bpy.app.timers.is_registered(scrub_timeout):
            bpy.app.timers.unregister(scrub_timeout)
        if is_scrubbing and not is_playing:
            bpy.app.timers.register(scrub_timeout, first_interval=SCRUB_TIMEOUT_DELAY)
        if is_playing and not bpy.app.timers.is_registered(playback_watchdog):
            bpy.app.timers.register(playback_watchdog, first_interval=0.05)

        from ..core import interpolation
        interpolation.process_scene(scene)
    else:
        force_all_modifiers_off()


def force_modifier_off_for_object(gp_obj):
    mod = gp_obj.modifiers.get(MODIFIER_NAME)
    if mod and mod.show_viewport:
        mod.show_viewport = False


def force_all_modifiers_off():
    global visibility_state
    ensure_visibility_state()
    stop_scrub_timer()
    visibility_state['is_scrubbing'] = False
    visibility_state['is_rendering'] = False
    _set_all_modifiers_visible(False)



def force_modifier_off_for_authoring():
    force_all_modifiers_off()


def on_undo_redo(scene, depsgraph=None):
    from ..core import cache as _cache
    # undo/redo is a DNA memfile swap - cached GreasePencilFrame wrappers are dead StructRNA; never dereference them
    if _cache.cache_registry:
        _cache.clear()
    handler_active = on_frame_change in bpy.app.handlers.frame_change_post
    if handler_active and not scene.gp_interpolation_enabled:
        scene.gp_interpolation_enabled = True
    if not scene.gp_interpolation_enabled or not _is_animation_playing():
        _set_all_modifiers_visible(False)


def on_render_pre(scene, depsgraph=None):
    ensure_visibility_state()
    visibility_state['is_rendering'] = True
    for _obj, mod in _get_target_objects():
        if mod.show_viewport != True:
            mod.show_viewport = True
        if hasattr(mod, "show_render") and mod.show_render != True:
            mod.show_render = True


def on_render_post(scene, depsgraph=None):
    ensure_visibility_state()
    visibility_state['is_rendering'] = False
    for _obj, mod in _get_target_objects():
        if hasattr(mod, "show_render") and mod.show_render:
            mod.show_render = False
    update_modifier_visibility()


def clear():
    global visibility_state
    stop_scrub_timer()
    visibility_state = {
        'last_frame': None,
        'last_frame_time': None,
        'is_scrubbing': False,
        'scrub_timer': None,
        'is_rendering': False,
    }
