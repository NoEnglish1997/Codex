from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class TimelineStrip(QWidget):
    """A lightweight editor timeline used as the studio's visual anchor."""

    _CLIP_COLORS = ("#D9B8B0", "#C99B92", "#D6AEA7", "#B87D6D")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineCanvas")
        self.setAccessibleName("视频与音频时间线")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(320, 154)
        self.setMaximumHeight(172)
        self._clips = ["岩壁", "结构", "吊装", "成品"]
        self._progress = 0.34

    def sizeHint(self) -> QSize:
        return QSize(620, 160)

    def set_clips(self, labels: list[str]) -> None:
        cleaned = [label.strip()[:12] for label in labels if label.strip()]
        self._clips = cleaned[:8] or ["等待素材"]
        self.update()

    @property
    def clip_labels(self) -> tuple[str, ...]:
        return tuple(self._clips)

    def set_progress(self, value: int) -> None:
        self._progress = min(1.0, max(0.0, value / 100))
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#F6EAE2"))

        label_width = 56
        timeline_left = label_width + 8
        timeline_right = width - 12
        track_width = max(1, timeline_right - timeline_left)

        painter.setPen(QPen(QColor("#B49CA4"), 1))
        painter.setFont(QFont("Segoe UI Variable", 8))
        for index in range(5):
            x = timeline_left + track_width * index / 4
            painter.drawLine(int(x), 14, int(x), 20)
            painter.drawText(QRectF(x - 18, 1, 40, 13), Qt.AlignmentFlag.AlignCenter, f"00:{index * 15:02d}")

        painter.setPen(QColor("#78656E"))
        painter.drawText(QRectF(6, 42, label_width - 10, 28), Qt.AlignmentFlag.AlignVCenter, "视频")
        painter.drawText(QRectF(6, 111, label_width - 10, 28), Qt.AlignmentFlag.AlignVCenter, "音频")

        clip_gap = 5
        count = max(1, len(self._clips))
        clip_width = (track_width - clip_gap * (count - 1)) / count
        clip_top, clip_height = 30.0, 70.0
        for index, label in enumerate(self._clips):
            x = timeline_left + index * (clip_width + clip_gap)
            rect = QRectF(x, clip_top, clip_width, clip_height)
            painter.setPen(QPen(QColor("#B87D6D"), 1))
            painter.setBrush(QColor(self._CLIP_COLORS[index % len(self._CLIP_COLORS)]))
            painter.drawRoundedRect(rect, 5, 5)

            # Quiet mountain/building silhouettes make the strip read like footage.
            silhouette = QPainterPath()
            silhouette.moveTo(x, clip_top + 43)
            silhouette.lineTo(x + clip_width * 0.24, clip_top + 23 + (index % 2) * 5)
            silhouette.lineTo(x + clip_width * 0.47, clip_top + 42)
            silhouette.lineTo(x + clip_width * 0.72, clip_top + 18)
            silhouette.lineTo(x + clip_width, clip_top + 38)
            silhouette.lineTo(x + clip_width, clip_top + 52)
            silhouette.lineTo(x, clip_top + 52)
            silhouette.closeSubpath()
            painter.fillPath(silhouette, QColor(93, 46, 70, 95))

            painter.fillRect(QRectF(x, clip_top + 50, clip_width, 20), QColor("#FAF7F4"))
            painter.setPen(QColor("#332831"))
            painter.setFont(QFont("Segoe UI Variable", 9, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(x + 7, clip_top + 50, clip_width - 14, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )
            if index < count - 1:
                marker_x = x + clip_width + clip_gap / 2
                painter.setPen(QPen(QColor("#FAF7F4"), 2))
                painter.setBrush(QColor("#9B596D"))
                painter.drawRoundedRect(QRectF(marker_x - 7, 52, 14, 25), 3, 3)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(QRectF(marker_x - 7, 52, 14, 25), Qt.AlignmentFlag.AlignCenter, "×")

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
        painter.setPen(QPen(QColor("#9F4D57"), 2))
        painter.drawLine(int(playhead_x), 20, int(playhead_x), height - 7)
        painter.setBrush(QColor("#9F4D57"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(playhead_x - 4, 16, 8, 8))

