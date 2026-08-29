# Executable — C++ Stroke Interpolation Module

## Purpose

Native C++ module (`gp_autointerpolate`) implementing the FTP-SC stroke interpolation algorithm plus the per-frame arc/spiral/linear interpolator. Built via CMake + nanobind into a Python extension (`.pyd`/`.so`), then wrapped into a wheel for distribution as a Blender extension dependency.

## Ownership

| Component | Files |
|-----------|-------|
| Binding entry point | `src/interpolate.cpp` (nanobind module + `Interpolator` class + `ftpsc::StrokeMatcher` bindings) |
| Per-frame interpolator | `src/interpolate.cpp` — `Interpolator::process_interpolation[_advanced]`, arc/spiral math, resampling |
| FTP-SC pipeline | `src/stage_one.cpp`, `src/stage_two.cpp`, `src/stroke_matcher.cpp/.h` |
| FTP-SC components | `src/fuzzy_topology.*`, `src/greedy_matcher.*`, `src/salient_point_matcher.*` (topology-only, no `similarity_transform`) |
| Core data | `src/stroke.h` (`ftpsc::Vec2`, `ftpsc::Stroke`) |
| Build | `CMakeLists.txt` (nanobind v2.9.2, `-DENABLE_ABI3=ON` for cp312-abi3, default OFF for cp311) |
| Fast build | `build_fast.bat` — incremental build that skips `cmake` configure when `build/` already exists (avoids re-downloading nanobind/nanoflann) |
| Driver scripts | `../build_autointerpolate.ps1`, `../setup.py`, `../.github/workflows/build.yml` |
| pybind11 backup | `backup_pybind11/` — preserved original pybind11 versions before migration |

## Local Contracts

- **Binding layer: nanobind v2.9.2** via `FetchContent`. NumPy interop uses `FArr = nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>` for input and `make_array()` with `nb::capsule` for output. Access raw data via `.data()` and `.shape(0)` (no bounds-checked element access). STL types auto-converted via `<nanobind/stl/string.h>`, `<nanobind/stl/vector.h>`, `<nanobind/stl/pair.h>`.
- **Empty ndarray safety.** A default-constructed `FArr()` has `ndim() == 0`; calling `.shape(0)` on it is undefined behavior (segfault). Always check `.ndim() > 0` before `.shape(0)` or `.data()`.
- **Stable ABI (abi3) enabled for Python 3.12+.** `CMakeLists.txt` uses `nanobind_add_module(... STABLE_ABI ...)` with manual `Python::SABIModule` linkage fix for nanobind v2.9.2 Windows bug. Floor is 3.12 — nanobind uses 3.12+ APIs (`PyType_FromMetaclass`, `PyObject_GetTypeData`, `vectorcallfunc`). Python 3.11 (Blender 4.3) requires a separate `cp311` wheel; 3.12+ (Blender 4.4+/5.x) is covered by a single `cp312-abi3` wheel.
- **Wheel assembly is decoupled from the C++ build.** CI builds the `.pyd`/`.so` with CMake first, then `setup.py`'s `CMakeBuild` just *locates and copies* the pre-built binary into the wheel. There is no in-tree `pyproject.toml`; `python -m build` is driven by legacy `setup.py`.
- **Two output surfaces on `Interpolator`:**
  - `process_interpolation` / `process_interpolation_advanced` — called **per frame per stroke** by `Addon/core/interpolation.py`. Hot path; this is where binding call overhead and per-access bounds checks matter most.
  - `StrokeMatcher.match[_with_seeds]` — FTP-SC correspondence; called from operators (`correspondence.py`), not per-frame.
- **C++17.** Headers use `#pragma once`. Math types (`Point3D`/`Point2D` in `interpolate.cpp`, `ftpsc::Vec2` in `stroke.h`) are distinct and do not share a header.
- **Optional native deps:** Eigen3 (Stage 2 PCA, `FTPSC_USE_EIGEN`), nanoflann v1.5.5 (k-NN, header-only, fetched), OpenMP (optional parallelism). Eigen absent → fallback PCA path.
- **Cross-platform flags:** Windows `.pyd` (MSVC via Ninja); macOS universal `x86_64;arm64` (deployment target 10.15); Linux `.so` with `-static-libgcc -static-libstdc++` + `$ORIGIN` rpath + optional static OpenMP for cross-distro.
- **Python side loads via `Addon/core/cpp_module.py`** (sole import site) and `Addon/utils/dll_loader.py` (Windows `<pkg>.libs` DLL path fixup for delvewheel-repaired wheels).
- **Debug:** `MatcherConfig.debug` + `debug_level` (1=summary, 2=seeds+matches+identity, 3=CD candidates). Exposed via nanobind; set from `Addon/operators/correspondence.py` when `gp_correspondence._debug_verbose` is True → prints to stderr (Blender System Console).
- **CMake Python discovery.** nanobind uses `find_package(Python ...)` (not `Python3`). Before FetchContent_MakeAvailable(nanobind), set `Python_ROOT_DIR` and `Python_EXECUTABLE` to the Python3 variables, then call `find_package(Python 3.11 REQUIRED COMPONENTS Interpreter Development.Module Development.SABIModule)` to pre-populate `Python::Module` and `Python::SABIModule` targets. The `Development.SABIModule` component is required for stable ABI builds.

## Work Guidance

- **Code style (user preference):** indent 3 spaces, no verbose `@brief/@param/@return` Doxygen boilerplate, no comments stating the obvious — keep comments short and readable. Applies to `src/fuzzy_topology.*` + `src/stroke.h` (scope of cleanup 2026-08-27); extend to other `src/*.cpp/.h` only when touched.
- **Use `build_fast.bat` for incremental builds.** It skips `cmake` configure when `build/CMakeCache.txt` exists, avoiding re-downloads of nanobind (~250MB git clone) and nanoflann on every build. Only delete `build/` when changing cmake flags, Python version, or dependency versions.
- **Full clean build** (`build_autointerpolate.ps1` or manual `Remove-Item -Recurse build/`) is only needed for: first-time setup, changing Python version, changing nanobind version, or debugging cmake issues.
- Keep all nanobind binding in `src/interpolate.cpp`; algorithmic code stays framework-agnostic C++.
- Do not introduce a second binding library alongside nanobind — pybind11 and nanobind cannot share a module (separate type systems). pybind11 backup is in `backup_pybind11/`.
- nanobind API differences from pybind11: `def_readwrite` → `def_rw`, `def_readonly` → `def_ro`, `py::array_t<T>` → `FArr`, `#include <pybind11/numpy.h>` → `<nanobind/ndarray.h>`, `#include <pybind11/stl.h>` → individual `<nanobind/stl/*.h>` headers.
- When changing `Interpolator`'s method signatures, update both the C++ binding block and `Addon/core/interpolation.py` (positional call sites).
- The FTP-SC `match()`/`match_with_seeds()` bindings parse a flat `[x0,y0, ..., -1, x0,y0, ...]` separator format — keep that wire format stable or update `correspondence.py`.
- Test against Blender's bundled Python, not system Python.

## Verification

- `cmake --build` succeeds on Windows (MSVC), macOS (clang, universal), Linux (gcc, static stdc++).
- `python -c "import gp_autointerpolate; gp_autointerpolate.Interpolator(); gp_autointerpolate.StrokeMatcher()"` loads cleanly under target Python.
- Per-frame path: `Interpolator().process_interpolation(...)` returns a non-empty `np.float32` array for matched point counts.
- **abi3 verification:** `dumpbin /dependents <pyd>` must show `python3.dll` (not `python3XX.dll`). Import test on Python 3.14+ must pass. Python 3.11 import is expected to fail (nanobind 3.12+ floor).
