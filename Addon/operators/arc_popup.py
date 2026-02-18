"""
Arc Settings Popup Operator
Allows setting arc trajectory parameters for selected keyframes.
"""

import bpy
from bpy.types import Operator
from bpy.props import FloatProperty, EnumProperty
from ..utils import arc_data, easing
from ..core import cache


class GP_OT_ShowArcPopup(Operator):
    """Set arc trajectory parameters for selected keyframes"""
    bl_idname = "gp.show_arc_popup"
    bl_label = "Arc Settings"
    bl_description = "Set arc trajectory parameters for selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    # Combined arc slider: -1 to +1
    # 0 = linear, positive = arc one way, negative = arc other way
    arc_curve: FloatProperty(
        name="Arc Curve",
        description="Arc trajectory: 0 = linear, ±1 = full arc curve",
        default=0.0,
        min=-1.0,
        max=1.0,
        subtype='FACTOR'
    )

    arc_type: EnumProperty(
        name="Arc Type",
        description="Type of arc interpolation",
        items=[
            ('BEZIER', "Bezier", "Quadratic bezier arc (simple, predictable)"),
            ('SPIRAL', "Spiral", "Logarithmic spiral (natural rotation paths)"),
        ],
        default='BEZIER'  # Bezier is now default
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
            layer = gp_obj.data.layers[layer_idx]
            
            params = arc_data.get_arc_params_from_frame(
                gp_obj.data, layer_idx, frame_num, layer
            )
            # Convert old format (arc_amount, arc_direction) to new arc_curve
            arc_amount = params[0]
            arc_direction = params[1]
            # Combine: arc_curve = arc_amount * arc_direction (preserves sign)
            self.arc_curve = arc_amount * arc_direction if arc_amount > 0 else 0.0
            self.arc_type = 'SPIRAL' if params[3] else 'BEZIER'
        
        return context.window_manager.invoke_props_popup(self, event)

    def draw(self, context):
        layout = self.layout
        
        # Arc Type toggle buttons (Bezier first)
        layout.label(text="Arc Type:")
        row = layout.row(align=True)
        row.prop_enum(self, "arc_type", 'BEZIER', text="Bezier")
        row.prop_enum(self, "arc_type", 'SPIRAL', text="Spiral")
        
        layout.separator()
        
        # Single combined arc slider
        layout.prop(self, "arc_curve", slider=True)
        
        # Visual hint
        if abs(self.arc_curve) < 0.01:
            layout.label(text="Linear path", icon='FORWARD')
        elif self.arc_curve > 0:
            layout.label(text="Curves right", icon='SPHERECURVE')
        else:
            layout.label(text="Curves left", icon='SPHERECURVE')

    def execute(self, context):
        gp_obj = context.active_object
        if not gp_obj:
            return {'CANCELLED'}
        
        selected_keys = easing.get_selected_keyframes(context)
        use_spiral = (self.arc_type == 'SPIRAL')
        
        # Convert arc_curve back to (arc_amount, arc_direction) for storage
        arc_amount = abs(self.arc_curve)
        arc_direction = 1.0 if self.arc_curve >= 0 else -1.0
        
        for layer_idx, frame_num in selected_keys:
            layer = gp_obj.data.layers[layer_idx]
            arc_data.set_arc_params_to_frame(
                gp_obj.data, layer, layer_idx, frame_num,
                arc_amount,
                arc_direction,
                0.0,
                use_spiral
            )
        
        if context.scene.gp_interpolation_enabled:
            cache.clear()
            cache.build(gp_obj)
        
        self.report({'INFO'}, f"Arc settings applied to {len(selected_keys)} keyframe(s)")
        return {'FINISHED'}


def register():
    try:
        bpy.utils.unregister_class(GP_OT_ShowArcPopup)
    except RuntimeError:
        pass
    bpy.utils.register_class(GP_OT_ShowArcPopup)


def unregister():
    try:
        bpy.utils.unregister_class(GP_OT_ShowArcPopup)
    except RuntimeError:
        pass
