# PolyVectorization-master baseline run (puppy.png)

Source: CircleCI baseline job (`polyvector_master_linux`) running `Vectorize/PolyVectorization-master/build/polyvector_thing` on `sample_inputs/puppy.png`.

## Key environment details (from CMake output)

- Compiler: GNU 9.4.0
- OpenMP: found (v4.5)
- OpenCV: 4.2.0 (system `/usr`)
- Boost: 1.71.0

## High-level run summary

- Input: `../sample_inputs/puppy.png`
- Connected components found: 17
- Component 0 nnz: 27570
- Curves traced (component 0): 8671
- Reeb graph (component 0): 17342 vertices, 18292 edges
- Loops removal: found 4074 edges to remove

## Timings present in log

These are the explicit timings printed by the baseline executable:

- `Computing Reeb graph... done in 17.9691 seconds.`
- `topoGraphEmbedding ... done in 36.6748 seconds.`
- `All done in 36.8084 seconds.` (this appears to correspond to a phase within the pipeline for component 0; in the baseline output it prints this after the long embedding stage output begins)

## Estimated end-to-end time (rough)

The baseline log does not print one single “total runtime” line.
However, based on the dominant timed sections above, component 0 alone accounts for roughly:

- Reeb graph: ~18s
- Topo embedding: ~37s
- Plus additional graph processing / splitting / simplify phases: typically a few seconds to tens of seconds

So a realistic estimate for the full `puppy.png` baseline run is:

- **~60–120 seconds total** (roughly 1–2 minutes), dominated by component 0.

## Output

- SVG output generated: `../sample_inputs/puppy.png.svg`
- Note: SVG initially missing `xmlns:xlink` even though it uses `xlink:href`; we patched this for viewer compatibility.

---

## Full log excerpt (user-provided)

```text
<PASTE FULL LOG HERE IF DESIRED>
```
