# stroke_guide.py - Modern Blender Extension Module
# OPTIMIZED: Reduced signature overhead and screen coordinate caching

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import bpy_extras.view3d_utils

# Module state
guide_state = {
    'show_prev': False,
    'show_next': False,
    'stroke_index': 0,
    'draw_handler': None,
    'auto_mode': True,
    'last_stroke_count': 0,
    'last_frame': None,
    'last_layer_signature': None,
    # OPTIMIZATION: Screen coordinate caching
    'coord_cache': {},
    'cached_view_matrix': None,
    'cache_region_size': None,
}


def get_stroke_guide_signature(gp_obj):
    """
    OPTIMIZED: Lightweight signature generation using layer ID and minimal data.
    Avoids iterating through all frames - only checks current frame stroke count.
    """
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return None
    
    layer = gp_obj.data.layers.active
    if not layer:
        return None
    
    current_frame = bpy.context.scene.frame_current
    
    # OPTIMIZATION: Use layer pointer ID instead of name (faster comparison)
    layer_id = id(layer)
    
    # OPTIMIZATION: Only get stroke count on current frame - no full frame iteration
    current_stroke_count = 0
    
    # Try to use cache lookup if available from main system
    if hasattr(layer, '_frame_lookup_cache') and current_frame in layer._frame_lookup_cache:
        frame = layer._frame_lookup_cache[current_frame]
        current_stroke_count = len(frame.drawing.strokes)
    else:
        # Fallback: Quick linear search for current frame only
        for frame in layer.frames:
            if frame.frame_number == current_frame:
                current_stroke_count = len(frame.drawing.strokes)
                break
    
    # Lightweight signature: layer pointer + frame + stroke count
    return (layer_id, current_frame, current_stroke_count)


def get_stroke_points(layer, frame_num, stroke_idx):
    """Direct stroke point access - fast and simple"""
    for frame in layer.frames:
        if frame.frame_number == frame_num:
            if stroke_idx < len(frame.drawing.strokes):
                stroke = frame.drawing.strokes[stroke_idx]
                return [p.position for p in stroke.points]
    return None


def update_stroke_guide_auto():
    """
    OPTIMIZED: Smart auto-update using signature hashing.
    Only updates when signature actually changes (no unnecessary processing).
    """
    if not guide_state['auto_mode']:
        return
    
    context = bpy.context
    gp_obj = context.active_object
    
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return
    
    # OPTIMIZATION: Signature-based change detection (no polling!)
    current_signature = get_stroke_guide_signature(gp_obj)
    if current_signature == guide_state['last_layer_signature']:
        return  # No changes - early exit for performance
    
    guide_state['last_layer_signature'] = current_signature
    
    if not current_signature:
        return
    
    layer_id, current_frame, current_stroke_count = current_signature
    
    # Handle frame changes
    if guide_state['last_frame'] != current_frame:
        # Frame changed - set stroke index to show NEXT stroke to draw
        guide_state['stroke_index'] = current_stroke_count
        guide_state['last_stroke_count'] = current_stroke_count
        guide_state['last_frame'] = current_frame
        
        # CRITICAL: Clear coordinate cache when frame changes
        guide_state['coord_cache'].clear()
        
        refresh_guide_display()
        return
    
    # Handle new stroke detection (same frame, more strokes)
    if current_stroke_count > guide_state['last_stroke_count']:
        guide_state['stroke_index'] = current_stroke_count  # Auto-advance to next stroke
        guide_state['last_stroke_count'] = current_stroke_count
        
        # Clear cache when stroke count changes
        guide_state['coord_cache'].clear()
        
        refresh_guide_display()
    elif current_stroke_count == 0:
        # New keyframe detected - reset to stroke 0
        guide_state['stroke_index'] = 0
        guide_state['last_stroke_count'] = 0
        
        # Clear cache
        guide_state['coord_cache'].clear()
        
        refresh_guide_display()


def convert_points_to_screen(points, gp_obj, region, rv3d):
    """
    OPTIMIZED: Convert 3D points to screen coordinates with validation.
    Returns list of 2D tuples or empty list if conversion fails.
    """
    coords_2d = []
    for pt in points:
        try:
            world_pt = gp_obj.matrix_world @ pt
            screen_pt = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world_pt)
            if screen_pt and len(screen_pt) >= 2:
                coords_2d.append((screen_pt[0], screen_pt[1]))
        except (ValueError, TypeError, AttributeError):
            continue
    
    return coords_2d


def draw_stroke_guide_overlay(gp_obj, layer, current_frame, direction, color):
    """
    OPTIMIZED: Draw stroke guide with screen coordinate caching.
    Caches converted coordinates until view changes.
    """
    frames = sorted([f.frame_number for f in layer.frames])
    target_frame = None
    
    # Find target keyframe
    if direction == 'prev':
        for f in reversed(frames):
            if f < current_frame:
                target_frame = f
                break
    else:  # next
        for f in frames:
            if f > current_frame:
                target_frame = f
                break
    
    if not target_frame:
        return
    
    # Get stroke points for current index
    points = get_stroke_points(layer, target_frame, guide_state['stroke_index'])
    if not points or len(points) < 2:
        return
    
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    
    if not region or not rv3d:
        return
    
    # OPTIMIZATION: Check if we can use cached coordinates
    # Create view matrix tuple for comparison (hashable)
    current_view_matrix = tuple(tuple(row) for row in rv3d.view_matrix)
    current_region_size = (region.width, region.height)
    
    # Cache key includes: target frame, direction, stroke index, view matrix, region size
    cache_key = (
        target_frame,
        direction,
        guide_state['stroke_index'],
        current_view_matrix,
        current_region_size
    )
    
    # Check if we can use cached coordinates
    if cache_key in guide_state['coord_cache']:
        coords_2d = guide_state['coord_cache'][cache_key]
    else:
        # Convert and cache
        coords_2d = convert_points_to_screen(points, gp_obj, region, rv3d)
        
        # Store in cache
        guide_state['coord_cache'][cache_key] = coords_2d
        
        # OPTIMIZATION: Limit cache size to prevent memory bloat
        if len(guide_state['coord_cache']) > 20:
            # Keep only most recent entries
            oldest_keys = list(guide_state['coord_cache'].keys())[:-10]
            for old_key in oldest_keys:
                del guide_state['coord_cache'][old_key]
    
    if len(coords_2d) < 2:
        return
    
    # Draw the overlay
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords_2d})
        
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(4.0)
        
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        
    except Exception as e:
        print(f"[Stroke Guide] Draw error: {e}")


def draw_guide_main():
    """Main draw function - integrates with existing draw handler pattern"""
    try:
        context = bpy.context
        gp_obj = context.active_object
        
        if not gp_obj or gp_obj.type != 'GREASEPENCIL':
            return
        
        layer = gp_obj.data.layers.active
        if not layer:
            return
        
        # Update stroke guide automatically (signature-based, no polling)
        update_stroke_guide_auto()
        
        current_frame = context.scene.frame_current
        
        # Draw previous keyframe guide (red)
        if guide_state['show_prev']:
            draw_stroke_guide_overlay(gp_obj, layer, current_frame, 'prev', (1.0, 0.3, 0.3, 0.7))
        
        # Draw next keyframe guide (blue) 
        if guide_state['show_next']:
            draw_stroke_guide_overlay(gp_obj, layer, current_frame, 'next', (0.3, 0.3, 1.0, 0.7))
        
    except Exception as e:
        print(f"[Stroke Guide] Main draw error: {e}")
    finally:
        # Always reset GPU state
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')


def refresh_guide_display():
    """Force refresh of guide display"""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def manage_draw_handler():
    """Smart handler management"""
    should_have_handler = guide_state['show_prev'] or guide_state['show_next']
    
    if should_have_handler and not guide_state['draw_handler']:
        # Register handler
        guide_state['draw_handler'] = bpy.types.SpaceView3D.draw_handler_add(
            draw_guide_main, (), 'WINDOW', 'POST_PIXEL')
        print("[Stroke Guide] Draw handler registered")
        
    elif not should_have_handler and guide_state['draw_handler']:
        # Unregister handler
        bpy.types.SpaceView3D.draw_handler_remove(guide_state['draw_handler'], 'WINDOW')
        guide_state['draw_handler'] = None
        
        # Clear caches when disabling
        guide_state['coord_cache'].clear()
        
        print("[Stroke Guide] Draw handler removed")


# Hook into existing frame change system
def on_stroke_guide_update(scene, depsgraph=None):
    """Hook into main frame_change_post handler - no separate handler needed!"""
    if guide_state['show_prev'] or guide_state['show_next']:
        # Only run when guides are active
        update_stroke_guide_auto()
        refresh_guide_display()


# Operators
class GP_TogglePrevGuide(bpy.types.Operator):
    bl_idname = "gp.toggle_prev_guide"
    bl_label = "Prev"
    bl_description = "Show/hide previous keyframe stroke guide"
    
    def execute(self, context):
        guide_state['show_prev'] = not guide_state['show_prev']
        if guide_state['show_prev']:
            # CRITICAL: Initialize to show CORRECT stroke when enabling
            gp_obj = context.active_object
            if gp_obj and gp_obj.type == 'GREASEPENCIL':
                layer = gp_obj.data.layers.active
                if layer:
                    current_frame = context.scene.frame_current
                    current_stroke_count = 0
                    
                    # Get current frame stroke count
                    for frame in layer.frames:
                        if frame.frame_number == current_frame:
                            current_stroke_count = len(frame.drawing.strokes)
                            break
                    
                    # Set to show NEXT stroke to draw
                    guide_state['stroke_index'] = current_stroke_count
                    guide_state['last_stroke_count'] = current_stroke_count
            
            guide_state['last_layer_signature'] = None  # Force update
            guide_state['coord_cache'].clear()  # Clear cache
        
        manage_draw_handler()
        refresh_guide_display()
        return {'FINISHED'}


class GP_ToggleNextGuide(bpy.types.Operator):
    bl_idname = "gp.toggle_next_guide"
    bl_label = "Next"
    bl_description = "Show/hide next keyframe stroke guide"
    
    def execute(self, context):
        guide_state['show_next'] = not guide_state['show_next']
        if guide_state['show_next']:
            # CRITICAL: Initialize to show CORRECT stroke when enabling
            gp_obj = context.active_object
            if gp_obj and gp_obj.type == 'GREASEPENCIL':
                layer = gp_obj.data.layers.active
                if layer:
                    current_frame = context.scene.frame_current
                    current_stroke_count = 0
                    
                    # Get current frame stroke count
                    for frame in layer.frames:
                        if frame.frame_number == current_frame:
                            current_stroke_count = len(frame.drawing.strokes)
                            break
                    
                    # Set to show NEXT stroke to draw
                    guide_state['stroke_index'] = current_stroke_count
                    guide_state['last_stroke_count'] = current_stroke_count
            
            guide_state['last_layer_signature'] = None  # Force update
            guide_state['coord_cache'].clear()  # Clear cache
        
        manage_draw_handler()
        refresh_guide_display()
        return {'FINISHED'}


class GP_ToggleAutoMode(bpy.types.Operator):
    bl_idname = "gp.toggle_auto_mode"
    bl_label = "Auto"
    bl_description = "Toggle automatic stroke index advancement"
    
    def execute(self, context):
        guide_state['auto_mode'] = not guide_state['auto_mode']
        if guide_state['auto_mode']:
            # Reset tracking when re-enabling auto mode
            guide_state['last_stroke_count'] = 0
            guide_state['stroke_index'] = 0
            guide_state['last_layer_signature'] = None
            guide_state['coord_cache'].clear()
        
        refresh_guide_display()
        return {'FINISHED'}


class GP_NextStroke(bpy.types.Operator):
    bl_idname = "gp.next_stroke"
    bl_label = "Next Stroke"
    
    def execute(self, context):
        guide_state['auto_mode'] = False  # Switch to manual
        guide_state['stroke_index'] += 1
        guide_state['coord_cache'].clear()  # Clear cache when manually changing
        refresh_guide_display()
        return {'FINISHED'}


class GP_PrevStroke(bpy.types.Operator):
    bl_idname = "gp.prev_stroke"
    bl_label = "Prev Stroke"
    
    def execute(self, context):
        guide_state['auto_mode'] = False  # Switch to manual
        if guide_state['stroke_index'] > 0:
            guide_state['stroke_index'] -= 1
        guide_state['coord_cache'].clear()  # Clear cache when manually changing
        refresh_guide_display()
        return {'FINISHED'}


# Header UI function
def draw_header(self, context):
    """Draw stroke guide controls in 3D View header"""
    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return
    
    layout = self.layout
    layout.separator_spacer()
    
    # Compact button layout
    row = layout.row(align=True)
    row.operator("gp.toggle_prev_guide", depress=guide_state['show_prev'], text="", icon="PLAY_REVERSE")
    row.operator("gp.toggle_next_guide", depress=guide_state['show_next'], text="", icon="PLAY")
    
    if guide_state['show_prev'] or guide_state['show_next']:
        # Mode toggle
        row.operator("gp.toggle_auto_mode", 
                    text="Auto" if guide_state['auto_mode'] else "Manual", 
                    depress=guide_state['auto_mode'])
        
        # Manual controls (only when needed)
        if not guide_state['auto_mode']:
            row.operator("gp.prev_stroke", text="", icon="ZOOM_OUT")
            row.operator("gp.next_stroke", text="", icon="ZOOM_IN")
        
        # Stroke index display
        row.label(text=f"S[{guide_state['stroke_index']}]")


# Registration classes
classes = (
    GP_TogglePrevGuide,
    GP_ToggleNextGuide,
    GP_ToggleAutoMode,
    GP_NextStroke,
    GP_PrevStroke,
)


def register():
    """Register stroke guide system - standard Blender pattern"""
    # Register operators
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add to header
    bpy.types.VIEW3D_HT_tool_header.prepend(draw_header)
    
    # Hook into existing frame change handler (no separate handler!)
    if on_stroke_guide_update not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_stroke_guide_update)


def unregister():
    """Clean unregister - standard Blender pattern"""
    # Clean up draw handler
    if guide_state['draw_handler']:
        bpy.types.SpaceView3D.draw_handler_remove(guide_state['draw_handler'], 'WINDOW')
        guide_state['draw_handler'] = None
    
    # Clear all caches
    guide_state['coord_cache'].clear()
    
    # Remove from frame change handler
    if on_stroke_guide_update in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_stroke_guide_update)
    
    # Remove from header
    bpy.types.VIEW3D_HT_tool_header.remove(draw_header)
    
    # Unregister operators
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


# Standalone test mode
if __name__ == "__main__":
    register()