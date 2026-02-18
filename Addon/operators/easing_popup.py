"""
Easing Popup Operator
"""

import bpy
from bpy.types import Operator
from bpy.props import EnumProperty
from ..utils import easing
from ..utils.easing import get_easing_curve_node
from ..core import cache


class GP_OT_ShowEasingPopup(Operator):
    """Set easing type for selected keyframes"""
    bl_idname = "gp.show_easing_popup"
    bl_label = "Easing"
    bl_description = "Set easing type for selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    easing_type: EnumProperty(
        name="Type",
        description="Easing curve type",
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
        from ..operators.easing_direct import get_target_keyframes
        return len(get_target_keyframes(context)) > 0

    def invoke(self, context, event):
        gp_obj = context.active_object
        from ..operators.easing_direct import get_target_keyframes
        selected_keys = get_target_keyframes(context)
        
        if selected_keys and gp_obj:
            layer_idx, frame_num = selected_keys[0]
            from ..operators.easing_direct import get_stored_easing_data
            preset, _ = get_stored_easing_data(gp_obj.data, layer_idx, frame_num)
            if preset:
                self.easing_type = preset
        
        return context.window_manager.invoke_props_popup(self, event)

    def draw(self, context):
        layout = self.layout
        
        # Easing presets as buttons
        col = layout.column(align=True)
        
        # Row 1: Linear, Custom (most used)
        row1 = col.row(align=True)
        row1.prop_enum(self, "easing_type", 'LINEAR', text="Linear")
        row1.prop_enum(self, "easing_type", 'CUSTOM', text="Custom")
        
        # Row 2: Ease In, Ease Out, Ease In-Out
        row2 = col.row(align=True)
        row2.prop_enum(self, "easing_type", 'EASE_IN', text="In")
        row2.prop_enum(self, "easing_type", 'EASE_OUT', text="Out")
        row2.prop_enum(self, "easing_type", 'EASE_IN_OUT', text="In-Out")
        
        # Show curve editor when Custom is selected
        if self.easing_type == 'CUSTOM':
            layout.separator()
            curve_node = get_easing_curve_node()
            if curve_node:
                layout.template_curve_mapping(curve_node, "mapping", type='NONE')
            else:
                layout.label(text="Curve not available", icon='ERROR')
                layout.label(text="Enable interpolation first")

    def execute(self, context):
        gp_obj = context.active_object
        if not gp_obj:
            return {'CANCELLED'}
        
        from ..operators.easing_direct import get_target_keyframes
        selected_keys = get_target_keyframes(context)
        
        for layer_idx, frame_num in selected_keys:
            layer = gp_obj.data.layers[layer_idx]
            easing.set_easing_curve_to_frame(gp_obj.data, layer, layer_idx, frame_num, self.easing_type)
        
        if context.scene.gp_interpolation_enabled:
            cache.clear()
            cache.build(gp_obj)

        return {'FINISHED'}


def register():
    try:
        bpy.utils.unregister_class(GP_OT_ShowEasingPopup)
    except RuntimeError:
        pass
    bpy.utils.register_class(GP_OT_ShowEasingPopup)


def unregister():
    try:
        bpy.utils.unregister_class(GP_OT_ShowEasingPopup)
    except RuntimeError:
        pass
