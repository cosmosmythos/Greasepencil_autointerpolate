#!/bin/bash
#
# Build gp_linevector Python wheel for Linux/macOS
#
# Builds the PolyVector-based line art vectorization module for Blender.
# Requires: CMake 3.15+, Python 3.11, OpenCV, Eigen3, Boost

set -e

echo "=== Building GP LineVector (PolyVector) ==="

# Check Python version - require Python 3.11
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    echo "✓ Found Python 3.11: $(python3.11 --version)"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    if [[ "$PYTHON_VERSION" =~ "Python 3.11" ]]; then
        PYTHON_CMD="python3"
        echo "✓ Found Python 3.11: $PYTHON_VERSION"
    else
        echo "❌ Python 3.11 is required for Blender 4.3+ compatibility"
        echo "Found: $PYTHON_VERSION"
        exit 1
    fi
else
    echo "❌ Python 3 not found"
    exit 1
fi

# Download missing headers
echo ""
echo "==> Downloading required headers..."

SVG_HEADER="Vectorize/src_polyvector/simple_svg_1.0.0.hpp"
if [ ! -f "$SVG_HEADER" ]; then
    echo "Downloading simple_svg_1.0.0.hpp..."
    curl -fsSL -o "$SVG_HEADER" \
        https://raw.githubusercontent.com/adishavit/simple-svg/master/simple_svg_1.0.0.hpp
    echo "✓ Downloaded simple_svg_1.0.0.hpp"
else
    echo "✓ simple_svg_1.0.0.hpp already exists"
fi

# Check dependencies
echo ""
echo "==> Checking dependencies..."

if ! command -v cmake &> /dev/null; then
    echo "❌ CMake not found"
    echo "Install: sudo apt-get install cmake    (Linux)"
    echo "    or: brew install cmake              (macOS)"
    exit 1
fi
echo "✓ CMake found: $(cmake --version | head -n1)"

# Platform-specific dependency instructions
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo ""
    echo "Note: This build requires OpenCV, Eigen3, and Boost."
    echo "To install on Ubuntu/Debian:"
    echo "  sudo apt-get install build-essential cmake libopencv-dev libeigen3-dev libboost-dev"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo "Note: This build requires OpenCV, Eigen3, and Boost."
    echo "To install on macOS:"
    echo "  brew install cmake opencv eigen boost"
fi

# Create build directory
echo ""
echo "==> Configuring CMake..."
mkdir -p Vectorize/build
cd Vectorize/build

# Get Python 3.11 executable path for CMake
PYTHON_EXE=$($PYTHON_CMD -c "import sys; print(sys.executable)")
echo "Python executable: $PYTHON_EXE"

# Configure CMake
CMAKE_ARGS=(
    ..
    -DCMAKE_BUILD_TYPE=Release
    -DPython3_EXECUTABLE="$PYTHON_EXE"
)

# macOS: Add Homebrew paths if available
if [[ "$OSTYPE" == "darwin"* ]] && command -v brew &> /dev/null; then
    BREW_PREFIX=$(brew --prefix)
    OPENCV_CMAKE="${BREW_PREFIX}/opt/opencv/lib/cmake/opencv4"
    
    if [ -d "$OPENCV_CMAKE" ]; then
        CMAKE_ARGS+=(-DCMAKE_PREFIX_PATH="${BREW_PREFIX}")
        CMAKE_ARGS+=(-DOpenCV_DIR="${OPENCV_CMAKE}")
        echo "Using Homebrew OpenCV: $OPENCV_CMAKE"
    fi
fi

echo "Running: cmake ${CMAKE_ARGS[@]}"
cmake "${CMAKE_ARGS[@]}"

# Build
echo ""
echo "==> Building C++ module..."
cmake --build . --config Release --verbose

echo ""
echo "✓ C++ module built successfully"

# Verify binary exists
BINARY=$(find . -name "gp_linevector*.so" -o -name "gp_linevector*.pyd" | head -n1)
if [ -n "$BINARY" ]; then
    echo "✓ Found binary: $BINARY"
else
    echo "⚠ Warning: Binary not found in build directory"
fi

cd ../..

# Build Python wheel
echo ""
echo "==> Building Python wheel..."

# Install build dependencies
$PYTHON_CMD -m pip install --upgrade pip setuptools wheel build

# Build wheel
$PYTHON_CMD setup_vectorize.py bdist_wheel

echo ""
echo "=== Build Complete ==="
echo "Wheel created in: dist/"

# List wheels
if ls dist/*.whl 1> /dev/null 2>&1; then
    echo ""
    echo "Created wheels:"
    ls -1 dist/*.whl | sed 's/^/  /'
    
    WHEEL=$(ls dist/*.whl | head -n1)
    echo ""
    echo "To install:"
    echo "  pip install $WHEEL"
fi
