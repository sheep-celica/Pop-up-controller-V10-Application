from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

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
