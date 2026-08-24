"""Application entry point."""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__
from .ui.main_window import MainWindow


def build_icon() -> QIcon:
    path = os.path.join(os.path.dirname(__file__), "resources", "serview.png")
    return QIcon(path) if os.path.exists(path) else QIcon()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="serview", description=__doc__)
    parser.add_argument("file", nargs="?", help="SER file to open on startup")
    parser.add_argument("--version", action="version", version=f"SER Viewer {__version__}")
    parser.add_argument("--selftest", action="store_true",
                        help="run a headless self-test and exit (used to check builds)")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.selftest:
        from .selftest import main as selftest_main
        return selftest_main()

    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("SER Viewer")
    app.setApplicationDisplayName("SER Viewer")
    app.setOrganizationName("SER Viewer")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(build_icon())

    window = MainWindow()
    window.show()
    if args.file:
        window.load_file(os.path.abspath(args.file))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
