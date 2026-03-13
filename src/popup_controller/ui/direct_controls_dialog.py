from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.serial_service import SerialConnectionError, SerialService


class DirectControlsDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False

        self.setWindowTitle("Direct Controls")
        self.resize(680, 420)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel("Direct Controls", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "Send live wink and toggle commands directly to the connected controller. "
            "These actions trigger immediately and do not modify stored settings.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Ready to send direct control commands.", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.actions_group = self._build_actions_group()
        buttons = self._build_buttons()

        root_layout.addWidget(title_label)
        root_layout.addWidget(summary_label)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.actions_group)
        root_layout.addStretch(1)
        root_layout.addWidget(buttons)

    def _build_actions_group(self) -> QGroupBox:
        group = QGroupBox("Actions", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        action_specs = (
            ("RH Wink", "Momentarily wink the right headlight.", "wink rh", "RH wink sent."),
            ("LH Wink", "Momentarily wink the left headlight.", "wink lh", "LH wink sent."),
            ("Both Wink", "Momentarily wink both headlights.", "wink both", "Both wink command sent."),
            (
                "Toggle Sleepy Eye Mode",
                "Toggle sleepy-eye mode without changing stored mapping or settings.",
                "toggleSleepyEyeMode",
                "Sleepy-eye toggle command sent.",
            ),
            ("Toggle Both", "Toggle both headlights together.", "toggle both", "Toggle-both command sent."),
        )

        self.action_buttons: list[QPushButton] = []
        for index, (title, description, command, success_message) in enumerate(action_specs):
            button = self._create_action_button(title, description, group)
            button.clicked.connect(
                lambda checked=False, current_command=command, current_message=success_message: self._send_control_command(
                    current_command,
                    current_message,
                )
            )
            self.action_buttons.append(button)
            layout.addWidget(button, index // 2, index % 2)

        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        self.close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        return buttons

    def _create_action_button(self, title: str, description: str, parent: QWidget) -> QPushButton:
        button = QPushButton(f"{title}\n{description}", parent)
        button.setProperty("sectionButton", True)
        button.setMinimumHeight(96)
        button.setToolTip(description)
        return button

    def _send_control_command(self, command: str, success_message: str) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(
                self,
                "Connect first",
                "Connect to the controller before sending direct control commands.",
            )
            return

        self._set_busy(True, f"Sending '{command}'...")
        try:
            response = self.serial_service.request_text(
                command,
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=self._process_events,
            )
            normalized = " ".join(line.strip() for line in response.splitlines() if line.strip())
            lowered = normalized.casefold()

            if any(marker in lowered for marker in ("unknown command", "placeholder", "rejected", "failed", "invalid", "error")):
                self.status_label.setText(normalized or "Direct control command failed.")
                QMessageBox.warning(self, "Direct Controls", normalized or "Direct control command failed.")
                return

            self.status_label.setText(normalized or success_message)
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Direct Controls", str(exc))
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.status_label.setText(message)

        self.actions_group.setEnabled(not busy)
        if self.close_button is not None:
            self.close_button.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
