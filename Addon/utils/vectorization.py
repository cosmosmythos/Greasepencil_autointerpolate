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
    verbose: bool = False,
) -> List[np.ndarray]:
    """
    Process image and extract polylines using PolyVector algorithm.
    
    This uses the state-of-the-art PolyVector field-based vectorization
    which properly handles junctions, gaps, and produces smooth curves.
    
    Args:
        image_array: Input image (H, W, C) with float values 0-1
        blur_pixels: Gaussian blur radius in pixels applied before vectorization (0 disables)
        verbose: Enable detailed debug logging (default=False)
    
    Returns:
        List of polylines as Nx2 numpy arrays
    
    Raises:
        RuntimeError: If PolyVector backend is not available
    
    Note:
        Smoothing (10 iterations, weight 0.5) and simplification (epsilon 1e-2)
        are hardcoded to exactly match PolyVectorization master.
    """
    if not _linevector_available:
        raise RuntimeError(
            "LineVector backend not available. "
            "Ensure wheels are loaded via blender_manifest.toml"
        )
    
    # ============================================================================
    # CRITICAL PREPROCESSING: Convert to master-equivalent grayscale uint8
    # Master expects: opaque RGB image with dark lines on light background
    # ============================================================================
    
    # Handle RGBA by compositing on WHITE background (master assumes opaque images)
    if image_array.shape[2] == 4:  # RGBA
        # Extract RGB and Alpha channels (float [0..1])
        rgb = image_array[..., :3].astype(np.float32)
        alpha = image_array[..., 3:4].astype(np.float32)
        
        # Composite on WHITE background: result = rgb*alpha + white*(1-alpha)
        # This matches master's expectation (dark lines on light background)
        composited = rgb * alpha + 1.0 * (1.0 - alpha)
        
        # Convert to grayscale using OpenCV weights (matches master's cvtColor BGR2GRAY)
        # Formula: 0.299*R + 0.587*G + 0.114*B
        gray = (0.299 * composited[..., 0] + 
                0.587 * composited[..., 1] + 
                0.114 * composited[..., 2])
        
        # Convert to uint8 [0..255] with rounding (not truncation!)
        image_array = np.clip(gray * 255.0 + 0.5, 0, 255).astype(np.uint8)
        
    elif image_array.shape[2] == 3:  # RGB (no alpha)
        # Convert RGB to grayscale using same weights as OpenCV
        if image_array.dtype in [np.float32, np.float64]:
            gray = (0.299 * image_array[..., 0] + 
                    0.587 * image_array[..., 1] + 
                    0.114 * image_array[..., 2])
            image_array = np.clip(gray * 255.0 + 0.5, 0, 255).astype(np.uint8)
        else:  # already uint8
            gray = (0.299 * image_array[..., 0].astype(np.float32) + 
                    0.587 * image_array[..., 1].astype(np.float32) + 
                    0.114 * image_array[..., 2].astype(np.float32))
            image_array = np.clip(gray + 0.5, 0, 255).astype(np.uint8)
    
    elif image_array.shape[2] == 1:  # Already grayscale
        if image_array.dtype in [np.float32, np.float64]:
            image_array = np.clip(image_array[..., 0] * 255.0 + 0.5, 0, 255).astype(np.uint8)
        else:
            image_array = image_array[..., 0].astype(np.uint8)
    
    else:
        raise ValueError(f"Unexpected image shape: {image_array.shape}. Expected H×W×C with C=1,3,4")
    
    # Now image_array is H×W grayscale uint8, ready for master-equivalent processing
    # Master will do: invert → threshold → repairMask → gradient → optimize
    # (all handled in C++ polyvector_core.cpp)
    
    # Call LineVector (threshold=90 matches master default)
    strokes = gp_linevector.vectorize_array(
        image_array,
        threshold=90,
        blur_pixels=int(blur_pixels),
        verbose=bool(verbose),
    )
    
    # Convert to numpy arrays
    polylines = []
    for stroke in strokes:
        if len(stroke) >= 2:  # Need at least 2 points
            points = np.array(stroke, dtype=np.float32)
            polylines.append(points)
    
    return polylines


