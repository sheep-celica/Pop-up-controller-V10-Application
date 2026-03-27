from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

from popup_controller.services.build_info_service import parse_build_info_snapshot
from popup_controller.services.controller_status_service import parse_controller_status_snapshot
from popup_controller.services.error_service import ErrorReport, parse_stored_error_report
from popup_controller.services.external_expander_service import parse_external_expander_snapshot
from popup_controller.services.firmware_release_service import FirmwareReleaseError, FirmwareReleaseService
from popup_controller.services.manufacture_service import ManufactureField, ManufactureSnapshot, parse_manufacture_snapshot
from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.services.settings_service import SettingsSnapshot, parse_settings_snapshot
from popup_controller.services.statistics_service import StatisticsParseError, StatisticsSnapshot, parse_statistics_snapshot
from popup_controller.services.temperature_service import parse_temperature_snapshot

FULL_EXPORT_IDLE_TIMEOUT_SECONDS = 0.20
SINGLE_VALUE_IDLE_TIMEOUT_SECONDS = 0.15


class SupportExportService:
    def build_report(
        self,
        serial_service: SerialService,
        app_version: str,
        selected_port: str | None,
        activity_log_lines: Sequence[str] = (),
        firmware_release_service: FirmwareReleaseService | None = None,
        progress_callback: Callable[[], None] | None = None,
        selected_firmware_path: str | None = None,
    ) -> dict[str, object]:
        command_results = {
            "printBuildInfo": self._request_command(
                serial_service,
                "printBuildInfo",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "getControllerStatus": self._request_command(
                serial_service,
                "getControllerStatus",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "getExternalExpander": self._request_command(
                serial_service,
                "getExternalExpander",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "readTemperature": self._request_command(
                serial_service,
                "readTemperature",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printEverything": self._request_command(
                serial_service,
                "printEverything",
                idle_timeout_seconds=FULL_EXPORT_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=4.0,
                progress_callback=progress_callback,
            ),
            "getIdleTimeToPowerOff": self._request_command(
                serial_service,
                "getIdleTimeToPowerOff",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printPopUpMinStatePersistMs": self._request_command(
                serial_service,
                "printPopUpMinStatePersistMs",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printRemoteInputPins": self._request_command(
                serial_service,
                "printRemoteInputPins",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printPopUpSensingDelayUs": self._request_command(
                serial_service,
                "printPopUpSensingDelayUs",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printRemoteInputsWithHeadlights": self._request_command(
                serial_service,
                "printRemoteInputsWithHeadlights",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            ),
            "printStatisticalData": self._request_command(
                serial_service,
                "printStatisticalData",
                idle_timeout_seconds=0.6,
                max_duration_seconds=3.0,
                progress_callback=progress_callback,
            ),
            "printErrors": self._request_command(
                serial_service,
                "printErrors",
                idle_timeout_seconds=0.6,
                max_duration_seconds=3.0,
                progress_callback=progress_callback,
            ),
        }

        build_info_snapshot = parse_build_info_snapshot(self._command_text(command_results["printBuildInfo"]))
        controller_status_snapshot = parse_controller_status_snapshot(self._command_text(command_results["getControllerStatus"]))
        external_expander_snapshot = parse_external_expander_snapshot(
            self._command_text(command_results["getExternalExpander"])
        )
        temperature_snapshot = parse_temperature_snapshot(self._command_text(command_results["readTemperature"]))
        settings_section = self._build_settings_section(command_results)
        statistics_section = self._build_statistics_section(command_results["printStatisticalData"])
        errors_section = self._build_errors_section(command_results["printErrors"])
        manufacture_snapshot = parse_manufacture_snapshot(self._command_text(command_results["printEverything"]))
        firmware_release_section = self._build_firmware_release_section(firmware_release_service)

        command_count = len(command_results)
        successful_commands = sum(1 for result in command_results.values() if result["status"] == "ok")
        failed_commands = command_count - successful_commands

        return {
            "schema_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "application": {
                "app_version": app_version,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "is_frozen": bool(getattr(sys, "frozen", False)),
                "selected_firmware_path": selected_firmware_path or "",
            },
            "connection": {
                "selected_port": selected_port or "",
                "connected_port": serial_service.port_name or "",
                "connected": serial_service.is_connected,
            },
            "controller_summary": {
                "firmware_version": build_info_snapshot.firmware_version,
                "build_timestamp": build_info_snapshot.build_timestamp,
                "build_date": build_info_snapshot.build_date,
                "controller_state": controller_status_snapshot.state,
                "controller_state_status": controller_status_snapshot.status_hint,
                "external_expander_state": external_expander_snapshot.state,
                "external_expander_status": external_expander_snapshot.status_hint,
                "temperature_c": temperature_snapshot.temperature_c,
                "temperature_status": temperature_snapshot.status_hint,
            },
            "settings": settings_section,
            "statistics": statistics_section,
            "errors": errors_section,
            "manufacture": {
                "parsed": self._serialize_manufacture_snapshot(manufacture_snapshot),
                "commands": {
                    "printEverything": command_results["printEverything"],
                },
            },
            "firmware_release": firmware_release_section,
            "commands": command_results,
            "activity_log_tail": list(activity_log_lines),
            "summary": {
                "command_count": command_count,
                "successful_commands": successful_commands,
                "failed_commands": failed_commands,
                "overall_status": "partial" if failed_commands else "ok",
            },
            "collection_notes": [
                "Unavailable or unsupported values are preserved explicitly instead of being omitted.",
                "Raw command responses are included to help diagnose parser or firmware format mismatches.",
            ],
        }

    def export_to_file(
        self,
        output_path: Path,
        serial_service: SerialService,
        app_version: str,
        selected_port: str | None,
        activity_log_lines: Sequence[str] = (),
        firmware_release_service: FirmwareReleaseService | None = None,
        progress_callback: Callable[[], None] | None = None,
        selected_firmware_path: str | None = None,
    ) -> Path:
        report = self.build_report(
            serial_service=serial_service,
            app_version=app_version,
            selected_port=selected_port,
            activity_log_lines=activity_log_lines,
            firmware_release_service=firmware_release_service,
            progress_callback=progress_callback,
            selected_firmware_path=selected_firmware_path,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return output_path

    def _request_command(
        self,
        serial_service: SerialService,
        command: str,
        *,
        idle_timeout_seconds: float,
        max_duration_seconds: float,
        progress_callback: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        try:
            raw_text = serial_service.request_text(
                command,
                idle_timeout_seconds=idle_timeout_seconds,
                max_duration_seconds=max_duration_seconds,
                progress_callback=progress_callback,
            )
            return {
                "command": command,
                "status": "ok",
                "error": "",
                "raw_text": raw_text,
                "raw_lines": self._normalize_lines(raw_text),
            }
        except SerialConnectionError as exc:
            return {
                "command": command,
                "status": "serial_error",
                "error": str(exc),
                "raw_text": "",
                "raw_lines": [],
            }

    def _build_settings_section(self, command_results: dict[str, dict[str, object]]) -> dict[str, object]:
        full_response = self._command_text(command_results["printEverything"])
        snapshot = parse_settings_snapshot(
            full_response,
            self._command_text(command_results["printPopUpMinStatePersistMs"]),
            self._command_text(command_results["printRemoteInputPins"]),
            self._command_text(command_results["getIdleTimeToPowerOff"]),
            sensing_delay_response=self._command_text(command_results["printPopUpSensingDelayUs"]),
            remote_inputs_with_headlights_response=self._command_text(
                command_results["printRemoteInputsWithHeadlights"]
            ),
        )
        return {
            "parsed": self._serialize_settings_snapshot(snapshot),
            "commands": {
                "printEverything": command_results["printEverything"],
                "getIdleTimeToPowerOff": command_results["getIdleTimeToPowerOff"],
                "printPopUpMinStatePersistMs": command_results["printPopUpMinStatePersistMs"],
                "printRemoteInputPins": command_results["printRemoteInputPins"],
                "printPopUpSensingDelayUs": command_results["printPopUpSensingDelayUs"],
                "printRemoteInputsWithHeadlights": command_results["printRemoteInputsWithHeadlights"],
            },
        }

    def _build_statistics_section(self, command_result: dict[str, object]) -> dict[str, object]:
        raw_text = self._command_text(command_result)
        parse_error = ""
        parsed: dict[str, object] | None = None
        try:
            if raw_text.strip():
                parsed = self._serialize_statistics_snapshot(parse_statistics_snapshot(raw_text))
        except StatisticsParseError as exc:
            parse_error = str(exc)

        return {
            "parsed": parsed,
            "parse_error": parse_error,
            "commands": {
                "printStatisticalData": command_result,
            },
        }

    def _build_errors_section(self, command_result: dict[str, object]) -> dict[str, object]:
        report = parse_stored_error_report(self._command_text(command_result))
        return {
            "parsed": self._serialize_error_report(report),
            "commands": {
                "printErrors": command_result,
            },
        }

    def _build_firmware_release_section(
        self,
        firmware_release_service: FirmwareReleaseService | None,
    ) -> dict[str, object]:
        if firmware_release_service is None:
            return {
                "parsed": None,
                "error": "GitHub firmware release service was not provided.",
            }

        try:
            release = firmware_release_service.fetch_latest_release()
        except FirmwareReleaseError as exc:
            return {
                "parsed": None,
                "error": str(exc),
            }

        return {
            "parsed": {
                "version": release.version,
                "release_name": release.release_name,
                "tag_name": release.tag_name,
                "asset_name": release.asset_name,
                "download_url": release.download_url,
                "asset_size_bytes": release.asset_size_bytes,
                "asset_sha256": release.asset_sha256,
                "published_at": release.published_at,
                "updated_at": release.updated_at,
                "html_url": release.html_url,
            },
            "error": "",
        }

    def _serialize_settings_snapshot(self, snapshot: SettingsSnapshot) -> dict[str, object]:
        return {
            "battery_calibration_a": snapshot.battery_calibration_a,
            "battery_calibration_b": snapshot.battery_calibration_b,
            "battery_voltage_v": snapshot.battery_voltage_v,
            "temperature_c": snapshot.temperature_c,
            "allow_sleepy_eye_with_headlights": snapshot.allow_sleepy_eye_with_headlights,
            "allow_remote_inputs_with_headlights": snapshot.allow_remote_inputs_with_headlights,
            "remote_inputs_with_headlights_status": snapshot.remote_inputs_with_headlights_status,
            "idle_power_off_seconds": snapshot.idle_power_off_seconds,
            "idle_power_off_days": snapshot.idle_power_off_days,
            "min_state_persist_ms": snapshot.min_state_persist_ms,
            "min_state_persist_status": snapshot.min_state_persist_status,
            "sensing_delay_us": snapshot.sensing_delay_us,
            "sensing_delay_status": snapshot.sensing_delay_status,
            "remote_input_mapping": list(snapshot.remote_input_mapping) if snapshot.remote_input_mapping else None,
            "remote_input_mapping_status": snapshot.remote_input_mapping_status,
            "rh_timing": {
                "title": snapshot.rh_timing.title,
                "lines": list(snapshot.rh_timing.lines),
            },
            "lh_timing": {
                "title": snapshot.lh_timing.title,
                "lines": list(snapshot.lh_timing.lines),
            },
            "raw_lines": list(snapshot.raw_lines),
        }

    def _serialize_statistics_snapshot(self, snapshot: StatisticsSnapshot) -> dict[str, object]:
        return {
            "boot_count": snapshot.boot_count,
            "total_runtime_seconds": snapshot.total_runtime_seconds,
            "total_runtime_days": snapshot.total_runtime_days,
            "rh_side": {
                "cycles": snapshot.rh_side.cycles,
                "errors": snapshot.rh_side.errors,
                "move_time_ms": snapshot.rh_side.move_time_ms,
            },
            "lh_side": {
                "cycles": snapshot.lh_side.cycles,
                "errors": snapshot.lh_side.errors,
                "move_time_ms": snapshot.lh_side.move_time_ms,
            },
            "inputs": {
                "button_rh": snapshot.inputs.button_rh,
                "button_lh": snapshot.inputs.button_lh,
                "button_both": snapshot.inputs.button_both,
                "remote_1": snapshot.inputs.remote_1,
                "remote_2": snapshot.inputs.remote_2,
                "remote_3": snapshot.inputs.remote_3,
                "remote_4": snapshot.inputs.remote_4,
            },
            "raw_lines": list(snapshot.raw_lines),
        }

    def _serialize_error_report(self, report: ErrorReport) -> dict[str, object]:
        return {
            "headlight_entries": [
                {
                    "boot_cycle": entry.boot_cycle,
                    "error_code": entry.error_code,
                    "battery_voltage_volts": entry.battery_voltage_volts,
                    "temperature_celsius": entry.temperature_celsius,
                    "raw_line": entry.raw_line,
                }
                for entry in report.headlight_entries
            ],
            "module_entries": [
                {
                    "boot_cycle": entry.boot_cycle,
                    "error_code": entry.error_code,
                    "battery_voltage_volts": entry.battery_voltage_volts,
                    "temperature_celsius": entry.temperature_celsius,
                    "raw_line": entry.raw_line,
                }
                for entry in report.module_entries
            ],
            "status_hint": report.status_hint,
            "has_errors": report.has_errors,
            "raw_lines": list(report.raw_lines),
        }

    def _serialize_manufacture_snapshot(self, snapshot: ManufactureSnapshot) -> dict[str, object]:
        return {
            "serial_number": self._serialize_manufacture_field(snapshot.serial_number),
            "board_serial": self._serialize_manufacture_field(snapshot.board_serial),
            "board_revision": self._serialize_manufacture_field(snapshot.board_revision),
            "car_model": self._serialize_manufacture_field(snapshot.car_model),
            "manufacture_date": self._serialize_manufacture_field(snapshot.manufacture_date),
            "initial_firmware_version": self._serialize_manufacture_field(snapshot.initial_firmware_version),
            "reported_field_count": snapshot.reported_field_count,
            "raw_lines": list(snapshot.raw_lines),
        }

    def _serialize_manufacture_field(self, field: ManufactureField) -> dict[str, object]:
        return {
            "value": field.value,
            "reported": field.reported,
            "compact_display": field.compact_display,
            "status_hint": field.status_hint,
        }

    def _command_text(self, command_result: dict[str, object]) -> str:
        raw_text = command_result.get("raw_text")
        if isinstance(raw_text, str):
            return raw_text
        return ""

    def _normalize_lines(self, raw_text: str) -> list[str]:
        return [line.strip() for line in raw_text.splitlines() if line.strip()]
