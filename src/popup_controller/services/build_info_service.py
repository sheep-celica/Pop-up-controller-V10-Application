from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_FIRMWARE_VERSION_RE = re.compile(r"FW_VERSION=(?P<value>\S+)", re.IGNORECASE)
_BUILD_TIMESTAMP_RE = re.compile(r"BUILD_TIMESTAMP=(?P<value>\S+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BuildInfoSnapshot:
    firmware_version: str | None
    build_timestamp: str | None
    raw_lines: tuple[str, ...]

    @property
    def build_date(self) -> str | None:
        if self.build_timestamp is None:
            return None

        normalized = self.build_timestamp.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"

        try:
            parsed_timestamp = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        return parsed_timestamp.date().isoformat()


def parse_build_info_snapshot(raw_response: str) -> BuildInfoSnapshot:
    lines = tuple(_normalize_lines(raw_response))
    firmware_version = _parse_value(lines, _FIRMWARE_VERSION_RE)
    build_timestamp = _parse_value(lines, _BUILD_TIMESTAMP_RE)
    return BuildInfoSnapshot(
        firmware_version=firmware_version,
        build_timestamp=build_timestamp,
        raw_lines=lines,
    )


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines


def _parse_value(lines: tuple[str, ...], pattern: re.Pattern[str]) -> str | None:
    for line in lines:
        match = pattern.search(line)
        if match is None:
            continue
        return match.group("value")
    return None
