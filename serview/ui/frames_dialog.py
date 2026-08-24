"""Export frames as still images, video or a new SER file."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..export.images import ImageExportOptions, ImageExporter
from ..export.ser import SerExportOptions, SerFileExporter
from ..export.video import VIDEO_CODECS, VideoExportOptions, VideoExporter
from ..imaging.pipeline import FrameProcessor
from ..ser.reader import SerReader
from .export_common import FrameRangeWidget
from .widgets import fit_to_screen, scrollable

TARGETS = (
    ("Still images (PNG / TIFF / BMP / JPEG)", "images"),
    ("Video (AVI / MP4)", "video"),
    ("Animated GIF", "gif"),
    ("SER file", "ser"),
)

IMAGE_EXTENSIONS = ((".png", "PNG"), (".tif", "TIFF"), (".bmp", "BMP"), (".jpg", "JPEG"))


class ExportFramesDialog(QDialog):
    """One dialog for every non-FITS export target."""

    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 current_frame: int, markers: tuple[int, int],
                 playback_fps: float = 25.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export frames")
        self.reader = reader
        self.processor = processor

        self.target_combo = QComboBox(self)
        for label, key in TARGETS:
            self.target_combo.addItem(label, key)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)

        self.path_edit = QLineEdit(os.path.splitext(reader.path)[0] + "_export.png", self)
        browse = QPushButton("Browse...", self)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        output_group = QGroupBox("Output", self)
        output_form = QFormLayout(output_group)
        output_form.addRow("Save as:", self.target_combo)
        output_form.addRow("File:", path_row)

        self.range_widget = FrameRangeWidget(reader.frame_count, current_frame, markers, self)
        self.range_widget.set_change_handler(self._refresh)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._build_image_page())
        self.stack.addWidget(self._build_video_page(playback_fps))
        self.stack.addWidget(self._build_gif_page())
        self.stack.addWidget(self._build_ser_page())

        common = QGroupBox("Common", self)
        common_form = QFormLayout(common)
        self.processing_check = QCheckBox("Apply the display processing", self)
        self.processing_check.setChecked(True)
        self.processing_check.toggled.connect(self._refresh)
        self.crop_check = QCheckBox("Apply the crop", self)
        self.crop_check.setChecked(True)
        self.resize_check = QCheckBox("Resize to:", self)
        self.resize_width = QSpinBox(self)
        self.resize_width.setRange(1, 20000)
        self.resize_width.setValue(reader.width)
        self.resize_height = QSpinBox(self)
        self.resize_height.setRange(1, 20000)
        self.resize_height.setValue(reader.height)
        self.resize_width.setEnabled(False)
        self.resize_height.setEnabled(False)
        self.resize_check.toggled.connect(self.resize_width.setEnabled)
        self.resize_check.toggled.connect(self.resize_height.setEnabled)
        resize_row = QHBoxLayout()
        resize_row.addWidget(self.resize_check)
        resize_row.addWidget(self.resize_width)
        resize_row.addWidget(QLabel("x", self))
        resize_row.addWidget(self.resize_height)
        resize_row.addStretch(1)
        common_form.addRow(self.processing_check)
        common_form.addRow(self.crop_check)
        common_form.addRow(resize_row)
        self.common_group = common

        self.summary_label = QLabel(self)
        self.summary_label.setTextFormat(Qt.RichText)
        self.summary_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        fit_to_screen(self, 560, 760)

        layout = QVBoxLayout(self)
        layout.addWidget(
            scrollable(output_group, self.range_widget, self.stack, common, parent=self),
            1,
        )
        layout.addWidget(self.summary_label)
        layout.addWidget(buttons)
        self._refresh()

    # -- pages ---------------------------------------------------------------
    def _build_image_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.image_format_combo = QComboBox(page)
        for extension, label in IMAGE_EXTENSIONS:
            self.image_format_combo.addItem(label, extension)
        self.image_format_combo.currentIndexChanged.connect(self._on_image_format_changed)
        self.image_depth_combo = QComboBox(page)
        self.image_depth_combo.addItem("8 bit", 8)
        self.image_depth_combo.addItem("16 bit", 16)
        self.jpeg_quality = QSpinBox(page)
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(95)
        self.jpeg_quality.setEnabled(False)
        form.addRow("Format:", self.image_format_combo)
        form.addRow("Bit depth:", self.image_depth_combo)
        form.addRow("JPEG quality:", self.jpeg_quality)
        return page

    def _build_video_page(self, playback_fps: float) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.codec_combo = QComboBox(page)
        for label in VIDEO_CODECS:
            self.codec_combo.addItem(label, label)
        self.codec_combo.setCurrentIndex(
            max(0, self.codec_combo.findData("Motion JPEG AVI")))
        self.codec_combo.currentIndexChanged.connect(self._sync_extension)
        self.video_fps = QDoubleSpinBox(page)
        self.video_fps.setRange(0.1, 240.0)
        self.video_fps.setValue(playback_fps)
        self.video_fps.setSuffix(" fps")
        form.addRow("Codec:", self.codec_combo)
        form.addRow("Frame rate:", self.video_fps)
        return page

    def _build_gif_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.gif_delay = QSpinBox(page)
        self.gif_delay.setRange(10, 10000)
        self.gif_delay.setValue(40)
        self.gif_delay.setSuffix(" ms")
        self.gif_final_delay = QSpinBox(page)
        self.gif_final_delay.setRange(10, 20000)
        self.gif_final_delay.setValue(40)
        self.gif_final_delay.setSuffix(" ms")
        self.gif_colours = QSpinBox(page)
        self.gif_colours.setRange(2, 256)
        self.gif_colours.setValue(256)
        self.gif_loop = QCheckBox("Loop forever", page)
        self.gif_loop.setChecked(True)
        form.addRow("Frame delay:", self.gif_delay)
        form.addRow("Final frame delay:", self.gif_final_delay)
        form.addRow("Colours:", self.gif_colours)
        form.addRow(self.gif_loop)
        return page

    def _build_ser_page(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.ser_debayer = QCheckBox("Debayer into an RGB SER file", page)
        self.ser_mono = QCheckBox("Convert to monochrome", page)
        self.ser_depth = QComboBox(page)
        self.ser_depth.addItem("Keep the original depth", 0)
        self.ser_depth.addItem("8 bit", 8)
        self.ser_depth.addItem("16 bit", 16)
        note = QLabel(
            "With the display processing switched off the pixel values are copied\n"
            "unchanged, so this is a lossless trim/crop of the original file.", page)
        note.setWordWrap(True)
        form.addRow(self.ser_debayer)
        form.addRow(self.ser_mono)
        form.addRow("Bit depth:", self.ser_depth)
        form.addRow(note)
        return page

    # -- behaviour -------------------------------------------------------------
    @property
    def target(self) -> str:
        return self.target_combo.currentData()

    def _on_target_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        is_ser = self.target == "ser"
        self.processing_check.setChecked(not is_ser)
        self.resize_check.setEnabled(not is_ser)
        if is_ser:
            self.resize_check.setChecked(False)
        self._sync_extension()
        self._refresh()

    def _on_image_format_changed(self, index: int) -> None:
        extension = self.image_format_combo.currentData()
        self.jpeg_quality.setEnabled(extension in (".jpg", ".jpeg"))
        self.image_depth_combo.setEnabled(extension in (".png", ".tif", ".tiff"))
        self._sync_extension()
        self._refresh()

    def _sync_extension(self, *args) -> None:
        base = os.path.splitext(self.path_edit.text())[0]
        if self.target == "images":
            extension = self.image_format_combo.currentData()
        elif self.target == "video":
            extension = VIDEO_CODECS[self.codec_combo.currentData()][0]
        elif self.target == "gif":
            extension = ".gif"
        else:
            extension = ".ser"
        self.path_edit.setText(base + extension)

    def _browse(self) -> None:
        filters = {
            "images": "Images (*.png *.tif *.tiff *.bmp *.jpg)",
            "video": "Video (*.avi *.mp4)",
            "gif": "Animated GIF (*.gif)",
            "ser": "SER files (*.ser)",
        }[self.target]
        path, _ = QFileDialog.getSaveFileName(self, "Export frames", self.path_edit.text(), filters)
        if path:
            self.path_edit.setText(path)
            self._refresh()

    def _resize_target(self) -> tuple[int, int] | None:
        if not self.resize_check.isChecked():
            return None
        return self.resize_width.value(), self.resize_height.value()

    # -- results ----------------------------------------------------------------
    def indices(self) -> list[int]:
        return self.range_widget.indices()

    def path(self) -> str:
        return self.path_edit.text().strip()

    def build_exporter(self):
        """Create the exporter matching the current selection."""
        processor = self.processor
        if not self.processing_check.isChecked():
            passthrough = processor.options.copy()
            for name, value in (("gain", 1.0), ("gamma", 1.0), ("black_level", 0.0),
                                ("saturation", 1.0), ("red_balance", 1.0),
                                ("green_balance", 1.0), ("blue_balance", 1.0),
                                ("auto_stretch", False), ("invert", False)):
                setattr(passthrough, name, value)
            processor = FrameProcessor(processor.colour_id, processor.pixel_depth, passthrough)
        if not self.crop_check.isChecked():
            options = processor.options.copy()
            options.crop.width = options.crop.height = 0
            processor = FrameProcessor(processor.colour_id, processor.pixel_depth, options)

        target = self.target
        if target == "images":
            return ImageExporter(self.reader, processor, ImageExportOptions(
                extension=self.image_format_combo.currentData(),
                bit_depth=self.image_depth_combo.currentData(),
                jpeg_quality=self.jpeg_quality.value(),
                resize=self._resize_target(),
                single_file=len(self.indices()) == 1,
            ))
        if target == "video":
            return VideoExporter(self.reader, processor, VideoExportOptions(
                codec=self.codec_combo.currentData(),
                fps=self.video_fps.value(),
                resize=self._resize_target(),
            ))
        if target == "gif":
            return VideoExporter(self.reader, processor, VideoExportOptions(
                resize=self._resize_target(),
                gif_delay_ms=self.gif_delay.value(),
                gif_final_delay_ms=self.gif_final_delay.value(),
                gif_loop=self.gif_loop.isChecked(),
                gif_colours=self.gif_colours.value(),
            ))
        return SerFileExporter(self.reader, processor, SerExportOptions(
            apply_processing=self.processing_check.isChecked(),
            apply_crop=self.crop_check.isChecked(),
            debayer=self.ser_debayer.isChecked(),
            to_mono=self.ser_mono.isChecked(),
            bit_depth=self.ser_depth.currentData(),
        ))

    def _refresh(self, *args) -> None:
        count = len(self.indices())
        target = self.target
        if target == "images":
            files = f"{count} image file(s)"
        elif target == "ser":
            files = "1 SER file"
        else:
            files = "1 file"
        self.summary_label.setText(f"<b>{files}</b> from {count} frame(s).")
