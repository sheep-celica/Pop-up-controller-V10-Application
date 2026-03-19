from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QDoubleValidator, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.ui.remote_mapping_reference_dialog import RemoteMappingReferenceDialog
from popup_controller.ui.window_helpers import apply_initial_window_size
from popup_controller.services.settings_service import (
    SettingsSnapshot,
    parse_battery_voltage_response,
    parse_settings_snapshot,
)


REMOTE_INPUT_LABELS = ("RH Wink", "LH Wink", "Both Wink", "Toggle Sleepy Eye Mode")
FULL_SETTINGS_IDLE_TIMEOUT_SECONDS = 0.20
SINGLE_VALUE_IDLE_TIMEOUT_SECONDS = 0.15


class SettingsDialog(QDialog):
    def __init__(
        self,
        serial_service: SerialService,
        parent: QWidget | None = None,
        reference_image_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self.reference_image_path = reference_image_path or Path(__file__).resolve().parent.parent / "assets" / "remote_mapping.png"
        self._busy = False
        self._initial_load_scheduled = False

        self.setWindowTitle("Settings")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel("Settings", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "This dialog loads live controller settings when it opens. Each section shows the current controller state first, then separates the new values you can write back.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Loading controller settings...", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.scroll_area = self._build_scroll_area()
        buttons = self._build_buttons()

        root_layout.addWidget(title_label)
        root_layout.addWidget(summary_label)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.loading_frame)
        root_layout.addWidget(self.scroll_area, stretch=1)
        root_layout.addWidget(buttons)

        self._set_busy(True, "Loading controller settings...")
        apply_initial_window_size(self, 920, 780)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._initial_load_scheduled:
            self._initial_load_scheduled = True
            QTimer.singleShot(75, self.load_settings)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Loading controller settings...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_scroll_area(self) -> QScrollArea:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.content_widget = QWidget(scroll_area)
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.battery_group = self._build_battery_group()
        self.sleepy_eye_group = self._build_sleepy_eye_group()
        self.remote_inputs_with_light_switch_group = self._build_remote_inputs_with_light_switch_group()
        self.idle_power_group = self._build_idle_power_group()
        self.min_state_group = self._build_min_state_group()
        self.sensing_delay_group = self._build_sensing_delay_group()
        self.remote_mapping_group = self._build_remote_mapping_group()
        self.timing_group = self._build_timing_group()

        content_layout.addWidget(self.battery_group)
        content_layout.addWidget(self.sleepy_eye_group)
        content_layout.addWidget(self.remote_inputs_with_light_switch_group)
        content_layout.addWidget(self.idle_power_group)
        content_layout.addWidget(self.min_state_group)
        content_layout.addWidget(self.sensing_delay_group)
        content_layout.addWidget(self.remote_mapping_group)
        content_layout.addWidget(self.timing_group)
        content_layout.addStretch(1)

        scroll_area.setWidget(self.content_widget)
        return scroll_area

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.refresh_button = QPushButton("Refresh settings", self)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        self.refresh_button.clicked.connect(lambda: self.load_settings())
        return buttons

    def _build_battery_group(self) -> QGroupBox:
        group = QGroupBox("Battery voltage calibration", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Calibration A", "battery_a", "current constant"))
        current_row.addWidget(self._create_metric_card("Calibration B", "battery_b", "current constant"))
        current_row.addWidget(self._create_metric_card("Live voltage", "battery_voltage", "latest controller reading"))
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "Use the new calibration constants you want to store. The live voltage button only refreshes the current reading.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.battery_a_input = QLineEdit(editor)
        self.battery_b_input = QLineEdit(editor)
        self.battery_a_input.setValidator(QDoubleValidator(-9999.0, 9999.0, 6, self))
        self.battery_b_input.setValidator(QDoubleValidator(-9999.0, 9999.0, 6, self))
        self.battery_update_button = QPushButton("Update constants", editor)
        self.read_voltage_button = QPushButton("Read voltage", editor)

        editor_layout.addWidget(QLabel("New a", editor), 1, 0)
        editor_layout.addWidget(self.battery_a_input, 1, 1)
        editor_layout.addWidget(QLabel("New b", editor), 1, 2)
        editor_layout.addWidget(self.battery_b_input, 1, 3)
        editor_layout.addWidget(self.battery_update_button, 2, 2)
        editor_layout.addWidget(self.read_voltage_button, 2, 3)

        self.battery_update_button.clicked.connect(self.update_battery_calibration)
        self.read_voltage_button.clicked.connect(self.read_voltage)
        layout.addWidget(editor)
        return group

    def _build_sleepy_eye_group(self) -> QGroupBox:
        group = QGroupBox("Sleepy eyes with headlights", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Current value", "sleepy_eye", "controller flag"))
        current_row.addStretch(1)
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "Choose the value you want the controller to store for sleepy-eye mode while headlights are on.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.sleepy_eye_combo = QComboBox(editor)
        self.sleepy_eye_combo.addItems(["TRUE", "FALSE"])
        self.sleepy_eye_update_button = QPushButton("Update setting", editor)

        editor_layout.addWidget(QLabel("New value", editor), 1, 0)
        editor_layout.addWidget(self.sleepy_eye_combo, 1, 1)
        editor_layout.addWidget(self.sleepy_eye_update_button, 1, 3)

        self.sleepy_eye_update_button.clicked.connect(self.update_sleepy_eye_setting)
        layout.addWidget(editor)
        return group

    def _build_remote_inputs_with_light_switch_group(self) -> QGroupBox:
        group = QGroupBox("Remote inputs with light-switch", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Current value", "remote_inputs_with_headlights", "controller flag"))
        current_row.addStretch(1)
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "Choose whether the controller should accept remote inputs while the light-switch is being used.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.remote_inputs_with_headlights_combo = QComboBox(editor)
        self.remote_inputs_with_headlights_combo.addItems(["TRUE", "FALSE"])
        self.remote_inputs_with_headlights_update_button = QPushButton("Update setting", editor)

        editor_layout.addWidget(QLabel("New value", editor), 1, 0)
        editor_layout.addWidget(self.remote_inputs_with_headlights_combo, 1, 1)
        editor_layout.addWidget(self.remote_inputs_with_headlights_update_button, 1, 3)

        self.remote_inputs_with_headlights_update_button.clicked.connect(
            self.update_remote_inputs_with_headlights_setting
        )
        layout.addWidget(editor)
        return group

    def _build_idle_power_group(self) -> QGroupBox:
        group = QGroupBox("Idle time to power off", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Seconds", "idle_seconds", "current timeout"))
        current_row.addWidget(self._create_metric_card("Days", "idle_days", "converted display"))
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "Set the new timeout using separate day, hour, minute, and second fields. The controller receives the total seconds.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.idle_days_spin = QSpinBox(editor)
        self.idle_days_spin.setRange(0, 3650)
        self.idle_hours_spin = QSpinBox(editor)
        self.idle_hours_spin.setRange(0, 23)
        self.idle_minutes_spin = QSpinBox(editor)
        self.idle_minutes_spin.setRange(0, 59)
        self.idle_seconds_spin = QSpinBox(editor)
        self.idle_seconds_spin.setRange(0, 59)
        self.idle_update_button = QPushButton("Update idle timeout", editor)

        editor_layout.addWidget(QLabel("Days", editor), 1, 0)
        editor_layout.addWidget(self.idle_days_spin, 1, 1)
        editor_layout.addWidget(QLabel("Hours", editor), 1, 2)
        editor_layout.addWidget(self.idle_hours_spin, 1, 3)
        editor_layout.addWidget(QLabel("Minutes", editor), 2, 0)
        editor_layout.addWidget(self.idle_minutes_spin, 2, 1)
        editor_layout.addWidget(QLabel("Seconds", editor), 2, 2)
        editor_layout.addWidget(self.idle_seconds_spin, 2, 3)
        editor_layout.addWidget(self.idle_update_button, 3, 3)

        self.idle_update_button.clicked.connect(self.update_idle_timeout)
        layout.addWidget(editor)
        return group

    def _build_min_state_group(self) -> QGroupBox:
        group = QGroupBox("Minimum time to change states", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Milliseconds", "min_state", "controller-reported value"))
        current_row.addStretch(1)
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "This is the minimum amount of time a pop-up state signal needs to persist (UP/DOWN) before it becomes valid.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.min_state_spin = QSpinBox(editor)
        self.min_state_spin.setRange(0, 600000)
        self.min_state_update_button = QPushButton("Update value", editor)

        editor_layout.addWidget(QLabel("New milliseconds", editor), 1, 0)
        editor_layout.addWidget(self.min_state_spin, 1, 1)
        editor_layout.addWidget(self.min_state_update_button, 1, 3)

        self.min_state_update_button.clicked.connect(self.update_min_state_persist)
        layout.addWidget(editor)
        return group

    def _build_sensing_delay_group(self) -> QGroupBox:
        group = QGroupBox("Pop-up sensing delay", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Microseconds", "sensing_delay", "controller-reported value"))
        current_row.addStretch(1)
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "This is the sensing delay used before the controller evaluates the pop-up position sensing input.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.sensing_delay_spin = QSpinBox(editor)
        self.sensing_delay_spin.setRange(0, 1000000)
        self.sensing_delay_update_button = QPushButton("Update value", editor)

        editor_layout.addWidget(QLabel("New microseconds", editor), 1, 0)
        editor_layout.addWidget(self.sensing_delay_spin, 1, 1)
        editor_layout.addWidget(self.sensing_delay_update_button, 1, 3)

        self.sensing_delay_update_button.clicked.connect(self.update_sensing_delay)
        layout.addWidget(editor)
        return group
    def _build_remote_mapping_group(self) -> QGroupBox:
        group = QGroupBox("Remote input mapping", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_metric_card("Current mapping", "remote_mapping", "controller-reported mapping"))
        current_row.addStretch(1)
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("New settings", group))
        editor = self._create_editor_card(group)
        editor_layout = QGridLayout(editor)
        editor_layout.setHorizontalSpacing(12)
        editor_layout.setVerticalSpacing(10)
        editor_layout.addWidget(
            self._create_section_note(
                "Choose a unique input number between 1 and 4 for each remote action. Duplicate values are not allowed. Use the reference button if you need the physical button layout image.",
                editor,
            ),
            0,
            0,
            1,
            4,
        )

        self.remote_input_combos = [self._create_remote_mapping_combo(editor) for _ in range(4)]
        self.remote_mapping_reference_button = QPushButton("View reference image", editor)
        self.remote_mapping_update_button = QPushButton("Update mapping", editor)

        for index, (label_text, combo) in enumerate(zip(REMOTE_INPUT_LABELS, self.remote_input_combos), start=1):
            row = 1 + (index - 1) // 2
            column = ((index - 1) % 2) * 2
            editor_layout.addWidget(QLabel(label_text, editor), row, column)
            editor_layout.addWidget(combo, row, column + 1)

        editor_layout.addWidget(self.remote_mapping_reference_button, 3, 2)
        editor_layout.addWidget(self.remote_mapping_update_button, 3, 3)

        self.remote_mapping_reference_button.clicked.connect(self.show_remote_mapping_reference)
        self.remote_mapping_update_button.clicked.connect(self.update_remote_mapping)
        layout.addWidget(editor)
        return group

    def _build_timing_group(self) -> QGroupBox:
        group = QGroupBox("Pop-up timing calibration", self.content_widget)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._create_section_heading("Current settings", group))
        current_row = QHBoxLayout()
        current_row.setSpacing(12)
        current_row.addWidget(self._create_timing_panel("RH calibration", "rh_timing", group))
        current_row.addWidget(self._create_timing_panel("LH calibration", "lh_timing", group))
        layout.addLayout(current_row)

        layout.addWidget(self._create_section_heading("Actions", group))
        editor = self._create_editor_card(group)
        editor_layout = QHBoxLayout(editor)
        editor_layout.setContentsMargins(14, 14, 14, 14)
        editor_layout.setSpacing(12)
        editor_layout.addWidget(
            self._create_section_note(
                "Use this maintenance action to clear the stored timing calibration. Some firmware versions still expose it as a placeholder command.",
                editor,
            ),
            stretch=1,
        )
        self.clear_timing_button = QPushButton("Clear timing calibration", editor)
        editor_layout.addWidget(self.clear_timing_button)

        self.clear_timing_button.clicked.connect(self.clear_timing_calibration)
        layout.addWidget(editor)
        return group

    def _create_metric_card(self, caption: str, key: str, suffix: str) -> QFrame:
        card = QFrame(self.content_widget)
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("metricCaption")

        value_label = QLabel("--", card)
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        suffix_label = QLabel(suffix, card)
        suffix_label.setObjectName("metricSuffix")
        suffix_label.setWordWrap(True)

        setattr(self, f"{key}_value", value_label)
        setattr(self, f"{key}_suffix", suffix_label)

        layout.addWidget(caption_label)
        layout.addWidget(value_label)
        layout.addWidget(suffix_label)
        layout.addStretch(1)
        return card

    def _create_timing_panel(self, title: str, key: str, parent: QWidget) -> QGroupBox:
        group = QGroupBox(title, parent)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        text_edit = QPlainTextEdit(group)
        text_edit.setReadOnly(True)
        text_edit.setMinimumHeight(200)
        setattr(self, f"{key}_text", text_edit)

        layout.addWidget(text_edit)
        return group

    def _create_editor_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("editorCard")
        return card

    def _create_section_heading(self, text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("sectionSubheading")
        return label

    def _create_section_note(self, text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("sectionNote")
        label.setWordWrap(True)
        return label

    def _create_remote_mapping_combo(self, parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItems(["1", "2", "3", "4"])
        return combo

    def load_settings(self, busy_message: str = "Loading controller settings...") -> None:
        if not self.serial_service.is_connected:
            self.status_label.setText("Connect to the controller before opening settings.")
            self._set_busy(False)
            return

        self._set_busy(True, busy_message)
        try:
            full_response = self.serial_service.request_text(
                "printEverything",
                idle_timeout_seconds=FULL_SETTINGS_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=4.0,
                progress_callback=self._process_loading_events,
            )
            if not full_response.strip():
                raise SerialConnectionError("The controller did not return any settings data.")

            idle_power_response = self.serial_service.request_text(
                "getIdleTimeToPowerOff",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            min_state_response = self.serial_service.request_text(
                "printPopUpMinStatePersistMs",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            remote_input_response = self.serial_service.request_text(
                "printRemoteInputPins",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            sensing_delay_response = self.serial_service.request_text(
                "printPopUpSensingDelayUs",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            remote_inputs_with_headlights_response = self.serial_service.request_text(
                "printRemoteInputsWithHeadlights",
                idle_timeout_seconds=SINGLE_VALUE_IDLE_TIMEOUT_SECONDS,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
            snapshot = parse_settings_snapshot(
                full_response,
                min_state_response,
                remote_input_response,
                idle_power_response,
                sensing_delay_response=sensing_delay_response,
                remote_inputs_with_headlights_response=remote_inputs_with_headlights_response,
            )
            self._apply_snapshot(snapshot)
            self.status_label.setText(self._build_status_message(snapshot))
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Settings", str(exc))
        finally:
            self._set_busy(False)

    def _apply_snapshot(self, snapshot: SettingsSnapshot) -> None:
        self._set_metric_card("battery_a", self._format_float(snapshot.battery_calibration_a, decimals=6), "current constant")
        self._set_metric_card("battery_b", self._format_float(snapshot.battery_calibration_b, decimals=6), "current constant")
        self._set_metric_card("battery_voltage", self._format_float(snapshot.battery_voltage_v, suffix=" V"), "latest controller reading")

        if snapshot.battery_calibration_a is not None:
            self.battery_a_input.setText(f"{snapshot.battery_calibration_a:.6f}")
        if snapshot.battery_calibration_b is not None:
            self.battery_b_input.setText(f"{snapshot.battery_calibration_b:.6f}")

        self._set_metric_card(
            "sleepy_eye",
            self._format_bool(snapshot.allow_sleepy_eye_with_headlights),
            "controller flag",
        )
        if snapshot.allow_sleepy_eye_with_headlights is not None:
            self.sleepy_eye_combo.setCurrentText("TRUE" if snapshot.allow_sleepy_eye_with_headlights else "FALSE")

        remote_inputs_with_headlights_suffix = snapshot.remote_inputs_with_headlights_status or "controller flag"
        self._set_metric_card(
            "remote_inputs_with_headlights",
            self._format_bool(snapshot.allow_remote_inputs_with_headlights),
            remote_inputs_with_headlights_suffix,
        )
        if snapshot.allow_remote_inputs_with_headlights is not None:
            self.remote_inputs_with_headlights_combo.setCurrentText(
                "TRUE" if snapshot.allow_remote_inputs_with_headlights else "FALSE"
            )

        self._set_metric_card(
            "idle_seconds",
            f"{snapshot.idle_power_off_seconds:,} s" if snapshot.idle_power_off_seconds is not None else "Unavailable",
            "current timeout",
        )
        self._set_metric_card(
            "idle_days",
            f"{snapshot.idle_power_off_days:.2f} days" if snapshot.idle_power_off_days is not None else "Unavailable",
            "converted display",
        )
        if snapshot.idle_power_off_seconds is not None:
            self._set_duration_inputs(snapshot.idle_power_off_seconds)

        min_state_value = f"{snapshot.min_state_persist_ms:,} ms" if snapshot.min_state_persist_ms is not None else "Unavailable"
        min_state_suffix = snapshot.min_state_persist_status or "controller-reported value"
        self._set_metric_card("min_state", min_state_value, min_state_suffix)
        if snapshot.min_state_persist_ms is not None:
            self.min_state_spin.setValue(snapshot.min_state_persist_ms)

        sensing_delay_value = f"{snapshot.sensing_delay_us:,} us" if snapshot.sensing_delay_us is not None else "Unavailable"
        sensing_delay_suffix = snapshot.sensing_delay_status or "controller-reported value"
        self._set_metric_card("sensing_delay", sensing_delay_value, sensing_delay_suffix)
        if snapshot.sensing_delay_us is not None:
            self.sensing_delay_spin.setValue(snapshot.sensing_delay_us)

        if snapshot.remote_input_mapping is None:
            self._set_metric_card("remote_mapping", "Unavailable", snapshot.remote_input_mapping_status)
        else:
            mapping_details = "\n".join(
                f"{label}: {value}" for label, value in zip(REMOTE_INPUT_LABELS, snapshot.remote_input_mapping)
            )
            self._set_metric_card("remote_mapping", "Available", mapping_details)
            for combo, value in zip(self.remote_input_combos, snapshot.remote_input_mapping):
                combo.setCurrentText(str(value))

        self.rh_timing_text.setPlainText(snapshot.rh_timing.display_text)
        self.lh_timing_text.setPlainText(snapshot.lh_timing.display_text)

    def _set_metric_card(self, key: str, value: str, suffix: str) -> None:
        getattr(self, f"{key}_value").setText(value)
        getattr(self, f"{key}_suffix").setText(suffix)

    def _build_status_message(self, snapshot: SettingsSnapshot) -> str:
        message = f"Settings refreshed from {self.serial_service.port_name}."
        warnings: list[str] = []
        if snapshot.allow_remote_inputs_with_headlights is None and snapshot.remote_inputs_with_headlights_status:
            warnings.append(snapshot.remote_inputs_with_headlights_status)
        if snapshot.min_state_persist_ms is None and snapshot.min_state_persist_status:
            warnings.append(snapshot.min_state_persist_status)
        if snapshot.sensing_delay_us is None and snapshot.sensing_delay_status:
            warnings.append(snapshot.sensing_delay_status)
        if snapshot.remote_input_mapping is None and snapshot.remote_input_mapping_status:
            warnings.append(snapshot.remote_input_mapping_status)
        if warnings:
            message += f" {' '.join(warnings)}"
        return message

    def update_battery_calibration(self) -> None:
        a_text = self.battery_a_input.text().strip()
        b_text = self.battery_b_input.text().strip()
        if not a_text or not b_text:
            QMessageBox.information(self, "Battery calibration", "Enter both calibration constants first.")
            return

        try:
            float(a_text)
            float(b_text)
        except ValueError:
            QMessageBox.warning(self, "Battery calibration", "Calibration constants must be valid numbers.")
            return

        self._submit_update_command(
            f"writeBatteryVoltageCalibration {a_text} {b_text}",
            "Updating battery voltage calibration...",
            "Battery calibration update failed",
        )

    def read_voltage(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before reading battery voltage.")
            return

        self._set_busy(True, "Reading battery voltage...")
        try:
            response = self.serial_service.request_text(
                "readBatteryVoltage",
                idle_timeout_seconds=0.7,
                max_duration_seconds=4.0,
                progress_callback=self._process_loading_events,
            )
            normalized = " ".join(line.strip() for line in response.splitlines() if line.strip())
            lowered = normalized.casefold()
            if any(marker in lowered for marker in ("unknown command", "placeholder", "failed", "invalid", "error")):
                self.status_label.setText(normalized or "Battery voltage read failed")
                QMessageBox.warning(self, "Battery voltage", normalized or "Battery voltage read failed")
                return

            battery_voltage_v = parse_battery_voltage_response(response)
            if battery_voltage_v is None:
                message = "The controller returned an unexpected battery voltage format."
                self.status_label.setText(message)
                QMessageBox.warning(self, "Battery voltage", message)
                return

            self._set_metric_card(
                "battery_voltage",
                self._format_float(battery_voltage_v, suffix=" V"),
                "5-reading average from controller",
            )
            self.status_label.setText(f"Battery voltage refreshed from {self.serial_service.port_name}.")
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Battery voltage", str(exc))
        finally:
            self._set_busy(False)

    def update_sleepy_eye_setting(self) -> None:
        value = self.sleepy_eye_combo.currentText().strip().lower()
        self._submit_update_command(
            f"writeSleepyEyeModeWithHeadlights {value}",
            "Updating sleepy-eye setting...",
            "Sleepy-eye setting update failed",
        )

    def update_remote_inputs_with_headlights_setting(self) -> None:
        value = self.remote_inputs_with_headlights_combo.currentText().strip().lower()
        self._submit_update_command(
            f"writeRemoteInputsWithHeadlights {value}",
            "Updating remote inputs with light-switch setting...",
            "Remote inputs with light-switch update failed",
        )

    def update_idle_timeout(self) -> None:
        total_seconds = self._current_duration_seconds()
        self._submit_update_command(
            f"writeIdleTimeToPowerOffSeconds {total_seconds}",
            "Updating idle power-off timeout...",
            "Idle timeout update failed",
        )

    def update_min_state_persist(self) -> None:
        milliseconds = self.min_state_spin.value()
        self._submit_update_command(
            f"writePopUpMinStatePersistMs {milliseconds}",
            "Updating minimum state persistence...",
            "Minimum state persistence update failed",
        )

    def update_sensing_delay(self) -> None:
        microseconds = self.sensing_delay_spin.value()
        self._submit_update_command(
            f"writePopUpSensingDelayUs {microseconds}",
            "Updating pop-up sensing delay...",
            "Pop-up sensing delay update failed",
        )

    def show_remote_mapping_reference(self) -> None:
        if not self.reference_image_path.is_file():
            QMessageBox.warning(
                self,
                "Remote mapping reference",
                f"Reference image not found: {self.reference_image_path}",
            )
            return

        dialog = RemoteMappingReferenceDialog(self.reference_image_path, self)
        dialog.exec()

    def update_remote_mapping(self) -> None:
        values = [int(combo.currentText()) for combo in self.remote_input_combos]
        if len(set(values)) != 4:
            QMessageBox.warning(
                self,
                "Remote input mapping",
                "Each remote action must use a unique input value between 1 and 4.",
            )
            return

        self._submit_update_command(
            f"setRemoteInputPins {values[0]} {values[1]} {values[2]} {values[3]}",
            "Updating remote input mapping...",
            "Remote input mapping update failed",
        )

    def clear_timing_calibration(self) -> None:
        confirmation = QMessageBox.question(
            self,
            "Clear timing calibration",
            "Clear the controller timing calibration now?",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._submit_update_command(
            "clearPopUptimingCalibration",
            "Clearing timing calibration...",
            "Timing calibration clear failed",
        )

    def _submit_update_command(self, command: str, busy_message: str, error_title: str) -> bool:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before sending settings updates.")
            return False

        self._set_busy(True, busy_message)
        try:
            response = self.serial_service.request_text(
                command,
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.5,
                progress_callback=self._process_loading_events,
            )
            normalized = " ".join(line.strip() for line in response.splitlines() if line.strip())
            lowered = normalized.casefold()

            if any(marker in lowered for marker in ("unknown command", "placeholder", "rejected", "failed", "invalid", "error", "duplicate")):
                self.status_label.setText(normalized or error_title)
                QMessageBox.warning(self, error_title, normalized or error_title)
                return False

            self.status_label.setText("Controller accepted the update. Refreshing live settings...")
            self.load_settings()
            return True
        except SerialConnectionError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, error_title, str(exc))
            return False
        finally:
            self._set_busy(False)

    def _set_duration_inputs(self, total_seconds: int) -> None:
        remaining = max(0, total_seconds)
        days, remaining = divmod(remaining, 86400)
        hours, remaining = divmod(remaining, 3600)
        minutes, seconds = divmod(remaining, 60)
        self.idle_days_spin.setValue(days)
        self.idle_hours_spin.setValue(hours)
        self.idle_minutes_spin.setValue(minutes)
        self.idle_seconds_spin.setValue(seconds)

    def _current_duration_seconds(self) -> int:
        return (
            self.idle_days_spin.value() * 86400
            + self.idle_hours_spin.value() * 3600
            + self.idle_minutes_spin.value() * 60
            + self.idle_seconds_spin.value()
        )

    def _format_float(self, value: float | None, suffix: str = "", decimals: int = 2) -> str:
        if value is None:
            return "Unavailable"
        return f"{value:.{decimals}f}{suffix}"

    def _format_bool(self, value: bool | None) -> str:
        if value is None:
            return "Unavailable"
        return "TRUE" if value else "FALSE"

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.scroll_area.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_loading_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
