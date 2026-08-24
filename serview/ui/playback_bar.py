"""Transport controls and the frame slider with its in/out markers."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QWidget,
)


class MarkerSlider(QSlider):
    """A horizontal slider that shades the region between the two markers."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._start = 0
        self._end = 0
        self.setMinimum(0)
        self.setMaximum(0)

    def set_markers(self, start: int, end: int) -> None:
        self._start, self._end = start, end
        self.update()

    @property
    def markers(self) -> tuple[int, int]:
        return self._start, self._end

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.maximum() <= self.minimum():
            return
        if (self._start, self._end) == (self.minimum(), self.maximum()):
            return
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self
        )
        span = self.maximum() - self.minimum()
        left = groove.left() + groove.width() * (self._start - self.minimum()) / span
        right = groove.left() + groove.width() * (self._end - self.minimum()) / span
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 170, 0, 90))
        painter.drawRect(QRect(int(left), groove.top(), max(2, int(right - left)), groove.height()))
        painter.end()


class PlaybackBar(QWidget):
    """Play/pause, stepping, frame slider, frame rate and marker controls."""

    play_toggled = Signal(bool)
    frame_requested = Signal(int)
    step_requested = Signal(int)          # +1 / -1 / +10 / -10
    fps_changed = Signal(float)
    markers_changed = Signal(int, int)
    repeat_changed = Signal(bool)
    direction_changed = Signal(bool)      # True when playing in reverse

    def __init__(self, parent=None):
        super().__init__(parent)
        style = self.style()
        self._updating = False
        self._frame_count = 0

        def button(icon, tooltip, slot, checkable=False) -> QToolButton:
            widget = QToolButton(self)
            widget.setIcon(style.standardIcon(icon))
            widget.setToolTip(tooltip)
            widget.setCheckable(checkable)
            widget.setAutoRaise(True)
            # Without this the buttons swallow Space and the arrow keys, which
            # the window uses for play/pause and stepping.
            widget.setFocusPolicy(Qt.NoFocus)
            widget.clicked.connect(slot)
            return widget

        self.first_button = button(QStyle.SP_MediaSkipBackward, "First frame (Home)",
                                   lambda: self.frame_requested.emit(0))
        self.prev_button = button(QStyle.SP_MediaSeekBackward, "Previous frame (Left)",
                                  lambda: self.step_requested.emit(-1))
        self.play_button = button(QStyle.SP_MediaPlay, "Play / pause (Space)",
                                  self._on_play_clicked, checkable=True)
        self.next_button = button(QStyle.SP_MediaSeekForward, "Next frame (Right)",
                                  lambda: self.step_requested.emit(1))
        self.last_button = button(QStyle.SP_MediaSkipForward, "Last frame (End)",
                                  lambda: self.frame_requested.emit(self._frame_count - 1))

        self.slider = MarkerSlider(self)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.valueChanged.connect(self._on_slider_moved)

        self.frame_spin = QSpinBox(self)
        self.frame_spin.setMinimum(1)
        self.frame_spin.setMaximum(1)
        self.frame_spin.setToolTip("Current frame")
        self.frame_spin.valueChanged.connect(self._on_spin_changed)
        self.total_label = QLabel("/ 0", self)

        self.fps_spin = QDoubleSpinBox(self)
        self.fps_spin.setRange(0.1, 240.0)
        self.fps_spin.setValue(25.0)
        self.fps_spin.setDecimals(1)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setToolTip("Playback frame rate")
        self.fps_spin.valueChanged.connect(self.fps_changed.emit)

        self.repeat_check = QCheckBox("Repeat", self)
        self.repeat_check.setChecked(True)
        self.repeat_check.toggled.connect(self.repeat_changed.emit)

        self.reverse_check = QCheckBox("Reverse", self)
        self.reverse_check.toggled.connect(self.direction_changed.emit)

        self.mark_start_button = QToolButton(self)
        self.mark_start_button.setText("[")
        self.mark_start_button.setToolTip("Set the start marker to the current frame ( [ )")
        self.mark_start_button.setAutoRaise(True)
        self.mark_start_button.clicked.connect(self.mark_start)

        self.mark_end_button = QToolButton(self)
        self.mark_end_button.setText("]")
        self.mark_end_button.setToolTip("Set the end marker to the current frame ( ] )")
        self.mark_end_button.setAutoRaise(True)
        self.mark_end_button.clicked.connect(self.mark_end)

        self.clear_markers_button = QToolButton(self)
        self.clear_markers_button.setText("[ ]")
        self.clear_markers_button.setToolTip("Clear the markers")
        self.clear_markers_button.setAutoRaise(True)
        self.clear_markers_button.clicked.connect(self.clear_markers)

        self.time_label = QLabel("--:--.---", self)
        self.time_label.setMinimumWidth(90)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setToolTip("Timestamp of the current frame (UTC)")

        for widget in (self.mark_start_button, self.mark_end_button,
                       self.clear_markers_button, self.repeat_check, self.reverse_check):
            widget.setFocusPolicy(Qt.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 4)
        for widget in (self.first_button, self.prev_button, self.play_button,
                       self.next_button, self.last_button):
            layout.addWidget(widget)
        layout.addSpacing(6)
        layout.addWidget(self.slider, 1)
        layout.addSpacing(6)
        layout.addWidget(self.frame_spin)
        layout.addWidget(self.total_label)
        layout.addWidget(self.time_label)
        layout.addSpacing(6)
        layout.addWidget(self.mark_start_button)
        layout.addWidget(self.mark_end_button)
        layout.addWidget(self.clear_markers_button)
        layout.addSpacing(6)
        layout.addWidget(self.fps_spin)
        layout.addWidget(self.repeat_check)
        layout.addWidget(self.reverse_check)
        self.set_frame_count(0)

    # -- state -----------------------------------------------------------
    def set_frame_count(self, count: int) -> None:
        self._frame_count = count
        enabled = count > 0
        for widget in (self.first_button, self.prev_button, self.play_button,
                       self.next_button, self.last_button, self.slider,
                       self.frame_spin, self.mark_start_button, self.mark_end_button,
                       self.clear_markers_button):
            widget.setEnabled(enabled)
        self._updating = True
        self.slider.setMaximum(max(0, count - 1))
        self.frame_spin.setMaximum(max(1, count))
        self.total_label.setText(f"/ {count}")
        self._updating = False
        self.clear_markers()

    def set_frame(self, index: int) -> None:
        self._updating = True
        self.slider.setValue(index)
        self.frame_spin.setValue(index + 1)
        self._updating = False

    def set_time_text(self, text: str) -> None:
        self.time_label.setText(text)

    def set_playing(self, playing: bool) -> None:
        self.play_button.setChecked(playing)
        icon = QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))

    @property
    def fps(self) -> float:
        return self.fps_spin.value()

    def set_fps(self, value: float) -> None:
        self.fps_spin.setValue(max(0.1, min(240.0, value)))

    @property
    def repeat(self) -> bool:
        return self.repeat_check.isChecked()

    @property
    def reverse(self) -> bool:
        return self.reverse_check.isChecked()

    # -- markers ----------------------------------------------------------
    @property
    def markers(self) -> tuple[int, int]:
        return self.slider.markers

    def mark_start(self) -> None:
        start = self.slider.value()
        end = max(start, self.slider.markers[1])
        self.slider.set_markers(start, end)
        self.markers_changed.emit(start, end)

    def mark_end(self) -> None:
        end = self.slider.value()
        start = min(end, self.slider.markers[0])
        self.slider.set_markers(start, end)
        self.markers_changed.emit(start, end)

    def clear_markers(self) -> None:
        start, end = 0, max(0, self._frame_count - 1)
        self.slider.set_markers(start, end)
        self.markers_changed.emit(start, end)

    # -- slots -------------------------------------------------------------
    def _on_play_clicked(self) -> None:
        self.play_toggled.emit(self.play_button.isChecked())

    def _on_slider_moved(self, value: int) -> None:
        if not self._updating:
            self.frame_requested.emit(value)

    def _on_spin_changed(self, value: int) -> None:
        if not self._updating:
            self.frame_requested.emit(value - 1)
