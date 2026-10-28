from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel


class PositionPreviewLabel(QLabel):
    """Preview surface that reports a normalized foreground anchor while dragging."""

    position_changed = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(270, 480)
        self.setText("点击“生成预览”查看画面\n拖动画面可设置自定义位置")
        self.setStyleSheet("border: 1px solid palette(mid); background: #181818; color: #dddddd;")
        self.setMouseTracking(True)
        self._dragging = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._emit_position(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._emit_position(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._emit_position(event)
        super().mouseReleaseEvent(event)

    def _emit_position(self, event: QMouseEvent) -> None:
        x = round(min(1.0, max(0.0, event.position().x() / max(1, self.width()))) * 100)
        y = round(min(1.0, max(0.0, event.position().y() / max(1, self.height()))) * 100)
        self.position_changed.emit(x, y)
