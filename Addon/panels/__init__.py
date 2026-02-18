"""
UI Panels for GP Auto Interpolate
"""

from . import dopesheet
from . import npanel


def register():
    dopesheet.register()
    npanel.register()


def unregister():
    npanel.unregister()
    dopesheet.unregister()
