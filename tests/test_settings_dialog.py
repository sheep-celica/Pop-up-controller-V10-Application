from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from popup_controller.config import AppSettings
from popup_controller.ui import main_window as main_window_module
from popup_controller.ui import settings_dialog as settings_dialog_module
from popup_controller.ui.main_window import MainWindow
from popup_controller.ui.sections import SECTION_DEFINITIONS
from popup_controller.ui.settings_dialog import SETTINGS_SECTION_DEFINITIONS, SettingsDialog


SETTINGS_RESPONSE = """[2185281] Battery voltage calibration constants: a=1.001585, b=0.097071
[2185291] ALLOW_SLEEPY_EYE_MODE_WITH_HEADLIGHTS=TRUE
[2185291] Idle power-off threshold: 86400 s.
[2185303] Temperature: 22.50 C
[2185306] Battery voltage: 2.87 V
"""


REMOTE_INPUTS_WITH_HEADLIGHTS_RESPONSE = """[283268] ALLOW_REMOTE_INPUTS_WITH_HEADLIGHTS=FALSE
"""


class FakeSerialService:
    def __init__(self, connected: bool = True, request_responses: dict[str, str] | None = None) -> None:
        self._connected = connected
        self.baudrate = 115200
        self._request_responses = dict(request_responses or {})
        self.request_calls: list[str] = []

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
        self.request_calls.append(command)
        return self._request_responses.get(command, "")

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


def test_settings_dialog_organizes_settings_into_clickable_sections(qtbot) -> None:
    dialog = SettingsDialog(serial_service=FakeSerialService())
    qtbot.addWidget(dialog)

    assert dialog.current_settings_section_id == "safety"
    assert dialog.section_stack.currentWidget() is dialog.settings_section_pages["safety"]
    assert set(dialog.settings_section_buttons) == {section_id for section_id, _title, _summary in SETTINGS_SECTION_DEFINITIONS}
    assert dialog.sleepy_eye_group.parentWidget() is dialog.settings_section_pages["safety"]
    assert dialog.safety_remote_inputs_with_light_switch_group.parentWidget() is dialog.settings_section_pages["safety"]
    assert dialog.remote_inputs_with_light_switch_group.parentWidget() is dialog.settings_section_pages["remote"]
    assert dialog.timing_group.parentWidget() is dialog.settings_section_pages["popup"]

    dialog._set_busy(False)
    dialog.settings_section_buttons["remote"].click()

    assert dialog.current_settings_section_id == "remote"
    assert dialog.section_stack.currentWidget() is dialog.settings_section_pages["remote"]
    assert dialog.settings_section_buttons["remote"].property("accent") is True
    assert dialog.settings_section_buttons["safety"].property("accent") is False


def test_settings_dialog_syncs_remote_inputs_with_light_switch_between_sections(qtbot) -> None:
    dialog = SettingsDialog(serial_service=FakeSerialService())
    qtbot.addWidget(dialog)

    dialog.remote_inputs_with_headlights_combo.setCurrentText("FALSE")

    assert dialog.safety_remote_inputs_with_headlights_combo.currentText() == "FALSE"

    dialog.safety_remote_inputs_with_headlights_combo.setCurrentText("TRUE")

    assert dialog.remote_inputs_with_headlights_combo.currentText() == "TRUE"


def test_settings_dialog_loads_sensing_delay_setting(qtbot) -> None:
    serial_service = FakeSerialService(
        request_responses={
            "printEverything": SETTINGS_RESPONSE,
            "getIdleTimeToPowerOff": "[51018] 86400\n",
            "printPopUpMinStatePersistMs": "[273808] MIN_STATE_PERSIST_MS=5\n",
            "printRemoteInputPins": "[274258] REMOTE_INPUT_PINS=4 3 2 1\n",
            "printPopUpSensingDelayUs": "[51018] POP_UP_SENSING_DELAY_US=1000\n",
            "printRemoteInputsWithHeadlights": REMOTE_INPUTS_WITH_HEADLIGHTS_RESPONSE,
        }
    )
    dialog = SettingsDialog(serial_service=serial_service)
    qtbot.addWidget(dialog)

    dialog.load_settings()

    assert "printPopUpSensingDelayUs" in serial_service.request_calls
    assert "printRemoteInputsWithHeadlights" in serial_service.request_calls
    assert dialog.sensing_delay_value.text() == "1,000 us"
    assert dialog.sensing_delay_spin.value() == 1000
    assert dialog.remote_inputs_with_headlights_value.text() == "FALSE"
    assert dialog.safety_remote_inputs_with_headlights_value.text() == "FALSE"
    assert dialog.remote_inputs_with_headlights_combo.currentText() == "FALSE"
    assert dialog.safety_remote_inputs_with_headlights_combo.currentText() == "FALSE"


def test_settings_dialog_updates_sensing_delay_with_expected_command(qtbot, monkeypatch) -> None:
    dialog = SettingsDialog(serial_service=FakeSerialService())
    qtbot.addWidget(dialog)

    captured: dict[str, str] = {}

    def fake_submit(command: str, busy_message: str, error_title: str) -> bool:
        captured["command"] = command
        captured["busy_message"] = busy_message
        captured["error_title"] = error_title
        return True

    monkeypatch.setattr(dialog, "_submit_update_command", fake_submit)
    dialog.sensing_delay_spin.setValue(1234)

    dialog.update_sensing_delay()

    assert captured == {
        "command": "writePopUpSensingDelayUs 1234",
        "busy_message": "Updating pop-up sensing delay...",
        "error_title": "Pop-up sensing delay update failed",
    }


def test_settings_dialog_updates_remote_inputs_with_light_switch_from_safety_section(qtbot, monkeypatch) -> None:
    dialog = SettingsDialog(serial_service=FakeSerialService())
    qtbot.addWidget(dialog)

    captured: dict[str, str] = {}

    def fake_submit(command: str, busy_message: str, error_title: str) -> bool:
        captured["command"] = command
        captured["busy_message"] = busy_message
        captured["error_title"] = error_title
        return True

    monkeypatch.setattr(dialog, "_submit_update_command", fake_submit)
    dialog.safety_remote_inputs_with_headlights_combo.setCurrentText("FALSE")

    dialog.update_remote_inputs_with_headlights_setting("safety_remote_inputs_with_headlights_combo")

    assert dialog.remote_inputs_with_headlights_combo.currentText() == "FALSE"
    assert captured == {
        "command": "writeRemoteInputsWithHeadlights false",
        "busy_message": "Updating remote inputs with light-switch setting...",
        "error_title": "Remote inputs with light-switch update failed",
    }


def test_settings_dialog_updates_remote_inputs_with_light_switch_with_expected_command(qtbot, monkeypatch) -> None:
    dialog = SettingsDialog(serial_service=FakeSerialService())
    qtbot.addWidget(dialog)

    captured: dict[str, str] = {}

    def fake_submit(command: str, busy_message: str, error_title: str) -> bool:
        captured["command"] = command
        captured["busy_message"] = busy_message
        captured["error_title"] = error_title
        return True

    monkeypatch.setattr(dialog, "_submit_update_command", fake_submit)
    dialog.remote_inputs_with_headlights_combo.setCurrentText("TRUE")

    dialog.update_remote_inputs_with_headlights_setting()

    assert captured == {
        "command": "writeRemoteInputsWithHeadlights true",
        "busy_message": "Updating remote inputs with light-switch setting...",
        "error_title": "Remote inputs with light-switch update failed",
    }
