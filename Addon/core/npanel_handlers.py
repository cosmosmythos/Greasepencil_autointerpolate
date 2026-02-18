"""
N-Panel Handlers
Manages curve loading and auto-saving for the N-Panel UI
"""

import bpy
from bpy.app.handlers import persistent

# Global state
_last_curve_hash = None
_loading_curve = False
_last_active_layer = None
_last_selected_frame = None
_last_playhead_frame = None


def get_curve_hash():
    """Get hash of current curve state (includes handle types)"""
    from ..utils.easing import get_easing_curve_node
    curve_node = get_easing_curve_node()
    if not curve_node or curve_node.type != 'CURVE_FLOAT':
        return None
    
    curve = curve_node.mapping.curves[0]
    points_data = [
        (round(pt.location.x, 4), round(pt.location.y, 4), pt.handle_type)
        for pt in curve.points
    ]
    return hash(tuple(points_data))


def set_loading_flag(loading):
    """Prevent auto-save during programmatic changes"""
    global _loading_curve, _last_curve_hash
    _loading_curve = loading
    if not loading:
        _last_curve_hash = get_curve_hash()


def load_curve_for_current_context(context):
    """Load curve for current keyframe/layer context"""
    global _loading_curve
    
    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return
    
    gp_obj = context.active_object
    gp_data = gp_obj.data
    
    if not gp_data.layers.active:
        return
    
    active_layer = gp_data.layers.active
    layer_idx = next((idx for idx, layer in enumerate(gp_data.layers) if layer == active_layer), None)
    
    if layer_idx is None:
        return
    
    current_frame = context.scene.frame_current
    frame_num = max((f.frame_number for f in active_layer.frames if f.frame_number <= current_frame), default=None)
    
    if frame_num is None:
        return
    
    from ..utils.easing import get_easing_curve_node
    curve_node = get_easing_curve_node()
    if not curve_node:
        return
    
    from ..operators.easing_direct import apply_preset_to_curve, get_stored_easing_data
    
    preset, data = get_stored_easing_data(gp_data, layer_idx, frame_num)
    
    # Default to LINEAR if no preset stored
    if not preset:
        preset = 'LINEAR'
    
    set_loading_flag(True)
    try:
        apply_preset_to_curve(preset, data)
    finally:
        set_loading_flag(False)


@persistent
def on_frame_change(scene, depsgraph=None):
    """Load curve when frame changes — primary mechanism for scrub updates"""
    global _last_playhead_frame
    
    try:
        context = bpy.context
        current_frame = scene.frame_current
        
        # Only reload if frame actually changed
        if current_frame == _last_playhead_frame:
            return
        _last_playhead_frame = current_frame
        
        load_curve_for_current_context(context)
    except Exception:
        pass


@persistent
def on_depsgraph_update(scene, depsgraph):
    """Single depsgraph handler: detect context changes first, then auto-save.
    
    Order matters:
    1. Check for layer/selection changes → load the correct curve
    2. Check for user curve edits → auto-save if CUSTOM
    
    This eliminates the race condition from having two separate handlers.
    """
    global _last_curve_hash, _loading_curve
    global _last_active_layer, _last_selected_frame
    
    if _loading_curve:
        return
    
    try:
        context = bpy.context
    except Exception:
        return
    
    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return
    
    gp_data = context.active_object.data
    active_layer = gp_data.layers.active
    
    if not active_layer:
        return
    
    # --- PHASE 1: Detect context changes (layer switch, key selection) ---
    context_changed = False
    
    # Layer switch
    if active_layer != _last_active_layer:
        _last_active_layer = active_layer
        context_changed = True
    
    # Keyframe selection change (dopesheet)
    if not context_changed and active_layer:
        selected_frames = [f.frame_number for f in active_layer.frames if f.select]
        if selected_frames:
            selected_frame = selected_frames[0]
            if selected_frame != _last_selected_frame:
                _last_selected_frame = selected_frame
                scene.frame_current = selected_frame
                context_changed = True
    
    if context_changed:
        load_curve_for_current_context(context)
        return  # Don't auto-save on the same update that loaded a curve
    
    # --- PHASE 2: Auto-save user curve edits ---
    current_hash = get_curve_hash()
    if current_hash is None:
        return
    
    if _last_curve_hash is None:
        _last_curve_hash = current_hash
        return
    
    if current_hash == _last_curve_hash:
        return
    
    _last_curve_hash = current_hash
    
    gp_obj = context.active_object
    
    layer_idx = next((idx for idx, layer in enumerate(gp_data.layers) if layer == active_layer), None)
    if layer_idx is None:
        return
    
    current_frame = context.scene.frame_current
    prev_key = max((f.frame_number for f in active_layer.frames if f.frame_number <= current_frame), default=None)
    if prev_key is None:
        return
    
    from ..operators.easing_direct import get_stored_easing_data
    stored_preset, _ = get_stored_easing_data(gp_data, layer_idx, prev_key)
    
    if stored_preset == 'CUSTOM' and context.scene.gp_interpolation_enabled:
        from ..utils import easing
        easing.set_easing_curve_to_frame(gp_data, active_layer, layer_idx, prev_key, 'CUSTOM')
        
        from . import cache
        cache.clear()
        cache.build(gp_obj)


def register():
    if on_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame_change)
    
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame_change)
    
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
