"""
GP Auto Interpolate
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


def on_load_post(dummy):
    """Handler called after a .blend file is loaded. Checks for node group updates."""
    from .core import cache
    from .core.constants import NODEGROUP_VERSION
    
    if cache.check_and_update_nodegroup():
        # Show notification to user
        def draw_message(self, context):
            self.layout.label(text=f"GPAI Nodes updated to {NODEGROUP_VERSION}")
        
        bpy.context.window_manager.popup_menu(draw_message, title="GP Auto Interpolate", icon='INFO')


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
        max=8
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
    
    # Register load handler for version checking
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)


def unregister():
    """Unregister addon"""
    # Remove load handler
    try:
        if on_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(on_load_post)
    except (ValueError, AttributeError):
        pass
    
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
