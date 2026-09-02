

interpolator_module = None
_interpolator_instance = None


def load():
    global interpolator_module, _interpolator_instance

    if interpolator_module is not None:
        return  # Already loaded

    try:

        try:
            from ..utils.dll_loader import add_wheel_dll_dirs
            add_wheel_dll_dirs("gp_autointerpolate")
        except Exception:
            pass

        import gp_autointerpolate
        interpolator_module = gp_autointerpolate
        _interpolator_instance = None
    except ImportError as e:
        print(f"[GPAI] ERROR: Failed to load module from wheel: {e}")
        interpolator_module = None
        _interpolator_instance = None


def get_interpolator():
    global _interpolator_instance
    if interpolator_module is None:
        raise RuntimeError("Module not loaded")
    if _interpolator_instance is None:
        _interpolator_instance = interpolator_module.Interpolator()
    return _interpolator_instance
