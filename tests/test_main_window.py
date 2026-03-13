from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from popup_controller.config import AppSettings
from popup_controller.services.firmware_service import FlashResult
from popup_controller.ui.main_window import MainWindow


class FakeSerialService:
    def __init__(self, port_name: str = "COM11") -> None:
        self.baudrate = 115200
        self.timeout_seconds = 0.1
        self._connected = True
        self._port_name = port_name
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
        return []

    def read_available(self):
        return []


class FakeFirmwareService:
    def flash_firmware(self, port: str, firmware_path: Path) -> FlashResult:
        return FlashResult(True, f"Flashed test bundle to {port}.")


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


def test_flash_success_schedules_delayed_reconnect(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService()
    window = MainWindow(
        settings=AppSettings(),
        serial_service=serial_service,
        firmware_service=FakeFirmwareService(),
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

    scheduled: dict[str, object] = {}

    def fake_single_shot(delay_ms: int, callback) -> None:
        scheduled["delay_ms"] = delay_ms
        scheduled["callback"] = callback

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(fake_single_shot))

    window.flash_firmware()

    assert serial_service.disconnect_calls == 1
    assert scheduled["delay_ms"] == 3000

    callback = scheduled["callback"]
    assert callable(callback)
    callback()

    assert serial_service.connect_calls == ["COM11"]
    assert serial_service.is_connected is True
    assert "Reconnected to COM11 after firmware flash" in window.controller_details_label.text()
