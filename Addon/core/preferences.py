
import bpy
from bpy.types import AddonPreferences, Panel
from bpy.props import EnumProperty, BoolProperty, IntProperty

_PREF_ID = "bl_ext.user_default.gp_auto_interpolate"

_LOG_LEVELS = [
    ("NONE",    "None",              "Disable all logging",       0),
    ("ERROR",   "Errors only",       "",                          1),
    ("WARNING", "Errors + Warnings", "",                          2),
    ("INFO",    "Info",              "Adds submission events",    3),
    ("DEBUG",   "Debug",             "Verbose — use for debugging", 4),
]

_HEADER_POS_ITEMS = [
    ("PREPEND", "Prepend", "Draw before built-in header items"),
    ("APPEND",  "Append",  "Draw after built-in header items"),
]

_DOPESHEET_POS_ITEMS = [
    ("PREPEND", "Prepend", "Draw before built-in header items"),
    ("APPEND",  "Append",  "Draw after built-in header items"),
]


def _get_prefs():
    addon = bpy.context.preferences.addons.get(_PREF_ID)
    return addon.preferences if addon is not None else None


def _on_log_level_change(self, context):
    pass


def _sync_headers():
    try:
        prefs = _get_prefs()
        if prefs is None:
            return
        enabled = bool(prefs.header_enabled)
        pos = prefs.header_position

        from .. import gp_correspondence as _gpc
        from .. import stroke_guide as _sg

        targets = [
            _gpc.draw_gpcorr_header,
            _sg.draw_header,
            draw_bezier_header,
        ]
        for fn in targets:
            try:
                bpy.types.VIEW3D_HT_tool_header.remove(fn)
            except Exception:
                pass
        if not enabled:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            return

        adder = bpy.types.VIEW3D_HT_tool_header.prepend if pos == "PREPEND" else bpy.types.VIEW3D_HT_tool_header.append
        for fn in targets:
            try:

                if fn is _gpc.draw_gpcorr_header and not prefs.header_show_correspondence:
                    continue
                if fn is _sg.draw_header and not prefs.header_show_stroke_guide:
                    continue
                if fn is draw_bezier_header and not prefs.header_show_bezier:
                    continue
                adder(fn)
            except Exception:
                pass

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


def _sync_dopesheet():
    try:
        prefs = _get_prefs()
        if prefs is None:
            return
        enabled = bool(prefs.dopesheet_enabled)
        pos = prefs.dopesheet_position

        from ..panels import dopesheet as _ds

        try:
            bpy.types.DOPESHEET_HT_header.remove(_ds.draw_gp_dopesheet_ui)
        except Exception:
            pass

        if not enabled:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'DOPESHEET_EDITOR':
                        area.tag_redraw()
            return

        adder = bpy.types.DOPESHEET_HT_header.prepend if pos == "PREPEND" else bpy.types.DOPESHEET_HT_header.append
        try:
            adder(_ds.draw_gp_dopesheet_ui)
        except Exception:
            pass

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'DOPESHEET_EDITOR':
                    area.tag_redraw()
    except Exception:
        pass


def _on_header_prefs_change(self, context):
    _sync_headers()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _on_dopesheet_prefs_change(self, context):
    try:
        _sync_dopesheet()
    except Exception:
        pass
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'DOPESHEET_EDITOR':
                area.tag_redraw()




def draw_bezier_header(self, context):
    prefs = _get_prefs()
    if prefs is None:
        return
    if not prefs.header_show_bezier:
        return
    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return
    layout = self.layout
    row = layout.row(align=True)
    row.prop(context.scene, "gp_bezier_fit_enabled", text="Bézier Fit", icon='CURVE_BEZCURVE', toggle=True)
    row.popover(panel="VIEW3D_PT_gpai_bezier_settings", text="")


class VIEW3D_PT_gpai_bezier_settings(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Bézier Fit"
    bl_ui_units_x = 7

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        col = layout.column(align=True)
        col.prop(scene, "gp_bezier_resample_subdiv", text="Resample")
        col.prop(scene, "gp_bezier_error", text="Error")
        col.prop(scene, "gp_bezier_fit_method", text="")
        if scene.gp_bezier_fit_method == 'ANGLE':
            col.prop(scene, "gp_bezier_angle", text="Angle")
            col.prop(scene, "gp_bezier_span", text="Span")


class GPAIPreferences(AddonPreferences):
    bl_idname = _PREF_ID

    ui_tabs: EnumProperty(
        name="Tab",
        description="Which settings section to show",
        items=[
            ("USER", "User", "Everyday settings"),
            ("DEVELOPER", "Developer", "Logging and internal settings"),
        ],
        default="USER",
    )

    show_draw_sensor_details: BoolProperty(
        name="Draw Sensor",
        description="Draw Sensor",
        default=False,
    )

    draw_sensor_enabled: BoolProperty(
        name="Draw Sensor",
        description="Fire drawing_done callbacks after each stroke",
        default=True,
    )

    show_header_details: BoolProperty(
        name="3D View Header",
        description="3D View Header",
        default=False,
    )

    show_dopesheet_details: BoolProperty(
        name="Dopesheet Header",
        description="Dopesheet Header",
        default=False,
    )

    show_logging_details: BoolProperty(
        name="Logging",
        description="Logging",
        default=False,
    )


    header_enabled: BoolProperty(
        name="Enable Header UI",
        description="Enable Header UI",
        default=True,
        update=_on_header_prefs_change,
    )

    header_position: EnumProperty(
        name="Position",
        description="Header position",
        items=_HEADER_POS_ITEMS,
        default="PREPEND",
        update=_on_header_prefs_change,
    )

    header_show_correspondence: BoolProperty(
        name="Stroke Correspondence",
        description="Enable Stroke Correspondence",
        default=True,
        update=_on_header_prefs_change,
    )

    header_show_stroke_guide: BoolProperty(
        name="Stroke Guide",
        description="Enable Stroke Guide",
        default=True,
        update=_on_header_prefs_change,
    )

    header_show_draw_sensor: BoolProperty(
        name="Draw Sensor Toggle",
        description="Enable Draw Sensor Toggle",
        default=False,
        update=_on_header_prefs_change,
    )

    header_show_bezier: BoolProperty(
        name="Bézier Fit",
        description="Enable Bézier Fit",
        default=True,
        update=_on_header_prefs_change,
    )


    dopesheet_enabled: BoolProperty(
        name="Enable Dopesheet UI",
        description="Enable Dopesheet UI",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_position: EnumProperty(
        name="Position",
        description="Dopesheet position",
        items=_DOPESHEET_POS_ITEMS,
        default="APPEND",
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_toggle: BoolProperty(
        name="Toggle Interpolation",
        description="Enable Toggle Interpolation",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_refresh: BoolProperty(
        name="Refresh",
        description="Enable Refresh",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_layer_filter: BoolProperty(
        name="Layer Filter",
        description="Enable Layer Filter",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_easing: BoolProperty(
        name="Easing",
        description="Enable Easing",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_arc: BoolProperty(
        name="Arc / Trajectory",
        description="Enable Arc / Trajectory",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_bake_single: BoolProperty(
        name="Bake Single",
        description="Enable Bake Single",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_bake_range: BoolProperty(
        name="Bake Range",
        description="Enable Bake Range",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    dopesheet_show_bake_step: BoolProperty(
        name="Bake Step",
        description="Enable Bake Step",
        default=True,
        update=_on_dopesheet_prefs_change,
    )

    # -- Developer --
    log_level: EnumProperty(
        name="Log level",
        description="Minimum severity to print",
        items=_LOG_LEVELS,
        default="NONE",
        update=_on_log_level_change,
    )

    log_tracebacks: BoolProperty(
        name="Log tracebacks",
        description="Include tracebacks in error logs",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "ui_tabs", expand=True)
        col.separator(factor=4, type='LINE')

        if self.ui_tabs == "USER":
            self._draw_user_section(col)
        else:
            self._draw_developer_section(col)

    def _draw_dropdown_header(self, layout, prop_name, text):
        row = layout.row()
        row.prop(
            self,
            prop_name,
            text=text,
            emboss=False,
            icon='TRIA_DOWN' if getattr(self, prop_name) else 'TRIA_RIGHT',
        )

    def _draw_user_section(self, layout):

        if not self.show_draw_sensor_details:
            self._draw_dropdown_header(layout, "show_draw_sensor_details", "Draw Sensor")
        else:
            box = layout.box()
            self._draw_dropdown_header(box, "show_draw_sensor_details", "Draw Sensor")
            box.prop(self, "draw_sensor_enabled")

        layout.separator()

        if not self.show_header_details:
            self._draw_dropdown_header(layout, "show_header_details", "3D View Header")
        else:
            box = layout.box()
            self._draw_dropdown_header(box, "show_header_details", "3D View Header")
            box.prop(self, "header_enabled")
            sub = box.column(align=True)
            sub.enabled = self.header_enabled
            sub.prop(self, "header_position", expand=True)
            sub.separator()
            sub.label(text="Tools:")
            sub.prop(self, "header_show_correspondence")
            sub.prop(self, "header_show_stroke_guide")
            sub.prop(self, "header_show_bezier")

        layout.separator()

        if not self.show_dopesheet_details:
            self._draw_dropdown_header(layout, "show_dopesheet_details", "Dopesheet")
        else:
            box = layout.box()
            self._draw_dropdown_header(box, "show_dopesheet_details", "Dopesheet")
            box.prop(self, "dopesheet_enabled")
            sub = box.column(align=True)
            sub.enabled = self.dopesheet_enabled
            sub.prop(self, "dopesheet_position", expand=True)
            sub.separator()
            sub.label(text="Tools:")
            sub.prop(self, "dopesheet_show_toggle")
            sub.prop(self, "dopesheet_show_refresh")
            sub.prop(self, "dopesheet_show_layer_filter")
            sub.separator(factor=0.6)
            sub.prop(self, "dopesheet_show_easing")
            sub.prop(self, "dopesheet_show_arc")
            sub.separator(factor=0.6)
            sub.prop(self, "dopesheet_show_bake_single")
            sub.prop(self, "dopesheet_show_bake_range")
            sub.prop(self, "dopesheet_show_bake_step")

    def _draw_developer_section(self, layout):
        if not self.show_logging_details:
            self._draw_dropdown_header(layout, "show_logging_details", "Logging")
            return
        box = layout.box()
        self._draw_dropdown_header(box, "show_logging_details", "Logging")
        box.prop(self, "log_level", text="Level")
        box.prop(self, "log_tracebacks")


def register():
    bpy.utils.register_class(GPAIPreferences)
    bpy.utils.register_class(VIEW3D_PT_gpai_bezier_settings)


def unregister():
    try:
        bpy.utils.unregister_class(VIEW3D_PT_gpai_bezier_settings)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(GPAIPreferences)
    except Exception:
        pass
