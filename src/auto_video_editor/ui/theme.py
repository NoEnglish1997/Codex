from __future__ import annotations

from string import Template

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


# Semantic tokens derived from the UI/UX Pro Max “Short Video Editor” design
# system. Components consume roles rather than defining ad-hoc colors.
THEME_COLORS = {
    "background": "#0B1120",
    "surface": "#141C2E",
    "surface_raised": "#192134",
    "surface_input": "#0F172A",
    "surface_hover": "#202A3D",
    "surface_selected": "#201A32",
    "border": "#2A354A",
    "border_strong": "#3B4961",
    "text": "#F8FAFC",
    "text_muted": "#A7B2C5",
    "text_subtle": "#94A3B8",
    "brand": "#EC4899",
    "brand_hover": "#DB2777",
    "cta": "#2563EB",
    "cta_hover": "#1D4ED8",
    "cta_pressed": "#1E40AF",
    "danger": "#EF4444",
    "danger_surface": "#321A24",
    "focus": "#F472B6",
    "disabled": "#64748B",
    "log": "#050914",
}


APP_STYLESHEET = Template(
    r"""
QMainWindow, QWidget#appRoot { background: $background; }
QWidget {
    color: $text;
    font-family: "Segoe UI Variable", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QFrame#topBar {
    background: $surface_raised;
    border: 1px solid $border;
    border-radius: 9px;
}
QLabel#appTitle { color: $text; font-size: 21px; font-weight: 700; }
QLabel#appSubtitle, QLabel#pageSubtitle, QLabel#mutedText {
    color: $text_muted;
    font-size: 12px;
}
QLabel#statusChip {
    color: $text_muted;
    background: $surface_input;
    border: 1px solid $border_strong;
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}

QFrame#configSurface {
    background: $surface;
    border: 1px solid $border;
    border-radius: 9px;
}
QScrollArea#workspacePage,
QScrollArea#workspacePage > QWidget > QWidget,
QWidget#pageContent {
    background: $surface;
    border: 0;
}
QLabel#pageTitle { color: $text; font-size: 20px; font-weight: 700; }

QListWidget#workspaceNavigation {
    color: $text_muted;
    background: $surface_input;
    border: 0;
    border-right: 1px solid $border;
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
    padding: 10px 8px;
    outline: 0;
}
QListWidget#workspaceNavigation::item {
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 0 12px;
    font-weight: 600;
}
QListWidget#workspaceNavigation::item:hover {
    color: $text;
    background: $surface_hover;
}
QListWidget#workspaceNavigation::item:selected {
    color: #FBCFE8;
    background: $surface_selected;
    border-left: 3px solid $brand;
}
QListWidget#workspaceNavigation::item:focus { border: 1px solid $focus; }

QGroupBox {
    color: $text;
    background: $surface_raised;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 16px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #FBCFE8;
    background: $surface_raised;
}
QGroupBox#actionPanel {
    background: $surface_raised;
    border: 1px solid $border_strong;
    border-radius: 9px;
    margin-top: 0;
    padding: 10px 12px 12px 12px;
}
QGroupBox#actionPanel::title { color: transparent; background: transparent; }

QLabel { background: transparent; }
QLabel#sectionTitle {
    color: $text;
    font-size: 14px;
    font-weight: 700;
    padding-right: 5px;
}
QLabel#stageLabel {
    color: #93C5FD;
    font-size: 12px;
    font-weight: 700;
    padding: 1px 0;
}
QLabel#statusPanel, QLabel#infoPanel {
    color: $text_muted;
    background: $surface_input;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 7px 9px;
}
QLabel#coverPreview {
    color: $text_subtle;
    background: $surface_input;
    border: 1px dashed $border_strong;
    border-radius: 7px;
}
QLabel#previewCanvas {
    color: $text_muted;
    background: $log;
    border: 1px solid $border_strong;
    border-radius: 7px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {
    color: $text;
    background: $surface_input;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
    selection-color: #FFFFFF;
    selection-background-color: $cta;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QFontComboBox:hover {
    background: $surface_hover;
    border-color: $disabled;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QFontComboBox:focus {
    border: 2px solid $focus;
    padding: 3px 7px;
}
QLineEdit:read-only { color: $text_muted; background: #111827; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView {
    color: $text;
    background: $surface_raised;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 4px;
    selection-color: $text;
    selection-background-color: $surface_selected;
    outline: 0;
}
QComboBox#compactNavigation {
    min-width: 150px;
    border-color: $brand;
}

QPushButton {
    color: $text_muted;
    background: $surface_hover;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 21px;
    font-weight: 600;
}
QPushButton:hover {
    color: $text;
    background: #29354A;
    border-color: $disabled;
}
QPushButton:focus {
    color: $text;
    border: 2px solid $focus;
    padding: 5px 11px;
}
QPushButton:pressed { background: #111827; }
QPushButton:disabled {
    color: $disabled;
    background: $surface_input;
    border-color: $border;
}
QPushButton#primaryButton {
    color: #FFFFFF;
    background: $cta;
    border-color: $cta;
    padding: 7px 18px;
    font-size: 13px;
}
QPushButton#primaryButton:hover {
    color: #FFFFFF;
    background: $cta_hover;
    border-color: $cta_hover;
}
QPushButton#primaryButton:pressed { background: $cta_pressed; }
QPushButton#primaryButton:focus {
    border: 2px solid #93C5FD;
    padding: 6px 17px;
}
QPushButton#dangerButton {
    color: #FCA5A5;
    background: $danger_surface;
    border-color: #7F1D2D;
}
QPushButton#dangerButton:hover {
    color: #FFFFFF;
    background: $danger;
    border-color: $danger;
}
QPushButton#quietButton {
    color: $text_subtle;
    background: transparent;
    border-color: transparent;
    padding-left: 7px;
    padding-right: 7px;
}
QPushButton#quietButton:hover {
    color: #FCA5A5;
    background: $danger_surface;
    border-color: #7F1D2D;
}

QCheckBox { color: $text_muted; spacing: 7px; }

QSlider::groove:horizontal {
    height: 4px;
    background: $border;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: $brand; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 15px;
    margin: -6px 0;
    background: $text;
    border: 2px solid $brand;
    border-radius: 7px;
}

QTabWidget::pane {
    background: $surface_input;
    border: 1px solid $border;
    border-radius: 7px;
    top: -1px;
    padding: 7px;
}
QTabBar::tab {
    color: $text_subtle;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 8px 14px;
    font-weight: 600;
}
QTabBar::tab:hover { color: $text; background: $surface_hover; }
QTabBar::tab:selected { color: #FBCFE8; border-bottom-color: $brand; }

QTreeWidget, QTableView, QListView {
    color: $text;
    background: $surface_input;
    alternate-background-color: #111827;
    border: 1px solid $border;
    border-radius: 7px;
    outline: 0;
    gridline-color: $border;
}
QTreeWidget::item { min-height: 29px; border-bottom: 1px solid $border; }
QTreeWidget::item:selected { color: #FBCFE8; background: $surface_selected; }
QHeaderView::section {
    color: $text_muted;
    background: $surface_raised;
    border: 0;
    border-bottom: 1px solid $border;
    padding: 7px;
    font-weight: 700;
}

QProgressBar {
    background: $border;
    border: 0;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
}
QProgressBar::chunk { background: $cta; border-radius: 4px; }
QPlainTextEdit {
    color: #CBD5E1;
    background: $log;
    border: 1px solid $border;
    border-radius: 7px;
    padding: 7px;
    selection-color: #FFFFFF;
    selection-background-color: $cta;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 3px;
}
QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: 3px;
    min-height: 34px;
}
QScrollBar::handle:vertical:hover { background: $disabled; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}
QToolTip {
    color: $text;
    background: #111827;
    border: 1px solid $border_strong;
    padding: 5px 7px;
}
"""
).substitute(THEME_COLORS)


def apply_theme(app: QApplication) -> None:
    """Apply the product design system consistently across Windows and tests."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    app.setStyleSheet(APP_STYLESHEET)
