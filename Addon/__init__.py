"""
GP Auto Interpolate
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, IntProperty, EnumProperty, FloatProperty

from . import core
from . import utils
from . import operators
from . import panels
from . import gp_correspondence

_BEZIER_METHOD_ITEMS = [
    ("ANGLE", "Angle", "Split at corners then fit each piece"),
    ("ERROR", "Error", "Fit whole stroke, split where error is high"),
]


@persistent
def on_load_post(dummy):
    from .core import cache
    from .core.constants import NODEGROUP_VERSION
    from .core.registry import migrate_legacy_target, get_targets, set_targets
    from .core import recache_triggers
    from .utils import visibility


    recache_triggers.subscribe_msgbus()
    recache_triggers._last_mode.clear()

    if cache.check_and_update_nodegroup():
        def draw_message(self, context):
            self.layout.label(text=f"GPAI Nodes updated to {NODEGROUP_VERSION}")
        bpy.context.window_manager.popup_menu(draw_message, title="GP Auto Interpolate", icon='INFO')

    scene = bpy.context.scene


    migrate_legacy_target(scene)

    if scene.gp_interpolation_enabled:
        targets = get_targets(scene)


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

    bpy.types.Scene.gp_bezier_resample_subdiv = IntProperty(
        name="Resample",
        description="Resample subdivision before fitting. 0 to disable",
        default=2,
        min=0,
        max=5,
    )
    bpy.types.Scene.gp_bezier_fit_method = EnumProperty(
        name="Method",
        description="Split mode",
        items=_BEZIER_METHOD_ITEMS,
        default="ANGLE",
    )
    bpy.types.Scene.gp_bezier_angle = FloatProperty(
        name="Angle",
        description="Corner angle",
        default=0.174533,  # 10°
        min=0.0174533,  # 1°
        max=3.14159,  # 180°
        subtype='ANGLE',
        unit='ROTATION',
    )
    bpy.types.Scene.gp_bezier_span = IntProperty(
        name="Span",
        description="Corner search radius (Points)",
        default=3,
        min=1,
        max=10,
    )
    bpy.types.Scene.gp_bezier_fit_enabled = BoolProperty(
        name="Bézier Fit",
        description="Auto-convert drawn stroke to Bézier",
        default=False,
    )
    bpy.types.Scene.gp_bezier_error = FloatProperty(
        name="Error",
        description="Fit error",
        default=0.1,
        min=0.001,
        max=0.5,
        step=0.1,
        precision=3,
        subtype='DISTANCE',
        unit='LENGTH',
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


    try:
        from .core.preferences import _sync_headers, _sync_dopesheet

        def _deferred_header_sync():
            try:
                _sync_headers()
                _sync_dopesheet()
            except Exception:
                pass
            return None


        try:
            _sync_headers()
            _sync_dopesheet()
        except Exception:
            pass

        try:
            bpy.app.timers.register(_deferred_header_sync, first_interval=0.12)
        except Exception:
            pass
    except Exception:
        pass

    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)


def unregister():
    try:
        if on_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_load_post)
    except (ValueError, AttributeError):
        pass


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
    del bpy.types.Scene.gp_bezier_resample_subdiv
    del bpy.types.Scene.gp_bezier_fit_method
    del bpy.types.Scene.gp_bezier_angle
    del bpy.types.Scene.gp_bezier_span
    del bpy.types.Scene.gp_bezier_fit_enabled
    del bpy.types.Scene.gp_bezier_error


if __name__ == "__main__":
    register()
