from __future__ import annotations

from string import Template

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


# “Desert Rose Cinematic Atelier”: the selected Anthropic Theme Factory palette,
# extended with accessible product roles for a native Windows editing workspace.
THEME_COLORS = {
    "background": "#E8D5C4",
    "surface": "#FAF7F4",
    "surface_raised": "#FFFFFF",
    "surface_input": "#FFFDFC",
    "surface_hover": "#F5E9E5",
    "surface_selected": "#F1DCD8",
    "border": "#DDCBC4",
    "border_strong": "#C6A49B",
    "text": "#332831",
    "text_muted": "#6D5E66",
    "text_subtle": "#75656D",
    "brand": "#B87D6D",
    "brand_hover": "#A96D5E",
    "cta": "#5D2E46",
    "cta_hover": "#713753",
    "cta_pressed": "#472236",
    "danger": "#A33E4A",
    "danger_surface": "#F6E2E2",
    "focus": "#8B4B61",
    "disabled": "#A49399",
    "log": "#29141F",
    "success": "#33725C",
    "header_text": "#FFF9F7",
    "timeline": "#F6EAE2",
}


APP_STYLESHEET = Template(
    r"""
QMainWindow, QWidget#appRoot { background: $background; }
QWidget {
    color: $text;
    font-family: "Segoe UI Variable", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}
QLabel { background: transparent; }

QFrame#studioHeader { background: $cta; border: 0; }
QLabel#brandMark {
    color: $cta;
    background: #F2D9CF;
    border-radius: 9px;
    font-size: 24px;
    font-weight: 800;
}
QLabel#appTitle { color: $header_text; font-size: 22px; font-weight: 650; }
QLabel#appSubtitle { color: #E9CBD4; font-size: 11px; letter-spacing: 1px; }
QLabel#headerStatus {
    color: #F8E9ED;
    background: transparent;
    padding: 4px 8px;
    font-size: 12px;
}
QComboBox#modeSwitch {
    color: $header_text;
    background: #6C3851;
    border: 1px solid #9A6175;
    border-radius: 8px;
    padding: 7px 12px;
    min-width: 176px;
    min-height: 24px;
    font-weight: 650;
}
QComboBox#modeSwitch:hover { background: #7A405A; border-color: #D4A5A5; }
QComboBox#modeSwitch::drop-down { border: 0; width: 26px; }
QPushButton#headerButton {
    color: #F6E4E9;
    background: transparent;
    border: 1px solid transparent;
    padding: 6px 9px;
}
QPushButton#headerButton:hover { color: #FFFFFF; background: #713753; border-color: #9A6175; }

QFrame#configSurface { background: $surface; border: 0; }
QFrame#libraryPane, QFrame#inspectorPane { background: $surface; border: 0; }
QFrame#libraryPane { border-right: 1px solid $border; }
QFrame#inspectorPane { border-left: 1px solid $border; }
QFrame#centerStage { background: #F0DED2; border: 0; }
QFrame#previewStage {
    background: #3A1929;
    border: 1px solid #704257;
    border-radius: 11px;
}
QLabel#paneTitle { color: $text; font-size: 19px; font-weight: 700; }
QLabel#sectionTitle { color: $text; font-size: 14px; font-weight: 700; }
QLabel#mutedText, QLabel#pageSubtitle { color: $text_muted; font-size: 12px; }
QLabel#stageEyebrow { color: #E8C8D1; font-size: 12px; font-weight: 650; }
QLabel#previewTime { color: #F2DDE3; font-size: 12px; }
QLabel#stageLabel { color: $cta; font-size: 12px; font-weight: 700; }
QLabel#readyBadge {
    color: $success;
    background: #E6F1EB;
    border: 1px solid #BFD9CD;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 650;
}

QScrollArea#paneScroll,
QScrollArea#paneScroll > QWidget > QWidget,
QWidget#scrollContent { background: transparent; border: 0; }
QSplitter::handle { background: $border; }
QSplitter::handle:horizontal { width: 1px; }

QListWidget#projectQueue {
    color: $text;
    background: transparent;
    border: 0;
    outline: 0;
    padding: 2px 0;
}
QListWidget#projectQueue::item {
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 8px;
    padding: 8px 10px;
    margin: 2px 0;
}
QListWidget#projectQueue::item:hover { background: $surface_hover; }
QListWidget#projectQueue::item:selected {
    color: $text;
    background: $surface_selected;
    border-left-color: $brand;
}

QTabWidget#inspectorTabs::pane {
    background: $surface;
    border: 0;
    border-top: 1px solid $border;
    top: -1px;
}
QTabWidget#inspectorTabs QTabBar::tab {
    color: $text_muted;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 9px 12px;
    font-weight: 650;
}
QTabWidget#inspectorTabs QTabBar::tab:hover { color: $text; background: $surface_hover; }
QTabWidget#inspectorTabs QTabBar::tab:selected { color: $cta; border-bottom-color: $brand; }

QGroupBox {
    color: $text;
    background: transparent;
    border: 0;
    border-top: 1px solid $border;
    border-radius: 0;
    margin-top: 17px;
    padding: 15px 4px 4px 4px;
    font-weight: 650;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 1px;
    padding: 0 7px 0 0;
    color: $cta;
    background: $surface;
}
QGroupBox#libraryGroup { margin-top: 13px; }
QGroupBox#actionPanel {
    background: $surface_raised;
    border: 0;
    border-top: 1px solid $border_strong;
    margin: 0;
    padding: 9px 14px 10px 14px;
}
QGroupBox#actionPanel::title { color: transparent; background: transparent; }

QLabel#statusPanel, QLabel#infoPanel {
    color: $text_muted;
    background: #F6E9E5;
    border: 1px solid #E5CFC8;
    border-radius: 7px;
    padding: 8px 10px;
}
QLabel#coverPreview {
    color: $text_subtle;
    background: #F5EBE7;
    border: 1px dashed $border_strong;
    border-radius: 8px;
}
QLabel#previewCanvas {
    color: #E6C8D1;
    background: $log;
    border: 1px solid #744258;
    border-radius: 8px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {
    color: $text;
    background: $surface_input;
    border: 1px solid $border;
    border-radius: 7px;
    padding: 5px 8px;
    min-height: 24px;
    selection-color: #FFFFFF;
    selection-background-color: $cta;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QFontComboBox:hover { background: #FFFFFF; border-color: $border_strong; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QFontComboBox:focus { border: 2px solid $focus; padding: 4px 7px; }
QLineEdit:read-only { color: $text_muted; background: #F5EFEC; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView {
    color: $text;
    background: $surface_raised;
    border: 1px solid $border_strong;
    border-radius: 7px;
    padding: 4px;
    selection-color: $text;
    selection-background-color: $surface_selected;
    outline: 0;
}

QPushButton {
    color: $text;
    background: $surface_raised;
    border: 1px solid $border_strong;
    border-radius: 7px;
    padding: 6px 11px;
    min-height: 22px;
    font-weight: 600;
}
QPushButton:hover { background: $surface_hover; border-color: $brand; }
QPushButton:focus { border: 2px solid $focus; padding: 5px 10px; }
QPushButton:pressed { background: $surface_selected; }
QPushButton:disabled { color: $disabled; background: #F0EBE8; border-color: $border; }
QPushButton#primaryButton {
    color: #FFFFFF;
    background: $cta;
    border-color: $cta;
    padding: 8px 18px;
    font-size: 13px;
}
QPushButton#primaryButton:hover { color: #FFFFFF; background: $cta_hover; border-color: $cta_hover; }
QPushButton#primaryButton:pressed { background: $cta_pressed; }
QPushButton#primaryButton:focus { border: 2px solid #D4A5A5; padding: 7px 17px; }
QPushButton#dangerButton { color: $danger; background: $danger_surface; border-color: #D9A7AA; }
QPushButton#dangerButton:hover { color: #FFFFFF; background: $danger; border-color: $danger; }
QPushButton#quietButton { color: $text_muted; background: transparent; border-color: transparent; }
QPushButton#quietButton:hover { color: $cta; background: $surface_hover; border-color: transparent; }
QPushButton#clayButton { color: #FFFFFF; background: $brand; border-color: $brand; }
QPushButton#clayButton:hover { color: #FFFFFF; background: $brand_hover; border-color: $brand_hover; }
QPushButton#playButton {
    color: #FFFFFF;
    background: $brand;
    border: 0;
    border-radius: 17px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0;
}

QCheckBox { color: $text_muted; spacing: 7px; }
QSlider::groove:horizontal { height: 4px; background: #D8C7C3; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $brand; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: $surface_raised;
    border: 2px solid $brand;
    border-radius: 7px;
}

QTabWidget::pane {
    background: $surface_input;
    border: 1px solid $border;
    border-radius: 7px;
    top: -1px;
    padding: 6px;
}
QTabBar::tab {
    color: $text_subtle;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    padding: 8px 11px;
    font-weight: 600;
}
QTabBar::tab:hover { color: $text; background: $surface_hover; }
QTabBar::tab:selected { color: $cta; border-bottom-color: $brand; }

QTreeWidget, QTableView, QListView {
    color: $text;
    background: $surface_input;
    alternate-background-color: #FAF3EF;
    border: 1px solid $border;
    border-radius: 7px;
    outline: 0;
    gridline-color: $border;
}
QTreeWidget::item { min-height: 29px; border-bottom: 1px solid #EEE1DC; }
QTreeWidget::item:selected { color: $text; background: $surface_selected; }
QHeaderView::section {
    color: $text_muted;
    background: #F3E7E2;
    border: 0;
    border-bottom: 1px solid $border;
    padding: 7px;
    font-weight: 650;
}

QWidget#timelineCanvas { background: $timeline; border: 1px solid $border; border-radius: 9px; }
QProgressBar {
    background: #DDD1CE;
    border: 0;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
}
QProgressBar::chunk { background: $brand; border-radius: 4px; }
QPlainTextEdit {
    color: #F1DDE3;
    background: $log;
    border: 1px solid #6E4054;
    border-radius: 7px;
    padding: 7px;
    selection-color: #FFFFFF;
    selection-background-color: $brand;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}

QScrollBar:vertical { background: transparent; width: 9px; margin: 3px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 3px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: $brand; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; height: 0; }
QToolTip { color: $header_text; background: $log; border: 1px solid #805168; padding: 5px 7px; }
"""
).substitute(THEME_COLORS)


def apply_theme(app: QApplication) -> None:
    """Apply the selected Desert Rose product design system."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    app.setStyleSheet(APP_STYLESHEET)
