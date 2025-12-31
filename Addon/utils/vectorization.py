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
    threshold: int = 90,
    auto_threshold: bool = False,
    despeckle_size: int = 10,
    simplify_epsilon: float = 2.0,
    blur_radius: int = 0
) -> List[np.ndarray]:
    """
    Process image and extract polylines using PolyVector algorithm.
    
    This uses the state-of-the-art PolyVector field-based vectorization
    which properly handles junctions, gaps, and produces smooth curves.
    
    Args:
        image_array: Input image (H, W, C) with float values 0-1
        threshold: Background/foreground threshold (0-255, default=90)
                   Lower values detect more ink
        auto_threshold: Not used (kept for API compatibility)
        despeckle_size: Not used (PolyVector handles noise internally)
        simplify_epsilon: Not used (PolyVector has built-in simplification)
        blur_radius: Not used (PolyVector handles smoothing internally)
    
    Returns:
        List of polylines as Nx2 numpy arrays
    
    Raises:
        RuntimeError: If PolyVector backend is not available
    
    Note:
        The old parameters (auto_threshold, despeckle_size, etc.) are kept
        for backward compatibility but are not used. PolyVector has its own
        internal preprocessing and optimization.
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
    strokes = gp_linevector.vectorize_array(image_array, threshold=threshold)
    
    # Convert to numpy arrays
    polylines = []
    for stroke in strokes:
        if len(stroke) >= 2:  # Need at least 2 points
            points = np.array(stroke, dtype=np.float32)
            polylines.append(points)
    
    return polylines


def get_skeleton_preview(
    image_array: np.ndarray,
    threshold: int = 90,
    auto_threshold: bool = False,
    despeckle_size: int = 10,
    blur_radius: int = 0
) -> np.ndarray:
    """
    Get preview of vectorization (returns simple thresholded image).
    
    Note: PolyVector doesn't expose intermediate skeleton,
    so we return a simple threshold for preview purposes.
    
    Returns:
        Binary image as HxW numpy array
    """
    if not _linevector_available:
        raise RuntimeError("LineVector backend not available")
    
    # Convert to grayscale if needed
    if len(image_array.shape) == 3:
        # Simple RGB to grayscale
        gray = np.dot(image_array[..., :3], [0.299, 0.587, 0.114])
    else:
        gray = image_array
    
    # Convert to uint8
    if gray.dtype == np.float32 or gray.dtype == np.float64:
        if gray.max() <= 1.0:
            gray = (gray * 255).astype(np.uint8)
        else:
            gray = gray.astype(np.uint8)
    
    # Threshold
    binary = (gray < threshold).astype(np.uint8) * 255
    
    return binary
