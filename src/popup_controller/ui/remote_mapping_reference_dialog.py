from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


class RemoteMappingReferenceDialog(QDialog):
    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path

        self.setWindowTitle("Remote button reference")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        pixmap = QPixmap(str(self.image_path))
        if pixmap.isNull():
            self.image_label.setText(f"Unable to load image: {self.image_path}")
            self.resize(520, 240)
        else:
            scaled_pixmap = pixmap.scaled(
                max(1, pixmap.width() // 2),
                max(1, pixmap.height() // 2),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setFixedSize(scaled_pixmap.size())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        root_layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(buttons)

        if pixmap.isNull():
            return

        self.setFixedSize(self.sizeHint())
