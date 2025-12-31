"""
Easing Popup Operator
"""

import bpy
import json
from bpy.types import Operator
from bpy.props import EnumProperty
from ..utils import easing
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
        ],
        default='LINEAR'
    )

    @classmethod
    def poll(cls, context):
        if not context.active_object or context.active_object.type != 'GREASEPENCIL':
            return False
        selected_keys = easing.get_selected_keyframes(context)
        return len(selected_keys) > 0

    def invoke(self, context, event):
        gp_obj = context.active_object
        selected_keys = easing.get_selected_keyframes(context)
        
        if selected_keys and gp_obj:
            layer_idx, frame_num = selected_keys[0]
            if "gp_easing_data" in gp_obj.data:
                try:
                    all_easing = json.loads(gp_obj.data["gp_easing_data"])
                    preset = all_easing.get(str(layer_idx), {}).get(str(frame_num), 'LINEAR')
                    self.easing_type = preset
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        
        return context.window_manager.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        
        # Easing type as toggle buttons (2x2 grid)
        layout.label(text="Easing Type:")
        
        # First row: Linear, Ease In
        row1 = layout.row(align=True)
        row1.prop_enum(self, "easing_type", 'LINEAR', text="Linear")
        row1.prop_enum(self, "easing_type", 'EASE_IN', text="In")
        
        # Second row: Ease Out, Ease In-Out
        row2 = layout.row(align=True)
        row2.prop_enum(self, "easing_type", 'EASE_OUT', text="Out")
        row2.prop_enum(self, "easing_type", 'EASE_IN_OUT', text="In-Out")

    def execute(self, context):
        gp_obj = context.active_object
        if not gp_obj:
            return {'CANCELLED'}
        
        selected_keys = easing.get_selected_keyframes(context)
        
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
