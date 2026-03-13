from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")


@dataclass(frozen=True, slots=True)
class ControllerStatusSnapshot:
    state: str | None
    status_hint: str
    raw_lines: tuple[str, ...]


def parse_controller_status_snapshot(raw_response: str) -> ControllerStatusSnapshot:
    lines = tuple(_normalize_lines(raw_response))
    normalized_text = " ".join(lines).casefold()

    if not lines:
        return ControllerStatusSnapshot(
            state=None,
            status_hint="Controller did not return a status.",
            raw_lines=lines,
        )

    if "unknown command" in normalized_text:
        return ControllerStatusSnapshot(
            state=None,
            status_hint="Controller status unavailable on this firmware.",
            raw_lines=lines,
        )

    if "placeholder" in normalized_text:
        return ControllerStatusSnapshot(
            state=None,
            status_hint="Controller reports the status command as a placeholder.",
            raw_lines=lines,
        )

    if "bench mode" in normalized_text:
        return ControllerStatusSnapshot(
            state="BENCH MODE",
            status_hint="",
            raw_lines=lines,
        )

    if re.search(r"\brunning\b", normalized_text):
        return ControllerStatusSnapshot(
            state="RUNNING",
            status_hint="",
            raw_lines=lines,
        )

    return ControllerStatusSnapshot(
        state=None,
        status_hint="Controller returned an unexpected status format.",
        raw_lines=lines,
    )


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines
