
from __future__ import annotations

from pathlib import Path
import os
import sys
from typing import Iterable, List


_added_dirs: List[os.PathLike] = []


def _candidate_lib_dirs(module_stem: str) -> Iterable[Path]:

    yield Path(__file__).resolve().parent.parent / f"{module_stem}.libs"  # Addon/<pkg>.libs

    for p in sys.path:
        try:
            pp = Path(p)
        except Exception:
            continue


        yield pp / f"{module_stem}.libs"




        data_glob = f"{module_stem}-*.data"
        try:
            for data_dir in pp.glob(data_glob):
                platlib = data_dir / "platlib"
                if platlib.exists():
                    yield platlib

                    yield platlib / f"{module_stem}.libs"
        except Exception:

            continue


def add_wheel_dll_dirs(module_stem: str) -> None:
    if sys.platform != "win32":
        return


    add_dir = getattr(os, "add_dll_directory", None)
    if add_dir is None:
        return

    for d in _candidate_lib_dirs(module_stem):
        if not d.is_dir():
            continue
        d_str = str(d)

        if any(str(x) == d_str for x in _added_dirs):
            continue
        try:
            add_dir(d_str)
            _added_dirs.append(d)
        except OSError:

            continue
