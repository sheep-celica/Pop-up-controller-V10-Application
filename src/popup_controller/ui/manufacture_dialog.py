from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QShowEvent
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
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.manufacture_service import (
    ManufactureField,
    ManufactureSnapshot,
    calculate_controller_age,
    parse_manufacture_snapshot,
    try_parse_manufacture_date,
)
from popup_controller.services.serial_service import SerialConnectionError, SerialService


class ManufactureDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False
        self._initial_load_scheduled = False

        self.setWindowTitle("Manufacture Data")
        self.resize(760, 540)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel("Manufacture Data", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "This dialog fetches controller identity and production metadata when it opens. Fields omitted by the firmware are shown as unavailable.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Loading manufacture data...", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.overview_group = self._build_overview_group()
        self.identity_group = self._build_identity_group()
        buttons = self._build_buttons()

        root_layout.addWidget(title_label)
        root_layout.addWidget(summary_label)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.loading_frame)
        root_layout.addWidget(self.overview_group)
        root_layout.addWidget(self.identity_group)
        root_layout.addStretch(1)
        root_layout.addWidget(buttons)

        self._set_busy(True, "Loading manufacture data...")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._initial_load_scheduled:
            self._initial_load_scheduled = True
            QTimer.singleShot(75, self.load_manufacture_data)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Loading manufacture data...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_overview_group(self) -> QGroupBox:
        group = QGroupBox("Overview", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.addWidget(self._create_metric_card("Serial number", "--", "controller serial", "serial_number"), 0, 0)
        layout.addWidget(self._create_metric_card("Manufacture date", "--", "recorded production date", "manufacture_date"), 0, 1)
        layout.addWidget(
            self._create_metric_card("Initial FW version", "--", "firmware at manufacture", "initial_firmware_version"),
            1,
            0,
            1,
            2,
        )
        return group

    def _build_identity_group(self) -> QGroupBox:
        group = QGroupBox("Board identity", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.addWidget(self._create_detail_card("Board serial", "board_serial"), 0, 0)
        layout.addWidget(self._create_detail_card("Board revision", "board_revision"), 0, 1)
        layout.addWidget(self._create_detail_card("Car model", "car_model"), 0, 2)
        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        return buttons

    def _create_metric_card(self, caption: str, value: str, suffix: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("metricCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(6)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("metricCaption")

        value_label = QLabel(value, card)
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        value_label.setWordWrap(True)

        suffix_label = QLabel(suffix, card)
        suffix_label.setObjectName("metricSuffix")
        suffix_label.setWordWrap(True)

        setattr(self, f"{key}_value", value_label)
        setattr(self, f"{key}_suffix", suffix_label)

        card_layout.addWidget(caption_label)
        card_layout.addWidget(value_label)
        card_layout.addWidget(suffix_label)
        card_layout.addStretch(1)
        return card

    def _create_detail_card(self, caption: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("miniMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("miniMetricCaption")
        caption_label.setWordWrap(True)

        value_label = QLabel("--", card)
        value_label.setObjectName("miniMetricValue")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)

        setattr(self, f"{key}_value", value_label)

        layout.addWidget(caption_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card

    def load_manufacture_data(self) -> None:
        if not self.serial_service.is_connected:
            self.status_label.setText("Connect to the controller before opening manufacture data.")
            self._set_busy(False)
            return

        self._set_busy(True, "Loading manufacture data...")
        try:
            raw_response = self.serial_service.request_text(
                "printEverything",
                idle_timeout_seconds=0.45,
                max_duration_seconds=4.0,
                progress_callback=self._process_loading_events,
            )
            if not raw_response.strip():
                raise SerialConnectionError("The controller did not return any manufacture data.")

            snapshot = parse_manufacture_snapshot(raw_response)
            self._apply_snapshot(snapshot)
            self.status_label.setText(self._build_status_message(snapshot))
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Manufacture data", str(exc))
        finally:
            self._set_busy(False)

    def _apply_snapshot(self, snapshot: ManufactureSnapshot) -> None:
        self._apply_overview_field("serial_number", snapshot.serial_number, "controller serial")
        self._apply_manufacture_date_field(snapshot.manufacture_date)
        self._apply_overview_field(
            "initial_firmware_version",
            snapshot.initial_firmware_version,
            "firmware at manufacture",
        )

        self.board_serial_value.setText(snapshot.board_serial.compact_display)
        self.board_revision_value.setText(snapshot.board_revision.compact_display)
        self.car_model_value.setText(snapshot.car_model.compact_display)

    def _apply_overview_field(self, key: str, field: ManufactureField, default_suffix: str) -> None:
        getattr(self, f"{key}_value").setText(field.compact_display)
        getattr(self, f"{key}_suffix").setText(field.status_hint or default_suffix)

    def _apply_manufacture_date_field(self, field: ManufactureField) -> None:
        self.manufacture_date_value.setText(field.compact_display)

        if field.value is None:
            self.manufacture_date_suffix.setText(field.status_hint or "recorded production date")
            return

        parsed_date = try_parse_manufacture_date(field)
        if parsed_date is None:
            self.manufacture_date_suffix.setText("Age unavailable for this date format")
            return

        age = calculate_controller_age(parsed_date)
        if age is None:
            self.manufacture_date_suffix.setText("Reported date is in the future")
            return

        self.manufacture_date_suffix.setText(f"Age: {age.display}")

    def _build_status_message(self, snapshot: ManufactureSnapshot) -> str:
        if snapshot.reported_field_count == 0:
            return (
                f"Controller responded on {self.serial_service.port_name}, but the expected manufacture fields were not reported."
            )
        if snapshot.reported_field_count < 6:
            return (
                f"Manufacture data refreshed from {self.serial_service.port_name}. Some fields are unavailable on this firmware."
            )
        return f"Manufacture data refreshed from {self.serial_service.port_name}."

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.overview_group.setEnabled(not busy)
        self.identity_group.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_loading_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)