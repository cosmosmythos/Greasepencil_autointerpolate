"""
Operators for GP Auto Interpolate
"""

from . import toggle
from . import refresh
from . import bake_single
from . import bake_range
from . import easing_popup
from . import arc_popup
from . import import_lineart
from . import correspondence


def register():
    toggle.register()
    refresh.register()
    bake_single.register()
    bake_range.register()
    easing_popup.register()
    arc_popup.register()
    import_lineart.register()
    correspondence.register()


def unregister():
    correspondence.unregister()
    import_lineart.unregister()
    arc_popup.unregister()
    easing_popup.unregister()
    bake_range.unregister()
    bake_single.unregister()
    refresh.unregister()
    toggle.unregister()

