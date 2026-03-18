from __future__ import annotations

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QScrollArea

from popup_controller.ui.direct_controls_dialog import DirectControlsDialog
from popup_controller.ui.errors_dialog import ErrorsDialog
from popup_controller.ui.manufacture_dialog import ManufactureDialog
from popup_controller.ui.remote_mapping_reference_dialog import RemoteMappingReferenceDialog
from popup_controller.ui.section_dialog import SectionDialog
from popup_controller.ui.sections import SECTION_DEFINITIONS
from popup_controller.ui.service_dialog import ServiceDialog
from popup_controller.ui.settings_dialog import SettingsDialog
from popup_controller.ui.statistics_dialog import StatisticsDialog
from popup_controller.ui.voltage_calibration_dialog import AddVoltageMeasurementDialog, VoltageCalibrationDialog


class FakeSerialService:
    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self.baudrate = 115200

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str | None:
        return "COM11" if self._connected else None

    def request_text(self, command: str, **kwargs) -> str:
        return ""

    def available_ports(self):
        return []

    def read_available(self):
        return []

    def connect(self, port: str) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False



def test_all_dialogs_expose_scroll_areas(qtbot, tmp_path) -> None:
    image_path = tmp_path / "remote_mapping.png"
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(0xFF336699)
    assert image.save(str(image_path)) is True

    serial_service = FakeSerialService()
    dialogs = [
        DirectControlsDialog(serial_service),
        ErrorsDialog(serial_service),
        ManufactureDialog(serial_service),
        RemoteMappingReferenceDialog(image_path),
        SectionDialog(SECTION_DEFINITIONS[0]),
        ServiceDialog(serial_service),
        SettingsDialog(serial_service, reference_image_path=image_path),
        StatisticsDialog(serial_service),
        AddVoltageMeasurementDialog(serial_service),
        VoltageCalibrationDialog(serial_service),
    ]

    for dialog in dialogs:
        qtbot.addWidget(dialog)
        assert hasattr(dialog, "scroll_area"), type(dialog).__name__
        assert isinstance(dialog.scroll_area, QScrollArea), type(dialog).__name__



def test_large_dialogs_scroll_when_resized_short(qtbot, tmp_path) -> None:
    image_path = tmp_path / "remote_mapping.png"
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(0xFF336699)
    assert image.save(str(image_path)) is True

    serial_service = FakeSerialService()
    dialogs = [
        SettingsDialog(serial_service, reference_image_path=image_path),
        StatisticsDialog(serial_service),
        ErrorsDialog(serial_service),
        ManufactureDialog(serial_service),
        ServiceDialog(serial_service),
        VoltageCalibrationDialog(serial_service),
    ]

    for dialog in dialogs:
        qtbot.addWidget(dialog)
        dialog.resize(640, 360)
        dialog.show()
        qtbot.wait(50)
        assert dialog.scroll_area.verticalScrollBar().maximum() > 0, type(dialog).__name__
