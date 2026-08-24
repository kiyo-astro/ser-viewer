"""The About box."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from .. import __version__

APP_NAME = "SER Viewer"


def about_html(version: str = __version__) -> str:
    """The text shown in the About box."""
    return (
        f"<h3 style='margin-bottom:2px'>{APP_NAME} {version}</h3>"
        "<p>A player for SER astronomy video format.</p>"
        "<p>Inspired by SER Player by Chris Garry. "
        "Built with PySide6, NumPy, OpenCV and Astropy.<br>"
        "Application developed by Kiyoaki Okudaira - Kyushu University "
        "Hanada Lab (Space Systems Dynamics)<br>"
        "Supported by JSPS KAKENHI Grant Number JP26H02172.</p>"
    )


class AboutDialog(QDialog):
    """A fixed width About box.

    QMessageBox sizes itself to the longest line, which on a small display gets
    clipped at the screen edge; a plain dialog with a word wrapped label keeps
    the text readable at any size.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")

        icon_label = QLabel(self)
        pixmap = QApplication.windowIcon().pixmap(96, 96)
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        icon_label.setFixedWidth(96 if not pixmap.isNull() else 0)

        self.text_label = QLabel(about_html(), self)
        self.text_label.setTextFormat(Qt.RichText)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_label.setFixedWidth(400)
        self.text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.accepted.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(icon_label)
        row.addSpacing(14)
        row.addWidget(self.text_label, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addSpacing(8)
        layout.addWidget(buttons)
        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.sizeHint())
