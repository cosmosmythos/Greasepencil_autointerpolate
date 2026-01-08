"""
GP Stroke Correspondence - Production UI
Integrated header buttons like stroke_guide.py

Refactored structure:
- Core utilities: Addon/utils/correspondence_utils.py
- Operators: Addon/operators/correspondence.py  
- This file: UI drawing, visualization, registration, and global state management
"""

import bpy
from bpy.props import BoolProperty
import random
import gpu
from gpu_extras.batch import batch_for_shader

# Import utilities
from .utils.correspondence_utils import get_match_id_from_stroke


# ============================================================================
# Global State (Shared across modules via this file)
# ============================================================================

_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_mode_active = False
_link_constraints = []  # [(layer_idx, frame1, stroke1_idx, frame2, stroke2_idx), ...]
_show_matches_viz = False
_draw_handle_view = None
_draw_handle_pixel = None
_match_colors = {}  # {match_id: (r, g, b, a)}


# ============================================================================
# Visualization: Color Generation
# ============================================================================

def generate_color_for_match_id(match_id, is_linked=False):
    """Generate consistent color for a match_id"""
    if is_linked:
        # Fixed bright color for linked matches (gold/orange)
        return (1.0, 0.6, 0.0, 1.0)
    
    # Use match_id as seed for consistent color
    random.seed(match_id)
    r = random.random() * 0.5 + 0.5  # 0.5-1.0
    g = random.random() * 0.5 + 0.5
    b = random.random() * 0.5 + 0.5
    return (r, g, b, 1.0)


# ============================================================================
# Visualization: Draw Callbacks
# ============================================================================

def draw_matches_view_callback():
    """Draw colored strokes in 3D viewport to show matches"""
    if not _show_matches_viz and not _link_mode_active:
        return
    
    context = bpy.context
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(4.0)
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Collect all match_ids from visible frames
    visible_match_ids = set()
    
    for layer_idx, layer in enumerate(obj.data.layers):
        for frame in layer.frames:
            # Only show matches for frames near playhead or selected frames
            if not frame.select and abs(frame.frame_number - context.scene.frame_current) > 5:
                continue
            
            if frame.drawing is None:
                continue
            
            for stroke_idx, stroke in enumerate(frame.drawing.strokes):
                match_id = get_match_id_from_stroke(obj, layer_idx, frame.frame_number, stroke_idx)
                if match_id >= 0:
                    visible_match_ids.add((layer_idx, frame.frame_number, stroke_idx, match_id))
    
    # Check if any match_ids correspond to linked constraints
    linked_match_ids = set()
    for constraint in _link_constraints:
        c_layer, c_frame1, c_stroke1, c_frame2, c_stroke2 = constraint
        # Get match_ids for linked strokes
        mid1 = get_match_id_from_stroke(obj, c_layer, c_frame1, c_stroke1)
        mid2 = get_match_id_from_stroke(obj, c_layer, c_frame2, c_stroke2)
        if mid1 >= 0:
            linked_match_ids.add(mid1)
        if mid2 >= 0:
            linked_match_ids.add(mid2)
    
    # Draw strokes with match colors
    for layer_idx, frame_num, stroke_idx, match_id in visible_match_ids:
        try:
            layer = obj.data.layers[layer_idx]
            
            # Find frame
            frame = None
            for f in layer.frames:
                if f.frame_number == frame_num:
                    frame = f
                    break
            
            if frame is None or frame.drawing is None:
                continue
            
            if stroke_idx >= len(frame.drawing.strokes):
                continue
            
            stroke = frame.drawing.strokes[stroke_idx]
            
            # Determine if this is a linked match
            is_linked = match_id in linked_match_ids
            
            # Get color
            if match_id not in _match_colors:
                _match_colors[match_id] = generate_color_for_match_id(match_id, is_linked)
            
            color = _match_colors[match_id]
            
            # Get stroke points in world space
            mw = obj.matrix_world
            points_3d = []
            for p in stroke.points:
                co_local = getattr(p, "position", None)
                if co_local is None:
                    co_local = getattr(p, "co", None)
                if co_local is None:
                    continue
                points_3d.append(mw @ co_local)
            
            if len(points_3d) < 2:
                continue
            
            # Create line segments
            vertices = []
            for i in range(len(points_3d) - 1):
                vertices.append(points_3d[i])
                vertices.append(points_3d[i + 1])
            
            batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
            shader.uniform_float("color", color)
            batch.draw(shader)
            
        except:
            pass
    
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def draw_selection_pixel_callback():
    """Draw link mode UI overlay in pixel space"""
    if not _link_mode_active:
        return
    
    import blf
    
    # Draw status text in top-left corner
    font_id = 0
    blf.size(font_id, 16)
    blf.color(font_id, 1.0, 0.8, 0.0, 1.0)
    blf.position(font_id, 15, bpy.context.region.height - 30, 0)
    blf.draw(font_id, "🔗 LINK MODE: Select one stroke in each of two frames, then click Link/Unlink")
    
    # Show number of linked constraints
    blf.size(font_id, 14)
    blf.color(font_id, 0.8, 0.8, 0.8, 1.0)
    blf.position(font_id, 15, bpy.context.region.height - 55, 0)
    blf.draw(font_id, f"Linked pairs: {len(_link_constraints)}")


# ============================================================================
# Draw Handler Management
# ============================================================================

def install_draw_handler():
    """Install viewport draw handlers"""
    global _draw_handle_view, _draw_handle_pixel
    
    from bpy.types import SpaceView3D
    
    if _draw_handle_view is None:
        _draw_handle_view = SpaceView3D.draw_handler_add(
            draw_matches_view_callback, (), 'WINDOW', 'POST_VIEW'
        )
    
    if _draw_handle_pixel is None:
        _draw_handle_pixel = SpaceView3D.draw_handler_add(
            draw_selection_pixel_callback, (), 'WINDOW', 'POST_PIXEL'
        )


def remove_draw_handler():
    """Remove viewport draw handlers"""
    global _draw_handle_view, _draw_handle_pixel, _match_colors
    
    from bpy.types import SpaceView3D
    
    if _draw_handle_view is not None:
        SpaceView3D.draw_handler_remove(_draw_handle_view, 'WINDOW')
        _draw_handle_view = None
    
    if _draw_handle_pixel is not None:
        SpaceView3D.draw_handler_remove(_draw_handle_pixel, 'WINDOW')
        _draw_handle_pixel = None
    
    _match_colors.clear()


# ============================================================================
# Header UI Integration
# ============================================================================

def draw_gpcorr_header(self, context):
    """Draw correspondence buttons in 3D View header"""
    layout = self.layout
    
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    row = layout.row(align=True)
    
    # Match button
    row.operator("gpcorr.match", text="Auto-Match", icon='UV_SYNC_SELECT')
    
    # Link mode toggle
    row.operator("gpcorr.link_mode", 
                 text="Link Mode" if not _link_mode_active else "Exit Link", 
                 icon='LINKED' if not _link_mode_active else 'UNLINKED',
                 depress=_link_mode_active)
    
    # Link/Unlink buttons (only visible in link mode)
    if _link_mode_active:
        row.operator("gpcorr.link_selected", text="Link", icon='ADD')
        row.operator("gpcorr.unlink_selected", text="Unlink", icon='REMOVE')
    
    # Visualization toggle (eye icon)
    row.prop(context.scene, "gpcorr_show_matches", text="", icon='HIDE_OFF' if context.scene.gpcorr_show_matches else 'HIDE_ON')
    
    # Show progress if job running
    if _match_job_running:
        status = _match_progress.get('status', '')
        current = _match_progress.get('current', 0)
        total = _match_progress.get('total', 0)
        if total > 0:
            row.label(text=f"[{current}/{total}] {status}")


# ============================================================================
# Visualization Toggle Callback
# ============================================================================

def toggle_viz_update(context):
    """Update callback for visualization toggle"""
    global _show_matches_viz
    _show_matches_viz = context.scene.gpcorr_show_matches

    # Ensure draw handlers exist while link mode is active OR visualization is enabled
    if _link_mode_active or _show_matches_viz:
        install_draw_handler()
    else:
        remove_draw_handler()

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


# ============================================================================
# Registration
# ============================================================================

def register():
    # Register operators from correspondence module
    from .operators import correspondence
    correspondence.register()
    
    # Add to tool header (left side, like stroke_guide)
    bpy.types.VIEW3D_HT_tool_header.prepend(draw_gpcorr_header)
    
    # Scene property for visualization toggle
    bpy.types.Scene.gpcorr_show_matches = BoolProperty(
        name="Show Matches",
        description="Show correspondence match visualization",
        default=False,
        update=lambda self, context: toggle_viz_update(context)
    )


def unregister():
    # Clean up draw handler
    remove_draw_handler()
    
    # Remove from tool header
    bpy.types.VIEW3D_HT_tool_header.remove(draw_gpcorr_header)
    
    # Remove scene property
    if hasattr(bpy.types.Scene, "gpcorr_show_matches"):
        del bpy.types.Scene.gpcorr_show_matches
    
    # Unregister operators
    from .operators import correspondence
    correspondence.unregister()
