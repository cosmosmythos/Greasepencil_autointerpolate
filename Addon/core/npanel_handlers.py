"""
N-Panel Handlers
Manages curve loading, auto-saving for the N-Panel UI,
and depsgraph-driven dirty flags for cache invalidation.

"""

import bpy
from bpy.app.handlers import persistent
from ..operators.easing_direct import get_stored_easing_data

# Global state
_last_curve_hash = None
_loading_curve = False
_last_preview_key = None      # (layer_idx, frame_num) or None
_last_playhead_frame = None


def _gp_id_types():
    """RNA classes for Grease Pencil datablocks (4.2 vs 4.3+ names differ)."""
    types = []
    for name in ("GreasePencil", "GreasePencilv3"):
        t = getattr(bpy.types, name, None)
        if t is not None:
            types.append(t)
    return tuple(types)


def _targets_by_gp_data(target_names):
    """Map gp_obj.data pointer -> list of registered target names.

    Cheap O(#enabled targets): avoids bpy.data.objects.get inside the depsgraph
    update loop (which can be very hot in large scenes).
    """
    by_data = {}
    objects = bpy.data.objects
    for name in target_names:
        ob = objects.get(name)
        if ob and ob.type == "GREASEPENCIL":
            gp_data = ob.data
            if gp_data is not None:
                lst = by_data.setdefault(gp_data, [])
                lst.append(name)
    return by_data


# ---------------------------------------------------------------------------
# Single source of truth: which key should the N-panel preview?
# ---------------------------------------------------------------------------

def resolve_preview_key(context):
    """Return (layer_idx, frame_num) for the key whose easing should be previewed.

    Priority:
        1. First selected dopesheet key on the active layer.
        2. Previous key <= playhead on the active layer.

    Returns (None, None) if nothing is resolvable.
    """
    gp_obj = context.active_object
    if not gp_obj or gp_obj.type != 'GREASEPENCIL':
        return None, None

    gp_data = gp_obj.data
    active_layer = gp_data.layers.active
    if not active_layer:
        return None, None

    layer_idx = next(
        (i for i, l in enumerate(gp_data.layers) if l == active_layer),
        None,
    )
    if layer_idx is None:
        return None, None

    # 1. Dopesheet selection wins
    selected = [f.frame_number for f in active_layer.frames if f.select]
    if selected:
        return layer_idx, min(selected)

    # 2. Fallback: previous key <= playhead
    cf = context.scene.frame_current
    prev = max(
        (f.frame_number for f in active_layer.frames if f.frame_number <= cf),
        default=None,
    )
    if prev is None:
        return None, None
    return layer_idx, prev


# ---------------------------------------------------------------------------
# Curve hash / loading flag
# ---------------------------------------------------------------------------

def get_curve_hash():
    """Get hash of current curve state (includes handle types)"""
    from ..utils.easing import get_easing_curve_node
    curve_node = get_easing_curve_node()
    if not curve_node or curve_node.type != 'CURVE_FLOAT':
        return None

    curve = curve_node.mapping.curves[0]
    points_data = [
        (round(pt.location.x, 4), round(pt.location.y, 4), pt.handle_type)
        for pt in curve.points
    ]
    return hash(tuple(points_data))


def set_loading_flag(loading):
    """Prevent auto-save during programmatic changes"""
    global _loading_curve, _last_curve_hash
    _loading_curve = loading
    if not loading:
        _last_curve_hash = get_curve_hash()


# ---------------------------------------------------------------------------
# Load curve for the currently-resolved preview key
# ---------------------------------------------------------------------------

def load_curve_for_current_context(context):
    """Load the easing curve for whichever key resolve_preview_key() picks."""
    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return

    gp_data = context.active_object.data
    layer_idx, frame_num = resolve_preview_key(context)
    if layer_idx is None or frame_num is None:
        return

    from ..utils.easing import get_easing_curve_node
    curve_node = get_easing_curve_node()
    if not curve_node:
        return

    from ..operators.easing_direct import (
        apply_preset_to_curve,
        get_stored_easing_data,
    )

    preset, data = get_stored_easing_data(gp_data, layer_idx, frame_num)
    if not preset:
        preset = 'LINEAR'

    set_loading_flag(True)
    try:
        apply_preset_to_curve(preset, data)
    finally:
        set_loading_flag(False)


# ---------------------------------------------------------------------------
# Frame-change handler (scrub / playback)
# ---------------------------------------------------------------------------

@persistent
def on_frame_change(scene, depsgraph=None):
    """Reload the preview curve when the playhead moves.

    This only matters when there is NO dopesheet selection — when there is a
    selection, resolve_preview_key() ignores the playhead anyway, so the
    early-out via _last_preview_key in on_depsgraph_update keeps things stable.
    """
    global _last_playhead_frame, _last_preview_key

    try:
        context = bpy.context
        current_frame = scene.frame_current

        if current_frame == _last_playhead_frame:
            return
        _last_playhead_frame = current_frame

        # Recompute preview key so depsgraph handler stays in sync
        new_key = resolve_preview_key(context)
        if new_key != _last_preview_key:
            _last_preview_key = new_key
            load_curve_for_current_context(context)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Depsgraph handler: dirty flags + preview reload + auto-save
# ---------------------------------------------------------------------------

@persistent
def on_depsgraph_update(scene, depsgraph):
    """Single depsgraph handler:

    1. Mark caches dirty for any registered GP object whose geometry changed.
    2. Reload the preview curve if the resolved preview key changed
       (layer switch OR dopesheet selection change).
    3. Auto-save user edits to the currently previewed CUSTOM curve.
    """
    global _last_curve_hash, _loading_curve, _last_preview_key

    if _loading_curve:
        return

    try:
        context = bpy.context
    except Exception:
        return

    screen = getattr(context, "screen", None)
    is_playing = bool(screen and screen.is_animation_playing)

    try:
        from ..utils import visibility
        is_rendering = visibility._is_rendering()
    except Exception:
        is_rendering = False

    # --- PHASE 0: Dirty flags for cache invalidation ---
    if scene.gp_interpolation_enabled:
        from ..core import cache
        from ..core.registry import get_targets
        targets = get_targets(scene)

        if not is_playing and not is_rendering:
            grease_pencil_types = _gp_id_types()
            if grease_pencil_types and targets:
                targets_by_gp = _targets_by_gp_data(targets)
                objects = bpy.data.objects

                for update in depsgraph.updates:
                    update_id = getattr(update, "id", None)
                    is_geom_update = bool(getattr(update, "is_updated_geometry", False))
                    if not isinstance(update_id, grease_pencil_types):
                        continue

                    matched_names = targets_by_gp.get(update_id)
                    if not matched_names:
                        continue

                    for target_name in matched_names:
                        gp_obj = objects.get(target_name)
                        if not gp_obj:
                            continue

                        if cache.is_dirty(target_name):
                            continue

                        if cache.is_runtime_update_active(target_name):
                            continue

                        cached_entry = cache.get_cache(target_name)
                        if is_geom_update:
                            current_sig = cache.get_source_signature(gp_obj)
                            cached_sig = cached_entry.get('source_signature')
                        else:
                            current_sig = cache.get_signature(gp_obj)
                            cached_sig = cached_entry.get('signature')

                        if (
                            cached_sig is not None
                            and current_sig is not None
                            and cached_sig == current_sig
                        ):
                            cache.consume_runtime_update_grace(target_name)
                            continue

                        cache.clear_runtime_update_grace(target_name)
                        cache.mark_dirty(target_name)

    # The rest is easing-only and concerns the active object only.
    if not context.active_object or context.active_object.type != 'GREASEPENCIL':
        return

    gp_data = context.active_object.data
    active_layer = gp_data.layers.active
    if not active_layer:
        return

    # --- PHASE 1: Detect preview-key changes (layer switch or selection) ---
    current_preview_key = resolve_preview_key(context)
    if current_preview_key != _last_preview_key:
        _last_preview_key = current_preview_key
        load_curve_for_current_context(context)
        return  # don't auto-save on the same tick we just loaded

    # --- PHASE 2: Auto-save user curve edits to the PREVIEWED key ---
    current_hash = get_curve_hash()
    if current_hash is None:
        return

    if _last_curve_hash is None:
        _last_curve_hash = current_hash
        return

    if current_hash == _last_curve_hash:
        return

    _last_curve_hash = current_hash

    # Save to whichever key is currently previewed (WYSIWYG editing)
    layer_idx, frame_num = current_preview_key
    if layer_idx is None or frame_num is None:
        return

    stored_preset, _ = get_stored_easing_data(gp_data, layer_idx, frame_num)
    if stored_preset != 'CUSTOM' or not context.scene.gp_interpolation_enabled:
        return

    gp_obj = context.active_object
    layer = gp_data.layers[layer_idx]

    from ..utils import easing
    easing.set_easing_curve_to_frame(gp_data, layer, layer_idx, frame_num, 'CUSTOM')

    from . import cache
    cache.clear(gp_obj.name)
    cache.build(gp_obj)


# ---------------------------------------------------------------------------
# Register / unregister
# ---------------------------------------------------------------------------

def register():
    if on_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame_change)

    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame_change)

    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
