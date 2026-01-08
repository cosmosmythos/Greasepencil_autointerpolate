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
    store_match_id_on_strokes,
    clear_match_ids_for_layer_frame,
    collect_strokes_2d,
    to_cpp_strokes
)

_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_constraints = []


def get_state():
    """Get reference to global state from parent module"""
    from .. import gp_correspondence
    return {
        'match_job_running': gp_correspondence._match_job_running,
        'match_progress': gp_correspondence._match_progress,
        'link_constraints': gp_correspondence._link_constraints,
        'link_mode_active': gp_correspondence._link_mode_active,
        'viewport_context': gp_correspondence._viewport_context,
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
def run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config):
    """Run correspondence matching between two frames. Returns (success, matches, message)."""
    try:
        import gp_autointerpolate
    except ImportError as e:
        return (False, [], f"gp_autointerpolate module not found: {e}")
    
    try:
        state = get_state()
        link_constraints = state['link_constraints']
        
        # Only clear match_ids on the earlier frame (frame1 stores match_id pointing to frame2)
        earlier_frame = min(frame1, frame2)
        clear_match_ids_for_layer_frame(gp_obj, layer_idx, earlier_frame)
        
        s1, indices1 = collect_strokes_2d(gp_obj, layer_idx, frame1)
        s2, indices2 = collect_strokes_2d(gp_obj, layer_idx, frame2)
        
        if len(s1) == 0 or len(s2) == 0:
            return (False, [], f"No valid strokes in frames {frame1} or {frame2}")
        
        cfg = gp_autointerpolate.MatcherConfig()
        cfg.enable_stage_two = True
        cfg.max_alpha = config['max_alpha']
        cfg.coincident_threshold = config['coincident_threshold']
        cfg.debug = config.get('debug', False)
        
        # Build seeds from linked constraints for this frame pair
        # Seeds are passed to C++ to guide the matching algorithm (per FTP-SC paper)
        seeds = []
        
        lookup_frame1, lookup_frame2 = (frame1, frame2) if frame1 < frame2 else (frame2, frame1)
        swap_order = (frame1 > frame2)
        
        for constraint in link_constraints:
            c_layer, c_frame1, c_stroke1, c_frame2, c_stroke2 = constraint
            if c_layer == layer_idx and c_frame1 == lookup_frame1 and c_frame2 == lookup_frame2:
                if swap_order:
                    actual_stroke1 = c_stroke2
                    actual_stroke2 = c_stroke1
                else:
                    actual_stroke1 = c_stroke1
                    actual_stroke2 = c_stroke2
                
                # Map original stroke indices to collected stroke indices
                try:
                    idx1 = indices1.index(actual_stroke1)
                    idx2 = indices2.index(actual_stroke2)
                    seeds.append((idx1, idx2))
                except ValueError:
                    pass  # Stroke not found in collection (maybe filtered out)
        
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
        
        matched_strokes = set()
        
        # Determine which frame is earlier (stores match_id) and which is later (target)
        if frame1 < frame2:
            src_frame, tgt_frame = frame1, frame2
            src_indices, tgt_indices = indices1, indices2
            # result_matches are (i, j) where i is src index, j is tgt index
            swap_match = False
        else:
            src_frame, tgt_frame = frame2, frame1
            src_indices, tgt_indices = indices2, indices1
            # result_matches are (i, j) but we need to swap them
            swap_match = True
        
        for idx, (i, j) in enumerate(result_matches):
            if swap_match:
                i, j = j, i
            
            src_stroke_idx = src_indices[i]
            tgt_stroke_idx = tgt_indices[j]
            
            # Store the target stroke index as match_id on the source frame stroke
            # This tells interpolation: "source stroke i corresponds to target stroke j"
            store_match_id_on_strokes(gp_obj, layer_idx, src_frame, [src_stroke_idx], tgt_stroke_idx)
            matched_strokes.add(src_stroke_idx)
        
        # Set unmatched strokes to their own index (position-based default)
        layer = gp_obj.data.layers[layer_idx]
        frame_obj = None
        for f in layer.frames:
            if f.frame_number == src_frame:
                frame_obj = f
                break
        
        if frame_obj and frame_obj.drawing:
            for stroke_idx in range(len(frame_obj.drawing.strokes)):
                if stroke_idx not in matched_strokes:
                    store_match_id_on_strokes(gp_obj, layer_idx, src_frame, [stroke_idx], stroke_idx)
        
        return (True, result_matches, f"Matched {len(result_matches)} pairs (linked: {len(linked_for_this_pair)})")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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
            target_name = scene.get("gp_interpolation_target")
            if target_name and target_name == gp_obj.name:
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
    
    if not success:
        print(f"[GPCORR] Error: {msg}")
    
    match_progress['current'] = current + 1
    return 0.1


def start_match_job(gp_obj, layer_idx, pairs, config):
    """Start non-blocking multi-pair matching job"""
    state = get_state()
    
    if state['match_job_running']:
        return False
    
    pairs_set = set()
    for f1, f2 in pairs:
        norm = (f1, f2) if f1 < f2 else (f2, f1)
        pairs_set.add(norm)
    
    # NOTE: We keep link_constraints - they should be used by the matcher, not cleared!
    # Only clear constraints for frame pairs that no longer exist in the animation
    
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
    
    return True
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
    bl_label = "Auto-Match Strokes"
    bl_description = "Run correspondence matching for selected layer and frame range"
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
    
    debug: BoolProperty(
        name="Debug Output",
        description="Print debug information to console",
        default=False
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
        box.prop(self, "debug")
    
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
            'debug': self.debug,
        }
        
        # Start matching job
        success = start_match_job(obj, layer_index, pairs, config)
        
        if success:
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
    bl_label = "Link Mode"
    bl_description = "Edit mode for locking/unlocking ID matching between two keyframes"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        from .. import gp_correspondence
        
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}
        
        link_mode_active = get_state()['link_mode_active']
        
        if not link_mode_active:
            # Activate link mode
            set_state(link_mode_active=True)

            # Auto-enable visualization while linking
            context.scene.gpcorr_show_matches = True
            gp_correspondence.install_draw_handler()
            
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
            
            self.report({'INFO'}, f"Link Mode ON | Frames: {frame_start}-{frame_end} selected | Select strokes to link")
            
            # Deselect all strokes initially
            bpy.ops.grease_pencil.select_all(action='DESELECT')
            
        else:
            # Deactivate link mode
            set_state(link_mode_active=False)

            # Auto-disable visualization when leaving link mode
            context.scene.gpcorr_show_matches = False

            # Deselect keyframes
            if obj and obj.type == 'GREASEPENCIL':
                for layer in obj.data.layers:
                    for frame in layer.frames:
                        frame.select = False
            
            # Disable multi-frame editing
            context.scene.tool_settings.use_grease_pencil_multi_frame_editing = False
            
            # Deselect all strokes
            bpy.ops.grease_pencil.select_all(action='DESELECT')
            
            # Return to previous mode (typically Paint)
            bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')
            
            # Ensure handlers are removed when leaving link mode (since Eye is off)
            gp_correspondence.remove_draw_handler()

            self.report({'INFO'}, "Link Mode OFF")
        
        return {'FINISHED'}
# Operator: Link Selected Pair
class GPCORR_OT_link_selected(Operator):
    bl_idname = "gpcorr.link_selected"
    bl_label = "Link"
    bl_description = "Lock ID matching for selected stroke pair"
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
        
        # Add to linked constraints (normalized order)
        constraint = (layer1, norm_frame1, norm_stroke1, norm_frame2, norm_stroke2)
        link_constraints = get_state()['link_constraints']
        
        if constraint not in link_constraints:
            link_constraints.append(constraint)
            set_state(link_constraints=link_constraints)
            
            self.report({'INFO'}, f"Linked: Frame {norm_frame1} Stroke {norm_stroke1} → Frame {norm_frame2} Stroke {norm_stroke2}")
            
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
                'debug': False,
            }
            success = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Linked and re-matching Frame {norm_frame1} → {norm_frame2}")
        else:
            self.report({'INFO'}, "This pair is already linked")

        bpy.ops.grease_pencil.select_all(action='DESELECT')
        
        return {'FINISHED'}
# Operator: Unlink Selected Pair
class GPCORR_OT_unlink_selected(Operator):
    bl_idname = "gpcorr.unlink_selected"
    bl_label = "Unlink"
    bl_description = "Unlock ID matching for selected stroke pair"
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
        
        # Remove the normalized constraint
        constraint = (layer1, norm_frame1, norm_stroke1, norm_frame2, norm_stroke2)
        
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
                'debug': False,
            }
            success = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Unlinked and re-matching Frame {norm_frame1} → {norm_frame2}")
        else:
            self.report({'INFO'}, "Selected pair was not linked")

        return {'FINISHED'}
# Registration
classes = (
    GPCORR_OT_match,
    GPCORR_OT_link_mode_toggle,
    GPCORR_OT_link_selected,
    GPCORR_OT_unlink_selected,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
