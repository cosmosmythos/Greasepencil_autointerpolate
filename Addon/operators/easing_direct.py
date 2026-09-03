import bpy
from bpy.types import Operator
from bpy.props import EnumProperty
from ..utils import easing
from ..utils.easing import get_layer_id_readonly, get_easing_curve_node, apply_control_points_to_curve
from ..core import cache


def apply_preset_to_curve(preset_name, stored_data=None):
    curve_node = get_easing_curve_node()
    if not curve_node:
        return

    curve_mapping = curve_node.mapping
    curve = curve_mapping.curves[0]

    if preset_name == 'CUSTOM' and stored_data:
        if isinstance(stored_data, list) and len(stored_data) > 0:
            if isinstance(stored_data[0], dict):
                apply_control_points_to_curve(curve, curve_mapping, stored_data)
            else:
                curve.points[0].location = (0.0, stored_data[0])
                curve.points[-1].location = (1.0, stored_data[-1])
                for i in [8, 16, 24, 32, 40, 48, 56]:
                    if i < len(stored_data):
                        curve.points.new(i / 63.0, stored_data[i]).handle_type = 'AUTO_CLAMPED'
    else:
        while len(curve.points) > 2:
            curve.points.remove(curve.points[1])
        if preset_name == 'LINEAR':
            curve.points[0].handle_type = 'VECTOR'
            curve.points[-1].handle_type = 'VECTOR'
        elif preset_name == 'EASE_IN':
            curve.points[0].handle_type = 'AUTO'
            curve.points[-1].handle_type = 'AUTO'
            curve.points.new(0.5, 0.25).handle_type = 'AUTO_CLAMPED'
        elif preset_name == 'EASE_OUT':
            curve.points[0].handle_type = 'AUTO'
            curve.points[-1].handle_type = 'AUTO'
            curve.points.new(0.5, 0.75).handle_type = 'AUTO_CLAMPED'
        elif preset_name == 'EASE_IN_OUT':
            curve.points[0].handle_type = 'AUTO'
            curve.points[-1].handle_type = 'AUTO'
            curve.points.new(0.25, 0.1).handle_type = 'AUTO_CLAMPED'
            curve.points.new(0.75, 0.9).handle_type = 'AUTO_CLAMPED'

    curve_mapping.update()

    # guard - dopesheet popup no longer draws curve (buttons only), but N-panel does
    try:
        for window in list(bpy.context.window_manager.windows):
            screen = getattr(window, "screen", None)
            if not screen:
                continue
            for area in list(screen.areas):
                try:
                    if getattr(area, "type", None) in {'VIEW_3D', 'DOPESHEET_EDITOR', 'PROPERTIES'}:
                        area.tag_redraw()
                except ReferenceError:
                    continue
    except Exception:
        pass


def get_stored_easing_data(gp_data, layer_idx, frame_number):
    import json
    from ..utils.easing import get_or_create_layer_id

    if "gp_easing_data" not in gp_data:
        return None, None

    try:
        all_easing = json.loads(gp_data["gp_easing_data"])
        layer_id = get_layer_id_readonly(gp_data, layer_idx)
        if layer_id is None:
            return None, None
        layer_key = str(layer_id)

        if layer_key in all_easing:
            for uuid, data in all_easing[layer_key].items():
                if data.get('frame') == frame_number:
                    preset = data.get('preset', 'LINEAR')
                    control_points = data.get('control_points') if preset == 'CUSTOM' else None
                    if control_points is None and preset == 'CUSTOM':
                        control_points = data.get('samples')
                    return preset, control_points
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return None, None


def get_target_keyframes(context):
    selected = easing.get_selected_keyframes(context)
    if selected:
        return selected


    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return []

    gp_data = gp_obj.data
    if not gp_data.layers.active:
        return []

    active_layer = gp_data.layers.active
    layer_idx = next((idx for idx, layer in enumerate(gp_data.layers) if layer == active_layer), None)
    if layer_idx is None:
        return []

    current_frame = context.scene.frame_current
    prev_key = max((f.frame_number for f in active_layer.frames if f.frame_number <= current_frame), default=None)
    if prev_key is not None:
        return [(layer_idx, prev_key)]
    return []


class GP_OT_ApplyEasingDirect(Operator):
    bl_idname = "gp.apply_easing_direct"
    bl_label = "Apply Easing"
    bl_description = "Apply easing type to selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    easing_type: EnumProperty(
        name="Type",
        items=[
            ('LINEAR', "Linear", "Linear interpolation"),
            ('EASE_IN', "Ease In", "Slow start, fast end"),
            ('EASE_OUT', "Ease Out", "Fast start, slow end"),
            ('EASE_IN_OUT', "Ease In-Out", "Slow start and end, fast middle"),
            ('CUSTOM', "Custom", "Use custom curve"),
        ],
        default='LINEAR'
    )

    @classmethod
    def poll(cls, context):
        if not context.active_object or context.active_object.type != 'GREASEPENCIL':
            return False
        return len(get_target_keyframes(context)) > 0

    def execute(self, context):
        gp_obj = context.active_object
        if not gp_obj:
            return {'CANCELLED'}

        selected_keys = get_target_keyframes(context)
        if not selected_keys:
            return {'CANCELLED'}

        layer_idx, frame_num = selected_keys[0]
        layer = gp_obj.data.layers[layer_idx]
        current_preset, stored_data = get_stored_easing_data(gp_obj.data, layer_idx, frame_num)

        from ..core.npanel_handlers import set_loading_flag

        if self.easing_type == 'CUSTOM':
            set_loading_flag(True)
            try:
                if current_preset == 'CUSTOM' and stored_data:
                    apply_preset_to_curve('CUSTOM', stored_data)
                else:
                    for lidx, fnum in selected_keys:
                        lyr = gp_obj.data.layers[lidx]
                        easing.set_easing_curve_to_frame(gp_obj.data, lyr, lidx, fnum, 'CUSTOM')

                if context.scene.gp_interpolation_enabled:
                    cache.clear(gp_obj.name)
                    cache.build(gp_obj)
            finally:
                set_loading_flag(False)
        else:
            set_loading_flag(True)
            try:
                apply_preset_to_curve(self.easing_type)
                for lidx, fnum in selected_keys:
                    lyr = gp_obj.data.layers[lidx]
                    easing.set_easing_curve_to_frame(gp_obj.data, lyr, lidx, fnum, self.easing_type)

                if context.scene.gp_interpolation_enabled:
                    cache.clear(gp_obj.name)
                    cache.build(gp_obj)
            finally:
                set_loading_flag(False)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_OT_ApplyEasingDirect)


def unregister():
    bpy.utils.unregister_class(GP_OT_ApplyEasingDirect)
