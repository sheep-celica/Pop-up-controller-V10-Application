from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_RUNTIME_RE = re.compile(r"Total runtime: (?P<seconds>\d+) s \((?P<days>[0-9.]+) days\)")
_SIDE_RE = re.compile(
    r"(?P<side>RH|LH) cycles / errors / move: (?P<cycles>\d+) / (?P<errors>\d+) / (?P<move_ms>\d+) ms"
)
_BUTTONS_RE = re.compile(r"Buttons RH/LH/BH: (?P<rh>\d+) / (?P<lh>\d+) / (?P<both>\d+)")
_REMOTE_RE = re.compile(r"Remote 1/2/3/4: (?P<r1>\d+) / (?P<r2>\d+) / (?P<r3>\d+) / (?P<r4>\d+)")


class StatisticsParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SideStatistics:
    cycles: int
    errors: int
    move_time_ms: int


@dataclass(frozen=True, slots=True)
class InputStatistics:
    button_rh: int
    button_lh: int
    button_both: int
    remote_1: int
    remote_2: int
    remote_3: int
    remote_4: int


@dataclass(frozen=True, slots=True)
class StatisticsSnapshot:
    boot_count: int
    total_runtime_seconds: int
    total_runtime_days: float
    rh_side: SideStatistics
    lh_side: SideStatistics
    inputs: InputStatistics
    raw_lines: tuple[str, ...]


def parse_statistics_snapshot(raw_response: str) -> StatisticsSnapshot:
    lines = tuple(_normalize_lines(raw_response))

    boot_count = _parse_boot_count(lines)
    total_runtime_seconds, total_runtime_days = _parse_runtime(lines)
    rh_side = _parse_side(lines, "RH")
    lh_side = _parse_side(lines, "LH")
    inputs = _parse_inputs(lines)

    return StatisticsSnapshot(
        boot_count=boot_count,
        total_runtime_seconds=total_runtime_seconds,
        total_runtime_days=total_runtime_days,
        rh_side=rh_side,
        lh_side=lh_side,
        inputs=inputs,
        raw_lines=lines,
    )


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines


def _parse_boot_count(lines: tuple[str, ...]) -> int:
    line = _find_line(lines, "Boot count:")
    try:
        return int(line.split(":", maxsplit=1)[1].strip())
    except (IndexError, ValueError) as exc:
        raise StatisticsParseError(f"Unable to parse boot count from: {line}") from exc


def _parse_runtime(lines: tuple[str, ...]) -> tuple[int, float]:
    line = _find_line(lines, "Total runtime:")
    match = _RUNTIME_RE.search(line)
    if match is None:
        raise StatisticsParseError(f"Unable to parse total runtime from: {line}")

    return int(match.group("seconds")), float(match.group("days"))


def _parse_side(lines: tuple[str, ...], side: str) -> SideStatistics:
    line = _find_line(lines, f"{side} cycles / errors / move:")
    match = _SIDE_RE.search(line)
    if match is None:
        raise StatisticsParseError(f"Unable to parse {side} side statistics from: {line}")

    return SideStatistics(
        cycles=int(match.group("cycles")),
        errors=int(match.group("errors")),
        move_time_ms=int(match.group("move_ms")),
    )


def _parse_inputs(lines: tuple[str, ...]) -> InputStatistics:
    buttons_line = _find_line(lines, "Buttons RH/LH/BH:")
    remote_line = _find_line(lines, "Remote 1/2/3/4:")

    buttons_match = _BUTTONS_RE.search(buttons_line)
    remote_match = _REMOTE_RE.search(remote_line)
    if buttons_match is None:
        raise StatisticsParseError(f"Unable to parse button usage from: {buttons_line}")
    if remote_match is None:
        raise StatisticsParseError(f"Unable to parse remote usage from: {remote_line}")

    return InputStatistics(
        button_rh=int(buttons_match.group("rh")),
        button_lh=int(buttons_match.group("lh")),
        button_both=int(buttons_match.group("both")),
        remote_1=int(remote_match.group("r1")),
        remote_2=int(remote_match.group("r2")),
        remote_3=int(remote_match.group("r3")),
        remote_4=int(remote_match.group("r4")),
    )


def _find_line(lines: tuple[str, ...], prefix: str) -> str:
    for line in lines:
        if line.startswith(prefix):
            return line

    raise StatisticsParseError(f"Expected line starting with '{prefix}' was not found.")