# Nanobind Migration Plan — `gp_autointerpolate`

> Status: **Proposal / plan of record**. No code changed yet. Read alongside `Executable/AGENTS.md` (binding/build facts) and `Addon/core/interpolation.py` (Python call sites).
>
> Research baseline: Nanobind **2.9.2** (Sep 2025) latest stable as of writing; pybind11 **v3.0.1** is the current binding. Sources cited inline.

## 1. Why migrate — the three real wins for *this* codebase

### 1.1 Collapse the dual-Python wheel matrix (strongest reason)

The CI matrix in `.github/workflows/build.yml` builds **two wheels per platform** (`3.11.9` and `3.13.9`) because `setup.py` declares no stable ABI. Blender's wheel-tag matcher then rejects mismatched tags ([blender/blender#130561](https://projects.blender.org/blender/blender/issues/130561); [blendercam#282](https://github.com/vilemduha/blendercam/issues/282): *"This Python version (3.13) isn't compatible with (3.11)"*), which is exactly what the dual build works around.

Nanobind has first-class **abi3 / stable-ABI** support via `NB_ABI_COMPATIBILITY` ([CMake API ref](https://nanobind.readthedocs.io/en/latest/api_cmake.html)). A single `cp311-abi3` wheel loads on **every CPython ≥ 3.11** — confirmed by the abi3 tagging rule ([pyodide discussion](https://github.com/pyodide/pyodide/discussions/4377)). With Blender 4.x on 3.11 and Blender 5.x on 3.13 ([OSArch](https://community.osarch.org/discussion/3310/blender-5-1-alpha-now-switched-python-from-3-11-to-3-13)), one abi3 wheel covers both. The 3.14 experimental path (`CMakeLists_py314test.txt`, `build_py314_experimental.yml`) is also absorbed for free.

**Matrix reduction:** 6 build jobs (3 OS × 2 Py) → 3 (one per OS), plus the experimental 3.14 job disappears. The `sed`-renaming hacks in `build_py314_experimental.yml` (`cp314-abi3` → `cp314-cp314`) become unnecessary.

⚠️ Caveat to validate early: some Blender versions had bugs validating abi3 tags ([#130561](https://projects.blender.org/blender/blender/issues/130561)). **Phase 0 (§6) exists to de-risk this before committing.**

### 1.2 Zero-copy NumPy on the hot path

`Addon/core/interpolation.py` calls `Interpolator.process_interpolation[_advanced]` **once per stroke per frame** during playback/scrubbing. Today the C++ side receives `py::array_t<float>` and reads via `.unchecked<1>()`, which — despite the name — still does a dimension bounds check on **every** `ptr(i)` access ([pybind11#584](https://github.com/pybind/pybind11/issues/584), [pybind11#2600](https://github.com/pybind/pybind11/issues/2600)). Tight loops in `resample_position_stroke` (interpolate.cpp:257-262), `is_position_data` (interpolate.cpp:228-233), and `apply_easing` pay this per element.

Nanobind's `nb::ndarray<float, nb::numpy, nb::c_contig>` gives a **typed raw pointer** with shape/contiguity validated **once at the boundary**, not per access ([ndarray docs](https://nanobind.readthedocs.io/en/latest/ndarray.html)). Inner loops become plain `float*` pointer arithmetic. Combined with lower base call overhead (~⅛ of pybind11 per the [nanobind README](https://github.com/wjakob/nanobind)), this is a measurable win on a path that runs every frame.

### 1.3 Build/dev ergonomics

- ~2–3× faster compiles and ~3× smaller binaries ([nanobind why](https://nanobind.readthedocs.io/en/latest/why.html)) — matters because CI builds twice today.
- `nanobind-packaging` (scikit-build-core backend) replaces the bespoke `setup.py` + `CMakeBuild` binary-copy dance with a standard `pyproject.toml` ([packaging docs](https://nanobind.readthedocs.io/en/latest/packaging.html)). `setup.py`'s 100-line `CMakeBuild` that recursively searches for the `.pyd` goes away.

### 1.4 What migration will *not* fix

- The FTP-SC algorithm cost itself (`stage_one`/`stage_two`) — that's native C++ either way.
- Python-side cache cost (`Addon/core/cache.build`) — that's a separate concern; see the `source_signature` removal already done.
- The `.unchecked` overhead is real but small in absolute terms for typical stroke sizes. Don't sell this as a 10× speedup; it's a per-call constant-factor win on a hot path.

---

## 2. Scope and ground rules

**In scope:** the `gp_autointerpolate` module only (`Executable/`). `gp_linevector` (`Vectorize/`) is a separate module with its own workflow (`build_polyvector.ps1`) and is **explicitly out of scope** for this plan.

**Hard constraint — all-or-nothing per module.** Pybind11 and nanobind use **incompatible type systems** and cannot share a module ([nanobind discussion #83](https://github.com/wjakob/nanobind/discussions/83)). There is no incremental "bind one function at a time" path within a single `.pyd`. Migration is therefore done as one atomic swap of `interpolate.cpp`'s binding block + CMake, validated by a behavior-equivalence test harness before the old code is deleted.

**Behavior preservation is the success criterion.** Interpolation output (float arrays for position/opacity/radius/handles) and FTP-SC match results must be bit-identical (or within float epsilon) to the pybind11 module on the same inputs. The Python-facing API (`Interpolator`, `StrokeMatcher`, `MatcherConfig`, `MatchingResult`) must remain import-compatible so `Addon/core/cpp_module.py` and `Addon/core/interpolation.py` change minimally.

---

## 3. Current binding surface — inventory (what must be ported)

From `Executable/src/interpolate.cpp`, the entire pybind11 surface is:

| C++ symbol | Binding | Used by (Python) |
|---|---|---|
| `Interpolator` (class) | `.def(py::init<>())` | `cpp_module.get_interpolator()` |
| `Interpolator::process_interpolation` | 8 args, 2 defaulted (`data_type="auto"`, `easing_curve=none`) | `interpolation.py:241,251,260,273,285` |
| `Interpolator::process_interpolation_advanced` | 12 args, none defaulted | `interpolation.py:233` |
| `ftpsc::MatcherConfig` (class) | `py::init<>`, 6 `.def_readwrite` | correspondence ops |
| `ftpsc::MatchingResult` (class) | 7 `.def_readonly`, 1 `.def("get_matches", lambdcast)` | correspondence ops |
| `ftpsc::StrokeMatcher` (class) | `py::init<>()`, `py::init<MatcherConfig>`, `match` (lambda), `match_with_seeds` (lambda), `get_config`, `set_config` | `correspondence.py` |

**Lambda bindings to watch:** `match` and `match_with_seeds` (interpolate.cpp:485-613) do nontrivial work in the binding layer — they parse the flat `[x0,y0,…,-1,…]` separator format into `std::vector<ftpsc::Stroke>` and convert a `py::list` of tuples into `std::vector<std::pair<int,int>>`. These must be ported carefully; the wire format is a contract with `correspondence.py`.

**Default-argument handling:** pybind11 uses `py::arg("...") = default`. Nanobind uses `nb::arg("...") = default` or `nb::arg().none()` — semantics are close but `py::none()` → `nb::none()` and theRV-conversion rules differ slightly ([porting guide](https://nanobind.readthedocs.io/en/latest/porting.html)).

---

## 4. Nanobind porting specifics (from the official porting guide)

Authoritative reference: [Porting guide — nanobind docs](https://nanobind.readthedocs.io/en/latest/porting.html). Summary of changes that touch *our* code:

### 4.1 Headers & namespace
```cpp
// Was:
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
namespace py = pybind11;

// Becomes:
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl.h>          // for std::vector, std::pair, std::string
#include <nanobind/stl/detail/...> // as needed for list/tuple casts
namespace nb = nanobind;
```

### 4.2 Module macro
```cpp
// Was: PYBIND11_MODULE(gp_autointerpolate, m) { ... }
// Becomes:
NB_MODULE(gp_autointerpolate, m) { ... }
```

### 4.3 Class & method bindings — near-identical
`py::class_<T>` → `nb::class_<T>`; `.def(py::init<>())` → `.def(nb::init<>())`; `py::arg` → `nb::arg`. Read-only/read-write members: `def_readonly`/`def_readwrite` are unchanged in name. ([porting guide](https://nanobind.readthedocs.io/en/latest/porting.html))

### 4.4 The big one — `py::array_t<float>` → `nb::ndarray`

This is the single largest mechanical change because it touches every method signature and every loop body. Recommended target type for our 1-D float32 buffers:

```cpp
// Input arrays: typed, contiguous, NumPy-owned (zero-copy reference).
using FArr = nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>;
```

- **Validation moves to the boundary.** `FArr` checks dtype/contiguity/dim **once** on entry. Inside the function, `.data()` gives a raw `float*` and `.shape(0)` / `.size()` give the count — no per-access checks.
- **Equivalent rewrite of `resample_position_stroke`:** replace `auto pos = positions.unchecked<1>(); … pos(i*3)` with `const float* p = positions.data(); … p[i*3]`. The `is_position_data` scan (interpolate.cpp:228) similarly becomes a raw-pointer min/max loop.
- **Return values:** pybind11 `py::array_t<float>(n, data)` copies into a new array. Nanobind prefers returning an `nb::ndarray` that *owns* its memory (e.g. allocate with `new[]`, wrap with a deleter) — see [Returning ndarray discussion #629](https://github.com/wjakob/nanobind/discussions/629) and [SO: owned memory](https://stackoverflow.com/questions/78777991/return-ndarray-in-nanobind-with-owned-memory). For our small per-stroke outputs, the simplest correct pattern is:

  ```cpp
  float* out = new float[n];
  std::copy(result.begin(), result.end(), out);
  return nb::ndarray<float, nb::numpy, nb::c_contig, nb::ndim<1>>(
      out, {n}, nb::capsule(out, [](void* p) noexcept { delete[] (float*) p; }));
  ```

  This returns a proper NumPy array the Python side can `np.concatenate` exactly as today (`interpolation.py:95`).

### 4.5 STL + Python-object conversions
`#include <nanobind/stl.h>` covers `std::vector<float>`, `std::pair`, `std::string`. The `match`/`match_with_seeds` lambdas use `py::list`, `py::tuple`, `item.cast<...>()` — these become `nb::list`, `nb::tuple`, `nb::cast<...>`. The `py::array_t<float>` parameters in those lambdas become `FArr` too.

### 4.6 Things explicitly **not** available / different
- No exact equivalent of pybind11's buffer protocol ([LLVM discourse](https://discourse.llvm.org/t/nanobind-for-mlir-python-bindings/83511)) — **we don't use it**, so non-issue.
- **Holder types:** nanobind co-locates instance data with the Python object instead of using `std::shared_ptr`-style holders ([porting guide](https://nanobind.readthedocs.io/en/latest/porting.html)). We use `py::init<>()` / `py::init<MatcherConfig>()` with default holders, so no custom-holder porting is needed — but verify `StrokeMatcher`'s two constructors port cleanly.

---

## 5. Build & packaging rewrite

### 5.1 CMake — swap the dependency
In `Executable/CMakeLists.txt` (and the `_py314test` variant if it survives — see §5.4):

```cmake
# Remove:
include(FetchContent)
FetchContent_Declare(pybind11 GIT_REPOSITORY ... GIT_TAG v3.0.1)
FetchContent_MakeAvailable(pybind11)
set(PYBIND11_FINDPYTHON OFF ...)   # the "fix twice" hack goes away
...
pybind11_add_module(gp_autointerpolate ${FTPSC_SOURCES})

# Replace with:
include(FetchContent)
FetchContent_Declare(
    nanobind
    GIT_REPOSITORY https://github.com/wjakob/nanobind.git
    GIT_TAG        v2.9.2           # pin; bump deliberately
)
FetchContent_MakeAvailable(nanobind)

nanobind_add_module(gp_autointerpolate
    NB_ABI_COMPATIBILITY 3.11        # ← enables abi3 stable ABI, cp311 minimum
    STABLE_ABI
    ${FTPSC_SOURCES}
)
```

- The `PYBIND11_FINDPYTHON OFF` double-set hack (CMakeLists.txt:35,51) is pybind11-specific and is **deleted**. Nanobind uses its own Python detection.
- Eigen / nanoflann / OpenMP / static-link / universal-binary blocks are **unchanged** — they're orthogonal to the binding library.
- `nanobind_add_module` handles `.pyd`/`.so` suffix and macOS universal flags itself, so some of the manual `set_target_properties(... SUFFIX ...)` block can be trimmed; verify output names stay `gp_autointerpolate.pyd`/`.so`.

### 5.2 Replace `setup.py` with `pyproject.toml`

The current `setup.py` `CMakeBuild` does nothing but locate and copy the prebuilt binary. With nanobind-packaging (scikit-build-core backend) the build is driven by CMake directly from `python -m build`. New root `pyproject.toml`:

```toml
[build-system]
requires = ["scikit-build-core>=0.10", "nanobind>=2.9.2"]
build-backend = "scikit_build_core.build"

[project]
name = "gp_autointerpolate"
version = "2.4.6"   # or read from blender_manifest.toml via tooling
requires-python = ">=3.11"
description = "High-performance C++ interpolation module for Blender Grease Pencil"

[tool.scikit-build]
cmake.version = ">=3.15"
wheel.install-dir = "."     # flat layout so `import gp_autointerpolate` resolves
```

Then delete `setup.py`. The CI step `python -m build --wheel` continues to work, but now it *builds* the C++ too (no pre-build required) — simpler and more reproducible. ([packaging docs](https://nanobind.readthedocs.io/en/latest/packaging.html))

### 5.3 CI — collapse the matrix
In `.github/workflows/build.yml`:
- `build_interpolate` job: drop the `python-version` matrix dimension entirely (abi3 wheel is Python-agnostic). Keep the 3-OS matrix.
- Remove the `python-version` arg from artifact names; rename to e.g. `wheel-interpolate-${{ matrix.platform }}`.
- The `package` job copies a single `cp311-abi3-*.whl` per platform instead of two.
- `Addon/utils/dll_loader.py` stays as-is (still needed for the `gp_linevector` OpenCV DLLs and any future repaired wheel).
- The Windows wheel **may** still want `delvewheel` repair if any DLLs (e.g. OpenMP) land outside the binary — but `gp_autointerpolate` has fewer external DLL deps than `gp_linevector`, so this is likely skippable. Test in Phase 1.

### 5.4 The experimental 3.14 build
`CMakeLists_py314test.txt` and `.github/workflows/build_py314_experimental.yml` exist solely to produce a 3.14-tagged wheel by `sed`-rewriting the tag. With abi3, **a single cp311-abi3 wheel runs on 3.14 unmodified**. Both files can be deleted. (Keep the abi3 target at `3.11` so the floor stays Blender 4.2.)

---

## 6. Phased rollout

### Phase 0 — De-risk abi3 in Blender (no code merge)
**Goal:** prove a nanobind abi3 wheel actually imports in Blender 4.2 (3.11) and a 5.x alpha (3.13) before investing in the full port.

1. Create a throwaway branch.
2. Take a trivial C++ function, bind it with nanobind + `NB_ABI_COMPATIBILITY 3.11`, build one wheel per OS.
3. Install each into the target Blender versions and `import` it. Confirm Blender's wheel-tag validator accepts `cp311-abi3` on 3.13 ([#130561](https://projects.blender.org/blender/blender/issues/130561) risk).
4. **Exit gate:** abi3 wheel imports on both 3.11 and 3.13 in Blender. If it fails → stop; the §1.1 win isn't realizable and the migration's value drops substantially (revisit whether §1.2 alone justifies the work).

### Phase 1 — Behavior-equivalence harness (on pybind11, before any port)
**Goal:** lock current behavior so the port can be proven non-regressive.

1. Add a small test script that calls `Interpolator.process_interpolation[_advanced]` and `StrokeMatcher.match[_with_seeds]` with a fixed corpus of inputs (a handful of synthetic strokes + a couple of real exported frames).
2. Capture outputs (numpy arrays + match tuples) as the **golden reference**.
3. This runs against the *current* pybind11 build. Commit the corpus + golden outputs. The port must reproduce them within `np.allclose(..., atol=1e-6)`.

### Phase 2 — Port `interpolate.cpp` to nanobind
**Goal:** behavior-identical nanobind module, still built by the *old* CI.

1. On a feature branch, rewrite headers/namespace/module macro (§4.1–4.3).
2. Port the `Interpolator` methods first (§4.4) — this is the hot path and the meatiest change. Run the Phase-1 harness; iterate until golden outputs match.
3. Port `MatcherConfig`, `MatchingResult`, `StrokeMatcher` + the two parsing lambdas (§4.5). Re-run harness.
4. Keep pybind11 CMake config in a side file (`CMakeLists.pybind.txt`) so a one-flag revert is possible during stabilization.

### Phase 3 — Build/packaging rewrite
**Goal:** abi3 wheel via scikit-build-core.

1. Swap CMake to nanobind + `NB_ABI_COMPATIBILITY 3.11` (§5.1).
2. Add root `pyproject.toml`, delete `setup.py` (§5.2).
3. Update `.github/workflows/build.yml`: drop the python-version matrix, single wheel per OS (§5.3).
4. Produce `cp311-abi3` wheels for win/macos-universal/linux; confirm each imports in Blender on 3.11 and 3.13.

### Phase 4 — Cleanup
1. Delete `CMakeLists_py314test.txt`, `.github/workflows/build_py314_experimental.yml`, the saved pybind11 CMake side-file, `setup.py` if any remnants.
2. Update `Executable/AGENTS.md` (binding library line, stable-ABI line, build files table) and root `AGENTS.md` Child DOX Index if any file list changed.
3. Bump version, ship.

---

## 7. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Blender rejects `cp311-abi3` tag on 3.13 (validator bug) | Medium | High — kills §1.1 | Phase 0 exists *only* to catch this before commitment |
| `nb::ndarray` return-path memory ownership bug (use-after-free) | Medium | High — silent corruption | Use the `nb::capsule` deleter pattern (§4.4) verbatim; add a stress test that holds returned arrays across many frames |
| Lambda port introduces wire-format drift in FTP-SC separator parsing | Low | Medium — breaks correspondence | Phase-1 harness covers `match`/`match_with_seeds`; keep the `-1` separator contract documented |
| Default-arg / `none()` semantics differ subtly | Low | Low — API quirk | `arg("easing_curve") = nb::none()` — verify Python `None` still reaches C++ as null array |
| Nanobind static-linking on Linux interacts badly with `-static-libstdc++` | Low | Medium — link error | Both are just linker flags; test on ubuntu-latest in Phase 3; nanobind docs cover Linux cross-distro ([packaging](https://nanobind.readthedocs.io/en/latest/packaging.html)) |
| Eigen/nanoflann include paths assumed pybind11 context | Very low | Low | Unrelated to binding lib; verify in Phase 3 build |
| `gp_linevector` left on pybind11 while sibling migrates | None | Low | Out of scope by design; two modules can use different binders independently |

---

## 8. What stays the same

- **Python call sites** (`Addon/core/interpolation.py`, `cpp_module.py`, `correspondence.py`) — class/method names and signatures are preserved by design. The only likely edit is if we choose to pass pre-flattened contiguous arrays from Python (already contiguous today, so probably none).
- **FTP-SC algorithm source** (`stage_one.cpp`, `stage_two.cpp`, `fuzzy_topology.*`, etc.) — pure C++, untouched.
- **Eigen / nanoflann / OpenMP** configuration.
- **`dll_loader.py`** — still needed for sibling module's repaired wheels.
- **macOS universal / Linux static-stdlib cross-platform strategy.**

---

## 9. Effort estimate (rough)

| Phase | Effort | Notes |
|---|---|---|
| 0 — abi3 de-risk | 0.5–1 day | Throwaway spike; the go/no-go gate |
| 1 — equivalence harness | 1 day | Corpus + golden capture; reusable as regression test |
| 2 — port `interpolate.cpp` | 2–3 days | Mostly the `array_t`→`ndarray` rewrite + lambda ports |
| 3 — build/packaging | 1 day | CMake + pyproject + CI matrix collapse |
| 4 — cleanup + docs | 0.5 day | DOX pass, delete dead files |
| **Total** | **5–6.5 days** | Dominated by Phase 2; gated by Phase 0 |

---

## 10. Decision gate

**Recommendation:** proceed to **Phase 0** only. The abi3-in-Blender question is the keystone — if it holds, the rest is straightforward mechanical porting with a clear payoff (3× fewer build jobs, simpler packaging, modest hot-path speedup). If Phase 0 fails, the remaining justification (§1.2 + §1.3) is *nice-to-have*, not worth 5 days, and the plan should be shelved or trimmed to a no-abi3 nanobind port (which would forgo the matrix collapse and cut the value roughly in half).

---

## Sources

- [Nanobind changelog (v2.9.2 latest)](https://nanobind.readthedocs.io/en/latest/changelog.html)
- [Porting guide — pybind11 → nanobind](https://nanobind.readthedocs.io/en/latest/porting.html)
- [The `nb::ndarray<..>` class](https://nanobind.readthedocs.io/en/latest/ndarray.html)
- [Packaging (scikit-build-core, abi3, cibuildwheel)](https://nanobind.readthedocs.io/en/latest/packaging.html)
- [CMake API reference (`NB_ABI_COMPATIBILITY`)](https://nanobind.readthedocs.io/en/latest/api_cmake.html)
- [Why nanobind (perf claims)](https://nanobind.readthedocs.io/en/latest/why.html)
- [nanobind GitHub](https://github.com/wjakob/nanobind)
- [Discussion #83 — no interop with pybind11](https://github.com/wjakob/nanobind/discussions/83)
- [Discussion #629 — returning owned ndarrays](https://github.com/wjakob/nanobind/discussions/629)
- [SO — ndarray with owned memory](https://stackoverflow.com/questions/78777991/return-ndarray-in-nanobind-with-owned-memory)
- [pybind11#584 — bounds-check overhead in array accessors](https://github.com/pybind/pybind11/issues/584)
- [pybind11#2600 — subscripting without bounds check](https://github.com/pybind/pybind11/issues/2600)
- [Blender #130561 — extension wheel/Python-version validation](https://projects.blender.org/blender/blender/issues/130561)
- [blendercam#282 — "3.13 isn't compatible with 3.11"](https://github.com/vilemduha/blendercam/issues/282)
- [OSArch — Blender 5.1 alpha on Python 3.13](https://community.osarch.org/discussion/3310/blender-5-1-alpha-now-switched-python-from-3-11-to-3-13)
- [Pyodide discussion — cp311-abi3 tag rule](https://github.com/pyodide/pyodide/discussions/4377)
- [MatecDev — Nanobind vs Pybind11 comparison](https://www.matecdev.com/posts/nanobind-vs-pybind11-cpp-python.html)
