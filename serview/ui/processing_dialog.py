"""Non-modal dialog holding every processing option, applied live."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..imaging.pipeline import MONO_MODES, CropRect, ProcessingOptions
from ..ser.format import ColourID
from .widgets import (
    LabeledSlider,
    fit_to_screen,
    scrollable,
    use_standard_window_frame,
)

BAYER_PATTERNS = ("RGGB", "GRBG", "GBRG", "BGGR", "CYYM", "YCMY", "YMCY", "MYYC")


class ProcessingDialog(QDialog):
    """Edits a :class:`ProcessingOptions` and reports every change."""

    options_changed = Signal(object)
    selection_requested = Signal()

    def __init__(self, options: ProcessingOptions, colour_id: ColourID, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing")
        use_standard_window_frame(self)
        self.options = options
        self.colour_id = colour_id
        self._loading = False

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        reset = buttons.addButton("Reset all", QDialogButtonBox.ResetRole)
        reset.clicked.connect(self.reset_all)
        buttons.rejected.connect(self.hide)

        # The options are taller than a laptop screen, so they scroll while the
        # buttons stay visible at the bottom.
        layout = QVBoxLayout(self)
        layout.addWidget(
            scrollable(
                self._build_debayer_group(),
                self._build_levels_group(),
                self._build_colour_group(),
                self._build_mono_group(),
                self._build_frame_group(),
                parent=self,
            ),
            1,
        )
        layout.addWidget(buttons)
        fit_to_screen(self, 480, 900)
        self.load(options)

    # -- construction ------------------------------------------------------
    def _build_debayer_group(self) -> QWidget:
        group = QGroupBox("Debayer", self)
        form = QFormLayout(group)
        self.debayer_check = QCheckBox("Debayer colour filter array data", group)
        self.debayer_check.toggled.connect(self._emit)
        self.bayer_combo = QComboBox(group)
        self.bayer_combo.addItem("Auto (from the SER header)", None)
        for pattern in BAYER_PATTERNS:
            self.bayer_combo.addItem(pattern, pattern)
        self.bayer_combo.currentIndexChanged.connect(self._emit)
        form.addRow(self.debayer_check)
        form.addRow("Pattern:", self.bayer_combo)
        group.setEnabled(self.colour_id.is_bayer)
        if not self.colour_id.is_bayer:
            group.setToolTip("The file does not contain Bayer data")
        return group

    def _build_levels_group(self) -> QWidget:
        group = QGroupBox("Gain and gamma", self)
        layout = QVBoxLayout(group)
        self.gain_slider = LabeledSlider("Gain", 0.1, 8.0, 1.0, 2, 0.05, group)
        self.gamma_slider = LabeledSlider("Gamma", 0.1, 4.0, 1.0, 2, 0.05, group)
        self.black_slider = LabeledSlider("Black level", 0.0, 0.9, 0.0, 3, 0.005, group)
        for slider in (self.gain_slider, self.gamma_slider, self.black_slider):
            slider.value_changed.connect(self._emit)
            layout.addWidget(slider)
        self.auto_stretch_check = QCheckBox("Auto stretch each frame (display aid)", group)
        self.auto_stretch_check.setToolTip(
            "Stretches every frame between its own minimum and maximum.\n"
            "Handy for faint data, but it makes the brightness flicker."
        )
        self.auto_stretch_check.toggled.connect(self._on_auto_stretch)
        layout.addWidget(self.auto_stretch_check)
        return group

    def _build_colour_group(self) -> QWidget:
        group = QGroupBox("Colour", self)
        layout = QVBoxLayout(group)
        self.saturation_slider = LabeledSlider("Saturation", 0.0, 3.0, 1.0, 2, 0.05, group)
        self.red_slider = LabeledSlider("Red balance", 0.0, 3.0, 1.0, 2, 0.05, group)
        self.green_slider = LabeledSlider("Green balance", 0.0, 3.0, 1.0, 2, 0.05, group)
        self.blue_slider = LabeledSlider("Blue balance", 0.0, 3.0, 1.0, 2, 0.05, group)
        for slider in (self.saturation_slider, self.red_slider,
                       self.green_slider, self.blue_slider):
            slider.value_changed.connect(self._emit)
            layout.addWidget(slider)

        align = QGridLayout()
        align.addWidget(QLabel("Channel align (atmospheric dispersion):"), 0, 0, 1, 5)
        self.align_spins: dict[str, QSpinBox] = {}
        for row, channel in enumerate(("Red", "Blue"), start=1):
            align.addWidget(QLabel(f"{channel}:"), row, 0)
            for column, axis in enumerate(("X", "Y")):
                spin = QSpinBox(group)
                spin.setRange(-20, 20)
                spin.setPrefix(f"{axis} ")
                spin.setSuffix(" px")
                spin.valueChanged.connect(self._emit)
                align.addWidget(spin, row, 1 + column)
                self.align_spins[f"{channel.lower()}_{axis.lower()}"] = spin
        layout.addLayout(align)
        return group

    def _build_mono_group(self) -> QWidget:
        group = QGroupBox("Monochrome conversion", self)
        form = QFormLayout(group)
        self.mono_check = QCheckBox("Convert colour frames to monochrome", group)
        self.mono_check.toggled.connect(self._emit)
        self.mono_combo = QComboBox(group)
        for key, label in MONO_MODES.items():
            self.mono_combo.addItem(label, key)
        self.mono_combo.currentIndexChanged.connect(self._emit)
        form.addRow(self.mono_check)
        form.addRow("Using:", self.mono_combo)
        return group

    def _build_frame_group(self) -> QWidget:
        group = QGroupBox("Frame", self)
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        self.invert_check = QCheckBox("Invert", group)
        self.flip_h_check = QCheckBox("Flip horizontally", group)
        self.flip_v_check = QCheckBox("Flip vertically", group)
        for check in (self.invert_check, self.flip_h_check, self.flip_v_check):
            check.toggled.connect(self._emit)
            row.addWidget(check)
        self.rotation_combo = QComboBox(group)
        for degrees in (0, 90, 180, 270):
            self.rotation_combo.addItem(f"{degrees}°", degrees)
        self.rotation_combo.currentIndexChanged.connect(self._emit)
        row.addWidget(QLabel("Rotate:"))
        row.addWidget(self.rotation_combo)
        row.addStretch(1)
        layout.addLayout(row)

        crop = QGridLayout()
        crop.addWidget(QLabel("Crop:"), 0, 0)
        self.crop_spins: dict[str, QSpinBox] = {}
        for column, (key, label) in enumerate(
            (("x", "X"), ("y", "Y"), ("width", "W"), ("height", "H"))
        ):
            spin = QSpinBox(group)
            spin.setRange(0, 100000)
            spin.setPrefix(f"{label} ")
            spin.valueChanged.connect(self._emit)
            crop.addWidget(spin, 0, 1 + column)
            self.crop_spins[key] = spin
        select_button = QPushButton("Use selection box", group)
        select_button.clicked.connect(self.selection_requested.emit)
        clear_button = QPushButton("No crop", group)
        clear_button.clicked.connect(self.clear_crop)
        crop.addWidget(select_button, 1, 1, 1, 2)
        crop.addWidget(clear_button, 1, 3, 1, 2)
        layout.addLayout(crop)
        return group

    # -- values -------------------------------------------------------------
    def load(self, options: ProcessingOptions) -> None:
        """Copy ``options`` into the widgets without emitting change signals."""
        self._loading = True
        self.options = options
        self.debayer_check.setChecked(options.debayer)
        index = self.bayer_combo.findData(options.bayer_override)
        self.bayer_combo.setCurrentIndex(max(0, index))
        self.gain_slider.setValue(options.gain)
        self.gamma_slider.setValue(options.gamma)
        self.black_slider.setValue(options.black_level)
        self.auto_stretch_check.setChecked(options.auto_stretch)
        self.saturation_slider.setValue(options.saturation)
        self.red_slider.setValue(options.red_balance)
        self.green_slider.setValue(options.green_balance)
        self.blue_slider.setValue(options.blue_balance)
        self.align_spins["red_x"].setValue(options.red_align[0])
        self.align_spins["red_y"].setValue(options.red_align[1])
        self.align_spins["blue_x"].setValue(options.blue_align[0])
        self.align_spins["blue_y"].setValue(options.blue_align[1])
        self.mono_check.setChecked(options.to_mono)
        self.mono_combo.setCurrentIndex(max(0, self.mono_combo.findData(options.mono_mode)))
        self.invert_check.setChecked(options.invert)
        self.flip_h_check.setChecked(options.flip_horizontal)
        self.flip_v_check.setChecked(options.flip_vertical)
        self.rotation_combo.setCurrentIndex(max(0, self.rotation_combo.findData(options.rotation)))
        for key in ("x", "y", "width", "height"):
            self.crop_spins[key].setValue(getattr(options.crop, key))
        self._loading = False
        self._update_enabled()

    def collect(self) -> ProcessingOptions:
        options = ProcessingOptions(
            debayer=self.debayer_check.isChecked(),
            bayer_override=self.bayer_combo.currentData(),
            gain=self.gain_slider.value(),
            gamma=self.gamma_slider.value(),
            black_level=self.black_slider.value(),
            auto_stretch=self.auto_stretch_check.isChecked(),
            saturation=self.saturation_slider.value(),
            red_balance=self.red_slider.value(),
            green_balance=self.green_slider.value(),
            blue_balance=self.blue_slider.value(),
            red_align=(self.align_spins["red_x"].value(), self.align_spins["red_y"].value()),
            blue_align=(self.align_spins["blue_x"].value(), self.align_spins["blue_y"].value()),
            to_mono=self.mono_check.isChecked(),
            mono_mode=self.mono_combo.currentData() or "luminance",
            invert=self.invert_check.isChecked(),
            crop=CropRect(**{key: spin.value() for key, spin in self.crop_spins.items()}),
            flip_horizontal=self.flip_h_check.isChecked(),
            flip_vertical=self.flip_v_check.isChecked(),
            rotation=self.rotation_combo.currentData() or 0,
        )
        return options

    def set_crop(self, x: int, y: int, width: int, height: int) -> None:
        self._loading = True
        for key, value in (("x", x), ("y", y), ("width", width), ("height", height)):
            self.crop_spins[key].setValue(value)
        self._loading = False
        self._emit()

    def clear_crop(self) -> None:
        self.set_crop(0, 0, 0, 0)

    def reset_all(self) -> None:
        self.load(ProcessingOptions())
        self._emit()

    # -- slots ---------------------------------------------------------------
    def _on_auto_stretch(self, enabled: bool) -> None:
        self._update_enabled()
        self._emit()

    def _update_enabled(self) -> None:
        self.black_slider.setEnabled(not self.auto_stretch_check.isChecked())
        self.bayer_combo.setEnabled(self.debayer_check.isChecked())
        self.mono_combo.setEnabled(self.mono_check.isChecked())

    def _emit(self, *args) -> None:
        if self._loading:
            return
        self._update_enabled()
        self.options = self.collect()
        self.options_changed.emit(self.options)
