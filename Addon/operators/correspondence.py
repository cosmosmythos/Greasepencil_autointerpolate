"""
Correspondence Operators
Handles matching, linking, and unlinking operations for GP stroke correspondence.
"""

import bpy
from bpy.types import Operator
from bpy.props import IntProperty, FloatProperty, BoolProperty, EnumProperty

from ..utils.correspondence_utils import (
    detect_keyframe_range,
    find_keyframe_pairs,
    collect_strokes_2d,
    to_cpp_strokes
)

_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_constraints = []
_stable_stroke_ids = {}  # {(layer_idx, frame_num): {current_idx: stable_id, ...}}


def get_state():
    """Get reference to global state from parent module"""
    from .. import gp_correspondence
    return {
        'match_job_running': gp_correspondence._match_job_running,
        'match_progress': gp_correspondence._match_progress,
        'link_constraints': gp_correspondence._link_constraints,
        'link_mode_active': gp_correspondence._link_mode_active,
        'viewport_context': gp_correspondence._viewport_context,
        'stable_stroke_ids': gp_correspondence._stable_stroke_ids,
    }


def set_state(**kwargs):
    """Update global state in parent module"""
    from .. import gp_correspondence
    for key, value in kwargs.items():
        if key == 'match_job_running':
            gp_correspondence._match_job_running = value
        elif key == 'match_progress':
            gp_correspondence._match_progress = value
        elif key == 'link_constraints':
            gp_correspondence._link_constraints = value
        elif key == 'link_mode_active':
            gp_correspondence._link_mode_active = value
        elif key == 'viewport_context':
            gp_correspondence._viewport_context = value
        elif key == 'show_linked_overlay':
            gp_correspondence._show_linked_overlay = value
        elif key == 'stable_stroke_ids':
            gp_correspondence._stable_stroke_ids = value
def ensure_stable_ids(gp_obj, layer_idx, frame_num):
    """
    Ensure all strokes on a frame have stable IDs that persist across reorders.
    Returns {current_idx: stable_id, ...}
    """
    state = get_state()
    stable_stroke_ids = state['stable_stroke_ids']
    key = (layer_idx, frame_num)
    
    # Get current drawing
    layer = gp_obj.data.layers[layer_idx]
    frame_obj = None
    for f in layer.frames:
        if f.frame_number == frame_num:
            frame_obj = f
            break
    
    if not frame_obj or not frame_obj.drawing:
        return {}
    
    num_strokes = len(frame_obj.drawing.strokes)
    
    # Initialize if not present or stroke count changed (new strokes added/deleted)
    if key not in stable_stroke_ids or len(stable_stroke_ids[key]) != num_strokes:
        stable_stroke_ids[key] = {i: i for i in range(num_strokes)}
        set_state(stable_stroke_ids=stable_stroke_ids)
    
    return stable_stroke_ids[key]


def run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config):
    """
    Run correspondence matching between two frames.
    Instead of storing match_id, we reorder strokes on the later frame so indices align.
    Returns (success, matches, message).
    """
    try:
        import gp_autointerpolate
    except ImportError as e:
        return (False, [], f"gp_autointerpolate module not found: {e}")
    
    try:
        state = get_state()
        link_constraints = state['link_constraints']
        
        # Ensure stable IDs exist for both frames
        stable_ids1 = ensure_stable_ids(gp_obj, layer_idx, frame1)
        stable_ids2 = ensure_stable_ids(gp_obj, layer_idx, frame2)
        
        s1, indices1 = collect_strokes_2d(gp_obj, layer_idx, frame1)
        s2, indices2 = collect_strokes_2d(gp_obj, layer_idx, frame2)
        
        if len(s1) == 0 or len(s2) == 0:
            return (False, [], f"No valid strokes in frames {frame1} or {frame2}")
        
        cfg = gp_autointerpolate.MatcherConfig()
        cfg.enable_stage_two = True
        cfg.max_alpha = config['max_alpha']
        cfg.coincident_threshold = config['coincident_threshold']
        cfg.debug = False  # Disable verbose C++ debug output
        
        # Build seeds from linked constraints for this frame pair
        seeds = []
        
        lookup_frame1, lookup_frame2 = (frame1, frame2) if frame1 < frame2 else (frame2, frame1)
        swap_order = (frame1 > frame2)
        
        # Build reverse mappings: stable_id -> current_idx
        stable_to_current1 = {stable_id: curr_idx for curr_idx, stable_id in stable_ids1.items()}
        stable_to_current2 = {stable_id: curr_idx for curr_idx, stable_id in stable_ids2.items()}
        
        for constraint in link_constraints:
            c_layer, c_frame1, c_stroke1_stable, c_frame2, c_stroke2_stable = constraint
            if c_layer == layer_idx and c_frame1 == lookup_frame1 and c_frame2 == lookup_frame2:
                if swap_order:
                    stable_id1 = c_stroke2_stable
                    stable_id2 = c_stroke1_stable
                else:
                    stable_id1 = c_stroke1_stable
                    stable_id2 = c_stroke2_stable
                
                # Map stable IDs to current indices, then to collected indices
                if stable_id1 in stable_to_current1 and stable_id2 in stable_to_current2:
                    current_idx1 = stable_to_current1[stable_id1]
                    current_idx2 = stable_to_current2[stable_id2]
                    
                    try:
                        idx1 = indices1.index(current_idx1)
                        idx2 = indices2.index(current_idx2)
                        seeds.append((idx1, idx2))
                    except ValueError:
                        pass  # Seed mapping failed, skip this constraint
        
        # Convert ALL strokes to C++ format (don't filter - let C++ handle seeds)
        S1 = to_cpp_strokes(s1)
        S2 = to_cpp_strokes(s2)
        
        matcher = gp_autointerpolate.StrokeMatcher(cfg)
        
        # Use match_with_seeds if we have user-linked pairs, otherwise standard match
        if seeds:
            result = matcher.match_with_seeds(S1, S2, seeds)
        else:
            result = matcher.match(S1, S2)
        
        raw_matches = result.get_matches()
        
        # Map collected indices back to original stroke indices
        result_matches = [(indices1[i], indices2[j]) for i, j in raw_matches]
        
        # Log final match result
        if seeds:
            print(f"[GPCORR] Matched {len(result_matches)} pairs (manual seeds: {len(seeds)}, auto: {len(result_matches) - len(seeds)})")
        else:
            print(f"[GPCORR] Matched {len(result_matches)} pairs")
        
        # Determine which frame is earlier (reference) and which is later (to be reordered)
        if frame1 < frame2:
            ref_frame, reorder_frame = frame1, frame2
            swap_match = False
        else:
            ref_frame, reorder_frame = frame2, frame1
            swap_match = True
        
        # Get the drawing for the frame to reorder
        layer = gp_obj.data.layers[layer_idx]
        reorder_frame_obj = None
        for f in layer.frames:
            if f.frame_number == reorder_frame:
                reorder_frame_obj = f
                break
        
        if not reorder_frame_obj or not reorder_frame_obj.drawing:
            return (False, [], f"Could not find drawing for frame {reorder_frame}")
        
        drawing = reorder_frame_obj.drawing
        num_strokes = len(drawing.strokes)
        
        # Build reorder map: new_indices[new_position] = old_position
        new_indices = list(range(num_strokes))
        assigned_positions = set()
        used_old_strokes = set()
        
        # First pass: assign matched strokes
        for ref_idx, reorder_idx in result_matches:
            if swap_match:
                ref_idx, reorder_idx = reorder_idx, ref_idx
            
            if ref_idx < num_strokes and reorder_idx < num_strokes:
                new_indices[ref_idx] = reorder_idx
                assigned_positions.add(ref_idx)
                used_old_strokes.add(reorder_idx)
        
        # Second pass: fill unassigned positions with remaining strokes
        remaining_old = [i for i in range(num_strokes) if i not in used_old_strokes]
        remaining_positions = [i for i in range(num_strokes) if i not in assigned_positions]
        
        for pos, old_stroke in zip(remaining_positions, remaining_old):
            new_indices[pos] = old_stroke
        
        # Apply reorder
        drawing.reorder_strokes(new_indices=new_indices)
        
        # Update stable ID mapping to reflect the reorder
        state = get_state()
        stable_stroke_ids = state['stable_stroke_ids']
        key = (layer_idx, reorder_frame)
        
        if key in stable_stroke_ids:
            old_stable_ids = stable_stroke_ids[key]
            new_stable_ids = {}
            
            for new_pos, old_pos in enumerate(new_indices):
                if old_pos in old_stable_ids:
                    new_stable_ids[new_pos] = old_stable_ids[old_pos]
            
            stable_stroke_ids[key] = new_stable_ids
            set_state(stable_stroke_ids=stable_stroke_ids)
        
        msg = f"Matched {len(result_matches)} pairs (seeds: {len(seeds)})"
        return (True, result_matches, msg)
        
    except Exception as e:
        return (False, [], f"Match failed: {e}")


def run_match_job_step():
    """Single step of multi-pair matching job."""
    state = get_state()
    
    if not state['match_job_running']:
        return None  # Stop timer
    
    match_progress = state['match_progress']
    job_data = match_progress.get('job_data')
    if not job_data:
        set_state(match_job_running=False)
        return None
    
    gp_obj = job_data['gp_obj']
    layer_idx = job_data['layer_idx']
    pairs = job_data['pairs']
    config = job_data['config']
    current = match_progress['current']
    
    if current >= len(pairs):
        set_state(match_job_running=False, viewport_context={})  # Clear saved viewport context
        match_progress['status'] = f"Complete! Matched {len(pairs)} frame pairs"

        scene = bpy.context.scene
        if scene.gp_interpolation_enabled:
            from ..core.registry import is_object_enabled
            if is_object_enabled(scene, gp_obj.name):
                from ..core import cache
                cache.build(gp_obj)

        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return None
    
    frame1, frame2 = pairs[current]
    match_progress['status'] = f"Matching frames {frame1} → {frame2}..."
    
    success, matches, msg = run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config)
    
    match_progress['current'] = current + 1
    return 0.1


def start_match_job(gp_obj, layer_idx, pairs, config):
    """Start non-blocking multi-pair matching job. Returns (success, camera_info)"""
    state = get_state()
    
    if state['match_job_running']:
        return (False, None)
    
    # Check for camera info
    import bpy
    scene = bpy.context.scene
    if scene.camera is None:
        camera_info = {'type': 'WARNING', 'message': "No active camera detected. Using default view projection - results may vary with viewport angle"}
    else:
        camera_info = {'type': 'INFO', 'message': f"Matching from camera '{scene.camera.name}' view"}
    
    match_progress = {
        'current': 0,
        'total': len(pairs),
        'status': 'Starting...',
        'job_data': {
            'gp_obj': gp_obj,
            'layer_idx': layer_idx,
            'pairs': pairs,
            'config': config
        }
    }
    
    set_state(match_job_running=True, match_progress=match_progress)
    
    # Register timer to run job steps
    bpy.app.timers.register(run_match_job_step)
    
    return (True, camera_info)
# Helper function to get layer items for EnumProperty
def get_layer_items(self, context):
    """Generate layer items for dropdown"""
    items = []
    obj = context.active_object
    if obj and obj.type == 'GREASEPENCIL':
        for idx, layer in enumerate(obj.data.layers):
            # EnumProperty items: (identifier, name, description, icon, number)
            items.append((str(idx), layer.name, f"Layer: {layer.name}", 'OUTLINER_DATA_GP_LAYER', idx))
    
    if not items:
        items.append(('0', "No Layers", "No GP layers available", 'ERROR', 0))
    
    return items


def update_active_layer(self, context):
    """Update callback - set the active layer when dropdown changes"""
    obj = context.active_object
    if obj and obj.type == 'GREASEPENCIL':
        layer_idx = int(self.layer_enum) if self.layer_enum.isdigit() else 0
        if layer_idx < len(obj.data.layers):
            obj.data.layers.active = obj.data.layers[layer_idx]
            # Force viewport redraw
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


# Operator: GP Match (Main Matching Operator)
class GPCORR_OT_match(Operator):
    bl_idname = "gpcorr.match"
    bl_label = "Auto-Link Strokes"
    bl_description = "Automatically pair strokes between keyframes"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Layer selection dropdown with names
    layer_enum: EnumProperty(
        name="Layer",
        description="Layer to match",
        items=get_layer_items,
        update=update_active_layer
    )
    
    # Use custom range toggle
    use_custom_range: BoolProperty(
        name="Custom Range",
        description="Override auto-detected range with custom start/end frames",
        default=False
    )
    
    # Frame range (only used when use_custom_range is True)
    frame_start: IntProperty(
        name="Start Frame",
        description="First frame of range",
        default=1
    )
    
    frame_end: IntProperty(
        name="End Frame",
        description="Last frame of range",
        default=24
    )
    
    # Matching parameters
    max_alpha: FloatProperty(
        name="Max Alpha",
        description="Topology connectivity distance (higher = more permissive matching)",
        default=0.05,
        min=0.01,
        max=0.2,
        step=1,  # 0.01 increments
    )
    
    threshold: FloatProperty(
        name="Threshold",
        description="Distance threshold for matching strokes",
        default=0.05,
        min=0.01,
        max=0.2,
        step=1,  # 0.01 increments
    )
    
    def draw(self, context):
        """Custom draw for the popup dialog"""
        layout = self.layout
        
        # Layer dropdown
        layout.prop(self, "layer_enum", text="Layer")
        
        layout.separator()
        
        # Custom range toggle
        layout.prop(self, "use_custom_range")
        
        # Show frame range inputs only when custom range is enabled
        if self.use_custom_range:
            row = layout.row(align=True)
            row.prop(self, "frame_start", text="Start")
            row.prop(self, "frame_end", text="End")
        else:
            # Show auto-detected range as info
            obj = context.active_object
            if obj and obj.type == 'GREASEPENCIL':
                layer_idx = int(self.layer_enum) if self.layer_enum.isdigit() else 0
                if layer_idx < len(obj.data.layers):
                    layer = obj.data.layers[layer_idx]
                    start, end = detect_keyframe_range(context.scene, layer)
                    layout.label(text=f"Auto-detected: frames {start} → {end}", icon='INFO')
        
        layout.separator()
        
        # Advanced settings
        box = layout.box()
        box.label(text="Advanced", icon='PREFERENCES')
        box.prop(self, "max_alpha")
        box.prop(self, "threshold")
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}
        
        # Get layer index from enum
        layer_index = int(self.layer_enum) if self.layer_enum.isdigit() else 0
        
        # Validate layer
        if layer_index >= len(obj.data.layers):
            self.report({'ERROR'}, f"Layer index {layer_index} out of range")
            return {'CANCELLED'}
        
        layer = obj.data.layers[layer_index]
        
        # Determine frame range
        if self.use_custom_range:
            frame_start = self.frame_start
            frame_end = self.frame_end
        else:
            # Auto-detect frame range
            frame_start, frame_end = detect_keyframe_range(context.scene, layer)
        
        # Find keyframe pairs
        pairs = find_keyframe_pairs(layer, frame_start, frame_end)
        
        if not pairs:
            self.report({'WARNING'}, f"No keyframe pairs found in range {frame_start}-{frame_end}")
            return {'CANCELLED'}
        
        # Save viewport context for timer callbacks (region/rv3d are lost in timer context)
        viewport_ctx = {}
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        viewport_ctx['region'] = region
                        viewport_ctx['region_data'] = area.spaces.active.region_3d
                        break
                break
        set_state(viewport_context=viewport_ctx)
        
        # Prepare config
        config = {
            'max_alpha': self.max_alpha,
            'coincident_threshold': self.threshold,
        }
        
        # Start matching job
        success, camera_info = start_match_job(obj, layer_index, pairs, config)
        
        if success:
            # Show camera info/warning
            if camera_info:
                self.report({camera_info['type']}, camera_info['message'])
            self.report({'INFO'}, f"Started matching job: {len(pairs)} frame pairs")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to start matching job (job already running?)")
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        obj = context.active_object
        if obj and obj.type == 'GREASEPENCIL':
            # Set default layer to active layer
            active_layer = obj.data.layers.active
            if active_layer:
                for idx, layer in enumerate(obj.data.layers):
                    if layer == active_layer:
                        self.layer_enum = str(idx)
                        break
            
            # Auto-detect and set frame range defaults
            layer_idx = int(self.layer_enum) if self.layer_enum.isdigit() else 0
            if layer_idx < len(obj.data.layers):
                layer = obj.data.layers[layer_idx]
                self.frame_start, self.frame_end = detect_keyframe_range(context.scene, layer)
        
        return context.window_manager.invoke_props_dialog(self, width=300)
# Operator: Link Mode Toggle
class GPCORR_OT_link_mode_toggle(Operator):
    bl_idname = "gpcorr.link_mode"
    bl_label = "Manual"
    bl_description = "Manually pair strokes between keyframes"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        from .. import gp_correspondence
        from ..utils import linked_stroke_overlay
        
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}
        
        link_mode_active = get_state()['link_mode_active']
        
        if not link_mode_active:
            # Activate link mode
            set_state(link_mode_active=True)
            
            # Auto-enable linked strokes overlay
            set_state(show_linked_overlay=True)
            linked_stroke_overlay.manage_draw_handler()
            
            # Switch to Edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Set stroke selection mode
            bpy.ops.grease_pencil.set_selection_mode(mode='STROKE')
            
            # Enable multi-frame editing
            context.scene.tool_settings.use_grease_pencil_multi_frame_editing = True
            
            # Auto-select two keyframes around playhead
            active_layer = obj.data.layers.active
            layer = active_layer if active_layer else obj.data.layers[0]
            frame_start, frame_end = detect_keyframe_range(context.scene, layer)
            
            # Select the two keyframes in timeline
            for frame in layer.frames:
                frame.select = False  # Deselect all first
            
            # Now select the two target frames
            for frame in layer.frames:
                if frame.frame_number == frame_start or frame.frame_number == frame_end:
                    frame.select = True
            
            # Info already visible in UI header
            pass
            
            # Deselect all strokes on ALL layers
            for layer in obj.data.layers:
                for frame in layer.frames:
                    if frame.drawing:
                        for stroke in frame.drawing.strokes:
                            stroke.select = False
            
        else:
            # Deactivate link mode
            set_state(link_mode_active=False)
            
            # Disable linked strokes overlay
            set_state(show_linked_overlay=False)
            linked_stroke_overlay.manage_draw_handler()

            # Deselect keyframes
            if obj and obj.type == 'GREASEPENCIL':
                for layer in obj.data.layers:
                    for frame in layer.frames:
                        frame.select = False
            
            # Disable multi-frame editing
            context.scene.tool_settings.use_grease_pencil_multi_frame_editing = False
            
            # Deselect all strokes on ALL layers
            for layer in obj.data.layers:
                for frame in layer.frames:
                    if frame.drawing:
                        for stroke in frame.drawing.strokes:
                            stroke.select = False
            
            # Return to previous mode (typically Paint)
            bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')

            # Info already visible in UI header
            pass
        
        return {'FINISHED'}
# Operator: Link Selected Pair
class GPCORR_OT_link_selected(Operator):
    bl_idname = "gpcorr.link_selected"
    bl_label = "Link"
    bl_description = "Pair selected strokes"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return get_state()['link_mode_active']
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            return {'CANCELLED'}
        
        # Detect selected strokes across frames
        selected_by_frame = {}  # {(layer_idx, frame_number): [stroke_indices]}
        
        for layer_idx, layer in enumerate(obj.data.layers):
            for frame in layer.frames:
                if not frame.select:
                    continue
                
                if not frame.drawing:
                    continue
                
                selected_strokes = []
                for stroke_idx, stroke in enumerate(frame.drawing.strokes):
                    if stroke.select:
                        selected_strokes.append(stroke_idx)
                
                if selected_strokes:
                    selected_by_frame[(layer_idx, frame.frame_number)] = selected_strokes
        
        # Validate: exactly one stroke selected in exactly two frames on same layer
        if len(selected_by_frame) != 2:
            self.report({'WARNING'}, f"Select exactly one stroke in each of two frames (found {len(selected_by_frame)} frames)")
            return {'CANCELLED'}
        
        frames_list = list(selected_by_frame.items())
        (layer1, frame1), strokes1 = frames_list[0]
        (layer2, frame2), strokes2 = frames_list[1]
        
        if layer1 != layer2:
            self.report({'WARNING'}, "Selected strokes must be on the same layer")
            return {'CANCELLED'}
        
        if len(strokes1) != 1 or len(strokes2) != 1:
            self.report({'WARNING'}, f"Select exactly one stroke per frame (found {len(strokes1)} and {len(strokes2)})")
            return {'CANCELLED'}
        
        stroke1_idx = strokes1[0]
        stroke2_idx = strokes2[0]
        
        # Normalize frame order: always store smaller frame first
        if frame1 < frame2:
            norm_frame1, norm_stroke1 = frame1, stroke1_idx
            norm_frame2, norm_stroke2 = frame2, stroke2_idx
        else:
            norm_frame1, norm_stroke1 = frame2, stroke2_idx
            norm_frame2, norm_stroke2 = frame1, stroke1_idx
        
        # Ensure stable IDs exist and get stable IDs for the selected strokes
        stable_ids1 = ensure_stable_ids(obj, layer1, norm_frame1)
        stable_ids2 = ensure_stable_ids(obj, layer1, norm_frame2)
        
        # Get stable IDs for the selected stroke indices
        stable_id1 = stable_ids1.get(norm_stroke1, norm_stroke1)
        stable_id2 = stable_ids2.get(norm_stroke2, norm_stroke2)
        
        # Add to linked constraints (normalized order, storing STABLE IDs)
        constraint = (layer1, norm_frame1, stable_id1, norm_frame2, stable_id2)
        link_constraints = get_state()['link_constraints']
        
        if constraint not in link_constraints:
            link_constraints.append(constraint)
            set_state(link_constraints=link_constraints)
            
            # Auto-run matching on this frame pair
            # The new link constraint will be passed as a seed to C++, 
            # allowing the algorithm to propagate better matches from it (per FTP-SC paper)
            pairs = [(norm_frame1, norm_frame2)]
            
            # Save viewport context for matching (needed for stroke projection)
            viewport_ctx = {}
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            viewport_ctx['region'] = region
                            viewport_ctx['region_data'] = area.spaces.active.region_3d
                            break
                    break
            set_state(viewport_context=viewport_ctx)
            
            # Run matching with default config - seeds will be extracted from link_constraints
            config = {
                'max_alpha': 0.05,
                'coincident_threshold': 0.05,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Linked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            self.report({'INFO'}, "This pair is already linked")

        bpy.ops.grease_pencil.select_all(action='DESELECT')
        
        return {'FINISHED'}
# Operator: Clear All Links
class GPCORR_OT_clear_all_links(Operator):
    bl_idname = "gpcorr.clear_all_links"
    bl_label = "Clear All Links"
    bl_description = "Remove all manual link constraints"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        state = get_state()
        # Only enable if there are actually links to clear
        return state['link_mode_active'] and len(state['link_constraints']) > 0

    def invoke(self, context, event):
        link_constraints = get_state()['link_constraints']
        count = len(link_constraints)
        
        # Show confirmation dialog
        return context.window_manager.invoke_confirm(
            self, 
            event,
            message=f"Clear all {count} manual link(s)?",
            confirm_text="Clear All"
        )

    def execute(self, context):
        link_constraints = get_state()['link_constraints']
        count = len(link_constraints)
        
        if count == 0:
            self.report({'INFO'}, "No links to clear")
            return {'CANCELLED'}
        
        set_state(link_constraints=[])
        
        self.report({'INFO'}, f"Cleared {count} link(s)")
        return {'FINISHED'}


# Operator: Unlink Selected Pair
class GPCORR_OT_unlink_selected(Operator):
    bl_idname = "gpcorr.unlink_selected"
    bl_label = "Unlink"
    bl_description = "Remove pairing"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_state()['link_mode_active']

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            return {'CANCELLED'}

        selected_by_frame = {}
        for layer_idx, layer in enumerate(obj.data.layers):
            for frame in layer.frames:
                if not frame.select or not frame.drawing:
                    continue
                sel = [i for i, s in enumerate(frame.drawing.strokes) if s.select]
                if sel:
                    selected_by_frame[(layer_idx, frame.frame_number)] = sel

        if len(selected_by_frame) != 2:
            self.report({'WARNING'}, f"Select exactly one stroke in each of two frames (found {len(selected_by_frame)} frames)")
            return {'CANCELLED'}

        (layer1, frame1), strokes1 = list(selected_by_frame.items())[0]
        (layer2, frame2), strokes2 = list(selected_by_frame.items())[1]

        if layer1 != layer2 or len(strokes1) != 1 or len(strokes2) != 1:
            self.report({'WARNING'}, "Selection must be one stroke per frame on the same layer")
            return {'CANCELLED'}

        stroke1_idx = strokes1[0]
        stroke2_idx = strokes2[0]

        # Normalize frame order (smaller frame first) for consistent lookup
        if frame1 < frame2:
            norm_frame1, norm_stroke1 = frame1, stroke1_idx
            norm_frame2, norm_stroke2 = frame2, stroke2_idx
        else:
            norm_frame1, norm_stroke1 = frame2, stroke2_idx
            norm_frame2, norm_stroke2 = frame1, stroke1_idx
        
        # Get stable IDs for the selected strokes
        stable_ids1 = ensure_stable_ids(obj, layer1, norm_frame1)
        stable_ids2 = ensure_stable_ids(obj, layer1, norm_frame2)
        stable_id1 = stable_ids1.get(norm_stroke1, norm_stroke1)
        stable_id2 = stable_ids2.get(norm_stroke2, norm_stroke2)
        
        # Remove the normalized constraint (using STABLE IDs)
        constraint = (layer1, norm_frame1, stable_id1, norm_frame2, stable_id2)
        
        link_constraints = get_state()['link_constraints']
        before = len(link_constraints)
        new_constraints = [c for c in link_constraints if c != constraint]
        set_state(link_constraints=new_constraints)
        after = len(new_constraints)

        bpy.ops.grease_pencil.select_all(action='DESELECT')

        if after < before:
            self.report({'INFO'}, "Unlinked selected pair")
            
            # Auto-run matching on this frame pair to re-match without the constraint
            layer = obj.data.layers[layer1]
            pairs = [(norm_frame1, norm_frame2)]
            
            # Save viewport context for matching
            viewport_ctx = {}
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            viewport_ctx['region'] = region
                            viewport_ctx['region_data'] = area.spaces.active.region_3d
                            break
                    break
            set_state(viewport_context=viewport_ctx)
            
            # Run matching with default config - no seeds since constraint was removed
            config = {
                'max_alpha': 0.05,
                'coincident_threshold': 0.05,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Unlinked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            self.report({'INFO'}, "Selected pair was not linked")

        return {'FINISHED'}
# Registration
classes = (
    GPCORR_OT_match,
    GPCORR_OT_link_mode_toggle,
    GPCORR_OT_link_selected,
    GPCORR_OT_clear_all_links,
    GPCORR_OT_unlink_selected,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
