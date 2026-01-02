# Build Troubleshooting Guide

## Common Build Issues

### Error: "Could not find built binary: gp_linevector.pyd"

**Cause**: The C++ module hasn't been built yet. `setup_vectorize.py` expects a pre-built binary.

**Solution**: Build the C++ module first using the build scripts:

```bash
# Windows
.\build_polyvector.ps1

# Linux/macOS
./build_polyvector.sh
```

Or manually:
```bash
cd Vectorize/build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
cd ../..
python setup_vectorize.py bdist_wheel
```

---

### Error: "CMake not found"

**Solution**: Install CMake 3.15 or newer

- **Windows**: `choco install cmake` or download from https://cmake.org/download/
- **macOS**: `brew install cmake`
- **Linux**: `sudo apt-get install cmake`

---

### Error: "Could NOT find OpenCV"

**Solution**: Install OpenCV development libraries

- **Windows**: `choco install opencv` 
  - Or manually set: `cmake .. -DOpenCV_DIR=C:/path/to/opencv/build`
- **macOS**: `brew install opencv`
- **Linux**: `sudo apt-get install libopencv-dev`

---

### Error: "Could NOT find Eigen3"

**Solution**: Install Eigen3 (header-only library)

- **Windows**: `choco install eigen`
- **macOS**: `brew install eigen`
- **Linux**: `sudo apt-get install libeigen3-dev`

---

### Error: "Could NOT find Boost"

**Solution**: Install Boost (only headers needed, no compilation)

- **Windows**: `choco install boost-msvc-14.3`
- **macOS**: `brew install boost`
- **Linux**: `sudo apt-get install libboost-dev`

---

### Error: "simple_svg_1.0.0.hpp: No such file"

**Cause**: Missing header file that must be downloaded separately

**Solution**: Download the header (build scripts do this automatically):

```bash
curl -fsSL -o Vectorize/src_polyvector/simple_svg_1.0.0.hpp \
  https://raw.githubusercontent.com/adishavit/simple-svg/master/simple_svg_1.0.0.hpp
```

---

### Python Version Mismatch Warning

**Warning**: "Python X.Y found, but Blender 4.3+ requires Python 3.11.x"

**Impact**: The module will build but may not load in Blender if Python versions don't match.

**Solution**: 
1. Install Python 3.11.x from https://www.python.org/downloads/
2. Use it explicitly: `python3.11 setup_vectorize.py bdist_wheel`
3. Or create a virtual environment with Python 3.11

---

## Build Process Overview

The build happens in two stages:

### Stage 1: CMake Build (C++ Module)
```bash
cd Vectorize/build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

Output: `Vectorize/output/gp_linevector.pyd` (Windows) or `.so` (Linux/macOS)

### Stage 2: Python Wheel Packaging
```bash
python setup_vectorize.py bdist_wheel
```

This copies the binary from Stage 1 into a distributable wheel in `dist/`

---

## Verifying the Build

After successful build:

```bash
# Check binary exists
ls Vectorize/output/gp_linevector.*

# Check wheel created
ls dist/*.whl

# Test installation
pip install dist/gp_linevector-*.whl
python -c "import gp_linevector; print(f'Version: {gp_linevector.__version__}')"
```

---

## CI/CD Build

The `.github/workflows/build.yml` shows the complete automated build process for all platforms. Reference this for:
- Exact dependency versions
- Platform-specific configurations
- Wheel repair/bundling steps

---

## Getting Help

If you encounter issues not covered here:

1. Check that all dependencies are installed: `cmake --version`, `python --version`
2. Review the CMake output for specific missing libraries
3. Try building manually step-by-step (see Manual CMake Build in README)
4. Open an issue with the full error output
