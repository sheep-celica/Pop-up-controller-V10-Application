# Architecture Notes

Use the top-level [README.md](../README.md) for setup, packaging, and release workflow details.
Use the [Semantic Coloring Rules](semantic-coloring.md) document for UI state-color behavior.

## Purpose

This application is split so controller communication, response parsing, and desktop UI concerns stay separate.

The main architectural goal is to keep protocol logic out of widgets while still letting the main window and dialogs compose live controller workflows cleanly.

## Main Responsibilities

- `src/popup_controller/main.py`
  Application entrypoint used for local execution and packaged startup.
- `src/popup_controller/app.py`
  Creates and configures the `QApplication`, including shared app setup.
- `src/popup_controller/config.py`
  Central runtime configuration, packaged-path handling, firmware release URL, and default app settings.
- `src/popup_controller/ui/`
  Main window, dialogs, section metadata, theme behavior, and shared widget/window helpers.
- `src/popup_controller/services/`
  Serial communication, firmware flashing, GitHub firmware release lookup/download, and response parsing for controller-facing features.
- `src/popup_controller/utils/`
  Shared utilities such as logging configuration.

## UI and Service Boundary

- Keep controller commands, serial transport, and response parsing in `services/`.
- Keep layout, interaction flow, and presentation state in `ui/`.
- `MainWindow` is the main integration point that wires services into the desktop workflow.
- When a feature talks to the controller, prefer extending an existing focused service or adding a new one instead of embedding protocol details in a dialog.

## Runtime Structure

- The app supports both source execution and frozen PyInstaller builds, so path-sensitive behavior should stay centralized in `config.py`.
- Firmware release discovery currently targets GitHub releases from the Pop-up Controller V10 firmware repository.
- Firmware flashing is treated as a service boundary so packaging and flashing behavior can evolve without spreading tool-specific logic across the UI.

## Change Guidance

- Add or extend tests in `tests/` when introducing controller-facing features or new UI workflows.
- If a change affects packaging inputs, also review the PyInstaller spec, packaging scripts, and copied distribution assets.
- If a change affects firmware release/version behavior, also review the release workflow and firmware release service/tests.
- If a change affects UI semantic status presentation, keep the implementation aligned with [Semantic Coloring Rules](semantic-coloring.md).
