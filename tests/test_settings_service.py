from popup_controller.services.settings_service import parse_battery_voltage_response, parse_settings_snapshot


SETTINGS_RESPONSE = """[2185144] printEverything command received.
[2185144] ---- Manufacture Data ----
[2185165] --------------------------
[2185165] ---- Statistics ----
[2185196] --------------------
[2185196] ---- RH Pop-up Timing Calibration ----
[2185207] Supported range: 11.0 V .. 15.0 V, default down-time: 600 ms
[2185207]   11.7 V -> 598 ms (3 samples)
[2185228] Populated buckets: 6/41, total samples: 13
[2185228] --------------------------------------
[2185239] ---- LH Pop-up Timing Calibration ----
[2185249] Supported range: 11.0 V .. 15.0 V, default down-time: 600 ms
[2185249]   12.5 V -> 604 ms (1 samples)
[2185270] Populated buckets: 8/41, total samples: 13
[2185281] --------------------------------------
[2185281] Battery voltage calibration constants: a=1.001585, b=0.097071
[2185291] ALLOW_SLEEPY_EYE_MODE_WITH_HEADLIGHTS=TRUE
[2185291] Idle power-off threshold: 86400 s.
---- Error Log ----
-------------------
[2185303] Temperature: 22.50 C
[2185306] Battery voltage: 2.87 V
"""


UNKNOWN_MIN_STATE_RESPONSE = """[2186251] Unknown command: printPopUpMinStatePersistMs
[2186251] Type 'help' for available commands.
"""


KNOWN_MIN_STATE_RESPONSE = """[101] Pop-up minimum state persistence: 250 ms
"""


CURRENT_FIRMWARE_MIN_STATE_RESPONSE = """[273808] MIN_STATE_PERSIST_MS=5
"""


LEGACY_REMOTE_MAPPING_RESPONSE = """[20] Remote input mapping: 1 / 2 / 3 / 4
"""


CURRENT_REMOTE_MAPPING_RESPONSE = """[274258] REMOTE_INPUT_PINS=4 3 2 1
"""


CURRENT_IDLE_POWER_RESPONSE = """[51018] 86400
"""


BATTERY_VOLTAGE_RESPONSE = """[275168] Battery voltage [1/5]: 2.85 V
[275671] Battery voltage [2/5]: 2.85 V
[276174] Battery voltage [3/5]: 2.85 V
[276677] Battery voltage [4/5]: 2.85 V
[277180] Battery voltage [5/5]: 2.85 V
[277180] Battery voltage average (5 readings): 2.85 V
"""


def test_parse_settings_snapshot_extracts_expected_values() -> None:
    snapshot = parse_settings_snapshot(SETTINGS_RESPONSE, UNKNOWN_MIN_STATE_RESPONSE)

    assert snapshot.battery_calibration_a == 1.001585
    assert snapshot.battery_calibration_b == 0.097071
    assert snapshot.allow_sleepy_eye_with_headlights is True
    assert snapshot.idle_power_off_seconds == 86400
    assert snapshot.idle_power_off_days == 1.0
    assert snapshot.temperature_c == 22.5
    assert snapshot.battery_voltage_v == 2.87
    assert snapshot.min_state_persist_ms is None
    assert "unavailable" in snapshot.min_state_persist_status.lower()
    assert snapshot.remote_input_mapping is None
    assert snapshot.rh_timing.display_text.startswith("Supported range")
    assert "Populated buckets: 8/41" in snapshot.lh_timing.display_text


def test_parse_settings_snapshot_tolerates_optional_future_fields() -> None:
    snapshot = parse_settings_snapshot(LEGACY_REMOTE_MAPPING_RESPONSE, KNOWN_MIN_STATE_RESPONSE)

    assert snapshot.battery_calibration_a is None
    assert snapshot.allow_sleepy_eye_with_headlights is None
    assert snapshot.idle_power_off_seconds is None
    assert snapshot.min_state_persist_ms == 250
    assert snapshot.min_state_persist_status == ""
    assert snapshot.remote_input_mapping == (1, 2, 3, 4)
    assert snapshot.remote_input_mapping_status == ""
    assert snapshot.rh_timing.display_text == "No calibration data reported by controller."


def test_parse_settings_snapshot_supports_current_firmware_formats() -> None:
    snapshot = parse_settings_snapshot(
        SETTINGS_RESPONSE,
        CURRENT_FIRMWARE_MIN_STATE_RESPONSE,
        CURRENT_REMOTE_MAPPING_RESPONSE,
        CURRENT_IDLE_POWER_RESPONSE,
    )

    assert snapshot.idle_power_off_seconds == 86400
    assert snapshot.min_state_persist_ms == 5
    assert snapshot.min_state_persist_status == ""
    assert snapshot.remote_input_mapping == (4, 3, 2, 1)
    assert snapshot.remote_input_mapping_status == ""


def test_parse_battery_voltage_response_prefers_latest_average_line() -> None:
    assert parse_battery_voltage_response(BATTERY_VOLTAGE_RESPONSE) == 2.85
