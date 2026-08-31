"""
GP Stroke Correspondence - Production UI
Integrated header buttons for stroke pairing.

Refactored structure:
- Core utilities: Addon/utils/correspondence_utils.py
- Operators: Addon/operators/correspondence.py  
- This file: UI drawing, registration, and global state management
"""

import bpy

# Global State (Shared across modules via this file)
_match_job_running = False
_match_progress = {"current": 0, "total": 0, "status": ""}
_link_mode_active = False
_link_constraints = []  # [(layer_idx, frame1, stroke1_idx, frame2, stroke2_idx), ...]
_viewport_context = {}  # Store viewport info (region, rv3d) for timer callbacks
_show_linked_overlay = False  # Toggle for showing orange overlay on linked strokes
_stable_stroke_ids = {}  # {(layer_idx, frame_num): {current_idx: stable_id, ...}}


def _operator_exists(idname):
    """Check if a Blender operator is registered and callable."""
    parts = idname.split(".")
    if len(parts) != 2:
        return False
    category, name = parts
    return hasattr(getattr(bpy.ops, category, None), name)


# Header UI Integration
def draw_gpcorr_header(self, context):
    """Draw correspondence buttons in 3D View header"""
    layout = self.layout
    
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    # Defensive check: ensure core operators are registered before drawing
    if not _operator_exists("gpcorr.link_mode"):
        return
    
    row = layout.row(align=True)
    
    # Link mode toggle (Manual only — Auto-Link removed per user request)
    row.operator("gpcorr.link_mode", 
                 text="Manual" if not _link_mode_active else "Done", 
                 icon='RESTRICT_INSTANCED_OFF' if not _link_mode_active else 'SOLO_ON',
                 depress=_link_mode_active)
    
    # Link/Unlink buttons (only visible in link mode)
    if _link_mode_active:
        row.operator("gpcorr.link_selected", text="Link", icon='ADD')
        row.operator("gpcorr.unlink_selected", text="Unlink", icon='REMOVE')
        row.operator("gpcorr.clear_all_links", text="", icon='CANCEL')
    
    # Linked strokes overlay toggle (eye icon)
    if _operator_exists("gpcorr.toggle_linked_overlay"):
        row.operator("gpcorr.toggle_linked_overlay", text="", 
                     icon='HIDE_OFF' if _show_linked_overlay else 'HIDE_ON',
                     depress=_show_linked_overlay)
    
    # Show progress if job running
    if _match_job_running:
        status = _match_progress.get('status', '')
        current = _match_progress.get('current', 0)
        total = _match_progress.get('total', 0)
        if total > 0:
            row.label(text=f"[{current}/{total}] {status}")


def register():
    """Register correspondence UI."""
    try:
        bpy.types.VIEW3D_HT_tool_header.prepend(draw_gpcorr_header)
    except Exception as e:
        print(f"[GPCORR] ERROR: Failed to register header UI: {e}")


def unregister():
    """Unregister correspondence UI."""
    try:
        bpy.types.VIEW3D_HT_tool_header.remove(draw_gpcorr_header)
    except Exception as e:
        print(f"[GPCORR] ERROR: Failed to unregister header UI: {e}")
