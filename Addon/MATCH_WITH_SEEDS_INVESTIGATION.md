# FTP-SC Match With Seeds Investigation

## Overview

This document analyzes how user-provided seeds (linked stroke pairs) should be integrated into the FTP-SC matching algorithm, based on the Yang18-SCA paper and the current C++ implementation.

---

## How the Algorithm Works (Per Paper)

### The Greedy Propagation Framework

```
1. SI-component: Find initial seed(s) - the best matching pair(s)
2. CD-component: From each seed, derive candidate pairs using α-topology
3. Add candidates to max-heap (ordered by matching degree / confidence)
4. WHILE heap not empty:
   - Pop best candidate
   - IF both strokes unmatched:
     - Add to correspondence (new seed)
     - Run CD-component to derive more candidates
     - Push new candidates to heap
```

### Key Insight from Paper (Section 3.3)

> "The FTP-SC technique enables us to incorporate user correction in an easy way, 
> i.e., simply replacing the initial seed in the SI-component with the user-specified one(s).
> Such incorporation makes the user intervention very efficient, since it allows 
> one user correction to have more influence and control over the correspondence results."

**Translation:** User-linked pairs should be used as **initial seeds**, which then **propagate** to fix neighboring matches via the CD-component.

---

## Current C++ Implementation

### `match()` - Standard matching
```cpp
Correspondence run_stage_one(initial_strokes, target_strokes) {
    // SI: Find best global pair as seed
    seeds = si_component(initial, target, empty_correspondence);
    
    // Greedy: propagate from seeds
    for each seed:
        add_match(seed)
        candidates = cd_component(seed)  // α-topology neighbors
        push to heap
    
    while heap not empty:
        pop best
        if unmatched: add_match, derive more candidates
}
```

### `match_with_seeds()` - With user seeds ✅ EXISTS!
```cpp
MatchingResult match_with_seeds(initial_strokes, target_strokes, manual_seeds) {
    
    // 1. Pre-populate correspondence with manual seeds
    for each manual_seed:
        add_match(manual_seed)
    
    // 2. Run normal Stage 1 (SI finds MORE seeds)
    stage_one_result = run_stage_one(initial, target)
    
    // 3. MERGE: manual seeds take priority
    merged = Correspondence()
    for each manual_seed:
        merged.add_match(seed)  // Manual seeds FIRST
    
    for each stage1_match:
        if not conflicting with manual:
            merged.add_match(match)
    
    // 4. Stage 2 propagates from merged correspondence
    if enable_stage_two:
        final = run_stage_two(initial, target, merged)
}
```

---

## The Problem: Current Python Implementation

### What Python Does Now (WRONG)
```python
# In run_correspondence_match():

# 1. EXCLUDE linked strokes from data sent to C++
s1_filtered = [s for i, s in enumerate(s1) if i not in strokes_to_exclude_1]
s2_filtered = [s for i, s in enumerate(s2) if i not in strokes_to_exclude_2]

# 2. Call C++ match() with FILTERED data (no seeds!)
result = matcher.match(S1_filtered, S2_filtered)

# 3. Manually append linked pairs to results
result_matches = linked_for_this_pair + matched_pairs
```

### Why This Is Wrong

1. **Linked pairs don't propagate** - CD-component never runs on user seeds
2. **Topology is broken** - α-connectivity is computed on filtered strokes, missing the linked ones
3. **No cascading fixes** - Paper says 1 user fix can fix many neighbors; current approach gets zero cascading benefit

---

## The Fix: Use `match_with_seeds()`

### Step 1: Expose in Python Bindings

Add to `interpolate.cpp`:
```cpp
.def("match_with_seeds", [](ftpsc::StrokeMatcher &self,
                            py::array_t<float> initial_strokes,
                            py::array_t<float> target_strokes,
                            py::list seeds_list) {
    
    // Parse strokes (same as match())
    std::vector<ftpsc::Stroke> init_strokes = parse_strokes(initial_strokes);
    std::vector<ftpsc::Stroke> targ_strokes = parse_strokes(target_strokes);
    
    // Parse seeds
    std::vector<std::pair<int, int>> seeds;
    for (auto item : seeds_list) {
        auto tuple = item.cast<py::tuple>();
        seeds.emplace_back(tuple[0].cast<int>(), tuple[1].cast<int>());
    }
    
    return self.match_with_seeds(init_strokes, targ_strokes, seeds);
})
```

### Step 2: Update Python Matching Code

```python
def run_correspondence_match(...):
    # Collect ALL strokes (don't filter!)
    s1, indices1 = collect_strokes_2d(gp_obj, layer_idx, frame1)
    s2, indices2 = collect_strokes_2d(gp_obj, layer_idx, frame2)
    
    S1 = to_cpp_strokes(s1)
    S2 = to_cpp_strokes(s2)
    
    # Build seeds from linked constraints
    seeds = []
    for constraint in link_constraints:
        if matches_this_frame_pair(constraint):
            seeds.append((stroke1_idx, stroke2_idx))
    
    # Call C++ with seeds
    if seeds:
        result = matcher.match_with_seeds(S1, S2, seeds)
    else:
        result = matcher.match(S1, S2)
    
    # Results already include seeds + propagated matches
    matches = result.get_matches()
```

---

## How Confidence/Quality Works

### Matching Degree (Cost)

```cpp
double compute_matching_degree(Stroke S, Stroke T) {
    // 1. Align strokes using similarity transform
    // 2. Compute point-to-point distances
    // 3. Return average distance (lower = better match)
}
```

### Heap Ordering

The algorithm uses a **max-heap** ordered by matching degree:
- **High confidence** pairs are popped first
- **Low confidence** pairs only used if nothing better available

### Stage 2 Refinement

Stage 2 uses **salient points** (corners) for additional validation:
- Matches from Stage 1 are treated as seeds
- CD-component finds neighbors using corner-based topology
- Can discover matches Stage 1 missed

---

## Success Measurement

### Current: Average Cost
```cpp
result.final_cost = result.final_correspondence.average_cost();
```
Lower average cost = better overall matching.

### Potential Improvements

1. **Return per-match costs** to Python for visualization
2. **Highlight low-confidence matches** in UI (user might want to link those)
3. **Track improvement** from user seeds vs. auto-only

---

## Summary

| Aspect | Current (Wrong) | Correct (Per Paper) |
|--------|-----------------|---------------------|
| Linked pairs | Excluded from C++ | Passed as seeds |
| Propagation | None | CD-component runs on user seeds |
| Topology | Broken (missing strokes) | Complete |
| Cascading fixes | 0 | Many (paper's key benefit) |
| C++ function | `match()` | `match_with_seeds()` |

---

## Action Items

1. [ ] Add `match_with_seeds` to Python bindings (`interpolate.cpp`)
2. [ ] Recompile C++ module
3. [ ] Update `run_correspondence_match()` to use seeds instead of filtering
4. [ ] Test cascading fix behavior (link 1, see many fix)
5. [ ] Consider exposing per-match costs for confidence visualization
