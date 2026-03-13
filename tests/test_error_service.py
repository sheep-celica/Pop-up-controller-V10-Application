import pytest

from popup_controller.services.error_service import parse_stored_error_report


STORED_ERRORS_RESPONSE = """[378993] printErrors command received.
[378994] ---- Error Log ----
[218980] Boot=79 Code=RH_POP_UP_TIMEOUT Vbat=12681 mV Temp=23.0 C
[218999] Boot=79 Code=LH_POP_UP_TIMEOUT Vbat=12669 mV Temp=23.0 C
[379000] -------------------
"""


MIXED_ERRORS_RESPONSE = """[100] ---- Error Log ----
[101] Boot=80 Code=RH_POP_UP_OVERCURRENT Vbat=12440 mV Temp=28.0 C
[102] Boot=80 Code=LOW_BATTERY_VOLTAGE Vbat=11100 mV Temp=28.0 C
[103] -------------------
"""


UNKNOWN_MODULE_RESPONSE = """[200] ---- Error Log ----
[201] Boot=81 Code=EXPANDER_FAULT Vbat=12005 mV Temp=26.5 C
[202] -------------------
"""


NO_ERRORS_RESPONSE = """[30] ---- Error Log ----
[31] -------------------
"""


UNKNOWN_COMMAND_RESPONSE = """[10] Unknown command: printErrors
[10] Type 'help' for available commands.
"""


def test_parse_stored_error_report_preserves_structured_headlight_details() -> None:
    report = parse_stored_error_report(STORED_ERRORS_RESPONSE)

    assert len(report.headlight_entries) == 2
    assert report.module_entries == ()
    assert report.has_errors is True

    first_entry = report.headlight_entries[0]
    second_entry = report.headlight_entries[1]

    assert first_entry.boot_cycle == 79
    assert first_entry.error_code == "RH_POP_UP_TIMEOUT"
    assert first_entry.battery_voltage_volts == pytest.approx(12.681)
    assert first_entry.temperature_celsius == pytest.approx(23.0)
    assert first_entry.raw_line == "Boot=79 Code=RH_POP_UP_TIMEOUT Vbat=12681 mV Temp=23.0 C"

    assert second_entry.boot_cycle == 79
    assert second_entry.error_code == "LH_POP_UP_TIMEOUT"
    assert second_entry.battery_voltage_volts == pytest.approx(12.669)
    assert second_entry.temperature_celsius == pytest.approx(23.0)


def test_parse_stored_error_report_splits_headlight_and_module_entries() -> None:
    report = parse_stored_error_report(MIXED_ERRORS_RESPONSE)

    assert len(report.headlight_entries) == 1
    assert len(report.module_entries) == 1
    assert report.headlight_entries[0].error_code == "RH_POP_UP_OVERCURRENT"
    assert report.module_entries[0].error_code == "LOW_BATTERY_VOLTAGE"
    assert report.module_entries[0].battery_voltage_volts == pytest.approx(11.1)


def test_parse_stored_error_report_keeps_unknown_codes_in_module_section() -> None:
    report = parse_stored_error_report(UNKNOWN_MODULE_RESPONSE)

    assert report.headlight_entries == ()
    assert len(report.module_entries) == 1
    assert report.module_entries[0].boot_cycle == 81
    assert report.module_entries[0].error_code == "EXPANDER_FAULT"
    assert report.module_entries[0].battery_voltage_volts == pytest.approx(12.005)
    assert report.module_entries[0].temperature_celsius == pytest.approx(26.5)


def test_parse_stored_error_report_recognizes_empty_error_logs() -> None:
    report = parse_stored_error_report(NO_ERRORS_RESPONSE)

    assert report.has_errors is False
    assert "no stored errors" in report.status_hint.lower()


def test_parse_stored_error_report_handles_unknown_commands() -> None:
    report = parse_stored_error_report(UNKNOWN_COMMAND_RESPONSE)

    assert report.has_errors is False
    assert "unavailable" in report.status_hint.lower()
