from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.services.statistics_service import StatisticsParseError, StatisticsSnapshot, parse_statistics_snapshot


class StatisticsDialog(QDialog):
    def __init__(self, serial_service: SerialService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.serial_service = serial_service
        self._busy = False
        self._initial_load_scheduled = False

        self.setWindowTitle("Statistical Data")
        self.resize(760, 640)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        title_label = QLabel("Statistical Data", self)
        title_label.setObjectName("dialogTitle")

        summary_label = QLabel(
            "This dialog fetches live usage counters and lifetime statistics from the controller when it opens.",
            self,
        )
        summary_label.setObjectName("dialogSummary")
        summary_label.setWordWrap(True)

        self.status_label = QLabel("Loading controller statistics...", self)
        self.status_label.setObjectName("controllerBadge")
        self.status_label.setWordWrap(True)

        self.loading_frame = self._build_loading_frame()
        self.overview_group = self._build_overview_group()
        self.side_group = self._build_side_group()
        self.input_group = self._build_input_group()
        buttons = self._build_buttons()

        root_layout.addWidget(title_label)
        root_layout.addWidget(summary_label)
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.loading_frame)
        root_layout.addWidget(self.overview_group)
        root_layout.addWidget(self.side_group)
        root_layout.addWidget(self.input_group)
        root_layout.addStretch(1)
        root_layout.addWidget(buttons)

        self._set_busy(True, "Loading controller statistics...")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._initial_load_scheduled:
            self._initial_load_scheduled = True
            QTimer.singleShot(75, self.load_statistics)

    def _build_loading_frame(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("loadingFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Loading controller statistics...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(180)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _build_overview_group(self) -> QGroupBox:
        group = QGroupBox("Overview", self)
        layout = QHBoxLayout(group)
        layout.setSpacing(12)
        layout.addWidget(self._create_metric_card("Boot count", "--", "controller starts", "boot_count"))
        layout.addWidget(self._create_metric_card("Lifetime runtime", "--", "--", "runtime"))
        return group

    def _build_side_group(self) -> QGroupBox:
        group = QGroupBox("Headlight mechanisms", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.addWidget(self._create_side_box("RH", "rh"), 0, 0)
        layout.addWidget(self._create_side_box("LH", "lh"), 0, 1)
        return group

    def _build_input_group(self) -> QGroupBox:
        group = QGroupBox("Input activity", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        buttons_group = QGroupBox("Physical buttons", group)
        buttons_layout = QGridLayout(buttons_group)
        buttons_layout.setHorizontalSpacing(10)
        buttons_layout.addWidget(self._create_small_metric_card("Right button", "button_rh"), 0, 0)
        buttons_layout.addWidget(self._create_small_metric_card("Left button", "button_lh"), 0, 1)
        buttons_layout.addWidget(self._create_small_metric_card("Both buttons", "button_both"), 0, 2)

        remote_group = QGroupBox("Remote inputs", group)
        remote_layout = QGridLayout(remote_group)
        remote_layout.setHorizontalSpacing(10)
        remote_layout.setVerticalSpacing(10)
        remote_layout.addWidget(self._create_small_metric_card("Remote 1", "remote_1"), 0, 0)
        remote_layout.addWidget(self._create_small_metric_card("Remote 2", "remote_2"), 0, 1)
        remote_layout.addWidget(self._create_small_metric_card("Remote 3", "remote_3"), 1, 0)
        remote_layout.addWidget(self._create_small_metric_card("Remote 4", "remote_4"), 1, 1)

        layout.addWidget(buttons_group)
        layout.addWidget(remote_group)
        return group

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        return buttons

    def _create_metric_card(self, caption: str, value: str, suffix: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("metricCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(6)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("metricCaption")

        value_label = QLabel(value, card)
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        suffix_label = QLabel(suffix, card)
        suffix_label.setObjectName("metricSuffix")
        suffix_label.setWordWrap(True)

        setattr(self, f"{key}_value", value_label)
        setattr(self, f"{key}_suffix", suffix_label)

        card_layout.addWidget(caption_label)
        card_layout.addWidget(value_label)
        card_layout.addWidget(suffix_label)
        card_layout.addStretch(1)
        return card

    def _create_side_box(self, title: str, prefix: str) -> QGroupBox:
        group = QGroupBox(title, self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(10)
        layout.addWidget(self._create_small_metric_card("Cycles", f"{prefix}_cycles"), 0, 0)
        layout.addWidget(self._create_small_metric_card("Lifetime errors", f"{prefix}_errors"), 0, 1)
        layout.addWidget(self._create_small_metric_card("Move time", f"{prefix}_move_time"), 1, 0, 1, 2)
        return group

    def _create_small_metric_card(self, caption: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("miniMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("miniMetricCaption")
        caption_label.setWordWrap(True)

        value_label = QLabel("--", card)
        value_label.setObjectName("miniMetricValue")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        setattr(self, f"{key}_value", value_label)

        layout.addWidget(caption_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card

    def load_statistics(self) -> None:
        if not self.serial_service.is_connected:
            self.status_label.setText("Connect to the controller before opening statistical data.")
            self._set_busy(False)
            return

        self._set_busy(True, "Loading controller statistics...")
        try:
            raw_response = self.serial_service.request_text(
                "printStatisticalData",
                progress_callback=self._process_loading_events,
            )
            if not raw_response.strip():
                raise SerialConnectionError("The controller did not return any statistical data.")

            snapshot = parse_statistics_snapshot(raw_response)
            self._apply_snapshot(snapshot)
            self.status_label.setText(f"Statistical data refreshed from {self.serial_service.port_name}.")
        except (SerialConnectionError, StatisticsParseError) as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Statistical data", str(exc))
        finally:
            self._set_busy(False)

    def _apply_snapshot(self, snapshot: StatisticsSnapshot) -> None:
        self.boot_count_value.setText(f"{snapshot.boot_count}")
        self.runtime_value.setText(f"{snapshot.total_runtime_seconds:,} s")
        self.runtime_suffix.setText(f"{snapshot.total_runtime_days:.2f} days")

        self.rh_cycles_value.setText(f"{snapshot.rh_side.cycles:,}")
        self.rh_errors_value.setText(f"{snapshot.rh_side.errors:,}")
        self.rh_move_time_value.setText(f"{snapshot.rh_side.move_time_ms:,} ms")

        self.lh_cycles_value.setText(f"{snapshot.lh_side.cycles:,}")
        self.lh_errors_value.setText(f"{snapshot.lh_side.errors:,}")
        self.lh_move_time_value.setText(f"{snapshot.lh_side.move_time_ms:,} ms")

        self.button_rh_value.setText(f"{snapshot.inputs.button_rh:,}")
        self.button_lh_value.setText(f"{snapshot.inputs.button_lh:,}")
        self.button_both_value.setText(f"{snapshot.inputs.button_both:,}")
        self.remote_1_value.setText(f"{snapshot.inputs.remote_1:,}")
        self.remote_2_value.setText(f"{snapshot.inputs.remote_2:,}")
        self.remote_3_value.setText(f"{snapshot.inputs.remote_3:,}")
        self.remote_4_value.setText(f"{snapshot.inputs.remote_4:,}")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if message:
            self.loading_label.setText(message)

        self.loading_frame.setVisible(busy)
        self.overview_group.setEnabled(not busy)
        self.side_group.setEnabled(not busy)
        self.input_group.setEnabled(not busy)

        if busy == self._busy:
            return

        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _process_loading_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
