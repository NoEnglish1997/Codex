from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFontComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import SettingsStore
from ..media.ffmpeg_locator import detect_capabilities
from ..media.ffprobe import ProbeError, probe_media
from ..media.timeline import calculate_timeline
from ..media.validation import VIDEO_EXTENSIONS, validate_render_job
from ..models import (
    FFmpegCapabilities,
    InterpolationMode,
    IssueSeverity,
    MusicShortPolicy,
    RenderJob,
    RenderResult,
    RenderSettings,
    SourceAudioMode,
    SubtitleStyle,
    VideoEncoder,
    VideoItem,
)
from ..utils.paths import sanitize_output_filename
from .render_worker import RenderWorker
from .video_list_widget import VideoListWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("自动视频剪辑 V1.1")
        self.resize(1080, 780)
        self.setMinimumSize(900, 650)
        self._store = SettingsStore()
        loaded = self._store.load()
        self._settings = loaded.settings
        self._capabilities: FFmpegCapabilities | None = None
        self._thread: QThread | None = None
        self._worker: RenderWorker | None = None
        self._last_result: RenderResult | None = None
        self._close_after_render = False
        self._primary_color = "#FFFFFF"
        self._outline_color = "#000000"
        self._build_ui()
        if loaded.warning:
            self._append_log(loaded.warning)
        self.detect_tools()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.config_widget = QWidget(scroll)
        main = QVBoxLayout(self.config_widget)
        main.setSpacing(10)
        header = QLabel("自动视频剪辑")
        header.setStyleSheet("font-size: 22px; font-weight: 600;")
        main.addWidget(header)
        main.addWidget(self._build_tools_group())
        main.addWidget(self._build_video_group(), 2)
        main.addWidget(self._build_optional_group())
        main.addWidget(self._build_settings_group())
        main.addWidget(self._build_output_group())
        scroll.setWidget(self.config_widget)

        outer = QWidget(self)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.addWidget(scroll, 1)
        outer_layout.addWidget(self._build_run_group())
        self.setCentralWidget(outer)

    def _build_tools_group(self) -> QGroupBox:
        group = QGroupBox("FFmpeg 环境")
        layout = QGridLayout(group)
        self.ffmpeg_edit = QLineEdit(self._settings.ffmpeg_path)
        self.ffprobe_edit = QLineEdit(self._settings.ffprobe_path)
        ffmpeg_browse = QPushButton("浏览…")
        ffprobe_browse = QPushButton("浏览…")
        ffmpeg_browse.clicked.connect(lambda: self._choose_executable(self.ffmpeg_edit, "选择 FFmpeg"))
        ffprobe_browse.clicked.connect(lambda: self._choose_executable(self.ffprobe_edit, "选择 FFprobe"))
        self.detect_button = QPushButton("检测")
        self.detect_button.clicked.connect(self.detect_tools)
        self.tool_status = QLabel("尚未检测")
        self.tool_status.setWordWrap(True)
        layout.addWidget(QLabel("FFmpeg"), 0, 0)
        layout.addWidget(self.ffmpeg_edit, 0, 1)
        layout.addWidget(ffmpeg_browse, 0, 2)
        layout.addWidget(QLabel("FFprobe"), 1, 0)
        layout.addWidget(self.ffprobe_edit, 1, 1)
        layout.addWidget(ffprobe_browse, 1, 2)
        layout.addWidget(self.detect_button, 0, 3, 2, 1)
        layout.addWidget(self.tool_status, 2, 0, 1, 4)
        return group

    def _build_video_group(self) -> QGroupBox:
        group = QGroupBox("视频素材（列表顺序就是最终剪辑顺序，可拖拽排序）")
        layout = QVBoxLayout(group)
        self.video_list = VideoListWidget()
        self.video_list.files_dropped.connect(self.add_video_paths)
        self.video_list.order_changed.connect(self._update_estimate)
        layout.addWidget(self.video_list)
        buttons = QHBoxLayout()
        for text, callback in (
            ("添加视频…", self._choose_videos),
            ("删除", self.video_list.remove_selected),
            ("上移", lambda: self.video_list.move_selected(-1)),
            ("下移", lambda: self.video_list.move_selected(1)),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return group

    def _build_optional_group(self) -> QGroupBox:
        group = QGroupBox("封面、Logo、字幕与配乐")
        layout = QGridLayout(group)
        self.cover_edit = QLineEdit()
        self.cover_edit.setReadOnly(True)
        self.cover_preview = QLabel("无封面")
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setFixedSize(90, 120)
        self.cover_preview.setStyleSheet("border: 1px solid palette(mid);")
        self.subtitle_edit = QLineEdit()
        self.subtitle_edit.setReadOnly(True)
        self.logo_edit = QLineEdit()
        self.logo_edit.setReadOnly(True)
        self.logo_scale = QSpinBox()
        self.logo_scale.setRange(10, 300)
        self.logo_scale.setSingleStep(10)
        self.logo_scale.setSuffix("%")
        self.logo_scale.setValue(self._settings.logo_scale_percent)
        self.logo_opacity = QSpinBox()
        self.logo_opacity.setRange(0, 100)
        self.logo_opacity.setSingleStep(5)
        self.logo_opacity.setSuffix("%")
        self.logo_opacity.setValue(self._settings.logo_opacity_percent)
        self.music_edit = QLineEdit()
        self.music_edit.setReadOnly(True)
        self.music_info = QLabel("无配乐")
        cover_button = QPushButton("选择封面…")
        logo_button = QPushButton("选择 Logo…")
        subtitle_button = QPushButton("选择字幕…")
        music_button = QPushButton("选择配乐…")
        clear_cover = QPushButton("清除")
        clear_logo = QPushButton("清除")
        clear_subtitle = QPushButton("清除")
        clear_music = QPushButton("清除")
        cover_button.clicked.connect(self._choose_cover)
        logo_button.clicked.connect(self._choose_logo)
        subtitle_button.clicked.connect(self._choose_subtitle)
        music_button.clicked.connect(self._choose_music)
        clear_cover.clicked.connect(lambda: self._set_optional_path(self.cover_edit, "", "cover"))
        clear_logo.clicked.connect(lambda: self._set_optional_path(self.logo_edit, "", "logo"))
        clear_subtitle.clicked.connect(lambda: self._set_optional_path(self.subtitle_edit, "", "subtitle"))
        clear_music.clicked.connect(lambda: self._set_optional_path(self.music_edit, "", "music"))
        layout.addWidget(QLabel("封面（精确 5 帧）"), 0, 0)
        layout.addWidget(self.cover_edit, 0, 1)
        layout.addWidget(cover_button, 0, 2)
        layout.addWidget(clear_cover, 0, 3)
        layout.addWidget(self.cover_preview, 0, 4, 6, 1)
        layout.addWidget(QLabel("移动 Logo（图片）"), 1, 0)
        layout.addWidget(self.logo_edit, 1, 1)
        layout.addWidget(logo_button, 1, 2)
        layout.addWidget(clear_logo, 1, 3)
        layout.addWidget(QLabel("Logo 缩放"), 2, 0)
        layout.addWidget(self.logo_scale, 2, 1)
        layout.addWidget(QLabel("100% = 默认最大 240×240"), 2, 2, 1, 2)
        layout.addWidget(QLabel("Logo 透明度"), 3, 0)
        layout.addWidget(self.logo_opacity, 3, 1)
        layout.addWidget(QLabel("0% = 完全透明，100% = 不透明"), 3, 2, 1, 2)
        layout.addWidget(QLabel("字幕（SRT/ASS）"), 4, 0)
        layout.addWidget(self.subtitle_edit, 4, 1)
        layout.addWidget(subtitle_button, 4, 2)
        layout.addWidget(clear_subtitle, 4, 3)
        layout.addWidget(QLabel("背景音乐"), 5, 0)
        layout.addWidget(self.music_edit, 5, 1)
        layout.addWidget(music_button, 5, 2)
        layout.addWidget(clear_music, 5, 3)
        layout.addWidget(self.music_info, 6, 1, 1, 3)
        return group

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox("剪辑配置")
        layout = QGridLayout(group)
        self.interpolation_combo = QComboBox()
        self.interpolation_combo.addItem("运动补偿（默认，CPU 密集）", InterpolationMode.MOTION.value)
        self.interpolation_combo.addItem("快速 60FPS（重复/丢帧，不是运动补偿）", InterpolationMode.FAST.value)
        self._select_combo(self.interpolation_combo, self._settings.interpolation_mode)
        self.source_audio_combo = QComboBox()
        self.source_audio_combo.addItem("静音原声（默认）", SourceAudioMode.MUTE.value)
        self.source_audio_combo.addItem("保留并混合原声", SourceAudioMode.MIX.value)
        self._select_combo(self.source_audio_combo, self._settings.source_audio_mode)
        self.music_policy_combo = QComboBox()
        self.music_policy_combo.addItem("不足时循环（默认）", MusicShortPolicy.LOOP.value)
        self.music_policy_combo.addItem("结束后静音", MusicShortPolicy.SILENCE.value)
        self._select_combo(self.music_policy_combo, self._settings.music_short_policy)
        self.encoder_combo = QComboBox()
        self.encoder_combo.addItem("自动：NVENC 可用时优先", VideoEncoder.AUTO.value)
        self.encoder_combo.addItem("CPU 兼容模式（libx264）", VideoEncoder.X264.value)
        self.encoder_combo.addItem("NVENC（失败回退 x264）", VideoEncoder.NVENC.value)
        self._select_combo(self.encoder_combo, self._settings.video_encoder)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(round(self._settings.music_volume * 100))
        self.volume_label = QLabel(f"{self.volume_slider.value()}%")
        self.volume_slider.valueChanged.connect(lambda value: self.volume_label.setText(f"{value}%"))
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume_slider)
        volume_row.addWidget(self.volume_label)
        volume_widget = QWidget()
        volume_widget.setLayout(volume_row)

        self.subtitle_enabled = QCheckBox("烧录硬字幕")
        self.subtitle_enabled.setChecked(True)
        self.mirror_second_clip = QCheckBox("第 2 段视频水平镜像")
        self.mirror_second_clip.setChecked(self._settings.mirror_second_clip)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self._settings.subtitle_font_name))
        self.font_size = QSpinBox()
        self.font_size.setRange(24, 140)
        self.font_size.setValue(68)
        self.outline_width = QSpinBox()
        self.outline_width.setRange(0, 12)
        self.outline_width.setValue(5)
        self.subtitle_margin = QSpinBox()
        self.subtitle_margin.setRange(0, 800)
        self.subtitle_margin.setValue(180)
        self.primary_color_button = QPushButton("文字 #FFFFFF")
        self.outline_color_button = QPushButton("描边 #000000")
        self.primary_color_button.clicked.connect(lambda: self._choose_color(True))
        self.outline_color_button.clicked.connect(lambda: self._choose_color(False))

        layout.addWidget(QLabel("固定输出"), 0, 0)
        layout.addWidget(QLabel("1440×2560 / 9:16 / 60FPS / 1秒叠化 / 封面5帧"), 0, 1, 1, 3)
        layout.addWidget(QLabel("帧率转换"), 1, 0)
        layout.addWidget(self.interpolation_combo, 1, 1)
        layout.addWidget(QLabel("原声"), 1, 2)
        layout.addWidget(self.source_audio_combo, 1, 3)
        layout.addWidget(QLabel("音乐不足"), 2, 0)
        layout.addWidget(self.music_policy_combo, 2, 1)
        layout.addWidget(QLabel("编码器"), 2, 2)
        layout.addWidget(self.encoder_combo, 2, 3)
        layout.addWidget(QLabel("配乐音量（片尾淡出1秒）"), 3, 0)
        layout.addWidget(volume_widget, 3, 1)
        layout.addWidget(self.mirror_second_clip, 3, 2, 1, 2)
        layout.addWidget(self.subtitle_enabled, 4, 0)
        layout.addWidget(QLabel("字幕字体"), 4, 1)
        layout.addWidget(self.font_combo, 4, 2, 1, 2)
        layout.addWidget(QLabel("字幕字号"), 5, 0)
        layout.addWidget(self.font_size, 5, 1)
        layout.addWidget(QLabel("描边宽度"), 5, 2)
        layout.addWidget(self.outline_width, 5, 3)
        layout.addWidget(QLabel("底部边距"), 6, 0)
        layout.addWidget(self.subtitle_margin, 6, 1)
        layout.addWidget(self.primary_color_button, 6, 2)
        layout.addWidget(self.outline_color_button, 6, 3)
        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("输出")
        layout = QGridLayout(group)
        self.output_dir_edit = QLineEdit(self._settings.output_dir)
        browse = QPushButton("选择目录…")
        browse.clicked.connect(self._choose_output_dir)
        self.filename_edit = QLineEdit(f"edited_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        self.estimate_label = QLabel("预计总时长：请添加视频（最终以 FFprobe 实测为准）")
        layout.addWidget(QLabel("输出目录"), 0, 0)
        layout.addWidget(self.output_dir_edit, 0, 1)
        layout.addWidget(browse, 0, 2)
        layout.addWidget(QLabel("文件名"), 1, 0)
        layout.addWidget(self.filename_edit, 1, 1, 1, 2)
        layout.addWidget(self.estimate_label, 2, 0, 1, 3)
        return group

    def _build_run_group(self) -> QGroupBox:
        group = QGroupBox("任务")
        layout = QVBoxLayout(group)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("开始剪辑")
        self.cancel_button = QPushButton("取消任务")
        self.open_button = QPushButton("打开输出文件夹")
        self.cancel_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_render)
        self.cancel_button.clicked.connect(self.cancel_render)
        self.open_button.clicked.connect(self.open_output_folder)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        self.stage_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setMinimumHeight(130)
        layout.addLayout(buttons)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view)
        return group

    def _choose_executable(self, edit: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title)
        if path:
            edit.setText(path)

    def detect_tools(self) -> None:
        self.detect_button.setEnabled(False)
        try:
            capabilities = detect_capabilities(self.ffmpeg_edit.text(), self.ffprobe_edit.text())
            self._capabilities = capabilities
            state = "全部必需能力可用" if capabilities.ready else f"缺少：{', '.join(capabilities.missing_required)}"
            gpu = "NVENC 实测可用" if capabilities.nvenc_usable else "NVENC 实测不可用，将回退 x264"
            self.tool_status.setText(f"{state}；{gpu}\n{capabilities.ffmpeg_version}")
            self.ffmpeg_edit.setText(str(capabilities.ffmpeg_path))
            self.ffprobe_edit.setText(str(capabilities.ffprobe_path))
            self._settings = replace(
                self._settings,
                ffmpeg_path=str(capabilities.ffmpeg_path),
                ffprobe_path=str(capabilities.ffprobe_path),
            )
            try:
                self._store.save(self._settings)
            except OSError as exc:
                self._append_log(f"设置暂时无法保存，但 FFmpeg 仍可使用：{exc}")
        except Exception as exc:
            self._capabilities = None
            self.tool_status.setText(f"检测失败：{exc}")
        finally:
            self.detect_button.setEnabled(True)

    def _choose_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频", "", "视频 (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;所有文件 (*)"
        )
        self.add_video_paths([Path(path) for path in paths])

    def add_video_paths(self, paths: list[Path]) -> None:
        if not self._capabilities:
            QMessageBox.warning(self, "FFmpeg 不可用", "请先完成 FFmpeg/FFprobe 检测。")
            return
        for path in paths:
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                self._append_log(f"忽略不支持的视频格式：{path}")
                continue
            try:
                probe = probe_media(path, self._capabilities.ffprobe_path)
                if not probe.has_video:
                    raise ProbeError("文件没有视频轨")
                self.video_list.add_video(VideoItem(path, path.name, probe))
            except Exception as exc:
                QMessageBox.critical(self, "视频读取失败", f"{path}\n{exc}")
        self._update_estimate()

    def _choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择封面", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if path:
            self._set_optional_path(self.cover_edit, path, "cover")

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Logo", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if path:
            self._set_optional_path(self.logo_edit, path, "logo")

    def _choose_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择字幕", "", "字幕 (*.srt *.ass)")
        if path:
            self._set_optional_path(self.subtitle_edit, path, "subtitle")

    def _choose_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择配乐", "", "音频 (*.mp3 *.wav *.m4a *.aac *.flac)")
        if path:
            self._set_optional_path(self.music_edit, path, "music")

    def _set_optional_path(self, edit: QLineEdit, path: str, kind: str) -> None:
        edit.setText(path)
        if kind == "cover":
            if path:
                pixmap = QPixmap(path)
                self.cover_preview.setPixmap(
                    pixmap.scaled(
                        self.cover_preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.cover_preview.clear()
                self.cover_preview.setText("无封面")
            self._update_estimate()
        elif kind == "music":
            if not path:
                self.music_info.setText("无配乐")
            elif self._capabilities:
                try:
                    info = probe_media(Path(path), self._capabilities.ffprobe_path)
                    self.music_info.setText(f"配乐时长：{info.duration_seconds:.3f} 秒")
                except Exception as exc:
                    self.music_info.setText(f"配乐读取失败：{exc}")

    def _choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir_edit.text())
        if path:
            self.output_dir_edit.setText(path)

    def _choose_color(self, primary: bool) -> None:
        current = self._primary_color if primary else self._outline_color
        color = QColorDialog.getColor(QColor(current), self, "选择字幕颜色")
        if not color.isValid():
            return
        value = color.name().upper()
        if primary:
            self._primary_color = value
            self.primary_color_button.setText(f"文字 {value}")
        else:
            self._outline_color = value
            self.outline_color_button.setText(f"描边 {value}")

    def _update_estimate(self) -> None:
        items = self.video_list.video_items()
        if not items or any(item.probe is None for item in items):
            self.estimate_label.setText("预计总时长：请添加视频（最终以 FFprobe 实测为准）")
            return
        estimates = [max(1, round(item.probe.duration_seconds * 60)) for item in items if item.probe]
        try:
            plan = calculate_timeline(estimates, bool(self.cover_edit.text()))
            self.estimate_label.setText(
                f"预计总时长：约 {plan.duration_seconds:.3f} 秒 / {plan.total_frames} 帧；"
                "渲染后以逐片实际帧数重新计算"
            )
        except ValueError as exc:
            self.estimate_label.setText(f"预计时间线无效：{exc}")

    def _render_settings(self) -> RenderSettings:
        return RenderSettings(
            interpolation_mode=InterpolationMode(self.interpolation_combo.currentData()),
            source_audio_mode=SourceAudioMode(self.source_audio_combo.currentData()),
            music_short_policy=MusicShortPolicy(self.music_policy_combo.currentData()),
            music_volume=self.volume_slider.value() / 100,
            video_encoder=VideoEncoder(self.encoder_combo.currentData()),
            mirror_second_clip=self.mirror_second_clip.isChecked(),
            logo_scale_percent=self.logo_scale.value(),
            logo_opacity_percent=self.logo_opacity.value(),
            subtitle_enabled=self.subtitle_enabled.isChecked(),
            subtitle_style=SubtitleStyle(
                font_name=self.font_combo.currentFont().family(),
                font_size=self.font_size.value(),
                primary_color=self._primary_color,
                outline_color=self._outline_color,
                outline_width=self.outline_width.value(),
                margin_bottom=self.subtitle_margin.value(),
            ),
        )

    def _build_job(self) -> RenderJob:
        filename = sanitize_output_filename(self.filename_edit.text())
        self.filename_edit.setText(filename)
        return RenderJob(
            video_items=self.video_list.video_items(),
            cover_path=Path(self.cover_edit.text()) if self.cover_edit.text() else None,
            subtitle_path=Path(self.subtitle_edit.text()) if self.subtitle_edit.text() else None,
            music_path=Path(self.music_edit.text()) if self.music_edit.text() else None,
            output_dir=Path(self.output_dir_edit.text()).expanduser(),
            output_filename=filename,
            settings=self._render_settings(),
            logo_path=Path(self.logo_edit.text()) if self.logo_edit.text() else None,
        )

    def start_render(self) -> None:
        if self._thread is not None:
            return
        if not self._capabilities or not self._capabilities.ready:
            QMessageBox.critical(self, "无法开始", "FFmpeg 环境未通过检测。")
            return
        job = self._build_job()
        issues = validate_render_job(job)
        errors = [issue.message for issue in issues if issue.severity == IssueSeverity.ERROR]
        for issue in issues:
            if issue.severity == IssueSeverity.WARNING:
                self._append_log(f"提示：{issue.message}")
        if errors:
            QMessageBox.warning(self, "任务配置有误", "\n".join(errors))
            return
        self._save_current_settings(job.settings)
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备开始")
        self.log_view.clear()
        self._last_result = None
        self._set_running(True)
        thread = QThread(self)
        worker = RenderWorker(job, self._capabilities)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._append_log)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self._on_cancelled)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _save_current_settings(self, settings: RenderSettings) -> None:
        self._settings = replace(
            self._settings,
            output_dir=str(Path(self.output_dir_edit.text()).expanduser()),
            interpolation_mode=settings.interpolation_mode.value,
            source_audio_mode=settings.source_audio_mode.value,
            music_short_policy=settings.music_short_policy.value,
            music_volume=settings.music_volume,
            video_encoder=settings.video_encoder.value,
            mirror_second_clip=settings.mirror_second_clip,
            subtitle_font_name=settings.subtitle_style.font_name,
            logo_scale_percent=settings.logo_scale_percent,
            logo_opacity_percent=settings.logo_opacity_percent,
            ffmpeg_path=self.ffmpeg_edit.text(),
            ffprobe_path=self.ffprobe_edit.text(),
        )
        try:
            self._store.save(self._settings)
        except OSError as exc:
            self._append_log(f"设置暂时无法保存，本次任务仍会继续：{exc}")

    def cancel_render(self) -> None:
        if self._worker:
            self.stage_label.setText("正在取消…")
            self.cancel_button.setEnabled(False)
            self._worker.cancel()

    def _on_progress(self, stage: str, value: int) -> None:
        self.stage_label.setText(stage)
        self.progress_bar.setValue(min(value, 99) if value < 100 else 100)

    def _on_success(self, result: RenderResult) -> None:
        self._last_result = result
        self.stage_label.setText(f"完成：{result.output_path.name}")
        self.progress_bar.setValue(100)
        self.open_button.setEnabled(True)
        QMessageBox.information(self, "剪辑完成", f"成片已核验并保存：\n{result.output_path}")

    def _on_failure(self, message: str) -> None:
        self.stage_label.setText("失败")
        self._append_log(message)
        QMessageBox.critical(self, "剪辑失败", message)

    def _on_cancelled(self) -> None:
        self.stage_label.setText("已取消，临时文件已清理")
        self._append_log("任务已取消。")

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_running(False)
        if self._close_after_render:
            self.close()

    def _set_running(self, running: bool) -> None:
        self.config_widget.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if running:
            self.open_button.setEnabled(False)
        elif self._last_result:
            self.open_button.setEnabled(True)

    def open_output_folder(self) -> None:
        if self._last_result and self._last_result.output_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path.parent)))

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is None:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "任务仍在运行",
            "关闭窗口将取消当前 FFmpeg 任务。是否取消并在清理完成后退出？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._close_after_render = True
            self.cancel_render()
        event.ignore()
