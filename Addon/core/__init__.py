"""
Core functionality for GP Auto Interpolate
"""

from . import cpp_module
from . import cache
from . import interpolation

def register():
    cpp_module.load()

def unregister():
    pass
