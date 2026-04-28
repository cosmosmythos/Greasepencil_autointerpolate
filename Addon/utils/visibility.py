"""
Visibility System for GP Auto Interpolate
Rule: modifier ON only during playback or active scrubbing. OFF otherwise.

v2: Multi-object — controls modifiers on ALL registered GP objects,
    not just one.
"""

import bpy
import time

from ..core.constants import MODIFIER_NAME

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
        _set_all_modifiers_visible(False)
        return None

    return 0.05


# ---------------------------------------------------------------------------
# Multi-object modifier helpers
# ---------------------------------------------------------------------------

def _get_target_objects():
    """Return list of (obj, modifier) pairs for all registered targets."""
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
    """Set modifier visibility on ALL registered GP objects."""
    for _obj, mod in _get_target_objects():
        if mod.show_viewport != visible:
            mod.show_viewport = visible


def _set_modifier_visible(visible: bool):
    """Legacy single-object alias — now applies to all targets."""
    _set_all_modifiers_visible(visible)


def update_modifier_visibility():
    """Enforce visibility rule. Used as initial sync after toggling ON."""
    is_playing = bpy.context.screen.is_animation_playing
    is_scrubbing = detect_scrubbing()

    if is_playing or is_scrubbing:
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
    """Dead-man timer: hide modifier when scrubbing ends."""
    if not bpy.context.screen.is_animation_playing:
        _set_all_modifiers_visible(False)
    return None


def on_frame_change(scene, depsgraph=None):
    """Per-frame visibility controller. Single source of truth."""
    if not scene.gp_interpolation_enabled:
        force_all_modifiers_off()
        return

    # Validate targets exist (handles renames/deletes)
    from ..core.registry import validate_targets
    targets = validate_targets(scene)
    if not targets:
        force_all_modifiers_off()
        return

    is_playing = bpy.context.screen.is_animation_playing
    is_scrubbing = detect_scrubbing()

    if is_playing or is_scrubbing:
        _set_all_modifiers_visible(True)

        if bpy.app.timers.is_registered(scrub_timeout):
            bpy.app.timers.unregister(scrub_timeout)

        if is_scrubbing and not is_playing:
            bpy.app.timers.register(scrub_timeout, first_interval=SCRUB_TIMEOUT_DELAY)
        if is_playing and not bpy.app.timers.is_registered(playback_watchdog):
            bpy.app.timers.register(playback_watchdog, first_interval=0.05)

        # Process ALL registered objects
        from ..core import interpolation
        interpolation.process_all(bpy.context)
    else:
        force_all_modifiers_off()


def force_modifier_off_for_object(gp_obj):
    """Hide modifier on a specific object and reset scrub state."""
    mod = gp_obj.modifiers.get(MODIFIER_NAME)
    if mod and mod.show_viewport:
        mod.show_viewport = False


def force_all_modifiers_off():
    """Unconditionally hide modifiers on ALL registered objects."""
    global visibility_state
    ensure_visibility_state()
    stop_scrub_timer()
    visibility_state['is_scrubbing'] = False
    _set_all_modifiers_visible(False)


# Legacy alias used by __init__.py unregister
def force_modifier_off_for_authoring():
    """Legacy alias for force_all_modifiers_off()."""
    force_all_modifiers_off()


def on_undo_redo(scene, depsgraph=None):
    """Correct modifier visibility after undo/redo."""
    handler_active = on_frame_change in bpy.app.handlers.frame_change_post

    if handler_active and not scene.gp_interpolation_enabled:
        scene.gp_interpolation_enabled = True
        from ..core import cache
        cache.clear()

    if not scene.gp_interpolation_enabled or not bpy.context.screen.is_animation_playing:
        _set_all_modifiers_visible(False)


def clear():
    global visibility_state
    stop_scrub_timer()
    visibility_state = {
        'last_frame': None,
        'last_frame_time': None,
        'is_scrubbing': False,
        'scrub_timer': None
    }