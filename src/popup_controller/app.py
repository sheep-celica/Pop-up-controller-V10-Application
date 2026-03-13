from __future__ import annotations

from PySide6.QtWidgets import QApplication

from popup_controller.config import AppSettings
from popup_controller.ui.theme import apply_dark_theme


def create_application(settings: AppSettings) -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(settings.app_name)
    app.setOrganizationName(settings.organization_name)
    apply_dark_theme(app)
    return app