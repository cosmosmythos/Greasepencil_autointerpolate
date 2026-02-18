"""
Operators for GP Auto Interpolate
"""

from . import toggle
from . import refresh
from . import bake_single
from . import bake_range
from . import easing_popup
from . import easing_direct
from . import arc_popup
from . import layer_filter
from . import import_lineart
from . import correspondence


def register():
    toggle.register()
    refresh.register()
    bake_single.register()
    bake_range.register()
    easing_popup.register()
    easing_direct.register()
    arc_popup.register()
    layer_filter.register()
    import_lineart.register()
    correspondence.register()


def unregister():
    correspondence.unregister()
    import_lineart.unregister()
    layer_filter.unregister()
    arc_popup.unregister()
    easing_direct.unregister()
    easing_popup.unregister()
    bake_range.unregister()
    bake_single.unregister()
    refresh.unregister()
    toggle.unregister()
