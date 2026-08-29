"""
Correspondence Operators
Handles matching, linking, and unlinking operations for GP stroke correspondence.
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty
import time
import traceback
import json
import os

from ..utils.correspondence_utils import (
    detect_keyframe_range,
    collect_strokes_2d,
    to_cpp_strokes
)


def _is_verbose():
    try:
        from .. import gp_correspondence
        return gp_correspondence._debug_verbose
    except Exception:
        return False


def _log(msg):
    if _is_verbose():
        print(f"[GPCORR] {msg}")


def _log_history(entry):
    try:
        from .. import gp_correspondence
        gp_correspondence._history_append(entry)
    except Exception as e:
        print(f"[GPCORR] history append failed: {e}")

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
    _t0 = time.time()
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

        if _is_verbose():
            _log(f"┌─ match L{layer_idx} {frame1}→{frame2} | s1:{len(s1)} s2:{len(s2)} | constraints:{len(link_constraints)} | cfg={config}")

        cfg = gp_autointerpolate.MatcherConfig()
        cfg.enable_stage_two = True
        cfg.max_alpha = config['max_alpha']
        cfg.coincident_threshold = config['coincident_threshold']
        # Verbose → enable C++ debug (prints to System Console via stderr)
        _verb = _is_verbose()
        cfg.debug = _verb
        try:
            cfg.debug_level = 2 if _verb else 1
        except AttributeError:
            pass
        if _verb:
            _log(f"│ C++ cfg debug={cfg.debug} max_alpha={cfg.max_alpha} thresh={cfg.coincident_threshold} stage2={cfg.enable_stage_two}")
        
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
                        if _is_verbose():
                            _log(f"│ seed skip (not in collected): stable {stable_id1}->{stable_id2} cur {current_idx1}->{current_idx2}")
                        pass
                elif _is_verbose():
                    _log(f"│ seed skip (stable miss): {constraint} -> {stable_id1}->{stable_id2}")

        if _is_verbose():
            _log(f"│ seeds col({len(seeds)}): {seeds} | stable constraints total:{len(link_constraints)}")
            _log(f"│ indices1 {indices1} | indices2 {indices2}")
            _log(f"│ stable1 {stable_ids1} | stable2 {stable_ids2}")

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

        if _is_verbose():
            _log(f"│ C++ raw col {len(raw_matches)}: {raw_matches}")
            _log(f"│ mapped orig {len(result_matches)}: {result_matches}")
            try:
                _log(f"│ C++ costs s1={result.stage_one_cost:.4f} final={result.final_cost:.4f} matched={result.num_matched} s2={result.used_stage_two} s1m={result.stage_one_correspondence.num_matches() if hasattr(result.stage_one_correspondence,'num_matches') else '?' }")
            except Exception:
                pass

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

        # Snapshot before reorder for delta
        _before_order = list(range(num_strokes))
        try:
            # stable IDs before
            _before_stable = dict(get_state()['stable_stroke_ids'].get((layer_idx, reorder_frame), {}))
        except Exception:
            _before_stable = {}
        
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

        # Metrics and history
        _identity = sum(1 for a, b in result_matches if a == b)
        _elapsed = time.time() - _t0
        _msg = f"Matched {len(result_matches)} pairs (seeds: {len(seeds)})"
        # Determine degradation vs previous history for same pair
        _prev_entry = None
        try:
            from .. import gp_correspondence as _gc
            for e in reversed(_gc._linking_history):
                if e.get('layer_idx') == layer_idx and tuple(e.get('frames', ())) == (frame1, frame2):
                    _prev_entry = e
                    break
        except Exception:
            pass
        _kept = _flipped = _broken = None
        if _prev_entry and _prev_entry.get('matches'):
            try:
                _prev_set = set(tuple(x) for x in _prev_entry['matches'])
                _cur_set = set(result_matches)
                _kept = len(_prev_set & _cur_set)
                _flipped = len(_cur_set - _prev_set)
                _broken = len(_prev_set - _cur_set)
            except Exception:
                pass

        if _is_verbose():
            _log(f"│ reorder F{reorder_frame}: {new_indices} (swap={swap_match})")
            _log(f"│ stable F{reorder_frame} before={_before_stable} after={dict(get_state()['stable_stroke_ids'].get(key, {}))}")
            _log(f"│ metrics identity { _identity}/{len(result_matches)} perfect={_identity==len(result_matches) and len(result_matches)==num_strokes} | elapsed {_elapsed:.3f}s")
            if _prev_entry is not None:
                _log(f"│ Δ vs prev kept={_kept} new={_flipped} broken={_broken} prev_seeds={_prev_entry.get('seeds')} prev_kept={_prev_entry.get('matches')}")
                if _flipped is not None and _flipped > 2 and _identity < len(result_matches):
                    _log(f"│ ⚠ DEGRADATION: { _flipped} new mismatches after fix — check seeds {seeds}")
            _log(f"└─ done {_msg} | C++ says {result.num_matched} matched")

        # Append to persistent history (always, even if not verbose — gives data)
        try:
            _entry = {
                "ts": time.time(),
                "layer_idx": layer_idx,
                "frames": (frame1, frame2),
                "num_strokes": (len(s1), len(s2), num_strokes),
                "indices": (list(indices1), list(indices2)),
                "seeds_col": list(seeds),
                "seeds_stable": [c for c in link_constraints if c[0]==layer_idx and c[1]==lookup_frame1 and c[3]==lookup_frame2],
                "raw_matches_col": list(raw_matches),
                "matches": list(result_matches),
                "reorder_frame": reorder_frame,
                "new_indices": list(new_indices),
                "identity": _identity,
                "perfect": (_identity == len(result_matches) == num_strokes),
                "elapsed": _elapsed,
                "config": dict(config),
                "prev_delta": {"kept": _kept, "flipped": _flipped, "broken": _broken} if _prev_entry else None,
                "cpp": {
                    "stage_one_cost": getattr(result, 'stage_one_cost', None),
                    "final_cost": getattr(result, 'final_cost', None),
                    "num_matched": getattr(result, 'num_matched', None),
                    "used_stage_two": getattr(result, 'used_stage_two', None),
                }
            }
            _log_history(_entry)
        except Exception as e:
            _log(f"│ history append failed: {e}")
            traceback.print_exc()

        msg = _msg
        return (True, result_matches, msg)
        
    except Exception as e:
        if _is_verbose():
            _log(f"└─ ✗ failed {frame1}→{frame2}: {e}")
            traceback.print_exc()
        return (False, [], f"Match failed: {e}")


def run_match_job_step():
    """Single step of multi-pair matching job."""
    state = get_state()
    
    if not state['match_job_running']:
        return None  # Stop timer
    if _is_verbose():
        _log(f"▶ job step check running={state['match_job_running']} progress={state['match_progress'].get('current',0)}/{state['match_progress'].get('total',0)}")
    
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
        if _is_verbose():
            _log(f"■ job done {len(pairs)} pairs — history len {len(get_state().get('link_constraints',[])) if False else 'n/a'}")
            try:
                from .. import gp_correspondence as _gc
                _log(f"■ history total entries={len(_gc._linking_history)} last={_gc._linking_history[-1]['matches'] if _gc._linking_history else 'none'}")
            except Exception:
                pass

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
    if _is_verbose():
        _log(f"▶ job step {current+1}/{len(pairs)} frames {frame1}→{frame2}")
    
    success, matches, msg = run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config)
    if _is_verbose():
        _log(f"◀ step {current+1} {msg} success={success}")
    
    match_progress['current'] = current + 1
    return 0.1


def start_match_job(gp_obj, layer_idx, pairs, config):
    """Start non-blocking multi-pair matching job. Returns (success, camera_info)"""
    state = get_state()
    
    if state['match_job_running']:
        if _is_verbose():
            _log(f"✗ start_match_job blocked: already running {state['match_progress']}")
        return (False, None)
    if _is_verbose():
        _log(f"▶ start_match_job L{layer_idx} pairs={pairs} cfg={config} obj={gp_obj.name if gp_obj else 'None'}")
    
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
        if _is_verbose():
            _log(f"Link sel L{layer1} F{norm_frame1}:{norm_stroke1}(stable {stable_id1}) ↔ F{norm_frame2}:{norm_stroke2}(stable {stable_id2}) before={link_constraints}")

        if constraint not in link_constraints:
            link_constraints.append(constraint)
            set_state(link_constraints=link_constraints)
            if _is_verbose():
                _log(f"Link ADDED {constraint} total now {len(link_constraints)}")

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
                'max_alpha': 0.5,
                'coincident_threshold': 0.5,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if _is_verbose():
                _log(f"Link trigger job success={success} pairs={pairs}")
            if success:
                self.report({'INFO'}, f"Linked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            if _is_verbose():
                _log(f"Link duplicate skip {constraint}")
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
        
        if _is_verbose():
            _log(f"CLEAR all {count} links before={link_constraints}")
        set_state(link_constraints=[])
        # also log history marker
        _log_history({"ts": time.time(), "action": "clear_all", "count": count, "before": list(link_constraints)})
        if _is_verbose():
            _log(f"CLEARED {count}")

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
        if _is_verbose():
            _log(f"Unlink sel L{layer1} F{norm_frame1}:{norm_stroke1}(stable {stable_id1}) ↔ F{norm_frame2}:{norm_stroke2}(stable {stable_id2}) try={constraint} before={link_constraints}")
        before = len(link_constraints)
        new_constraints = [c for c in link_constraints if c != constraint]
        set_state(link_constraints=new_constraints)
        after = len(new_constraints)
        if _is_verbose():
            _log(f"Unlink {'REMOVED' if after<before else 'NOT FOUND'} after={new_constraints}")

        bpy.ops.grease_pencil.select_all(action='DESELECT')

        if after < before:
            _log_history({"ts": time.time(), "action": "unlink", "constraint": constraint, "before": before, "after": after})
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
                'max_alpha': 0.5,
                'coincident_threshold': 0.5,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if _is_verbose():
                _log(f"Unlink trigger job success={success} pairs={pairs}")
            if success:
                self.report({'INFO'}, f"Unlinked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            if _is_verbose():
                _log(f"Unlink not linked {constraint}")
            self.report({'INFO'}, "Selected pair was not linked")

        return {'FINISHED'}

# Operator: Toggle Debug Verbose
class GPCORR_OT_toggle_debug(Operator):
    bl_idname = "gpcorr.toggle_debug"
    bl_label = "Toggle Debug"
    bl_description = "Toggle verbose console logging for linking/matching"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .. import gp_correspondence as _gc
        _gc._debug_verbose = not _gc._debug_verbose
        state = "ON" if _gc._debug_verbose else "OFF"
        print(f"[GPCORR] verbose {state}")
        # also log history
        _log_history({"ts": time.time(), "action": "toggle_debug", "verbose": _gc._debug_verbose})
        self.report({'INFO'}, f"GPCORR verbose {state} (see System Console)")
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


# Operator: Dump Linking History
class GPCORR_OT_dump_history(Operator):
    bl_idname = "gpcorr.dump_history"
    bl_label = "Dump History"
    bl_description = "Write linking history to JSON file and print summary to console"
    bl_options = {'REGISTER'}

    filepath: StringProperty(name="File Path", default="", subtype='FILE_PATH')

    def invoke(self, context, event):
        # default to ~/gp_linking_history.jsonl and also dump pretty JSON
        default = os.path.join(os.path.expanduser("~"), "gp_linking_history.json")
        self.filepath = default
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "filepath")
        try:
            from .. import gp_correspondence as _gc
            self.layout.label(text=f"{len(_gc._linking_history)} entries in memory")
        except: pass

    def execute(self, context):
        from .. import gp_correspondence as _gc
        hist = list(_gc._linking_history)
        path = bpy.path.abspath(self.filepath) if self.filepath else os.path.join(os.path.expanduser("~"), "gp_linking_history.json")
        # also ensure jsonl exists
        jsonl = os.path.join(os.path.expanduser("~"), "gp_linking_history.jsonl")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(hist, f, indent=2, default=str)
            print(f"[GPCORR] dumped {len(hist)} entries to {path}")
            print(f"[GPCORR] jsonl also at {jsonl} ({os.path.getsize(jsonl) if os.path.exists(jsonl) else 0} bytes)")
            # console summary
            for i, e in enumerate(hist[-15:]):
                print(f"[GPCORR][hist {i}] {e.get('frames')} seeds={e.get('seeds_col')} matches={e.get('matches')} id={e.get('identity')}/{len(e.get('matches',[]))} perfect={e.get('perfect')} delta={e.get('prev_delta')}")
            self.report({'INFO'}, f"Dumped {len(hist)} to {path}")
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"Dump failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


# Operator: Clear History
class GPCORR_OT_clear_history(Operator):
    bl_idname = "gpcorr.clear_history"
    bl_label = "Clear History"
    bl_description = "Clear in-memory linking history and JSONL file"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .. import gp_correspondence as _gc
        n = len(_gc._linking_history)
        _gc._linking_history.clear()
        # also truncate jsonl
        try:
            jsonl = os.path.join(os.path.expanduser("~"), "gp_linking_history.jsonl")
            if os.path.exists(jsonl):
                open(jsonl, "w").close()
        except Exception:
            pass
        print(f"[GPCORR] cleared history {n} entries")
        self.report({'INFO'}, f"Cleared {n} history entries")
        return {'FINISHED'}

# Registration
classes = (
    GPCORR_OT_link_mode_toggle,
    GPCORR_OT_link_selected,
    GPCORR_OT_clear_all_links,
    GPCORR_OT_unlink_selected,
    GPCORR_OT_toggle_debug,
    GPCORR_OT_dump_history,
    GPCORR_OT_clear_history,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
