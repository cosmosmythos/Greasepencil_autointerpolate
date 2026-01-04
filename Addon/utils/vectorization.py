"""Vectorization utilities for converting raster images to vector strokes.

Uses PolyVector algorithm (Bessmeltsev & Solomon 2019) for high-quality
line art vectorization with proper junction handling.
"""

import numpy as np
from typing import List

# Ensure wheel-bundled DLLs are discoverable on Windows before importing the extension.
try:
    from .dll_loader import add_wheel_dll_dirs

    add_wheel_dll_dirs("gp_linevector")
except Exception:
    # Non-fatal: if this fails we still attempt the import below.
    pass

# Import LineVector backend (REQUIRED)
try:
    import gp_linevector

    _linevector_available = True
except ImportError as e:
    _linevector_available = False
    print(f"[GPAI Lineart] ERROR: LineVector module not available: {e}")
    print("[GPAI Lineart] Please ensure wheels are installed via blender_manifest.toml")


def is_backend_available() -> bool:
    """Check if LineVector backend is available."""

    return _linevector_available


def process_image_file(
    filepath: str,
    blur_pixels: int = 0,
    verbose: bool = False,
) -> List[np.ndarray]:
    """Process image file directly via C++ (master-equivalent).

    Uses OpenCV to load image exactly like PolyVectorization master:
    - No Blender color management
    - RGBA composited on white background
    - OpenCV grayscale conversion
    - Then inverted, thresholded, vectorized
    """

    if not _linevector_available:
        raise RuntimeError(
            "LineVector backend not available. "
            "Ensure wheels are loaded via blender_manifest.toml"
        )

    strokes = gp_linevector.vectorize_image(
        filepath,
        threshold=90,
        blur_pixels=int(blur_pixels),
        verbose=bool(verbose),
    )

    polylines: List[np.ndarray] = []
    for stroke in strokes:
        if len(stroke) >= 2:
            polylines.append(np.array(stroke, dtype=np.float32))

    return polylines


def process_image_file_with_downscale(
    filepath: str,
    blur_pixels: int = 0,
    user_downscale: int = 1,
    verbose: bool = False,
) -> List[np.ndarray]:
    """Process image file with smart downscaling for performance.

    All processing happens in C++/OpenCV:
    - Auto-cap: if max(width, height) > 1024, scale to 1024 on longest side
    - User downscale: further divide by user_downscale (1-4)
    - Resize with cv::INTER_AREA for quality downsampling
    - Vectorize at reduced resolution
    - Scale polylines back to original image coordinates

    For small images (<= 1024px), auto-cap is skipped unless user_downscale > 1.
    """

    if not _linevector_available:
        raise RuntimeError(
            "LineVector backend not available. "
            "Ensure wheels are loaded via blender_manifest.toml"
        )

    strokes = gp_linevector.vectorize_image_downscale(
        filepath,
        threshold=90,
        blur_pixels=int(blur_pixels),
        user_downscale=int(user_downscale),
        verbose=bool(verbose),
    )

    polylines: List[np.ndarray] = []
    for stroke in strokes:
        if len(stroke) >= 2:
            polylines.append(np.array(stroke, dtype=np.float32))

    return polylines
