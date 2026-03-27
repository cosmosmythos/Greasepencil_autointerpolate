"""Refresh Cache Operator"""

import bpy
from bpy.types import Operator
from ..core import cache


class GP_RefreshInterpolation(Operator):
    bl_idname = "gp.refresh_interpolation"
    bl_label = "Refresh Cache"
    bl_description = "Refresh interpolation cache"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and
                context.scene.gp_interpolation_enabled)

    def execute(self, context):
        gp_obj = context.active_object
        cache.ensure_modifier(gp_obj)
        cache.clear()
        cache.build(gp_obj)
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, "Interpolation cache refreshed")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_RefreshInterpolation)


def unregister():
    bpy.utils.unregister_class(GP_RefreshInterpolation)