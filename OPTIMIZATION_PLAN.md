# Interpolation Optimization Plan

Two optimizations to reduce per-frame cost during playback/scrub.

---

## Optimization 1: Incremental Cache Rebuild

### Problem

`cache.build()` re-reads ALL frames on ALL layers via `foreach_get`. Drawing on frame 48 re-reads frames 1, 24, and 48 — 2 of 3 are wasted. Each `foreach_get` is a Blender API call that crosses the Python→C boundary.

### Goal

When only one frame changes, do `foreach_get` on that frame only (5 calls instead of 500).

### Changes

#### `Addon/core/cache.py` — add `rebuild_frame()`

New function that re-reads ONE frame's stroke data into the existing cache entry:

1. Look up existing `layer_cache` from `cache_registry`
2. Re-read ONLY `frame_num`'s attributes via `foreach_get` (position, opacity, radius, handle_left, handle_right)
3. Replace `keyframes[layer_idx][frame_num]` with new stroke data
4. Re-sample easing for `frame_num`
5. Re-fetch arc params for `frame_num`
6. Update `sorted_frames` if `frame_num` was added/removed
7. Update `frame_lookup[frame_num]` reference
8. Update `_keyframe_signature`
9. Return `True` on success, `False` if cache doesn't exist (needs full build)

Signature:
```python
def rebuild_frame(gp_obj, layer_idx, frame_num):
    """Re-reads ONE frame's stroke data into the existing cache entry.
    Returns True on success, False if full rebuild needed.
    """
```

The frame removal case (frame exists in cache but not in Blender) deletes the frame from all cache sub-dicts and re-sorts `sorted_frames`.

#### Callers to update

| Caller | File:Line | Current | Change |
|---|---|---|---|
| Easing curve edit | `npanel_handlers.py:340-341` | `clear()` + `build()` | `rebuild_frame()` for the specific keyframe |
| Arc settings | `arc_popup.py:113-114` | `clear()` + `build()` | `rebuild_frame()` for affected keyframes |
| Easing popup | `easing_popup.py:94-95` | `clear()` + `build()` | `rebuild_frame()` for affected keyframes |
| Easing direct | `easing_direct.py:162-163,175-176` | `clear()` + `build()` | `rebuild_frame()` for the specific keyframe |

Callers that keep full `build()` (uncertain what changed):
- `interpolation.py:148` — dirty flag (unknown change source)
- `interpolation.py:166` — keyframe sig mismatch (frame list changed, unclear which)
- `correspondence.py:262` — stroke reordered
- `refresh.py:35` — user intent: full refresh
- `toggle.py:40` — first enable
- `layer_filter.py:93` — filter changed

### Performance impact

- **Before:** Single frame change → 5 layers × 20 frames × 5 attrs = 500 `foreach_get` calls
- **After:** Single frame change → 1 frame × 5 attrs = 5 `foreach_get` calls
- **Savings:** 99% reduction in attribute reads for single-frame changes

---

## Optimization 2: Batch C++ Calls Per Layer

### Problem

Python loops over strokes, making 3-5 C++ calls per stroke. For 50 strokes: 150-250 pybind11 calls with per-call overhead (argument marshaling, vector allocation, GIL).

### Goal

One C++ call per layer that processes all strokes at once. Eliminate per-stroke Python loop and pybind11 boundary crossings.

### Changes

#### `Executable/src/interpolate.cpp` — add `process_layer_batch()` to `Interpolator`

New method that accepts pre-concatenated arrays + offset table:

```cpp
py::array_t<float> process_layer_batch(
    int current_frame,
    int prev_frame,
    py::array_t<float> prev_positions,      // concatenated [s0_xyz, s1_xyz, ...]
    int next_frame,
    py::array_t<float> next_positions,      // same format
    py::array_t<int32_t> stroke_offsets,     // [start0, start1, ..., total_points]
    py::array_t<float> easing_curve,         // 64 samples
    float arc_amount,
    float arc_direction,
    bool use_spiral,
    py::array_t<float> stroke_normals,       // [n0x,n0y,n0z, n1x,...] per stroke
    py::array_t<float> prev_opacity,         // concatenated scalars
    py::array_t<float> next_opacity,
    py::array_t<float> prev_radius,
    py::array_t<float> next_radius
);
```

Returns one concatenated `py::array_t<float>` with all interpolated positions.

Internal algorithm:
1. Compute `t = apply_easing((current - prev) / (next - prev), easing_curve)`
2. For each stroke (from `stroke_offsets`):
   - Extract prev/next position slices using offsets
   - Resample both to prev's point count (reuses existing `resample_position_stroke`)
   - Interpolate (lerp or arc) using the stroke's normal
   - Write result into output buffer at the correct offset
3. Return concatenated output array

The output array is pre-allocated. Each stroke writes into its own slice — no dynamic allocation per stroke.

#### pybind11 binding

```cpp
.def("process_layer_batch", &Interpolator::process_layer_batch,
     py::arg("current_frame"), py::arg("prev_frame"),
     py::arg("prev_positions"), py::arg("next_frame"),
     py::arg("next_positions"), py::arg("stroke_offsets"),
     py::arg("easing_curve"), py::arg("arc_amount"),
     py::arg("arc_direction"), py::arg("use_spiral"),
     py::arg("stroke_normals"),
     py::arg("prev_opacity"), py::arg("next_opacity"),
     py::arg("prev_radius"), py::arg("next_radius"))
```

Add to `PYBIND11_MODULE` block at end of `interpolate.cpp`.

#### `Addon/core/interpolation.py` — replace per-stroke loop with batch call

New helper function:
```python
def concat_stroke_data(strokes, attr_name):
    """Concatenate one attribute from all strokes into a flat array + offset table.

    Returns (flat_array, offsets) where:
      flat_array: np.float32 concatenated data
      offsets: np.int32 [start0, start1, ..., total_len] — slice boundaries
    """
    arrays = []
    offsets = [0]
    for stroke in strokes:
        arr = stroke[attr_name]
        arrays.append(arr)
        offsets.append(offsets[-1] + len(arr))
    return np.concatenate(arrays).astype(np.float32), np.array(offsets, dtype=np.int32)
```

Replace the per-stroke loop in `process_object()` (lines 231-304):

```python
# Before (current):
for stroke_idx, prev_stroke in enumerate(prev_strokes):
    if stroke_idx >= len(next_strokes):
        continue
    interpolated_positions = interpolator.process_interpolation(...)
    interpolated_opacity = interpolator.process_interpolation(...)
    interpolated_radius = interpolator.process_interpolation(...)
    interpolated_hl = interpolator.process_interpolation(...)
    interpolated_hr = interpolator.process_interpolation(...)
    # ... append each to lists ...

# After (batch):
prev_pos_concat, offsets = concat_stroke_data(prev_strokes, 'position')
next_pos_concat, _ = concat_stroke_data(next_strokes, 'position')

# Normals (one per stroke)
normals = np.concatenate([
    calculate_stroke_normal(s['position']) for s in prev_strokes
]).astype(np.float32)

# Scalars
prev_op, _ = concat_stroke_data(prev_strokes, 'opacity')
next_op, _ = concat_stroke_data(next_strokes, 'opacity')
prev_rad, _ = concat_stroke_data(prev_strokes, 'radius')
next_rad, _ = concat_stroke_data(next_strokes, 'radius')

result = interpolator.process_layer_batch(
    current_frame, prev_frame, prev_pos_concat,
    next_frame, next_pos_concat,
    offsets, easing_samples,
    arc_amount, arc_direction, use_spiral, normals,
    prev_op, next_op, prev_rad, next_rad
)
```

The result is already concatenated — pass directly to `write_interpolated_data_to_frame()`.

Handle data: if all prev/next handle point counts match, include in the batch call. If any stroke has mismatched handle counts, fall back to per-stroke handle interpolation for that stroke only. Alternatively, always pass handle data and let C++ skip mismatched strokes internally.

#### `Addon/operators/bake_single.py` — same batch pattern

Replace per-stroke loop (lines 189-259) with batch call using same `concat_stroke_data()` helper. Results go into `all_positions`, `all_opacities`, etc. via `.extend()` on the batch result.

#### `Addon/operators/bake_range.py` — same batch pattern

Replace per-stroke loop (lines 223-332) with batch call. The per-group caching (lines 220-254) stays — it pre-caches numpy arrays once per `(start_frame, end_frame)` pair. The batch call replaces the inner per-stroke loop.

### Performance impact

- **Before:** 50 strokes × 5 attrs = 250 pybind11 calls, 250 vector allocations
- **After:** 1 batch call, 1 allocation per attribute type
- **Savings:** ~99% reduction in Python↔C++ boundary crossings, ~90% reduction in heap allocations

---

## Implementation Order

| Phase | What | Risk | Effort |
|---|---|---|---|
| **1a** | Add `rebuild_frame()` to `cache.py` | Low | 1-2h |
| **1b** | Wire `rebuild_frame()` into operator callers | Low | 1h |
| **2a** | Add `process_layer_batch()` to C++ `Interpolator` | Medium | 3-4h |
| **2b** | Add pybind11 binding | Low | 15m |
| **2c** | Add `concat_stroke_data()` helper to `interpolation.py` | Low | 30m |
| **2d** | Replace per-stroke loop in `process_object()` with batch | Medium | 2h |
| **2e** | Update `bake_single.py` and `bake_range.py` | Low | 1-2h |
| **3** | Test: draw, scrub, move keys, bake, toggle, easing, arc | — | 1-2h |

**Total: 10-14 hours**

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `rebuild_frame()` misses edge case | Stale cache for one frame | Returns `False` to trigger full `build()` fallback |
| Batch C++ produces different results than per-stroke | Visual regression | Debug flag to run both paths and compare output |
| Handle mismatch in batch mode | Handles not interpolated | C++ fills with prev handle data when counts differ |
| Bake output differs | Wrong baked animation | Same verification — compare batch vs per-stroke |
