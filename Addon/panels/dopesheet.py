"""
Dope Sheet Header UI
"""

import bpy


def draw_gp_dopesheet_ui(self, context):
    """Draw UI buttons in Dope Sheet header"""
    if (context.active_object and context.active_object.type == 'GREASEPENCIL'):
        enabled = context.scene.gp_interpolation_enabled
        icon = 'RECORD_ON' if enabled else 'RENDER_ANIMATION'
        
        # 1. Interpolation toggle (always active)
        self.layout.operator("gp.toggle_interpolation", text="", icon=icon, depress=enabled)
        
        # Create row for other buttons - greyed out when interpolation disabled
        row = self.layout.row(align=True)
        row.enabled = enabled  # Grey out instead of hide
        
        # 2. Refresh Cache
        row.operator("gp.refresh_interpolation", text="", icon='FILE_REFRESH')
        
        # 3. Easing button
        row.operator("gp.show_easing_popup", text="", icon='IPO_BEZIER')
        
        # 4. Arc Settings button
        row.operator("gp.show_arc_popup", text="", icon='FORCE_CURVE')
        
        # Separator before bake group
        row.separator()
        
        # 5. Bake Single
        row.operator("gp.bake_single", text="", icon='KEY_HLT')
        
        # 6. Bake Range with step input
        row.operator("gp.bake_selected_range", text="", icon='GREASEPENCIL_LAYER_GROUP')
        row.prop(context.scene, "gp_bake_step", text="")


def register():
    bpy.types.DOPESHEET_HT_header.append(draw_gp_dopesheet_ui)


def unregister():
    bpy.types.DOPESHEET_HT_header.remove(draw_gp_dopesheet_ui)

