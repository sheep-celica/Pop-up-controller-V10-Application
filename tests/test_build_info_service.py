from popup_controller.services.build_info_service import parse_build_info_snapshot


BUILD_INFO_RESPONSE = """[253171] FW_VERSION=1.0.3
[253171] BUILD_TIMESTAMP=2026-03-12T18:33:55Z
"""


PARTIAL_BUILD_INFO_RESPONSE = """[12] FW_VERSION=1.0.4
"""


INVALID_TIMESTAMP_RESPONSE = """[14] BUILD_TIMESTAMP=not-a-timestamp
"""


def test_parse_build_info_snapshot_extracts_version_and_date() -> None:
    snapshot = parse_build_info_snapshot(BUILD_INFO_RESPONSE)

    assert snapshot.firmware_version == "1.0.3"
    assert snapshot.build_timestamp == "2026-03-12T18:33:55Z"
    assert snapshot.build_date == "2026-03-12"


def test_parse_build_info_snapshot_tolerates_missing_fields() -> None:
    snapshot = parse_build_info_snapshot(PARTIAL_BUILD_INFO_RESPONSE)

    assert snapshot.firmware_version == "1.0.4"
    assert snapshot.build_timestamp is None
    assert snapshot.build_date is None


def test_parse_build_info_snapshot_handles_invalid_timestamps() -> None:
    snapshot = parse_build_info_snapshot(INVALID_TIMESTAMP_RESPONSE)

    assert snapshot.firmware_version is None
    assert snapshot.build_timestamp == "not-a-timestamp"
    assert snapshot.build_date is None
