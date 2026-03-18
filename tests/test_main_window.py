from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QMessageBox, QScrollArea

from popup_controller.config import AppSettings
from popup_controller.services.firmware_service import FlashResult
from popup_controller.services.firmware_release_service import FirmwareDownloadResult, FirmwareReleaseInfo
from popup_controller.services.serial_service import SerialPortInfo
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

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    def available_ports(self):
        return list(self._available_ports)

    def read_available(self):
        return []

    def request_text(self, command: str, **kwargs) -> str:
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

    assert isinstance(window.centralWidget(), QScrollArea)
    assert window.central_scroll_area.verticalScrollBar().maximum() > 0


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


def test_flash_success_schedules_delayed_reconnect(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService()
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
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(window, "_refresh_build_info", lambda: None)
    monkeypatch.setattr(window, "_refresh_controller_state", lambda: None)
    monkeypatch.setattr(window, "_refresh_external_expander", lambda: None)
    monkeypatch.setattr(window, "_refresh_temperature", lambda: None)

    scheduled: dict[str, object] = {}

    def fake_single_shot(delay_ms: int, callback) -> None:
        scheduled["delay_ms"] = delay_ms
        scheduled["callback"] = callback

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(fake_single_shot))

    window.flash_firmware()

    assert serial_service.disconnect_calls == 1
    assert firmware_service.calls == [("COM11", Path(window.firmware_path_input.text()))]
    assert scheduled["delay_ms"] == 3000

    callback = scheduled["callback"]
    assert callable(callback)
    callback()

    assert serial_service.connect_calls == ["COM11"]
    assert serial_service.is_connected is True
    assert "Reconnected to COM11 after firmware flash" in window.controller_details_label.text()


def test_flash_without_controller_connection_uses_selected_serial_port(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(
        port_name="COM7",
        connected=False,
        available_ports=[SerialPortInfo(device="COM7", description="USB Serial Device")],
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
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    monkeypatch.setattr(window, "_refresh_build_info", lambda: None)
    monkeypatch.setattr(window, "_refresh_controller_state", lambda: None)
    monkeypatch.setattr(window, "_refresh_external_expander", lambda: None)
    monkeypatch.setattr(window, "_refresh_temperature", lambda: None)

    scheduled: dict[str, object] = {}

    def fake_single_shot(delay_ms: int, callback) -> None:
        scheduled["delay_ms"] = delay_ms
        scheduled["callback"] = callback

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(fake_single_shot))

    window.flash_firmware()

    assert serial_service.disconnect_calls == 0
    assert firmware_service.calls == [("COM7", Path(window.firmware_path_input.text()))]
    assert scheduled["delay_ms"] == 3000

    callback = scheduled["callback"]
    assert callable(callback)
    callback()

    assert serial_service.connect_calls == ["COM7"]
    assert serial_service.is_connected is True
    assert "Reconnected to COM7 after firmware flash" in window.controller_details_label.text()



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
    assert "v1.0.9" in window.latest_firmware_status_label.text()
    assert "pop_up_controller_v10_firmware_v_1.0.9.zip" in window.latest_firmware_status_label.text()


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

    assert release_service.fetch_calls == 1
    assert "v1.0.9" in window.latest_firmware_status_label.text()

    window.showEvent(QShowEvent())
    assert release_service.fetch_calls == 1
