from popup_controller.services.statistics_service import parse_statistics_snapshot


SAMPLE_RESPONSE = """[2981864] printStatisticalData command received.
[2981864] ---- Statistics ----
[2981864] Boot count: 73
[2981864] Total runtime: 97052 s (1.12 days)
[2981875] RH cycles / errors / move: 238 / 5 / 187909 ms
[2981875] LH cycles / errors / move: 242 / 5 / 195456 ms
[2981885] Buttons RH/LH/BH: 12 / 6 / 0
[2981885] Remote 1/2/3/4: 7 / 10 / 4 / 1
[2981885] --------------------
"""


def test_parse_statistics_snapshot_extracts_expected_fields() -> None:
    snapshot = parse_statistics_snapshot(SAMPLE_RESPONSE)

    assert snapshot.boot_count == 73
    assert snapshot.total_runtime_seconds == 97052
    assert snapshot.total_runtime_days == 1.12
    assert snapshot.rh_side.cycles == 238
    assert snapshot.rh_side.errors == 5
    assert snapshot.rh_side.move_time_ms == 187909
    assert snapshot.lh_side.cycles == 242
    assert snapshot.inputs.button_both == 0
    assert snapshot.inputs.remote_4 == 1