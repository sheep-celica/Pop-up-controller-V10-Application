from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from popup_controller.config import AppSettings
from popup_controller.ui import main_window as main_window_module
from popup_controller.ui import settings_dialog as settings_dialog_module
from popup_controller.ui.main_window import MainWindow
from popup_controller.ui.sections import SECTION_DEFINITIONS
from popup_controller.ui.settings_dialog import SettingsDialog


class FakeSerialService:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.baudrate = 115200

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str | None:
        return "COM11" if self._connected else None

    def available_ports(self):
        return []

    def read_available(self):
        return []

    def request_text(self, command: str, **kwargs) -> str:
        return ""

    def connect(self, port: str) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False


def test_settings_dialog_opens_remote_mapping_reference_dialog(qtbot, monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "remote_mapping.png"
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(0xFF336699)
    assert image.save(str(image_path)) is True

    dialog = SettingsDialog(
        serial_service=FakeSerialService(),
        reference_image_path=image_path,
    )
    qtbot.addWidget(dialog)

    opened: dict[str, object] = {}

    class DummyReferenceDialog:
        def __init__(self, image_path_arg: Path, parent=None) -> None:
            opened["image_path"] = image_path_arg
            opened["parent"] = parent

        def exec(self) -> int:
            opened["executed"] = True
            return 0

    monkeypatch.setattr(settings_dialog_module, "RemoteMappingReferenceDialog", DummyReferenceDialog)

    dialog.show_remote_mapping_reference()

    assert opened == {
        "image_path": image_path,
        "parent": dialog,
        "executed": True,
    }


def test_settings_dialog_warns_when_remote_mapping_reference_is_missing(qtbot, monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "missing_remote_mapping.png"
    dialog = SettingsDialog(
        serial_service=FakeSerialService(),
        reference_image_path=image_path,
    )
    qtbot.addWidget(dialog)

    warnings: list[tuple[str, str]] = []

    def fake_warning(parent, title, text):
        warnings.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", fake_warning)

    dialog.show_remote_mapping_reference()

    assert warnings == [
        (
            "Remote mapping reference",
            f"Reference image not found: {image_path}",
        )
    ]


def test_main_window_passes_remote_mapping_reference_path_to_settings_dialog(qtbot, monkeypatch, tmp_path) -> None:
    reference_image_path = tmp_path / "remote_mapping.png"
    settings = AppSettings(remote_mapping_reference_image_path=reference_image_path)
    window = MainWindow(
        settings=settings,
        serial_service=FakeSerialService(connected=True),
    )
    qtbot.addWidget(window)

    captured: dict[str, object] = {}

    class DummySettingsDialog:
        def __init__(self, serial_service, parent=None, reference_image_path=None) -> None:
            captured["serial_service"] = serial_service
            captured["parent"] = parent
            captured["reference_image_path"] = reference_image_path

        def exec(self) -> int:
            captured["executed"] = True
            return 0

    monkeypatch.setattr(main_window_module, "SettingsDialog", DummySettingsDialog)

    settings_section = next(section for section in SECTION_DEFINITIONS if section.section_id == "settings")
    window.open_section_dialog(settings_section)

    assert captured == {
        "serial_service": window.serial_service,
        "parent": window,
        "reference_image_path": reference_image_path,
        "executed": True,
    }
