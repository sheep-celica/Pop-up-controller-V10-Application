from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.services.settings_service import parse_battery_voltage_response
from popup_controller.ui.window_helpers import apply_initial_window_size, create_scrollable_dialog_layout
from popup_controller.services.voltage_calibration_service import (
    VoltageCalibrationError,
    VoltageCalibrationResult,
    VoltageMeasurementPoint,
    fit_voltage_calibration,
)


_ERROR_MARKERS = ("unknown command", "placeholder", "rejected", "failed", "invalid", "error", "duplicate")


class AddVoltageMeasurementDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self.measurement_point: VoltageMeasurementPoint | None = None
        self._busy = False

        self.setWindowTitle("Add voltage calibration point")

        root_layout, content_layout, self.scroll_area = create_scrollable_dialog_layout(self)

        title_label = QLabel("Add voltage calibration point", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "Enter the real measured battery voltage. When you click Add point, the app will read the controller voltage using readBatteryVoltage and store both values together.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Ready to capture a new measurement point.", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        editor = self._build_editor_card()
        buttons = self._build_buttons()

        content_layout.addWidget(title_label)
        content_layout.addWidget(summary_label)
        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.loading_frame)
        content_layout.addWidget(editor)
        content_layout.addStretch(1)
        root_layout.addWidget(buttons)

        self._set_busy(False)
        apply_initial_window_size(self, 520, 260)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        frame.setVisible(False)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Reading controller voltage...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_editor_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("editorCard")
        layout = QGridLayout(card)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        note = QLabel(
            "Use the same multimeter and setup you want to calibrate against. The controller reading is captured only after you press Add point.",
            card,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.measured_voltage_input = QLineEdit(card)
        self.measured_voltage_input.setPlaceholderText("Example: 13.82")
        self.measured_voltage_input.setValidator(QDoubleValidator(0.0, 100.0, 6, self))

        layout.addWidget(note, 0, 0, 1, 2)
        layout.addWidget(QLabel("Measured voltage (V)", card), 1, 0)
        layout.addWidget(self.measured_voltage_input, 1, 1)
        return card

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(self)
        self.add_point_button = QPushButton("Add point", self)
        self.cancel_button = QPushButton("Cancel", self)
        buttons.addButton(self.add_point_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        self.add_point_button.clicked.connect(self.add_measurement_point)
        self.cancel_button.clicked.connect(self.reject)
        return buttons

    def add_measurement_point(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before capturing a measurement point.")
            return

        measured_text = self.measured_voltage_input.text().strip()
        if not measured_text:
            QMessageBox.information(self, "Measured voltage", "Enter the real measured voltage before adding a point.")
            return

        try:
            measured_voltage_v = float(measured_text)
        except ValueError:
            QMessageBox.warning(self, "Measured voltage", "Measured voltage must be a valid number.")
            return

        self._set_busy(True, "Reading controller voltage...")
        try:
            response = self.serial_service.request_text(
                "readBatteryVoltage",
                idle_timeout_seconds=0.7,
                max_duration_seconds=4.0,
                progress_callback=self._process_events,
            )
            normalized = _normalize_response(response)
            if _response_has_error(normalized):
                self.status_label.setText(normalized or "Battery voltage read failed.")
                QMessageBox.warning(self, "Battery voltage", normalized or "Battery voltage read failed.")
                return

            controller_voltage_v = parse_battery_voltage_response(response)
            if controller_voltage_v is None:
                message = "The controller returned an unexpected battery voltage format."
                self.status_label.setText(message)
                QMessageBox.warning(self, "Battery voltage", message)
                return

            self.measurement_point = VoltageMeasurementPoint(
                measured_voltage_v=measured_voltage_v,
                controller_voltage_v=controller_voltage_v,
            )
            self.status_label.setText(
                f"Captured measured {measured_voltage_v:.3f} V and controller {controller_voltage_v:.3f} V."
            )
            self.accept()
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Battery voltage", str(exc))
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.measured_voltage_input.setEnabled(not busy)
        self.add_point_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


class VoltageCalibrationDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False
        self._measurement_points: list[VoltageMeasurementPoint] = []
        self._calibration_result: VoltageCalibrationResult | None = None

        self.setWindowTitle("Voltage calibration")

        root_layout, content_layout, self.scroll_area = create_scrollable_dialog_layout(self)

        title_label = QLabel("Voltage calibration", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "Build a calibration from measured points, fit a linear model, then save the resulting constants to the controller. The fit uses: measured voltage ~= a * controller voltage + b.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Add measurement points to begin voltage calibration.", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.measurements_group = self._build_measurements_group()
        self.results_group = self._build_results_group()
        buttons = self._build_buttons()

        content_layout.addWidget(title_label)
        content_layout.addWidget(summary_label)
        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.loading_frame)
        content_layout.addWidget(self.measurements_group)
        content_layout.addWidget(self.results_group)
        content_layout.addStretch(1)
        root_layout.addWidget(buttons)

        self._set_busy(False)
        apply_initial_window_size(self, 860, 620)
        self._update_table()
        self._set_calibration_result(None)

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

    def _build_measurements_group(self) -> QGroupBox:
        group = QGroupBox("Measurement points", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        note = QLabel(
            "Each point stores one real measured voltage and one controller reading captured at the same moment.",
            group,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.measurements_table = QTableWidget(0, 3, group)
        self.measurements_table.setHorizontalHeaderLabels(
            ["Measured voltage (V)", "Controller voltage (V)", "Difference (V)"]
        )
        self.measurements_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.measurements_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.measurements_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.measurements_table.verticalHeader().setVisible(False)
        header = self.measurements_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        self.add_point_button = QPushButton("Add measurement point", group)
        self.remove_point_button = QPushButton("Remove selected", group)
        self.clear_points_button = QPushButton("Clear points", group)
        self.calculate_button = QPushButton("Create calibration constants", group)

        self.add_point_button.clicked.connect(self.add_measurement_point)
        self.remove_point_button.clicked.connect(self.remove_selected_point)
        self.clear_points_button.clicked.connect(self.clear_points)
        self.calculate_button.clicked.connect(self.calculate_constants)

        button_row.addWidget(self.add_point_button)
        button_row.addWidget(self.remove_point_button)
        button_row.addWidget(self.clear_points_button)
        button_row.addStretch(1)
        button_row.addWidget(self.calculate_button)

        layout.addWidget(note)
        layout.addWidget(self.measurements_table, stretch=1)
        layout.addLayout(button_row)
        return group

    def _build_results_group(self) -> QGroupBox:
        group = QGroupBox("Calculated constants", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        note = QLabel(
            "After calculating, save writes the current a and b using writeBatteryVoltageCalibration.",
            group,
        )
        note.setObjectName("sectionNote")
        note.setWordWrap(True)

        self.calculated_a_value = QLabel("--", group)
        self.calculated_a_value.setObjectName("valueField")
        self.calculated_b_value = QLabel("--", group)
        self.calculated_b_value.setObjectName("valueField")
        self.fit_summary_value = QLabel("No calculated constants yet.", group)
        self.fit_summary_value.setObjectName("valueField")
        self.fit_summary_value.setWordWrap(True)

        self.save_button = QPushButton("Save constants to controller", group)
        self.save_button.clicked.connect(self.save_calibration)

        layout.addWidget(note, 0, 0, 1, 4)
        layout.addWidget(QLabel("Calculated a", group), 1, 0)
        layout.addWidget(self.calculated_a_value, 1, 1)
        layout.addWidget(QLabel("Calculated b", group), 1, 2)
        layout.addWidget(self.calculated_b_value, 1, 3)
        layout.addWidget(QLabel("Fit summary", group), 2, 0)
        layout.addWidget(self.fit_summary_value, 2, 1, 1, 3)
        layout.addWidget(self.save_button, 3, 3)
        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        return buttons

    def add_measurement_point(self) -> None:
        dialog = AddVoltageMeasurementDialog(self.serial_service, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.measurement_point is None:
            return

        self._append_measurement_point(dialog.measurement_point)
        self.status_label.setText(
            f"Added measurement point {len(self._measurement_points)}: measured {dialog.measurement_point.measured_voltage_v:.3f} V, controller {dialog.measurement_point.controller_voltage_v:.3f} V."
        )

    def _append_measurement_point(self, point: VoltageMeasurementPoint) -> None:
        self._measurement_points.append(point)
        self._update_table()
        self._set_calibration_result(None)

    def remove_selected_point(self) -> None:
        selected_row = self.measurements_table.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "Measurement points", "Select a measurement point to remove.")
            return

        removed_point = self._measurement_points.pop(selected_row)
        self._update_table()
        self._set_calibration_result(None)
        self.status_label.setText(
            f"Removed measurement point: measured {removed_point.measured_voltage_v:.3f} V, controller {removed_point.controller_voltage_v:.3f} V."
        )

    def clear_points(self) -> None:
        if not self._measurement_points:
            return

        confirmation = QMessageBox.question(
            self,
            "Clear measurement points",
            "Remove all voltage calibration measurement points?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._measurement_points.clear()
        self._update_table()
        self._set_calibration_result(None)
        self.status_label.setText("Cleared all voltage calibration measurement points.")

    def calculate_constants(self) -> None:
        try:
            result = fit_voltage_calibration(self._measurement_points)
        except VoltageCalibrationError as exc:
            QMessageBox.information(self, "Voltage calibration", str(exc))
            return

        self._set_calibration_result(result)
        self.status_label.setText(
            f"Calculated voltage calibration from {result.point_count} point(s). Review a and b, then save when ready."
        )

    def save_calibration(self) -> None:
        if self._calibration_result is None:
            QMessageBox.information(
                self,
                "Voltage calibration",
                "Create calibration constants before saving them to the controller.",
            )
            return

        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before saving voltage calibration.")
            return

        confirmation = QMessageBox.question(
            self,
            "Save voltage calibration",
            f"Write a={self._calibration_result.format_a()} and b={self._calibration_result.format_b()} to the controller now?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        command = (
            f"writeBatteryVoltageCalibration {self._calibration_result.format_a()} "
            f"{self._calibration_result.format_b()}"
        )

        self._set_busy(True, "Writing battery voltage calibration...")
        try:
            response = self.serial_service.request_text(
                command,
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.5,
                progress_callback=self._process_events,
            )
            normalized = _normalize_response(response)
            if _response_has_error(normalized):
                self.status_label.setText(normalized or "Voltage calibration update failed.")
                QMessageBox.warning(self, "Voltage calibration", normalized or "Voltage calibration update failed.")
                return

            success_message = normalized or "Controller accepted the voltage calibration update."
            self.status_label.setText(success_message)
            QMessageBox.information(self, "Voltage calibration", success_message)
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Voltage calibration", str(exc))
        finally:
            self._set_busy(False)

    def _update_table(self) -> None:
        self.measurements_table.setRowCount(len(self._measurement_points))
        for row_index, point in enumerate(self._measurement_points):
            values = (
                f"{point.measured_voltage_v:.3f}",
                f"{point.controller_voltage_v:.3f}",
                f"{point.error_voltage_v:+.3f}",
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.measurements_table.setItem(row_index, column_index, item)

        has_points = bool(self._measurement_points)
        self.remove_point_button.setEnabled(has_points)
        self.clear_points_button.setEnabled(has_points)
        self.calculate_button.setEnabled(len(self._measurement_points) >= 2)

        if has_points:
            self.measurements_table.selectRow(len(self._measurement_points) - 1)

    def _set_calibration_result(self, result: VoltageCalibrationResult | None) -> None:
        self._calibration_result = result
        if result is None:
            self.calculated_a_value.setText("--")
            self.calculated_b_value.setText("--")
            self.fit_summary_value.setText("No calculated constants yet.")
            self.save_button.setEnabled(False)
            return

        self.calculated_a_value.setText(result.format_a())
        self.calculated_b_value.setText(result.format_b())
        self.fit_summary_value.setText(
            f"{result.point_count} point(s), RMS error {result.rms_error_v:.4f} V, max absolute error {result.max_abs_error_v:.4f} V."
        )
        self.save_button.setEnabled(True)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.measurements_group.setEnabled(not busy)
        self.results_group.setEnabled(not busy)
        self.save_button.setEnabled(not busy and self._calibration_result is not None)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


def _normalize_response(response: str) -> str:
    return " ".join(line.strip() for line in response.splitlines() if line.strip())


def _response_has_error(normalized_response: str) -> bool:
    lowered = normalized_response.casefold()
    return any(marker in lowered for marker in _ERROR_MARKERS)
