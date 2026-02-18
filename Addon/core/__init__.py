"""
Core functionality for GP Auto Interpolate
"""

from . import cpp_module
from . import cache
from . import interpolation
from . import npanel_handlers

def register():
    cpp_module.load()
    npanel_handlers.register()

def unregister():
    npanel_handlers.unregister()
