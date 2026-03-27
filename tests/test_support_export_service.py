from __future__ import annotations

import json
from pathlib import Path

from popup_controller.services.firmware_release_service import FirmwareReleaseError, FirmwareReleaseInfo
from popup_controller.services.serial_service import SerialConnectionError
from popup_controller.services.support_export_service import SupportExportService


class FakeSerialService:
    def __init__(self, request_responses: dict[str, str] | None = None, failures: set[str] | None = None) -> None:
        self._request_responses = dict(request_responses or {})
        self._failures = set(failures or set())
        self._port_name = "COM11"

    @property
    def is_connected(self) -> bool:
        return True

    @property
    def port_name(self) -> str | None:
        return self._port_name

    def request_text(self, command: str, **kwargs) -> str:
        if command in self._failures:
            raise SerialConnectionError(f"{command} failed for test")
        return self._request_responses.get(command, "")


class FakeFirmwareReleaseService:
    def fetch_latest_release(self) -> FirmwareReleaseInfo:
        return FirmwareReleaseInfo(
            version="1.0.9",
            release_name="Firmware version 1.0.9",
            tag_name="v1.0.9",
            asset_name="firmware.zip",
            download_url="https://example.invalid/firmware.zip",
            asset_size_bytes=123,
            asset_sha256="abc123",
            published_at="2026-03-15T17:57:58Z",
            updated_at="2026-03-17T20:45:30Z",
            html_url="https://example.invalid/releases/v1.0.9",
        )


class FailingFirmwareReleaseService:
    def fetch_latest_release(self) -> FirmwareReleaseInfo:
        raise FirmwareReleaseError("GitHub lookup failed for test")


def test_support_export_service_writes_expected_sections(tmp_path: Path) -> None:
    serial_service = FakeSerialService(
        request_responses={
            "printBuildInfo": "FW_VERSION=1.0.10\nBUILD_TIMESTAMP=2026-03-15T09:20:11Z\n",
            "getControllerStatus": "Controller status: RUNNING\n",
            "getExternalExpander": "Connected\n",
            "readTemperature": "Temperature: 24.50 C\n",
            "printEverything": (
                "Battery voltage calibration constants: a=0.123456, b=7.890123\n"
                "ALLOW_SLEEPY_EYE_MODE_WITH_HEADLIGHTS=TRUE\n"
                "Battery voltage: 12.06 V\n"
                "Serial Number: SN-123\n"
                "Board Serial: BRD-42\n"
                "Board Revision: REV-C\n"
                "Car Model: Celica\n"
                "Manufacture Date: 2026-02-24\n"
                "Initial FW Version: 1.0.8\n"
                "---- RH Pop-up Timing Calibration ----\n"
                "RH line 1\n"
                "---- LH Pop-up Timing Calibration ----\n"
                "LH line 1\n"
            ),
            "getIdleTimeToPowerOff": "86400\n",
            "printPopUpMinStatePersistMs": "750\n",
            "printRemoteInputPins": "Remote input pins: 1 2 3 4\n",
            "printPopUpSensingDelayUs": "450\n",
            "printRemoteInputsWithHeadlights": "ALLOW_REMOTE_INPUTS_WITH_HEADLIGHTS=FALSE\n",
            "printStatisticalData": (
                "Boot count: 12\n"
                "Total runtime: 86400 s (1.0 days)\n"
                "RH cycles / errors / move: 10 / 1 / 150 ms\n"
                "LH cycles / errors / move: 11 / 2 / 155 ms\n"
                "Buttons RH/LH/BH: 1 / 2 / 3\n"
                "Remote 1/2/3/4: 4 / 5 / 6 / 7\n"
            ),
            "printErrors": (
                "---- Error Log ----\n"
                "Boot=3 Code=RH_FAULT Vbat=12050 mV Temp=24.0 C\n"
                "Boot=4 Code=CAN_FAULT Vbat=11980 mV Temp=23.5 C\n"
                "-----\n"
            ),
        }
    )
    service = SupportExportService()
    output_path = tmp_path / "support-report.json"

    service.export_to_file(
        output_path=output_path,
        serial_service=serial_service,
        app_version="1.0.12",
        selected_port="COM11",
        activity_log_lines=("Connected to COM11", "Build info loaded"),
        firmware_release_service=FakeFirmwareReleaseService(),
        selected_firmware_path=r"C:\firmware\flash_bundle.zip",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["connection"]["connected"] is True
    assert payload["controller_summary"]["firmware_version"] == "1.0.10"
    assert payload["settings"]["parsed"]["idle_power_off_days"] == 1.0
    assert payload["settings"]["parsed"]["remote_input_mapping"] == [1, 2, 3, 4]
    assert payload["statistics"]["parsed"]["rh_side"]["cycles"] == 10
    assert payload["errors"]["parsed"]["headlight_entries"][0]["error_code"] == "RH_FAULT"
    assert payload["errors"]["parsed"]["module_entries"][0]["error_code"] == "CAN_FAULT"
    assert payload["manufacture"]["parsed"]["serial_number"]["value"] == "SN-123"
    assert payload["firmware_release"]["parsed"]["version"] == "1.0.9"
    assert payload["activity_log_tail"] == ["Connected to COM11", "Build info loaded"]
    assert payload["summary"]["failed_commands"] == 0


def test_support_export_service_records_partial_failures(tmp_path: Path) -> None:
    serial_service = FakeSerialService(
        request_responses={
            "printBuildInfo": "FW_VERSION=1.0.10\n",
            "printEverything": "Serial Number: SN-123\n",
            "printErrors": "no stored errors\n",
        },
        failures={"printStatisticalData", "readTemperature"},
    )
    service = SupportExportService()
    output_path = tmp_path / "support-report.json"

    service.export_to_file(
        output_path=output_path,
        serial_service=serial_service,
        app_version="1.0.12",
        selected_port="COM11",
        firmware_release_service=FailingFirmwareReleaseService(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["commands"]["printStatisticalData"]["status"] == "serial_error"
    assert payload["commands"]["readTemperature"]["status"] == "serial_error"
    assert payload["firmware_release"]["parsed"] is None
    assert payload["firmware_release"]["error"] == "GitHub lookup failed for test"
    assert payload["summary"]["overall_status"] == "partial"
