from __future__ import annotations

import os
import importlib.util
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from auto_video_editor.models import InterpolationMode
from auto_video_editor.models import ProbeInfo, VideoItem
from auto_video_editor.ui.main_window import MainWindow
from auto_video_editor.ui.video_list_widget import VideoListWidget


def _app():
    return QApplication.instance() or QApplication([])


def _item(name: str) -> VideoItem:
    path = Path(name)
    return VideoItem(
        path,
        name,
        ProbeInfo(path, 3.0, 1920, 1080, 1920, 1080, has_video=True),
    )


def test_video_list_preserves_manual_order_and_duplicates():
    app = _app()
    widget = VideoListWidget()
    widget.add_video(_item("z.mp4"))
    widget.add_video(_item("a.mp4"))
    widget.add_video(_item("a.mp4"))
    assert [item.display_name for item in widget.video_items()] == ["z.mp4", "a.mp4", "a.mp4"]
    widget.setCurrentItem(widget.topLevelItem(2))
    widget.move_selected(-1)
    assert widget.indexOfTopLevelItem(widget.currentItem()) == 1
    widget.close()
    app.processEvents()


def _load_media_factory():
    path = Path(__file__).parents[1] / "scripts" / "create_test_media.py"
    spec = importlib.util.spec_from_file_location("create_test_media_for_ui", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_test_media


@pytest.mark.integration
def test_gui_can_import_reorder_and_render_without_freezing(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    window = MainWindow()
    if not window._capabilities or not window._capabilities.ready:
        window.close()
        pytest.skip("FFmpeg is not available to the GUI")
    media = _load_media_factory()(tmp_path / "gui-media", str(window._capabilities.ffmpeg_path), duration=2.1)
    window.add_video_paths([media["landscape"], media["portrait"]])
    window.video_list.setCurrentItem(window.video_list.topLevelItem(1))
    window.video_list.move_selected(-1)
    assert window.video_list.video_items()[0].source_path == media["portrait"]
    window._select_combo(window.interpolation_combo, InterpolationMode.FAST.value)
    window._set_optional_path(window.music_edit, str(media["long_music"]), "music")
    assert "6.000" in window.music_info.text()
    window.output_dir_edit.setText(str(tmp_path / "gui-output"))
    window.filename_edit.setText("GUI 流程.mp4")
    window.start_button.click()
    deadline = time.monotonic() + 120
    while window._thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert window._thread is None, "GUI render worker did not stop"
    assert window._last_result is not None, window.log_view.toPlainText()
    assert window._last_result.output_path.is_file()
    assert window._last_result.verification.valid
    assert window._last_result.verification.probe is not None
    assert window._last_result.verification.probe.has_audio
    assert window.progress_bar.value() == 100
    window.close()
    app.processEvents()
