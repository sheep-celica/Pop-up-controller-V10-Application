from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")


@dataclass(frozen=True, slots=True)
class ExternalExpanderSnapshot:
    state: str | None
    status_hint: str
    raw_lines: tuple[str, ...]


def parse_external_expander_snapshot(raw_response: str) -> ExternalExpanderSnapshot:
    lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(lines).casefold()

    if not lines:
        return ExternalExpanderSnapshot(
            state=None,
            status_hint="Controller did not return an external expander state.",
            raw_lines=lines,
        )

    if "unknown command" in normalized_text:
        return ExternalExpanderSnapshot(
            state=None,
            status_hint="External expander state unavailable on this firmware.",
            raw_lines=lines,
        )

    if "placeholder" in normalized_text:
        return ExternalExpanderSnapshot(
            state=None,
            status_hint="Controller reports the external expander command as a placeholder.",
            raw_lines=lines,
        )

    return ExternalExpanderSnapshot(
        state=lines[0],
        status_hint="",
        raw_lines=lines,
    )


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines
