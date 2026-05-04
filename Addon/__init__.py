"""
GP Auto Interpolate
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, IntProperty

from . import core
from . import utils
from . import operators
from . import panels
from . import gp_correspondence


@persistent
def on_load_post(dummy):
    """Handler called after a .blend file is loaded."""
    from .core import cache
    from .core.constants import NODEGROUP_VERSION
    from .core.registry import migrate_legacy_target, get_targets, set_targets
    from .utils import visibility

    if cache.check_and_update_nodegroup():
        def draw_message(self, context):
            self.layout.label(text=f"GPAI Nodes updated to {NODEGROUP_VERSION}")
        bpy.context.window_manager.popup_menu(draw_message, title="GP Auto Interpolate", icon='INFO')

    scene = bpy.context.scene

    # Migrate old single-target format → new multi-target list
    migrate_legacy_target(scene)

    if scene.gp_interpolation_enabled:
        targets = get_targets(scene)

        # Validate targets still exist
        valid_targets = set()
        for target_name in targets:
            gp_obj = bpy.data.objects.get(target_name)
            if gp_obj and gp_obj.type == 'GREASEPENCIL':
                cache.ensure_modifier(gp_obj)
                cache.build(gp_obj)
                valid_targets.add(target_name)

        if valid_targets:
            set_targets(scene, valid_targets)

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
            scene.gp_interpolation_enabled = False
            set_targets(scene, set())
            scene["gp_interpolation_target"] = ""


def register():
    bpy.types.Scene.gp_interpolation_enabled = BoolProperty(
        name="Enable Interpolation",
        description="Enable real-time GP interpolation",
        default=False
    )

    bpy.types.Scene.gp_bake_step = IntProperty(
        name="Every",
        description="Bake every N frames",
        default=1,
        min=1,
        max=8
    )

    core.register()
    utils.register()
    operators.register()
    panels.register()
    gp_correspondence.register()

    try:
        from . import stroke_guide
        stroke_guide.register()
    except ImportError as e:
        print(f"[GPAI] Stroke guide: {e}")

    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)


def unregister():
    try:
        if on_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_load_post)
    except (ValueError, AttributeError):
        pass

    # Clean up runtime state before submodule unregistration
    from .utils import visibility
    from .core import cache

    for handler_list, func in [
        (bpy.app.handlers.frame_change_post, visibility.on_frame_change),
        (bpy.app.handlers.undo_post, visibility.on_undo_redo),
        (bpy.app.handlers.redo_post, visibility.on_undo_redo),
        (bpy.app.handlers.render_pre, visibility.on_render_pre),
        (bpy.app.handlers.render_post, visibility.on_render_post),
        (bpy.app.handlers.render_cancel, visibility.on_render_post),
    ]:
        try:
            if func in handler_list:
                handler_list.remove(func)
        except (ValueError, AttributeError):
            pass

    try:
        visibility.force_modifier_off_for_authoring()
    except (AttributeError, KeyError):
        pass

    visibility.clear()
    cache.clear()

    # Unregister submodules (reverse order)
    try:
        from . import stroke_guide
        stroke_guide.unregister()
    except ImportError:
        pass

    gp_correspondence.unregister()
    panels.unregister()
    operators.unregister()
    utils.unregister()
    core.unregister()

    del bpy.types.Scene.gp_interpolation_enabled
    del bpy.types.Scene.gp_bake_step


if __name__ == "__main__":
    register()
