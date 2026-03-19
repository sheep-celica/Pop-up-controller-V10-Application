from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_BATTERY_CALIBRATION_RE = re.compile(
    r"Battery voltage calibration constants:\s*a=(?P<a>[-+]?\d+(?:\.\d+)?),\s*b=(?P<b>[-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SLEEPY_EYE_RE = re.compile(r"ALLOW_SLEEPY_EYE_MODE_WITH_HEADLIGHTS=(?P<value>TRUE|FALSE)", re.IGNORECASE)
_REMOTE_INPUTS_WITH_HEADLIGHTS_RE = re.compile(
    r"ALLOW_REMOTE_INPUTS_WITH_HEADLIGHTS=(?P<value>TRUE|FALSE)",
    re.IGNORECASE,
)
_IDLE_POWER_OFF_RE = re.compile(r"Idle power-off threshold:\s*(?P<seconds>\d+)\s*s\.?", re.IGNORECASE)
_TEMPERATURE_RE = re.compile(r"Temperature:\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*C", re.IGNORECASE)
_BATTERY_VOLTAGE_RE = re.compile(
    r"Battery voltage(?: [^:]+)?:\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*V",
    re.IGNORECASE,
)
_REMOTE_INPUTS_RE = re.compile(
    r"(?:Remote input(?: pins| mapping)?|REMOTE_INPUT_PINS)\s*[:=]\s*"
    r"(?P<i1>[1-4])(?:\s*[/,\-]\s*|\s+)"
    r"(?P<i2>[1-4])(?:\s*[/,\-]\s*|\s+)"
    r"(?P<i3>[1-4])(?:\s*[/,\-]\s*|\s+)"
    r"(?P<i4>[1-4])",
    re.IGNORECASE,
)
_MIN_STATE_MS_RE = re.compile(r"(?:MIN_STATE_PERSIST_MS\s*=\s*)?(?P<value>\d+)(?:\s*ms)?\b", re.IGNORECASE)
_SENSING_DELAY_US_RE = re.compile(
    r"(?:POP_UP_SENSING_DELAY_US\s*=\s*|(?:Pop-up\s+)?sensing delay(?:\s+us)?\s*[:=]\s*)?"
    r"(?P<value>\d+)(?:\s*(?:us|microseconds?))?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TimingCalibrationBlock:
    title: str
    lines: tuple[str, ...]

    @property
    def display_text(self) -> str:
        if not self.lines:
            return "No calibration data reported by controller."
        return "\n".join(self.lines)


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    battery_calibration_a: float | None
    battery_calibration_b: float | None
    battery_voltage_v: float | None
    temperature_c: float | None
    allow_sleepy_eye_with_headlights: bool | None
    allow_remote_inputs_with_headlights: bool | None
    remote_inputs_with_headlights_status: str
    idle_power_off_seconds: int | None
    min_state_persist_ms: int | None
    min_state_persist_status: str
    sensing_delay_us: int | None
    sensing_delay_status: str
    remote_input_mapping: tuple[int, int, int, int] | None
    remote_input_mapping_status: str
    rh_timing: TimingCalibrationBlock
    lh_timing: TimingCalibrationBlock
    raw_lines: tuple[str, ...]

    @property
    def idle_power_off_days(self) -> float | None:
        if self.idle_power_off_seconds is None:
            return None
        return self.idle_power_off_seconds / 86400.0


def parse_settings_snapshot(
    raw_response: str,
    min_state_response: str | None = None,
    remote_input_response: str | None = None,
    idle_power_response: str | None = None,
    sensing_delay_response: str | None = None,
    remote_inputs_with_headlights_response: str | None = None,
) -> SettingsSnapshot:
    lines = tuple(_normalize_lines(raw_response))

    battery_calibration_a, battery_calibration_b = _parse_battery_calibration(lines)
    allow_sleepy_eye_with_headlights = _parse_sleepy_eye_setting(lines)
    allow_remote_inputs_with_headlights, remote_inputs_with_headlights_status = _parse_bool_response(
        lines,
        _REMOTE_INPUTS_WITH_HEADLIGHTS_RE,
        remote_inputs_with_headlights_response,
    )
    idle_power_off_seconds = _parse_idle_power_off_seconds(lines, idle_power_response)
    temperature_c = _parse_float_value(lines, _TEMPERATURE_RE)
    battery_voltage_v = _parse_last_float_value(lines, _BATTERY_VOLTAGE_RE)
    remote_input_mapping, remote_input_mapping_status = _parse_remote_input_mapping(lines, remote_input_response)
    rh_timing = TimingCalibrationBlock(
        title="RH",
        lines=_extract_section(lines, "---- RH Pop-up Timing Calibration ----"),
    )
    lh_timing = TimingCalibrationBlock(
        title="LH",
        lines=_extract_section(lines, "---- LH Pop-up Timing Calibration ----"),
    )
    min_state_persist_ms, min_state_persist_status = _parse_value_response(min_state_response, _MIN_STATE_MS_RE)
    sensing_delay_us, sensing_delay_status = _parse_value_response(sensing_delay_response, _SENSING_DELAY_US_RE)

    return SettingsSnapshot(
        battery_calibration_a=battery_calibration_a,
        battery_calibration_b=battery_calibration_b,
        battery_voltage_v=battery_voltage_v,
        temperature_c=temperature_c,
        allow_sleepy_eye_with_headlights=allow_sleepy_eye_with_headlights,
        allow_remote_inputs_with_headlights=allow_remote_inputs_with_headlights,
        remote_inputs_with_headlights_status=remote_inputs_with_headlights_status,
        idle_power_off_seconds=idle_power_off_seconds,
        min_state_persist_ms=min_state_persist_ms,
        min_state_persist_status=min_state_persist_status,
        sensing_delay_us=sensing_delay_us,
        sensing_delay_status=sensing_delay_status,
        remote_input_mapping=remote_input_mapping,
        remote_input_mapping_status=remote_input_mapping_status,
        rh_timing=rh_timing,
        lh_timing=lh_timing,
        raw_lines=lines,
    )


def parse_battery_voltage_response(raw_response: str) -> float | None:
    lines = tuple(_normalize_lines(raw_response))
    return _parse_last_float_value(lines, _BATTERY_VOLTAGE_RE)


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines


def _parse_battery_calibration(lines: tuple[str, ...]) -> tuple[float | None, float | None]:
    for line in lines:
        match = _BATTERY_CALIBRATION_RE.search(line)
        if match is None:
            continue
        return float(match.group("a")), float(match.group("b"))
    return None, None


def _parse_sleepy_eye_setting(lines: tuple[str, ...]) -> bool | None:
    for line in lines:
        match = _SLEEPY_EYE_RE.search(line)
        if match is None:
            continue
        return match.group("value").upper() == "TRUE"
    return None


def _parse_bool_response(
    lines: tuple[str, ...],
    pattern: re.Pattern[str],
    raw_response: str | None = None,
) -> tuple[bool | None, str]:
    parsed_value = _extract_bool_value(lines, pattern)
    if parsed_value is not None:
        return parsed_value, ""

    if raw_response is None or not raw_response.strip():
        return None, "Current value unavailable on this firmware."

    response_lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(response_lines).casefold()
    if "unknown command" in normalized_text:
        return None, "Current value unavailable on this firmware."
    if "placeholder" in normalized_text:
        return None, "Controller reports this command as a placeholder."

    parsed_value = _extract_bool_value(response_lines, pattern)
    if parsed_value is not None:
        return parsed_value, ""

    return None, "Controller returned an unexpected format for this value."


def _extract_bool_value(lines: tuple[str, ...], pattern: re.Pattern[str]) -> bool | None:
    for line in lines:
        match = pattern.search(line)
        if match is None:
            continue
        return match.group("value").upper() == "TRUE"
    return None


def _parse_idle_power_off_seconds(lines: tuple[str, ...], raw_response: str | None = None) -> int | None:
    if raw_response is not None and raw_response.strip():
        parsed_value = _extract_idle_power_off_seconds(tuple(_normalize_lines(raw_response)))
        if parsed_value is not None:
            return parsed_value
    return _extract_idle_power_off_seconds(lines)


def _extract_idle_power_off_seconds(lines: tuple[str, ...]) -> int | None:
    for line in lines:
        match = _IDLE_POWER_OFF_RE.search(line)
        if match is not None:
            return int(match.group("seconds"))
        if line.isdigit():
            return int(line)
    return None


def _parse_float_value(lines: tuple[str, ...], pattern: re.Pattern[str]) -> float | None:
    for line in lines:
        match = pattern.search(line)
        if match is None:
            continue
        return float(match.group("value"))
    return None


def _parse_last_float_value(lines: tuple[str, ...], pattern: re.Pattern[str]) -> float | None:
    parsed_value: float | None = None
    for line in lines:
        match = pattern.search(line)
        if match is None:
            continue
        parsed_value = float(match.group("value"))
    return parsed_value


def _parse_remote_input_mapping(
    lines: tuple[str, ...],
    raw_response: str | None = None,
) -> tuple[tuple[int, int, int, int] | None, str]:
    parsed_mapping = _extract_remote_input_mapping(lines)
    if parsed_mapping is not None:
        return parsed_mapping, ""

    if raw_response is None or not raw_response.strip():
        return None, "Current mapping not reported by this firmware."

    response_lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(response_lines).casefold()
    if "unknown command" in normalized_text:
        return None, "Current mapping unavailable on this firmware."
    if "placeholder" in normalized_text:
        return None, "Controller reports this command as a placeholder."

    parsed_mapping = _extract_remote_input_mapping(response_lines)
    if parsed_mapping is not None:
        return parsed_mapping, ""

    return None, "Controller returned an unexpected format for the current mapping."


def _extract_remote_input_mapping(lines: tuple[str, ...]) -> tuple[int, int, int, int] | None:
    for line in lines:
        match = _REMOTE_INPUTS_RE.search(line)
        if match is None:
            continue
        return (
            int(match.group("i1")),
            int(match.group("i2")),
            int(match.group("i3")),
            int(match.group("i4")),
        )
    return None


def _extract_section(lines: tuple[str, ...], header: str) -> tuple[str, ...]:
    start_index = next((index for index, line in enumerate(lines) if line.startswith(header)), None)
    if start_index is None:
        return ()

    section_lines: list[str] = []
    for line in lines[start_index + 1 :]:
        if line.startswith("---- ") or set(line) == {"-"}:
            break
        section_lines.append(line)
    return tuple(section_lines)


def _parse_value_response(raw_response: str | None, pattern: re.Pattern[str]) -> tuple[int | None, str]:
    if raw_response is None or not raw_response.strip():
        return None, "Current value unavailable on this firmware."

    lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(lines).casefold()
    if "unknown command" in normalized_text:
        return None, "Current value unavailable on this firmware."
    if "placeholder" in normalized_text:
        return None, "Controller reports this command as a placeholder."

    for line in lines:
        match = pattern.search(line)
        if match is not None:
            return int(match.group("value")), ""
        if line.isdigit():
            return int(line), ""

    return None, "Controller returned an unexpected format for this value."
