from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path
import re
import threading
from datetime import datetime

from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from popup_controller.config import AppSettings
from popup_controller.services.build_info_service import parse_build_info_snapshot
from popup_controller.services.external_expander_service import parse_external_expander_snapshot
from popup_controller.services.controller_status_service import parse_controller_status_snapshot
from popup_controller.services.firmware_service import FirmwareService
from popup_controller.services.firmware_release_service import FirmwareReleaseError, FirmwareReleaseInfo, FirmwareReleaseService
from popup_controller.services.serial_service import SerialConnectionError, SerialService
from popup_controller.services.support_export_service import SupportExportService
from popup_controller.services.temperature_service import parse_temperature_snapshot
from popup_controller.ui.direct_controls_dialog import DirectControlsDialog
from popup_controller.ui.errors_dialog import ErrorsDialog
from popup_controller.ui.manufacture_dialog import ManufactureDialog
from popup_controller.ui.service_dialog import SERVICE_ACCESS_PASSWORD, ServiceDialog
from popup_controller.ui.section_dialog import SectionDialog
from popup_controller.ui.settings_dialog import SettingsDialog
from popup_controller.ui.sections import SECTION_DEFINITIONS, SectionDefinition
from popup_controller.ui.statistics_dialog import StatisticsDialog
from popup_controller.ui.window_helpers import create_form_field_label, set_transparent_surface, set_window_surface

logger = logging.getLogger(__name__)

HEADER_INFO_CARD_LAYOUT_BREAKPOINT_WIDE = 1280
HEADER_INFO_CARD_LAYOUT_BREAKPOINT_MEDIUM = 860
SECTION_BUTTON_LAYOUT_BREAKPOINT = 900
_SEMVER_COMPONENT_RE = re.compile(r"\d+")
_TEMPERATURE_MIN_OK_C = -20.0
_TEMPERATURE_MAX_OK_C = 40.0


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings,
        serial_service: SerialService | None = None,
        firmware_service: FirmwareService | None = None,
        firmware_release_service: FirmwareReleaseService | None = None,
        support_export_service: SupportExportService | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.serial_service = serial_service or SerialService(
            baudrate=settings.default_baudrate,
            timeout_seconds=settings.serial_timeout_seconds,
        )
        self.firmware_service = firmware_service or FirmwareService()
        self.firmware_release_service = firmware_release_service or FirmwareReleaseService(
            settings.firmware_release_api_url
        )
        self.support_export_service = support_export_service or SupportExportService()
        self._latest_firmware_release: FirmwareReleaseInfo | None = None
        self._startup_firmware_check_scheduled = False
        self._header_info_card_columns = 0
        self._section_button_columns = 0
        self.header_info_cards: list[QFrame] = []
        self.section_button_order: list[str] = []
        self.section_buttons: dict[str, QPushButton] = {}
        self._controller_operating_state: str | None = None
        self._current_firmware_version: str | None = None
        self._current_build_date: str | None = None
        self._current_external_expander_state: str | None = None
        self._current_temperature_c: float | None = None
        self._build_info_has_live_data = False
        self._startup_firmware_fetch_thread: threading.Thread | None = None
        self._startup_firmware_fetch_result: dict[str, object] | None = None
        self._startup_firmware_fetch_poll_timer = QTimer(self)
        self._startup_firmware_fetch_poll_timer.setInterval(75)
        self._startup_firmware_fetch_poll_timer.timeout.connect(self._check_startup_firmware_fetch)
        self.setWindowTitle(settings.app_display_name)
        if settings.icon_path.is_file():
            self.setWindowIcon(QIcon(str(settings.icon_path)))

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(settings.serial_poll_interval_ms)
        self._poll_timer.timeout.connect(self._poll_serial_feedback)
        self._busy_operation_active = False
        self._busy_status_text = ""
        self._busy_cursor_active = False
        self._busy_scroll_value: int | None = None
        self._suppress_scroll_wheel = False

        self._build_ui()
        self._connect_signals()
        self._refresh_available_ports(
            empty_message="No serial ports detected. Connect a board, then press 'Find controller' to search."
        )
        self._update_connection_state()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_responsive_layouts()
        if self._startup_firmware_check_scheduled or not self.settings.auto_check_latest_firmware_on_startup:
            return

        self._startup_firmware_check_scheduled = True
        self._set_latest_firmware_status("Checking GitHub...")
        QTimer.singleShot(0, self._start_startup_firmware_fetch)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_layouts()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.central_scroll_area.viewport() and event.type() == QEvent.Type.Wheel:
            if self._suppress_scroll_wheel:
                return True
        return super().eventFilter(watched, event)

    def _start_startup_firmware_fetch(self) -> None:
        if self._startup_firmware_fetch_thread is not None and self._startup_firmware_fetch_thread.is_alive():
            return

        self._startup_firmware_fetch_result = {"done": False}

        def runner() -> None:
            try:
                release = self.firmware_release_service.fetch_latest_release()
                self._startup_firmware_fetch_result = {
                    "done": True,
                    "release": release,
                }
            except FirmwareReleaseError as exc:
                self._startup_firmware_fetch_result = {
                    "done": True,
                    "error": exc,
                }

        self._startup_firmware_fetch_thread = threading.Thread(target=runner, daemon=True)
        self._startup_firmware_fetch_thread.start()
        self._startup_firmware_fetch_poll_timer.start()

    def _check_startup_firmware_fetch(self) -> None:
        if not self._startup_firmware_fetch_result or not self._startup_firmware_fetch_result.get("done"):
            return

        self._startup_firmware_fetch_poll_timer.stop()
        result = self._startup_firmware_fetch_result
        self._startup_firmware_fetch_thread = None
        self._startup_firmware_fetch_result = None

        error = result.get("error")
        if isinstance(error, FirmwareReleaseError):
            self._set_latest_firmware_status("GitHub release unavailable.", tooltip=str(error))
            self._append_log(f"GitHub firmware lookup failed: {error}")
            self.statusBar().showMessage("GitHub firmware lookup failed.")
            return

        release = result.get("release")
        if isinstance(release, FirmwareReleaseInfo):
            self._apply_latest_firmware_release(release)

    def _build_ui(self) -> None:
        self.central_container = set_window_surface(QWidget(self))
        container_layout = QVBoxLayout(self.central_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.central_scroll_area = QScrollArea(self.central_container)
        self.central_scroll_area.setWidgetResizable(True)
        self.central_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.central_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.central_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.central_scroll_area.viewport().installEventFilter(self)

        scroll_content = set_window_surface(QWidget(self.central_scroll_area))
        root_layout = QVBoxLayout(scroll_content)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)
        root_layout.addWidget(self._build_header_card())
        root_layout.addWidget(self._build_connection_group())
        root_layout.addWidget(self._build_sections_group())
        root_layout.addWidget(self._build_firmware_group())
        root_layout.addWidget(self._build_feedback_group(), stretch=1)
        self.central_scroll_area.setWidget(scroll_content)

        self.loading_slot = set_transparent_surface(QWidget(self.central_container))
        loading_slot_layout = QVBoxLayout(self.loading_slot)
        loading_slot_layout.setContentsMargins(18, 0, 18, 10)
        loading_slot_layout.setSpacing(0)
        self.main_loading_frame = self._build_loading_frame(self.loading_slot)
        loading_slot_layout.addWidget(self.main_loading_frame)
        loading_slot_margins = loading_slot_layout.contentsMargins()
        self.loading_slot.setFixedHeight(
            self.main_loading_frame.sizeHint().height()
            + loading_slot_margins.top()
            + loading_slot_margins.bottom()
        )

        container_layout.addWidget(self.central_scroll_area, stretch=1)
        container_layout.addWidget(self.loading_slot)

        self.setCentralWidget(self.central_container)
        self._update_responsive_layouts()
        self.setStatusBar(QStatusBar(self))

    def _build_header_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("headerCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.hero_title_label = QLabel(f"Pop-up Controller V10 Application v{self.settings.app_version}", card)
        self.hero_title_label.setObjectName("heroTitle")

        self.hero_subtitle_label = QLabel(
            "Find a running controller for live diagnostics, or choose any visible serial port to flash new firmware.",
            card,
        )
        self.hero_subtitle_label.setObjectName("heroSubtitle")
        self.hero_subtitle_label.setWordWrap(True)

        self.controller_details_label = QLabel(
            "No controller selected yet. Detect a running controller or pick a serial port below to flash firmware.",
            card,
        )
        self.controller_details_label.setObjectName("controllerBadge")
        self.controller_details_label.setWordWrap(True)
        self.controller_details_label.setMinimumWidth(0)

        self.header_metrics_widget = set_transparent_surface(QWidget(card))
        self.header_metrics_layout = QGridLayout(self.header_metrics_widget)
        self.header_metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.header_metrics_layout.setHorizontalSpacing(12)
        self.header_metrics_layout.setVerticalSpacing(12)

        self.header_info_cards = [
            self._create_header_info_card("FW version", "--", "firmware_version"),
            self._create_header_info_card("Build date", "--", "build_date"),
            self._create_header_info_card("Controller state", "--", "controller_state"),
            self._create_header_info_card("Remote expansion module", "--", "external_expander"),
            self._create_header_info_card("Temperature", "--", "temperature"),
        ]

        layout.addWidget(self.hero_title_label)
        layout.addWidget(self.hero_subtitle_label)
        layout.addWidget(self.controller_details_label)
        layout.addWidget(self.header_metrics_widget)
        return card

    def _build_loading_frame(self, parent: QWidget) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("loadingFrame")
        frame.setVisible(False)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.loading_label = QLabel("Working...", frame)
        self.loading_label.setObjectName("loadingLabel")

        self.loading_bar = QProgressBar(frame)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setMinimumWidth(220)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar, stretch=1)
        return frame

    def _create_header_info_card(self, caption: str, value: str, key: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("miniMetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        caption_label = QLabel(caption, card)
        caption_label.setObjectName("miniMetricCaption")

        value_label = QLabel(value, card)
        value_label.setObjectName("miniMetricValue")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)

        setattr(self, f"{key}_value", value_label)
        setattr(self, f"{key}_card", card)

        layout.addWidget(caption_label)
        if key == "firmware_version":
            value_row = set_transparent_surface(QWidget(card))
            value_row_layout = QHBoxLayout(value_row)
            value_row_layout.setContentsMargins(0, 0, 0, 0)
            value_row_layout.setSpacing(8)

            self.firmware_update_indicator = QLabel("!", value_row)
            self.firmware_update_indicator.setObjectName("updateIndicator")
            self.firmware_update_indicator.setToolTip("A newer version is available.")
            self.firmware_update_indicator.setVisible(False)

            value_row_layout.addWidget(value_label)
            value_row_layout.addWidget(self.firmware_update_indicator, 0, Qt.AlignmentFlag.AlignTop)
            value_row_layout.addStretch(1)
            layout.addWidget(value_row)
        else:
            layout.addWidget(value_label)
        layout.addStretch(1)
        return card

    def _set_header_card_semantic_state(self, key: str, semantic_state: str | None) -> None:
        card = getattr(self, f"{key}_card")
        value_label = getattr(self, f"{key}_value")
        self._set_semantic_state(card, semantic_state)
        self._set_semantic_state(value_label, semantic_state)

    def _set_semantic_state(self, widget: QWidget, semantic_state: str | None) -> None:
        if widget.property("semanticState") == semantic_state:
            return

        widget.setProperty("semanticState", semantic_state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _parse_version_components(self, version_text: str | None) -> tuple[int, ...] | None:
        if not version_text:
            return None

        parts = tuple(int(part) for part in _SEMVER_COMPONENT_RE.findall(version_text))
        if not parts:
            return None
        return parts

    def _firmware_is_outdated(self) -> bool:
        current_version = self._parse_version_components(self._current_firmware_version)
        latest_version = self._parse_version_components(self._latest_firmware_release.version if self._latest_firmware_release else None)
        if current_version is None or latest_version is None:
            return False
        return current_version < latest_version

    def _update_build_info_semantics(self) -> None:
        if not self._build_info_has_live_data:
            self._set_header_card_semantic_state("firmware_version", None)
            self._set_header_card_semantic_state("build_date", None)
            self.firmware_update_indicator.setVisible(False)
            return

        if not self._current_firmware_version or not self._current_build_date:
            self._set_header_card_semantic_state("firmware_version", "danger")
            self._set_header_card_semantic_state("build_date", "danger")
            self.firmware_update_indicator.setVisible(False)
            return

        semantic_state = "caution" if self._firmware_is_outdated() else "good"
        self._set_header_card_semantic_state("firmware_version", semantic_state)
        self._set_header_card_semantic_state("build_date", semantic_state)
        self.firmware_update_indicator.setVisible(semantic_state == "caution")
        self._set_semantic_state(self.firmware_update_indicator, semantic_state if semantic_state == "caution" else None)

    def _apply_latest_firmware_release(self, release: FirmwareReleaseInfo) -> None:
        self._latest_firmware_release = release
        self._set_latest_firmware_status(
            self._describe_latest_firmware_release(release),
            tooltip="\n".join(
                line
                for line in (release.release_name or None, release.html_url, release.download_url)
                if line
            ),
        )
        self._append_log(f"Latest GitHub firmware: {self._release_version_text(release)} ({release.asset_name}).")
        self.statusBar().showMessage(f"Latest GitHub firmware: {self._release_version_text(release)}")
        self._update_build_info_semantics()

    def _update_controller_state_semantics(self) -> None:
        if self._controller_operating_state is None:
            self._set_header_card_semantic_state("controller_state", "danger")
            return
        if self._controller_operating_state == "BENCH MODE":
            self._set_header_card_semantic_state("controller_state", "caution")
            return
        self._set_header_card_semantic_state("controller_state", "good")

    def _update_external_expander_semantics(self) -> None:
        if self._current_external_expander_state is None:
            self._set_header_card_semantic_state("external_expander", "danger")
            return

        normalized = self._current_external_expander_state.strip().casefold()
        if normalized in {"not connected", "disconnected"}:
            self._set_header_card_semantic_state("external_expander", "danger")
            return
        self._set_header_card_semantic_state("external_expander", "good")

    def _update_temperature_semantics(self) -> None:
        if self._current_temperature_c is None:
            self._set_header_card_semantic_state("temperature", "danger")
            return

        if self._current_temperature_c < _TEMPERATURE_MIN_OK_C or self._current_temperature_c > _TEMPERATURE_MAX_OK_C:
            self._set_header_card_semantic_state("temperature", "danger")
            return
        self._set_header_card_semantic_state("temperature", "good")

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Serial connection", self)
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(1, 1)

        self.port_combo = QComboBox(group)
        self.find_controller_button = QPushButton("Find controller", group)
        self.find_controller_button.setProperty("accent", True)
        self.connect_button = QPushButton("Connect", group)
        self.reboot_button = QPushButton("Reboot controller", group)
        self.reboot_button.setToolTip("Reboot the controller and require a fresh search before reconnecting.")
        self.status_label = QLabel("Disconnected", group)
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.port_label = create_form_field_label("COM port", group)
        self.connection_status_label = create_form_field_label("Status", group)

        layout.addWidget(self.port_label, 0, 0)
        layout.addWidget(self.port_combo, 0, 1)
        layout.addWidget(self.find_controller_button, 0, 2)
        layout.addWidget(self.connect_button, 0, 3)
        layout.addWidget(self.connection_status_label, 1, 0)
        layout.addWidget(self.status_label, 1, 1, 1, 2)
        layout.addWidget(self.reboot_button, 1, 3)
        return group

    def _build_sections_group(self) -> QGroupBox:
        self.sections_group = QGroupBox("Controller sections", self)
        self.sections_layout = QGridLayout(self.sections_group)
        self.sections_layout.setHorizontalSpacing(12)
        self.sections_layout.setVerticalSpacing(12)

        for section in SECTION_DEFINITIONS:
            button = QPushButton(f"{section.title}\n{section.button_subtitle}", self.sections_group)
            button.setProperty("sectionButton", True)
            button.setMinimumHeight(88)
            button.setToolTip(section.summary)
            self.section_buttons[section.section_id] = button
            self.section_button_order.append(section.section_id)

        self.export_support_button = QPushButton("Export support file", self.sections_group)
        self.export_support_button.setToolTip(
            "Collect controller details from all readable sections and save them as a JSON support report."
        )

        return self.sections_group

    def _build_firmware_group(self) -> QGroupBox:
        self.firmware_group = QGroupBox("Firmware", self)
        layout = QFormLayout(self.firmware_group)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        row = set_transparent_surface(QWidget(self.firmware_group))
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self.firmware_path_input = QLineEdit(row)
        self.firmware_path_input.setPlaceholderText("Select a flash bundle .zip or flash_manifest.json")
        default_bundle_path = (self.settings.firmware_directory / "flash_bundle.zip").resolve()
        if default_bundle_path.exists():
            self.firmware_path_input.setText(str(default_bundle_path))
        self.browse_firmware_button = QPushButton("Browse", row)
        self.flash_button = QPushButton("Flash firmware", row)
        self.flash_button.setProperty("accent", True)
        self.firmware_file_label = create_form_field_label("Firmware file", self.firmware_group)

        row_layout.addWidget(self.firmware_path_input, stretch=1)
        row_layout.addWidget(self.browse_firmware_button)
        row_layout.addWidget(self.flash_button)

        layout.addRow(self.firmware_file_label, row)

        latest_row = set_transparent_surface(QWidget(self.firmware_group))
        latest_row_layout = QHBoxLayout(latest_row)
        latest_row_layout.setContentsMargins(0, 0, 0, 0)
        latest_row_layout.setSpacing(8)

        status_text = self._initial_latest_firmware_status()

        self.latest_firmware_status_label = QLabel(status_text, latest_row)
        self.latest_firmware_status_label.setObjectName("statusPill")
        self.latest_firmware_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.latest_firmware_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.latest_firmware_status_label.setWordWrap(False)
        self.latest_firmware_status_label.setMinimumWidth(0)
        self.download_latest_firmware_button = QPushButton("Download latest", latest_row)
        self.github_release_label = create_form_field_label("GitHub release", self.firmware_group)
        self._match_button_widths(self.flash_button, self.download_latest_firmware_button)

        latest_row_layout.addWidget(self.latest_firmware_status_label, stretch=1)
        latest_row_layout.addWidget(self.download_latest_firmware_button, 0, Qt.AlignmentFlag.AlignTop)

        layout.addRow(self.github_release_label, latest_row)
        return self.firmware_group

    def _build_feedback_group(self) -> QGroupBox:
        self.feedback_group = QGroupBox("Activity log", self)
        layout = QVBoxLayout(self.feedback_group)
        self.feedback_log = QPlainTextEdit(self.feedback_group)
        self.feedback_log.setReadOnly(True)
        layout.addWidget(self.feedback_log, stretch=1)

        self.manual_command_row = set_transparent_surface(QWidget(self.feedback_group))
        command_layout = QHBoxLayout(self.manual_command_row)
        command_layout.setContentsMargins(0, 0, 0, 0)
        command_layout.setSpacing(8)

        self.manual_command_input = QLineEdit(self.manual_command_row)
        self.manual_command_input.setPlaceholderText("Send a controller command manually")
        self.manual_command_input.setClearButtonEnabled(True)
        self.manual_command_input.setToolTip(
            "Send any controller command and append its reply to the activity log."
        )

        self.manual_command_button = QPushButton("Send command", self.manual_command_row)
        self.manual_command_button.setToolTip(
            "Send the text above to the connected controller and log the response."
        )

        command_layout.addWidget(self.manual_command_input, stretch=1)
        command_layout.addWidget(self.manual_command_button)
        layout.addWidget(self.manual_command_row)
        return self.feedback_group

    def _connect_signals(self) -> None:
        self.find_controller_button.clicked.connect(self.find_controller)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.reboot_button.clicked.connect(self.reboot_controller)
        self.browse_firmware_button.clicked.connect(self.browse_firmware)
        self.flash_button.clicked.connect(self.flash_firmware)
        self.download_latest_firmware_button.clicked.connect(self.download_latest_firmware)
        self.export_support_button.clicked.connect(self.export_support_file)
        self.manual_command_button.clicked.connect(self.send_manual_command)
        self.manual_command_input.returnPressed.connect(self.send_manual_command)
        self.manual_command_input.textChanged.connect(lambda _text: self._update_connection_state())

        for section in SECTION_DEFINITIONS:
            self.section_buttons[section.section_id].clicked.connect(
                lambda checked=False, current_section=section: self.open_section_dialog(current_section)
            )

    def _match_button_widths(self, *buttons: QPushButton) -> None:
        if not buttons:
            return

        for button in buttons:
            button.ensurePolished()

        uniform_width = max(button.sizeHint().width() for button in buttons)
        for button in buttons:
            button.setMinimumWidth(uniform_width)

    def _update_responsive_layouts(self) -> None:
        self._update_header_info_card_layout()
        self._update_section_button_layout()

    def _content_width_hint(self) -> int:
        viewport_width = self.central_scroll_area.viewport().width()
        if viewport_width > 0:
            return viewport_width
        return self.settings.default_window_width

    def _header_info_card_column_count(self) -> int:
        width = self._content_width_hint()
        if width >= HEADER_INFO_CARD_LAYOUT_BREAKPOINT_WIDE:
            return len(self.header_info_cards)
        if width >= HEADER_INFO_CARD_LAYOUT_BREAKPOINT_MEDIUM:
            return 3
        return 2

    def _update_header_info_card_layout(self) -> None:
        column_count = self._header_info_card_column_count()
        if column_count == self._header_info_card_columns:
            return

        self._header_info_card_columns = column_count
        while self.header_metrics_layout.count():
            self.header_metrics_layout.takeAt(0)

        for column in range(len(self.header_info_cards)):
            self.header_metrics_layout.setColumnStretch(column, 0)

        for index, card in enumerate(self.header_info_cards):
            row = index // column_count
            column = index % column_count
            self.header_metrics_layout.addWidget(card, row, column)

        for column in range(column_count):
            self.header_metrics_layout.setColumnStretch(column, 1)

    def _section_button_column_count(self) -> int:
        width = self._content_width_hint()
        if width >= SECTION_BUTTON_LAYOUT_BREAKPOINT:
            return 2
        return 1

    def _update_section_button_layout(self) -> None:
        column_count = self._section_button_column_count()
        if column_count == self._section_button_columns:
            return

        self._section_button_columns = column_count
        while self.sections_layout.count():
            self.sections_layout.takeAt(0)

        for column in range(2):
            self.sections_layout.setColumnStretch(column, 0)

        for index, section_id in enumerate(self.section_button_order):
            row = index // column_count
            column = index % column_count
            self.sections_layout.addWidget(self.section_buttons[section_id], row, column)

        action_row = max(1, (len(self.section_button_order) + column_count - 1) // column_count)
        self.sections_layout.addWidget(self.export_support_button, action_row, 0, 1, column_count)

        for column in range(column_count):
            self.sections_layout.setColumnStretch(column, 1)

    def find_controller(self) -> None:
        if self.serial_service.is_connected:
            QMessageBox.warning(
                self,
                "Disconnect first",
                "Disconnect from the current serial port before searching again.",
            )
            return

        selected_port = self.serial_service.port_name or self._selected_port()
        available_ports = self._refresh_available_ports(
            empty_message="No serial ports detected. Check the USB cable and try again.",
            preferred_port=selected_port,
        )
        if not available_ports:
            self.controller_details_label.setText(
                "No serial ports are currently visible to the application."
            )
            self._append_log("No serial ports detected while searching for the controller.")
            self._update_connection_state()
            return

        self.controller_details_label.setText(
            f"Scanning {len(available_ports)} serial port(s) for a valid controller reply..."
        )
        self._append_log(
            f"Searching {len(available_ports)} serial port(s) for the controller."
        )
        self._begin_busy("Searching for controller...")

        try:
            result = self.serial_service.find_controller_port(
                probe_command=self.settings.controller_probe_command,
                expected_response_fragment=self.settings.controller_probe_response_fragment,
                warmup_seconds=self.settings.controller_probe_warmup_seconds,
                probe_window_seconds=self.settings.controller_probe_window_seconds,
                progress_callback=self._process_loading_events,
                port_status_callback=self._update_search_progress,
            )
        except SerialConnectionError as exc:
            QMessageBox.critical(self, "Search failed", str(exc))
            self._update_connection_state()
            return
        finally:
            self._end_busy()

        if result is None:
            self._append_log("Controller was not found on the available COM ports.")
            selected_port = self._selected_port()
            if selected_port:
                self.controller_details_label.setText(
                    "The scan completed, but no device answered like a running controller. "
                    f"You can still flash firmware directly to {selected_port} or choose another visible serial port."
                )
            else:
                self.controller_details_label.setText(
                    "The scan completed, but no device answered with the expected controller response."
                )
            self._update_connection_state()
            return

        self.port_combo.clear()
        self.port_combo.addItem(f"{result.port.device} - {result.port.description}", result.port.device)
        self.port_combo.setEnabled(True)

        first_reply_line = next(
            (line.strip() for line in result.response.splitlines() if line.strip()),
            "",
        )
        self._append_log(f"Found controller on {result.port.device}.")
        if first_reply_line:
            self._append_log(f"Probe reply: {first_reply_line}")

        self.controller_details_label.setText(
            f"Detected controller on {result.port.device} ({result.port.description}). Connect to load live data."
        )
        self._update_connection_state()

    def open_section_dialog(self, section: SectionDefinition) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(
                self,
                "Connect first",
                "Connect to the controller before opening a live section dialog.",
            )
            return

        if section.section_id == "direct_controls" and self._controller_operating_state == "BENCH MODE":
            QMessageBox.information(
                self,
                "Direct controls unavailable",
                "Direct controls cannot be opened while the controller is in bench mode.",
            )
            return

        if section.section_id == "statistics":
            dialog = StatisticsDialog(self.serial_service, self)
        elif section.section_id == "errors":
            dialog = ErrorsDialog(self.serial_service, self)
        elif section.section_id == "manufacture":
            dialog = ManufactureDialog(self.serial_service, self)
        elif section.section_id == "settings":
            dialog = SettingsDialog(
                self.serial_service,
                self,
                self.settings.remote_mapping_reference_image_path,
            )
        elif section.section_id == "direct_controls":
            dialog = DirectControlsDialog(self.serial_service, self)
        elif section.section_id == "service":
            if not self._request_service_access():
                return
            dialog = ServiceDialog(self.serial_service, self)
        else:
            dialog = SectionDialog(section, self)

        poll_was_active = self._poll_timer.isActive()
        if poll_was_active:
            self._poll_timer.stop()

        try:
            dialog.exec()
        finally:
            if poll_was_active and self.serial_service.is_connected:
                self._poll_timer.start()

    def toggle_connection(self) -> None:
        if self.serial_service.is_connected:
            current_port = self.serial_service.port_name
            self.serial_service.disconnect()
            self._clear_build_info()
            self._clear_controller_state()
            self._clear_external_expander()
            self._clear_temperature()
            self._append_log("Disconnected from serial port.")
            self.controller_details_label.setText(
                f"Disconnected from {current_port}. Reconnect to use the live controller sections again."
            )
            self._poll_timer.stop()
            self._update_connection_state()
            return

        port = self._selected_port()
        if not port:
            QMessageBox.warning(self, "No port selected", "Find the controller before connecting.")
            return

        self._connect_to_port(port)

    def _connect_to_port(
        self,
        port: str,
        failure_title: str = "Connection failed",
        show_failure_dialog: bool = True,
    ) -> bool:
        self.controller_details_label.setText(
            f"Connecting to {port}. Verifying that the device is running controller firmware."
        )
        self._begin_busy(f"Connecting to {port}...")

        try:
            probe_response = self.serial_service.connect_to_controller(
                port,
                probe_command=self.settings.controller_probe_command,
                expected_response_fragment=self.settings.controller_probe_response_fragment,
                warmup_seconds=self.settings.controller_probe_warmup_seconds,
                probe_window_seconds=self.settings.controller_probe_window_seconds,
                progress_callback=self._process_loading_events,
            )
        except SerialConnectionError as exc:
            self._append_log(f"Connection to {port} failed: {exc}")
            self.controller_details_label.setText(f"Unable to connect to {port}. {exc}")
            self._update_connection_state()
            self._end_busy()
            if show_failure_dialog:
                QMessageBox.critical(self, failure_title, str(exc))
            return False

        self._append_log(f"Connected to {port} at {self.serial_service.baudrate} baud.")
        first_reply_line = next(
            (line.strip() for line in probe_response.splitlines() if line.strip()),
            "",
        )
        if first_reply_line:
            self._append_log(f"Controller probe reply: {first_reply_line}")
        refresh_steps: tuple[tuple[str, Callable[[Callable[[], None] | None], None]], ...] = (
            ("Loading build info...", self._refresh_build_info),
            ("Loading controller state...", self._refresh_controller_state),
            ("Loading external expander status...", self._refresh_external_expander),
            ("Loading temperature...", self._refresh_temperature),
        )
        for status_text, refresh_callback in refresh_steps:
            self._update_busy(status_text)
            refresh_callback(progress_callback=self._process_loading_events)

        self.controller_details_label.setText(
            f"Connected to {port}. The live controller sections are ready to open."
        )
        self._poll_timer.start()
        self._end_busy()
        self._update_connection_state()
        return True

    def _reconnect_after_flash(self, port: str) -> None:
        if self.serial_service.is_connected:
            return

        self.controller_details_label.setText(
            f"Trying to reconnect to {port} after firmware flash..."
        )
        self.statusBar().showMessage(f"Trying to reconnect to {port} after firmware flash...")
        QApplication.processEvents()

        if self._connect_to_port(port, failure_title="Reconnect failed", show_failure_dialog=False):
            self.controller_details_label.setText(
                f"Reconnected to {port} after firmware flash. Verify the new firmware information above."
            )
            self._append_log(f"Automatic reconnect after firmware flash succeeded on {port}.")
            self.statusBar().showMessage(f"Reconnected to {port} after firmware flash.")
            return

        self.controller_details_label.setText(
            f"Automatic reconnect to {port} after firmware flash did not succeed. Press Connect to try again."
        )
        self._append_log(f"Automatic reconnect after firmware flash did not succeed on {port}.")
        self.statusBar().showMessage(f"Automatic reconnect to {port} failed.")

    def reboot_controller(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(self, "Connect first", "Connect to the controller before requesting a reboot.")
            return

        confirmation = QMessageBox.question(
            self,
            "Reboot controller",
            "Reboot the controller now? The app will disconnect and require a fresh search before reconnecting.",
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        current_port = self.serial_service.port_name or "controller"
        try:
            self.serial_service.send_command("reboot")
        except SerialConnectionError as exc:
            QMessageBox.warning(self, "Reboot controller", str(exc))
            return

        self._append_log(f"Reboot command sent to {current_port}.")
        self._poll_timer.stop()
        self.serial_service.disconnect()
        self._reset_port_selection("Controller reboot requested. Press 'Find controller' to search again.")
        self.controller_details_label.setText(
            f"Reboot requested for {current_port}. Wait for the controller to restart, then search again to reconnect."
        )
        self._update_connection_state()

    def send_manual_command(self) -> None:
        command = self.manual_command_input.text().strip()
        if not command:
            self.manual_command_input.setFocus()
            return

        if not self.serial_service.is_connected:
            QMessageBox.information(
                self,
                "Connect first",
                "Connect to the controller before sending manual commands.",
            )
            return

        self._append_log(f"TX > {command}")
        poll_was_active = self._poll_timer.isActive()
        if poll_was_active:
            self._poll_timer.stop()

        self._begin_busy(f"Sending '{command}'...")
        try:
            response = self.serial_service.request_text(
                command,
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=self._process_loading_events,
            )
        except SerialConnectionError as exc:
            self._append_log(f"Manual command failed: {exc}")
            QMessageBox.warning(self, "Manual command", str(exc))
            return
        finally:
            self._end_busy()
            if poll_was_active and self.serial_service.is_connected:
                self._poll_timer.start()

        response_lines = [line.strip() for line in response.splitlines() if line.strip()]
        if response_lines:
            for line in response_lines:
                self._append_log(f"RX < {line}")
        else:
            self._append_log("RX < (no response)")

        self.manual_command_input.clear()

    def _request_service_access(self) -> bool:
        password, accepted = QInputDialog.getText(
            self,
            "Service access",
            "Enter the service password:",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return False

        if password.strip() != SERVICE_ACCESS_PASSWORD:
            QMessageBox.warning(self, "Service access", "Incorrect service password.")
            return False

        return True

    def _refresh_build_info(self, progress_callback: Callable[[], None] | None = None) -> None:
        if not self.serial_service.is_connected:
            self._clear_build_info()
            return

        try:
            raw_response = self.serial_service.request_text(
                "printBuildInfo",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            )
        except SerialConnectionError as exc:
            self._clear_build_info()
            self._build_info_has_live_data = True
            self._set_header_card_semantic_state("firmware_version", "danger")
            self._set_header_card_semantic_state("build_date", "danger")
            self._append_log(f"Build info read failed: {exc}")
            return

        snapshot = parse_build_info_snapshot(raw_response)
        self._build_info_has_live_data = True
        firmware_version = snapshot.firmware_version or "Unavailable"
        build_date = snapshot.build_date or "Unavailable"

        self.firmware_version_value.setText(firmware_version)
        self.build_date_value.setText(build_date)
        self.firmware_version_value.setToolTip(snapshot.firmware_version or "")
        self.build_date_value.setToolTip(snapshot.build_timestamp or "")
        self._current_firmware_version = snapshot.firmware_version
        self._current_build_date = snapshot.build_date
        self._update_build_info_semantics()

        if snapshot.firmware_version or snapshot.build_timestamp:
            self._append_log(
                f"Build info: FW {firmware_version}, built {snapshot.build_timestamp or build_date}."
            )
        else:
            self._append_log("Build info command returned no recognizable fields.")

    def _clear_build_info(self) -> None:
        self.firmware_version_value.setText("--")
        self.build_date_value.setText("--")
        self.firmware_version_value.setToolTip("")
        self.build_date_value.setToolTip("")
        self._current_firmware_version = None
        self._current_build_date = None
        self._build_info_has_live_data = False
        self._set_header_card_semantic_state("firmware_version", None)
        self._set_header_card_semantic_state("build_date", None)
        self.firmware_update_indicator.setVisible(False)

    def _refresh_controller_state(self, progress_callback: Callable[[], None] | None = None) -> None:
        if not self.serial_service.is_connected:
            self._clear_controller_state()
            return

        try:
            raw_response = self.serial_service.request_text(
                "getControllerStatus",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            )
        except SerialConnectionError as exc:
            self._clear_controller_state()
            self._set_header_card_semantic_state("controller_state", "danger")
            self._append_log(f"Controller status read failed: {exc}")
            return

        snapshot = parse_controller_status_snapshot(raw_response)
        self._controller_operating_state = snapshot.state
        self.controller_state_value.setText(snapshot.state or "Unavailable")
        self.controller_state_value.setToolTip(snapshot.status_hint or "\n".join(snapshot.raw_lines))
        self._update_controller_state_semantics()
        self._update_section_button_states()

        if snapshot.state is not None:
            self._append_log(f"Controller state: {snapshot.state}.")
        else:
            self._append_log(f"Controller state unavailable: {snapshot.status_hint}")

    def _clear_controller_state(self) -> None:
        self._controller_operating_state = None
        self.controller_state_value.setText("--")
        self.controller_state_value.setToolTip("")
        self._set_header_card_semantic_state("controller_state", None)
        self._update_section_button_states()

    def _refresh_external_expander(self, progress_callback: Callable[[], None] | None = None) -> None:
        if not self.serial_service.is_connected:
            self._clear_external_expander()
            return

        try:
            raw_response = self.serial_service.request_text(
                "getExternalExpander",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            )
        except SerialConnectionError as exc:
            self._clear_external_expander()
            self._set_header_card_semantic_state("external_expander", "danger")
            self._append_log(f"Remote expansion module read failed: {exc}")
            return

        snapshot = parse_external_expander_snapshot(raw_response)
        self.external_expander_value.setText(snapshot.state or "Unavailable")
        self.external_expander_value.setToolTip(snapshot.status_hint or "\n".join(snapshot.raw_lines))
        self._current_external_expander_state = snapshot.state
        self._update_external_expander_semantics()

        if snapshot.state is not None:
            self._append_log(f"Remote expansion module: {snapshot.state}.")
        else:
            self._append_log(f"Remote expansion module unavailable: {snapshot.status_hint}")

    def _clear_external_expander(self) -> None:
        self.external_expander_value.setText("--")
        self.external_expander_value.setToolTip("")
        self._current_external_expander_state = None
        self._set_header_card_semantic_state("external_expander", None)

    def _refresh_temperature(self, progress_callback: Callable[[], None] | None = None) -> None:
        if not self.serial_service.is_connected:
            self._clear_temperature()
            return

        try:
            raw_response = self.serial_service.request_text(
                "readTemperature",
                idle_timeout_seconds=0.35,
                max_duration_seconds=2.0,
                progress_callback=progress_callback,
            )
        except SerialConnectionError as exc:
            self._clear_temperature()
            self._set_header_card_semantic_state("temperature", "danger")
            self._append_log(f"Temperature read failed: {exc}")
            return

        snapshot = parse_temperature_snapshot(raw_response)
        display_value = "Unavailable"
        if snapshot.temperature_c is not None:
            display_value = f"{snapshot.temperature_c:.2f} C"

        self.temperature_value.setText(display_value)
        self.temperature_value.setToolTip(snapshot.status_hint or "\n".join(snapshot.raw_lines))
        self._current_temperature_c = snapshot.temperature_c
        self._update_temperature_semantics()

        if snapshot.temperature_c is not None:
            self._append_log(f"Temperature: {snapshot.temperature_c:.2f} C.")
        else:
            self._append_log(f"Temperature unavailable: {snapshot.status_hint}")

    def _clear_temperature(self) -> None:
        self.temperature_value.setText("--")
        self.temperature_value.setToolTip("")
        self._current_temperature_c = None
        self._set_header_card_semantic_state("temperature", None)

    def refresh_latest_firmware(self) -> None:
        self._fetch_latest_firmware_release(show_error_dialog=True)

    def _fetch_latest_firmware_release(self, show_error_dialog: bool) -> FirmwareReleaseInfo | None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("Checking latest firmware release on GitHub...")
        QApplication.processEvents()
        try:
            release = self.firmware_release_service.fetch_latest_release()
        except FirmwareReleaseError as exc:
            self._set_latest_firmware_status("GitHub release unavailable.", tooltip=str(exc))
            self._append_log(f"GitHub firmware lookup failed: {exc}")
            self.statusBar().showMessage("GitHub firmware lookup failed.")
            if show_error_dialog:
                QMessageBox.warning(self, "Firmware release", str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()

        self._apply_latest_firmware_release(release)
        return release

    def _initial_latest_firmware_status(self) -> str:
        if self.settings.auto_check_latest_firmware_on_startup:
            return "Checks GitHub on startup."
        return "Not checked yet."

    def _set_latest_firmware_status(self, status_text: str, *, tooltip: str = "") -> None:
        self.latest_firmware_status_label.setText(status_text)
        self.latest_firmware_status_label.setToolTip(tooltip)

    def download_latest_firmware(self) -> None:
        release = self._latest_firmware_release or self._fetch_latest_firmware_release(show_error_dialog=True)
        if release is None:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(f"Downloading {self._release_version_text(release)} from GitHub...")
        QApplication.processEvents()
        try:
            result = self.firmware_release_service.download_release_asset(release, self.settings.firmware_directory)
        except FirmwareReleaseError as exc:
            self._append_log(f"GitHub firmware download failed: {exc}")
            self.statusBar().showMessage("GitHub firmware download failed.")
            QMessageBox.warning(self, "Download latest firmware", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.firmware_path_input.setText(str(result.path))
        action_text = "Downloaded" if result.downloaded else "Using cached copy of"
        version_text = self._release_version_text(release)
        self._append_log(f"{action_text} GitHub firmware {version_text} at {result.path}.")
        selected_port = self.serial_service.port_name or self._selected_port()
        if selected_port:
            self.controller_details_label.setText(
                f"{action_text} {version_text} from GitHub. Ready to flash it to {selected_port}."
            )
        else:
            self.controller_details_label.setText(
                f"{action_text} {version_text} from GitHub. Select a serial port when you're ready to flash it."
            )
        self.statusBar().showMessage(f"{action_text} {version_text} from GitHub.")

    def _describe_latest_firmware_release(self, release: FirmwareReleaseInfo) -> str:
        if release.published_at:
            published_date = release.published_at.split("T", 1)[0]
            return f"{self._release_version_text(release)} - Published {published_date}"
        return self._release_version_text(release)

    def _release_version_text(self, release: FirmwareReleaseInfo) -> str:
        if release.version:
            return f"v{release.version}"
        if release.release_name:
            return release.release_name
        if release.tag_name:
            return release.tag_name
        return release.asset_name

    def browse_firmware(self) -> None:
        start_dir = str(self.settings.firmware_directory.resolve())
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select firmware bundle",
            start_dir,
            "Flash bundles (*.zip *.json);;All files (*.*)",
        )
        if selected_file:
            self.firmware_path_input.setText(selected_file)

    def export_support_file(self) -> None:
        if not self.serial_service.is_connected:
            QMessageBox.information(
                self,
                "Connect first",
                "Connect to the controller before exporting a support file.",
            )
            return

        default_name = self._default_support_export_file_name()
        selected_file, _ = QFileDialog.getSaveFileName(
            self,
            "Export support file",
            str((Path.cwd() / default_name).resolve()),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected_file:
            return

        output_path = Path(selected_file)
        activity_log_tail = self._support_export_log_tail()
        poll_was_active = self._poll_timer.isActive()
        if poll_was_active:
            self._poll_timer.stop()

        self._append_log(f"Starting support export to {output_path}.")
        self._begin_busy("Collecting support data...")
        try:
            self.support_export_service.export_to_file(
                output_path=output_path,
                serial_service=self.serial_service,
                app_version=self.settings.app_version,
                selected_port=self.serial_service.port_name or self._selected_port(),
                activity_log_lines=activity_log_tail,
                firmware_release_service=self.firmware_release_service,
                progress_callback=self._process_loading_events,
                selected_firmware_path=self.firmware_path_input.text().strip(),
            )
        except OSError as exc:
            self._append_log(f"Support export failed: {exc}")
            QMessageBox.warning(self, "Support export", str(exc))
            return
        finally:
            self._end_busy()
            if poll_was_active and self.serial_service.is_connected:
                self._poll_timer.start()

        self._append_log(f"Support export saved to {output_path}.")
        self.statusBar().showMessage(f"Support export saved to {output_path}")
        QMessageBox.information(
            self,
            "Support export",
            f"Saved support report to:\n{output_path}",
        )

    def _default_support_export_file_name(self) -> str:
        port_name = (self.serial_service.port_name or self._selected_port() or "controller").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"popup-controller-support-{port_name}-{timestamp}.json"

    def _support_export_log_tail(self, max_lines: int = 200) -> tuple[str, ...]:
        lines = [line.strip() for line in self.feedback_log.toPlainText().splitlines() if line.strip()]
        return tuple(lines[-max_lines:])

    def flash_firmware(self) -> None:
        selected_port = self.serial_service.port_name or self._selected_port() or ""
        if not selected_port:
            QMessageBox.warning(self, "No port selected", "Select a serial port before starting a firmware flash.")
            return

        was_connected = self.serial_service.is_connected
        firmware_path_text = self.firmware_path_input.text().strip()
        if not firmware_path_text:
            QMessageBox.warning(
                self,
                "No flash bundle selected",
                "Select a flash bundle .zip or flash_manifest.json before flashing.",
            )
            return

        firmware_path = Path(firmware_path_text)
        confirmation_message = (
            f"Flash the selected firmware to {selected_port}? "
            "The app will disconnect from the controller before esptool starts."
            if was_connected
            else f"Flash the selected firmware to {selected_port}? "
            "The controller does not need to be connected before esptool starts."
        )
        confirmation = QMessageBox.question(
            self,
            "Flash firmware",
            confirmation_message,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        self._poll_timer.stop()
        if was_connected:
            self.serial_service.disconnect()
        self._clear_build_info()
        self._clear_controller_state()
        self._clear_external_expander()
        self._clear_temperature()
        self.controller_details_label.setText(
            f"Preparing firmware flash on {selected_port}. Wait for the controller to reboot after flashing completes."
        )
        self._append_log(f"Starting firmware flash on {selected_port} using {firmware_path}.")
        self._begin_busy(f"Flashing firmware on {selected_port}...")

        try:
            result = self._run_blocking_task(
                lambda: self.firmware_service.flash_firmware(selected_port, firmware_path)
            )
        finally:
            self._end_busy()

        self._append_log(result.message)
        if result.success:
            QMessageBox.information(
                self,
                "Firmware",
                result.message,
            )
            self._reconnect_after_flash(selected_port)
        else:
            self.controller_details_label.setText(
                f"Firmware flash failed on {selected_port}. Review the activity log and try again when ready."
            )
            QMessageBox.warning(self, "Firmware", result.message)

        self._update_connection_state()
    def _poll_serial_feedback(self) -> None:
        try:
            messages = self.serial_service.read_available()
        except SerialConnectionError as exc:
            self._poll_timer.stop()
            self.serial_service.disconnect()
            self._clear_build_info()
            self._clear_controller_state()
            self._clear_external_expander()
            self._clear_temperature()
            self.controller_details_label.setText(
                "The controller connection was lost while reading serial feedback."
            )
            self._update_connection_state()
            QMessageBox.critical(self, "Read failed", str(exc))
            return

        for message in messages:
            self._append_log(f"RX < {message}")

    def _selected_port(self) -> str | None:
        value = self.port_combo.currentData()
        if not value:
            return None
        return str(value)

    def _update_search_progress(self, port_info, current_index: int, total: int) -> None:
        self._update_busy(f"Searching {port_info.device} ({current_index}/{total})...")
        self.controller_details_label.setText(
            f"Scanning {port_info.device} ({current_index}/{total}) - {port_info.description}. Waiting for a valid controller reply..."
        )

    def _refresh_available_ports(
        self,
        empty_message: str,
        preferred_port: str | None = None,
    ) -> list:
        available_ports = self.serial_service.available_ports()
        if not available_ports:
            self._reset_port_selection(empty_message)
            return []

        self.port_combo.clear()
        for port_info in available_ports:
            self.port_combo.addItem(f"{port_info.device} - {port_info.description}", port_info.device)

        self.port_combo.setEnabled(True)

        if preferred_port:
            port_index = self.port_combo.findData(preferred_port)
            if port_index >= 0:
                self.port_combo.setCurrentIndex(port_index)

        return available_ports

    def _reset_port_selection(self, message: str) -> None:
        self.port_combo.clear()
        self.port_combo.addItem(message, "")
        self.port_combo.setEnabled(False)
        self._clear_build_info()
        self._clear_controller_state()
        self._clear_external_expander()
        self._clear_temperature()

    def _restore_busy_scroll_position(self) -> None:
        if self._busy_scroll_value is None:
            return
        self.central_scroll_area.verticalScrollBar().setValue(self._busy_scroll_value)

    def _release_busy_scroll_guard(self) -> None:
        self._restore_busy_scroll_position()
        self._busy_scroll_value = None
        self._suppress_scroll_wheel = False

    def _begin_busy(self, status_text: str) -> None:
        if not self._busy_operation_active:
            self._busy_scroll_value = self.central_scroll_area.verticalScrollBar().value()
        self._suppress_scroll_wheel = True
        self._busy_operation_active = True
        self._busy_status_text = status_text
        self.loading_label.setText(status_text)
        self.main_loading_frame.setVisible(True)
        if not self._busy_cursor_active:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._busy_cursor_active = True
        self._update_connection_state()
        self._process_loading_events()
        self._restore_busy_scroll_position()
        QTimer.singleShot(0, self._restore_busy_scroll_position)

    def _update_busy(self, status_text: str) -> None:
        if not self._busy_operation_active:
            return
        self._busy_status_text = status_text
        self.loading_label.setText(status_text)
        self._update_connection_state()
        self._process_loading_events()

    def _end_busy(self) -> None:
        if not self._busy_operation_active:
            return
        self._busy_operation_active = False
        self._busy_status_text = ""
        self.main_loading_frame.setVisible(False)
        if self._busy_cursor_active:
            QApplication.restoreOverrideCursor()
            self._busy_cursor_active = False
        self._update_connection_state()
        self._process_loading_events()
        self._restore_busy_scroll_position()
        QTimer.singleShot(0, self._restore_busy_scroll_position)
        QTimer.singleShot(150, self._release_busy_scroll_guard)

    def _process_loading_events(self) -> None:
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _run_blocking_task(self, task: Callable[[], object]) -> object:
        result: dict[str, object] = {}
        errors: list[BaseException] = []
        completed = threading.Event()

        def runner() -> None:
            try:
                result["value"] = task()
            except BaseException as exc:
                errors.append(exc)
            finally:
                completed.set()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        while not completed.wait(0.05):
            self._process_loading_events()
        thread.join()
        self._process_loading_events()

        if errors:
            raise errors[0]
        return result.get("value")

    def _update_connection_state(self) -> None:
        connected = self.serial_service.is_connected
        selected_port = self._selected_port()

        self.connect_button.setText("Disconnect" if connected else "Connect")
        if self._busy_operation_active and self._busy_status_text:
            status_text = self._busy_status_text
        elif connected:
            status_text = f"Connected to {self.serial_service.port_name}"
        elif selected_port:
            status_text = f"Ready to connect or flash on {selected_port}"
        else:
            status_text = "Disconnected"

        busy = self._busy_operation_active
        self.status_label.setText(status_text)
        self.sections_group.setEnabled(connected and not busy)
        self._update_section_button_states()
        self.export_support_button.setEnabled(not busy and connected)
        self.firmware_group.setEnabled(not busy)
        self.flash_button.setEnabled(not busy and (connected or bool(selected_port)))
        self.connect_button.setEnabled(not busy and (connected or bool(selected_port)))
        self.reboot_button.setEnabled(not busy and connected)
        self.find_controller_button.setEnabled(not busy and not connected)
        self.manual_command_input.setEnabled(not busy and connected)
        self.manual_command_button.setEnabled(not busy and connected and bool(self.manual_command_input.text().strip()))
        self.statusBar().showMessage(status_text)

    def _update_section_button_states(self) -> None:
        direct_controls_button = self.section_buttons.get("direct_controls")
        if direct_controls_button is None:
            return

        direct_controls_button.setEnabled(
            self.serial_service.is_connected and self._controller_operating_state != "BENCH MODE"
        )

    def _append_log(self, message: str) -> None:
        logger.info(message)
        self.feedback_log.appendPlainText(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._end_busy()
        self._poll_timer.stop()
        if self.serial_service.is_connected:
            self.serial_service.disconnect()
        event.accept()

