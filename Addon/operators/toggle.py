"""
Toggle Interpolation Operator (robust, minimal)
"""

import bpy
from bpy.types import Operator
from ..core import cache
from ..utils import visibility


class GP_ToggleInterpolation(Operator):
    bl_idname = "gp.toggle_interpolation"
    bl_label = "Interpolation"
    bl_description = "Toggle real-time interpolation processing"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object and context.active_object.type == 'GREASEPENCIL')

    def execute(self, context):
        scene = context.scene
        gp_obj = context.active_object

        scene.gp_interpolation_enabled = not scene.gp_interpolation_enabled

        if scene.gp_interpolation_enabled:
            # Enable: build cache, set target, add handler, start with proper visibility management
            cache.build(gp_obj)
            scene["gp_interpolation_target"] = gp_obj.name

            if visibility.on_frame_change not in bpy.app.handlers.frame_change_post:
                bpy.app.handlers.frame_change_post.append(visibility.on_frame_change)

            # Initialize visibility system properly
            visibility.update_modifier_visibility()
        else:
            # Disable: clean shutdown with proper state cleanup
            try:
                if visibility.on_frame_change in bpy.app.handlers.frame_change_post:
                    bpy.app.handlers.frame_change_post.remove(visibility.on_frame_change)
            except Exception:
                pass

            # Stop scrub timer and clean visibility state
            visibility.stop_scrub_timer()
            
            # Ensure modifier is turned off
            try:
                visibility._set_modifier_visible(False)
            except Exception:
                pass

            # Clear all state
            visibility.clear()
            cache.clear()
            scene["gp_interpolation_target"] = ""

        return {'FINISHED'}


def register():
    try:
        bpy.utils.register_class(GP_ToggleInterpolation)
    except ValueError:
        # Class already registered, skip
        pass


def unregister():
    try:
        bpy.utils.unregister_class(GP_ToggleInterpolation)
    except (ValueError, RuntimeError):
        # Class not registered or already unregistered, skip
        pass
