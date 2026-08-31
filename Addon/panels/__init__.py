"""
UI
"""

from . import dopesheet
from . import npanel
from . import toolshelf


def register():
    dopesheet.register()
    npanel.register()
    toolshelf.register()


def unregister():
    toolshelf.unregister()
    npanel.unregister()
    dopesheet.unregister()
