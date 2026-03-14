from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from popup_controller.config import AppSettings
from popup_controller.services.build_info_service import parse_build_info_snapshot
from popup_controller.services.external_expander_service import parse_external_expander_snapshot
from popup_controller.services.controller_status_service import parse_controller_status_snapshot
from popup_controller.services.firmware_service import FirmwareService
from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.ui.direct_controls_dialog import DirectControlsDialog
from popup_controller.ui.errors_dialog import ErrorsDialog
from popup_controller.ui.manufacture_dialog import ManufactureDialog
from popup_controller.ui.service_dialog import SERVICE_ACCESS_PASSWORD, ServiceDialog
from popup_controller.ui.section_dialog import SectionDialog
from popup_controller.ui.settings_dialog import SettingsDialog
from popup_controller.ui.sections import SECTION_DEFINITIONS, SectionDefinition
from popup_controller.ui.statistics_dialog import StatisticsDialog

logger = logging.getLogger(__name__)

FLASH_RECONNECT_DELAY_MS = 3000


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        serial_service: SerialService | None = None,
        firmware_service: FirmwareService | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.serial_service = serial_service or SerialService(
            baudrate=settings.default_baudrate,
            timeout_seconds=settings.serial_timeout_seconds,
        )
        self.firmware_service = firmware_service or FirmwareService()
        self.section_buttons: dict[str, QPushButton] = {}
        self._controller_operating_state: str | None = None
        self.setWindowTitle(settings.app_display_name)
        if settings.icon_path.is_file():
            self.setWindowIcon(QIcon(str(settings.icon_path)))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(settings.serial_poll_interval_ms)
        self._poll_timer.timeout.connect(self._poll_serial_feedback)

        self._build_ui()
        self._connect_signals()
        self._refresh_available_ports(
            empty_message="No serial ports detected. Connect a board, then press 'Find controller' to search."
        )
        self._update_connection_state()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)
        root_layout.addWidget(self._build_header_card())
        root_layout.addWidget(self._build_connection_group())
        root_layout.addWidget(self._build_sections_group())
        root_layout.addWidget(self._build_firmware_group())
        root_layout.addWidget(self._build_feedback_group(), stretch=1)
        self.setCentralWidget(central_widget)
        self.setStatusBar(QStatusBar(self))

    def _build_header_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("headerCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.hero_title_label = QLabel(f"ESP32 Pop-up Controller v{self.settings.app_version}", card)
        self.hero_title_label.setObjectName("heroTitle")

        self.hero_subtitle_label = QLabel(
            "Find a running controller for live diagnostics, or choose any visible serial port to flash a fresh ESP32.",
            card,
        )
        self.hero_subtitle_label.setObjectName("heroSubtitle")
        self.hero_subtitle_label.setWordWrap(True)

        self.controller_details_label = QLabel(
            "No controller selected yet. Detect a running controller or pick a serial port below to flash firmware.",
            card,
        )
        self.controller_details_label.setObjectName("controllerBadge")
        self.controller_details_label.setWordWrap(True)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        info_row.addWidget(self._create_header_info_card("FW version", "--", "firmware_version"))
        info_row.addWidget(self._create_header_info_card("Build date", "--", "build_date"))
        info_row.addWidget(self._create_header_info_card("Controller state", "--", "controller_state"))
        info_row.addWidget(self._create_header_info_card("External expander", "--", "external_expander"))
        info_row.addStretch(1)

        layout.addWidget(self.hero_title_label)
        layout.addWidget(self.hero_subtitle_label)
        layout.addWidget(self.controller_details_label)
        layout.addLayout(info_row)
        return card

    def _create_header_info_card(self, caption: str, value: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("miniMetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("miniMetricCaption")

        value_label = QLabel(value, card)
        value_label.setObjectName("miniMetricValue")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        setattr(self, f"{key}_value", value_label)

        layout.addWidget(caption_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Serial connection", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.port_combo = QComboBox(group)
        self.find_controller_button = QPushButton("Find controller", group)
        self.find_controller_button.setProperty("accent", True)
        self.connect_button = QPushButton("Connect", group)
        self.reboot_button = QPushButton("Reboot controller", group)
        self.reboot_button.setToolTip("Reboot the controller and require a fresh search before reconnecting.")
        self.status_label = QLabel("Disconnected", group)
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(QLabel("COM port", group), 0, 0)
        layout.addWidget(self.port_combo, 0, 1)
        layout.addWidget(self.find_controller_button, 0, 2)
        layout.addWidget(self.connect_button, 0, 3)
        layout.addWidget(QLabel("Status", group), 1, 0)
        layout.addWidget(self.status_label, 1, 1, 1, 2)
        layout.addWidget(self.reboot_button, 1, 3)
        return group

    def _build_sections_group(self) -> QGroupBox:
        self.sections_group = QGroupBox("Controller sections", self)
        layout = QGridLayout(self.sections_group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        for index, section in enumerate(SECTION_DEFINITIONS):
            button = QPushButton(f"{section.title}\n{section.button_subtitle}", self.sections_group)
            button.setProperty("sectionButton", True)
            button.setMinimumHeight(88)
            button.setToolTip(section.summary)
            self.section_buttons[section.section_id] = button
            layout.addWidget(button, index // 2, index % 2)

        return self.sections_group

    def _build_firmware_group(self) -> QGroupBox:
        self.firmware_group = QGroupBox("Firmware", self)
        layout = QFormLayout(self.firmware_group)

        row = QWidget(self.firmware_group)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        self.firmware_path_input = QLineEdit(row)
        self.firmware_path_input.setPlaceholderText("Select a flash bundle .zip or flash_manifest.json")
        default_bundle_path = (self.settings.firmware_directory / "flash_bundle.zip").resolve()
        if default_bundle_path.exists():
            self.firmware_path_input.setText(str(default_bundle_path))
        self.browse_firmware_button = QPushButton("Browse", row)
        self.flash_button = QPushButton("Flash firmware", row)

        row_layout.addWidget(self.firmware_path_input, stretch=1)
        row_layout.addWidget(self.browse_firmware_button)
        row_layout.addWidget(self.flash_button)

        layout.addRow("Firmware file", row)
        return self.firmware_group

    def _build_feedback_group(self) -> QGroupBox:
        self.feedback_group = QGroupBox("Activity log", self)
        layout = QVBoxLayout(self.feedback_group)
        self.feedback_log = QPlainTextEdit(self.feedback_group)
        self.feedback_log.setReadOnly(True)
        layout.addWidget(self.feedback_log)
        return self.feedback_group

    def _connect_signals(self) -> None:
        self.find_controller_button.clicked.connect(self.find_controller)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.reboot_button.clicked.connect(self.reboot_controller)
        self.browse_firmware_button.clicked.connect(self.browse_firmware)
        self.flash_button.clicked.connect(self.flash_firmware)

        for section in SECTION_DEFINITIONS:
            self.section_buttons[section.section_id].clicked.connect(
                lambda checked=False, current_section=section: self.open_section_dialog(current_section)
            )

    def find_controller(self) -> None:
        if self.serial_service.is_connected:
            QMessageBox.warning(
                self,
                "Disconnect first",
                "Disconnect from the current serial port before searching again.",
            )
            return

        selected_port = self.serial_service.port_name or self._selected_port()
        available_ports = self._refresh_available_ports(
            empty_message="No serial ports detected. Check the USB cable and try again.",
            preferred_port=selected_port,
        )
        if not available_ports:
            self.controller_details_label.setText(
                "No serial ports are currently visible to the application."
            )
            self._append_log("No serial ports detected while searching for the controller.")
            self._update_connection_state()
            return

        self.find_controller_button.setEnabled(False)
        self.status_label.setText("Searching for controller...")
        self.statusBar().showMessage(self.status_label.text())
        self.controller_details_label.setText(
            f"Scanning {len(available_ports)} serial port(s) for a valid controller reply..."
        )
        self._append_log(
            f"Searching {len(available_ports)} serial port(s) for the controller."
        )
        QApplication.processEvents()

        try:
            result = self.serial_service.find_controller_port(
                probe_command=self.settings.controller_probe_command,
                expected_response_fragment=self.settings.controller_probe_response_fragment,
                warmup_seconds=self.settings.controller_probe_warmup_seconds,
                probe_window_seconds=self.settings.controller_probe_window_seconds,
            )
        except SerialConnectionError as exc:
            QMessageBox.critical(self, "Search failed", str(exc))
            self._update_connection_state()
            return
        finally:
            self.find_controller_button.setEnabled(True)

        if result is None:
            self._append_log("Controller was not found on the available COM ports.")
            selected_port = self._selected_port()
            if selected_port:
                self.controller_details_label.setText(
                    "The scan completed, but no device answered like a running controller. "
                    f"You can still flash firmware directly to {selected_port} or choose another visible serial port."
                )
            else:
                self.controller_details_label.setText(
                    "The scan completed, but no device answered with the expected controller response."
                )
            self._update_connection_state()
            return

        self.port_combo.clear()
        self.port_combo.addItem(f"{result.port.device} - {result.port.description}", result.port.device)
        self.port_combo.setEnabled(True)

        first_reply_line = next(
            (line.strip() for line in result.response.splitlines() if line.strip()),
            "",
        )
        self._append_log(f"Found controller on {result.port.device}.")
        if first_reply_line:
            self._append_log(f"Probe reply: {first_reply_line}")

        self.controller_details_label.setText(
            f"Detected controller on {result.port.device} ({result.port.description}). Connect to load live data."
        )
        self._update_connection_state()

    def open_section_dialog(self, section: SectionDefinition) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(
                self,
                "Connect first",
                "Connect to the controller before opening a live section dialog.",
            )
            return

        if section.section_id == "direct_controls" and self._controller_operating_state == "BENCH MODE":
            QMessageBox.information(
                self,
                "Direct controls unavailable",
                "Direct controls cannot be opened while the controller is in bench mode.",
            )
            return

        if section.section_id == "statistics":
            dialog = StatisticsDialog(self.serial_service, self)
        elif section.section_id == "errors":
            dialog = ErrorsDialog(self.serial_service, self)
        elif section.section_id == "manufacture":
            dialog = ManufactureDialog(self.serial_service, self)
        elif section.section_id == "settings":
            dialog = SettingsDialog(
                self.serial_service,
                self,
                self.settings.remote_mapping_reference_image_path,
            )
        elif section.section_id == "direct_controls":
            dialog = DirectControlsDialog(self.serial_service, self)
        elif section.section_id == "service":
            if not self._request_service_access():
                return
            dialog = ServiceDialog(self.serial_service, self)
        else:
            dialog = SectionDialog(section, self)

        poll_was_active = self._poll_timer.isActive()
        if poll_was_active:
            self._poll_timer.stop()

        try:
            dialog.exec()
        finally:
            if poll_was_active and self.serial_service.is_connected:
                self._poll_timer.start()

    def toggle_connection(self) -> None:
        if self.serial_service.is_connected:
            current_port = self.serial_service.port_name
            self.serial_service.disconnect()
            self._clear_build_info()
            self._clear_controller_state()
            self._clear_external_expander()
            self._append_log("Disconnected from serial port.")
            self.controller_details_label.setText(
                f"Disconnected from {current_port}. Reconnect to use the live controller sections again."
            )
            self._poll_timer.stop()
            self._update_connection_state()
            return

        port = self._selected_port()
        if not port:
            QMessageBox.warning(self, "No port selected", "Find the controller before connecting.")
            return

        self._connect_to_port(port)

    def _connect_to_port(
        self,
        port: str,
        failure_title: str = "Connection failed",
        show_failure_dialog: bool = True,
    ) -> bool:
        try:
            self.serial_service.connect(port)
        except SerialConnectionError as exc:
            self._append_log(f"Connection to {port} failed: {exc}")
            self.controller_details_label.setText(f"Unable to connect to {port}. {exc}")
            self._update_connection_state()
            if show_failure_dialog:
                QMessageBox.critical(self, failure_title, str(exc))
            return False

        self._append_log(f"Connected to {port} at {self.serial_service.baudrate} baud.")
        self.controller_details_label.setText(
            f"Connected to {port}. The live controller sections are ready to open."
        )
        self._refresh_build_info()
        self._refresh_controller_state()
        self._refresh_external_expander()
        self._poll_timer.start()
        self._update_connection_state()
        return True

    def _schedule_post_flash_reconnect(self, port: str) -> None:
        self.controller_details_label.setText(
            f"Firmware flash finished on {port}. Waiting 3 seconds before reconnecting automatically."
        )
        self.statusBar().showMessage(f"Waiting 3 seconds before reconnecting to {port}...")
        QTimer.singleShot(FLASH_RECONNECT_DELAY_MS, lambda port_name=port: self._reconnect_after_flash(port_name))

    def _reconnect_after_flash(self, port: str) -> None:
        if self.serial_service.is_connected:
            return

        self.controller_details_label.setText(
            f"Trying to reconnect to {port} after firmware flash..."
        )
        self.statusBar().showMessage(f"Trying to reconnect to {port} after firmware flash...")
        QApplication.processEvents()

        if self._connect_to_port(port, failure_title="Reconnect failed", show_failure_dialog=False):
            self.controller_details_label.setText(
                f"Reconnected to {port} after firmware flash. Verify the new firmware information above."
            )
            self._append_log(f"Automatic reconnect after firmware flash succeeded on {port}.")
            self.statusBar().showMessage(f"Reconnected to {port} after firmware flash.")
            return

        self.controller_details_label.setText(
            f"Automatic reconnect to {port} after firmware flash did not succeed. Press Connect to try again."
        )
        self._append_log(f"Automatic reconnect after firmware flash did not succeed on {port}.")
        self.statusBar().showMessage(f"Automatic reconnect to {port} failed.")

    def reboot_controller(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before requesting a reboot.")
            return

        confirmation = QMessageBox.question(
            self,
            "Reboot controller",
            "Reboot the controller now? The app will disconnect and require a fresh search before reconnecting.",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        current_port = self.serial_service.port_name or "controller"
        try:
            self.serial_service.send_command("reboot")
        except SerialConnectionError as exc:
            QMessageBox.warning(self, "Reboot controller", str(exc))
            return

        self._append_log(f"Reboot command sent to {current_port}.")
        self._poll_timer.stop()
        self.serial_service.disconnect()
        self._reset_port_selection("Controller reboot requested. Press 'Find controller' to search again.")
        self.controller_details_label.setText(
            f"Reboot requested for {current_port}. Wait for the controller to restart, then search again to reconnect."
        )
        self._update_connection_state()

    def _request_service_access(self) -> bool:
        password, accepted = QInputDialog.getText(
            self,
            "Service access",
            "Enter the service password:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return False

        if password.strip() != SERVICE_ACCESS_PASSWORD:
            QMessageBox.warning(self, "Service access", "Incorrect service password.")
            return False

        return True

    def _refresh_build_info(self) -> None:
        if not self.serial_service.is_connected:
            self._clear_build_info()
            return

        try:
            raw_response = self.serial_service.request_text(
                "printBuildInfo",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
            )
        except SerialConnectionError as exc:
            self._clear_build_info()
            self._append_log(f"Build info read failed: {exc}")
            return

        snapshot = parse_build_info_snapshot(raw_response)
        firmware_version = snapshot.firmware_version or "Unavailable"
        build_date = snapshot.build_date or "Unavailable"

        self.firmware_version_value.setText(firmware_version)
        self.build_date_value.setText(build_date)
        self.firmware_version_value.setToolTip(snapshot.firmware_version or "")
        self.build_date_value.setToolTip(snapshot.build_timestamp or "")

        if snapshot.firmware_version or snapshot.build_timestamp:
            self._append_log(
                f"Build info: FW {firmware_version}, built {snapshot.build_timestamp or build_date}."
            )
        else:
            self._append_log("Build info command returned no recognizable fields.")

    def _clear_build_info(self) -> None:
        self.firmware_version_value.setText("--")
        self.build_date_value.setText("--")
        self.firmware_version_value.setToolTip("")
        self.build_date_value.setToolTip("")

    def _refresh_controller_state(self) -> None:
        if not self.serial_service.is_connected:
            self._clear_controller_state()
            return

        try:
            raw_response = self.serial_service.request_text(
                "getControllerStatus",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
            )
        except SerialConnectionError as exc:
            self._clear_controller_state()
            self._append_log(f"Controller status read failed: {exc}")
            return

        snapshot = parse_controller_status_snapshot(raw_response)
        self._controller_operating_state = snapshot.state
        self.controller_state_value.setText(snapshot.state or "Unavailable")
        self.controller_state_value.setToolTip(snapshot.status_hint or "\n".join(snapshot.raw_lines))
        self._update_section_button_states()

        if snapshot.state is not None:
            self._append_log(f"Controller state: {snapshot.state}.")
        else:
            self._append_log(f"Controller state unavailable: {snapshot.status_hint}")

    def _clear_controller_state(self) -> None:
        self._controller_operating_state = None
        self.controller_state_value.setText("--")
        self.controller_state_value.setToolTip("")
        self._update_section_button_states()

    def _refresh_external_expander(self) -> None:
        if not self.serial_service.is_connected:
            self._clear_external_expander()
            return

        try:
            raw_response = self.serial_service.request_text(
                "getExternalExpander",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
            )
        except SerialConnectionError as exc:
            self._clear_external_expander()
            self._append_log(f"External expander read failed: {exc}")
            return

        snapshot = parse_external_expander_snapshot(raw_response)
        self.external_expander_value.setText(snapshot.state or "Unavailable")
        self.external_expander_value.setToolTip(snapshot.status_hint or "\n".join(snapshot.raw_lines))

        if snapshot.state is not None:
            self._append_log(f"External expander: {snapshot.state}.")
        else:
            self._append_log(f"External expander unavailable: {snapshot.status_hint}")

    def _clear_external_expander(self) -> None:
        self.external_expander_value.setText("--")
        self.external_expander_value.setToolTip("")

    def browse_firmware(self) -> None:
        start_dir = str(self.settings.firmware_directory.resolve())
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select firmware bundle",
            start_dir,
            "Flash bundles (*.zip *.json);;All files (*.*)",
        )
        if selected_file:
            self.firmware_path_input.setText(selected_file)

    def flash_firmware(self) -> None:
        selected_port = self.serial_service.port_name or self._selected_port() or ""
        if not selected_port:
            QMessageBox.warning(self, "No port selected", "Select a serial port before starting a firmware flash.")
            return

        was_connected = self.serial_service.is_connected
        firmware_path_text = self.firmware_path_input.text().strip()
        if not firmware_path_text:
            QMessageBox.warning(
                self,
                "No flash bundle selected",
                "Select a flash bundle .zip or flash_manifest.json before flashing.",
            )
            return

        firmware_path = Path(firmware_path_text)
        confirmation_message = (
            f"Flash the selected firmware to {selected_port}? "
            "The app will disconnect from the controller before esptool starts."
            if was_connected
            else f"Flash the selected firmware to {selected_port}? "
            "The controller does not need to be connected before esptool starts."
        )
        confirmation = QMessageBox.question(
            self,
            "Flash firmware",
            confirmation_message,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._poll_timer.stop()
        if was_connected:
            self.serial_service.disconnect()
        self._clear_build_info()
        self._clear_controller_state()
        self._clear_external_expander()
        self.controller_details_label.setText(
            f"Preparing firmware flash on {selected_port}. Wait for the controller to reboot after flashing completes."
        )
        self._append_log(f"Starting firmware flash on {selected_port} using {firmware_path}.")
        self._update_connection_state()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(f"Flashing firmware on {selected_port}...")
        QApplication.processEvents()
        try:
            result = self.firmware_service.flash_firmware(selected_port, firmware_path)
        finally:
            QApplication.restoreOverrideCursor()

        self._append_log(result.message)
        if result.success:
            QMessageBox.information(
                self,
                "Firmware",
                f"{result.message}\n\nThe app will try to reconnect to {selected_port} in 3 seconds.",
            )
            self._schedule_post_flash_reconnect(selected_port)
        else:
            self.controller_details_label.setText(
                f"Firmware flash failed on {selected_port}. Review the activity log and try again when ready."
            )
            QMessageBox.warning(self, "Firmware", result.message)

        self._update_connection_state()

    def _poll_serial_feedback(self) -> None:
        try:
            messages = self.serial_service.read_available()
        except SerialConnectionError as exc:
            self._poll_timer.stop()
            self.serial_service.disconnect()
            self._clear_build_info()
            self._clear_controller_state()
            self._clear_external_expander()
            self.controller_details_label.setText(
                "The controller connection was lost while reading serial feedback."
            )
            self._update_connection_state()
            QMessageBox.critical(self, "Read failed", str(exc))
            return

        for message in messages:
            self._append_log(f"RX < {message}")

    def _selected_port(self) -> str | None:
        value = self.port_combo.currentData()
        if not value:
            return None
        return str(value)

    def _refresh_available_ports(
        self,
        empty_message: str,
        preferred_port: str | None = None,
    ) -> list:
        available_ports = self.serial_service.available_ports()
        if not available_ports:
            self._reset_port_selection(empty_message)
            return []

        self.port_combo.clear()
        for port_info in available_ports:
            self.port_combo.addItem(f"{port_info.device} - {port_info.description}", port_info.device)

        self.port_combo.setEnabled(True)

        if preferred_port:
            port_index = self.port_combo.findData(preferred_port)
            if port_index >= 0:
                self.port_combo.setCurrentIndex(port_index)

        return available_ports

    def _reset_port_selection(self, message: str) -> None:
        self.port_combo.clear()
        self.port_combo.addItem(message, "")
        self.port_combo.setEnabled(False)
        self._clear_build_info()
        self._clear_controller_state()
        self._clear_external_expander()

    def _update_connection_state(self) -> None:
        connected = self.serial_service.is_connected
        selected_port = self._selected_port()

        self.connect_button.setText("Disconnect" if connected else "Connect")
        if connected:
            status_text = f"Connected to {self.serial_service.port_name}"
        elif selected_port:
            status_text = f"Ready to connect or flash on {selected_port}"
        else:
            status_text = "Disconnected"

        self.status_label.setText(status_text)
        self.sections_group.setEnabled(connected)
        self._update_section_button_states()
        self.firmware_group.setEnabled(connected or bool(selected_port))
        self.connect_button.setEnabled(connected or bool(selected_port))
        self.reboot_button.setEnabled(connected)
        self.find_controller_button.setEnabled(not connected)
        self.statusBar().showMessage(status_text)

    def _update_section_button_states(self) -> None:
        direct_controls_button = self.section_buttons.get("direct_controls")
        if direct_controls_button is None:
            return

        direct_controls_button.setEnabled(
            self.serial_service.is_connected and self._controller_operating_state != "BENCH MODE"
        )

    def _append_log(self, message: str) -> None:
        logger.info(message)
        self.feedback_log.appendPlainText(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._poll_timer.stop()
        if self.serial_service.is_connected:
            self.serial_service.disconnect()
        event.accept()
