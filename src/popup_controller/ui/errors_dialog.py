from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.error_service import ErrorEntry, ErrorReport, parse_stored_error_report
from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.ui.window_helpers import apply_initial_window_size, create_scrollable_dialog_layout


class ErrorsDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False
        self._initial_load_scheduled = False

        self.setWindowTitle("Errors")

        root_layout, content_layout, self.scroll_area = create_scrollable_dialog_layout(self)

        title_label = QLabel("Errors", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "This dialog reads the stored controller error log, lets you clear it, and groups the reported entries into headlight-specific and other module faults.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Loading stored controller errors...", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.headlight_group = self._build_error_group("Headlight / pop-up stored errors", "headlight")
        self.module_group = self._build_error_group("Other module stored errors", "module")
        buttons = self._build_buttons()

        content_layout.addWidget(title_label)
        content_layout.addWidget(summary_label)
        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.loading_frame)
        content_layout.addWidget(self.headlight_group)
        content_layout.addWidget(self.module_group)
        content_layout.addStretch(1)
        root_layout.addWidget(buttons)

        apply_initial_window_size(self, 920, 560)

        self._set_busy(True, "Loading stored controller errors...")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._initial_load_scheduled:
            self._initial_load_scheduled = True
            QTimer.singleShot(75, self.load_errors)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Loading stored controller errors...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_error_group(self, title: str, key: str) -> QGroupBox:
        group = QGroupBox(title, self)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        table = QTableWidget(0, 4, group)
        table.setHorizontalHeaderLabels(("Boot cycle", "Error code", "Battery voltage [V]", "Temperature [\N{DEGREE SIGN}C]"))
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setMinimumHeight(170)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        setattr(self, f"{key}_table", table)

        hint_label = QLabel("--", group)
        hint_label.setObjectName("metricSuffix")
        hint_label.setWordWrap(True)
        setattr(self, f"{key}_hint", hint_label)

        layout.addWidget(table)
        layout.addWidget(hint_label)
        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.clear_errors_button = QPushButton("Clear errors", self)
        self.refresh_button = QPushButton("Refresh errors", self)
        buttons.addButton(self.clear_errors_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        self.clear_errors_button.clicked.connect(self.clear_errors)
        self.refresh_button.clicked.connect(self.load_errors)
        return buttons

    def clear_errors(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before clearing errors.")
            return

        confirmation = QMessageBox.question(
            self,
            "Clear errors",
            "Clear the controller's stored error log now?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, "Clearing stored controller errors...")
        try:
            response = self.serial_service.request_text(
                "clearErrors",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            normalized = " ".join(line.strip() for line in response.splitlines() if line.strip())
            if not normalized:
                normalized = "Controller stored error log clear command accepted."

            lowered = normalized.casefold()
            if any(marker in lowered for marker in ("unknown command", "placeholder", "rejected", "failed", "invalid")):
                self.status_label.setText(normalized)
                QMessageBox.warning(self, "Clear errors", normalized)
                return

            self.status_label.setText(normalized)
            self.load_errors()
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Clear errors", str(exc))
        finally:
            self._set_busy(False)

    def load_errors(self) -> None:
        if not self.serial_service.is_connected:
            self.status_label.setText("Connect to the controller before opening errors.")
            self._set_busy(False)
            return

        self._set_busy(True, "Loading stored controller errors...")
        try:
            print_response = self.serial_service.request_text(
                "printErrors",
                idle_timeout_seconds=0.6,
                max_duration_seconds=3.0,
                progress_callback=self._process_loading_events,
            )
            report = parse_stored_error_report(print_response)
            self._apply_report("headlight", report.headlight_entries, report)
            self._apply_report("module", report.module_entries, report)
            self.status_label.setText(self._build_status_message(report))
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Errors", str(exc))
        finally:
            self._set_busy(False)

    def _apply_report(self, key: str, entries: tuple[ErrorEntry, ...], report: ErrorReport) -> None:
        table = getattr(self, f"{key}_table")
        hint_label = getattr(self, f"{key}_hint")

        table.setRowCount(0)

        if entries:
            table.setRowCount(len(entries))
            for row_index, entry in enumerate(entries):
                self._set_table_item(table, row_index, 0, self._format_boot_cycle(entry), Qt.AlignmentFlag.AlignCenter)
                self._set_table_item(table, row_index, 1, entry.error_code, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, entry.raw_line)
                self._set_table_item(table, row_index, 2, self._format_voltage(entry), Qt.AlignmentFlag.AlignCenter, entry.raw_line)
                self._set_table_item(table, row_index, 3, self._format_temperature(entry), Qt.AlignmentFlag.AlignCenter, entry.raw_line)
            hint_label.setText("Parsed from the stored controller error log.")
            return

        lowered_hint = report.status_hint.casefold()
        if "no stored errors" in lowered_hint:
            hint_label.setText("No stored errors reported by the controller.")
        else:
            hint_label.setText(report.status_hint or "No additional details reported.")

    def _set_table_item(
        self,
        table: QTableWidget,
        row: int,
        column: int,
        text: str,
        alignment: Qt.AlignmentFlag,
        tooltip: str = "",
    ) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(int(alignment))
        if tooltip:
            item.setToolTip(tooltip)
        table.setItem(row, column, item)

    def _format_boot_cycle(self, entry: ErrorEntry) -> str:
        if entry.boot_cycle is None:
            return "--"
        return str(entry.boot_cycle)

    def _format_voltage(self, entry: ErrorEntry) -> str:
        if entry.battery_voltage_volts is None:
            return "--"
        return f"{entry.battery_voltage_volts:.2f}"

    def _format_temperature(self, entry: ErrorEntry) -> str:
        if entry.temperature_celsius is None:
            return "--"
        return f"{entry.temperature_celsius:.1f}"

    def _build_status_message(self, report: ErrorReport) -> str:
        messages = [f"Stored errors refreshed from {self.serial_service.port_name}."]
        if report.has_errors:
            error_count = len(report.headlight_entries) + len(report.module_entries)
            messages.append(f"{error_count} stored error log entr{'y' if error_count == 1 else 'ies'} reported.")
        elif report.status_hint:
            messages.append(report.status_hint)
        return " ".join(messages)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.headlight_group.setEnabled(not busy)
        self.module_group.setEnabled(not busy)
        self.clear_errors_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_loading_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


