# Architecture Notes

## Responsibilities

- `src/popup_controller/main.py`
  Application entrypoint used by both local development and packaging.
- `src/popup_controller/app.py`
  Creates and configures the `QApplication`.
- `src/popup_controller/config.py`
  Central place for app defaults such as baud rate and polling interval.
- `src/popup_controller/ui/main_window.py`
  Main desktop window and user interaction wiring.
- `src/popup_controller/services/serial_service.py`
  Serial transport abstraction using `pyserial`.
- `src/popup_controller/services/firmware_service.py`
  Future firmware flashing integration point.
- `src/popup_controller/utils/logging_config.py`
  Shared logging setup for development and troubleshooting.

## Why this layout

- keeps UI code separate from hardware communication
- gives firmware flashing its own service boundary
- works cleanly with `pyinstaller`, tests, and future protocol-specific modules
- scales to additional windows, dialogs, and device features without flattening everything into one file
