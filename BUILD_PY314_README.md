# Python 3.14 Experimental Build (Arch Linux Blender 5.0)

## ⚠️ IMPORTANT DISCLAIMER

**This is a ONE-TIME experimental build for a specific customer using Arch Linux's Blender 5.0 package.**

- ❌ **NOT OFFICIALLY SUPPORTED**
- ❌ **NOT FOR GENERAL DISTRIBUTION**
- ❌ **CANNOT BE TESTED** (developer not on Linux)
- ✅ **USE AT YOUR OWN RISK**

## Why This Build Exists

Arch Linux's Blender 5.0 package:
- Built against system Python 3.14
- Rolling release = always latest libraries
- Breaks compatibility with standard addon builds (Python 3.11)

## The Problem

Python 3.13+ removed internal API `_PyThreadState_UncheckedGet` that pybind11 uses.
- Official Blender (blender.org) = Python 3.11 ✅ Works with standard builds
- Arch Blender package = Python 3.14 ❌ Requires this experimental build

## Recommended Solution

**Download Blender directly from blender.org** instead of using distro packages:
- ✅ Bundled Python 3.11
- ✅ Compatible with all addons
- ✅ Tested and supported
- ✅ Works across all Linux distros

## How to Use This Experimental Build

### 1. Trigger the Build (Maintainer Only)

```bash
# Go to GitHub Actions
# Select "Build Python 3.14 Wheels (EXPERIMENTAL)"
# Click "Run workflow"
```

### 2. Download Artifacts

After build completes:
- `gp_autointerpolate-*-cp314-cp314-linux_*.whl`
- `gp_linevector-*-cp314-cp314-linux_*.whl`

### 3. Manual Installation

```bash
# In Blender's Python environment (Arch Linux only)
pip install gp_autointerpolate-*-cp314-cp314-linux_*.whl
pip install gp_linevector-*-cp314-cp314-linux_*.whl
```

## Files Modified for This Build

### CMakeLists.txt Changes

Both `Executable/CMakeLists.txt` and `Vectorize/CMakeLists.txt`:
- Changed: `find_package(Python3 3.11 ...)` → `find_package(Python3 3.14 ...)`
- Backups created: `*.backup_py311`

### To Restore Original (Python 3.11) Build

```bash
# Restore interpolate
cp Executable/CMakeLists.txt.backup_py311 Executable/CMakeLists.txt

# Restore linevector
cp Vectorize/CMakeLists.txt.backup_py311 Vectorize/CMakeLists.txt
```

## Technical Details

### What Changed

1. **Python Version**: 3.11 → 3.14
2. **Wheel Tag**: `cp311-abi3` → `cp314-cp314`
3. **Platform Tag**: `manylinux_2_*` → `linux_*` (Arch-specific)
4. **Build Environment**: Ubuntu container → Arch Linux container

### What Stayed the Same

- ✅ Static linking of libstdc++ and libgcc
- ✅ RPATH configuration (`$ORIGIN`)
- ✅ OpenMP static linking
- ✅ Same source code
- ✅ Same optimization flags

### Known Limitations

1. **Cannot be tested by maintainer** (not on Linux)
2. **May not work** if Arch's Blender has other custom patches
3. **No ongoing support** - this is experimental only
4. **Future Python versions** (3.15, 3.16) will require new builds
5. **Other distros** may have different issues

## Why NOT to Maintain Multiple Python Versions

### The Slippery Slope

- Today: Python 3.14 for Arch
- Tomorrow: Python 3.15 for Fedora Rawhide
- Next week: Python 3.16 for Gentoo
- **Where does it end?**

### Maintenance Burden

Each Python version requires:
- Separate CMakeLists configuration
- Separate GitHub workflow
- Separate testing (impossible without that distro)
- Separate debugging when issues arise
- Documentation for each variant

### Industry Standard

**99% of Blender addon developers only support blender.org releases.**

Why? Because:
- Predictable environment
- Testable by developers
- Sustainable long-term
- Professional workflows depend on stability

## Final Recommendation

**If you're reading this because the addon doesn't work:**

1. Download Blender from **blender.org** (not distro repos)
2. Use the standard wheels from the main `build.yml` workflow
3. Enjoy a stable, tested, supported experience

**If you insist on using distro Blender:**

1. Understand this is experimental and unsupported
2. Be prepared for breakage with future updates
3. Don't expect timely fixes for distro-specific issues
4. Consider this a favor, not a promise

---

**Created:** 2026-02-18  
**Purpose:** One-time build for Arch Linux customer (Stoa)  
**Status:** Experimental / Unsupported  
**Support:** Use blender.org releases for official support
