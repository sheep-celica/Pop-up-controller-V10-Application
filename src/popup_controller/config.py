from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys


def _default_runtime_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_name: str = "Pop-up Controller"
    organization_name: str = "Sheep"
    default_baudrate: int = 115200
    serial_timeout_seconds: float = 0.1
    serial_poll_interval_ms: int = 150
    controller_probe_command: str = "help"
    controller_probe_response_fragment: str = "Available commands:"
    controller_probe_warmup_seconds: float = 1.5
    controller_probe_window_seconds: float = 1.2
    default_window_width: int = 980
    default_window_height: int = 640
    firmware_directory: Path = field(default_factory=lambda: _default_runtime_directory() / "firmware")
