
import bpy
from bpy.types import Operator
from ..core import cache
from ..core.registry import get_targets, set_targets, is_object_enabled
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
        targets = get_targets(scene)

        if gp_obj.name in targets:

            targets.discard(gp_obj.name)
            cache.clear(gp_obj.name)
            visibility.force_modifier_off_for_object(gp_obj)
        else:

            targets.add(gp_obj.name)
            cache.ensure_modifier(gp_obj)
            cache.build(gp_obj)

        set_targets(scene, targets)

        # Derive master switch
        scene.gp_interpolation_enabled = len(targets) > 0


        if targets:
            scene["gp_interpolation_target"] = gp_obj.name
        else:
            scene["gp_interpolation_target"] = ""

        if scene.gp_interpolation_enabled:

            if visibility.on_frame_change not in bpy.app.handlers.frame_change_post:
                bpy.app.handlers.frame_change_post.append(visibility.on_frame_change)
            if visibility.on_undo_redo not in bpy.app.handlers.undo_post:
                bpy.app.handlers.undo_post.append(visibility.on_undo_redo)
            if visibility.on_undo_redo not in bpy.app.handlers.redo_post:
                bpy.app.handlers.redo_post.append(visibility.on_undo_redo)
            if visibility.on_render_pre not in bpy.app.handlers.render_pre:
                bpy.app.handlers.render_pre.append(visibility.on_render_pre)
            if visibility.on_render_post not in bpy.app.handlers.render_post:
                bpy.app.handlers.render_post.append(visibility.on_render_post)
            if visibility.on_render_post not in bpy.app.handlers.render_cancel:
                bpy.app.handlers.render_cancel.append(visibility.on_render_post)

            visibility.update_modifier_visibility()
        else:

            try:
                if visibility.on_frame_change in bpy.app.handlers.frame_change_post:
                    bpy.app.handlers.frame_change_post.remove(visibility.on_frame_change)
                if visibility.on_undo_redo in bpy.app.handlers.undo_post:
                    bpy.app.handlers.undo_post.remove(visibility.on_undo_redo)
                if visibility.on_undo_redo in bpy.app.handlers.redo_post:
                    bpy.app.handlers.redo_post.remove(visibility.on_undo_redo)
                if visibility.on_render_pre in bpy.app.handlers.render_pre:
                    bpy.app.handlers.render_pre.remove(visibility.on_render_pre)
                if visibility.on_render_post in bpy.app.handlers.render_post:
                    bpy.app.handlers.render_post.remove(visibility.on_render_post)
                if visibility.on_render_post in bpy.app.handlers.render_cancel:
                    bpy.app.handlers.render_cancel.remove(visibility.on_render_post)
            except (ValueError, AttributeError):
                pass

            visibility.force_all_modifiers_off()
            visibility.clear()
            cache.clear()

        return {'FINISHED'}


def register():
    bpy.utils.register_class(GP_ToggleInterpolation)


def unregister():
    bpy.utils.unregister_class(GP_ToggleInterpolation)
