import bpy
from bpy.types import Panel
from ..utils.easing import get_easing_curve_node
from ..operators.easing_direct import get_stored_easing_data
from ..core.registry import is_object_enabled


def get_current_keyframe_at_playhead(context):
    from ..core.npanel_handlers import resolve_preview_key

    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return None, None, None

    gp_data = context.active_object.data
    active_layer = gp_data.layers.active
    if not active_layer:
        return None, None, None

    layer_idx, frame_num = resolve_preview_key(context)
    if layer_idx is None:
        # graceful: panel needs layer even without key
        layer_idx_only = next(
            (i for i, l in enumerate(gp_data.layers) if l == active_layer),
            None,
        )
        return None, layer_idx_only, active_layer

    return frame_num, layer_idx, active_layer


EASING_LABELS = {
    'LINEAR': 'Linear', 'EASE_IN': 'Ease In', 'EASE_OUT': 'Ease Out',
    'EASE_IN_OUT': 'Ease In-Out', 'CUSTOM': 'Custom',
}


class VIEW3D_PT_gp_auto_interpolate(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GPAI'
    bl_label = "GP Auto Interpolate"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'GREASEPENCIL'

    def draw_header(self, context):
        self.layout.label(text="", icon='GP_SELECT_STROKES')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        gp_obj = context.active_object
        gp_data = gp_obj.data
        enabled = scene.gp_interpolation_enabled
        obj_enabled = is_object_enabled(scene, gp_obj.name)

        # Main Controls
        box = layout.box()
        row = box.row(align=True)
        icon = 'RECORD_ON' if obj_enabled else 'RENDER_ANIMATION'
        row.operator("gp.toggle_interpolation", text="", icon=icon, depress=obj_enabled)
        sub = row.row(align=True)
        sub.enabled = obj_enabled
        sub.operator("gp.refresh_interpolation", text="", icon='FILE_REFRESH')
        sub.operator("gp.layer_filter_popup", text="", icon='DECORATE_LOCKED')
        sub.operator("gp.show_arc_popup", text="", icon='FORCE_CURVE')
        sub.operator("gp.bake_single", text="", icon='KEY_HLT')
        sub.operator("gp.bake_selected_range", text="", icon='GREASEPENCIL_LAYER_GROUP')
        sub.separator()
        sub.prop(scene, "gp_bake_step", text="")

        # Easing Section
        current_key, layer_idx, active_layer = get_current_keyframe_at_playhead(context)


        current_easing = 'LINEAR'
        if layer_idx is not None and current_key is not None:
            stored_preset, _ = get_stored_easing_data(gp_data, layer_idx, current_key)
            if stored_preset:
                current_easing = stored_preset
        easing_label = EASING_LABELS.get(current_easing, 'Linear')

        box2 = layout.box()
        col = box2.column(align=True)



        row_layer = col.row(align=True)
        if active_layer:
            name = active_layer.name[:12] if len(active_layer.name) > 12 else active_layer.name
            row_layer.label(text=name, icon='OUTLINER_DATA_GP_LAYER')
        else:
            row_layer.label(text="No Layer", icon='OUTLINER_DATA_GP_LAYER')


        row_key = col.row(align=True)
        if current_key is not None:
            row_key.label(text=f"KEY {current_key}", icon='KEYFRAME_HLT')
        else:
            row_key.label(text="No Key", icon='KEYFRAME')
        row_key.label(text=f"Easing: {easing_label}")

        # Easing Buttons
        row3 = col.row(align=True)
        row3.enabled = obj_enabled and current_key is not None
        row3.scale_y = 0.9
        for easing_id, icon in [('LINEAR', 'IPO_LINEAR'), ('EASE_IN', 'IPO_EASE_IN'),
                                 ('EASE_OUT', 'IPO_EASE_OUT'), ('EASE_IN_OUT', 'IPO_EASE_IN_OUT'),
                                 ('CUSTOM', 'IPO_BEZIER')]:
            op = row3.operator("gp.apply_easing_direct", text="", icon=icon, depress=(current_easing == easing_id))
            op.easing_type = easing_id

        # Curve Graph
        curve_node = get_easing_curve_node()
        if curve_node:
            col.template_curve_mapping(curve_node, "mapping", type='NONE')


def register():
    bpy.utils.register_class(VIEW3D_PT_gp_auto_interpolate)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_gp_auto_interpolate)
