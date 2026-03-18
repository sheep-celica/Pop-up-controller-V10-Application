from __future__ import annotations

from popup_controller.app import create_application
from popup_controller.config import AppSettings
from popup_controller.ui.main_window import MainWindow
from popup_controller.ui.window_helpers import apply_initial_window_size
from popup_controller.utils.logging_config import configure_logging


def main() -> int:
    settings = AppSettings()
    configure_logging()

    app = create_application(settings)
    window = MainWindow(settings=settings)
    apply_initial_window_size(window, settings.default_window_width, settings.default_window_height)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
