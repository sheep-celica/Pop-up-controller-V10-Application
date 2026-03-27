# AGENTS.md

## Purpose

This repository contains the Windows desktop application for the Pop-up Controller V10 board.

- The app is used by the project author to verify controller behavior, validate factory settings, and support bring-up/testing.
- The app is also used by customers to flash new firmware, change user settings, inspect errors, view statistics, and review manufacture data.
- The related board firmware repository is: https://github.com/sheep-celica/pop-up-controller-v10

## Tech Stack

- Python
- PySide6 desktop UI
- `pyserial` for controller communication
- `esptool` for ESP32 flashing
- `pytest` and `pytest-qt` for tests
- PyInstaller for Windows packaging

## Repository Layout

- `src/popup_controller/main.py`: application entrypoint
- `src/popup_controller/app.py`: `QApplication` creation and setup
- `src/popup_controller/config.py`: central app defaults, runtime paths, firmware release URL, and packaged asset paths
- `src/popup_controller/ui/`: main window, dialogs, shared section metadata, theming, and window helpers
- `src/popup_controller/services/`: serial communication, firmware flashing, GitHub firmware release lookup/download, and response parsing
- `src/popup_controller/utils/`: shared utilities such as logging configuration
- `src/popup_controller/assets/`: icons and bundled images used by the UI
- `tests/`: unit and UI-oriented tests, generally mirroring services, dialogs, and main window behavior
- `firmware/`: local firmware bundles that can be flashed or distributed with the packaged app
- `.github/workflows/`: GitHub Actions automation for release packaging
- `scripts/`: helper scripts for packaging, optional git-hook setup, and build-version injection
- `docs/architecture.md`: short architecture overview
- `docs/semantic-coloring.md`: semantic red/yellow/green UI behavior rules and current mappings
- `popup-controller.spec`: PyInstaller build spec

## Architecture Notes

- Keep controller communication and parsing logic in `services/`, not directly in UI widgets.
- Keep UI composition, user interaction, and state presentation in `ui/`.
- `MainWindow` is the integration point that wires services into the desktop workflow.
- Prefer extending an existing service or adding a new focused service when introducing controller commands or response parsing.
- When adding a new controller-facing feature, update the relevant UI surface and add or extend tests in `tests/`.
- Be careful with file paths and runtime behavior in `config.py`; this app supports both source execution and frozen PyInstaller builds.
- Firmware release behavior currently targets GitHub releases from the Pop-up Controller V10 firmware repository.
- UI semantic color behavior is documented in `docs/semantic-coloring.md`; keep detailed color rules there rather than in this file.

## Working In This Repo

- Assume Windows-first workflows unless the code clearly supports something broader.
- Prefer repo-root relative commands and paths in documentation and automation.
- Preserve the existing `src/` package layout.
- Avoid moving protocol details into dialogs or window classes.
- Maintain `CHANGES_SINCE_LAST_RELEASE.md` as a brief markdown bulletin of unreleased user-facing, workflow, packaging, or notable support-impacting changes since the latest git release tag.
- When your change meaningfully alters behavior, tooling, packaging, docs, or support workflow, update `CHANGES_SINCE_LAST_RELEASE.md` in the same change set with a short plain-language bullet.
- If you change packaging inputs, also review `popup-controller.spec`, `scripts/build_exe.ps1`, and any copied distribution assets.
- If you change versioning or release behavior, also review `scripts/build_version.py`, `.github/workflows/`, and the firmware release service/tests.
- If you add new user-visible sections or dialogs, review `src/popup_controller/ui/sections.py`, related dialog classes, and layout tests.

## Common Commands

Run from the repository root.

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
python -m popup_controller
python -m pytest
python -m pytest tests\test_main_window.py
python -m ruff check .
scripts\build_exe.ps1
scripts\build_exe.ps1 -SkipTests
```

## Testing Expectations

- Run targeted tests for the area you touch at minimum.
- Run `python -m pytest` after broader UI, firmware, packaging, or shared service changes when practical.
- For UI changes, prefer checking the related dialog or window tests in addition to service tests.
- If a change affects flashing or GitHub firmware lookup, review the firmware service and firmware release service tests.

## Keeping This File Consistent

If `AGENTS.md` becomes stale, incomplete, or inconsistent with the repository:

- Re-read `README.md`, `docs/architecture.md`, `pyproject.toml`, and the current top-level tree before editing it.
- Prefer describing the repo as it exists now, not as it used to exist or as a future plan.
- Update this file in the same change set as any structural, workflow, packaging, or test-layout changes that make it outdated.
- Remove or rewrite instructions that mention files, commands, features, or directories that no longer exist.
- Add newly important directories, scripts, or workflows once they become part of normal contributor or agent work.
- Keep instructions specific and actionable; avoid generic guidance that does not help with this repository.
- When uncertain, verify against the codebase first and state a narrow, factual rule instead of a broad assumption.

## Notifications

- Before sending your final user-facing response for a completed task, run `C:\Users\Sheep\AppData\Local\Python\pythoncore-3.14-64\python.exe .codex\tools\notify_client.py "Codex finished" "Task complete in this repository."` from the repository root to send the desktop notification.
- When you are blocked waiting for my approval or input, run `C:\Users\Sheep\AppData\Local\Python\pythoncore-3.14-64\python.exe .codex\tools\notify_client.py "Codex needs input" "Waiting for approval or more instructions."` from the repository root to send the desktop notification.
- If the notification command fails once, continue with the task and mention briefly that the notification failed.
