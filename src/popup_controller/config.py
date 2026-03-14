from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

from popup_controller import __version__


def _default_runtime_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def _default_package_directory() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root is not None:
            return Path(bundle_root).resolve() / "popup_controller"
        return Path(sys.executable).resolve().parent / "popup_controller"
    return Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_name: str = "Pop-up Controller"
    organization_name: str = "Sheep"
    app_version: str = __version__
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
    remote_mapping_reference_image_path: Path = field(
        default_factory=lambda: _default_package_directory() / "assets" / "remote_mapping.png"
    )
    icon_path: Path = field(default_factory=lambda: _default_package_directory() / "assets" / "pop_up_icon.ico")

    @property
    def app_display_name(self) -> str:
        return f"{self.app_name} v{self.app_version}"
