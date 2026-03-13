from popup_controller.services.controller_status_service import parse_controller_status_snapshot


PLAIN_BENCH_MODE_RESPONSE = """[50211] BENCH MODE
"""


RUNNING_RESPONSE = """[66] Controller status: RUNNING
"""


UNKNOWN_COMMAND_RESPONSE = """[10] Unknown command: getControllerStatus
[10] Type 'help' for available commands.
"""


UNEXPECTED_RESPONSE = """[77] Status pending
"""


def test_parse_controller_status_snapshot_recognizes_bench_mode() -> None:
    snapshot = parse_controller_status_snapshot(PLAIN_BENCH_MODE_RESPONSE)

    assert snapshot.state == "BENCH MODE"
    assert snapshot.status_hint == ""


def test_parse_controller_status_snapshot_recognizes_running() -> None:
    snapshot = parse_controller_status_snapshot(RUNNING_RESPONSE)

    assert snapshot.state == "RUNNING"
    assert snapshot.status_hint == ""


def test_parse_controller_status_snapshot_handles_unknown_command() -> None:
    snapshot = parse_controller_status_snapshot(UNKNOWN_COMMAND_RESPONSE)

    assert snapshot.state is None
    assert "unavailable" in snapshot.status_hint.lower()


def test_parse_controller_status_snapshot_flags_unexpected_formats() -> None:
    snapshot = parse_controller_status_snapshot(UNEXPECTED_RESPONSE)

    assert snapshot.state is None
    assert "unexpected" in snapshot.status_hint.lower()
