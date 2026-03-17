from popup_controller.services.temperature_service import parse_temperature_snapshot


DIRECT_TEMPERATURE_RESPONSE = """[734828] Temperature: 22.50 C
"""


PRINT_EVERYTHING_RESPONSE = """[734712] printEverything command received.
[734828] Temperature: 22.50 C
[734842] Battery voltage: 12.06 V
"""


UNKNOWN_COMMAND_RESPONSE = """[10] Unknown command: getTemperature
[10] Type 'help' for available commands.
"""


UNEXPECTED_RESPONSE = """[77] Temperature sensor warming up
"""


def test_parse_temperature_snapshot_extracts_temperature() -> None:
    snapshot = parse_temperature_snapshot(DIRECT_TEMPERATURE_RESPONSE)

    assert snapshot.temperature_c == 22.5
    assert snapshot.status_hint == ""


def test_parse_temperature_snapshot_extracts_temperature_from_print_everything() -> None:
    snapshot = parse_temperature_snapshot(PRINT_EVERYTHING_RESPONSE)

    assert snapshot.temperature_c == 22.5
    assert snapshot.status_hint == ""


def test_parse_temperature_snapshot_handles_unknown_command() -> None:
    snapshot = parse_temperature_snapshot(UNKNOWN_COMMAND_RESPONSE)

    assert snapshot.temperature_c is None
    assert "unavailable" in snapshot.status_hint.lower()


def test_parse_temperature_snapshot_flags_unexpected_formats() -> None:
    snapshot = parse_temperature_snapshot(UNEXPECTED_RESPONSE)

    assert snapshot.temperature_c is None
    assert "unexpected" in snapshot.status_hint.lower()