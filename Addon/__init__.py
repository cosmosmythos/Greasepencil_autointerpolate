"""
GP Auto Interpolate - Modern Extension Structure
Blender 4.3+ Grease Pencil Interpolation Addon
"""

# NOTE: Wheels are loaded automatically by Blender from blender_manifest.toml
# No sys.path manipulation needed - that causes policy violations

import bpy
from bpy.props import BoolProperty, IntProperty

# Import submodules
from . import core
from . import utils
from . import operators
from . import panels
from . import gp_correspondence


def register():
    """Register addon"""
    # Register scene properties
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
        max=4
    )
    
    # Register submodules
    core.register()
    utils.register()
    operators.register()
    panels.register()
    gp_correspondence.register()
    
    # Register stroke guide if available
    try:
        from . import stroke_guide
        stroke_guide.register()
    except ImportError as e:
        print(f"[GPAI] Stroke guide not available: {e}")


def unregister():
    """Unregister addon"""
    # Unregister stroke guide
    try:
        from . import stroke_guide
        stroke_guide.unregister()
    except ImportError:
        pass
    
    # Unregister submodules (reverse order)
    gp_correspondence.unregister()
    panels.unregister()
    operators.unregister()
    utils.unregister()
    core.unregister()
    
    # Clean up visibility and cache
    from .utils import visibility
    from .core import cache

    # Remove frame-change handler if present
    try:
        if visibility.on_frame_change in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(visibility.on_frame_change)
    except (ValueError, AttributeError) as e:
        print(f"[GPAI] Handler cleanup: {e}")

    # Ensure modifier is OFF and clear state
    try:
        visibility._set_modifier_visible(False)
    except (AttributeError, KeyError) as e:
        print(f"[GPAI] Modifier cleanup: {e}")

    visibility.clear()
    cache.clear()

    # Delete scene properties
    del bpy.types.Scene.gp_interpolation_enabled
    del bpy.types.Scene.gp_bake_step


if __name__ == "__main__":
    register()
