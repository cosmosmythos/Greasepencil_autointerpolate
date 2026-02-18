"""
Dope Sheet Header UI
"""

import bpy


def draw_gp_dopesheet_ui(self, context):
    """Draw UI buttons in Dope Sheet header"""
    if (context.active_object and context.active_object.type == 'GREASEPENCIL'):
        enabled = context.scene.gp_interpolation_enabled
        icon = 'RECORD_ON' if enabled else 'RENDER_ANIMATION'
        
        # SECTION 1: Interpolate & Refresh & Layer Filter
        row1 = self.layout.row(align=True)
        row1.operator("gp.toggle_interpolation", text="", icon=icon, depress=enabled)
        sub1 = row1.row(align=True)
        sub1.enabled = enabled
        sub1.operator("gp.refresh_interpolation", text="", icon='FILE_REFRESH')
        sub1.operator("gp.layer_filter_popup", text="", icon='DECORATE_LOCKED')
        
        # SECTION 2: Easing & Trajectory
        row2 = self.layout.row(align=True)
        row2.enabled = enabled
        row2.operator("gp.show_easing_popup", text="", icon='IPO_BEZIER')
        row2.operator("gp.show_arc_popup", text="", icon='FORCE_CURVE')
        
        # SECTION 3: Baking
        row3 = self.layout.row(align=True)
        row3.enabled = enabled
        row3.operator("gp.bake_single", text="", icon='KEY_HLT')
        row3.operator("gp.bake_selected_range", text="", icon='GREASEPENCIL_LAYER_GROUP')
        row3.prop(context.scene, "gp_bake_step", text="")


def register():
    bpy.types.DOPESHEET_HT_header.append(draw_gp_dopesheet_ui)


def unregister():
    bpy.types.DOPESHEET_HT_header.remove(draw_gp_dopesheet_ui)

