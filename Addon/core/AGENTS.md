# Core — GP Auto Interpolate Engine

## Purpose

Central engine for stroke interpolation. Loads the native C++ module, maintains a multi-object stroke cache with dirty-flag invalidation, runs the per-frame interpolation pipeline, tracks enabled objects, and listens to depsgraph / frame-change / msgbus events for cache invalidation.

## Ownership

| File | Role |
|------|------|
| `__init__.py` | Registers core submodules; calls `preferences.register()` first (like TEXTURESYNTH) then `cpp_module.load()` + `npanel_handlers` + `recache_triggers` + `draw_sensor` + `stroke_delete_on_draw` |
| `preferences.py` | AddonPreferences `bl_ext.user_default.gp_auto_interpolate` — preview-lock style: `USER`/`DEVELOPER` tabs + `TRIA_DOWN`/`TRIA_RIGHT` collapsibles (`3D View Header` / `Dopesheet`); Header: `header_enabled` + `PREPEND`/`APPEND` + per-tool `Enable X` (`Stroke Correspondence`, `Stroke Guide`, `Draw Sensor Toggle`); Dopesheet: `dopesheet_enabled` + `PREPEND`/`APPEND` + per-tool `Enable X` (`Toggle Interpolation`, `Refresh`, `Layer Filter`, `Easing`, `Arc / Trajectory`, `Bake Single`, `Bake Range`, `Bake Step`); live `_sync_headers`/`_sync_dopesheet` re-registers `VIEW3D_HT_tool_header`/`DOPESHEET_HT_header` + `tag_redraw`; description = `Enable X` (name) |
| `cpp_module.py` | Sole loader for the compiled C++ `gp_autointerpolate` wheel; `get_interpolator()` returns a process-singleton `Interpolator` |
| `cache.py` | Multi-object stroke cache + dirty-flag and runtime-update-guard API; `build()` extracts per-keyframe stroke data and easing/arc params |
| `interpolation.py` | Per-frame pipeline: bisect prev/next key, call C++, write `*_i` mirror attributes |
| `registry.py` | Enabled-object set stored as JSON in scene props; legacy single-target migration |
| `npanel_handlers.py` | depsgraph + frame_change_post handlers: dirty flags, deferred structural-signature check, easing-UI sync |
| `recache_triggers.py` | msgbus triggers (mode change, active-object change) → `mark_dirty` |
| `bake_utils.py` | Bake-only helpers (stroke normal, arc params, apply to FINAL attributes) |
| `constants.py` | Shared names + version strings |
| `draw_sensor.py` | Draw-finish sensor: PAINT-only + mouse-down (tablet+mouse via `GetKeyState`) + `is_updated_geometry` burst → 3-state `DRAWING→RELEASED→FINALIZED` (0.05s post-process wait) + counts gate → silent `register_drawing_done_callback`. Header toggle `Scene.gp_draw_sensor_enabled` in `VIEW3D_HT_tool_header` (gated by `prefs.header_show_draw_sensor`) |
| `stroke_delete_on_draw.py` | Demo hook: `register_drawing_done_callback` → resamples last stroke to quarter average edge spacing via `drawing.resize_strokes`, lerping position/radius/opacity only (polyline, no handles); guards non-finite/wild (>1e6) segments and clamps to 4096 points; always re-baselines sensor in `finally` (toggle `Scene.gp_resample_on_draw`) |

## Local Contracts

- **Draw-finish sensor `draw_sensor.py` is PAINT-only and counts-gated, not time-graced.** `on_depsgraph_update` ARMs only on `is_updated_geometry` for `GreasePencil`/`Object:GreasePencil` while `active_object.mode` is `PAINT_GPENCIL`/`PAINT_GREASE_PENCIL`. `on_load_post` re-baselines `(strokes, points)` — no grace delay. `_idle_check` (0.05s) fires only if total strokes/points increased since last stable; mode-switch / file-new / undo-erase with no increase are silently suppressed. `is_brush_stroke_running()` is `GetKeyState(VK_LBUTTON) && _in_draw_mode()` (mouse+tablet, no `wm.operators` history). State is `DRAWING (mouse down) → RELEASED (lift) → FINALIZED` after one settled `is_updated_geometry` post-process tick — pause with finger still down never leaves `DRAWING`. Notifies via `register_drawing_done_callback` (silent, no Status Bar — use callback for `rebuild_frame` or last-stroke work). `self.report` from handlers/timers is suppressed by Blender, so no modal watcher is used.
- **Primary per-frame entry point is `utils/visibility.on_frame_change`, not a core handler.** When playing / scrubbing / rendering it shows modifiers then calls `interpolation.process_scene(scene)`. `core/npanel_handlers.on_frame_change` only syncs the easing-curve UI and never runs interpolation.
- **Invalidation uses two layers:** geometry-path immediate rebuild + deferred keyframe signature check.
  - Geometry depsgraph update (`is_updated_geometry=True`) → immediate rebuild via `cache.clear() + cache.build()`. Only runs when the object is not already dirty, not currently building, and has no pending runtime grace.
  - Non-geometry update (keyframe move/add/remove) → deferred (timer) comparison of the **lightweight** `get_keyframe_signature()`. On mismatch → immediate rebuild (`clear + build`), not just `mark_dirty`.
  - msgbus mode / active-object change → `mark_dirty` (consumed by `process_object` on next frame).
  - Modifier toggle, interpolation toggle, layer visibility changes do NOT trigger rebuild (no depsgraph update fires).
  - `_targets_by_gp_data()` maps `gp_obj.data.name` (string) → target names. Uses datablock name as key, not Python object identity.
- **`get_keyframe_signature()` runs in `_deferred_sig_check()` via timer** — never in the per-frame loop.
- **Dirty flags are consumed at the top of `process_object`** (`interpolation.py`), which calls `build()` only when the object is dirty or has no cache yet.
- **`build()` is per-object and isolated**: it writes only `cache_registry[obj_name]`, never clears or touches siblings.
- **Feedback-loop suppression via `is_runtime_update_active()` check.** The depsgraph handler skips objects where `is_runtime_update_active()` is True. Grace counter is set to zero (`grace_updates=0`) so user edits are never suppressed.
- **Two signatures, different scopes.**
  - `get_signature()` (structural: layer/frame/stroke/point counts + keyframe numbers) — build-time only.
  - `get_keyframe_signature()` (lightweight: layer count + keyframe numbers only) — timer-based, not per-frame.
- **Preferences own header/dopesheet visibility (preview-lock style).** `preferences.py` `Enable X` — description equals name (`Enable Stroke Guide`, etc.). Header `VIEW3D_HT_tool_header` and Dopesheet `DOPESHEET_HT_header` use `PREPEND`/`APPEND` with live `_sync_headers`/`_sync_dopesheet` (immediate + 0.12s deferred after `panels`/`gp_correspondence`/`stroke_guide` register) + `tag_redraw`. Individual draws early-out: `stroke_guide`/`gp_correspondence`/`draw_sensor` check `header_show_*`, `panels/dopesheet` checks `dopesheet_show_*` per row.

## Work Guidance

- Keep `cpp_module.py` the sole native loader; never `import gp_autointerpolate` directly elsewhere.
- Never call `get_signature()` inside depsgraph handlers or per-frame loops — build-time and deferred-timer only. `get_keyframe_signature()` is the only signature safe for the hot path (no stroke/point iteration).
- Any new source attribute the engine reads must also be mirrored to a `*_i` attribute by `_ensure_interpolation_attributes`: interpolation writes only to mirrors, and the modifier composes them.
- Preserve the cached layer schema (`keyframes` / `sorted_frames` / `frame_lookup` / `easing_data` / `easing_samples` / `arc_data`) — `interpolation.py` reads these fields without guards.
- `rebuild_frame()` is surgical: rebuilds stroke data for ONE frame, updates `sorted_frames` + sig. Does NOT rebuild `easing_data`/`easing_samples`/`arc_data` — use `clear()+build()` for easing changes.
- Changes to interpolation output must stay backward-compatible with `bake_utils.apply_interpolation_to_frame`, which writes the same data to FINAL attributes for baking.

## Verification

- `cpp_module.load()` then `get_interpolator()` returns an instance without import error.
- Toggle a GP object on, scrub between two keys → interpolated `*_i` data appears on in-between frames.
- Edit geometry on one key → the next frame change rebuilds only that object's cache (dirty flag), not sibling objects'.
- Add a frame in Dopesheet → cache rebuilds automatically (detected by deferred sig check).
- Remove a frame in Dopesheet → cache rebuilds automatically.
- Toggle modifier or interpolation enabled → no unnecessary rebuilds.
- Preferences: disable `Stroke Guide` in `3D View Header` → header buttons vanish without restart; flip `Prepend`/`Append` → header moves edge; disable `Easing` in `Dopesheet` → button vanishes.
