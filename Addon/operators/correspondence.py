
import bpy
from bpy.types import Operator

from ..utils.correspondence_utils import (
    detect_keyframe_range,
    collect_strokes_2d,
    to_cpp_strokes
)

_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_constraints = []
_stable_stroke_ids = {}


def get_state():
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


    if key not in stable_stroke_ids or len(stable_stroke_ids[key]) != num_strokes:
        stable_stroke_ids[key] = {i: i for i in range(num_strokes)}
        set_state(stable_stroke_ids=stable_stroke_ids)

    return stable_stroke_ids[key]


def run_correspondence_match(gp_obj, layer_idx, frame1, frame2, config):
    try:
        import gp_autointerpolate
    except ImportError as e:
        return (False, [], f"gp_autointerpolate module not found: {e}")

    try:
        state = get_state()
        link_constraints = state['link_constraints']


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
        cfg.debug = False


        seeds = []

        lookup_frame1, lookup_frame2 = (frame1, frame2) if frame1 < frame2 else (frame2, frame1)
        swap_order = (frame1 > frame2)


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


                if stable_id1 in stable_to_current1 and stable_id2 in stable_to_current2:
                    current_idx1 = stable_to_current1[stable_id1]
                    current_idx2 = stable_to_current2[stable_id2]

                    try:
                        idx1 = indices1.index(current_idx1)
                        idx2 = indices2.index(current_idx2)
                        seeds.append((idx1, idx2))
                    except ValueError:
                        pass


        S1 = to_cpp_strokes(s1)
        S2 = to_cpp_strokes(s2)

        matcher = gp_autointerpolate.StrokeMatcher(cfg)


        if seeds:
            result = matcher.match_with_seeds(S1, S2, seeds)
        else:
            result = matcher.match(S1, S2)

        raw_matches = result.get_matches()


        result_matches = [(indices1[i], indices2[j]) for i, j in raw_matches]


        if frame1 < frame2:
            ref_frame, reorder_frame = frame1, frame2
            swap_match = False
        else:
            ref_frame, reorder_frame = frame2, frame1
            swap_match = True


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


        new_indices = list(range(num_strokes))
        assigned_positions = set()
        used_old_strokes = set()


        for ref_idx, reorder_idx in result_matches:
            if swap_match:
                ref_idx, reorder_idx = reorder_idx, ref_idx

            if ref_idx < num_strokes and reorder_idx < num_strokes:
                new_indices[ref_idx] = reorder_idx
                assigned_positions.add(ref_idx)
                used_old_strokes.add(reorder_idx)


        remaining_old = [i for i in range(num_strokes) if i not in used_old_strokes]
        remaining_positions = [i for i in range(num_strokes) if i not in assigned_positions]

        for pos, old_stroke in zip(remaining_positions, remaining_old):
            new_indices[pos] = old_stroke

        # Apply reorder
        drawing.reorder_strokes(new_indices=new_indices)


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
        set_state(match_job_running=False, viewport_context={})
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
    state = get_state()

    if state['match_job_running']:
        return (False, None)


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


    bpy.app.timers.register(run_match_job_step)

    return (True, camera_info)

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


            set_state(show_linked_overlay=True)
            linked_stroke_overlay.manage_draw_handler()


            bpy.ops.object.mode_set(mode='EDIT')


            bpy.ops.grease_pencil.set_selection_mode(mode='STROKE')


            context.scene.tool_settings.use_grease_pencil_multi_frame_editing = True


            active_layer = obj.data.layers.active
            layer = active_layer if active_layer else obj.data.layers[0]
            frame_start, frame_end = detect_keyframe_range(context.scene, layer)


            for frame in layer.frames:
                frame.select = False  # Deselect all first


            for frame in layer.frames:
                if frame.frame_number == frame_start or frame.frame_number == frame_end:
                    frame.select = True


            pass


            for layer in obj.data.layers:
                for frame in layer.frames:
                    if frame.drawing:
                        for stroke in frame.drawing.strokes:
                            stroke.select = False

        else:
            # Deactivate link mode
            set_state(link_mode_active=False)


            set_state(show_linked_overlay=False)
            linked_stroke_overlay.manage_draw_handler()

            # Deselect keyframes
            if obj and obj.type == 'GREASEPENCIL':
                for layer in obj.data.layers:
                    for frame in layer.frames:
                        frame.select = False


            context.scene.tool_settings.use_grease_pencil_multi_frame_editing = False


            for layer in obj.data.layers:
                for frame in layer.frames:
                    if frame.drawing:
                        for stroke in frame.drawing.strokes:
                            stroke.select = False


            bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')


            pass

        return {'FINISHED'}

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


        selected_by_frame = {}

        for layer_idx, layer in enumerate(obj.data.layers):
            for frame in layer.frames:
                if not frame.drawing:
                    continue

                selected_strokes = []
                for stroke_idx, stroke in enumerate(frame.drawing.strokes):
                    if stroke.select:
                        selected_strokes.append(stroke_idx)

                if selected_strokes:
                    selected_by_frame[(layer_idx, frame.frame_number)] = selected_strokes


        if len(selected_by_frame) != 2:
            self.report({'WARNING'}, "Select exactly one stroke in each of two frames")
            return {'CANCELLED'}

        frames_list = list(selected_by_frame.items())
        (layer1, frame1), strokes1 = frames_list[0]
        (layer2, frame2), strokes2 = frames_list[1]

        if layer1 != layer2:
            self.report({'WARNING'}, "Selected strokes must be on the same layer")
            return {'CANCELLED'}

        if len(strokes1) != 1 or len(strokes2) != 1:
            self.report({'WARNING'}, "Select exactly one stroke per frame")
            return {'CANCELLED'}

        stroke1_idx = strokes1[0]
        stroke2_idx = strokes2[0]


        if frame1 < frame2:
            norm_frame1, norm_stroke1 = frame1, stroke1_idx
            norm_frame2, norm_stroke2 = frame2, stroke2_idx
        else:
            norm_frame1, norm_stroke1 = frame2, stroke2_idx
            norm_frame2, norm_stroke2 = frame1, stroke1_idx


        stable_ids1 = ensure_stable_ids(obj, layer1, norm_frame1)
        stable_ids2 = ensure_stable_ids(obj, layer1, norm_frame2)


        stable_id1 = stable_ids1.get(norm_stroke1, norm_stroke1)
        stable_id2 = stable_ids2.get(norm_stroke2, norm_stroke2)


        constraint = (layer1, norm_frame1, stable_id1, norm_frame2, stable_id2)
        link_constraints = get_state()['link_constraints']

        if constraint not in link_constraints:
            link_constraints.append(constraint)
            set_state(link_constraints=link_constraints)




            pairs = [(norm_frame1, norm_frame2)]


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


            config = {
                'max_alpha': 0.5,
                'coincident_threshold': 0.5,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Linked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            self.report({'INFO'}, "This pair is already linked")

        bpy.ops.grease_pencil.select_all(action='DESELECT')

        return {'FINISHED'}

class GPCORR_OT_clear_all_links(Operator):
    bl_idname = "gpcorr.clear_all_links"
    bl_label = "Clear All Links"
    bl_description = "Remove all manual link constraints"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        state = get_state()

        return state['link_mode_active'] and len(state['link_constraints']) > 0

    def invoke(self, context, event):
        link_constraints = get_state()['link_constraints']
        count = len(link_constraints)


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
                if not frame.drawing:
                    continue
                sel = [i for i, s in enumerate(frame.drawing.strokes) if s.select]
                if sel:
                    selected_by_frame[(layer_idx, frame.frame_number)] = sel

        if len(selected_by_frame) != 2:
            self.report({'WARNING'}, "Select exactly one stroke in each of two frames")
            return {'CANCELLED'}

        (layer1, frame1), strokes1 = list(selected_by_frame.items())[0]
        (layer2, frame2), strokes2 = list(selected_by_frame.items())[1]

        if layer1 != layer2 or len(strokes1) != 1 or len(strokes2) != 1:
            self.report({'WARNING'}, "Selection must be one stroke per frame on the same layer")
            return {'CANCELLED'}

        stroke1_idx = strokes1[0]
        stroke2_idx = strokes2[0]


        if frame1 < frame2:
            norm_frame1, norm_stroke1 = frame1, stroke1_idx
            norm_frame2, norm_stroke2 = frame2, stroke2_idx
        else:
            norm_frame1, norm_stroke1 = frame2, stroke2_idx
            norm_frame2, norm_stroke2 = frame1, stroke1_idx


        stable_ids1 = ensure_stable_ids(obj, layer1, norm_frame1)
        stable_ids2 = ensure_stable_ids(obj, layer1, norm_frame2)
        stable_id1 = stable_ids1.get(norm_stroke1, norm_stroke1)
        stable_id2 = stable_ids2.get(norm_stroke2, norm_stroke2)


        constraint = (layer1, norm_frame1, stable_id1, norm_frame2, stable_id2)

        link_constraints = get_state()['link_constraints']
        before = len(link_constraints)
        new_constraints = [c for c in link_constraints if c != constraint]
        set_state(link_constraints=new_constraints)
        after = len(new_constraints)

        bpy.ops.grease_pencil.select_all(action='DESELECT')

        if after < before:
            self.report({'INFO'}, "Unlinked selected pair")


            layer = obj.data.layers[layer1]
            pairs = [(norm_frame1, norm_frame2)]


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


            config = {
                'max_alpha': 0.5,
                'coincident_threshold': 0.5,
            }
            success, _ = start_match_job(obj, layer1, pairs, config)
            if success:
                self.report({'INFO'}, f"Unlinked strokes on frames {norm_frame1}-{norm_frame2}")
        else:
            self.report({'INFO'}, "Selected pair was not linked")

        return {'FINISHED'}

classes = (
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
