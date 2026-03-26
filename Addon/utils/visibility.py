"""
Visibility System for GP Auto Interpolate
Rule: modifier ON only during playback or active scrubbing. OFF otherwise.
"""

import bpy
import time

SCRUB_DETECTION_THRESHOLD = 0.1
SCRUB_TIMEOUT_DELAY = 0.05

visibility_state = {
    'last_frame': None,
    'last_frame_time': None,
    'is_scrubbing': False,
    'scrub_timer': None
}


def ensure_visibility_state():
    global visibility_state
    if not isinstance(visibility_state, dict):
        visibility_state = {}
    for key in ('last_frame', 'last_frame_time', 'is_scrubbing', 'scrub_timer'):
        if key not in visibility_state:
            visibility_state[key] = False if key == 'is_scrubbing' else None


def detect_scrubbing():
    global visibility_state
    ensure_visibility_state()

    current_time = time.time()
    current_frame = bpy.context.scene.frame_current

    if visibility_state['last_frame_time'] is None:
        visibility_state['last_frame_time'] = current_time
        visibility_state['last_frame'] = current_frame
        return False

    if current_frame == visibility_state['last_frame']:
        return visibility_state['is_scrubbing']

    time_diff = current_time - visibility_state['last_frame_time']
    frame_diff = abs(current_frame - visibility_state['last_frame'])
    is_scrubbing = (time_diff < SCRUB_DETECTION_THRESHOLD and frame_diff >= 1) or frame_diff > 1

    visibility_state['last_frame'] = current_frame
    visibility_state['last_frame_time'] = current_time
    visibility_state['is_scrubbing'] = is_scrubbing
    return is_scrubbing


def playback_watchdog():
    """Polls playback state. When playback stops, hides modifier."""
    scene = bpy.context.scene
    
    if not scene.gp_interpolation_enabled:
        return None
    
    if not bpy.context.screen.is_animation_playing:
        _set_modifier_visible(False)
        return None
    
    return 0.05


def _get_modifier():
    scene = bpy.context.scene
    gp_name = scene.get("gp_interpolation_target", "")
    if not gp_name:
        return None
    gp = bpy.data.objects.get(gp_name)
    if not gp:
        return None
    return gp.modifiers.get("Auto-Interpolate (c)")


def _set_modifier_visible(visible: bool):
    modifier = _get_modifier()
    if modifier and modifier.show_viewport != visible:
        modifier.show_viewport = visible


def update_modifier_visibility():
    """Enforce visibility rule. Used as initial sync after toggling ON."""
    is_playing = bpy.context.screen.is_animation_playing
    is_scrubbing = detect_scrubbing()

    if is_playing or is_scrubbing:
        _set_modifier_visible(True)
    else:
        force_modifier_off_for_authoring()


def stop_scrub_timer():
    global visibility_state
    ensure_visibility_state()
    if bpy.app.timers.is_registered(scrub_timeout):
        bpy.app.timers.unregister(scrub_timeout)
    if bpy.app.timers.is_registered(playback_watchdog):
        bpy.app.timers.unregister(playback_watchdog)        
    visibility_state['scrub_timer'] = None


def scrub_timeout():
    """Dead-man timer: hide modifier when scrubbing ends."""
    if not bpy.context.screen.is_animation_playing:
        _set_modifier_visible(False)
    return None


def on_frame_change(scene, depsgraph=None):
    """Per-frame visibility controller. Single source of truth."""
    if not scene.gp_interpolation_enabled:
        force_modifier_off_for_authoring()
        return

    target_name = scene.get("gp_interpolation_target")
    gp_obj = bpy.data.objects.get(target_name) if target_name else None
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        force_modifier_off_for_authoring()
        return

    is_playing = bpy.context.screen.is_animation_playing
    is_scrubbing = detect_scrubbing()

    if is_playing or is_scrubbing:
        _set_modifier_visible(True)

        if bpy.app.timers.is_registered(scrub_timeout):
            bpy.app.timers.unregister(scrub_timeout)

        if is_scrubbing and not is_playing:
            bpy.app.timers.register(scrub_timeout, first_interval=SCRUB_TIMEOUT_DELAY)
        if is_playing and not bpy.app.timers.is_registered(playback_watchdog):
            bpy.app.timers.register(playback_watchdog, first_interval=0.05)

        from ..core import interpolation
        interpolation.process(bpy.context)
    else:
        force_modifier_off_for_authoring()


def force_modifier_off_for_authoring():
    """Unconditionally hide modifier and reset scrub state."""
    global visibility_state
    ensure_visibility_state()
    stop_scrub_timer()
    visibility_state['is_scrubbing'] = False
    _set_modifier_visible(False)


def on_undo_redo(scene, depsgraph=None):
    """Correct modifier visibility after undo/redo (which can restore show_viewport=True)."""
    handler_active = on_frame_change in bpy.app.handlers.frame_change_post

    if handler_active and not scene.gp_interpolation_enabled:
        scene.gp_interpolation_enabled = True
        from ..core import cache
        cache.clear()

    if not scene.gp_interpolation_enabled or not bpy.context.screen.is_animation_playing:
        _set_modifier_visible(False)


def clear():
    global visibility_state
    stop_scrub_timer()
    visibility_state = {
        'last_frame': None,
        'last_frame_time': None,
        'is_scrubbing': False,
        'scrub_timer': None
    }