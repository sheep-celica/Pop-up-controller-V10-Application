from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QGroupBox, QLabel, QVBoxLayout, QWidget

from popup_controller.ui.sections import SectionDefinition


class SectionDialog(QDialog):
    def __init__(self, section: SectionDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.section = section
        self.setWindowTitle(section.title)
        self.resize(560, 460)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel(section.title, self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(section.summary, self)
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        note_label = QLabel(
            "This dialog is the shell for the future UI. The app will eventually load and present this "
            "section's data using background controller commands.",
            self,
        )
        note_label.setWordWrap(True)

        planned_fields_group = QGroupBox("Planned fields", self)
        planned_fields_layout = QVBoxLayout(planned_fields_group)
        planned_fields_layout.addWidget(self._create_bullets(section.planned_fields, planned_fields_group))

        source_commands_group = QGroupBox("Likely source commands", self)
        source_commands_layout = QVBoxLayout(source_commands_group)
        source_commands_layout.addWidget(self._create_bullets(section.source_commands, source_commands_group))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        root_layout.addWidget(title_label)
        root_layout.addWidget(summary_label)
        root_layout.addWidget(note_label)
        root_layout.addWidget(planned_fields_group)
        root_layout.addWidget(source_commands_group)
        root_layout.addStretch(1)
        root_layout.addWidget(buttons)

    def _create_bullets(self, items: tuple[str, ...], parent: QWidget) -> QLabel:
        bullet_lines = "".join(f"<li>{item}</li>" for item in items)
        label = QLabel(f"<ul>{bullet_lines}</ul>", parent)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label