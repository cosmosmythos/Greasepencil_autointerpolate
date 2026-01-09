"""
Linked Stroke Overlay System
Draws bright orange overlay on user-linked stroke pairs.

Visibility conditions:
1. _show_linked_overlay toggle is enabled
2. Playhead is on a keyframe holding the stroke OR keyframe is selected on timeline
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import bpy_extras.view3d_utils

# Module state
overlay_state = {
    'draw_handler': None,
    'redraw_timer_running': False,
}

# Bright orange color for linked strokes
LINKED_STROKE_COLOR = (1.0, 0.5, 0.0, 0.85)


def get_linked_overlay_state():
    """Get the current overlay toggle state from gp_correspondence."""
    from .. import gp_correspondence
    return gp_correspondence._show_linked_overlay


def set_linked_overlay_state(value):
    """Set the overlay toggle state in gp_correspondence."""
    from .. import gp_correspondence
    gp_correspondence._show_linked_overlay = value


def get_link_constraints():
    """Get the current link constraints from gp_correspondence."""
    from .. import gp_correspondence
    return gp_correspondence._link_constraints


def is_on_keyframe_or_selected(gp_obj, layer):
    """
    Check if playhead is on a keyframe OR any keyframe is selected.
    
    Returns:
        set of frame numbers that should show linked strokes
    """
    visible_frames = set()
    current_frame = bpy.context.scene.frame_current
    
    for frame in layer.frames:
        # Condition 1: Playhead is on this keyframe
        if frame.frame_number == current_frame:
            visible_frames.add(frame.frame_number)
        # Condition 2: Keyframe is selected in timeline
        if frame.select:
            visible_frames.add(frame.frame_number)
    
    return visible_frames


def get_stroke_points_world(gp_obj, layer, frame_num, stroke_idx):
    """Get stroke points in world coordinates."""
    for frame in layer.frames:
        if frame.frame_number == frame_num:
            if frame.drawing and stroke_idx < len(frame.drawing.strokes):
                stroke = frame.drawing.strokes[stroke_idx]
                mw = gp_obj.matrix_world
                return [mw @ p.position for p in stroke.points]
    return None


def convert_points_to_screen(points, region, rv3d):
    """Convert 3D world points to screen coordinates."""
    coords_2d = []
    for pt in points:
        try:
            screen_pt = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, pt)
            if screen_pt and len(screen_pt) >= 2:
                coords_2d.append((float(screen_pt[0]), float(screen_pt[1])))
        except (ValueError, TypeError, AttributeError):
            continue
    return coords_2d


def draw_stroke_overlay(coords_2d, color):
    """Draw a stroke overlay with the given color."""
    if len(coords_2d) < 2:
        return
    
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(4.0)
        
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords_2d})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        
    except Exception as e:
        print(f"[Linked Overlay] Draw error: {e}")


def draw_linked_strokes_main():
    """Main draw function for linked strokes overlay."""
    try:
        # Check if overlay should be shown
        if not get_linked_overlay_state():
            return
        
        context = bpy.context
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            return
        
        region = context.region
        rv3d = context.region_data
        
        if not region or not rv3d:
            return
        
        link_constraints = get_link_constraints()
        if not link_constraints:
            return
        
        # Get active layer index
        active_layer = gp_obj.data.layers.active
        if not active_layer:
            return
        
        active_layer_idx = None
        for idx, layer in enumerate(gp_obj.data.layers):
            if layer == active_layer:
                active_layer_idx = idx
                break
        
        if active_layer_idx is None:
            return
        
        # Get frames that should show linked strokes
        visible_frames = is_on_keyframe_or_selected(gp_obj, active_layer)
        
        if not visible_frames:
            return
        
        # Draw linked strokes for visible frames
        for constraint in link_constraints:
            layer_idx, frame1, stroke1_idx, frame2, stroke2_idx = constraint
            
            # Only draw for active layer
            if layer_idx != active_layer_idx:
                continue
            
            # Draw stroke on frame1 if visible
            if frame1 in visible_frames:
                points = get_stroke_points_world(gp_obj, active_layer, frame1, stroke1_idx)
                if points:
                    coords_2d = convert_points_to_screen(points, region, rv3d)
                    draw_stroke_overlay(coords_2d, LINKED_STROKE_COLOR)
            
            # Draw stroke on frame2 if visible
            if frame2 in visible_frames:
                points = get_stroke_points_world(gp_obj, active_layer, frame2, stroke2_idx)
                if points:
                    coords_2d = convert_points_to_screen(points, region, rv3d)
                    draw_stroke_overlay(coords_2d, LINKED_STROKE_COLOR)
    
    except Exception as e:
        print(f"[Linked Overlay] Main draw error: {e}")
    finally:
        # Always reset GPU state
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')


def refresh_overlay_display():
    """Force refresh of overlay display."""
    screen = getattr(bpy.context, "screen", None)
    if not screen:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _redraw_timer_callback():
    """Timer callback: keep viewports redrawing while overlay is active."""
    if get_linked_overlay_state():
        refresh_overlay_display()
        return 0.1  # 10 fps refresh rate
    
    overlay_state['redraw_timer_running'] = False
    return None


def _ensure_redraw_timer():
    """Start the redraw timer if it isn't already running."""
    if overlay_state['redraw_timer_running']:
        return
    if bpy.app.timers.is_registered(_redraw_timer_callback):
        overlay_state['redraw_timer_running'] = True
        return
    
    overlay_state['redraw_timer_running'] = True
    bpy.app.timers.register(_redraw_timer_callback, first_interval=0.1)


def _stop_redraw_timer():
    """Stop the redraw timer."""
    overlay_state['redraw_timer_running'] = False
    if bpy.app.timers.is_registered(_redraw_timer_callback):
        bpy.app.timers.unregister(_redraw_timer_callback)


def manage_draw_handler():
    """Smart handler management - register/unregister based on toggle state."""
    should_have_handler = get_linked_overlay_state()
    
    if should_have_handler and not overlay_state['draw_handler']:
        # Register handler
        overlay_state['draw_handler'] = bpy.types.SpaceView3D.draw_handler_add(
            draw_linked_strokes_main, (), 'WINDOW', 'POST_PIXEL')
        _ensure_redraw_timer()
        
    elif not should_have_handler and overlay_state['draw_handler']:
        # Unregister handler
        bpy.types.SpaceView3D.draw_handler_remove(overlay_state['draw_handler'], 'WINDOW')
        overlay_state['draw_handler'] = None
        _stop_redraw_timer()


def on_frame_change(scene, depsgraph=None):
    """Frame change handler - refresh overlay when playhead moves."""
    if get_linked_overlay_state():
        refresh_overlay_display()


# Operator: Toggle Linked Overlay
class GPCORR_OT_toggle_linked_overlay(bpy.types.Operator):
    bl_idname = "gpcorr.toggle_linked_overlay"
    bl_label = "Toggle Linked Strokes Overlay"
    bl_description = "Show/hide orange overlay on manually linked stroke pairs"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        current_state = get_linked_overlay_state()
        set_linked_overlay_state(not current_state)
        manage_draw_handler()
        refresh_overlay_display()
        return {'FINISHED'}


# Registration
classes = (
    GPCORR_OT_toggle_linked_overlay,
)


def register():
    """Register linked stroke overlay system."""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Hook into frame change handler
    if on_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame_change)


def unregister():
    """Unregister linked stroke overlay system."""
    # Clean up draw handler
    if overlay_state['draw_handler']:
        bpy.types.SpaceView3D.draw_handler_remove(overlay_state['draw_handler'], 'WINDOW')
        overlay_state['draw_handler'] = None
    
    _stop_redraw_timer()
    
    # Remove frame change handler
    if on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame_change)
    
    # Unregister operators
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
