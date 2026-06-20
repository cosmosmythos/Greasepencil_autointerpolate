# .github — CI Workflows

## Purpose

GitHub Actions workflows for building, testing, and releasing Blender extension wheels.

## Ownership

| File | Role |
|------|------|
| `workflows/build.yml` | Main CI: builds interpolate + linevector wheels, packages platform zips, creates releases |

## Local Contracts

- **Two wheel types per platform.** `build_interpolate` produces `cp311` (standard, Python 3.11) and `cp312-abi3` (stable ABI, Python 3.12+). The abi3 wheel covers all future Python versions.
- **abi3 build uses Python 3.12** (the minimum floor). CMake flag: `-DENABLE_ABI3=ON`. setup.py env var: `ENABLE_ABI3=1`.
- **Wheel assembly is decoupled from C++.** CMake builds the `.pyd`/`.so` first, then `setup.py`'s `CMakeBuild` copies it into the wheel.
- **Package job** collects all wheels by platform suffix (`*win_amd64.whl`, `*universal2.whl`, `*manylinux*.whl`) and bundles into per-platform zips.

## Work Guidance

- Standard builds pin `python-version: '3.11.9'`. abi3 builds use `python-version: '3.12'` (latest patch, forward-compatible).
- Do not add per-version wheels for Python 3.12+ — the abi3 wheel covers them.
- The `build_py314_experimental.yml` was deleted — abi3 makes it obsolete.

## Verification

- Each build job uploads a wheel artifact. The package job bundles them into release zips.
- `dumpbin /dependents <pyd>` must show `python3.dll` for abi3 wheels, `python3XX.dll` for standard wheels.
