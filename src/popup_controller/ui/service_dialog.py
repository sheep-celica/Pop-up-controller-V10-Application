from __future__ import annotations

from PySide6.QtCore import QDate, QEventLoop, QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.ui.voltage_calibration_dialog import VoltageCalibrationDialog
from popup_controller.ui.window_helpers import apply_initial_window_size, create_fixed_loading_slot, create_scrollable_dialog_layout


SERVICE_ACCESS_PASSWORD = "SE-aeemc2"


class ServiceDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False

        self.setWindowTitle("Service")

        root_layout, content_layout, self.scroll_area = create_scrollable_dialog_layout(self)

        title_label = QLabel("Service", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "This protected dialog groups maintenance actions that can reset controller data, write production metadata, and guide voltage calibration writes.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Authenticated service access granted.", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.loading_slot = create_fixed_loading_slot(self, self.loading_frame)
        self.statistics_group = self._build_statistics_group()
        self.voltage_calibration_group = self._build_voltage_calibration_group()
        self.manufacture_group = self._build_manufacture_group()
        buttons = self._build_buttons()

        content_layout.addWidget(title_label)
        content_layout.addWidget(summary_label)
        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.statistics_group)
        content_layout.addWidget(self.voltage_calibration_group)
        content_layout.addWidget(self.manufacture_group)
        content_layout.addStretch(1)
        root_layout.addWidget(self.loading_slot)
        root_layout.addWidget(buttons)

        apply_initial_window_size(self, 860, 680)

        self._set_busy(False)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        frame.setVisible(False)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Working...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_statistics_group(self) -> QGroupBox:
        group = QGroupBox("Statistical data", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        note = QLabel(
            "Clears the controller's stored statistical data. This command uses a controller password that is separate from the service-access password used to open this dialog.",
            group,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.clear_statistics_password_input = QLineEdit(group)
        self.clear_statistics_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.clear_statistics_password_input.setPlaceholderText("Enter the controller password for clearStatisticalData")

        self.clear_statistics_button = QPushButton("Clear statistical data", group)
        self.clear_statistics_button.clicked.connect(self.clear_statistics)

        layout.addWidget(note, 0, 0, 1, 3)
        layout.addWidget(QLabel("Controller password", group), 1, 0)
        layout.addWidget(self.clear_statistics_password_input, 1, 1)
        layout.addWidget(self.clear_statistics_button, 1, 2)
        return group

    def _build_voltage_calibration_group(self) -> QGroupBox:
        group = QGroupBox("Voltage calibration", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        note = QLabel(
            "Open the guided voltage calibration workflow to capture measurement points, calculate a and b, and save those constants to the controller.",
            group,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.open_voltage_calibration_button = QPushButton("Open voltage calibration", group)
        self.open_voltage_calibration_button.clicked.connect(self.open_voltage_calibration_dialog)

        layout.addWidget(note, 0, 0, 1, 2)
        layout.addWidget(self.open_voltage_calibration_button, 1, 1)
        return group

    def _build_manufacture_group(self) -> QGroupBox:
        group = QGroupBox("Write manufacture data", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        note = QLabel(
            "Provide all required arguments for writeManufactureData. Manufacture date is sent as YYYY-MM-DD and uses the date picker below. Car model may contain spaces; the other fields must be single tokens.",
            group,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.serial_number_input = self._create_single_token_input(group)
        self.board_serial_input = self._create_single_token_input(group)
        self.board_revision_input = self._create_single_token_input(group)
        self.manufacture_date_input = QLineEdit(group)
        self.manufacture_date_input.setReadOnly(True)
        self.manufacture_date_input.setText(QDate.currentDate().toString("yyyy-MM-dd"))
        self.pick_manufacture_date_button = QPushButton("Pick date", group)
        self.pick_manufacture_date_button.clicked.connect(self.pick_manufacture_date)
        self.car_model_input = QLineEdit(group)
        self.write_manufacture_button = QPushButton("Write manufacture data", group)
        self.write_manufacture_button.clicked.connect(self.write_manufacture_data)

        layout.addWidget(note, 0, 0, 1, 4)
        layout.addWidget(QLabel("Serial number", group), 1, 0)
        layout.addWidget(self.serial_number_input, 1, 1)
        layout.addWidget(QLabel("Board serial", group), 1, 2)
        layout.addWidget(self.board_serial_input, 1, 3)
        manufacture_date_row = QWidget(group)
        manufacture_date_row_layout = QHBoxLayout(manufacture_date_row)
        manufacture_date_row_layout.setContentsMargins(0, 0, 0, 0)
        manufacture_date_row_layout.setSpacing(8)
        manufacture_date_row_layout.addWidget(self.manufacture_date_input, stretch=1)
        manufacture_date_row_layout.addWidget(self.pick_manufacture_date_button)

        layout.addWidget(QLabel("Board revision", group), 2, 0)
        layout.addWidget(self.board_revision_input, 2, 1)
        layout.addWidget(QLabel("Manufacture date", group), 2, 2)
        layout.addWidget(manufacture_date_row, 2, 3)
        layout.addWidget(QLabel("Car model", group), 3, 0)
        layout.addWidget(self.car_model_input, 3, 1, 1, 3)
        layout.addWidget(self.write_manufacture_button, 4, 3)
        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        return buttons

    def _create_single_token_input(self, parent: QWidget) -> QLineEdit:
        field = QLineEdit(parent)
        field.setValidator(QRegularExpressionValidator(QRegularExpression(r"\S*"), field))
        return field

    def clear_statistics(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before clearing statistical data.")
            return

        password = self.clear_statistics_password_input.text().strip()
        if not password:
            password, accepted = QInputDialog.getText(
                self,
                "Clear statistical data",
                "Enter the controller password to clear statistical data:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return
            password = password.strip()
            if password:
                self.clear_statistics_password_input.setText(password)

        if not password:
            QMessageBox.information(
                self,
                "Password required",
                "Enter the controller password used by clearStatisticalData before sending the command.",
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Clear statistical data",
            "Clear the controller statistical data now? This action cannot be undone.",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._submit_service_command(
            f"clearStatisticalData {password}",
            "Submitting statistical reset...",
            "Clear statistical data failed",
            "Controller statistical data clear command accepted.",
        )

    def open_voltage_calibration_dialog(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before opening voltage calibration.")
            return

        dialog = VoltageCalibrationDialog(self.serial_service, self)
        dialog.exec()

    def pick_manufacture_date(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Select manufacture date")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        calendar = QCalendarWidget(dialog)
        selected_date = QDate.fromString(self.manufacture_date_input.text().strip(), "yyyy-MM-dd")
        if not selected_date.isValid():
            selected_date = QDate.currentDate()
        calendar.setSelectedDate(selected_date)
        calendar.setGridVisible(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout.addWidget(calendar)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.manufacture_date_input.setText(calendar.selectedDate().toString("yyyy-MM-dd"))

    def write_manufacture_data(self) -> None:
        values = {
            "serial number": self.serial_number_input.text().strip(),
            "board serial": self.board_serial_input.text().strip(),
            "board revision": self.board_revision_input.text().strip(),
            "manufacture date": self.manufacture_date_input.text().strip(),
            "car model": self.car_model_input.text().strip(),
        }
        missing = [label for label, value in values.items() if not value]
        if missing:
            QMessageBox.information(
                self,
                "Manufacture data",
                f"Enter all manufacture fields before writing. Missing: {', '.join(missing)}.",
            )
            return

        for label in ("serial number", "board serial", "board revision", "manufacture date"):
            if any(character.isspace() for character in values[label]):
                QMessageBox.warning(
                    self,
                    "Manufacture data",
                    f"{label.title()} must be a single token without spaces.",
                )
                return

        command = (
            f"writeManufactureData {values['manufacture date']} {values['serial number']} "
            f"{values['board serial']} {values['board revision']} {values['car model']}"
        )
        self._submit_service_command(
            command,
            "Writing manufacture data...",
            "Write manufacture data failed",
            "Controller manufacture data write command accepted.",
        )

    def _submit_service_command(
        self,
        command: str,
        busy_message: str,
        error_title: str,
        success_message: str,
    ) -> bool:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before sending service commands.")
            return False

        self._set_busy(True, busy_message)
        try:
            response = self.serial_service.request_text(
                command,
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.5,
                progress_callback=self._process_events,
            )
            normalized = " ".join(line.strip() for line in response.splitlines() if line.strip())
            if not normalized:
                normalized = success_message
            lowered = normalized.casefold()
            if any(marker in lowered for marker in ("unknown command", "placeholder", "rejected", "incorrect password", "failed", "invalid", "error", "duplicate")):
                self.status_label.setText(normalized)
                QMessageBox.warning(self, error_title, normalized)
                return False

            self.status_label.setText(normalized)
            QMessageBox.information(self, "Service", normalized)
            return True
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, error_title, str(exc))
            return False
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.statistics_group.setEnabled(not busy)
        self.voltage_calibration_group.setEnabled(not busy)
        self.manufacture_group.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

