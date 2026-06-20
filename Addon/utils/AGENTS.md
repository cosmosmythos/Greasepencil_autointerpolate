# Utils — GP Auto Interpolate

## Purpose

Shared utility modules for GP Auto Interpolate. Easing curves, arc data, visibility/scrub detection, vectorization wrapper, DLL loading, and overlay helpers.

## Ownership

| File | Role |
|------|------|
| `easing.py` | Easing curve system (complex, ~450 lines) |
| `arc_data.py` | Arc stroke data structures |
| `visibility.py` | Modifier on/off rule + scrub detection; **owns the primary per-frame handler** `on_frame_change` that drives `interpolation.process_scene` |
| `vectorization.py` | PolyVector vectorization wrapper |
| `dll_loader.py` | Windows DLL loader for wheel dependencies |
| `linked_stroke_overlay.py` | Linked stroke overlay rendering |
| `correspondence_utils.py` | Correspondence helper functions |

## Local Contracts

- Utilities must not import from `core/` or `operators/` (keep dependency direction one-way)
  - Exception: `visibility.py` imports `interpolation` and `cache` from core at call time (lazy) because it owns the per-frame entry point. Do not add further core imports from utils.
- `dll_loader.py` is Windows-only; must be a no-op on other platforms
- `easing.py` is the most complex utility; changes require careful review

## Work Guidance

- Keep utils stateless where possible
- Easing system uses custom data structures; maintain backward compatibility with saved presets
- Visibility system hooks into depsgraph events from `core/`
- Visibility rule: modifier viewport ON only during playback / scrub / render; OFF otherwise. Never write `show_render` from the play/stop path (only `on_render_pre`/`on_render_post`) — it triggers a depsgraph update that re-invalidates the cache.

## Verification

- Easing curves render correctly in the UI
- DLL loader resolves dependencies on Windows
- Vectorization produces valid stroke data
