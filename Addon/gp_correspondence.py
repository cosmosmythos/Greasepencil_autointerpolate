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
# Global State (Shared across modules via this file)
_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_mode_active = False
_link_constraints = []  # [(layer_idx, frame1, stroke1_idx, frame2, stroke2_idx), ...]
_show_matches_viz = False
_viewport_context = {}  # Store viewport info (region, rv3d) for timer callbacks
_draw_handle_view = None
_draw_handle_pixel = None
_chain_colors = {}  # {chain_id: (r, g, b, a)}

def generate_color_for_chain(chain_id):
    """Generate consistent color for a chain ID."""
    # Use chain_id as seed for consistent color
    random.seed(chain_id)
    r = random.random() * 0.5 + 0.5  # 0.5-1.0
    g = random.random() * 0.5 + 0.5
    b = random.random() * 0.5 + 0.5
    return (r, g, b, 1.0)


def clear_color_cache():
    """Clear the color cache to force regeneration."""
    global _chain_colors
    _chain_colors.clear()


def build_connection_chains(obj, layer_idx):
    """
    Build connection chains by following match_id links across frames.
    
    Returns: dict mapping (frame_num, stroke_idx) -> chain_id
    
    All strokes in the same chain get the same chain_id, so they get the same color.
    """
    layer = obj.data.layers[layer_idx]
    
    # Get sorted frame numbers
    frames = sorted([f.frame_number for f in layer.frames if f.drawing])
    if not frames:
        return {}
    
    # Build forward links: (frame, stroke_idx) -> (next_frame, target_stroke_idx)
    forward_links = {}
    frame_stroke_counts = {}
    
    for i, frame_num in enumerate(frames):
        frame_obj = None
        for f in layer.frames:
            if f.frame_number == frame_num:
                frame_obj = f
                break
        
        if not frame_obj or not frame_obj.drawing:
            continue
        
        num_strokes = len(frame_obj.drawing.strokes)
        frame_stroke_counts[frame_num] = num_strokes
        
        # If not the last frame, read match_ids to build links
        if i < len(frames) - 1:
            next_frame = frames[i + 1]
            for stroke_idx in range(num_strokes):
                match_id = get_match_id_from_stroke(obj, layer_idx, frame_num, stroke_idx)
                if match_id >= 0:
                    forward_links[(frame_num, stroke_idx)] = (next_frame, match_id)
    
    # Now build chains using Union-Find approach
    # Each unique chain gets a chain_id
    stroke_to_chain = {}  # (frame, stroke_idx) -> chain_id
    chain_counter = 0
    
    # Process each frame's strokes
    for frame_num in frames:
        num_strokes = frame_stroke_counts.get(frame_num, 0)
        for stroke_idx in range(num_strokes):
            key = (frame_num, stroke_idx)
            
            if key in stroke_to_chain:
                continue  # Already assigned
            
            # Start a new chain from this stroke
            chain_id = chain_counter
            chain_counter += 1
            
            # Follow the chain forward
            current = key
            while current:
                if current in stroke_to_chain:
                    # Merge: this stroke already belongs to another chain
                    # Use the existing chain_id for consistency
                    break
                
                stroke_to_chain[current] = chain_id
                
                # Follow forward link
                if current in forward_links:
                    current = forward_links[current]
                else:
                    current = None
    
    return stroke_to_chain
# Visualization: Draw Callbacks
def draw_matches_view_callback():
    """Draw colored strokes in 3D viewport to show matches, plus orange highlights for selected strokes"""
    if not _show_matches_viz and not _link_mode_active:
        return
    
    context = bpy.context
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(4.0)
    gpu.state.depth_test_set('ALWAYS')  # Draw on top
    
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Build connection chains for visible layers
    all_chains = {}  # {layer_idx: {(frame, stroke_idx): chain_id}}
    visible_layers = set()
    
    for layer_idx, layer in enumerate(obj.data.layers):
        for frame in layer.frames:
            # Only show matches for frames near playhead or selected frames
            if not frame.select and abs(frame.frame_number - context.scene.frame_current) > 5:
                continue
            if frame.drawing is not None:
                visible_layers.add(layer_idx)
                break
    
    for layer_idx in visible_layers:
        all_chains[layer_idx] = build_connection_chains(obj, layer_idx)
    
    # Collect visible strokes
    visible_strokes = []  # [(layer_idx, frame_num, stroke_idx)]
    
    for layer_idx, layer in enumerate(obj.data.layers):
        for frame in layer.frames:
            # Only show matches for frames near playhead or selected frames
            if not frame.select and abs(frame.frame_number - context.scene.frame_current) > 5:
                continue
            
            if frame.drawing is None:
                continue
            
            for stroke_idx in range(len(frame.drawing.strokes)):
                visible_strokes.append((layer_idx, frame.frame_number, stroke_idx))
    
    # Draw strokes with chain-based colors
    for layer_idx, frame_num, stroke_idx in visible_strokes:
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
            
            # Get chain_id for this stroke
            chain_map = all_chains.get(layer_idx, {})
            chain_id = chain_map.get((frame_num, stroke_idx), stroke_idx)  # fallback to stroke_idx
            
            # Get color (cached for consistency)
            if chain_id not in _chain_colors:
                _chain_colors[chain_id] = generate_color_for_chain(chain_id)
            
            color = _chain_colors[chain_id]
            
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
    
    # Draw orange filled squares at center of selected strokes (in link mode) - ON TOP
    if _link_mode_active:
        for layer in obj.data.layers:
            for frame in layer.frames:
                if frame.drawing is None:
                    continue
                
                for stroke in frame.drawing.strokes:
                    if not stroke.select:
                        continue
                    
                    if len(stroke.points) == 0:
                        continue
                    
                    try:
                        # Get midpoint of stroke (middle point index, ON the actual stroke)
                        mw = obj.matrix_world
                        mid_idx = len(stroke.points) // 2
                        mid_point = stroke.points[mid_idx]
                        
                        co_local = getattr(mid_point, "position", None)
                        if co_local is None:
                            co_local = getattr(mid_point, "co", None)
                        if co_local is None:
                            continue
                        
                        center_3d = mw @ co_local
                        
                        # Draw filled square facing camera (billboard)
                        size = 0.03  # Size in world units (doubled)
                        
                        # Get view matrix to make square face camera
                        view_matrix = context.region_data.view_matrix
                        # Extract camera right and up vectors
                        cam_right = view_matrix.inverted()[0].to_3d().normalized()
                        cam_up = view_matrix.inverted()[1].to_3d().normalized()
                        
                        # Create square vertices facing camera
                        vertices = [
                            center_3d - cam_right * size - cam_up * size,
                            center_3d + cam_right * size - cam_up * size,
                            center_3d + cam_right * size + cam_up * size,
                            center_3d - cam_right * size + cam_up * size,
                        ]
                        
                        # Two triangles to make filled square
                        indices = [0, 1, 2, 0, 2, 3]
                        tri_vertices = [vertices[i] for i in indices]
                        
                        batch = batch_for_shader(shader, 'TRIS', {"pos": tri_vertices})
                        shader.uniform_float("color", (1.0, 0.4, 0.0, 1.0))  # Vibrant orange, fully opaque
                        batch.draw(shader)
                    except:
                        pass
    
    gpu.state.line_width_set(1.0)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('NONE')


def draw_selection_pixel_callback():
    """Draw link mode UI text overlay"""
    if not _link_mode_active:
        return
    
    context = bpy.context
    
    # Draw text overlay
    import blf
    font_id = 0
    blf.size(font_id, 16)
    blf.color(font_id, 1.0, 0.8, 0.0, 1.0)
    blf.position(font_id, 15, context.region.height - 30, 0)
    blf.draw(font_id, "🔗 LINK MODE: Select one stroke in each of two frames, then click Link/Unlink")
    
    blf.size(font_id, 14)
    blf.color(font_id, 0.8, 0.8, 0.8, 1.0)
    blf.position(font_id, 15, context.region.height - 55, 0)
    blf.draw(font_id, f"Linked pairs: {len(_link_constraints)}")
# Draw Handler Management
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
    global _draw_handle_view, _draw_handle_pixel, _chain_colors
    
    from bpy.types import SpaceView3D
    
    if _draw_handle_view is not None:
        SpaceView3D.draw_handler_remove(_draw_handle_view, 'WINDOW')
        _draw_handle_view = None
    
    if _draw_handle_pixel is not None:
        SpaceView3D.draw_handler_remove(_draw_handle_pixel, 'WINDOW')
        _draw_handle_pixel = None
    
    _chain_colors.clear()
# Header UI Integration
def draw_gpcorr_header(self, context):
    """Draw correspondence buttons in 3D View header"""
    layout = self.layout
    
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    row = layout.row(align=True)
    
    # Match button
    row.operator("gpcorr.match", text="Auto-Match", icon='COLLECTION_COLOR_06')
    
    # Link mode toggle
    row.operator("gpcorr.link_mode", 
                 text="Link" if not _link_mode_active else "Done", 
                 icon='RESTRICT_INSTANCED_OFF' if not _link_mode_active else 'SOLO_ON',
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
# Visualization Toggle Callback
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
def register():
    """Register correspondence UI and visualization."""
    # Use VIEW3D_HT_header (main header) with prepend for leftmost static position
    bpy.types.VIEW3D_HT_header.prepend(draw_gpcorr_header)
    
    bpy.types.Scene.gpcorr_show_matches = BoolProperty(
        name="Show Matches",
        description="Show correspondence match visualization",
        default=False,
        update=lambda self, context: toggle_viz_update(context)
    )


def unregister():
    """Unregister correspondence UI and visualization."""
    remove_draw_handler()
    
    bpy.types.VIEW3D_HT_header.remove(draw_gpcorr_header)
    
    if hasattr(bpy.types.Scene, "gpcorr_show_matches"):
        del bpy.types.Scene.gpcorr_show_matches
