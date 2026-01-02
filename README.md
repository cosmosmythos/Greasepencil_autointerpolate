# Grease Pencil Auto-Interpolate

Blender addon for automatic interpolation and line art vectorization.

## Features

- **Auto-Interpolation**: Smooth interpolation between grease pencil keyframes
- **Line Art Import**: High-quality vectorization using PolyVector algorithm
- **Blender 4.3+ Support**: Uses new Grease Pencil v3 API

## Installation

1. Download the addon
2. Install in Blender: Edit → Preferences → Add-ons → Install
3. Enable "Grease Pencil: Auto-Interpolate"

For line art import, install the polyvector wheel:
```bash
pip install wheels/polyvector-*.whl
```

## Line Art Vectorization

Uses state-of-the-art PolyVector algorithm (Bessmeltsev & Solomon 2019) for:
- ✅ Perfect junction handling (X and T junctions)
- ✅ Automatic gap bridging in sketches
- ✅ Smooth, professional-quality output

### Building from Source

**Requirements**: CMake 3.15+, Python 3.11, OpenCV, Eigen3, Boost

#### Quick Start

```bash
# Windows
.\build_polyvector.ps1

# Linux/macOS
chmod +x build_polyvector.sh
./build_polyvector.sh
```

Wheels will be in `dist/` directory.

#### Install Dependencies

**Windows (using Chocolatey):**
```powershell
choco install cmake opencv eigen boost-msvc-14.3 -y
```

**macOS (using Homebrew):**
```bash
brew install cmake opencv eigen boost
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install build-essential cmake libopencv-dev libeigen3-dev libboost-dev
```

#### Advanced Build Options

**Windows with vcpkg:**
```powershell
.\build_polyvector.ps1 -VcpkgRoot C:\path\to\vcpkg
```

**Manual CMake build:**
```bash
# 1. Download required header
curl -fsSL -o Vectorize/src_polyvector/simple_svg_1.0.0.hpp \
  https://raw.githubusercontent.com/adishavit/simple-svg/master/simple_svg_1.0.0.hpp

# 2. Build C++ module
mkdir -p Vectorize/build && cd Vectorize/build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
cd ../..

# 3. Build Python wheel
pip install wheel setuptools
python setup_vectorize.py bdist_wheel
```

## License

See LICENSE file.
