"""PyInstaller entry point.

The bundled script runs as ``__main__`` with no package context, so it cannot
use the relative imports that ``serview/main.py`` does; go through the package
instead.
"""

import multiprocessing
import os
import sys


def _ensure_streams() -> None:
    """A windowed Windows build has no stdout, and ``print`` would then fail."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _ensure_streams()

    from serview.main import main

    sys.exit(main())
