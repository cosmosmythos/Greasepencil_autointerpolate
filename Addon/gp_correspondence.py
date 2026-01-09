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


# Header UI Integration
def draw_gpcorr_header(self, context):
    """Draw correspondence buttons in 3D View header"""
    layout = self.layout
    
    obj = context.active_object
    if obj is None or obj.type != 'GREASEPENCIL':
        return
    
    row = layout.row(align=True)
    
    # Match button
    row.operator("gpcorr.match", text="Auto-Link", icon='COLLECTION_COLOR_06')
    
    # Link mode toggle
    row.operator("gpcorr.link_mode", 
                 text="Manual" if not _link_mode_active else "Done", 
                 icon='RESTRICT_INSTANCED_OFF' if not _link_mode_active else 'SOLO_ON',
                 depress=_link_mode_active)
    
    # Link/Unlink buttons (only visible in link mode)
    if _link_mode_active:
        row.operator("gpcorr.link_selected", text="Link", icon='ADD')
        row.operator("gpcorr.unlink_selected", text="Unlink", icon='REMOVE')
    
    # Show progress if job running
    if _match_job_running:
        status = _match_progress.get('status', '')
        current = _match_progress.get('current', 0)
        total = _match_progress.get('total', 0)
        if total > 0:
            row.label(text=f"[{current}/{total}] {status}")
def register():
    """Register correspondence UI."""
    bpy.types.VIEW3D_HT_header.prepend(draw_gpcorr_header)


def unregister():
    """Unregister correspondence UI."""
    bpy.types.VIEW3D_HT_header.remove(draw_gpcorr_header)
