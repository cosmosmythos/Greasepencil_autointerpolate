"""
Toggle Interpolation Operator for GP Auto Interpolate
"""

import bpy
from bpy.types import Operator
from ..core import cache
from ..utils import visibility


class GP_ToggleInterpolation(Operator):
    bl_idname = "gp.toggle_interpolation"
    bl_label = "Interpolation"
    bl_description = "Toggle real-time interpolation processing"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'GREASEPENCIL'

    def execute(self, context):
        scene = context.scene
        gp_obj = context.active_object

        scene.gp_interpolation_enabled = not scene.gp_interpolation_enabled

        if scene.gp_interpolation_enabled:
            cache.ensure_modifier(gp_obj)
            cache.build(gp_obj)
            scene["gp_interpolation_target"] = gp_obj.name

            if visibility.on_frame_change not in bpy.app.handlers.frame_change_post:
                bpy.app.handlers.frame_change_post.append(visibility.on_frame_change)
            if visibility.on_undo_redo not in bpy.app.handlers.undo_post:
                bpy.app.handlers.undo_post.append(visibility.on_undo_redo)
            if visibility.on_undo_redo not in bpy.app.handlers.redo_post:
                bpy.app.handlers.redo_post.append(visibility.on_undo_redo)

            visibility.update_modifier_visibility()
        else:
            try:
                if visibility.on_frame_change in bpy.app.handlers.frame_change_post:
                    bpy.app.handlers.frame_change_post.remove(visibility.on_frame_change)
                if visibility.on_undo_redo in bpy.app.handlers.undo_post:
                    bpy.app.handlers.undo_post.remove(visibility.on_undo_redo)
                if visibility.on_undo_redo in bpy.app.handlers.redo_post:
                    bpy.app.handlers.redo_post.remove(visibility.on_undo_redo)
            except (ValueError, AttributeError):
                pass

            visibility.force_modifier_off_for_authoring()
            visibility.clear()
            cache.clear()
            scene["gp_interpolation_target"] = ""

        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_ToggleInterpolation)


def unregister():
    bpy.utils.unregister_class(GP_ToggleInterpolation)