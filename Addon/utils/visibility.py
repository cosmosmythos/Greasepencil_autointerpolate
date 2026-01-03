"""
Smart Visibility System for GP Auto Interpolate
Ported from proven Local implementation with intelligent scrub detection,
timer-based timeout, and animation awareness.
"""

import bpy
import time

# Performance tuning constants
SCRUB_DETECTION_THRESHOLD = 0.1  # Time threshold (seconds) to detect scrubbing
SCRUB_TIMEOUT_DELAY = 0.1        # Delay (seconds) before turning off modifier after scrub stops

# Visibility manager state (ported from Local)
visibility_state = {
    'last_frame': None,
    'last_frame_time': None,
    'is_scrubbing': False,
    'scrub_timer': None
}


def ensure_visibility_state():
    """Ensures visibility_state is properly initialized."""
    global visibility_state
    if not isinstance(visibility_state, dict):
        visibility_state = {}
    
    required_keys = ['last_frame', 'last_frame_time', 'is_scrubbing', 'scrub_timer']
    for key in required_keys:
        if key not in visibility_state:
            if key == 'is_scrubbing':
                visibility_state[key] = False
            else:
                visibility_state[key] = None


def detect_scrubbing():
    """Detects if user is actively scrubbing the timeline based on frame change frequency."""
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


def should_show_modifier():
    """Determines if modifier should be visible based on interpolation state and play/scrub activity."""
    scene = bpy.context.scene
    
    if not scene.gp_interpolation_enabled:
        return False
    
    is_playing = bpy.context.screen.is_animation_playing
    is_scrubbing = detect_scrubbing()
    
    return is_playing or is_scrubbing


def _get_modifier():
    """Get the Auto-Interpolate modifier from target object."""
    scene = bpy.context.scene
    gp_name = scene.get("gp_interpolation_target", "")
    if not gp_name:
        return None
    gp = bpy.data.objects.get(gp_name)
    if not gp:
        return None
    return gp.modifiers.get("Auto-Interpolate (c)")


def _set_modifier_visible(visible: bool):
    """Set modifier visibility with redundancy check."""
    modifier = _get_modifier()
    if not modifier:
        return
    
    if modifier.show_viewport != visible:
        modifier.show_viewport = visible


def update_modifier_visibility():
    """Updates the visibility of the Auto-Interpolate modifier based on current state.

    Important: frame_change_post handlers can run in contexts where bpy.context.active_object
    is unavailable. Always resolve the target object via the stored scene property.
    """
    scene = bpy.context.scene

    target_name = scene.get("gp_interpolation_target")
    if not target_name:
        return

    gp_obj = bpy.data.objects.get(target_name)
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return

    should_show = should_show_modifier()
    _set_modifier_visible(should_show)


def stop_scrub_timer():
    """Stops and clears the scrub detection timer."""
    global visibility_state
    ensure_visibility_state()
    if bpy.app.timers.is_registered(scrub_timeout):
        bpy.app.timers.unregister(scrub_timeout)
    visibility_state['scrub_timer'] = None


def scrub_timeout():
    """Timer callback to detect when scrubbing has stopped."""
    global visibility_state
    visibility_state['is_scrubbing'] = False
    update_modifier_visibility()
    visibility_state['scrub_timer'] = None
    return None


def on_frame_change(scene, depsgraph=None):
    """
    Integrated frame change handler with visibility management and interpolation.
    Ported from proven Local implementation.
    """
    # Early exit if interpolation disabled
    if not scene.gp_interpolation_enabled:
        return
    
    # Check if target object matches
    target_name = scene.get("gp_interpolation_target")
    if not target_name:
        return
    
    # In frame_change_post, bpy.context may not expose active_object.
    # Use the stored target name to resolve the object directly.
    active_obj = bpy.data.objects.get(target_name)
    if not active_obj:
        return
    
    # Update modifier visibility
    update_modifier_visibility()
    
    # Set up scrub timeout timer if scrubbing detected
    global visibility_state
    ensure_visibility_state()
    if visibility_state.get('is_scrubbing', False):
        stop_scrub_timer()
        visibility_state['scrub_timer'] = bpy.app.timers.register(scrub_timeout, first_interval=SCRUB_TIMEOUT_DELAY)
    
    # Only process interpolation if modifier should be visible (optimization)
    if should_show_modifier():
        from ..core import interpolation
        # interpolation.process expects a context-like object; in restricted handler contexts
        # bpy.context may miss attributes, so pass it through but guard inside interpolation.
        interpolation.process(bpy.context)


def clear():
    """Clear all visibility state and stop timers."""
    global visibility_state
    stop_scrub_timer()
    visibility_state = {
        'last_frame': None,
        'last_frame_time': None,
        'is_scrubbing': False,
        'scrub_timer': None
    }
