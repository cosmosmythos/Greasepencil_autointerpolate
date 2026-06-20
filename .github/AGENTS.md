# .github — CI Workflows

## Purpose

GitHub Actions workflows for building, testing, and releasing Blender extension wheels.

## Ownership

| File | Role |
|------|------|
| `workflows/build.yml` | Main CI: builds interpolate + linevector wheels, packages platform zips, creates releases |

## Local Contracts

- **Two wheel types per platform.** `build_interpolate` produces `cp311` (non-abi3, Python 3.11) and `cp312-abi3` (stable ABI, Python 3.12+). The abi3 wheel covers all future Python versions.
- **abi3 build uses Python 3.12** (the minimum floor). CMake flag: `-DENABLE_ABI3=ON`. setup.py env var: `ENABLE_ABI3=1`.
- **Wheel assembly is decoupled from C++.** CMake builds the `.pyd`/`.so` first, then `setup.py`'s `CMakeBuild` copies it into the wheel.
- **Package job** collects all wheels by platform suffix (`*win_amd64.whl`, `*universal2.whl`, `*manylinux*.whl`) and bundles into per-platform zips. It runs on push to main/master, tag push (`v*`), manual workflow dispatch, and pull requests.
- **Release creation** happens automatically for main/master pushes, manual dispatches, and tag pushes, but is skipped on pull requests (where zips are only kept as workflow run artifacts). Tag pushes use the Git tag directly for the release, while branch pushes and manual runs generate a tag using the current version and build number.

## Work Guidance

- cp311 builds pin `python-version: '3.11.9'`. abi3 builds use `python-version: '3.12'` (latest patch, forward-compatible).
- Do not add per-version wheels for Python 3.12+ — the abi3 wheel covers them.
- The `build_py314_experimental.yml` was deleted — abi3 makes it obsolete.
- **All builds use Ninja** (`CMAKE_GENERATOR: Ninja` env var + `pip install ninja`). No Visual Studio generator — `windows-latest` runners don't have it pre-installed.
- **MSVC setup**: `ilammy/msvc-dev-cmd@v1` (not `microsoft/setup-msbuild`). Works with `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` for Node 24 compatibility.
- **Eigen3 on Windows**: Downloaded directly from GitLab (not choco). Set `EIGEN3_ROOT` env var and pass `-DCMAKE_MODULE_PATH` to cmake. Linux/macOS use apt/brew.
- **OpenCV on Windows**: OpenCV 5.0.0 (has VS2026/MSVC 1951 support with vc18→vc17 fallback). Official dist is a self-extracting `.exe` — download and extract with `7z`. Set `OPENCV_ROOT` env var; pass `-DOpenCV_DIR=${OPENCV_ROOT}/build` to cmake. Do NOT downgrade to 4.11.0 — it rejects unknown MSVC versions.
- **Boost on Windows**: Downloaded as full source archive from `archives.boost.io`. Header-only; pass `-DCMAKE_PREFIX_PATH=${BOOST_ROOT}` for `find_package(Boost)`. Linux/macOS use apt/brew.
- **LineVector Windows DLL bundling**: `delvewheel repair --add-path "${OPENCV_ROOT}/build/x64/vc16/bin"` to bundle OpenCV DLLs.

## Verification

- Each build job uploads a wheel artifact. The package job bundles them into release zips.
- `dumpbin /dependents <pyd>` must show `python3.dll` for abi3 wheels, `python3XX.dll` for non-abi3 wheels.
