# Core — GP Auto Interpolate Engine

## Purpose

Central engine for stroke interpolation. Loads the native C++ module, maintains a multi-object stroke cache with dirty-flag invalidation, runs the per-frame interpolation pipeline, tracks enabled objects, and listens to depsgraph / frame-change / msgbus events for cache invalidation.

## Ownership

| File | Role |
|------|------|
| `__init__.py` | Registers core submodules; calls `cpp_module.load()` and registers `npanel_handlers` + `recache_triggers` |
| `cpp_module.py` | Sole loader for the compiled C++ `gp_autointerpolate` wheel; `get_interpolator()` returns a process-singleton `Interpolator` |
| `cache.py` | Multi-object stroke cache + dirty-flag and runtime-update-guard API; `build()` extracts per-keyframe stroke data and easing/arc params |
| `interpolation.py` | Per-frame pipeline: bisect prev/next key, call C++, write `*_i` mirror attributes |
| `registry.py` | Enabled-object set stored as JSON in scene props; legacy single-target migration |
| `npanel_handlers.py` | depsgraph + frame_change_post handlers: dirty flags, deferred structural-signature check, easing-UI sync |
| `recache_triggers.py` | msgbus triggers (mode change, active-object change) → `mark_dirty` |
| `bake_utils.py` | Bake-only helpers (stroke normal, arc params, apply to FINAL attributes) |
| `constants.py` | Shared names + version strings |

## Local Contracts

- **Primary per-frame entry point is `utils/visibility.on_frame_change`, not a core handler.** When playing / scrubbing / rendering it shows modifiers then calls `interpolation.process_scene(scene)`. `core/npanel_handlers.on_frame_change` only syncs the easing-curve UI and never runs interpolation.
- **Invalidation uses two layers:** dirty flag + deferred keyframe signature check.
  - Dirty flag paths, all converge on `cache.mark_dirty()`:
    - Geometry depsgraph update → unconditional `mark_dirty` (no hash).
    - Non-geometry update (keyframe move/add/remove) → deferred (timer) comparison of the **lightweight** `get_keyframe_signature()` only.
    - msgbus mode / active-object change → `mark_dirty`.
  - `get_keyframe_signature()` (layer count + keyframe numbers only, no stroke/point iteration) runs in `_deferred_sig_check()` via timer — never in the per-frame loop. Catches keyframe moves that `is_updated_geometry` doesn't report.
- **Dirty flags are consumed at the top of `process_object`** (`interpolation.py`), which calls `build()` only when the object is dirty or has no cache yet.
- **`build()` is per-object and isolated**: it writes only `cache_registry[obj_name]`, never clears or touches siblings.
- **Feedback-loop suppression, not thread-safety.** The addon's own writes (`*_i` attributes, modifier visibility) fire depsgraph updates that would re-invalidate the cache. `begin_runtime_update` / `end_runtime_update` + the grace counter suppress these self-triggered updates. Blender runs these handlers single-threaded; the concern is re-entrancy, not races.
- **Two signatures, different scopes.**
  - `get_signature()` (structural: layer/frame/stroke/point counts + keyframe numbers) — used only at build time and in deferred non-geometry sig check. Never computed in the hot path.
  - `get_keyframe_signature()` (lightweight: layer count + keyframe numbers only) — used in `_deferred_sig_check()` (timer-based, not per-frame). Catches keyframe moves/adds/removes.

## Work Guidance

- Keep `cpp_module.py` the sole native loader; never `import gp_autointerpolate` directly elsewhere.
- Never call `get_signature()` inside depsgraph handlers or per-frame loops — build-time and deferred-timer only. `get_keyframe_signature()` is the only signature safe for the hot path (no stroke/point iteration).
- Any new source attribute the engine reads must also be mirrored to a `*_i` attribute by `_ensure_interpolation_attributes`: interpolation writes only to mirrors, and the modifier composes them.
- Preserve the cached layer schema (`keyframes` / `sorted_frames` / `frame_lookup` / `easing_data` / `easing_samples` / `arc_data`) — `interpolation.py` reads these fields without guards.
- Changes to interpolation output must stay backward-compatible with `bake_utils.apply_interpolation_to_frame`, which writes the same data to FINAL attributes for baking.

## Verification

- `cpp_module.load()` then `get_interpolator()` returns an instance without import error.
- Toggle a GP object on, scrub between two keys → interpolated `*_i` data appears on in-between frames.
- Edit geometry on one key → the next frame change rebuilds only that object's cache (dirty flag), not sibling objects'.
