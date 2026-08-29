# Operators — GP Auto Interpolate

## Purpose

Blender operator modules for GP Auto Interpolate. Each file defines one operator class with `register()`/`unregister()` functions.

## Ownership

| File | Operator |
|------|----------|
| `toggle.py` | Toggle interpolation on/off |
| `refresh.py` | Refresh/recache stroke data |
| `bake_single.py` | Bake interpolation for current frame |
| `bake_range.py` | Bake interpolation over frame range |
| `easing_popup.py` | Easing curve popup UI |
| `easing_direct.py` | Direct easing application |
| `arc_popup.py` | Arc selection popup |
| `correspondence.py` | Manual stroke correspondence (link / unlink, seeded matching) — Auto-Link (`gpcorr.match`) removed |
| `layer_filter.py` | Layer visibility filtering |
| `import_lineart.py` | Import Line Art strokes |

## Local Contracts

- Every operator module must expose `register()` and `unregister()`
- Operators must be self-contained; prefer importing from `utils/` over `core/` for pure helpers
- Use `bl_idname`, `bl_label`, `bl_description` class attributes consistently

## Work Guidance

- Follow Blender operator naming: `GP_AUTOINTERPOLATE_OT_<action>`
- Keep operator logic in `execute()` or `invoke()`, delegate heavy work to `core/`
- Register operators in `Addon/__init__.py` via module-level `register()` calls

## Verification

- Each operator registers without error
- Operators appear in Blender search (F3) under their label
