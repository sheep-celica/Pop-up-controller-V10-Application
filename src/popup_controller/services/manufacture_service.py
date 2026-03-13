from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
import re


_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d+\]\s*")
_KEY_NORMALIZER_RE = re.compile(r"[^a-z0-9]+")
_ISO_DATE_RE = re.compile(r"(?P<value>\d{4}-\d{2}-\d{2})")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "serial_number": ("Serial Number",),
    "board_serial": ("Board Serial",),
    "board_revision": ("Board Revision", "Board Rev"),
    "car_model": ("Car Model", "Vehicle Model"),
    "manufacture_date": ("Manufacture Date", "Manufactured Date", "Production Date"),
    "initial_firmware_version": ("Initial FW Version", "Initial Firmware Version"),
}

_EMPTY_VALUE_MARKERS = {"", "empty", "notset", "unset"}


@dataclass(frozen=True, slots=True)
class ManufactureField:
    value: str | None
    reported: bool

    @property
    def compact_display(self) -> str:
        if self.value is not None:
            return self.value
        return "Empty" if self.reported else "Unavailable"

    @property
    def status_hint(self) -> str:
        if self.value is not None:
            return ""
        return "No value stored on controller" if self.reported else "Not reported by this firmware"


@dataclass(frozen=True, slots=True)
class ControllerAge:
    years: int
    months: int
    days: int

    @property
    def display(self) -> str:
        return (
            f"{self.years} {_format_unit(self.years, 'year')}, "
            f"{self.months} {_format_unit(self.months, 'month')}, "
            f"{self.days} {_format_unit(self.days, 'day')} old"
        )


@dataclass(frozen=True, slots=True)
class ManufactureSnapshot:
    serial_number: ManufactureField
    board_serial: ManufactureField
    board_revision: ManufactureField
    car_model: ManufactureField
    manufacture_date: ManufactureField
    initial_firmware_version: ManufactureField
    raw_lines: tuple[str, ...]

    @property
    def reported_field_count(self) -> int:
        return sum(
            1
            for field in (
                self.serial_number,
                self.board_serial,
                self.board_revision,
                self.car_model,
                self.manufacture_date,
                self.initial_firmware_version,
            )
            if field.reported
        )


_FIELD_NAME_BY_KEY = {
    _KEY_NORMALIZER_RE.sub("", alias.casefold()): field_name
    for field_name, aliases in _FIELD_ALIASES.items()
    for alias in aliases
}


def parse_manufacture_snapshot(raw_response: str) -> ManufactureSnapshot:
    lines = tuple(_normalize_lines(raw_response))
    parsed_fields: dict[str, ManufactureField] = {}

    for line in lines:
        if ":" not in line:
            continue

        label, raw_value = line.split(":", maxsplit=1)
        field_name = _FIELD_NAME_BY_KEY.get(_normalize_key(label))
        if field_name is None:
            continue

        parsed_fields[field_name] = ManufactureField(
            value=_normalize_field_value(raw_value),
            reported=True,
        )

    return ManufactureSnapshot(
        serial_number=parsed_fields.get("serial_number", ManufactureField(value=None, reported=False)),
        board_serial=parsed_fields.get("board_serial", ManufactureField(value=None, reported=False)),
        board_revision=parsed_fields.get("board_revision", ManufactureField(value=None, reported=False)),
        car_model=parsed_fields.get("car_model", ManufactureField(value=None, reported=False)),
        manufacture_date=parsed_fields.get("manufacture_date", ManufactureField(value=None, reported=False)),
        initial_firmware_version=parsed_fields.get(
            "initial_firmware_version",
            ManufactureField(value=None, reported=False),
        ),
        raw_lines=lines,
    )


def try_parse_manufacture_date(field: ManufactureField | str | None) -> date | None:
    raw_value = field.value if isinstance(field, ManufactureField) else field
    if raw_value is None:
        return None

    cleaned = raw_value.strip()
    if not cleaned:
        return None

    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        match = _ISO_DATE_RE.search(cleaned)
        if match is None:
            return None
        try:
            return date.fromisoformat(match.group("value"))
        except ValueError:
            return None


def calculate_controller_age(manufacture_date: date, reference_date: date | None = None) -> ControllerAge | None:
    today = reference_date or date.today()
    if manufacture_date > today:
        return None

    years = today.year - manufacture_date.year
    months = today.month - manufacture_date.month
    days = today.day - manufacture_date.day

    if days < 0:
        previous_month = today.month - 1 or 12
        previous_month_year = today.year if today.month != 1 else today.year - 1
        days += monthrange(previous_month_year, previous_month)[1]
        months -= 1

    if months < 0:
        months += 12
        years -= 1

    return ControllerAge(years=years, months=months, days=days)


def _normalize_lines(raw_response: str) -> list[str]:
    normalized_lines: list[str] = []
    for line in raw_response.splitlines():
        cleaned = _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        if cleaned:
            normalized_lines.append(cleaned)
    return normalized_lines


def _normalize_key(value: str) -> str:
    return _KEY_NORMALIZER_RE.sub("", value.casefold())


def _normalize_field_value(raw_value: str) -> str | None:
    cleaned = raw_value.strip()
    if not cleaned:
        return None

    if _normalize_key(cleaned) in _EMPTY_VALUE_MARKERS:
        return None

    return cleaned


def _format_unit(value: int, singular: str) -> str:
    return singular if value == 1 else f"{singular}s"