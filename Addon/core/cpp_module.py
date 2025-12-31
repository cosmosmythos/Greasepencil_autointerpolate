"""
C++ Module Loader
Loads the wheel-provided C++ module
"""

# Global reference to C++ module
interpolator_module = None


def load():
    """Load the C++ interpolation module from wheel"""
    global interpolator_module
    
    if interpolator_module is not None:
        return  # Already loaded
    
    try:
        import gp_autointerpolate  # Direct import from wheel
        interpolator_module = gp_autointerpolate
        print("[GPAI] Module loaded successfully")
    except ImportError as e:
        print(f"[GPAI] ERROR: Failed to load C++ module from wheel: {e}")
        import sys
        print(f"[GPAI] DEBUG: sys.path contains:")
        for p in sys.path:
            if 'gp_auto' in p.lower() or 'extension' in p.lower():
                print(f"  {p}")
        interpolator_module = None


def get_interpolator():
    """Get an instance of the C++ Interpolator"""
    if interpolator_module is None:
        raise RuntimeError("C++ module not loaded. Call cpp_module.load() first.")
    return interpolator_module.Interpolator()
