"""Pieces shared by the export dialogs: frame selection and the worker thread."""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QRadioButton,
    QSpinBox,
)

from ..export.fits import ExportCancelled


class FrameRangeWidget(QGroupBox):
    """Choose which frames to export."""

    def __init__(self, frame_count: int, current: int, markers: tuple[int, int],
                 parent=None):
        super().__init__("Frames", parent)
        self.frame_count = frame_count
        self.current = current
        self.markers = markers

        self.all_radio = QRadioButton("All frames", self)
        self.markers_radio = QRadioButton("Between the markers", self)
        self.current_radio = QRadioButton("Current frame only", self)
        self.custom_radio = QRadioButton("Range:", self)
        self.all_radio.setChecked(True)

        group = QButtonGroup(self)
        for button in (self.all_radio, self.markers_radio, self.current_radio, self.custom_radio):
            group.addButton(button)
            button.toggled.connect(self._update_enabled)

        marked = markers != (0, max(0, frame_count - 1))
        self.markers_radio.setEnabled(marked)
        if marked:
            self.markers_radio.setChecked(True)
            self.markers_radio.setText(
                f"Between the markers ({markers[0] + 1} - {markers[1] + 1})"
            )

        self.from_spin = QSpinBox(self)
        self.from_spin.setRange(1, max(1, frame_count))
        self.from_spin.setValue(1)
        self.to_spin = QSpinBox(self)
        self.to_spin.setRange(1, max(1, frame_count))
        self.to_spin.setValue(frame_count)
        self.step_spin = QSpinBox(self)
        self.step_spin.setRange(1, max(1, frame_count))
        self.step_spin.setPrefix("every ")
        self.step_spin.setSuffix(" frame(s)")
        self.reverse_check = QCheckBox("Reverse order", self)

        for widget in (self.from_spin, self.to_spin, self.step_spin):
            widget.valueChanged.connect(lambda _: self.changed())
        for button in (self.all_radio, self.markers_radio, self.current_radio, self.custom_radio):
            button.toggled.connect(lambda _: self.changed())
        self.reverse_check.toggled.connect(lambda _: self.changed())

        self.count_label = QLabel(self)

        layout = QGridLayout(self)
        layout.addWidget(self.all_radio, 0, 0, 1, 4)
        layout.addWidget(self.markers_radio, 1, 0, 1, 4)
        layout.addWidget(self.current_radio, 2, 0, 1, 4)
        layout.addWidget(self.custom_radio, 3, 0)
        layout.addWidget(self.from_spin, 3, 1)
        layout.addWidget(QLabel("to", self), 3, 2)
        layout.addWidget(self.to_spin, 3, 3)
        layout.addWidget(self.step_spin, 4, 1, 1, 3)
        layout.addWidget(self.reverse_check, 5, 0, 1, 4)
        layout.addWidget(self.count_label, 6, 0, 1, 4)
        self._on_change: Callable[[], None] | None = None
        self._update_enabled()

    def set_change_handler(self, handler: Callable[[], None]) -> None:
        self._on_change = handler
        self._refresh_label()

    def changed(self) -> None:
        self._refresh_label()
        if self._on_change:
            self._on_change()

    def _update_enabled(self) -> None:
        custom = self.custom_radio.isChecked()
        for widget in (self.from_spin, self.to_spin, self.step_spin):
            widget.setEnabled(custom)
        self._refresh_label()

    def _refresh_label(self) -> None:
        count = len(self.indices())
        self.count_label.setText(
            f"{count} frame will be exported" if count == 1
            else f"{count} frames will be exported"
        )

    def indices(self) -> list[int]:
        if self.current_radio.isChecked():
            return [self.current]
        if self.markers_radio.isChecked():
            start, end, step = self.markers[0], self.markers[1], 1
        elif self.custom_radio.isChecked():
            start = self.from_spin.value() - 1
            end = self.to_spin.value() - 1
            step = self.step_spin.value()
        else:
            start, end, step = 0, self.frame_count - 1, 1
        if end < start:
            start, end = end, start
        indices = list(range(start, end + 1, step))
        return list(reversed(indices)) if self.reverse_check.isChecked() else indices


class ExportWorker(QThread):
    """Runs an exporter's ``export`` method off the GUI thread."""

    progress = Signal(int, int)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, exporter, path: str, indices: Sequence[int], parent=None):
        super().__init__(parent)
        self._exporter = exporter
        self._path = path
        self._indices = list(indices)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _progress(self, done: int, total: int) -> bool:
        self.progress.emit(done, total)
        return not self._cancelled

    def run(self) -> None:
        try:
            written = self._exporter.export(self._path, self._indices, self._progress)
        except ExportCancelled:
            self.failed.emit("")
        except Exception as error:  # surfaced in a message box
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.finished_ok.emit(written)
