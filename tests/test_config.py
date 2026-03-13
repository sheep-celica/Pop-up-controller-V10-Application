from popup_controller.config import AppSettings


def test_default_settings() -> None:
    settings = AppSettings()

    assert settings.default_baudrate == 115200
    assert settings.controller_probe_command == "help"
    assert settings.controller_probe_response_fragment == "Available commands:"
    assert settings.serial_poll_interval_ms > 0