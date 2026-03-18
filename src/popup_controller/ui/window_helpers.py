from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

DEFAULT_WINDOW_WIDTH_RATIO = 0.72
DEFAULT_WINDOW_HEIGHT_RATIO = 0.84
DEFAULT_SCREEN_MARGIN_PX = 80
DEFAULT_MAX_WINDOW_WIDTH = 1500
DEFAULT_MAX_WINDOW_HEIGHT = 1200


def calculate_initial_window_size(
    preferred_width: int,
    preferred_height: int,
    *,
    available_width: int,
    available_height: int,
    width_ratio: float = DEFAULT_WINDOW_WIDTH_RATIO,
    height_ratio: float = DEFAULT_WINDOW_HEIGHT_RATIO,
    screen_margin_px: int = DEFAULT_SCREEN_MARGIN_PX,
    max_width: int = DEFAULT_MAX_WINDOW_WIDTH,
    max_height: int = DEFAULT_MAX_WINDOW_HEIGHT,
) -> QSize:
    usable_width = min(max_width, max(240, available_width - screen_margin_px), available_width)
    usable_height = min(max_height, max(240, available_height - screen_margin_px), available_height)

    target_width = min(usable_width, max(preferred_width, round(available_width * width_ratio)))
    target_height = min(usable_height, max(preferred_height, round(available_height * height_ratio)))
    return QSize(target_width, target_height)



def apply_initial_window_size(
    widget: QWidget,
    preferred_width: int,
    preferred_height: int,
    *,
    width_ratio: float = DEFAULT_WINDOW_WIDTH_RATIO,
    height_ratio: float = DEFAULT_WINDOW_HEIGHT_RATIO,
    screen_margin_px: int = DEFAULT_SCREEN_MARGIN_PX,
    max_width: int = DEFAULT_MAX_WINDOW_WIDTH,
    max_height: int = DEFAULT_MAX_WINDOW_HEIGHT,
) -> QSize:
    screen = _screen_for_widget(widget)
    if screen is None:
        size = QSize(preferred_width, preferred_height)
        widget.resize(size)
        return size

    available_geometry = screen.availableGeometry()
    size = calculate_initial_window_size(
        preferred_width,
        preferred_height,
        available_width=available_geometry.width(),
        available_height=available_geometry.height(),
        width_ratio=width_ratio,
        height_ratio=height_ratio,
        screen_margin_px=screen_margin_px,
        max_width=max_width,
        max_height=max_height,
    )
    widget.resize(size)
    return size



def create_scrollable_dialog_layout(
    dialog: QWidget,
    *,
    margin: int = 18,
    spacing: int = 12,
) -> tuple[QVBoxLayout, QVBoxLayout, QScrollArea]:
    root_layout = QVBoxLayout(dialog)
    root_layout.setContentsMargins(margin, margin, margin, margin)
    root_layout.setSpacing(spacing)

    scroll_area = QScrollArea(dialog)
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    content_widget = QWidget(scroll_area)
    content_layout = QVBoxLayout(content_widget)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(spacing)

    scroll_area.setWidget(content_widget)
    root_layout.addWidget(scroll_area, stretch=1)
    return root_layout, content_layout, scroll_area



def _screen_for_widget(widget: QWidget) -> QScreen | None:
    parent = widget.parentWidget()
    if parent is not None and parent.window().screen() is not None:
        return parent.window().screen()

    if widget.screen() is not None:
        return widget.screen()

    handle = widget.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()

    return QGuiApplication.primaryScreen()
