"""
Refresh Cache Operator
"""

import bpy
from bpy.types import Operator
from ..core import cache


class GP_RefreshInterpolation(Operator):
    bl_idname = "gp.refresh_interpolation"
    bl_label = "Refresh Cache"
    bl_description = "Refresh interpolation cache"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and 
                context.active_object.type == 'GREASEPENCIL' and
                context.scene.gp_interpolation_enabled)

    def execute(self, context):
        cache.clear()
        gp_obj = context.active_object
        if gp_obj:
            cache.build(gp_obj)
            self.report({'INFO'}, "Interpolation cache refreshed")
        return {'FINISHED'}


def register():
    try:
        bpy.utils.register_class(GP_RefreshInterpolation)
    except ValueError:
        # Class already registered, skip
        pass


def unregister():
    try:
        bpy.utils.unregister_class(GP_RefreshInterpolation)
    except (ValueError, RuntimeError):
        # Class not registered or already unregistered, skip
        pass
