from PySide6.QtWidgets import QWidget

from popup_controller.ui.window_helpers import calculate_initial_window_size, create_form_field_label



def test_calculate_initial_window_size_grows_on_large_screen() -> None:
    size = calculate_initial_window_size(980, 640, available_width=1920, available_height=1080)

    assert size.width() == 1382
    assert size.height() == 907



def test_calculate_initial_window_size_stays_within_small_screen_limits() -> None:
    size = calculate_initial_window_size(980, 640, available_width=800, available_height=600)

    assert size.width() == 720
    assert size.height() == 520


def test_create_form_field_label_uses_shared_object_name(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    label = create_form_field_label("COM port", parent)

    assert label.objectName() == "formFieldLabel"
