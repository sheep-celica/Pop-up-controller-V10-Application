from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_ERROR_LOG_HEADER = "---- Error Log ----"
_ERROR_LOG_FOOTER_RE = re.compile(r"^-{5,}$")
_BOOT_CYCLE_RE = re.compile(r"\bBoot=(?P<boot>\d+)\b")
_ERROR_CODE_RE = re.compile(r"\bCode=(?P<code>[A-Z0-9_]+)\b")
_BATTERY_VOLTAGE_RE = re.compile(r"\bVbat=(?P<millivolts>\d+)\s*mV\b")
_TEMPERATURE_RE = re.compile(r"\bTemp=(?P<temperature>-?\d+(?:\.\d+)?)\s*C\b")


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    boot_cycle: int | None
    error_code: str
    battery_voltage_volts: float | None
    temperature_celsius: float | None
    raw_line: str


@dataclass(frozen=True, slots=True)
class ErrorReport:
    headlight_entries: tuple[ErrorEntry, ...]
    module_entries: tuple[ErrorEntry, ...]
    status_hint: str
    raw_lines: tuple[str, ...]

    @property
    def has_errors(self) -> bool:
        return bool(self.headlight_entries or self.module_entries)


def parse_stored_error_report(raw_response: str) -> ErrorReport:
    lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(lines).casefold()

    if not lines:
        return ErrorReport((), (), "Controller did not return any stored error data.", lines)
    if "unknown command" in normalized_text:
        return ErrorReport((), (), "Stored error data unavailable on this firmware.", lines)
    if "placeholder" in normalized_text:
        return ErrorReport((), (), "Controller reports the stored error command as a placeholder.", lines)

    error_lines, saw_error_log = _extract_error_log_entries(lines)
    if not error_lines and not saw_error_log:
        error_lines = tuple(_fallback_error_lines(lines))

    headlight_entries: list[ErrorEntry] = []
    module_entries: list[ErrorEntry] = []
    for line in error_lines:
        entry = _parse_error_entry(line)
        if _is_headlight_entry(entry):
            headlight_entries.append(entry)
        else:
            module_entries.append(entry)

    if headlight_entries or module_entries:
        return ErrorReport(tuple(headlight_entries), tuple(module_entries), "", lines)

    if any(marker in normalized_text for marker in ("no errors", "error log empty", "no stored errors")):
        return ErrorReport((), (), "No stored errors reported by controller.", lines)

    if saw_error_log:
        return ErrorReport((), (), "No stored errors reported by controller.", lines)

    return ErrorReport((), (), "Controller did not return any stored error log entries.", lines)


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines


def _extract_error_log_entries(lines: tuple[str, ...]) -> tuple[tuple[str, ...], bool]:
    entries: list[str] = []
    in_error_log = False
    saw_error_log = False

    for line in lines:
        if line == _ERROR_LOG_HEADER:
            in_error_log = True
            saw_error_log = True
            continue

        if not in_error_log:
            continue

        if _ERROR_LOG_FOOTER_RE.fullmatch(line):
            break

        entries.append(line)

    return tuple(entries), saw_error_log


def _fallback_error_lines(lines: tuple[str, ...]) -> list[str]:
    ignored_prefixes = (
        "Type 'help'",
        "Unknown command:",
        "printErrors command received.",
    )

    return [
        line
        for line in lines
        if line != _ERROR_LOG_HEADER
        and not _ERROR_LOG_FOOTER_RE.fullmatch(line)
        and not line.startswith(ignored_prefixes)
    ]


def _parse_error_entry(line: str) -> ErrorEntry:
    boot_match = _BOOT_CYCLE_RE.search(line)
    code_match = _ERROR_CODE_RE.search(line)
    voltage_match = _BATTERY_VOLTAGE_RE.search(line)
    temperature_match = _TEMPERATURE_RE.search(line)

    boot_cycle = int(boot_match.group("boot")) if boot_match is not None else None
    error_code = code_match.group("code") if code_match is not None else line
    battery_voltage_volts = (
        int(voltage_match.group("millivolts")) / 1000.0 if voltage_match is not None else None
    )
    temperature_celsius = (
        float(temperature_match.group("temperature")) if temperature_match is not None else None
    )

    return ErrorEntry(
        boot_cycle=boot_cycle,
        error_code=error_code,
        battery_voltage_volts=battery_voltage_volts,
        temperature_celsius=temperature_celsius,
        raw_line=line,
    )


def _is_headlight_entry(entry: ErrorEntry) -> bool:
    return entry.error_code.startswith(("RH_", "LH_"))
