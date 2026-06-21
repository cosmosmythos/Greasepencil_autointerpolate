# GP Depsgraph Event Map

## Test Environment
- **Blender:** 5.0
- **Object:** "Stroke" (GreasePencil)
- **Layer:** "Lines"
- **Frames:** [1, 80]
- **Extension:** gp_auto_interpolate (installed as bl_ext)

---

## Test Results

### Part 1: What fires depsgraph updates?

| Action | GP update? | geom | xform | OBJ update? | geom | xform |
|--------|-----------|------|-------|-------------|------|-------|
| frame_set (playhead move) | NO | - | - | NO | - | - |
| Rapid scrub (frame_set ×20) | NO | - | - | NO | - | - |
| frame_set(current) no-op | NO | - | - | NO | - | - |
| **frames.new (add keyframe)** | **YES** | **True** | False | **YES** | **True** | False |
| **frames.remove (delete keyframe)** | **YES** | **True** | False | **YES** | **True** | False |
| layer.hide = True | YES | True | False | YES | True | False |
| layer.hide = False | YES | True | False | YES | True | False |
| modifier.show_viewport OFF | NO | - | - | NO | - | - |
| modifier.show_viewport ON | NO | - | - | NO | - | - |
| interpolation_enabled OFF | NO | - | - | NO | - | - |
| interpolation_enabled ON | NO | - | - | NO | - | - |
| view_layer.update() | YES | True | True | YES | True | False |

### Part 2: Keyframe Operations (the ones that matter)

| Action | GP fires? | geom |
|--------|----------|------|
| Add frame 40 | YES | True |
| Remove frame 40 | YES | True |
| Move keyframe 80→60 (remove+add) | YES | True |
| Move keyframe 80→55 (remove+add) | YES | True |
| frame_set(30) AFTER keyframe move | NO | - |

### Key Findings

1. **frame_set NEVER fires depsgraph.** Moving the playhead does NOT trigger depsgraph_update_post. The only way to detect playhead movement is frame_change_post.

2. **frames.new / frames.remove fire depsgraph with geom=True.** Adding or removing a keyframe fires a geometry update on both the GreasePencil datablock and the Object.

3. **Modifier toggle fires NOTHING.** Changing modifier.show_viewport does not trigger depsgraph.

4. **Interpolation toggle fires NOTHING.** Changing scene.gp_interpolation_enabled does not trigger depsgraph.

5. **layer.hide fires depsgraph with geom=True.** Toggling layer visibility fires geometry updates.

6. **view_layer.update() fires depsgraph with geom=True AND xform=True.** This is the strongest signal — it always fires.

---

## THE BUG: Why the addon doesn't detect keyframe changes

### The detection chain (current code)

```
depsgraph fires
  → on_depsgraph_update handler
    → _targets_by_gp_data(targets)  ← builds dict with Python object keys
      → targets_by_gp.get(update_id) ← FAILS: identity mismatch
        → handler exits without doing anything
```

### Root cause: Python object identity

`_targets_by_gp_data` builds a dict keyed by `gp_data` (the Python object):
```python
gp_data = ob.data  # Python object
by_data.setdefault(gp_data, [])  # key = Python object
```

But the depsgraph returns a **different Python wrapper** for the same datablock:
```python
update_id = getattr(update, "id", None)  # different Python wrapper
targets_by_gp.get(update_id)  # FAILS: different object, same data
```

This is a known Blender behavior — depsgraph returns fresh Python wrappers, not the same object you stored.

### Result

The handler **silently does nothing** for ALL updates. It never reaches the geometry check, never marks dirty, never triggers rebuild. The entire cache invalidation system is dead.

### What SHOULD happen

When a keyframe is added/removed/moved (frames.new / frames.remove):
1. Depsgraph fires with geom=True
2. Handler should detect this
3. Cache should be cleared and rebuilt (same as Refresh button)

---

## What the Refresh button does

```python
cache.clear(gp_obj.name)   # clear the cache
cache.build(gp_obj)         # rebuild from current data
```

That's it. Two lines. This is what should happen automatically when a keyframe changes.

---

## What the older addon did

The older addon (Addon/OLDER/) had a different approach:
- It detected keyframe selection changes in the Dopesheet
- When a keyframe was selected/moved, it forced `scene.frame_current = selected_frame`
- This triggered frame_change_post, which triggered interpolation
- It was explicit and predictable — not reliant on depsgraph matching

---

## Proposed fix

Fix the identity mismatch in `_targets_by_gp_data` by using name-based lookup instead of object identity. Then the handler will actually detect geometry changes and can rebuild the cache.

The simplest approach: change `targets_by_gp.get(update_id)` to use the datablock's name instead of the object itself.
