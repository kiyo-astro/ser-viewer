"""Smoke tests for the Qt user interface (run with the offscreen platform)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from serview.imaging import CropRect  # noqa: E402
from serview.ui.fits_dialog import FitsExportDialog  # noqa: E402
from serview.ui.frames_dialog import ExportFramesDialog  # noqa: E402
from serview.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def window(app, bayer12_ser, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    window = MainWindow()
    window.load_file(bayer12_ser)
    yield window
    window.close_file()
    window.deleteLater()


def test_window_loads_a_file(window, bayer12_ser):
    assert window.reader is not None
    assert window.frame_count == 8
    assert window.image_view.image_size == (64, 48)
    assert "Bayer" in window.file_label.text()


def test_stepping_and_markers(window):
    window.show_frame(3)
    assert window.current_index == 3
    window.step_frame(1)
    assert window.current_index == 4
    window.playback_bar.mark_start()
    window.show_frame(6)
    window.playback_bar.mark_end()
    assert window.playback_bar.markers == (4, 6)
    window.show_frame(6)
    window.step_frame(1)          # wraps back to the start marker
    assert window.current_index == 4


def test_playback_starts_and_stops(window):
    window.set_playing(True)
    assert window.timer.isActive()
    window.set_playing(False)
    assert not window.timer.isActive()


def test_processing_dialog_updates_the_display(window):
    window.show_processing()
    dialog = window.processing_dialog
    before = window._display_image.mean()
    dialog.gain_slider.setValue(2.0)
    dialog._emit()
    assert window.options.gain == pytest.approx(2.0)
    assert window._display_image.mean() > before
    dialog.reset_all()
    assert window.options.gain == pytest.approx(1.0)


def test_selection_sets_the_crop(window):
    from PySide6.QtCore import QRect

    window._on_selection_changed(QRect(4, 6, 20, 10))
    assert window.options.crop == CropRect(4, 6, 20, 10)
    assert window.image_view.image_size == (20, 10)


def test_histogram_and_header_dialogs(window):
    window.show_histogram()
    assert window.histogram_dialog.plot.histogram is not None
    window.show_header()
    assert window.header_dialog.table.rowCount() > 10


def test_fits_dialog_defaults_to_raw_for_bayer(window):
    dialog = FitsExportDialog(window.reader, window.processor, 0,
                              window.playback_bar.markers, window)
    assert dialog.options().colour_mode == "raw"
    assert len(dialog.indices()) == window.frame_count
    assert "MB" in dialog.summary_label.text() or "KB" in dialog.summary_label.text()
    dialog.range_widget.current_radio.setChecked(True)
    assert dialog.indices() == [0]
    dialog.deleteLater()


def test_frames_dialog_builds_every_exporter(window, tmp_path):
    dialog = ExportFramesDialog(window.reader, window.processor, 0,
                                window.playback_bar.markers, 25.0, window)
    for index in range(dialog.target_combo.count()):
        dialog.target_combo.setCurrentIndex(index)
        exporter = dialog.build_exporter()
        assert exporter is not None
        assert dialog.path().endswith(
            {"images": ".png", "video": ".avi", "gif": ".gif", "ser": ".ser"}[dialog.target]
        )
    dialog.deleteLater()


def test_export_runs_through_the_worker(window, tmp_path):
    from serview.export.fits import FitsExporter, FitsExportOptions
    from serview.ui.export_common import ExportWorker

    exporter = FitsExporter(window.reader, window.processor,
                            FitsExportOptions(colour_mode="raw"))
    out = str(tmp_path / "worker.fits")
    worker = ExportWorker(exporter, out, [0, 1, 2])
    results: list = []
    worker.finished_ok.connect(results.append)
    worker.start()
    worker.wait(20000)
    QApplication.processEvents()
    assert results and os.path.exists(out)


def test_dialogs_fit_on_the_screen(window):
    """The option dialogs must never be taller than the screen.

    They used to be laid out at their full natural height, so on a laptop the
    bottom - including the buttons - was cut off and unreachable.
    """
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QDialogButtonBox

    from serview.ui.fits_dialog import FitsExportDialog
    from serview.ui.frames_dialog import ExportFramesDialog

    available = QGuiApplication.primaryScreen().availableGeometry()
    window.show_processing()
    dialogs = [
        window.processing_dialog,
        FitsExportDialog(window.reader, window.processor, 0,
                         window.playback_bar.markers, window),
        ExportFramesDialog(window.reader, window.processor, 0,
                           window.playback_bar.markers, 25.0, window),
    ]
    for dialog in dialogs:
        dialog.show()
        QApplication.processEvents()
        assert dialog.height() <= available.height(), f"{dialog.windowTitle()} is too tall"
        assert dialog.width() <= available.width(), f"{dialog.windowTitle()} is too wide"
        # It must also be possible to shrink the dialog on a small display.
        assert dialog.minimumSizeHint().height() <= 400

        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        bottom = buttons.mapTo(dialog, buttons.rect().bottomLeft()).y()
        assert bottom <= dialog.height(), f"{dialog.windowTitle()} buttons are off-screen"
        dialog.close()
        dialog.deleteLater()


def test_about_box_text():
    from serview import __version__
    from serview.ui.about_dialog import about_html

    text = about_html(__version__)
    for expected in (
        f"SER Viewer {__version__}",
        "A player for SER astronomy video format.",
        "Inspired by SER Player by Chris Garry.",
        "Built with PySide6, NumPy, OpenCV and Astropy.",
        "Application developed by Kiyoaki Okudaira - Kyushu University "
        "Hanada Lab (Space Systems Dynamics)",
        "Supported by JSPS KAKENHI Grant Number JP26H02172.",
    ):
        assert expected in text


def test_tool_windows_have_normal_title_bar_buttons(window):
    """Qt.Tool draws macOS utility panels with undersized window buttons."""
    from PySide6.QtCore import Qt

    window.show_processing()
    window.show_histogram()
    window.show_header()
    for dialog in (window.processing_dialog, window.histogram_dialog, window.header_dialog):
        flags = dialog.windowFlags()
        assert (flags & Qt.Tool) != Qt.Tool, f"{dialog.windowTitle()} is still a tool window"
        for hint in (Qt.WindowCloseButtonHint, Qt.WindowMinimizeButtonHint,
                     Qt.WindowMaximizeButtonHint):
            assert flags & hint, f"{dialog.windowTitle()} is missing {hint}"


def test_window_title_uses_the_application_name(window, bayer12_ser):
    import os

    assert window.windowTitle() == f"{os.path.basename(bayer12_ser)} - SER Viewer"
    window.close_file()
    assert window.windowTitle() == "SER Viewer"


def test_closing_the_main_window_closes_the_tool_dialogs(window):
    window.show_processing()
    window.show_histogram()
    window.show_header()
    window.close()
    for dialog in (window.processing_dialog, window.histogram_dialog, window.header_dialog):
        assert not dialog.isVisible()
