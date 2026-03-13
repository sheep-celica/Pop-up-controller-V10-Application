from datetime import date

from popup_controller.services.manufacture_service import (
    calculate_controller_age,
    parse_manufacture_snapshot,
    try_parse_manufacture_date,
)


SAMPLE_RESPONSE = """[4189] ---- Manufacture Data ----
[4189] Locked: true
[4189] Serial Number: 1000
[4189] Board Serial: <empty>
[4199] Board Revision: <empty>
[4199] Car Model: <empty>
[4199] Manufacture Date: 2026-02-24
[4199] Initial FW Version: 1.0.10
[4209] --------------------------
"""


PARTIAL_RESPONSE = """[52] ---- Manufacture Data ----
[52] Serial Number: 1001
[52] Manufacture Date: 2026-03-01
[52] Initial Firmware Version: 1.2.0
[52] --------------------------
"""


INVALID_DATE_RESPONSE = """[52] ---- Manufacture Data ----
[52] Manufacture Date: built around spring 2026
[52] --------------------------
"""


def test_parse_manufacture_snapshot_extracts_expected_fields() -> None:
    snapshot = parse_manufacture_snapshot(SAMPLE_RESPONSE)

    assert snapshot.serial_number.value == "1000"
    assert snapshot.serial_number.compact_display == "1000"
    assert snapshot.board_serial.reported is True
    assert snapshot.board_serial.value is None
    assert snapshot.board_serial.compact_display == "Empty"
    assert snapshot.manufacture_date.value == "2026-02-24"
    assert snapshot.initial_firmware_version.value == "1.0.10"
    assert snapshot.reported_field_count == 6


def test_parse_manufacture_snapshot_tolerates_missing_fields() -> None:
    snapshot = parse_manufacture_snapshot(PARTIAL_RESPONSE)

    assert snapshot.serial_number.value == "1001"
    assert snapshot.board_serial.reported is False
    assert snapshot.board_serial.compact_display == "Unavailable"
    assert snapshot.board_revision.reported is False
    assert snapshot.car_model.reported is False
    assert snapshot.initial_firmware_version.value == "1.2.0"
    assert snapshot.reported_field_count == 3


def test_try_parse_manufacture_date_extracts_iso_date_when_available() -> None:
    sample_snapshot = parse_manufacture_snapshot(SAMPLE_RESPONSE)
    invalid_snapshot = parse_manufacture_snapshot(INVALID_DATE_RESPONSE)

    assert try_parse_manufacture_date(sample_snapshot.manufacture_date) == date(2026, 2, 24)
    assert try_parse_manufacture_date("Built on 2026-02-24 by fixture") == date(2026, 2, 24)
    assert try_parse_manufacture_date(invalid_snapshot.manufacture_date) is None


def test_calculate_controller_age_returns_year_month_day_components() -> None:
    age = calculate_controller_age(date(2026, 2, 24), reference_date=date(2026, 3, 13))

    assert age is not None
    assert (age.years, age.months, age.days) == (0, 0, 17)
    assert age.display == "0 years, 0 months, 17 days old"



def test_calculate_controller_age_returns_none_for_future_dates() -> None:
    assert calculate_controller_age(date(2026, 3, 14), reference_date=date(2026, 3, 13)) is None