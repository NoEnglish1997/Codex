from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from ..media.validation import VIDEO_EXTENSIONS
from ..models import VideoItem


class VideoListWidget(QTreeWidget):
    files_dropped = Signal(list)
    order_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(6)
        self.setHeaderLabels(["文件", "时长", "分辨率", "FPS", "音轨", "裁剪"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSortingEnabled(False)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, self.header().ResizeMode.Stretch)
        for column in range(1, 6):
            self.header().setSectionResizeMode(column, self.header().ResizeMode.ResizeToContents)

    def add_video(self, video: VideoItem) -> None:
        probe = video.probe
        duration = f"{probe.duration_seconds:.2f}s" if probe else "未读取"
        resolution = f"{probe.display_width}×{probe.display_height}" if probe else "—"
        frame_rate = f"{float(probe.avg_frame_rate):.3f}" if probe and probe.avg_frame_rate else "—"
        audio = "有" if probe and probe.has_audio else "无"
        trim = self._trim_text(video)
        item = QTreeWidgetItem([video.display_name, duration, resolution, frame_rate, audio, trim])
        item.setData(0, Qt.ItemDataRole.UserRole, video)
        item.setToolTip(0, str(video.source_path))
        self.addTopLevelItem(item)
        self.order_changed.emit()

    def video_items(self) -> tuple[VideoItem, ...]:
        return tuple(
            self.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
            for index in range(self.topLevelItemCount())
        )

    def current_video(self) -> VideoItem | None:
        item = self.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def set_selected_trim(self, start_seconds: float, end_seconds: float) -> int:
        changed = 0
        for item in self.selectedItems():
            video = item.data(0, Qt.ItemDataRole.UserRole)
            updated = replace(
                video,
                trim_start_seconds=max(0.0, start_seconds),
                trim_end_seconds=max(0.0, end_seconds),
            )
            item.setData(0, Qt.ItemDataRole.UserRole, updated)
            item.setText(5, self._trim_text(updated))
            changed += 1
        if changed:
            self.order_changed.emit()
        return changed

    @staticmethod
    def _trim_text(video: VideoItem) -> str:
        if video.trim_start_seconds <= 0 and video.trim_end_seconds <= 0:
            return "完整"
        end = f"{video.trim_end_seconds:.2f}s" if video.trim_end_seconds > 0 else "结尾"
        return f"{video.trim_start_seconds:.2f}s–{end}"

    def remove_selected(self) -> None:
        rows = sorted({self.indexOfTopLevelItem(item) for item in self.selectedItems()}, reverse=True)
        for row in rows:
            if row >= 0:
                self.takeTopLevelItem(row)
        if rows:
            self.order_changed.emit()

    def move_selected(self, delta: int) -> None:
        current = self.currentItem()
        if current is None:
            return
        row = self.indexOfTopLevelItem(current)
        target = row + delta
        if row < 0 or target < 0 or target >= self.topLevelItemCount():
            return
        item = self.takeTopLevelItem(row)
        self.insertTopLevelItem(target, item)
        self.setCurrentItem(item)
        self.order_changed.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._has_video_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._has_video_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._has_video_urls(event.mimeData()):
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        self.order_changed.emit()

    @staticmethod
    def _has_video_urls(mime: QMimeData) -> bool:
        return mime.hasUrls() and any(
            Path(url.toLocalFile()).suffix.lower() in VIDEO_EXTENSIONS for url in mime.urls()
        )
