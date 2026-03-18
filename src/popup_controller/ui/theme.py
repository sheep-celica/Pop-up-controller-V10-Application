from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#16181d"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f4f7fb"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#101217"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1d24"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0f1116"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#f4f7fb"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#eef2f9"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#222733"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f4f7fb"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3da9fc"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#08111b"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#78c4ff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#707784"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#707784"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#707784"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            background-color: #16181d;
            color: #f4f7fb;
            selection-background-color: #3da9fc;
            selection-color: #08111b;
        }
        QMainWindow,
        QDialog {
            background-color: #111318;
        }
        QFrame#headerCard {
            background-color: #1b2230;
            border: 1px solid #2d3748;
            border-radius: 18px;
        }
        QFrame#loadingFrame {
            background-color: #101822;
            border: 1px solid #29445d;
            border-radius: 12px;
        }
        QFrame#metricCard {
            background-color: #141922;
            border: 1px solid #2d3748;
            border-radius: 14px;
        }
        QFrame#miniMetricCard {
            background-color: #10151d;
            border: 1px solid #293546;
            border-radius: 12px;
        }
        QFrame#editorCard {
            background-color: #121720;
            border: 1px solid #2e3c50;
            border-radius: 14px;
        }
        QStatusBar {
            background-color: #111318;
            border-top: 1px solid #2a3140;
            color: #dbe4f0;
        }
        QGroupBox {
            background-color: #1b2029;
            border: 1px solid #2c3442;
            border-radius: 14px;
            margin-top: 14px;
            padding: 18px 16px 14px 16px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            top: 2px;
            padding: 0 6px;
            color: #f4f7fb;
        }
        QLabel#heroTitle,
        QLabel#dialogTitle {
            font-size: 24px;
            font-weight: 700;
            color: #f9fbff;
            background: transparent;
        }
        QLabel#heroSubtitle,
        QLabel#dialogSummary {
            font-size: 13px;
            color: #acb6c6;
            background: transparent;
        }
        QLabel#controllerBadge {
            background-color: #0f1722;
            border: 1px solid #29445d;
            border-radius: 10px;
            padding: 10px 12px;
            color: #d7ebff;
        }
        QLabel#statusPill {
            background-color: #111927;
            border: 1px solid #2a415a;
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: 600;
            color: #d7ebff;
        }
        QLabel#loadingLabel {
            color: #d7ebff;
            font-weight: 600;
            background: transparent;
        }
        QLabel#sectionSubheading {
            color: #d7ebff;
            font-size: 13px;
            font-weight: 700;
            background: transparent;
        }
        QLabel#sectionNote {
            color: #9aabc0;
            background: transparent;
        }
        QLabel#metricCaption,
        QLabel#metricSuffix,
        QLabel#miniMetricCaption {
            color: #9aabc0;
            background: transparent;
        }
        QLabel#metricValue {
            font-size: 28px;
            font-weight: 700;
            color: #f8fbff;
            background: transparent;
        }
        QLabel#miniMetricCaption {
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#miniMetricValue {
            font-size: 24px;
            font-weight: 700;
            color: #f8fbff;
            background: transparent;
        }
        QLabel#valueField {
            color: #f4f7fb;
            font-weight: 600;
            padding: 2px 0;
        }
        QLineEdit,
        QComboBox,
        QPlainTextEdit,
        QAbstractSpinBox {
            background-color: #101217;
            border: 1px solid #313849;
            border-radius: 10px;
            padding: 8px 10px;
        }
        QLineEdit:focus,
        QComboBox:focus,
        QPlainTextEdit:focus,
        QAbstractSpinBox:focus {
            border: 1px solid #3da9fc;
        }
        QComboBox::drop-down,
        QAbstractSpinBox::up-button,
        QAbstractSpinBox::down-button {
            border: none;
            width: 26px;
            background: transparent;
        }
        QComboBox::down-arrow,
        QAbstractSpinBox::up-arrow,
        QAbstractSpinBox::down-arrow {
            width: 10px;
            height: 10px;
        }
        QPushButton {
            background-color: #293142;
            border: 1px solid #344055;
            border-radius: 10px;
            padding: 9px 14px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #324057;
        }
        QPushButton:pressed {
            background-color: #202b3e;
        }
        QPushButton:disabled {
            background-color: #1a202a;
            color: #707784;
            border-color: #252c37;
        }
        QPushButton[accent="true"] {
            background-color: #3da9fc;
            color: #08111b;
            border: 1px solid #67bdfd;
        }
        QPushButton[accent="true"]:hover {
            background-color: #57b4fd;
        }
        QPushButton[accent="true"]:pressed {
            background-color: #2f96e6;
        }
        QPushButton[sectionButton="true"] {
            text-align: left;
            padding: 14px 16px;
            font-size: 13px;
            line-height: 1.4;
        }
        QPlainTextEdit {
            font-family: Consolas;
            font-size: 12px;
        }
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollBar:vertical {
            background-color: #0f141c;
            width: 14px;
            margin: 2px;
            border-radius: 7px;
        }
        QScrollBar::handle:vertical {
            background-color: #4c6684;
            min-height: 32px;
            border-radius: 7px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #6a8caf;
        }
        QScrollBar:horizontal {
            background-color: #0f141c;
            height: 14px;
            margin: 2px;
            border-radius: 7px;
        }
        QScrollBar::handle:horizontal {
            background-color: #4c6684;
            min-width: 32px;
            border-radius: 7px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #6a8caf;
        }
        QScrollBar::add-line,
        QScrollBar::sub-line,
        QScrollBar::add-page,
        QScrollBar::sub-page {
            background: transparent;
            border: none;
        }
        QProgressBar {
            background-color: #0c121a;
            border: 1px solid #33516d;
            border-radius: 8px;
            min-height: 12px;
            padding: 2px;
        }
        QProgressBar::chunk {
            background-color: #3da9fc;
            border-radius: 6px;
        }
        QToolTip {
            background-color: #0f1116;
            color: #f4f7fb;
            border: 1px solid #344055;
        }
        """
    )