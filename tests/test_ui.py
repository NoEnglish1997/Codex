from __future__ import annotations

import os
import importlib.util
import json
import shutil
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from auto_video_editor.models import InterpolationMode, OutputQuality
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
def test_gui_batch_render_continues_after_invalid_folder_and_downloads_log(tmp_path, monkeypatch):
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
    batch_root = tmp_path / "batch-root"
    valid = batch_root / "素材10"
    invalid = batch_root / "素材2"
    valid.mkdir(parents=True)
    invalid.mkdir(parents=True)
    shutil.copy2(media["landscape"], valid / "视频1.mp4")
    shutil.copy2(media["portrait"], valid / "视频2.mp4")
    shutil.copy2(media["cover"], valid / "封面.png")
    shutil.copy2(media["subtitle"], valid / "字幕.srt")
    shutil.copy2(media["music_mp3"], valid / "配乐.mp3")
    shutil.copy2(media["landscape"], invalid / "只有一段.mp4")

    window._select_combo(window.interpolation_combo, InterpolationMode.FAST.value)
    window._select_combo(window.quality_combo, OutputQuality.BITRATE_12M.value)
    window._set_optional_path(window.logo_edit, str(media["logo"]), "logo")
    output_dir = tmp_path / "gui-output"
    output_dir.mkdir()
    window.batch_root_edit.setText(str(batch_root))
    window.output_dir_edit.setText(str(output_dir))
    window.filename_edit.setText("批量成片_")
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
    report = json.loads(window._last_result.report_path.read_text(encoding="utf-8"))
    assert report["settings"]["output_quality"] == "bitrate_12m"
    assert window.progress_bar.value() == 100
    assert [path.name for path in output_dir.iterdir()] == ["批量成片_1.mp4"]
    assert "失败/跳过 1" in window.stage_label.text()
    assert "素材2" in window.log_view.toPlainText()

    log_path = tmp_path / "下载日志.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(log_path), ""))
    window.download_log_button.click()
    assert log_path.read_text(encoding="utf-8-sig").endswith("\n")
    assert "批量完成" in log_path.read_text(encoding="utf-8-sig")
    window.close()
    app.processEvents()
