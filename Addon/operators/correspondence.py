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
    clear_match_ids_for_layer_frames,
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
def run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config):
    """Run correspondence matching between two frames. Returns (success, matches, message)."""
    try:
        import gp_autointerpolate
    except ImportError as e:
        return (False, [], f"gp_autointerpolate module not found: {e}")
    
    try:
        state = get_state()
        link_constraints = state['link_constraints']
        
        clear_match_ids_for_layer_frames(gp_obj, layer_idx, frame1, frame2)
        
        s1, indices1 = collect_strokes_2d(gp_obj, layer_idx, frame1)
        s2, indices2 = collect_strokes_2d(gp_obj, layer_idx, frame2)
        
        if len(s1) == 0 or len(s2) == 0:
            return (False, [], f"No valid strokes in frames {frame1} or {frame2}")
        
        S1 = to_cpp_strokes(s1)
        S2 = to_cpp_strokes(s2)
        
        cfg = gp_autointerpolate.MatcherConfig()
        cfg.enable_stage_two = True
        cfg.max_alpha = config['max_alpha']
        cfg.coincident_threshold = config['coincident_threshold']
        cfg.debug = config['debug']
        cfg.debug_level = config['debug_level']
        
        linked_for_this_pair = []
        strokes_to_exclude_1 = set()
        strokes_to_exclude_2 = set()
        
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
                
                try:
                    filtered_idx1 = indices1.index(actual_stroke1)
                    filtered_idx2 = indices2.index(actual_stroke2)
                    linked_for_this_pair.append((filtered_idx1, filtered_idx2))
                    strokes_to_exclude_1.add(filtered_idx1)
                    strokes_to_exclude_2.add(filtered_idx2)
                except ValueError:
                    pass
        
        if len(strokes_to_exclude_1) >= len(S1) or len(strokes_to_exclude_2) >= len(S2):
            result_matches = linked_for_this_pair
        else:
            S1_filtered = [s for i, s in enumerate(S1) if i not in strokes_to_exclude_1]
            S2_filtered = [s for i, s in enumerate(S2) if i not in strokes_to_exclude_2]
            
            if len(S1_filtered) > 0 and len(S2_filtered) > 0:
                matcher = gp_autointerpolate.StrokeMatcher(cfg)
                result = matcher.match(S1_filtered, S2_filtered)
                
                idx1_map = [i for i in range(len(S1)) if i not in strokes_to_exclude_1]
                idx2_map = [i for i in range(len(S2)) if i not in strokes_to_exclude_2]
                
                matched_pairs = [(idx1_map[i], idx2_map[j]) for i, j in result.final_correspondence.matches]
                result_matches = linked_for_this_pair + matched_pairs
            else:
                result_matches = linked_for_this_pair
        
        matched_strokes_frame1 = set()
        matched_strokes_frame2 = set()
        
        for match_id, (i, j) in enumerate(result_matches):
            original_i = indices1[i]
            original_j = indices2[j]
            
            store_match_id_on_strokes(gp_obj, layer_idx, frame1, [original_i], match_id)
            store_match_id_on_strokes(gp_obj, layer_idx, frame2, [original_j], match_id)
            
            matched_strokes_frame1.add(original_i)
            matched_strokes_frame2.add(original_j)
        
        layer = gp_obj.data.layers[layer_idx]
        
        for f_num in [frame1, frame2]:
            matched_set = matched_strokes_frame1 if f_num == frame1 else matched_strokes_frame2
            
            frame_obj = None
            for f in layer.frames:
                if f.frame_number == f_num:
                    frame_obj = f
                    break
            
            if frame_obj and frame_obj.drawing:
                for stroke_idx in range(len(frame_obj.drawing.strokes)):
                    if stroke_idx not in matched_set:
                        store_match_id_on_strokes(gp_obj, layer_idx, f_num, [stroke_idx], stroke_idx)
        
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
        set_state(match_job_running=False)
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
    
    link_constraints = state['link_constraints']
    new_constraints = [
        c for c in link_constraints 
        if c[0] != layer_idx or (c[1], c[3]) not in pairs_set
    ]
    set_state(link_constraints=new_constraints)
    
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
# Operator: GP Match (Main Matching Operator)
class GPCORR_OT_match(Operator):
    bl_idname = "gpcorr.match"
    bl_label = "Auto-Match Strokes"
    bl_description = "Run correspondence matching for selected layer and frame range"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Layer selection (dropdown populated dynamically)
    layer_index: IntProperty(
        name="Layer",
        description="Layer to match",
        default=0,
        min=0
    )
    
    # Frame range
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
    
    # Auto-detect mode
    auto_detect: BoolProperty(
        name="Auto-Detect Range",
        description="Automatically detect keyframe range around playhead",
        default=True
    )
    
    # Matching parameters
    max_alpha: FloatProperty(
        name="Max Alpha",
        description="Maximum angle for corner detection",
        default=165.0,
        min=0.0,
        max=180.0
    )
    
    coincident_threshold: FloatProperty(
        name="Coincident Threshold",
        description="Distance threshold for coincident points",
        default=0.02,
        min=0.0,
        max=1.0
    )
    
    debug: BoolProperty(
        name="Debug Output",
        description="Print debug information to console",
        default=False
    )
    
    debug_level: IntProperty(
        name="Debug Level",
        description="Debug verbosity (0=minimal, 2=verbose)",
        default=0,
        min=0,
        max=2
    )
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'GREASEPENCIL':
            self.report({'ERROR'}, "Select a Grease Pencil object")
            return {'CANCELLED'}
        
        # Validate layer
        if self.layer_index >= len(obj.data.layers):
            self.report({'ERROR'}, f"Layer index {self.layer_index} out of range")
            return {'CANCELLED'}
        
        layer = obj.data.layers[self.layer_index]
        
        # Auto-detect frame range if enabled
        if self.auto_detect:
            self.frame_start, self.frame_end = detect_keyframe_range(context.scene, layer)
        
        # Find keyframe pairs
        pairs = find_keyframe_pairs(layer, self.frame_start, self.frame_end)
        
        if not pairs:
            self.report({'WARNING'}, f"No keyframe pairs found in range {self.frame_start}-{self.frame_end}")
            return {'CANCELLED'}
        
        # Prepare config
        config = {
            'max_alpha': self.max_alpha,
            'coincident_threshold': self.coincident_threshold,
            'debug': self.debug,
            'debug_level': self.debug_level
        }
        
        # Start matching job
        success = start_match_job(obj, self.layer_index, pairs, config)
        
        if success:
            self.report({'INFO'}, f"Started matching job: {len(pairs)} frame pairs")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to start matching job")
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        obj = context.active_object
        if obj and obj.type == 'GREASEPENCIL':
            # Set default layer to active layer
            active_layer = obj.data.layers.active
            if active_layer:
                for idx, layer in enumerate(obj.data.layers):
                    if layer == active_layer:
                        self.layer_index = idx
                        break
        
        return context.window_manager.invoke_props_dialog(self)
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
        else:
            self.report({'INFO'}, "Selected pair was not linked")

        # redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

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
