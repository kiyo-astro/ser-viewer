"""Small reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class LabeledSlider(QWidget):
    """A slider and a spin box that stay in sync, plus a reset button."""

    value_changed = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float, value: float,
                 decimals: int = 2, step: float = 0.05, parent=None):
        super().__init__(parent)
        self._scale = 10 ** decimals
        self._default = value
        self._updating = False

        self.label = QLabel(label, self)
        self.label.setMinimumWidth(110)

        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(int(minimum * self._scale), int(maximum * self._scale))
        self.slider.setValue(int(value * self._scale))
        self.slider.valueChanged.connect(self._on_slider)

        self.spin = QDoubleSpinBox(self)
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setValue(value)
        self.spin.setFixedWidth(80)
        self.spin.valueChanged.connect(self._on_spin)

        self.reset_button = QToolButton(self)
        self.reset_button.setText("↺")
        self.reset_button.setToolTip("Reset to the default value")
        self.reset_button.setAutoRaise(True)
        self.reset_button.clicked.connect(self.reset)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        layout.addWidget(self.reset_button)

    def value(self) -> float:
        return self.spin.value()

    def setValue(self, value: float) -> None:
        self._updating = True
        self.spin.setValue(value)
        self.slider.setValue(int(value * self._scale))
        self._updating = False

    def reset(self) -> None:
        self.setValue(self._default)
        self.value_changed.emit(self._default)

    def _on_slider(self, raw: int) -> None:
        if self._updating:
            return
        self._updating = True
        value = raw / self._scale
        self.spin.setValue(value)
        self._updating = False
        self.value_changed.emit(value)

    def _on_spin(self, value: float) -> None:
        if self._updating:
            return
        self._updating = True
        self.slider.setValue(int(value * self._scale))
        self._updating = False
        self.value_changed.emit(value)


def scrollable(*widgets: QWidget, parent: QWidget | None = None) -> QScrollArea:
    """Stack ``widgets`` vertically inside a scroll area.

    Dialogs that hold a lot of options are taller than a laptop screen, and a
    plain QDialog simply gets clipped - the buttons at the bottom become
    unreachable. Putting the options in here keeps them scrollable while the
    dialog's buttons stay pinned outside.
    """
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)

    area = QScrollArea(parent)
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return area


def fit_to_screen(dialog: QWidget, width: int, height: int, margin: int = 100) -> None:
    """Resize ``dialog`` to the preferred size, but never past the screen."""
    screen = dialog.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        dialog.resize(width, height)
        return
    available = screen.availableGeometry()
    dialog.resize(
        max(360, min(width, available.width() - margin)),
        max(320, min(height, available.height() - margin)),
    )


def use_standard_window_frame(dialog: QWidget) -> None:
    """Give a modeless dialog an ordinary window frame.

    ``Qt.Tool`` turns a dialog into a macOS *utility panel*, whose close,
    minimise and zoom buttons are drawn noticeably smaller than a normal
    window's.  These dialogs stay open beside the main window for long stretches
    of work, so they should look and behave like ordinary windows.
    """
    dialog.setWindowFlags(
        Qt.Window
        | Qt.WindowTitleHint
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint
        | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
