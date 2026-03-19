from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SectionDefinition:
    section_id: str
    title: str
    button_subtitle: str
    summary: str
    planned_fields: tuple[str, ...]
    source_commands: tuple[str, ...]


SECTION_DEFINITIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(
        section_id="statistics",
        title="Statistical Data",
        button_subtitle="Runtime, usage counters, and timing calibration",
        summary=(
            "This section focuses on lifecycle counters, usage history, and timing calibration data returned by the controller."
        ),
        planned_fields=(
            "Boot count",
            "Total runtime",
            "RH and LH cycle counts, error counts, and move times",
            "Physical button usage counters",
            "Remote input usage counters",
            "RH and LH pop-up timing calibration buckets",
        ),
        source_commands=(
            "printStatisticalData",
            "printPopUpTimingCalibration",
        ),
    ),
    SectionDefinition(
        section_id="errors",
        title="Errors",
        button_subtitle="Stored controller error log",
        summary=(
            "This section reads the controller's stored error log, can clear it, and groups the reported entries into headlight / pop-up and other module sections while preserving the parsed details from the controller."
        ),
        planned_fields=(
            "Headlight / pop-up stored error log",
            "Other module stored error log",
            "Clear stored errors action",
        ),
        source_commands=(
            "printErrors",
            "clearErrors",
        ),
    ),
    SectionDefinition(
        section_id="settings",
        title="Settings",
        button_subtitle="Calibration, power, mapping, and timing",
        summary=(
            "This section groups controller settings, calibration constants, timing data, hidden firmware options, and remote input mapping while tolerating missing or unsupported values."
        ),
        planned_fields=(
            "Battery voltage calibration constants and live voltage readback",
            "Sleepy-eye mode with headlights flag",
            "Remote inputs with light-switch flag",
            "Idle power-off threshold in seconds and days",
            "Minimum state-persistence milliseconds",
            "Remote input mapping",
            "RH and LH pop-up timing calibration blocks",
        ),
        source_commands=(
            "printEverything",
            "printBatteryVoltageCalibration",
            "readBatteryVoltage",
            "getIdleTimeToPowerOff",
            "printSleepyEyeModeWithHeadlights",
            "printRemoteInputsWithHeadlights",
            "writeRemoteInputsWithHeadlights",
            "printPopUpMinStatePersistMs",
            "printRemoteInputPins",
            "setRemoteInputPins",
            "clearPopUptimingCalibration",
        ),
    ),
    SectionDefinition(
        section_id="manufacture",
        title="Manufacture Data",
        button_subtitle="Controller identity and production metadata",
        summary=(
            "This section displays controller identity and production metadata returned by the firmware, while tolerating fields that may be missing on other firmware versions."
        ),
        planned_fields=(
            "Serial number",
            "Board serial",
            "Board revision",
            "Car model",
            "Manufacture date",
            "Initial firmware version",
        ),
        source_commands=(
            "printEverything",
        ),
    ),
    SectionDefinition(
        section_id="direct_controls",
        title="Direct Controls",
        button_subtitle="Live wink and toggle actions",
        summary=(
            "This section sends direct control commands to the connected controller without changing stored settings."
        ),
        planned_fields=(
            "RH wink action",
            "LH wink action",
            "Both wink action",
            "Toggle sleepy-eye mode action",
            "Toggle both action",
        ),
        source_commands=(
            "wink rh",
            "wink lh",
            "wink both",
            "toggleSleepyEyeMode",
            "toggle both",
        ),
    ),
    SectionDefinition(
        section_id="service",
        title="Service",
        button_subtitle="Protected reset and write operations",
        summary=(
            "This password-protected section groups maintenance commands such as clearing controller statistics and writing manufacture data."
        ),
        planned_fields=(
            "Clear statistical data",
            "Write manufacture data",
            "Protected service status messages",
        ),
        source_commands=(
            "clearStatisticalData <password>",
            "writeManufactureData <serial_number> <board_serial> <board_revision> <car_model...>",
        ),
    ),
)
