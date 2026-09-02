"""
Dope Sheet Header UI
"""

import bpy
from ..core.registry import is_object_enabled

_PREF_ID = "bl_ext.user_default.gp_auto_interpolate"


def _get_prefs():
    addon = bpy.context.preferences.addons.get(_PREF_ID)
    return addon.preferences if addon is not None else None


def draw_gp_dopesheet_ui(self, context):
    prefs = _get_prefs()
    if prefs is not None and not prefs.dopesheet_enabled:
        return
    if not (context.active_object and context.active_object.type == 'GREASEPENCIL'):
        return


    show_toggle = True
    show_refresh = True
    show_layer = True
    show_easing = True
    show_arc = True
    show_bake_single = True
    show_bake_range = True
    show_bake_step = True
    if prefs is not None:
        show_toggle = bool(prefs.dopesheet_show_toggle)
        show_refresh = bool(prefs.dopesheet_show_refresh)
        show_layer = bool(prefs.dopesheet_show_layer_filter)
        show_easing = bool(prefs.dopesheet_show_easing)
        show_arc = bool(prefs.dopesheet_show_arc)
        show_bake_single = bool(prefs.dopesheet_show_bake_single)
        show_bake_range = bool(prefs.dopesheet_show_bake_range)
        show_bake_step = bool(prefs.dopesheet_show_bake_step)


    if not any((show_toggle, show_refresh, show_layer, show_easing, show_arc, show_bake_single, show_bake_range, show_bake_step)):
        return

    obj_enabled = is_object_enabled(context.scene, context.active_object.name)
    icon = 'RECORD_ON' if obj_enabled else 'RENDER_ANIMATION'


    if show_toggle or show_refresh or show_layer:
        row1 = self.layout.row(align=True)
        if show_toggle:
            row1.operator("gp.toggle_interpolation", text="", icon=icon, depress=obj_enabled)

        if show_refresh or show_layer:
            sub1 = row1.row(align=True)
            sub1.enabled = obj_enabled
            if show_refresh:
                sub1.operator("gp.refresh_interpolation", text="", icon='FILE_REFRESH')
            if show_layer:
                sub1.operator("gp.layer_filter_popup", text="", icon='DECORATE_LOCKED')


    if show_easing or show_arc:
        row2 = self.layout.row(align=True)
        row2.enabled = obj_enabled
        if show_easing:
            row2.operator("gp.show_easing_popup", text="", icon='IPO_BEZIER')
        if show_arc:
            row2.operator("gp.show_arc_popup", text="", icon='FORCE_CURVE')

    # SECTION 3: Baking
    if show_bake_single or show_bake_range or show_bake_step:
        row3 = self.layout.row(align=True)
        row3.enabled = obj_enabled
        if show_bake_single:
            row3.operator("gp.bake_single", text="", icon='KEY_HLT')
        if show_bake_range:
            row3.operator("gp.bake_selected_range", text="", icon='GREASEPENCIL_LAYER_GROUP')
        if show_bake_step:
            row3.prop(context.scene, "gp_bake_step", text="")


def register():
    bpy.types.DOPESHEET_HT_header.append(draw_gp_dopesheet_ui)


def unregister():
    bpy.types.DOPESHEET_HT_header.remove(draw_gp_dopesheet_ui)
