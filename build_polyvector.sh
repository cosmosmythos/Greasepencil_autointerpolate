#!/bin/bash
# Linux/macOS script to build gp_linevector wheel
# Usage: ./build_polyvector.sh

set -e  # Exit on error

echo "========================================"
echo "Building GP LineVector Python Wheel"
echo "========================================"

# Check Python version
PYTHON_VERSION=$(python3.11 --version 2>&1 || python3 --version 2>&1)
if [[ ! "$PYTHON_VERSION" =~ 3\.11 ]]; then
    echo "WARNING: Python 3.11 is required for Blender 4.3+"
    echo "Current Python: $PYTHON_VERSION"
fi

# Check for dependencies
echo ""
echo "Checking dependencies..."

check_command() {
    if command -v $1 &> /dev/null; then
        echo "  ✓ $1 found"
        return 0
    else
        echo "  ✗ $1 NOT found"
        return 1
    fi
}

check_command cmake || { echo "Install cmake first!"; exit 1; }
check_command pkg-config || { echo "Install pkg-config first!"; exit 1; }

# Check OpenCV
if pkg-config --exists opencv4 || pkg-config --exists opencv; then
    echo "  ✓ OpenCV found"
else
    echo "  ✗ OpenCV NOT found"
    echo "  Install: sudo apt-get install libopencv-dev  (Linux)"
    echo "           brew install opencv                  (macOS)"
    exit 1
fi

# Check Eigen3
if pkg-config --exists eigen3; then
    echo "  ✓ Eigen3 found"
else
    echo "  ✗ Eigen3 NOT found"
    echo "  Install: sudo apt-get install libeigen3-dev  (Linux)"
    echo "           brew install eigen                   (macOS)"
    exit 1
fi

# Clean previous build
if [ -d "Vectorize/build" ]; then
    echo ""
    echo "Cleaning previous build..."
    rm -rf Vectorize/build
fi

# Create build directory
echo ""
echo "Configuring CMake..."
cd Vectorize
mkdir -p build
cd build

# Platform-specific CMake configuration
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - build universal binary
    cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="10.15"
else
    # Linux
    cmake .. \
        -DCMAKE_BUILD_TYPE=Release
fi

echo "CMake configuration successful"

# Build
echo ""
echo "Building module..."
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
echo "Build successful"

# Check output
OUTPUT_FILE="../output/gp_linevector.so"
if [ -f "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "  Output: $OUTPUT_FILE"
    echo "  Size: $FILE_SIZE"
else
    echo "WARNING: gp_linevector.so not found in output directory"
fi

# Build wheel
cd ../..
echo ""
echo "Building Python wheel..."

# Use python3.11 if available, otherwise python3
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
else
    PYTHON_CMD=python3
fi

$PYTHON_CMD setup_vectorize.py bdist_wheel

# Show result
echo ""
echo "========================================"
echo "Build Complete!"
echo "========================================"

if ls dist/*.whl 1> /dev/null 2>&1; then
    WHEEL=$(ls dist/*.whl | tail -n 1)
    WHEEL_SIZE=$(du -h "$WHEEL" | cut -f1)
    WHEEL_NAME=$(basename "$WHEEL")
    echo "Wheel created: $WHEEL_NAME"
    echo "Size: $WHEEL_SIZE"
    echo ""
    echo "To install: pip install $WHEEL"
fi
