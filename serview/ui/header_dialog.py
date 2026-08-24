"""Shows the SER header and the timestamp of the current frame."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..ser.reader import SerReader
from .widgets import use_standard_window_frame


class HeaderDialog(QDialog):
    def __init__(self, reader: SerReader, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SER file details")
        use_standard_window_frame(self)
        self.resize(520, 560)
        self._reader = reader

        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        copy = buttons.addButton("Copy", QDialogButtonBox.ActionRole)
        copy.clicked.connect(self.copy_to_clipboard)
        buttons.rejected.connect(self.hide)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self, frame_index: int | None = None) -> None:
        info = dict(self._reader.describe())
        if frame_index is not None:
            info["Current frame"] = f"{frame_index + 1} of {self._reader.frame_count}"
            stamp = self._reader.timestamp(frame_index)
            info["Current frame time (UTC)"] = (
                stamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if stamp else "-"
            )
        self.table.setRowCount(len(info))
        for row, (key, value) in enumerate(info.items()):
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(str(value)))

    def copy_to_clipboard(self) -> None:
        lines = []
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0).text()
            value = self.table.item(row, 1).text()
            lines.append(f"{key}\t{value}")
        QGuiApplication.clipboard().setText("\n".join(lines))
