"""Windows DLL loader helpers.

Blender extensions often ship binary wheels repaired with `delvewheel`, which places
external DLL dependencies in a sibling "<package>.libs" folder next to the `.pyd`.

On Windows, Python may fail to import the extension module if that directory is not
on the DLL search path. Since Python 3.8, the correct way to extend the DLL search
path is `os.add_dll_directory`.

This module provides a small helper to be called *before* importing binary modules.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
from typing import Iterable, List


_added_dirs: List[os.PathLike] = []


def _candidate_lib_dirs(module_stem: str) -> Iterable[Path]:
    """Return possible DLL-containing directories for a given module/package name.

    `delvewheel` commonly uses `<distname>.libs/`, but depending on install layout
    (notably Blender Extensions), wheels may also end up with DLLs located under
    `<distname>-<ver>.data/platlib/`.
    """
    # Rare: add-on-local folder
    yield Path(__file__).resolve().parent.parent / f"{module_stem}.libs"  # Addon/<pkg>.libs

    for p in sys.path:
        try:
            pp = Path(p)
        except Exception:
            continue

        # Typical delvewheel layout
        yield pp / f"{module_stem}.libs"

        # Blender Extensions observed layout:
        #   gp_linevector-1.0.0.data/platlib/*.dll
        # We add platlib itself, and also any nested *.libs directories just in case.
        data_glob = f"{module_stem}-*.data"
        try:
            for data_dir in pp.glob(data_glob):
                platlib = data_dir / "platlib"
                if platlib.exists():
                    yield platlib
                    # Some tools may still create a .libs folder under platlib
                    yield platlib / f"{module_stem}.libs"
        except Exception:
            # If pp isn't a real filesystem path or glob fails, ignore.
            continue


def add_wheel_dll_dirs(module_stem: str) -> None:
    """Add wheel-bundled DLL directories to Windows DLL search path.

    Safe to call multiple times.

    Args:
        module_stem: e.g. "gp_linevector" or "gp_autointerpolate"
    """
    if sys.platform != "win32":
        return

    # Only available on Python 3.8+
    add_dir = getattr(os, "add_dll_directory", None)
    if add_dir is None:
        return

    for d in _candidate_lib_dirs(module_stem):
        if not d.is_dir():
            continue
        d_str = str(d)
        # Avoid re-adding the same directory
        if any(str(x) == d_str for x in _added_dirs):
            continue
        try:
            add_dir(d_str)
            _added_dirs.append(d)
        except OSError:
            # If Blender/python rejects the directory for any reason, ignore and continue.
            continue
