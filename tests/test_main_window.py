from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QScrollArea

from popup_controller.config import AppSettings
from popup_controller.services.firmware_service import FlashResult
from popup_controller.services.firmware_release_service import FirmwareDownloadResult, FirmwareReleaseInfo
from popup_controller.services.serial_service import SerialConnectionError, SerialPortInfo
from popup_controller.ui import main_window as main_window_module
from popup_controller.ui.main_window import MainWindow
from popup_controller.ui.sections import SECTION_DEFINITIONS


class FakeSerialService:
    def __init__(
        self,
        port_name: str = "COM11",
        connected: bool = True,
        available_ports: list[SerialPortInfo] | None = None,
        request_responses: dict[str, str] | None = None,
    ) -> None:
        self.baudrate = 115200
        self.timeout_seconds = 0.1
        self._connected = connected
        self._port_name = port_name
        self._available_ports = list(available_ports or [])
        self._request_responses = dict(request_responses or {})
        self.connect_calls: list[str] = []
        self.request_calls: list[str] = []
        self.disconnect_calls = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str | None:
        return self._port_name if self._connected else None

    def connect(self, port: str) -> None:
        self.connect_calls.append(port)
        self._connected = True
        self._port_name = port

    def connect_to_controller(
        self,
        port: str,
        probe_command: str = "help",
        expected_response_fragment: str = "Available commands:",
        **kwargs,
    ) -> str:
        self.connect(port)
        response = self._request_responses.get(probe_command, "")
        if expected_response_fragment not in response:
            self.disconnect()
            raise SerialConnectionError(
                f"{port} opened, but the device did not answer the controller probe. "
                "It may be an unflashed ESP32. You can still flash firmware to this port."
            )
        return response

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    def available_ports(self):
        return list(self._available_ports)

    def find_controller_port(self, **kwargs):
        return None

    def read_available(self):
        return []

    def request_text(self, command: str, **kwargs) -> str:
        self.request_calls.append(command)
        return self._request_responses.get(command, "")




class FakeFirmwareService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def flash_firmware(self, port: str, firmware_path: Path) -> FlashResult:
        self.calls.append((port, firmware_path))
        return FlashResult(True, f"Flashed test bundle to {port}.")


class FakeFirmwareReleaseService:
    def __init__(self) -> None:
        self.release = FirmwareReleaseInfo(
            version="1.0.9",
            release_name="Firmware version 1.0.9",
            tag_name="firmware",
            asset_name="pop_up_controller_v10_firmware_v_1.0.9.zip",
            download_url="https://example.invalid/firmware.zip",
            asset_size_bytes=None,
            asset_sha256=None,
            published_at="2026-03-15T17:57:58Z",
            updated_at="2026-03-17T20:45:30Z",
            html_url="https://example.invalid/releases/tag/firmware",
        )
        self.fetch_calls = 0
        self.download_calls: list[tuple[FirmwareReleaseInfo, Path]] = []

    def fetch_latest_release(self) -> FirmwareReleaseInfo:
        self.fetch_calls += 1
        return self.release

    def download_release_asset(self, release: FirmwareReleaseInfo, destination_directory: Path) -> FirmwareDownloadResult:
        self.download_calls.append((release, destination_directory))
        destination_directory.mkdir(parents=True, exist_ok=True)
        downloaded_path = destination_directory / release.asset_name
        downloaded_path.write_bytes(b"zip data")
        return FirmwareDownloadResult(path=downloaded_path, downloaded=True)


class FakeSupportExportService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export_to_file(self, **kwargs):
        self.calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        output_path.write_text('{"ok": true}', encoding="utf-8")
        return output_path


def test_main_window_shows_application_version(qtbot) -> None:
    settings = AppSettings()
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.windowTitle() == settings.app_display_name
    assert settings.app_version in window.hero_title_label.text()


def test_main_window_uses_scroll_area_for_overflow_content(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window.resize(settings.default_window_width, settings.default_window_height)
    window.show()
    qtbot.wait(50)

    assert window.centralWidget() is window.central_container
    assert isinstance(window.central_scroll_area, QScrollArea)
    assert window.loading_slot.height() >= window.main_loading_frame.sizeHint().height()
    assert window.central_scroll_area.verticalScrollBar().maximum() > 0


def test_main_window_preserves_scroll_position_after_busy_cycle(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window.resize(settings.default_window_width, settings.default_window_height)
    window.show()
    qtbot.wait(50)

    scroll_bar = window.central_scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    qtbot.wait(10)
    scroll_bar.setValue(0)
    qtbot.wait(10)

    assert scroll_bar.value() == 0

    window._begin_busy("Searching for controller...")
    scroll_bar.setValue(min(scroll_bar.maximum(), 80))
    window._end_busy()
    qtbot.wait(200)

    assert scroll_bar.value() == 0


def test_main_window_reflows_header_cards_on_narrow_width(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window.resize(780, settings.default_window_height)
    window.show()
    qtbot.wait(50)

    positions = [window.header_metrics_layout.getItemPosition(index)[:2] for index in range(window.header_metrics_layout.count())]

    assert max(column for _, column in positions) == 1
    assert max(row for row, _ in positions) >= 2


def test_main_window_marks_nested_layout_wrappers_with_surface_roles(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.central_container.property("surfaceRole") == "window"
    assert window.loading_slot.property("surfaceRole") == "transparent"
    assert window.header_metrics_widget.property("surfaceRole") == "transparent"


def test_main_window_uses_accented_form_labels_for_field_captions(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.port_label.objectName() == "formFieldLabel"
    assert window.connection_status_label.objectName() == "formFieldLabel"
    assert window.firmware_file_label.objectName() == "formFieldLabel"
    assert window.github_release_label.objectName() == "formFieldLabel"


def test_main_window_styles_latest_release_like_serial_status_and_removes_manual_check_button(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.latest_firmware_status_label.objectName() == "statusPill"
    assert window.latest_firmware_status_label.wordWrap() is False
    assert "Check latest" not in [
        button.text() for button in window.firmware_group.findChildren(QPushButton) if button.text()
    ]


def test_main_window_places_support_export_button_in_sections_group(qtbot) -> None:
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.export_support_button.parentWidget() is window.sections_group
    assert window.export_support_button.text() == "Export support file"


def test_main_window_header_cards_start_neutral_before_connection_attempt(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.firmware_version_card.property("semanticState") is None
    assert window.build_date_card.property("semanticState") is None
    assert window.controller_state_card.property("semanticState") is None
    assert window.external_expander_card.property("semanticState") is None
    assert window.temperature_card.property("semanticState") is None
    assert window.firmware_update_indicator.isHidden() is True


def test_main_window_latest_release_lookup_does_not_turn_fw_cards_red_without_live_build_info(qtbot) -> None:
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
        firmware_release_service=FakeFirmwareReleaseService(),
    )
    qtbot.addWidget(window)

    window._apply_latest_firmware_release(window.firmware_release_service.fetch_latest_release())

    assert window.firmware_version_card.property("semanticState") is None
    assert window.build_date_card.property("semanticState") is None
    assert window.firmware_update_indicator.isHidden() is True


def test_main_window_renames_external_expander_card_caption(qtbot) -> None:
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    labels = window.external_expander_card.findChildren(type(window.external_expander_value))
    assert any(label.text() == "Remote expansion module" for label in labels)


def test_main_window_marks_connected_header_cards_green_when_values_are_healthy(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={
            "printBuildInfo": "FW_VERSION=1.0.9\nBUILD_TIMESTAMP=2026-03-15T17:57:58Z\n",
            "getControllerStatus": "[66] Controller status: RUNNING\n",
            "getExternalExpander": "Connected\n",
            "readTemperature": "[734828] Temperature: 22.50 C\n",
        },
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_build_info()
    window._refresh_controller_state()
    window._refresh_external_expander()
    window._refresh_temperature()

    assert window.firmware_version_card.property("semanticState") == "good"
    assert window.build_date_card.property("semanticState") == "good"
    assert window.controller_state_card.property("semanticState") == "good"
    assert window.external_expander_card.property("semanticState") == "good"
    assert window.temperature_card.property("semanticState") == "good"


def test_main_window_marks_outdated_firmware_and_build_date_caution(qtbot, tmp_path: Path) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={
            "printBuildInfo": "FW_VERSION=1.0.8\nBUILD_TIMESTAMP=2026-03-10T12:00:00Z\n",
        },
    )
    release_service = FakeFirmwareReleaseService()
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False, firmware_directory=tmp_path),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
        firmware_release_service=release_service,
    )
    qtbot.addWidget(window)

    window._refresh_build_info()
    assert window.firmware_version_card.property("semanticState") == "good"
    assert window.build_date_card.property("semanticState") == "good"

    window.refresh_latest_firmware()

    assert window.firmware_version_card.property("semanticState") == "caution"
    assert window.build_date_card.property("semanticState") == "caution"
    assert window.firmware_update_indicator.isHidden() is False
    assert window.firmware_update_indicator.toolTip() == "A newer version is available."
    assert window.firmware_update_indicator.text() == "!"


def test_main_window_marks_bench_mode_caution(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"getControllerStatus": "[66] Controller status: BENCH MODE\n"},
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_controller_state()

    assert window.controller_state_card.property("semanticState") == "caution"


def test_main_window_marks_external_expander_not_connected_danger(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"getExternalExpander": "Not Connected\n"},
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_external_expander()

    assert window.external_expander_card.property("semanticState") == "danger"


def test_main_window_marks_out_of_range_temperature_danger(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"readTemperature": "[734828] Temperature: 44.50 C\n"},
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_temperature()

    assert window.temperature_card.property("semanticState") == "danger"


def test_main_window_marks_failed_readouts_danger(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={
            "printBuildInfo": "",
            "getControllerStatus": "",
            "getExternalExpander": "",
            "readTemperature": "",
        },
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_build_info()
    window._refresh_controller_state()
    window._refresh_external_expander()
    window._refresh_temperature()

    assert window.firmware_version_card.property("semanticState") == "danger"
    assert window.build_date_card.property("semanticState") == "danger"
    assert window.controller_state_card.property("semanticState") == "danger"
    assert window.external_expander_card.property("semanticState") == "danger"
    assert window.temperature_card.property("semanticState") == "danger"


def test_main_window_disables_manual_command_controls_until_connected_and_non_empty(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    serial_service = FakeSerialService(connected=False)
    window = MainWindow(
        settings=settings,
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.manual_command_input.isEnabled() is False
    assert window.manual_command_button.isEnabled() is False

    serial_service._connected = True
    window._update_connection_state()

    assert window.manual_command_input.isEnabled() is True
    assert window.manual_command_button.isEnabled() is False

    window.manual_command_input.setText("help")

    assert window.manual_command_button.isEnabled() is True


def test_send_manual_command_logs_transmit_and_response(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"help": "Available commands:\nprintBuildInfo\n"},
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window.manual_command_input.setText("help")
    window.send_manual_command()

    assert serial_service.request_calls == ["help"]
    assert window.manual_command_input.text() == ""
    assert window.feedback_log.toPlainText().splitlines()[-3:] == [
        "TX > help",
        "RX < Available commands:",
        "RX < printBuildInfo",
    ]


def test_send_manual_command_prompts_for_connection_when_disconnected(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(connected=False)
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    messages: list[tuple[str, str]] = []

    def fake_information(parent, title, text):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)

    window.manual_command_input.setText("help")
    window.send_manual_command()

    assert serial_service.request_calls == []
    assert messages == [("Connect first", "Connect to the controller before sending manual commands.")]


def test_support_export_button_requires_connection(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(connected=False)
    export_service = FakeSupportExportService()
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
        support_export_service=export_service,
    )
    qtbot.addWidget(window)

    messages: list[tuple[str, str]] = []

    def fake_information(parent, title, text):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)

    window.export_support_file()

    assert export_service.calls == []
    assert messages == [("Connect first", "Connect to the controller before exporting a support file.")]


def test_support_export_saves_json_report(qtbot, monkeypatch, tmp_path: Path) -> None:
    serial_service = FakeSerialService(connected=True)
    export_service = FakeSupportExportService()
    release_service = FakeFirmwareReleaseService()
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False, firmware_directory=tmp_path),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
        firmware_release_service=release_service,
        support_export_service=export_service,
    )
    qtbot.addWidget(window)

    target_path = tmp_path / "support.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_path), "JSON files (*.json)"))
    info_messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda parent, title, text: info_messages.append((title, text)) or QMessageBox.StandardButton.Ok,
    )

    window.feedback_log.setPlainText("Line 1\nLine 2\n")
    window.firmware_path_input.setText(str(tmp_path / "flash_bundle.zip"))
    window.export_support_file()

    assert len(export_service.calls) == 1
    call = export_service.calls[0]
    assert call["output_path"] == target_path
    assert call["app_version"] == window.settings.app_version
    assert call["selected_port"] == "COM11"
    assert call["activity_log_lines"] == ("Line 1", "Line 2")
    assert call["firmware_release_service"] is release_service
    assert call["selected_firmware_path"] == str(tmp_path / "flash_bundle.zip")
    assert target_path.read_text(encoding="utf-8") == '{"ok": true}'
    assert info_messages == [("Support export", f"Saved support report to:\n{target_path}")]


def test_main_window_matches_firmware_action_button_widths_and_flash_accent(qtbot) -> None:
    settings = AppSettings(auto_check_latest_firmware_on_startup=False)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    assert window.flash_button.property("accent") is True
    assert window.flash_button.minimumWidth() == window.download_latest_firmware_button.minimumWidth()


def test_flash_success_reconnects_immediately(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(request_responses={"help": "Available commands:\n"})
    firmware_service = FakeFirmwareService()
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=firmware_service,
    )
    qtbot.addWidget(window)

    window.port_combo.clear()
    window.port_combo.addItem("COM11 - Test", "COM11")
    window.port_combo.setEnabled(True)
    window.firmware_path_input.setText(str((Path.cwd() / "firmware" / "flash_bundle.zip").resolve()))

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    info_messages: list[str] = []

    def fake_information(parent, title, text):
        info_messages.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(window, "_refresh_build_info", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_controller_state", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_external_expander", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_temperature", lambda **kwargs: None)

    window.flash_firmware()

    assert serial_service.disconnect_calls == 1
    assert firmware_service.calls == [("COM11", Path(window.firmware_path_input.text()))]
    assert info_messages == ["Flashed test bundle to COM11."]
    assert serial_service.connect_calls == ["COM11"]
    assert serial_service.is_connected is True
    assert "Reconnected to COM11 after firmware flash" in window.controller_details_label.text()


def test_flash_without_controller_connection_reconnects_immediately(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(
        port_name="COM7",
        connected=False,
        available_ports=[SerialPortInfo(device="COM7", description="USB Serial Device")],
        request_responses={"help": "Available commands:\n"},
    )
    firmware_service = FakeFirmwareService()
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=firmware_service,
    )
    qtbot.addWidget(window)

    assert window.port_combo.currentData() == "COM7"
    assert window.firmware_group.isEnabled() is True
    assert window.status_label.text() == "Ready to connect or flash on COM7"

    window.firmware_path_input.setText(str((Path.cwd() / "firmware" / "flash_bundle.zip").resolve()))

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    info_messages: list[str] = []

    def fake_information(parent, title, text):
        info_messages.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(window, "_refresh_build_info", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_controller_state", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_external_expander", lambda **kwargs: None)
    monkeypatch.setattr(window, "_refresh_temperature", lambda **kwargs: None)

    window.flash_firmware()

    assert serial_service.disconnect_calls == 0
    assert firmware_service.calls == [("COM7", Path(window.firmware_path_input.text()))]
    assert info_messages == ["Flashed test bundle to COM7."]
    assert serial_service.connect_calls == ["COM7"]
    assert serial_service.is_connected is True
    assert "Reconnected to COM7 after firmware flash" in window.controller_details_label.text()


def test_connect_rejects_device_that_does_not_answer_like_controller(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(
        port_name="COM7",
        connected=False,
        available_ports=[SerialPortInfo(device="COM7", description="USB Serial Device")],
        request_responses={"help": ""},
    )
    window = MainWindow(
        settings=AppSettings(auto_check_latest_firmware_on_startup=False),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    critical_messages: list[tuple[str, str]] = []

    def fake_critical(parent, title, text):
        critical_messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", fake_critical)

    window.toggle_connection()

    assert serial_service.connect_calls == ["COM7"]
    assert serial_service.disconnect_calls == 1
    assert serial_service.is_connected is False
    assert window.sections_group.isEnabled() is False
    assert window.status_label.text() == "Ready to connect or flash on COM7"
    assert "still flash firmware to this port" in window.controller_details_label.text()
    assert critical_messages == [
        (
            "Connection failed",
            "COM7 opened, but the device did not answer the controller probe. "
            "It may be an unflashed ESP32. You can still flash firmware to this port.",
        )
    ]



def test_direct_controls_button_is_disabled_in_bench_mode(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"getControllerStatus": "[66] Controller status: BENCH MODE\n"},
    )
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_controller_state()

    assert window.controller_state_value.text() == "BENCH MODE"
    assert window.section_buttons["direct_controls"].isEnabled() is False


def test_direct_controls_dialog_is_blocked_in_bench_mode(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"getControllerStatus": "[66] Controller status: BENCH MODE\n"},
    )
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)
    window._refresh_controller_state()

    messages: list[tuple[str, str]] = []

    def fake_information(parent, title, text):
        messages.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)

    opened = {"value": False}

    class DummyDirectControlsDialog:
        def __init__(self, *args, **kwargs) -> None:
            opened["value"] = True

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(main_window_module, "DirectControlsDialog", DummyDirectControlsDialog)

    direct_controls_section = next(
        section for section in SECTION_DEFINITIONS if section.section_id == "direct_controls"
    )
    window.open_section_dialog(direct_controls_section)

    assert opened["value"] is False
    assert messages == [
        (
            "Direct controls unavailable",
            "Direct controls cannot be opened while the controller is in bench mode.",
        )
    ]


def test_refresh_temperature_updates_header_card_from_read_temperature(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"readTemperature": "[734828] Temperature: 22.50 C\n"},
    )
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_temperature()

    assert window.temperature_value.text() == "22.50 C"
    assert "Temperature: 22.50 C" in window.temperature_value.toolTip()


def test_refresh_temperature_marks_unavailable_when_not_reported(qtbot) -> None:
    serial_service = FakeSerialService(
        connected=True,
        request_responses={"readTemperature": "[734842] Battery voltage: 12.06 V\n"},
    )
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
    )
    qtbot.addWidget(window)

    window._refresh_temperature()

    assert window.temperature_value.text() == "Unavailable"
    assert "unexpected" in window.temperature_value.toolTip().lower()


def test_refresh_latest_firmware_updates_status_label(qtbot, tmp_path: Path) -> None:
    release_service = FakeFirmwareReleaseService()
    window = MainWindow(
        settings=AppSettings(firmware_directory=tmp_path),
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
        firmware_release_service=release_service,
    )
    qtbot.addWidget(window)

    window.refresh_latest_firmware()

    assert release_service.fetch_calls == 1
    assert window.latest_firmware_status_label.text() == "v1.0.9 - Published 2026-03-15"


def test_download_latest_firmware_populates_flash_bundle_path(qtbot, tmp_path: Path) -> None:
    release_service = FakeFirmwareReleaseService()
    serial_service = FakeSerialService(
        connected=False,
        available_ports=[SerialPortInfo(device="COM7", description="USB Serial Device")],
    )
    window = MainWindow(
        settings=AppSettings(firmware_directory=tmp_path),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
        firmware_release_service=release_service,
    )
    qtbot.addWidget(window)

    window.download_latest_firmware()

    expected_path = (tmp_path / release_service.release.asset_name).resolve()
    assert release_service.fetch_calls == 1
    assert release_service.download_calls == [(release_service.release, tmp_path)]
    assert Path(window.firmware_path_input.text()) == expected_path
    assert "v1.0.9" in window.controller_details_label.text()


def test_main_window_auto_checks_latest_firmware_on_first_show(qtbot, monkeypatch, tmp_path: Path) -> None:
    release_service = FakeFirmwareReleaseService()
    window = MainWindow(
        settings=AppSettings(firmware_directory=tmp_path),
        serial_service=FakeSerialService(connected=False),
        firmware_service=FakeFirmwareService(),
        firmware_release_service=release_service,
    )
    qtbot.addWidget(window)

    scheduled: dict[str, object] = {}

    def fake_single_shot(delay_ms: int, callback) -> None:
        scheduled["delay_ms"] = delay_ms
        scheduled["callback"] = callback

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(fake_single_shot))

    window.showEvent(QShowEvent())

    assert scheduled["delay_ms"] == 0
    callback = scheduled["callback"]
    assert callable(callback)
    callback()
    qtbot.waitUntil(lambda: release_service.fetch_calls == 1, timeout=1000)
    window._check_startup_firmware_fetch()

    assert release_service.fetch_calls == 1
    assert window.latest_firmware_status_label.text() == "v1.0.9 - Published 2026-03-15"

    window.showEvent(QShowEvent())
    assert release_service.fetch_calls == 1

