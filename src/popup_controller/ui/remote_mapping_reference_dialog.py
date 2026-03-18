from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QWidget

from popup_controller.ui.window_helpers import apply_initial_window_size, create_scrollable_dialog_layout


class RemoteMappingReferenceDialog(QDialog):
    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path

        self.setWindowTitle("Remote button reference")

        root_layout, content_layout, self.scroll_area = create_scrollable_dialog_layout(self)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        preferred_width = 520
        preferred_height = 240

        pixmap = QPixmap(str(self.image_path))
        if pixmap.isNull():
            self.image_label.setText(f"Unable to load image: {self.image_path}")
            self.image_label.setWordWrap(True)
        else:
            scaled_pixmap = pixmap.scaled(
                max(1, pixmap.width() // 2),
                max(1, pixmap.height() // 2),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setMinimumSize(scaled_pixmap.size())
            preferred_width = scaled_pixmap.width() + 72
            preferred_height = scaled_pixmap.height() + 120

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        content_layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addStretch(1)
        root_layout.addWidget(buttons)

        apply_initial_window_size(
            self,
            preferred_width,
            preferred_height,
            width_ratio=0.7,
            height_ratio=0.8,
            max_width=1100,
            max_height=900,
        )
