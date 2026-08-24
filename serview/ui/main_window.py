"""The SER Viewer main window."""

from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QRect, QSettings, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from ..export.fits import FitsExporter
from ..imaging.pipeline import FrameProcessor, ProcessingOptions
from ..ser.reader import SerError, SerReader
from .about_dialog import AboutDialog
from .export_common import ExportWorker
from .fits_dialog import FitsExportDialog
from .frames_dialog import ExportFramesDialog
from .header_dialog import HeaderDialog
from .histogram_dialog import HistogramDialog
from .image_view import ImageView
from .playback_bar import PlaybackBar
from .processing_dialog import ProcessingDialog

MAX_RECENT_FILES = 10




class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SER Viewer")
        self.resize(1100, 760)
        self.setAcceptDrops(True)

        self.settings = QSettings("SER Viewer", "SER Viewer")
        self.reader: SerReader | None = None
        self.processor: FrameProcessor | None = None
        self.options = ProcessingOptions()
        self.current_index = 0
        self._display_image: np.ndarray | None = None
        self._raw_frame: np.ndarray | None = None
        self._playing = False

        self.image_view = ImageView(self)
        self.image_view.cursor_moved.connect(self._on_cursor_moved)
        self.image_view.selection_changed.connect(self._on_selection_changed)
        self.image_view.zoom_changed.connect(self._on_zoom_changed)
        self.image_view.double_clicked.connect(self.toggle_play)

        self.playback_bar = PlaybackBar(self)
        self.playback_bar.play_toggled.connect(self.set_playing)
        self.playback_bar.frame_requested.connect(self.show_frame)
        self.playback_bar.step_requested.connect(self.step_frame)
        self.playback_bar.fps_changed.connect(self._on_fps_changed)
        self.playback_bar.markers_changed.connect(lambda *_: self._update_status())

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.image_view, 1)
        layout.addWidget(self.playback_bar)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

        self.processing_dialog: ProcessingDialog | None = None
        self.histogram_dialog: HistogramDialog | None = None
        self.header_dialog: HeaderDialog | None = None

        self._build_actions()
        self._build_status_bar()
        self._update_actions()
        self._restore_geometry()

    # -- construction ---------------------------------------------------------
    def _build_actions(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        self.open_action = self._action("&Open SER file...", QKeySequence.Open, self.open_file)
        file_menu.addAction(self.open_action)
        self.recent_menu = file_menu.addMenu("Open &recent")
        self._rebuild_recent_menu()
        self.close_action = self._action("&Close file", QKeySequence.Close, self.close_file)
        file_menu.addAction(self.close_action)
        file_menu.addSeparator()
        self.export_fits_action = self._action(
            "Export to &FITS...", QKeySequence("Ctrl+E"), self.export_fits)
        file_menu.addAction(self.export_fits_action)
        self.export_frames_action = self._action(
            "Export frames as images, video or SER...", QKeySequence("Ctrl+Shift+E"),
            self.export_frames)
        file_menu.addAction(self.export_frames_action)
        file_menu.addSeparator()
        quit_action = self._action("&Quit", QKeySequence.Quit, self.close)
        quit_action.setMenuRole(QAction.QuitRole)
        file_menu.addAction(quit_action)

        play_menu = menu.addMenu("&Playback")
        self.play_action = self._action("&Play / pause", QKeySequence(Qt.Key_Space), self.toggle_play)
        play_menu.addAction(self.play_action)
        play_menu.addAction(self._action("Next frame", QKeySequence(Qt.Key_Right),
                                         lambda: self.step_frame(1)))
        play_menu.addAction(self._action("Previous frame", QKeySequence(Qt.Key_Left),
                                         lambda: self.step_frame(-1)))
        play_menu.addAction(self._action("Forward 10 frames", QKeySequence(Qt.Key_PageDown),
                                         lambda: self.step_frame(10)))
        play_menu.addAction(self._action("Back 10 frames", QKeySequence(Qt.Key_PageUp),
                                         lambda: self.step_frame(-10)))
        play_menu.addAction(self._action("First frame", QKeySequence(Qt.Key_Home),
                                         lambda: self.show_frame(0)))
        play_menu.addAction(self._action("Last frame", QKeySequence(Qt.Key_End),
                                         lambda: self.show_frame(self.frame_count - 1)))
        play_menu.addSeparator()
        play_menu.addAction(self._action("Set start marker", QKeySequence(Qt.Key_BracketLeft),
                                         self.playback_bar.mark_start))
        play_menu.addAction(self._action("Set end marker", QKeySequence(Qt.Key_BracketRight),
                                         self.playback_bar.mark_end))
        play_menu.addAction(self._action("Clear markers", QKeySequence("Ctrl+["),
                                         self.playback_bar.clear_markers))

        view_menu = menu.addMenu("&View")
        view_menu.addAction(self._action("Zoom &in", QKeySequence.ZoomIn, self.image_view.zoom_in))
        view_menu.addAction(self._action("Zoom &out", QKeySequence.ZoomOut, self.image_view.zoom_out))
        view_menu.addAction(self._action("Actual size (100%)", QKeySequence("Ctrl+1"),
                                         lambda: self.image_view.set_zoom(1.0)))
        view_menu.addAction(self._action("Fit to window", QKeySequence("Ctrl+0"),
                                         self.image_view.zoom_to_fit))
        view_menu.addSeparator()
        self.selection_action = self._action("Selection box mode", QKeySequence("Ctrl+B"), None)
        self.selection_action.setCheckable(True)
        self.selection_action.toggled.connect(self.image_view.set_selection_mode)
        view_menu.addAction(self.selection_action)
        view_menu.addSeparator()
        self.fullscreen_action = self._action("Full screen", QKeySequence.FullScreen, None)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.toggled.connect(self._on_fullscreen)
        view_menu.addAction(self.fullscreen_action)

        tools_menu = menu.addMenu("&Tools")
        self.processing_action = self._action("&Processing...", QKeySequence("Ctrl+P"),
                                              self.show_processing)
        tools_menu.addAction(self.processing_action)
        self.histogram_action = self._action("&Histogram...", QKeySequence("Ctrl+H"),
                                             self.show_histogram)
        tools_menu.addAction(self.histogram_action)
        self.header_action = self._action("File &details...", QKeySequence("Ctrl+I"),
                                          self.show_header)
        tools_menu.addAction(self.header_action)

        help_menu = menu.addMenu("&Help")
        about_action = self._action("&About SER Viewer", None, self.show_about)
        about_action.setMenuRole(QAction.AboutRole)
        help_menu.addAction(about_action)

    def _action(self, text: str, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if slot is not None:
            action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_status_bar(self) -> None:
        self.file_label = QLabel("No file loaded", self)
        self.pixel_label = QLabel("", self)
        self.zoom_label = QLabel("", self)
        bar = self.statusBar()
        bar.addWidget(self.file_label, 1)
        bar.addPermanentWidget(self.pixel_label)
        bar.addPermanentWidget(self.zoom_label)

    # -- file handling ----------------------------------------------------------
    @property
    def frame_count(self) -> int:
        return self.reader.frame_count if self.reader else 0

    def open_file(self) -> None:
        directory = self.settings.value("last_directory", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SER file", directory, "SER files (*.ser *.SER);;All files (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        self.set_playing(False)
        try:
            reader = SerReader(path)
        except (SerError, ValueError, OSError) as error:
            QMessageBox.critical(self, "Cannot open the SER file",
                                 f"{os.path.basename(path)} could not be opened.\n\n{error}")
            return
        if self.reader is not None:
            self.reader.close()
        self.reader = reader
        self.options = ProcessingOptions()
        self.processor = FrameProcessor(reader.colour_id, reader.pixel_depth, self.options)
        self.current_index = 0

        self.settings.setValue("last_directory", os.path.dirname(path))
        self._remember_recent(path)

        self.playback_bar.set_frame_count(reader.frame_count)
        self.playback_bar.set_fps(reader.fps or 25.0)
        self.image_view.set_selection(None)
        self.image_view.enable_fit()

        for dialog, attribute in ((self.processing_dialog, "processing_dialog"),
                                  (self.header_dialog, "header_dialog")):
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
                setattr(self, attribute, None)

        self.setWindowTitle(f"{os.path.basename(path)} - SER Viewer")
        self.show_frame(0)
        self.image_view.zoom_to_fit()
        self._update_actions()

        for warning in reader.warnings:
            self.statusBar().showMessage(warning.message, 10000)

    def close_file(self) -> None:
        self.set_playing(False)
        if self.reader is not None:
            self.reader.close()
        self.reader = None
        self.processor = None
        self._display_image = None
        self._raw_frame = None
        self.image_view.set_image(None)
        self.playback_bar.set_frame_count(0)
        self.setWindowTitle("SER Viewer")
        self.file_label.setText("No file loaded")
        for name in ("processing_dialog", "histogram_dialog", "header_dialog"):
            dialog = getattr(self, name)
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
                setattr(self, name, None)
        self._update_actions()

    def _remember_recent(self, path: str) -> None:
        recent = [p for p in self.settings.value("recent_files", []) or [] if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent_files", recent[:MAX_RECENT_FILES])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.settings.value("recent_files", []) or []
        for path in recent:
            action = QAction(os.path.basename(path), self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.load_file(p))
            self.recent_menu.addAction(action)
        self.recent_menu.setEnabled(bool(recent))
        if recent:
            self.recent_menu.addSeparator()
            clear = QAction("Clear the list", self)
            clear.triggered.connect(self._clear_recent)
            self.recent_menu.addAction(clear)

    def _clear_recent(self) -> None:
        self.settings.setValue("recent_files", [])
        self._rebuild_recent_menu()

    # -- playback ----------------------------------------------------------------
    def show_frame(self, index: int) -> None:
        if self.reader is None or self.frame_count == 0:
            return
        index = max(0, min(self.frame_count - 1, int(index)))
        self.current_index = index
        frame = self.reader.frame(index)
        self._raw_frame = frame
        self._display_image = self.processor.to_display(frame)
        self.image_view.set_image(self._display_image)
        self.playback_bar.set_frame(index)
        stamp = self.reader.timestamp(index)
        self.playback_bar.set_time_text(
            stamp.strftime("%H:%M:%S.%f")[:-3] if stamp else "--:--:--.---"
        )
        if self.histogram_dialog is not None and self.histogram_dialog.isVisible():
            self.histogram_dialog.set_image(self._display_image)
        if self.header_dialog is not None and self.header_dialog.isVisible():
            self.header_dialog.refresh(index)
        self._update_status()

    def step_frame(self, delta: int) -> None:
        if self.reader is None:
            return
        start, end = self.playback_bar.markers
        index = self.current_index + delta
        if index > end:
            index = start if self.playback_bar.repeat else end
        elif index < start:
            index = end if self.playback_bar.repeat else start
        self.show_frame(index)

    def toggle_play(self) -> None:
        self.set_playing(not self._playing)

    def set_playing(self, playing: bool) -> None:
        if self.reader is None:
            playing = False
        self._playing = playing
        self.playback_bar.set_playing(playing)
        if playing:
            self.timer.start(max(4, int(1000.0 / max(0.1, self.playback_bar.fps))))
        else:
            self.timer.stop()

    def _on_tick(self) -> None:
        start, end = self.playback_bar.markers
        delta = -1 if self.playback_bar.reverse else 1
        index = self.current_index + delta
        if index > end or index < start:
            if not self.playback_bar.repeat:
                self.set_playing(False)
                return
            index = start if delta > 0 else end
        self.show_frame(index)

    def _on_fps_changed(self, fps: float) -> None:
        if self._playing:
            self.timer.start(max(4, int(1000.0 / max(0.1, fps))))

    # -- tool dialogs ---------------------------------------------------------------
    def show_processing(self) -> None:
        if self.reader is None:
            return
        if self.processing_dialog is None:
            self.processing_dialog = ProcessingDialog(self.options, self.reader.colour_id, self)
            self.processing_dialog.options_changed.connect(self._on_options_changed)
            self.processing_dialog.selection_requested.connect(self._use_selection_as_crop)
        self.processing_dialog.show()
        self.processing_dialog.raise_()

    def show_histogram(self) -> None:
        if self.histogram_dialog is None:
            self.histogram_dialog = HistogramDialog(self)
        self.histogram_dialog.set_image(self._display_image)
        self.histogram_dialog.show()
        self.histogram_dialog.raise_()

    def show_header(self) -> None:
        if self.reader is None:
            return
        if self.header_dialog is None:
            self.header_dialog = HeaderDialog(self.reader, self)
        self.header_dialog.refresh(self.current_index)
        self.header_dialog.show()
        self.header_dialog.raise_()

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def _on_options_changed(self, options: ProcessingOptions) -> None:
        self.options = options
        if self.processor is not None:
            self.processor.options = options
        self.image_view.set_selection(
            QRect(options.crop.x, options.crop.y, options.crop.width, options.crop.height)
            if options.crop.valid else None
        )
        self.show_frame(self.current_index)

    def _use_selection_as_crop(self) -> None:
        self.selection_action.setChecked(True)
        self.statusBar().showMessage(
            "Drag a rectangle on the image to set the crop area", 6000)

    def _on_selection_changed(self, rect: QRect) -> None:
        if self.processing_dialog is None:
            self.show_processing()
        self.processing_dialog.set_crop(rect.x(), rect.y(), rect.width(), rect.height())
        self.selection_action.setChecked(False)

    # -- exporting ---------------------------------------------------------------------
    def export_fits(self) -> None:
        if self.reader is None:
            return
        self.set_playing(False)
        dialog = FitsExportDialog(self.reader, self.processor, self.current_index,
                                  self.playback_bar.markers, self)
        if dialog.exec() != FitsExportDialog.Accepted:
            return
        path = dialog.path()
        if not path:
            return
        exporter = FitsExporter(self.reader, self.processor, dialog.options())
        self._run_export(exporter, path, dialog.indices(), "Exporting to FITS")

    def export_frames(self) -> None:
        if self.reader is None:
            return
        self.set_playing(False)
        dialog = ExportFramesDialog(self.reader, self.processor, self.current_index,
                                    self.playback_bar.markers, self.playback_bar.fps, self)
        if dialog.exec() != ExportFramesDialog.Accepted:
            return
        path = dialog.path()
        if not path:
            return
        self._run_export(dialog.build_exporter(), path, dialog.indices(), "Exporting frames")

    def _run_export(self, exporter, path: str, indices, title: str) -> None:
        if not indices:
            QMessageBox.warning(self, title, "No frames were selected.")
            return
        progress = QProgressDialog(f"{title}...", "Cancel", 0, len(indices), self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = ExportWorker(exporter, path, indices, self)
        worker.progress.connect(lambda done, total: progress.setValue(done))
        progress.canceled.connect(worker.cancel)

        def on_done(written: list[str]) -> None:
            progress.close()
            count = len(written)
            first = written[0] if written else path
            message = (f"{count} file{'s' if count != 1 else ''} written to\n"
                       f"{os.path.dirname(first) or '.'}")
            box = QMessageBox(QMessageBox.Information, "Export finished", message,
                              QMessageBox.Ok, self)
            reveal = box.addButton("Show in folder", QMessageBox.ActionRole)
            box.exec()
            if box.clickedButton() is reveal:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(first) or "."))

        def on_failed(message: str) -> None:
            progress.close()
            if message:
                QMessageBox.critical(self, "Export failed", message)
            else:
                self.statusBar().showMessage("Export cancelled", 5000)

        worker.finished_ok.connect(on_done)
        worker.failed.connect(on_failed)
        worker.start()
        self._export_worker = worker  # keep a reference alive

    # -- status bar -------------------------------------------------------------------
    def _update_status(self) -> None:
        if self.reader is None:
            return
        reader = self.reader
        start, end = self.playback_bar.markers
        marker_text = ""
        if (start, end) != (0, reader.frame_count - 1):
            marker_text = f"  |  markers {start + 1}-{end + 1}"
        fps = reader.fps
        self.file_label.setText(
            f"{os.path.basename(reader.path)}  |  {reader.width}x{reader.height}  |  "
            f"{reader.colour_id.label}  |  {reader.pixel_depth} bit  |  "
            f"{reader.frame_count} frames"
            + (f"  |  {fps:.2f} fps recorded" if fps else "")
            + marker_text
        )

    def _on_cursor_moved(self, x: int, y: int) -> None:
        if x < 0 or self._display_image is None or self.reader is None:
            self.pixel_label.setText("")
            return
        options = self.options
        text = f"({x}, {y})"
        geometry_is_simple = (
            options.rotation == 0 and not options.flip_horizontal and not options.flip_vertical
        )
        if geometry_is_simple:
            crop = options.crop
            source_x = x + (crop.x if crop.valid else 0)
            source_y = y + (crop.y if crop.valid else 0)
            if (self._raw_frame is not None
                    and 0 <= source_x < self.reader.width
                    and 0 <= source_y < self.reader.height):
                raw = self._raw_frame[source_y, source_x]
                values = " / ".join(str(int(v)) for v in np.atleast_1d(raw))
                text = f"({source_x}, {source_y})  ADU {values}"
        else:
            value = self._display_image[y, x]
            text += "  display " + " / ".join(str(int(v)) for v in np.atleast_1d(value))
        self.pixel_label.setText(text)

    def _on_zoom_changed(self, factor: float) -> None:
        self.zoom_label.setText(f"{factor * 100:.0f}%")

    def _update_actions(self) -> None:
        loaded = self.reader is not None
        for action in (self.close_action, self.export_fits_action, self.export_frames_action,
                       self.play_action, self.processing_action, self.header_action,
                       self.selection_action):
            action.setEnabled(loaded)

    def _on_fullscreen(self, enabled: bool) -> None:
        self.showFullScreen() if enabled else self.showNormal()

    # -- window plumbing ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".ser"):
                self.load_file(path)
                break

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.set_playing(False)
        # These are ordinary windows rather than tool panels, so they keep the
        # application alive unless they are closed along with the main window.
        for name in ("processing_dialog", "histogram_dialog", "header_dialog"):
            dialog = getattr(self, name)
            if dialog is not None:
                dialog.close()
        if self.reader is not None:
            self.reader.close()
        super().closeEvent(event)
