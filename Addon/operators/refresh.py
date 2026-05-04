"""Refresh Cache Operator"""

import bpy
from bpy.types import Operator
from ..core import cache
from ..core.registry import is_object_enabled


class GP_RefreshInterpolation(Operator):
    bl_idname = "gp.refresh_interpolation"
    bl_label = "Refresh Cache"
    bl_description = "Refresh interpolation cache"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        gp_obj = context.active_object
        return bool(
            gp_obj and
            gp_obj.type == 'GREASEPENCIL' and
            context.scene.gp_interpolation_enabled and
            is_object_enabled(context.scene, gp_obj.name)
        )

    def execute(self, context):
        gp_obj = context.active_object
        if (not gp_obj or gp_obj.type != 'GREASEPENCIL' or
                not is_object_enabled(context.scene, gp_obj.name)):
            self.report({'WARNING'}, "Active Grease Pencil object is not enabled for interpolation")
            return {'CANCELLED'}

        try:
            cache.ensure_modifier(gp_obj)
            cache.clear(gp_obj.name)
            cache.build(gp_obj)
        except Exception as exc:
            self.report({'ERROR'}, f"Refresh failed: {exc}")
            return {'CANCELLED'}

        screen = getattr(context, "screen", None)
        if screen:
            for area in screen.areas:
                area.tag_redraw()

        self.report({'INFO'}, "Interpolation cache refreshed")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_RefreshInterpolation)


def unregister():
    bpy.utils.unregister_class(GP_RefreshInterpolation)
