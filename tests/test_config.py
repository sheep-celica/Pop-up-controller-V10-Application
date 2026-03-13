from popup_controller import __version__
from popup_controller.config import AppSettings


def test_default_settings() -> None:
    settings = AppSettings()

    assert settings.app_version == __version__
    assert settings.app_display_name == f"Pop-up Controller v{__version__}"
    assert settings.default_baudrate == 115200
    assert settings.controller_probe_command == "help"
    assert settings.controller_probe_response_fragment == "Available commands:"
    assert settings.serial_poll_interval_ms > 0
    assert settings.icon_path.name == "pop_up_icon.ico"
