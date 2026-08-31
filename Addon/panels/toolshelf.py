import bpy
from bpy.types import Operator, Panel


class GP_OT_bezierfit(Operator):
    bl_idname = "gp.bezier_fit"
    bl_label = "Bezier Fit"
    bl_description = ""
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return {'FINISHED'}


class VIEW3D_PT_gpai_t_shelf(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = ""

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'GREASEPENCIL':
            return False
        allowed = {
            'PAINT_GPENCIL', 'EDIT_GPENCIL', 'SCULPT_GPENCIL',
            'PAINT_GREASE_PENCIL', 'EDIT_GREASE_PENCIL', 'SCULPT_GREASE_PENCIL',
            'VERTEX_GREASE_PENCIL', 'WEIGHT_GREASE_PENCIL', 'OBJECT',
        }
        return context.mode in allowed or 'GREASE_PENCIL' in context.mode or 'GPENCIL' in context.mode

    def draw(self, context):
        layout = self.layout
        layout.operator("gp.bezier_fit", text="Bezier Fit", icon='CURVE_BEZCURVE')


def register():
    bpy.utils.register_class(GP_OT_bezierfit)
    bpy.utils.register_class(VIEW3D_PT_gpai_t_shelf)


def unregister():
    try:
        bpy.utils.unregister_class(VIEW3D_PT_gpai_t_shelf)
    except RuntimeError:
        pass
    try:
        bpy.utils.unregister_class(GP_OT_bezierfit)
    except RuntimeError:
        pass
