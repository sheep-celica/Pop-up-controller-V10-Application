from popup_controller.ui.sections import SECTION_DEFINITIONS


def test_section_definitions_cover_expected_areas() -> None:
    section_ids = {section.section_id for section in SECTION_DEFINITIONS}

    assert section_ids == {"statistics", "errors", "settings", "manufacture", "direct_controls", "service"}
    assert len(SECTION_DEFINITIONS) == 6


def test_errors_section_matches_supported_controller_commands() -> None:
    errors_section = next(section for section in SECTION_DEFINITIONS if section.section_id == "errors")

    assert errors_section.button_subtitle == "Stored controller error log"
    assert errors_section.source_commands == ("printErrors", "clearErrors")
    assert errors_section.planned_fields == (
        "Headlight / pop-up stored error log",
        "Other module stored error log",
        "Clear stored errors action",
    )
