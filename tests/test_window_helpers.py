from popup_controller.ui.window_helpers import calculate_initial_window_size



def test_calculate_initial_window_size_grows_on_large_screen() -> None:
    size = calculate_initial_window_size(980, 640, available_width=1920, available_height=1080)

    assert size.width() == 1382
    assert size.height() == 907



def test_calculate_initial_window_size_stays_within_small_screen_limits() -> None:
    size = calculate_initial_window_size(980, 640, available_width=800, available_height=600)

    assert size.width() == 720
    assert size.height() == 520
