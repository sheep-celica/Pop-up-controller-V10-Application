# Semantic Coloring Rules

## Purpose

This document defines the app-wide semantic color behavior for UI elements that represent controller health, feature state, or actionability.

The intent is to keep status communication visually consistent across dialogs, cards, labels, combo boxes, and future UI surfaces.

## Semantic States

- `good`
  Green. Use when the value is healthy, expected, enabled, connected, current, or otherwise in a normal/okay state.
- `caution`
  Yellow. Use when the value is not failing, but needs attention, is degraded, is outdated, or represents a warning-like state.
- `danger`
  Red. Use when the value is unavailable because a live read failed, is out of safe range, is disconnected, invalid, or otherwise clearly indicates a problem.
- unset / no semantic state
  Neutral default styling. Use before a live read has been attempted, or when no health judgment should be implied yet.

## Current Implementation

Semantic styling is currently applied through the shared Qt `semanticState` dynamic property in the UI theme.

The theme currently styles:

- `QFrame#metricCard`
- `QFrame#miniMetricCard`
- `QLabel`
- `QComboBox`

This allows both the container card and the value inside it to communicate the same state.

## Settings Dialog Rules

File: `src/popup_controller/ui/settings_dialog.py`

Current boolean settings in the Settings dialog use semantic colors for both the current-value cards and the editable TRUE/FALSE combo boxes.

Current mappings:

- `TRUE` -> `good`
- `FALSE` -> `danger`
- unavailable / unknown -> `caution`

This currently applies to:

- Sleepy eyes with headlights
- Remote inputs with light-switch

If additional boolean settings are added later, they should follow the same mapping unless there is a strong domain reason not to.

## Main Window Header Card Rules

File: `src/popup_controller/ui/main_window.py`

The five top status cards remain neutral until the app has actually attempted a live controller read for that specific card. GitHub release lookup alone must not turn controller data cards red.

### FW version

- `good`
  When live build info has been read successfully and the installed firmware is current.
- `caution`
  When live build info has been read successfully and the installed firmware is older than the latest GitHub release.
- `danger`
  When a live build-info read was attempted but failed or returned unusable data.
- neutral
  Before any live build-info read has been attempted.

When this card is `caution`, show an exclamation indicator with a tooltip explaining that a newer version is available.

### Build date

- Use the same semantic state as the FW version card.

### Controller state

- `good`
  Normal running state.
- `caution`
  `BENCH MODE`
- `danger`
  A live read failed or returned no usable status.
- neutral
  Before any live status read attempt.

### Remote expansion module

- `good`
  Connected / healthy / any normal non-error state returned by the controller.
- `danger`
  Live read failure, unavailable result, or returned state of `Not Connected` / disconnected.
- neutral
  Before any live read attempt.

### Temperature

- `good`
  Temperature is available and within the normal range.
- `danger`
  Live read failure, unavailable result, temperature below `-20 C`, or temperature above `40 C`.
- neutral
  Before any live read attempt.

## Implementation Guidance

- Prefer setting semantic state in the widget/controller code that owns the value rather than inferring it purely from text in the theme.
- Keep the business rule close to the service response handling so color changes stay aligned with parsed controller state.
- Use neutral styling instead of `danger` when no live read has been attempted yet.
- If a new surface presents the same controller fact as an existing surface, reuse the same semantic rule.
- If a future feature needs a different meaning for `TRUE` / `FALSE`, document that exception explicitly here.

## Files To Review When Changing These Rules

- `src/popup_controller/ui/theme.py`
- `src/popup_controller/ui/main_window.py`
- `src/popup_controller/ui/settings_dialog.py`
- `tests/test_main_window.py`
- `tests/test_settings_dialog.py`
