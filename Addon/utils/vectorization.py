"""
Vectorization utilities for converting raster images to vector strokes.

Uses PolyVector algorithm (Bessmeltsev & Solomon 2019) for high-quality
line art vectorization with proper junction handling.
"""

import numpy as np
from typing import List

# Import LineVector backend (REQUIRED)
try:
    import gp_linevector
    _linevector_available = True
    print("[GPAI Lineart] LineVector module loaded successfully")
    print(f"[GPAI Lineart] Version: {gp_linevector.__version__}")
except ImportError as e:
    _linevector_available = False
    print(f"[GPAI Lineart] ERROR: LineVector module not available: {e}")
    print("[GPAI Lineart] Please ensure wheels are installed via blender_manifest.toml")


def is_backend_available() -> bool:
    """Check if LineVector backend is available."""
    return _linevector_available


def process_image_to_polylines(
    image_array: np.ndarray,
    blur_pixels: int = 0,
    smooth_steps: int = 10,
    smooth_weight: float = 0.5,
) -> List[np.ndarray]:
    """
    Process image and extract polylines using PolyVector algorithm.
    
    This uses the state-of-the-art PolyVector field-based vectorization
    which properly handles junctions, gaps, and produces smooth curves.
    
    Args:
        image_array: Input image (H, W, C) with float values 0-1
        blur_pixels: Gaussian blur radius in pixels applied before vectorization (0 disables)
        smooth_steps: Smoothing iterations (0-20). Default 10.
        smooth_weight: Smoothing strength (0.0-1.0). Default 0.5.
    
    Returns:
        List of polylines as Nx2 numpy arrays
    
    Raises:
        RuntimeError: If PolyVector backend is not available
    
    Note:
        PolyVector has built-in preprocessing, noise removal, simplification,
        and smoothing. No additional parameters are needed.
    """
    if not _linevector_available:
        raise RuntimeError(
            "LineVector backend not available. "
            "Ensure wheels are loaded via blender_manifest.toml"
        )
    
    # Convert float [0,1] to uint8 [0,255] if needed
    if image_array.dtype == np.float32 or image_array.dtype == np.float64:
        if image_array.max() <= 1.0:
            image_array = (image_array * 255).astype(np.uint8)
        else:
            image_array = image_array.astype(np.uint8)
    
    # Ensure uint8
    if image_array.dtype != np.uint8:
        image_array = image_array.astype(np.uint8)
    
    # Call LineVector
    # Threshold is intentionally fixed to 90 (master default). Users should adjust image contrast beforehand.
    strokes = gp_linevector.vectorize_array(
        image_array,
        threshold=90,
        blur_pixels=int(blur_pixels),
        smooth_steps=int(smooth_steps),
        smooth_weight=float(smooth_weight),
    )
    
    # Convert to numpy arrays
    polylines = []
    for stroke in strokes:
        if len(stroke) >= 2:  # Need at least 2 points
            points = np.array(stroke, dtype=np.float32)
            polylines.append(points)
    
    return polylines


