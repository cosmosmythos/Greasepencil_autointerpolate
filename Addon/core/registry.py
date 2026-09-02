
import bpy
import json


def get_targets(scene) -> set:
    raw = scene.get("gp_interpolation_targets", "[]")
    try:
        return set(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return set()


def set_targets(scene, targets: set):
    scene["gp_interpolation_targets"] = json.dumps(list(targets))


def is_object_enabled(scene, obj_name) -> bool:
    return obj_name in get_targets(scene)


def validate_targets(scene) -> set:
    targets = get_targets(scene)
    valid = {n for n in targets
             if bpy.data.objects.get(n) is not None
             and bpy.data.objects[n].type == 'GREASEPENCIL'}
    if valid != targets:
        set_targets(scene, valid)

        scene.gp_interpolation_enabled = len(valid) > 0
    return valid


def migrate_legacy_target(scene):
    old_key = "gp_interpolation_target"
    new_key = "gp_interpolation_targets"

    if old_key in scene and new_key not in scene:
        old_target = scene[old_key]
        if old_target:
            set_targets(scene, {old_target})
            print(f"[GPAI] Migrated legacy target '{old_target}' to multi-target format")


