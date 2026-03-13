from popup_controller.services.external_expander_service import parse_external_expander_snapshot


NOT_CONNECTED_RESPONSE = """[50616] Not Connected
"""


CONNECTED_RESPONSE = """[14] Connected
"""


UNKNOWN_COMMAND_RESPONSE = """[10] Unknown command: getExternalExpander
[10] Type 'help' for available commands.
"""



def test_parse_external_expander_snapshot_extracts_state() -> None:
    snapshot = parse_external_expander_snapshot(NOT_CONNECTED_RESPONSE)

    assert snapshot.state == "Not Connected"
    assert snapshot.status_hint == ""


def test_parse_external_expander_snapshot_tolerates_other_reported_states() -> None:
    snapshot = parse_external_expander_snapshot(CONNECTED_RESPONSE)

    assert snapshot.state == "Connected"
    assert snapshot.status_hint == ""


def test_parse_external_expander_snapshot_handles_unknown_command() -> None:
    snapshot = parse_external_expander_snapshot(UNKNOWN_COMMAND_RESPONSE)

    assert snapshot.state is None
    assert "unavailable" in snapshot.status_hint.lower()
