from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APP_STYLESHEET = r"""
QMainWindow {
    background: #F3F6FB;
}

QWidget {
    color: #172033;
    font-size: 13px;
}

QWidget#configSurface,
QScrollArea,
QScrollArea > QWidget > QWidget {
    background: transparent;
}

QFrame#heroCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #172554,
        stop: 0.55 #1D4ED8,
        stop: 1 #2563EB
    );
    border: 0;
    border-radius: 16px;
}

QLabel#heroTitle {
    color: #FFFFFF;
    font-size: 27px;
    font-weight: 700;
}

QLabel#heroSubtitle {
    color: #DBEAFE;
    font-size: 13px;
}

QLabel#heroChip {
    color: #EFF6FF;
    background: rgba(255, 255, 255, 36);
    border: 1px solid rgba(255, 255, 255, 68);
    border-radius: 11px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

QGroupBox {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    margin-top: 18px;
    padding: 18px 14px 14px 14px;
    font-weight: 600;
    color: #1E293B;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 7px;
    color: #334155;
    background: #FFFFFF;
}

QGroupBox#actionPanel {
    border: 1px solid #CBD5E1;
    border-radius: 14px;
    margin-top: 0;
    padding: 12px 14px 14px 14px;
}

QGroupBox#actionPanel::title {
    color: transparent;
    background: transparent;
}

QLabel {
    background: transparent;
}

QLabel#mutedText {
    color: #64748B;
    font-size: 12px;
}

QLabel#statusPanel,
QLabel#infoPanel {
    color: #334155;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 8px 10px;
}

QLabel#stageLabel {
    color: #1E3A8A;
    font-size: 13px;
    font-weight: 700;
    padding: 2px 0;
}

QLabel#sectionTitle {
    color: #334155;
    font-size: 14px;
    font-weight: 700;
    padding-right: 6px;
}

QLabel#coverPreview,
QLabel#previewCanvas {
    color: #94A3B8;
    background: #F8FAFC;
    border: 1px dashed #CBD5E1;
    border-radius: 10px;
}

QLabel#previewCanvas {
    color: #CBD5E1;
    background: #111827;
    border: 1px solid #334155;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QFontComboBox {
    color: #172033;
    background: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 5px 9px;
    min-height: 24px;
    selection-background-color: #2563EB;
}

QLineEdit:hover,
QComboBox:hover,
QSpinBox:hover,
QDoubleSpinBox:hover,
QFontComboBox:hover {
    border-color: #94A3B8;
    background: #FFFFFF;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QFontComboBox:focus {
    border: 2px solid #3B82F6;
    padding: 4px 8px;
    background: #FFFFFF;
}

QLineEdit:read-only {
    color: #475569;
    background: #F1F5F9;
}

QComboBox::drop-down {
    border: 0;
    width: 28px;
}

QComboBox QAbstractItemView {
    color: #172033;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 4px;
    selection-color: #1D4ED8;
    selection-background-color: #DBEAFE;
    outline: 0;
}

QPushButton {
    color: #334155;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 7px 13px;
    min-height: 20px;
    font-weight: 600;
}

QPushButton:hover {
    color: #1D4ED8;
    background: #EFF6FF;
    border-color: #93C5FD;
}

QPushButton:pressed {
    background: #DBEAFE;
}

QPushButton:disabled {
    color: #94A3B8;
    background: #F1F5F9;
    border-color: #E2E8F0;
}

QPushButton#primaryButton {
    color: #FFFFFF;
    background: #2563EB;
    border-color: #2563EB;
    padding: 9px 20px;
    font-size: 14px;
}

QPushButton#primaryButton:hover {
    color: #FFFFFF;
    background: #1D4ED8;
    border-color: #1D4ED8;
}

QPushButton#primaryButton:pressed {
    background: #1E40AF;
}

QPushButton#dangerButton {
    color: #B91C1C;
    background: #FFF7F7;
    border-color: #FECACA;
}

QPushButton#dangerButton:hover {
    color: #FFFFFF;
    background: #DC2626;
    border-color: #DC2626;
}

QPushButton#quietButton {
    color: #64748B;
    background: transparent;
    border-color: transparent;
    padding-left: 8px;
    padding-right: 8px;
}

QPushButton#quietButton:hover {
    color: #B91C1C;
    background: #FEF2F2;
    border-color: #FEE2E2;
}

QCheckBox {
    spacing: 8px;
    color: #334155;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid #94A3B8;
    border-radius: 5px;
    background: #FFFFFF;
}

QCheckBox::indicator:hover {
    border-color: #3B82F6;
}

QCheckBox::indicator:checked {
    background: #2563EB;
    border: 4px solid #2563EB;
}

QSlider::groove:horizontal {
    height: 5px;
    background: #E2E8F0;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #3B82F6;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 16px;
    margin: -6px 0;
    background: #FFFFFF;
    border: 2px solid #2563EB;
    border-radius: 8px;
}

QTabWidget::pane {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 9px;
    top: -1px;
    padding: 8px;
}

QTabBar::tab {
    color: #64748B;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 9px 16px;
    font-weight: 600;
}

QTabBar::tab:hover {
    color: #2563EB;
    background: #EFF6FF;
}

QTabBar::tab:selected {
    color: #1D4ED8;
    border-bottom-color: #2563EB;
}

QTreeWidget,
QTableView,
QListView {
    color: #1E293B;
    background: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    outline: 0;
    gridline-color: #E2E8F0;
}

QTreeWidget::item {
    min-height: 30px;
    border-bottom: 1px solid #F1F5F9;
}

QTreeWidget::item:selected {
    color: #1E3A8A;
    background: #DBEAFE;
}

QHeaderView::section {
    color: #475569;
    background: #F8FAFC;
    border: 0;
    border-bottom: 1px solid #E2E8F0;
    padding: 8px;
    font-weight: 700;
}

QProgressBar {
    color: #1E3A8A;
    background: #E2E8F0;
    border: 0;
    border-radius: 6px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
    font-size: 10px;
}

QProgressBar::chunk {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #2563EB, stop: 1 #06B6D4);
    border-radius: 6px;
}

QPlainTextEdit {
    color: #CBD5E1;
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 9px;
    padding: 8px;
    selection-color: #FFFFFF;
    selection-background-color: #1D4ED8;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 3px;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 4px;
    min-height: 36px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QToolTip {
    color: #F8FAFC;
    background: #172033;
    border: 1px solid #334155;
    padding: 5px 7px;
}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the same predictable theme on Windows and test platforms."""
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLESHEET)
