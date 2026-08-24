"""The FITS export dialog."""

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
    QVBoxLayout,
)

from ..export.fits import FitsExportOptions
from ..imaging.pipeline import FrameProcessor
from ..ser.reader import SerReader
from .export_common import FrameRangeWidget
from .widgets import fit_to_screen, scrollable

LAYOUTS = (
    ("Single FITS cube (one file, NAXIS3 = frames)", "cube"),
    ("Numbered FITS sequence (one file per frame)", "sequence"),
)

COLOUR_MODES = (
    ("Debayered RGB", "rgb"),
    ("Monochrome", "mono"),
    ("Raw sensor data (no debayer, BAYERPAT keyword)", "raw"),
)

BIT_DEPTHS = (
    ("Keep the original depth", "native"),
    ("16 bit unsigned", "uint16"),
    ("32 bit float (0.0 - 1.0)", "float32"),
)


class FitsExportDialog(QDialog):
    """Collects a path, a frame range and :class:`FitsExportOptions`."""

    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 current_frame: int, markers: tuple[int, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export to FITS")
        self.reader = reader
        self.processor = processor

        default = os.path.splitext(reader.path)[0] + ".fits"
        self.path_edit = QLineEdit(default, self)
        browse = QPushButton("Browse...", self)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        self.layout_combo = QComboBox(self)
        for label, key in LAYOUTS:
            self.layout_combo.addItem(label, key)
        self.layout_combo.currentIndexChanged.connect(self._refresh)

        output_group = QGroupBox("Output", self)
        output_form = QFormLayout(output_group)
        output_form.addRow("File:", path_row)
        output_form.addRow("Layout:", self.layout_combo)

        self.range_widget = FrameRangeWidget(reader.frame_count, current_frame, markers, self)
        self.range_widget.set_change_handler(self._refresh)

        # -- pixel data ---------------------------------------------------
        data_group = QGroupBox("Pixel data", self)
        data_form = QFormLayout(data_group)
        self.colour_combo = QComboBox(self)
        for label, key in COLOUR_MODES:
            self.colour_combo.addItem(label, key)
        if reader.colour_id.is_bayer:
            self.colour_combo.setCurrentIndex(2)  # raw is the usual choice for stacking
        elif not reader.colour_id.is_colour:
            self.colour_combo.setCurrentIndex(1)
        self.colour_combo.currentIndexChanged.connect(self._refresh)

        self.depth_combo = QComboBox(self)
        for label, key in BIT_DEPTHS:
            self.depth_combo.addItem(label, key)
        self.depth_combo.currentIndexChanged.connect(self._refresh)

        self.processing_check = QCheckBox(
            "Apply the display processing (gain, gamma, colour)", self)
        self.processing_check.setToolTip(
            "Off (recommended): the SER pixel values are written unchanged, so the\n"
            "data stays linear and can be stacked or measured.\n"
            "On: what you see in the player is written instead."
        )
        self.processing_check.toggled.connect(self._refresh)

        self.crop_check = QCheckBox("Apply the crop from the processing dialog", self)
        self.crop_check.setChecked(True)
        self.crop_check.toggled.connect(self._refresh)

        self.flip_check = QCheckBox("Store rows bottom-up (flip vertically)", self)
        self.flip_check.setToolTip(
            "SER stores the first row at the top. Most astronomy software reads the\n"
            "ROWORDER keyword that is written either way; enable this only if your\n"
            "software expects classic bottom-up FITS rows."
        )
        self.flip_check.toggled.connect(self._refresh)

        data_form.addRow("Colour:", self.colour_combo)
        data_form.addRow("Bit depth:", self.depth_combo)
        data_form.addRow(self.processing_check)
        data_form.addRow(self.crop_check)
        data_form.addRow(self.flip_check)

        # -- metadata -------------------------------------------------------
        meta_group = QGroupBox("FITS header", self)
        meta_form = QFormLayout(meta_group)
        self.object_edit = QLineEdit(self)
        self.object_edit.setPlaceholderText("e.g. Jupiter, Sun, M42")
        self.observer_edit = QLineEdit(reader.header.observer, self)
        self.telescope_edit = QLineEdit(reader.header.telescope, self)
        self.instrument_edit = QLineEdit(reader.header.instrument, self)
        self.exposure_spin = QDoubleSpinBox(self)
        self.exposure_spin.setRange(0.0, 100000.0)
        self.exposure_spin.setDecimals(5)
        self.exposure_spin.setSuffix(" s")
        self.exposure_spin.setSpecialValueText("not recorded")
        self.focal_spin = QDoubleSpinBox(self)
        self.focal_spin.setRange(0.0, 100000.0)
        self.focal_spin.setSuffix(" mm")
        self.focal_spin.setSpecialValueText("unknown")
        self.pixel_spin = QDoubleSpinBox(self)
        self.pixel_spin.setRange(0.0, 1000.0)
        self.pixel_spin.setDecimals(3)
        self.pixel_spin.setSuffix(" µm")
        self.pixel_spin.setSpecialValueText("unknown")
        meta_form.addRow("OBJECT:", self.object_edit)
        meta_form.addRow("OBSERVER:", self.observer_edit)
        meta_form.addRow("TELESCOP:", self.telescope_edit)
        meta_form.addRow("INSTRUME:", self.instrument_edit)
        meta_form.addRow("EXPTIME:", self.exposure_spin)
        meta_form.addRow("FOCALLEN:", self.focal_spin)
        meta_form.addRow("XPIXSZ / YPIXSZ:", self.pixel_spin)

        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.RichText)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        fit_to_screen(self, 580, 820)

        # Keep the summary and the buttons pinned; scroll the options above them
        # so the dialog always fits on the screen.
        layout = QVBoxLayout(self)
        layout.addWidget(
            scrollable(output_group, self.range_widget, data_group, meta_group,
                       parent=self),
            1,
        )
        layout.addWidget(self.summary_label)
        layout.addWidget(buttons)
        self._refresh()

    # -- helpers ------------------------------------------------------------
    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to FITS", self.path_edit.text(),
            "FITS files (*.fits *.fit *.fts)"
        )
        if path:
            self.path_edit.setText(path)

    def options(self) -> FitsExportOptions:
        return FitsExportOptions(
            layout=self.layout_combo.currentData(),
            colour_mode=self.colour_combo.currentData(),
            bit_depth=self.depth_combo.currentData(),
            apply_processing=self.processing_check.isChecked(),
            apply_crop=self.crop_check.isChecked(),
            flip_vertical=self.flip_check.isChecked(),
            object_name=self.object_edit.text().strip(),
            observer=self.observer_edit.text().strip(),
            telescope=self.telescope_edit.text().strip(),
            instrument=self.instrument_edit.text().strip(),
            exposure_seconds=self.exposure_spin.value() or None,
            focal_length_mm=self.focal_spin.value() or None,
            pixel_size_um=self.pixel_spin.value() or None,
        )

    def indices(self) -> list[int]:
        return self.range_widget.indices()

    def path(self) -> str:
        return self.path_edit.text().strip()

    # -- summary -------------------------------------------------------------
    def _refresh(self, *args) -> None:
        options = self.options()
        indices = self.indices()
        count = len(indices)

        is_raw = options.colour_mode == "raw"
        self.colour_combo.setEnabled(
            self.reader.colour_id.is_bayer or self.reader.colour_id.is_colour
        )

        crop = self.processor.options.crop
        if options.apply_crop and crop.valid:
            clamped = crop.clamped(self.reader.width, self.reader.height)
            width, height = clamped.width, clamped.height
        else:
            width, height = self.reader.width, self.reader.height

        planes = 1
        if options.colour_mode == "rgb" and (
            self.reader.colour_id.is_colour or self.reader.colour_id.is_bayer
        ):
            planes = 3

        bytes_per_sample = {"native": self.reader.bytes_per_sample,
                            "uint16": 2, "float32": 4}[options.bit_depth]
        if options.bit_depth == "native" and options.apply_processing:
            bytes_per_sample = self.reader.bytes_per_sample
        total_bytes = width * height * planes * bytes_per_sample * count
        total_bytes += 5760 * (1 if options.layout == "cube" else count)

        if options.layout == "cube":
            axes = [width, height]
            if planes == 3:
                axes.append(3)
            if count > 1:
                axes.append(count)
            shape = " x ".join(str(a) for a in axes)
            files = "1 file"
        else:
            shape = f"{width} x {height}" + (" x 3" if planes == 3 else "")
            files = f"{count} files"

        warning = ""
        if options.apply_processing:
            warning = ("<br><span style='color:#c86400'>The pixel values will not be "
                       "linear because the display processing is applied.</span>")
        elif is_raw and self.reader.colour_id.is_bayer:
            warning = ("<br><span style='color:#2e7d32'>Raw Bayer data with a BAYERPAT "
                       "keyword - the right choice for stacking software.</span>")

        self.summary_label.setText(
            f"<b>{files}</b>, NAXIS = {shape}, "
            f"about <b>{_human_size(total_bytes)}</b> in total.{warning}"
        )


def _human_size(size: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
