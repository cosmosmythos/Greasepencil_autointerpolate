"""
C++ Module Loader
Loads the wheel-provided C++ module
"""

# Global reference to C++ module
interpolator_module = None
_interpolator_instance = None


def load():
    """Load the C++ interpolation module from wheel"""
    global interpolator_module, _interpolator_instance
    
    if interpolator_module is not None:
        return  # Already loaded
    
    try:
        # Ensure wheel-bundled DLLs are discoverable on Windows before importing the extension.
        try:
            from ..utils.dll_loader import add_wheel_dll_dirs
            add_wheel_dll_dirs("gp_autointerpolate")
        except Exception:
            pass

        import gp_autointerpolate  # Direct import from wheel
        interpolator_module = gp_autointerpolate
        _interpolator_instance = None
    except ImportError as e:
        print(f"[GPAI] ERROR: Failed to load module from wheel: {e}")
        interpolator_module = None
        _interpolator_instance = None


def get_interpolator():
    """Get an instance of the C++ Interpolator"""
    global _interpolator_instance
    if interpolator_module is None:
        raise RuntimeError("Module not loaded")
    if _interpolator_instance is None:
        _interpolator_instance = interpolator_module.Interpolator()
    return _interpolator_instance
