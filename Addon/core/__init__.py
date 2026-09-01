"""
Core functionality
"""

from . import cpp_module
from . import cache
from . import registry
from . import interpolation
from . import npanel_handlers
from . import recache_triggers
from . import draw_sensor
from . import bezier_fit
from . import preferences


def register():
    preferences.register()
    cpp_module.load()
    npanel_handlers.register()
    recache_triggers.register()
    draw_sensor.register()
    bezier_fit.register()


def unregister():
    bezier_fit.unregister()
    draw_sensor.unregister()
    recache_triggers.unregister()
    npanel_handlers.unregister()
    preferences.unregister()
