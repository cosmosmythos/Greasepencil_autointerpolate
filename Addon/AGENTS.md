# Addon — GP Auto Interpolate

## Purpose

Blender addon package for Grease Pencil stroke interpolation. Registers operators, UI panels, and core engine on startup. Users install this as a Blender extension.

## Ownership

- Root package: `Addon/__init__.py`
- Manifest: `blender_manifest.toml`
- Blend file: `Auto-Interpolate (c).blend` (reference/template asset)
- Entry scripts: `gp_correspondence.py` (header UI + `_debug_verbose` / `_linking_history` / JSONL at `~/gp_linking_history.jsonl`), `stroke_guide.py`

## Local Contracts

- All sub-modules must expose `register()` and `unregister()` functions
- Core, operators, panels, and utils are loaded via `Addon/__init__.py`
- Wheels (prebuilt `.whl` C++ modules) are installed from `wheels/` at runtime, not committed

## Work Guidance

- Follow Blender addon conventions: `bl_info` dict in `__init__.py`, `register()`/`unregister()` lifecycle
- Keep operators self-contained with their own `register()`/`unregister()`
- Utils are shared helpers; avoid circular imports between sub-packages
- The `.blend` file is a reference asset, not runtime data
- Clear `__pycache__/` under `Addon/` after local tests to avoid stale bytecode

## Verification

- Blender loads the addon without errors (check Blender console)
- `blender --background --python-expr "import addon_utils; print(addon_utils.check('GP Auto Interpolate'))"` verifies registration

## Child DOX Index

| Child | Scope |
|-------|-------|
| `core/AGENTS.md` | Core engine: C++ module loading, cache, interpolation pipeline, registry, depsgraph handlers |
| `operators/AGENTS.md` | Blender operators: bake, toggle, refresh, easing, correspondence, arc, layer, line art |
| `utils/AGENTS.md` | Shared utilities: easing curves, arc data, visibility, vectorization wrapper, DLL loader |
