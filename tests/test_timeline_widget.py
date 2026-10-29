from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from auto_video_editor.ui.studio_widgets import TimelineClipView, TimelineStrip


def _app():
    return QApplication.instance() or QApplication([])


def test_interactive_timeline_emits_selection_seek_trim_reorder_and_transition():
    app = _app()
    widget = TimelineStrip()
    widget.resize(700, 160)
    widget.set_manual_clips([
        TimelineClipView("第一段", 4.0),
        TimelineClipView("第二段", 6.0),
        TimelineClipView("第三段", 5.0),
    ])
    widget.set_interactive(True)
    widget.show()
    app.processEvents()

    selected = QSignalSpy(widget.clip_selected)
    reordered = QSignalSpy(widget.reorder_requested)
    trimmed = QSignalSpy(widget.trim_requested)
    sought = QSignalSpy(widget.seek_requested)
    transitioned = QSignalSpy(widget.transition_requested)

    first = widget._clip_rects[0]
    third = widget._clip_rects[2]
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=first.center().toPoint())
    assert widget.selected_index == 0
    assert selected.count() == 1

    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=first.center().toPoint())
    QTest.mouseMove(widget, third.center().toPoint(), delay=10)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=third.center().toPoint())
    assert reordered.count() == 1
    assert list(reordered.at(0)) == [0, 2]

    right_handle = QPoint(round(first.right() - 2), round(first.center().y()))
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=right_handle)
    QTest.mouseMove(widget, QPoint(right_handle.x() - 30, right_handle.y()), delay=10)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(right_handle.x() - 30, right_handle.y()))
    assert trimmed.count() == 1
    assert trimmed.at(0)[0] == 0
    assert 0 < trimmed.at(0)[2] < 4.0

    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(round(third.center().x()), 128))
    assert sought.count() == 1
    assert sought.at(0)[0] == 2

    transition = widget._transition_rects[0].center().toPoint()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=transition)
    assert transitioned.count() == 1
    assert transitioned.at(0)[0] == 0

    widget.close()
    app.processEvents()
