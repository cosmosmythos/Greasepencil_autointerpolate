"""
Multi-Object Registry for GP Auto Interpolate
Manages which GP objects have real-time interpolation enabled.
Stores target names as a JSON list in scene custom properties.
"""

import bpy
import json


def get_targets(scene) -> set:
    """Get set of enabled GP object names from scene storage."""
    raw = scene.get("gp_interpolation_targets", "[]")
    try:
        return set(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return set()


def set_targets(scene, targets: set):
    """Save the enabled GP object names to scene storage."""
    scene["gp_interpolation_targets"] = json.dumps(list(targets))


def is_object_enabled(scene, obj_name) -> bool:
    """Check if a specific GP object has interpolation enabled."""
    return obj_name in get_targets(scene)


def validate_targets(scene) -> set:
    """Remove stale names (deleted/renamed objects). Call on frame handler entry.
    
    Returns the validated set of target names.
    """
    targets = get_targets(scene)
    valid = {n for n in targets
             if bpy.data.objects.get(n) is not None
             and bpy.data.objects[n].type == 'GREASEPENCIL'}
    if valid != targets:
        set_targets(scene, valid)
        # Update the master switch
        scene.gp_interpolation_enabled = len(valid) > 0
    return valid


def migrate_legacy_target(scene):
    """Migrate old single-target format to new multi-target list.
    
    Old format: scene["gp_interpolation_target"] = "ObjectName"  (string)
    New format: scene["gp_interpolation_targets"] = '["ObjectName"]'  (JSON list)
    """
    old_key = "gp_interpolation_target"
    new_key = "gp_interpolation_targets"
    
    if old_key in scene and new_key not in scene:
        old_target = scene[old_key]
        if old_target:
            set_targets(scene, {old_target})
            print(f"[GPAI] Migrated legacy target '{old_target}' to multi-target format")
    
    # Keep old key around for backward compat (toggle.py still writes it
    # for the visibility system), but the new key is the source of truth.
