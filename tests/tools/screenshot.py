"""Render the main window to a PNG so the UI can be checked without a human."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from serview.ui.main_window import MainWindow


def main() -> int:
    ser_path, out_path = sys.argv[1], sys.argv[2]
    app = QApplication([sys.argv[0]])
    window = MainWindow()
    window.resize(1180, 820)
    window.show()
    window.load_file(ser_path)
    target = window
    if len(sys.argv) > 3:
        for command in sys.argv[3].split(","):
            widget = _run_command(window, command)
            if widget is not None:
                target = widget

    def grab() -> None:
        target.grab().save(out_path)
        app.quit()

    QTimer.singleShot(700, grab)
    return app.exec()


def _run_command(window: MainWindow, command: str):
    """Run one scripted UI action; returns a widget to screenshot, if any."""
    if command == "processing":
        window.show_processing()
        return window.processing_dialog
    if command == "histogram":
        window.show_histogram()
        return window.histogram_dialog
    if command == "header":
        window.show_header()
        return window.header_dialog
    if command == "fits":
        from serview.ui.fits_dialog import FitsExportDialog
        dialog = FitsExportDialog(window.reader, window.processor, window.current_index,
                                  window.playback_bar.markers, window)
        dialog.show()
        return dialog
    if command == "frames":
        from serview.ui.frames_dialog import ExportFramesDialog
        dialog = ExportFramesDialog(window.reader, window.processor, window.current_index,
                                    window.playback_bar.markers, 25.0, window)
        dialog.show()
        return dialog
    if command.startswith("frame:"):
        window.show_frame(int(command.split(":")[1]))
    elif command.startswith("gamma:"):
        window.options.gamma = float(command.split(":")[1])
        window._on_options_changed(window.options)
    elif command.startswith("crop:"):
        from serview.imaging.pipeline import CropRect
        x, y, w, h = (int(v) for v in command.split(":")[1].split("x"))
        window.options.crop = CropRect(x, y, w, h)
        window._on_options_changed(window.options)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
