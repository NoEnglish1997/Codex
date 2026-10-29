from __future__ import annotations

import os
import importlib.util
import json
import shutil
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from auto_video_editor.models import CanvasMode, InterpolationMode, OutputQuality, TransitionType
from auto_video_editor.models import ProbeInfo, VideoItem
from auto_video_editor.project import ProjectStore
from auto_video_editor.ui.main_window import MainWindow
from auto_video_editor.ui.theme import APP_STYLESHEET, THEME_COLORS, apply_theme
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


def test_main_window_advanced_controls_build_render_settings(tmp_path, monkeypatch):
    app = _app()
    apply_theme(app)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(MainWindow, "detect_tools", lambda self: None)
    window = MainWindow()
    assert app.styleSheet() == APP_STYLESHEET
    assert window.start_button.objectName() == "primaryButton"
    assert window.config_widget.objectName() == "configSurface"
    assert window.log_view.height() == 92
    assert window.log_view.isHidden()
    assert window.inspector_tabs.count() == 4
    assert window.project_queue.accessibleName() == "批量项目队列"
    assert window.timeline_strip.accessibleName() == "视频与音频时间线"
    assert window.mode_combo.accessibleName() == "工作模式"
    assert window.video_group.isHidden()
    assert THEME_COLORS["background"] == "#E8D5C4"
    assert THEME_COLORS["cta"] == "#5D2E46"
    assert "qlineargradient" not in APP_STYLESHEET
    window._select_combo(window.transition_type_combo, TransitionType.WIPE_LEFT.value)
    window.transition_seconds.setValue(0.5)
    window._select_combo(window.canvas_mode_combo, CanvasMode.CROP.value)
    window.sharpen.setValue(0.8)
    window.normalize_audio.setChecked(True)
    window.duck_music.setChecked(True)
    window.cover_title.setText("结构安全")
    window.highlight_words.setText("安全，结构")

    settings = window._render_settings()
    assert settings.transition_type == TransitionType.WIPE_LEFT
    assert settings.transition_frames == 30
    assert settings.canvas_mode == CanvasMode.CROP
    assert settings.sharpen_amount == 0.8
    assert settings.normalize_audio is True
    assert settings.duck_music_under_source is True
    assert settings.cover_title == "结构安全"
    assert settings.subtitle_style.highlight_words == ("安全", "结构")
    window._select_combo(window.mode_combo, "manual")
    assert not window.video_group.isHidden()
    assert window.batch_group.isHidden()
    assert window.project_queue.isHidden()
    window.resize(900, 650)
    window.show()
    app.processEvents()
    assert window.preview_label.size().width() == 118
    assert window.header_log_button.isHidden()
    for index in range(window.inspector_tabs.count()):
        window.inspector_tabs.setCurrentIndex(index)
        app.processEvents()
        assert window.inspector_tabs.currentWidget().horizontalScrollBar().maximum() == 0
    window.resize(1280, 820)
    app.processEvents()
    assert window.preview_label.size().width() == 202
    assert window.header_log_button.isVisible()
    window.toggle_log_button.click()
    assert window.log_view.isVisible()
    assert window.toggle_log_button.text() == "运行日志⌃"
    window.close()
    app.processEvents()


def test_batch_scan_populates_desert_rose_project_queue_and_timeline(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(MainWindow, "detect_tools", lambda self: None)
    source = tmp_path / "批量素材" / "峡谷悬池"
    source.mkdir(parents=True)
    for name in ("1岩壁.mp4", "2吊装.mp4", "封面.png", "字幕.srt", "音乐.mp3"):
        (source / name).touch()

    window = MainWindow()
    window.batch_root_edit.setText(str(source.parent))
    window.preview_batch()

    assert window.project_queue.count() == 1
    assert "峡谷悬池" in window.project_queue.item(0).text()
    assert "2 段" in window.project_queue.item(0).text()
    assert window.timeline_strip.clip_labels == ("1岩壁", "2吊装")
    assert window.task_project_label.text() == "峡谷悬池 · 2 段素材已就绪"
    window.close()
    app.processEvents()


def test_manual_timeline_controls_real_source_order_trim_seek_and_transition(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(MainWindow, "detect_tools", lambda self: None)
    window = MainWindow()
    window._select_combo(window.mode_combo, "manual")
    for name in ("第一段.mp4", "第二段.mp4", "第三段.mp4"):
        window.video_list.add_video(_item(name))

    window.timeline_strip.reorder_requested.emit(0, 2)
    assert [item.display_name for item in window.video_list.video_items()] == [
        "第二段.mp4", "第三段.mp4", "第一段.mp4",
    ]
    window.timeline_strip.trim_requested.emit(0, 0.5, 2.5)
    assert window.video_list.video_items()[0].trim_start_seconds == 0.5
    assert window.video_list.video_items()[0].trim_end_seconds == 2.5

    window.timeline_strip.seek_requested.emit(1, 1.25)
    assert window.video_list.current_video_index() == 1
    assert window._preview_seek_seconds == 1.25
    assert window.preview_time.text() == "00:01.250"

    window.timeline_strip.transition_requested.emit(0)
    assert window.inspector_tabs.currentIndex() == 2
    assert window.advanced_tabs.currentIndex() == 1
    window.close()
    app.processEvents()


def test_manual_editor_split_undo_redo_delete_and_autosave(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setattr(MainWindow, "detect_tools", lambda self: None)
    window = MainWindow()
    window._select_combo(window.mode_combo, "manual")
    window.video_list.add_video(_item("第一段.mp4"))
    window.video_list.select_row(0)
    window._preview_seek_seconds = 1.5

    window.split_at_playhead()
    clips = window.video_list.video_items()
    assert len(clips) == 2
    assert clips[0].trim_end_seconds == 1.5
    assert clips[1].trim_start_seconds == 1.5
    assert window.undo_button.isEnabled()

    window.undo_timeline()
    assert len(window.video_list.video_items()) == 1
    assert window.redo_button.isEnabled()
    window.redo_timeline()
    assert len(window.video_list.video_items()) == 2

    window.video_list.select_row(1)
    window.delete_selected_clips()
    assert len(window.video_list.video_items()) == 1
    window._autosave_project()
    autosave = tmp_path / "config" / "AutoVideoEditor" / "autosave.autocut.json"
    assert autosave.is_file()
    assert ProjectStore.load(autosave).clips[0].trim_end_seconds == 1.5
    window.close()
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


@pytest.mark.integration
def test_manual_timeline_seek_generates_the_requested_ffmpeg_still(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    window = MainWindow()
    if not window._capabilities or not window._capabilities.ready:
        window.close()
        pytest.skip("FFmpeg is not available to the GUI")
    media = _load_media_factory()(
        tmp_path / "timeline-media", str(window._capabilities.ffmpeg_path), duration=2.1
    )
    window._select_combo(window.mode_combo, "manual")
    window.add_video_paths([media["landscape"]])
    window._on_timeline_seek(0, 1.0)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.processEvents()
        process_running = (
            window._preview_process is not None
            and window._preview_process.state() != QProcess.ProcessState.NotRunning
        )
        if not window._timeline_preview_timer.isActive() and not process_running:
            break
        time.sleep(0.01)

    assert window._preview_path.is_file()
    assert window.preview_label.pixmap() is not None
    assert not window.preview_label.pixmap().isNull()
    assert window.preview_time.text().startswith("00:01.000 / ")
    assert window.timeline_strip.selected_index == 0
    window.close()
    app.processEvents()
