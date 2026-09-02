
import bpy


_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_mode_active = False
_link_constraints = []
_viewport_context = {}
_show_linked_overlay = False
_stable_stroke_ids = {}


def _operator_exists(idname):
    parts = idname.split(".")
    if len(parts) != 2:
        return False
    category, name = parts
    return hasattr(getattr(bpy.ops, category, None), name)


# Header UI Integration
def draw_gpcorr_header(self, context):

    try:
        addon = bpy.context.preferences.addons.get("bl_ext.user_default.gp_auto_interpolate")
        if addon is not None and not addon.preferences.header_show_correspondence:
            return
    except Exception:
        pass
    layout = self.layout

    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return


    if not _operator_exists("gpcorr.link_mode"):
        return

    row = layout.row(align=True)

    row.operator("gpcorr.link_mode",
                 text="Link" if not _link_mode_active else "Done",
                 icon='RESTRICT_INSTANCED_OFF' if not _link_mode_active else 'SOLO_ON',
                 depress=_link_mode_active)


    if _link_mode_active:
        row.operator("gpcorr.link_selected", text="Link", icon='ADD')
        row.operator("gpcorr.unlink_selected", text="Unlink", icon='REMOVE')
        row.operator("gpcorr.clear_all_links", text="", icon='CANCEL')


    if _operator_exists("gpcorr.toggle_linked_overlay"):
        row.operator("gpcorr.toggle_linked_overlay", text="",
                     icon='HIDE_OFF' if _show_linked_overlay else 'HIDE_ON',
                     depress=_show_linked_overlay)


    if _match_job_running:
        status = _match_progress.get('status', '')
        current = _match_progress.get('current', 0)
        total = _match_progress.get('total', 0)
        if total > 0:
            row.label(text=f"[{current}/{total}] {status}")


def register():
    try:
        bpy.types.VIEW3D_HT_tool_header.prepend(draw_gpcorr_header)
    except Exception as e:
        print(f"[GPCORR] ERROR: Failed to register header UI: {e}")


def unregister():
    try:
        bpy.types.VIEW3D_HT_tool_header.remove(draw_gpcorr_header)
    except Exception as e:
        print(f"[GPCORR] ERROR: Failed to unregister header UI: {e}")
