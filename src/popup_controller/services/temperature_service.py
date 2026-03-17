from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_TEMPERATURE_RE = re.compile(
    r"\b(?:Temperature|Temp)\s*[:=]\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*C\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TemperatureSnapshot:
    temperature_c: float | None
    status_hint: str
    raw_lines: tuple[str, ...]


def parse_temperature_snapshot(raw_response: str) -> TemperatureSnapshot:
    lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(lines).casefold()

    if not lines:
        return TemperatureSnapshot(
            temperature_c=None,
            status_hint="Controller did not return a temperature.",
            raw_lines=lines,
        )

    if "unknown command" in normalized_text:
        return TemperatureSnapshot(
            temperature_c=None,
            status_hint="Temperature readout unavailable on this firmware.",
            raw_lines=lines,
        )

    if "placeholder" in normalized_text:
        return TemperatureSnapshot(
            temperature_c=None,
            status_hint="Controller reports the temperature command as a placeholder.",
            raw_lines=lines,
        )

    for line in lines:
        match = _TEMPERATURE_RE.search(line)
        if match is None:
            continue
        return TemperatureSnapshot(
            temperature_c=float(match.group("value")),
            status_hint="",
            raw_lines=lines,
        )

    return TemperatureSnapshot(
        temperature_c=None,
        status_hint="Controller returned an unexpected temperature format.",
        raw_lines=lines,
    )


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines