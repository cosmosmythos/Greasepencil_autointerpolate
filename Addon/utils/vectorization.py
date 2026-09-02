
import numpy as np
from typing import List


try:
    from .dll_loader import add_wheel_dll_dirs

    add_wheel_dll_dirs("gp_linevector")
except Exception:

    pass


try:
    import gp_linevector

    _linevector_available = True
except ImportError as e:
    _linevector_available = False
    print(f"[GPAI Lineart] ERROR: LineVector module not available: {e}")
    print("[GPAI Lineart] Please ensure wheels are installed via blender_manifest.toml")


def is_backend_available() -> bool:

    return _linevector_available


def process_image_file(
    filepath: str,
    blur_pixels: int = 0,
    verbose: bool = False,
) -> List[np.ndarray]:

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
