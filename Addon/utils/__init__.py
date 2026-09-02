
from . import easing
from . import arc_data
from . import visibility
from . import vectorization
from . import linked_stroke_overlay


def register():
    linked_stroke_overlay.register()


def unregister():
    linked_stroke_overlay.unregister()
