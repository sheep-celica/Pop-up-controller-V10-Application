from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QMessageBox

from popup_controller.manufacture_options import BOARD_REVISION_OPTIONS, CAR_MODEL_OPTIONS
from popup_controller.services.voltage_calibration_service import VoltageMeasurementPoint
from popup_controller.ui import service_dialog as service_dialog_module
from popup_controller.ui.service_dialog import ServiceDialog
from popup_controller.ui.voltage_calibration_dialog import (
    AddVoltageMeasurementDialog,
    VoltageCalibrationDialog,
)


READ_BATTERY_RESPONSE = """[275168] Battery voltage [1/5]: 13.45 V
[277180] Battery voltage average (5 readings): 13.45 V
"""


class FakeSerialService:
    def __init__(self, responses: dict[str, str] | None = None, connected: bool = True) -> None:
        self._responses = dict(responses or {})
        self._connected = connected
        self.commands: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def request_text(self, command: str, **kwargs) -> str:
        self.commands.append(command)
        return self._responses.get(command, "")


def test_add_voltage_measurement_dialog_reads_controller_voltage(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService({"readBatteryVoltage": READ_BATTERY_RESPONSE})
    dialog = AddVoltageMeasurementDialog(serial_service)
    qtbot.addWidget(dialog)

    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    dialog.measured_voltage_input.setText("13.82")
    dialog.add_measurement_point()

    assert serial_service.commands == ["readBatteryVoltage"]
    assert dialog.measurement_point == VoltageMeasurementPoint(measured_voltage_v=13.82, controller_voltage_v=13.45)


def test_voltage_calibration_dialog_calculates_and_saves_constants(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService(
        {"writeBatteryVoltageCalibration 1.100000 -0.800000": "[10] Battery voltage calibration updated."}
    )
    dialog = VoltageCalibrationDialog(serial_service)
    qtbot.addWidget(dialog)

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    dialog._append_measurement_point(VoltageMeasurementPoint(measured_voltage_v=12.4, controller_voltage_v=12.0))
    dialog._append_measurement_point(VoltageMeasurementPoint(measured_voltage_v=13.5, controller_voltage_v=13.0))
    dialog._append_measurement_point(VoltageMeasurementPoint(measured_voltage_v=14.6, controller_voltage_v=14.0))

    dialog.calculate_constants()

    assert dialog.calculated_a_value.text() == "1.100000"
    assert dialog.calculated_b_value.text() == "-0.800000"
    assert dialog.save_button.isEnabled() is True

    dialog.save_calibration()

    assert serial_service.commands == ["writeBatteryVoltageCalibration 1.100000 -0.800000"]
    assert "updated" in dialog.status_label.text().lower()


def test_service_dialog_defaults_manufacture_date_to_today(qtbot) -> None:
    serial_service = FakeSerialService()
    dialog = ServiceDialog(serial_service)
    qtbot.addWidget(dialog)

    assert dialog.manufacture_date_input.text() == QDate.currentDate().toString("yyyy-MM-dd")
    assert dialog.manufacture_date_input.isReadOnly() is True
    assert dialog.pick_manufacture_date_button.text() == "Pick date"


def test_service_dialog_uses_configured_dropdowns_for_revision_and_car_model(qtbot) -> None:
    serial_service = FakeSerialService()
    dialog = ServiceDialog(serial_service)
    qtbot.addWidget(dialog)

    dialog.serial_number_input.setText("SN 123")

    assert dialog.serial_number_input.hasAcceptableInput() is False
    assert dialog.board_serial_input.validator() is not None
    assert dialog.board_revision_combo.count() == len(BOARD_REVISION_OPTIONS)
    assert [dialog.board_revision_combo.itemText(index) for index in range(dialog.board_revision_combo.count())] == list(
        BOARD_REVISION_OPTIONS
    )
    assert dialog.board_revision_combo.currentIndex() == -1
    assert dialog.car_model_combo.count() == len(CAR_MODEL_OPTIONS)
    assert [dialog.car_model_combo.itemText(index) for index in range(dialog.car_model_combo.count())] == list(
        CAR_MODEL_OPTIONS
    )
    assert dialog.car_model_combo.currentIndex() == -1


def test_service_dialog_rejects_spaces_in_manufacture_date_value(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService()
    dialog = ServiceDialog(serial_service)
    qtbot.addWidget(dialog)

    warnings: list[tuple[str, str]] = []

    def fake_warning(parent, title, text):
        warnings.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", fake_warning)
    monkeypatch.setattr(dialog, "_submit_service_command", lambda *args, **kwargs: True)

    dialog.serial_number_input.setText("SN123")
    dialog.board_serial_input.setText("BOARD456")
    dialog.board_revision_combo.setCurrentText("Revision_C")
    dialog.manufacture_date_input.setText("2026 03 21")
    dialog.car_model_combo.setCurrentText("T18_Toyota_Celica")

    dialog.write_manufacture_data()

    assert warnings == [("Manufacture data", "Manufacture Date must be a single token without spaces.")]


def test_service_dialog_writes_manufacture_data_with_selected_date(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService()
    dialog = ServiceDialog(serial_service)
    qtbot.addWidget(dialog)

    captured: dict[str, str] = {}

    def fake_submit(command: str, busy_message: str, error_title: str, success_message: str) -> bool:
        captured["command"] = command
        captured["busy_message"] = busy_message
        captured["error_title"] = error_title
        captured["success_message"] = success_message
        return True

    monkeypatch.setattr(dialog, "_submit_service_command", fake_submit)

    dialog.serial_number_input.setText("SN123")
    dialog.board_serial_input.setText("BOARD456")
    dialog.board_revision_combo.setCurrentText("Revision_C")
    dialog.manufacture_date_input.setText("2026-03-21")
    dialog.car_model_combo.setCurrentText("T18_Toyota_Celica")

    dialog.write_manufacture_data()

    assert captured == {
        "command": "writeManufactureData 2026-03-21 SN123 BOARD456 Revision_C T18_Toyota_Celica",
        "busy_message": "Writing manufacture data...",
        "error_title": "Write manufacture data failed",
        "success_message": "Controller manufacture data write command accepted.",
    }


def test_service_dialog_opens_voltage_calibration_dialog(qtbot, monkeypatch) -> None:
    serial_service = FakeSerialService()
    dialog = ServiceDialog(serial_service)
    qtbot.addWidget(dialog)

    opened = {"value": False}

    class DummyVoltageCalibrationDialog:
        def __init__(self, serial_service_arg, parent=None) -> None:
            assert serial_service_arg is serial_service
            assert parent is dialog
            opened["value"] = True

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(service_dialog_module, "VoltageCalibrationDialog", DummyVoltageCalibrationDialog)

    dialog.open_voltage_calibration_dialog()

    assert opened["value"] is True
