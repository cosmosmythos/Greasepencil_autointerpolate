# Vectorize — C++ Line Art Vectorization Module

## Purpose

Native C++ module (`gp_linevector`) implementing the PolyVector algorithm (Bessmeltsev & Solomon 2019) for line art vectorization. Built via CMake into a Python wheel. Heavier dependencies than Executable: OpenCV, Eigen3, Boost.

## Ownership

| Component | Files |
|-----------|-------|
| Entry point | `polyvector_pybind.cpp` |
| Core algorithm | `polyvector_core.cpp/.h` |
| Topology | `graph_typedefs`, `AlmostReebGraph`, `ChainDecomposition`, `TopoGraphEmbedding` |
| Optimization | `Optimizer`, `TotalEnergy`, `l2_regularizer`, `polynomial_energy`, `LBFGS/` |
| Geometry | `CircularSegment`, `intersections`, `ScanConvert` |
| Preprocessing | `Simplify`, `Smooth`, `SplitEmUp`, `FillHole`, `RemoveShortBranches` |
| Graph ops | `ContractDeg2`, `ContractLoops`, `ContractLoops2`, `FindRoots`, `findSingularities` |
| Tracing | `traceAuto`, `greedyTrace` |
| Build | `CMakeLists.txt`, `CMakeLists_py314test.txt` |

## Local Contracts

- Entry point is `polyvector_pybind.cpp` (pybind11 module definition)
- Requires OpenCV 5.x, Eigen3, Boost at build time
- `LBFGS/` is vendored third-party; do not modify

## Work Guidance

- CMake finds dependencies via `find_package()`; ensure CI images have them installed
- **OpenCV 5.x required** — 4.11.0 rejects VS2026 (MSVC 1951). CI downloads pre-built 5.0.0 Windows binaries; macOS/Linux use brew/apt.
- PolyVector algorithm is research-grade; changes may affect output quality
- Test with representative line art inputs before merging topology changes

## Verification

- `cmake --build` succeeds with all dependencies resolved
- Module imports without error: `python -c "import gp_linevector"`
- Vectorization output matches reference results for test inputs
