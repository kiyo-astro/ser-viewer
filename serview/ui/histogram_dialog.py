"""Live histogram of the frame currently on screen."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..imaging.histogram import Histogram, compute_histogram
from .widgets import use_standard_window_frame

CHANNEL_COLOURS = {
    "Mono": QColor(220, 220, 220),
    "Red": QColor(235, 90, 90),
    "Green": QColor(90, 210, 110),
    "Blue": QColor(95, 145, 245),
}


class HistogramPlot(QWidget):
    """Draws the histogram curves, optionally on a logarithmic scale."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.histogram: Histogram | None = None
        self.logarithmic = True
        self.setMinimumSize(340, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_histogram(self, histogram: Histogram | None) -> None:
        self.histogram = histogram
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(24, 24, 26))

        grid = QPen(QColor(70, 70, 74), 0)
        painter.setPen(grid)
        for fraction in (0.25, 0.5, 0.75):
            x = rect.left() + rect.width() * fraction
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        histogram = self.histogram
        if histogram is None or histogram.counts.size == 0:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(rect, Qt.AlignCenter, "No frame loaded")
            return

        counts = histogram.counts.astype(np.float64)
        if self.logarithmic:
            counts = np.log10(counts + 1.0)
        peak = counts.max() or 1.0

        for index, name in enumerate(histogram.channels):
            colour = CHANNEL_COLOURS.get(name, QColor(200, 200, 200))
            path = QPainterPath()
            path.moveTo(rect.left(), rect.bottom())
            bins = counts.shape[1]
            for bin_index in range(bins):
                x = rect.left() + rect.width() * bin_index / (bins - 1)
                y = rect.bottom() - rect.height() * (counts[index, bin_index] / peak)
                path.lineTo(x, y)
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
            fill = QColor(colour)
            fill.setAlpha(70 if len(histogram.channels) > 1 else 110)
            painter.fillPath(path, fill)
            painter.setPen(QPen(colour, 1.2))
            painter.drawPath(path)

        painter.setPen(QColor(120, 120, 124))
        painter.drawRect(rect)


class HistogramDialog(QDialog):
    """Histogram plus per channel statistics; updates as frames change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Histogram")
        use_standard_window_frame(self)
        self.resize(460, 380)

        self.plot = HistogramPlot(self)
        self.stats_label = QLabel(self)
        self.stats_label.setTextFormat(Qt.RichText)
        self.stats_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.log_check = QCheckBox("Logarithmic", self)
        self.log_check.setChecked(True)
        self.log_check.toggled.connect(self._on_log_toggled)

        self.bins_combo = QComboBox(self)
        for count in (64, 128, 256, 512):
            self.bins_combo.addItem(f"{count} bins", count)
        self.bins_combo.setCurrentIndex(2)
        self.bins_combo.currentIndexChanged.connect(lambda _: self._recompute())

        controls = QHBoxLayout()
        controls.addWidget(self.log_check)
        controls.addWidget(self.bins_combo)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.plot, 1)
        layout.addLayout(controls)
        layout.addWidget(self.stats_label)

        self._image: np.ndarray | None = None

    def set_image(self, image: np.ndarray | None) -> None:
        self._image = image
        self._recompute()

    def _recompute(self) -> None:
        if self._image is None:
            self.plot.set_histogram(None)
            self.stats_label.clear()
            return
        histogram = compute_histogram(self._image, self.bins_combo.currentData())
        self.plot.set_histogram(histogram)
        self.stats_label.setText(self._format_stats(histogram))

    @staticmethod
    def _format_stats(histogram: Histogram) -> str:
        rows = [
            "<table cellspacing='6'><tr><th align='left'>Channel</th>"
            "<th>Min</th><th>Max</th><th>Mean</th><th>Median</th>"
            "<th>Black</th><th>Clipped</th></tr>"
        ]
        for index, name in enumerate(histogram.channels):
            colour = CHANNEL_COLOURS.get(name, QColor(200, 200, 200)).name()
            rows.append(
                f"<tr><td style='color:{colour}'>{name}</td>"
                f"<td align='right'>{histogram.minimum[index]:.3f}</td>"
                f"<td align='right'>{histogram.maximum[index]:.3f}</td>"
                f"<td align='right'>{histogram.mean[index]:.3f}</td>"
                f"<td align='right'>{histogram.median[index]:.3f}</td>"
                f"<td align='right'>{histogram.clipped_low[index] * 100:.2f}%</td>"
                f"<td align='right'>{histogram.clipped_high[index] * 100:.2f}%</td></tr>"
            )
        rows.append("</table>")
        return "".join(rows)

    def _on_log_toggled(self, enabled: bool) -> None:
        self.plot.logarithmic = enabled
        self.plot.update()
