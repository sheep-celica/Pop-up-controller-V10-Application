# Changes Since Last Release

Last tagged release: `v1.2.0`

## Unreleased

- 2026-03-27: Added a new main-window `Export support file` action that collects controller summary data, settings, statistics, stored errors, manufacture data, firmware release metadata, and the recent activity-log tail into a single JSON report for support/debugging.
- 2026-03-27: Updated the GitHub Actions release packaging workflow to use `actions/upload-artifact@v6` in the remaining older step. This keeps the release build pipeline aligned with the newer Node.js 24-based action versions already used elsewhere in the workflow.
