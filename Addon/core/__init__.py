"""
Core functionality for GP Auto Interpolate
"""

from . import cpp_module
from . import cache
from . import registry
from . import interpolation
from . import npanel_handlers
from . import recache_triggers

def register():
    cpp_module.load()
    npanel_handlers.register()
    recache_triggers.register()

def unregister():
    recache_triggers.unregister()
    npanel_handlers.unregister()
