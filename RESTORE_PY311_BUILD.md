# How to Restore Python 3.11 Build (Official Releases)

## ⚠️ IMPORTANT: After Building Python 3.14 Wheels

The CMakeLists.txt files have been modified for Python 3.14. 
**You MUST restore them before building official releases!**

## Quick Restore Commands

### Option 1: Using Backups (Recommended)

```bash
# Restore gp_autointerpolate
cp Executable/CMakeLists.txt.backup_py311 Executable/CMakeLists.txt

# Restore gp_linevector  
cp Vectorize/CMakeLists.txt.backup_py311 Vectorize/CMakeLists.txt

# Verify restoration
git diff Executable/CMakeLists.txt
git diff Vectorize/CMakeLists.txt
```

### Option 2: Git Restore

```bash
# Restore from git (if committed)
git checkout Executable/CMakeLists.txt
git checkout Vectorize/CMakeLists.txt
```

## Verification

After restoring, both files should have:
- `find_package(Python3 3.11 COMPONENTS ...)`
- Messages mentioning "Blender 4.3+"
- Python 3.11.x compatibility warnings

## What Changed

### Python 3.14 Version (EXPERIMENTAL)
```cmake
find_package(Python3 3.14 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Building for Arch Linux Blender 5.0 (EXPERIMENTAL)")
```

### Python 3.11 Version (OFFICIAL)
```cmake
find_package(Python3 3.11 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Building GP Auto Interpolate module for Blender 4.3+")
```

## Build Workflow Usage

### For Official Releases (Python 3.11)
1. **Restore CMakeLists.txt to Python 3.11** (see above)
2. Use workflow: `.github/workflows/build.yml`
3. Trigger: Automatically on push/tag, or manual dispatch
4. Output: Official wheels for all platforms

### For Experimental Python 3.14 Build
1. **Ensure CMakeLists.txt are set to Python 3.14** (current state)
2. Use workflow: `.github/workflows/build_py314_experimental.yml`
3. Trigger: Manual dispatch only
4. Output: Linux-only wheels for Arch Blender 5.0

## Important Notes

- **Never commit Python 3.14 changes** to main branch
- Always verify which Python version is configured before building
- The backup files (`.backup_py311`) should remain in the repo
- setup.py files don't need restoration (modified by workflow dynamically)

## Checklist Before Official Release

- [ ] Restored Executable/CMakeLists.txt to Python 3.11
- [ ] Restored Vectorize/CMakeLists.txt to Python 3.11
- [ ] Verified with `git diff` or by checking file contents
- [ ] Tested build with official workflow (build.yml)
- [ ] Confirmed wheel tags are `cp311-abi3-manylinux_*` or `cp311-abi3-win_*`

---

**Remember:** Python 3.14 build is **EXPERIMENTAL and UNSUPPORTED**.  
Official releases should always use Python 3.11!
