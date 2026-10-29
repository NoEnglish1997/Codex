from __future__ import annotations

import math
from dataclasses import dataclass, replace

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


@dataclass(frozen=True)
class TimelineClipView:
    label: str
    duration_seconds: float
    trim_start_seconds: float = 0.0
    trim_end_seconds: float = 0.0

    @property
    def effective_end(self) -> float:
        return self.trim_end_seconds if self.trim_end_seconds > 0 else self.duration_seconds

    @property
    def effective_duration(self) -> float:
        return max(0.1, self.effective_end - self.trim_start_seconds)


class TimelineStrip(QWidget):
    """Interactive manual-edit timeline and read-only batch sequence strip."""

    clip_selected = Signal(int)
    reorder_requested = Signal(int, int)
    trim_requested = Signal(int, float, float)
    seek_requested = Signal(int, float)
    transition_requested = Signal(int)

    _CLIP_COLORS = ("#D9B8B0", "#C99B92", "#D6AEA7", "#B87D6D")
    _LABEL_WIDTH = 56
    _CLIP_TOP = 30.0
    _CLIP_HEIGHT = 70.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineCanvas")
        self.setAccessibleName("视频与音频时间线")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(320, 154)
        self.setMaximumHeight(172)
        self._clips = [
            TimelineClipView("岩壁", 12),
            TimelineClipView("结构", 18),
            TimelineClipView("吊装", 15),
            TimelineClipView("成品", 20),
        ]
        self._interactive = False
        self._selected_index = -1
        self._progress = 0.34
        self._playhead: tuple[int, float] | None = None
        self._clip_rects: list[QRectF] = []
        self._transition_rects: list[QRectF] = []
        self._drag_mode: str | None = None
        self._drag_index = -1
        self._drag_target = -1
        self._drag_start_x = 0.0
        self._drag_original: TimelineClipView | None = None
        self._zoom_factor = 1.0
        self._snap_enabled = True

    def sizeHint(self) -> QSize:
        return QSize(round(620 * self._zoom_factor), 160)

    def set_zoom_factor(self, factor: float) -> None:
        self._zoom_factor = min(4.0, max(1.0, factor))
        self.setMinimumWidth(round(320 * self._zoom_factor))
        self.updateGeometry()
        self.update()

    def set_snap_enabled(self, enabled: bool) -> None:
        self._snap_enabled = enabled

    @property
    def clip_labels(self) -> tuple[str, ...]:
        return tuple(clip.label for clip in self._clips)

    @property
    def selected_index(self) -> int:
        return self._selected_index

    def set_interactive(self, enabled: bool) -> None:
        self._interactive = enabled
        self.setToolTip(
            "点击片段选中；拖动片段排序；拖动两侧手柄裁剪；点击刻度或音轨定位预览"
            if enabled
            else "批量模式按扫描规则显示片段顺序；切换到手动剪辑可直接编辑时间线"
        )
        self.update()

    def set_clips(self, labels: list[str]) -> None:
        cleaned = [label.strip()[:12] for label in labels if label.strip()]
        self._clips = [TimelineClipView(label, 10.0) for label in cleaned[:8]]
        if not self._clips:
            self._clips = [TimelineClipView("等待素材", 10.0)]
        self._selected_index = -1
        self._playhead = None
        self.update()

    def set_manual_clips(self, clips: list[TimelineClipView]) -> None:
        self._clips = list(clips)
        self._interactive = True
        if self._selected_index >= len(self._clips):
            self._selected_index = len(self._clips) - 1
        self.update()

    def set_selected_index(self, index: int) -> None:
        self._selected_index = index if 0 <= index < len(self._clips) else -1
        self.update()

    def set_playhead(self, index: int, source_seconds: float) -> None:
        if not 0 <= index < len(self._clips):
            return
        clip = self._clips[index]
        value = min(clip.effective_end, max(clip.trim_start_seconds, source_seconds))
        self._playhead = (index, value)
        self._selected_index = index
        self.update()

    def set_progress(self, value: int) -> None:
        self._progress = min(1.0, max(0.0, value / 100))
        if not self._interactive:
            self._playhead = None
        self.update()

    def _layout_tracks(self) -> tuple[float, float]:
        timeline_left = self._LABEL_WIDTH + 8.0
        timeline_right = max(timeline_left + 1, self.width() - 12.0)
        track_width = timeline_right - timeline_left
        gap = 5.0
        count = max(1, len(self._clips))
        usable = max(1.0, track_width - gap * (count - 1))
        total_duration = sum(clip.effective_duration for clip in self._clips) or 1.0
        minimum = min(42.0, usable / count)
        flexible = max(0.0, usable - minimum * count)
        self._clip_rects = []
        x = timeline_left
        for clip in self._clips:
            width = minimum + flexible * clip.effective_duration / total_duration
            self._clip_rects.append(QRectF(x, self._CLIP_TOP, width, self._CLIP_HEIGHT))
            x += width + gap
        self._transition_rects = []
        for first, second in zip(self._clip_rects, self._clip_rects[1:]):
            middle = (first.right() + second.left()) / 2
            self._transition_rects.append(QRectF(middle - 8, 50, 16, 29))
        return timeline_left, track_width

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#F6EAE2"))
        timeline_left, track_width = self._layout_tracks()

        painter.setPen(QPen(QColor("#B49CA4"), 1))
        painter.setFont(QFont("Segoe UI Variable", 8))
        total_seconds = sum(clip.effective_duration for clip in self._clips)
        for index in range(5):
            x = timeline_left + track_width * index / 4
            painter.drawLine(int(x), 14, int(x), 20)
            seconds = round(total_seconds * index / 4)
            painter.drawText(
                QRectF(x - 20, 1, 44, 13),
                Qt.AlignmentFlag.AlignCenter,
                f"{seconds // 60:02d}:{seconds % 60:02d}",
            )

        painter.setPen(QColor("#78656E"))
        painter.drawText(QRectF(6, 42, self._LABEL_WIDTH - 10, 28), Qt.AlignmentFlag.AlignVCenter, "视频")
        painter.drawText(QRectF(6, 111, self._LABEL_WIDTH - 10, 28), Qt.AlignmentFlag.AlignVCenter, "音频")

        for index, (clip, rect) in enumerate(zip(self._clips, self._clip_rects)):
            selected = index == self._selected_index
            painter.setPen(QPen(QColor("#5D2E46" if selected else "#B87D6D"), 2 if selected else 1))
            painter.setBrush(QColor(self._CLIP_COLORS[index % len(self._CLIP_COLORS)]))
            painter.drawRoundedRect(rect, 5, 5)

            silhouette = QPainterPath()
            silhouette.moveTo(rect.left(), rect.top() + 43)
            silhouette.lineTo(rect.left() + rect.width() * 0.24, rect.top() + 23 + (index % 2) * 5)
            silhouette.lineTo(rect.left() + rect.width() * 0.47, rect.top() + 42)
            silhouette.lineTo(rect.left() + rect.width() * 0.72, rect.top() + 18)
            silhouette.lineTo(rect.right(), rect.top() + 38)
            silhouette.lineTo(rect.right(), rect.top() + 52)
            silhouette.lineTo(rect.left(), rect.top() + 52)
            silhouette.closeSubpath()
            painter.fillPath(silhouette, QColor(93, 46, 70, 95))

            painter.fillRect(QRectF(rect.left(), rect.top() + 50, rect.width(), 20), QColor("#FAF7F4"))
            painter.setPen(QColor("#332831"))
            painter.setFont(QFont("Segoe UI Variable", 9, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(rect.left() + 7, rect.top() + 50, rect.width() - 14, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                clip.label,
            )
            if self._interactive and selected:
                painter.fillRect(QRectF(rect.left(), rect.top(), 6, rect.height()), QColor("#5D2E46"))
                painter.fillRect(QRectF(rect.right() - 6, rect.top(), 6, rect.height()), QColor("#5D2E46"))

        for index, rect in enumerate(self._transition_rects):
            painter.setPen(QPen(QColor("#FAF7F4"), 2))
            painter.setBrush(QColor("#9B596D"))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "×")
            if self._interactive:
                painter.setPen(QColor("#76505E"))
                painter.setFont(QFont("Segoe UI Variable", 7))
                painter.drawText(
                    QRectF(rect.left() - 12, rect.bottom() + 1, rect.width() + 24, 11),
                    Qt.AlignmentFlag.AlignCenter,
                    f"T{index + 1}",
                )

        audio_rect = QRectF(timeline_left, 113, track_width, 28)
        painter.setPen(QPen(QColor("#D3B8B1"), 1))
        painter.setBrush(QColor("#F1D8D4"))
        painter.drawRoundedRect(audio_rect, 5, 5)
        painter.setPen(QPen(QColor("#A65F73"), 1))
        middle = audio_rect.center().y()
        points = max(40, int(track_width / 5))
        for index in range(points):
            x = audio_rect.left() + 3 + index * (track_width - 6) / max(1, points - 1)
            amplitude = 2.5 + 7 * abs(math.sin(index * 0.69) * math.cos(index * 0.17))
            painter.drawLine(int(x), int(middle - amplitude), int(x), int(middle + amplitude))

        playhead_x = timeline_left + track_width * self._progress
        if self._playhead is not None and 0 <= self._playhead[0] < len(self._clip_rects):
            clip = self._clips[self._playhead[0]]
            rect = self._clip_rects[self._playhead[0]]
            fraction = (self._playhead[1] - clip.trim_start_seconds) / clip.effective_duration
            playhead_x = rect.left() + rect.width() * min(1.0, max(0.0, fraction))
        painter.setPen(QPen(QColor("#9F4D57"), 2))
        painter.drawLine(int(playhead_x), 20, int(playhead_x), height - 7)
        painter.setBrush(QColor("#9F4D57"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(playhead_x - 4, 16, 8, 8))

        if self._drag_mode == "reorder" and 0 <= self._drag_target < len(self._clip_rects):
            target = self._clip_rects[self._drag_target]
            painter.setPen(QPen(QColor("#5D2E46"), 3))
            painter.drawLine(int(target.left()), 26, int(target.left()), 105)

    def _clip_at(self, position) -> int:  # type: ignore[no-untyped-def]
        for index, rect in enumerate(self._clip_rects):
            if rect.adjusted(-2, -2, 2, 2).contains(position):
                return index
        return -1

    def _seek_at(self, x: float) -> None:
        if not self._clips:
            return
        index = min(
            range(len(self._clip_rects)),
            key=lambda value: abs(self._clip_rects[value].center().x() - x),
        )
        rect = self._clip_rects[index]
        fraction = min(1.0, max(0.0, (x - rect.left()) / max(1.0, rect.width())))
        clip = self._clips[index]
        source_seconds = clip.trim_start_seconds + fraction * clip.effective_duration
        self.set_playhead(index, source_seconds)
        self.clip_selected.emit(index)
        self.seek_requested.emit(index, source_seconds)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._interactive or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._layout_tracks()
        position = event.position()
        index = self._clip_at(position)
        if index >= 0:
            rect = self._clip_rects[index]
            near_start = abs(position.x() - rect.left()) <= 9
            near_end = abs(position.x() - rect.right()) <= 9
            if near_start or near_end:
                self.set_selected_index(index)
                self.clip_selected.emit(index)
                self._drag_index = index
                self._drag_target = index
                self._drag_start_x = position.x()
                self._drag_original = self._clips[index]
                self._drag_mode = "trim_start" if near_start else "trim_end"
                event.accept()
                return
        for transition_index, rect in enumerate(self._transition_rects):
            if rect.adjusted(-3, -3, 3, 8).contains(position):
                self.transition_requested.emit(transition_index)
                event.accept()
                return
        if position.y() < 26 or position.y() > 105:
            self._seek_at(position.x())
            event.accept()
            return
        if index < 0:
            return
        self.set_selected_index(index)
        self.clip_selected.emit(index)
        rect = self._clip_rects[index]
        self._drag_index = index
        self._drag_target = index
        self._drag_start_x = position.x()
        self._drag_original = self._clips[index]
        self._drag_mode = "reorder"
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position()
        if not self._interactive:
            super().mouseMoveEvent(event)
            return
        if self._drag_mode and 0 <= self._drag_index < len(self._clips):
            if self._drag_mode == "reorder":
                self._drag_target = min(
                    range(len(self._clip_rects)),
                    key=lambda value: abs(self._clip_rects[value].center().x() - position.x()),
                )
            elif self._drag_original is not None:
                rect = self._clip_rects[self._drag_index]
                seconds_per_pixel = self._drag_original.effective_duration / max(1.0, rect.width())
                delta = (position.x() - self._drag_start_x) * seconds_per_pixel
                clip = self._drag_original
                if self._drag_mode == "trim_start":
                    start = min(clip.effective_end - 0.1, max(0.0, clip.trim_start_seconds + delta))
                    if self._snap_enabled:
                        start = round(start * 60) / 60
                    self._clips[self._drag_index] = replace(clip, trim_start_seconds=start)
                else:
                    original_end = clip.effective_end
                    end = min(clip.duration_seconds, max(clip.trim_start_seconds + 0.1, original_end + delta))
                    if self._snap_enabled:
                        end = round(end * 60) / 60
                    self._clips[self._drag_index] = replace(clip, trim_end_seconds=end)
            self.update()
            event.accept()
            return
        index = self._clip_at(position)
        if index >= 0:
            rect = self._clip_rects[index]
            near_handle = abs(position.x() - rect.left()) <= 9 or abs(position.x() - rect.right()) <= 9
            self.setCursor(Qt.CursorShape.SizeHorCursor if near_handle else Qt.CursorShape.OpenHandCursor)
        elif position.y() < 26 or position.y() > 105:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            super().mouseReleaseEvent(event)
            return
        mode = self._drag_mode
        index = self._drag_index
        target = self._drag_target
        self._drag_mode = None
        self._drag_index = -1
        self._drag_target = -1
        self._drag_original = None
        self.unsetCursor()
        if mode == "reorder" and index >= 0 and target >= 0 and index != target:
            self.reorder_requested.emit(index, target)
        elif mode in {"trim_start", "trim_end"} and 0 <= index < len(self._clips):
            clip = self._clips[index]
            end = 0.0 if clip.trim_end_seconds >= clip.duration_seconds - 0.001 else clip.trim_end_seconds
            self.trim_requested.emit(index, clip.trim_start_seconds, end)
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._interactive and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self._clips:
            step = -1 if event.key() == Qt.Key.Key_Left else 1
            index = self._selected_index if self._selected_index >= 0 else 0
            index = min(len(self._clips) - 1, max(0, index + step))
            self.set_selected_index(index)
            self.clip_selected.emit(index)
            event.accept()
            return
        super().keyPressEvent(event)
