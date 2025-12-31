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

```bash
# Windows
.\build_polyvector.ps1 -VcpkgRoot C:\path\to\vcpkg

# Linux/macOS
./build_polyvector.sh
```

Wheels will be in `dist/` directory.

## License

See LICENSE file.
