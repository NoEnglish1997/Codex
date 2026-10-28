from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QSize, QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices, QFont, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import SettingsStore
from ..media.batch import (
    batch_output_filename,
    scan_batch_root,
    settings_for_batch_source,
    video_items_for_batch_source,
)
from ..media.clips import effective_clip_range
from ..media.estimates import estimate_export
from ..media.ffmpeg_locator import detect_capabilities
from ..media.ffprobe import ProbeError, probe_media
from ..media.timeline import calculate_timeline
from ..media.validation import VIDEO_EXTENSIONS, validate_render_job
from ..models import (
    CanvasMode,
    CanvasPosition,
    FFmpegCapabilities,
    BatchFailure,
    BatchRenderSummary,
    BatchRenderTask,
    InterpolationMode,
    IssueSeverity,
    MusicShortPolicy,
    LogoMotion,
    OutputQuality,
    RenderJob,
    RenderResult,
    RenderSettings,
    SourceAudioMode,
    SubtitleStyle,
    TransitionType,
    VideoEncoder,
    VideoItem,
    VideoSortMode,
)
from ..presets import (
    BUILTIN_PRESETS,
    PresetStore,
    render_settings_from_mapping,
    render_settings_to_mapping,
)
from ..media.video_filters import build_enhancement_filter, build_normalization_filter
from ..media.watcher import FolderStabilityTracker
from ..utils.paths import config_dir, sanitize_output_filename
from .batch_render_worker import BatchRenderWorker
from .render_worker import RenderWorker
from .preview_widget import PositionPreviewLabel
from .video_list_widget import VideoListWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("自动视频剪辑 V3.2")
        self.resize(1080, 780)
        self.setMinimumSize(900, 650)
        self._store = SettingsStore()
        loaded = self._store.load()
        self._settings = loaded.settings
        self._profile_settings = render_settings_from_mapping(self._settings.render_profile)
        self._preset_store = PresetStore()
        self._custom_presets = self._preset_store.load_custom()
        self._capabilities: FFmpegCapabilities | None = None
        self._thread: QThread | None = None
        self._worker: RenderWorker | BatchRenderWorker | None = None
        self._last_result: RenderResult | None = None
        self._last_output_dir: Path | None = None
        self._last_manual_job: RenderJob | None = None
        self._last_manual_failed = False
        self._last_retry_tasks: tuple[BatchRenderTask, ...] = ()
        self._current_batch_tasks: tuple[BatchRenderTask, ...] = ()
        self._close_after_render = False
        self._active_mode: str | None = None
        self._batch_prefix = self._settings.output_prefix
        self._batch_template = self._settings.output_template
        self._manual_filename = f"edited_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self._primary_color = "#FFFFFF"
        self._outline_color = "#000000"
        self._highlight_color = self._profile_settings.subtitle_style.highlight_color
        self._preview_process: QProcess | None = None
        self._preview_path = config_dir() / "preview.jpg"
        self._watch_tracker = FolderStabilityTracker()
        self._build_ui()
        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self._poll_watch_folder)
        self._on_watch_toggled(self.watch_checkbox.isChecked())
        if loaded.warning:
            self._append_log(loaded.warning)
        self.detect_tools()

    def _build_ui(self) -> None:
        outer = QWidget(self)
        outer.setObjectName("appRoot")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(10)
        outer_layout.addWidget(self._build_hero())

        self.config_widget = QFrame()
        self.config_widget.setObjectName("configSurface")
        workspace = QHBoxLayout(self.config_widget)
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(10)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        self.nav_list = self._build_sidebar()
        workspace.addWidget(self.nav_list)
        workspace.addWidget(self.page_stack, 1)

        project_page, project = self._build_page_shell(
            "项目与素材",
            "选择工作模式、组织素材并设置输出位置。",
        )
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        quick_row.addWidget(self._build_mode_group(), 1)
        quick_row.addWidget(self._build_preset_group(), 2)
        project.addLayout(quick_row)
        self.batch_group = self._build_batch_group()
        project.addWidget(self.batch_group)
        self.video_group = self._build_video_group()
        project.addWidget(self.video_group)
        self.optional_group = self._build_optional_group()
        project.addWidget(self.optional_group)
        self.output_group = self._build_output_group()
        project.addWidget(self.output_group)
        project.addStretch(1)

        settings_page, settings = self._build_page_shell(
            "剪辑与效果",
            "调整画布、转场、封面、Logo、字幕与音频处理。",
        )
        settings.addWidget(self._build_settings_group())
        settings.addWidget(self._build_advanced_group())
        settings.addStretch(1)

        preview_page, preview = self._build_page_shell(
            "画面预览",
            "生成单帧预览并拖动主体位置，不必等待完整编码。",
        )
        self.preview_group = self._build_preview_group()
        preview.addWidget(self.preview_group)
        preview.addStretch(1)

        tools_page, tools = self._build_page_shell(
            "环境与工具",
            "检测本地 FFmpeg、FFprobe 与可用编码能力。",
        )
        tools.addWidget(self._build_tools_group())
        environment_note = QLabel(
            "所有视频处理均在本机完成；程序不会上传素材，也不会静默下载 FFmpeg。"
        )
        environment_note.setObjectName("infoPanel")
        environment_note.setWordWrap(True)
        tools.addWidget(environment_note)
        tools.addStretch(1)

        for page in (project_page, settings_page, preview_page, tools_page):
            self.page_stack.addWidget(page)
        self.nav_list.currentRowChanged.connect(self._set_workspace_page)
        self.compact_navigation.currentIndexChanged.connect(self._set_workspace_page)
        self.nav_list.setCurrentRow(0)

        outer_layout.addWidget(self.config_widget, 1)
        outer_layout.addWidget(self._build_run_group())
        outer_layout.setStretch(0, 0)
        outer_layout.setStretch(1, 1)
        outer_layout.setStretch(2, 0)
        self.setCentralWidget(outer)
        self._on_mode_changed()
        self._update_navigation_layout()

    def _build_hero(self) -> QFrame:
        hero = QFrame()
        hero.setObjectName("topBar")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(18, 11, 16, 11)
        layout.setSpacing(14)

        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("自动视频剪辑")
        title.setObjectName("appTitle")
        subtitle = QLabel("本地专业工作流 · 批量处理 · 单次最终编码")
        subtitle.setObjectName("appSubtitle")
        text.addWidget(title)
        text.addWidget(subtitle)
        layout.addLayout(text, 1)

        chips = QHBoxLayout()
        chips.setSpacing(7)
        self.compact_navigation = QComboBox()
        self.compact_navigation.setObjectName("compactNavigation")
        self.compact_navigation.addItems(("项目与素材", "剪辑与效果", "画面预览", "环境与工具"))
        self.compact_navigation.setAccessibleName("紧凑工作区导航")
        self.compact_navigation.setVisible(False)
        layout.addWidget(self.compact_navigation)
        self.status_chips: list[QLabel] = []
        for value in ("V3.2", "2K 竖屏", "完全本地", "非 AI"):
            chip = QLabel(value)
            chip.setObjectName("statusChip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.status_chips.append(chip)
            chips.addWidget(chip)
        layout.addLayout(chips)
        return hero

    def _set_workspace_page(self, index: int) -> None:
        if not hasattr(self, "page_stack") or not 0 <= index < self.page_stack.count():
            return
        self.page_stack.setCurrentIndex(index)
        if hasattr(self, "nav_list") and self.nav_list.currentRow() != index:
            self.nav_list.setCurrentRow(index)
        if self.compact_navigation.currentIndex() != index:
            self.compact_navigation.setCurrentIndex(index)

    def _update_navigation_layout(self) -> None:
        if not hasattr(self, "nav_list"):
            return
        compact = self.width() < 1040
        self.nav_list.setVisible(not compact)
        self.compact_navigation.setVisible(compact)
        for chip in self.status_chips[1:]:
            chip.setVisible(not compact)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_navigation_layout()

    def _build_sidebar(self) -> QListWidget:
        navigation = QListWidget()
        navigation.setObjectName("workspaceNavigation")
        navigation.setFixedWidth(176)
        navigation.setSpacing(3)
        navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for label in ("项目与素材", "剪辑与效果", "画面预览", "环境与工具"):
            navigation.addItem(label)
        for index in range(navigation.count()):
            navigation.item(index).setSizeHint(QSize(152, 42))
        navigation.setAccessibleName("工作区导航")
        return navigation

    def _build_page_shell(self, title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("workspacePage")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pageContent")
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 18)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        description = QLabel(subtitle)
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addSpacing(2)
        scroll.setWidget(content)
        return scroll, layout

    def _build_mode_group(self) -> QGroupBox:
        group = QGroupBox("工作模式")
        layout = QHBoxLayout(group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("批量文件夹（默认）", "batch")
        self.mode_combo.addItem("手动单任务", "manual")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(QLabel("模式"))
        layout.addWidget(self.mode_combo, 1)
        return group

    def _build_preset_group(self) -> QGroupBox:
        group = QGroupBox("参数预设")
        layout = QHBoxLayout(group)
        self.preset_combo = QComboBox()
        self._refresh_preset_combo()
        apply_button = QPushButton("应用预设")
        save_button = QPushButton("另存为预设…")
        delete_button = QPushButton("删除自定义预设")
        apply_button.clicked.connect(self._apply_selected_preset)
        save_button.clicked.connect(self._save_custom_preset)
        delete_button.clicked.connect(self._delete_custom_preset)
        layout.addWidget(QLabel("常用方案"))
        layout.addWidget(self.preset_combo, 1)
        layout.addWidget(apply_button)
        layout.addWidget(save_button)
        layout.addWidget(delete_button)
        return group

    def _build_batch_group(self) -> QGroupBox:
        group = QGroupBox("批量素材")
        layout = QGridLayout(group)
        self.batch_root_edit = QLineEdit(self._settings.batch_input_dir)
        browse = QPushButton("选择总文件夹…")
        browse.clicked.connect(self._choose_batch_root)
        scan = QPushButton("扫描检查")
        scan.clicked.connect(self.preview_batch)
        self.batch_status = QLabel("请选择包含多个素材子文件夹的总目录。")
        self.batch_status.setObjectName("infoPanel")
        self.batch_status.setWordWrap(True)
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItem("按文件名自然排序", VideoSortMode.NATURAL.value)
        self.sort_mode_combo.addItem("按创建时间", VideoSortMode.CREATED.value)
        self.sort_mode_combo.addItem("按修改时间", VideoSortMode.MODIFIED.value)
        self.sort_mode_combo.addItem("按 config.json 指定", VideoSortMode.CONFIG.value)
        self.sort_mode_combo.addItem("确定性随机顺序", VideoSortMode.RANDOM.value)
        self._select_combo(self.sort_mode_combo, self._settings.video_sort_mode)
        self.first_pattern_edit = QLineEdit(self._settings.first_video_pattern)
        self.first_pattern_edit.setPlaceholderText("例如：开头*.mp4（可空）")
        self.last_pattern_edit = QLineEdit(self._settings.last_video_pattern)
        self.last_pattern_edit.setPlaceholderText("例如：结尾*.mp4（可空）")
        self.output_template_edit = QLineEdit(self._settings.output_template)
        self.output_template_edit.setPlaceholderText("{prefix}{folder}_{index}_{date}.mp4")
        self.watch_checkbox = QCheckBox("监控新增子文件夹并自动处理")
        self.watch_checkbox.setChecked(self._settings.watch_enabled)
        self.watch_interval = QSpinBox()
        self.watch_interval.setRange(2, 300)
        self.watch_interval.setSuffix(" 秒")
        self.watch_interval.setValue(self._settings.watch_interval_seconds)
        self.watch_checkbox.toggled.connect(self._on_watch_toggled)
        self.watch_interval.valueChanged.connect(self._restart_watch_timer)
        layout.addWidget(QLabel("素材总目录"), 0, 0)
        layout.addWidget(self.batch_root_edit, 0, 1)
        layout.addWidget(browse, 0, 2)
        layout.addWidget(scan, 0, 3)
        layout.addWidget(QLabel("视频顺序"), 1, 0)
        layout.addWidget(self.sort_mode_combo, 1, 1)
        layout.addWidget(self.first_pattern_edit, 1, 2)
        layout.addWidget(self.last_pattern_edit, 1, 3)
        layout.addWidget(QLabel("命名模板"), 2, 0)
        layout.addWidget(self.output_template_edit, 2, 1, 1, 3)
        layout.addWidget(self.watch_checkbox, 3, 0, 1, 2)
        layout.addWidget(self.watch_interval, 3, 2)
        layout.addWidget(self.batch_status, 4, 0, 1, 4)
        return group

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
        self.tool_status.setObjectName("statusPanel")
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
        self.video_list.itemSelectionChanged.connect(self._load_selected_trim)
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
        trim_row = QHBoxLayout()
        self.trim_start = QDoubleSpinBox()
        self.trim_start.setRange(0, 36000)
        self.trim_start.setDecimals(3)
        self.trim_start.setSuffix(" 秒")
        self.trim_end = QDoubleSpinBox()
        self.trim_end.setRange(0, 36000)
        self.trim_end.setDecimals(3)
        self.trim_end.setSuffix(" 秒（0=结尾）")
        apply_trim = QPushButton("应用到选中视频")
        reset_trim = QPushButton("恢复完整时长")
        apply_trim.clicked.connect(self._apply_selected_trim)
        reset_trim.clicked.connect(self._reset_selected_trim)
        trim_row.addWidget(QLabel("裁剪开始"))
        trim_row.addWidget(self.trim_start)
        trim_row.addWidget(QLabel("裁剪结束"))
        trim_row.addWidget(self.trim_end)
        trim_row.addWidget(apply_trim)
        trim_row.addWidget(reset_trim)
        layout.addLayout(trim_row)
        return group

    def _build_optional_group(self) -> QGroupBox:
        group = QGroupBox("封面、Logo、字幕与配乐")
        layout = QGridLayout(group)
        self.cover_edit = QLineEdit()
        self.cover_edit.setReadOnly(True)
        self.cover_preview = QLabel("无封面")
        self.cover_preview.setObjectName("coverPreview")
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setFixedSize(90, 120)
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
        self.music_info.setObjectName("mutedText")
        cover_button = QPushButton("选择封面…")
        logo_button = QPushButton("选择 Logo…")
        subtitle_button = QPushButton("选择字幕…")
        music_button = QPushButton("选择配乐…")
        clear_cover = QPushButton("清除")
        clear_logo = QPushButton("清除")
        clear_subtitle = QPushButton("清除")
        clear_music = QPushButton("清除")
        for button in (clear_cover, clear_logo, clear_subtitle, clear_music):
            button.setObjectName("quietButton")
        cover_button.clicked.connect(self._choose_cover)
        logo_button.clicked.connect(self._choose_logo)
        subtitle_button.clicked.connect(self._choose_subtitle)
        music_button.clicked.connect(self._choose_music)
        clear_cover.clicked.connect(lambda: self._set_optional_path(self.cover_edit, "", "cover"))
        clear_logo.clicked.connect(lambda: self._set_optional_path(self.logo_edit, "", "logo"))
        clear_subtitle.clicked.connect(lambda: self._set_optional_path(self.subtitle_edit, "", "subtitle"))
        clear_music.clicked.connect(lambda: self._set_optional_path(self.music_edit, "", "music"))
        cover_label = QLabel("封面图片")
        subtitle_label = QLabel("字幕（SRT/ASS）")
        music_label = QLabel("背景音乐")
        layout.addWidget(cover_label, 0, 0)
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
        layout.addWidget(subtitle_label, 4, 0)
        layout.addWidget(self.subtitle_edit, 4, 1)
        layout.addWidget(subtitle_button, 4, 2)
        layout.addWidget(clear_subtitle, 4, 3)
        layout.addWidget(music_label, 5, 0)
        layout.addWidget(self.music_edit, 5, 1)
        layout.addWidget(music_button, 5, 2)
        layout.addWidget(clear_music, 5, 3)
        layout.addWidget(self.music_info, 6, 1, 1, 3)
        self.manual_asset_widgets = (
            cover_label,
            self.cover_edit,
            cover_button,
            clear_cover,
            self.cover_preview,
            subtitle_label,
            self.subtitle_edit,
            subtitle_button,
            clear_subtitle,
            music_label,
            self.music_edit,
            music_button,
            clear_music,
            self.music_info,
        )
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
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("标准：智能压缩（CRF/CQ 19）", OutputQuality.STANDARD.value)
        self.quality_combo.addItem("高质量：更清晰、更大（CRF/CQ 16）", OutputQuality.HIGH.value)
        self.quality_combo.addItem("超高质量：大文件（CRF/CQ 14）", OutputQuality.ULTRA.value)
        self.quality_combo.addItem("稳定 12 Mbps（20秒约30MB）", OutputQuality.BITRATE_12M.value)
        self.quality_combo.addItem("稳定 16 Mbps（20秒约40MB，接近剪映）", OutputQuality.BITRATE_16M.value)
        self.quality_combo.addItem("稳定 20 Mbps（20秒约50MB）", OutputQuality.BITRATE_20M.value)
        self._select_combo(self.quality_combo, self._settings.output_quality)
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
        self.subtitle_enabled.setChecked(self._profile_settings.subtitle_enabled)
        self.mirror_second_clip = QCheckBox("第 2 段视频水平镜像")
        self.mirror_second_clip.setChecked(self._settings.mirror_second_clip)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self._settings.subtitle_font_name or self._profile_settings.subtitle_style.font_name))
        self.font_size = QSpinBox()
        self.font_size.setRange(24, 140)
        self.font_size.setValue(self._profile_settings.subtitle_style.font_size)
        self.outline_width = QSpinBox()
        self.outline_width.setRange(0, 12)
        self.outline_width.setValue(self._profile_settings.subtitle_style.outline_width)
        self.subtitle_margin = QSpinBox()
        self.subtitle_margin.setRange(0, 800)
        self.subtitle_margin.setValue(self._profile_settings.subtitle_style.margin_bottom)
        self._primary_color = self._profile_settings.subtitle_style.primary_color
        self._outline_color = self._profile_settings.subtitle_style.outline_color
        self.primary_color_button = QPushButton(f"文字 {self._primary_color}")
        self.outline_color_button = QPushButton(f"描边 {self._outline_color}")
        self.primary_color_button.clicked.connect(lambda: self._choose_color(True))
        self.outline_color_button.clicked.connect(lambda: self._choose_color(False))

        layout.addWidget(QLabel("固定输出"), 0, 0)
        layout.addWidget(QLabel("1440×2560 / 9:16 / 60FPS；转场和封面时长可在高级设置调整"), 0, 1, 1, 3)
        layout.addWidget(QLabel("帧率转换"), 1, 0)
        layout.addWidget(self.interpolation_combo, 1, 1)
        layout.addWidget(QLabel("原声"), 1, 2)
        layout.addWidget(self.source_audio_combo, 1, 3)
        layout.addWidget(QLabel("音乐不足"), 2, 0)
        layout.addWidget(self.music_policy_combo, 2, 1)
        layout.addWidget(QLabel("编码器"), 2, 2)
        layout.addWidget(self.encoder_combo, 2, 3)
        layout.addWidget(QLabel("导出质量"), 3, 0)
        layout.addWidget(self.quality_combo, 3, 1, 1, 3)
        layout.addWidget(QLabel("配乐音量"), 4, 0)
        layout.addWidget(volume_widget, 4, 1)
        layout.addWidget(self.mirror_second_clip, 4, 2, 1, 2)
        layout.addWidget(self.subtitle_enabled, 5, 0)
        layout.addWidget(QLabel("字幕字体"), 5, 1)
        layout.addWidget(self.font_combo, 5, 2, 1, 2)
        layout.addWidget(QLabel("字幕字号"), 6, 0)
        layout.addWidget(self.font_size, 6, 1)
        layout.addWidget(QLabel("描边宽度"), 6, 2)
        layout.addWidget(self.outline_width, 6, 3)
        layout.addWidget(QLabel("底部边距"), 7, 0)
        layout.addWidget(self.subtitle_margin, 7, 1)
        layout.addWidget(self.primary_color_button, 7, 2)
        layout.addWidget(self.outline_color_button, 7, 3)
        self.quality_combo.currentIndexChanged.connect(self._update_estimate)
        self.subtitle_enabled.toggled.connect(self._update_subtitle_preview)
        self.font_combo.currentFontChanged.connect(self._update_subtitle_preview)
        self.font_size.valueChanged.connect(self._update_subtitle_preview)
        self.outline_width.valueChanged.connect(self._update_subtitle_preview)
        return group

    def _build_advanced_group(self) -> QGroupBox:
        group = QGroupBox("高级剪辑设置")
        outer = QVBoxLayout(group)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        outer.addWidget(tabs)

        visual = QWidget()
        visual_layout = QGridLayout(visual)
        self.canvas_mode_combo = QComboBox()
        self.canvas_mode_combo.addItem("模糊背景＋完整前景", CanvasMode.BLUR.value)
        self.canvas_mode_combo.addItem("放大填满并裁切", CanvasMode.CROP.value)
        self.canvas_mode_combo.addItem("纯色背景＋完整前景", CanvasMode.SOLID.value)
        self.canvas_position_combo = QComboBox()
        for text, value in (
            ("居中", CanvasPosition.CENTER.value), ("靠左", CanvasPosition.LEFT.value),
            ("靠右", CanvasPosition.RIGHT.value), ("靠上", CanvasPosition.TOP.value),
            ("靠下", CanvasPosition.BOTTOM.value), ("自定义/预览拖动", CanvasPosition.CUSTOM.value),
        ):
            self.canvas_position_combo.addItem(text, value)
        self.canvas_x = QSpinBox()
        self.canvas_x.setRange(0, 100)
        self.canvas_x.setSuffix("%")
        self.canvas_y = QSpinBox()
        self.canvas_y.setRange(0, 100)
        self.canvas_y.setSuffix("%")
        self.canvas_color_button = QPushButton(self._profile_settings.canvas_color)
        self.canvas_color_button.clicked.connect(self._choose_canvas_color)
        self.sharpen = QDoubleSpinBox()
        self.sharpen.setRange(0, 2)
        self.sharpen.setSingleStep(0.05)
        self.sharpen.setDecimals(2)
        self.denoise = QDoubleSpinBox()
        self.denoise.setRange(0, 20)
        self.denoise.setSingleStep(0.5)
        self.brightness = QSpinBox()
        self.brightness.setRange(-100, 100)
        self.brightness.setSuffix("%")
        self.contrast = QSpinBox()
        self.contrast.setRange(50, 200)
        self.contrast.setSuffix("%")
        self.saturation = QSpinBox()
        self.saturation.setRange(0, 300)
        self.saturation.setSuffix("%")
        self.shadow_boost = QSpinBox()
        self.shadow_boost.setRange(0, 100)
        self.shadow_boost.setSuffix("%")
        self.highlight_protection = QSpinBox()
        self.highlight_protection.setRange(0, 100)
        self.highlight_protection.setSuffix("%")
        visual_layout.addWidget(QLabel("画布方式"), 0, 0)
        visual_layout.addWidget(self.canvas_mode_combo, 0, 1)
        visual_layout.addWidget(QLabel("前景/裁切位置"), 0, 2)
        visual_layout.addWidget(self.canvas_position_combo, 0, 3)
        visual_layout.addWidget(QLabel("自定义 X"), 1, 0)
        visual_layout.addWidget(self.canvas_x, 1, 1)
        visual_layout.addWidget(QLabel("自定义 Y"), 1, 2)
        visual_layout.addWidget(self.canvas_y, 1, 3)
        visual_layout.addWidget(QLabel("纯色背景"), 2, 0)
        visual_layout.addWidget(self.canvas_color_button, 2, 1)
        visual_layout.addWidget(QLabel("锐化"), 2, 2)
        visual_layout.addWidget(self.sharpen, 2, 3)
        visual_layout.addWidget(QLabel("降噪"), 3, 0)
        visual_layout.addWidget(self.denoise, 3, 1)
        visual_layout.addWidget(QLabel("亮度"), 3, 2)
        visual_layout.addWidget(self.brightness, 3, 3)
        visual_layout.addWidget(QLabel("对比度"), 4, 0)
        visual_layout.addWidget(self.contrast, 4, 1)
        visual_layout.addWidget(QLabel("饱和度"), 4, 2)
        visual_layout.addWidget(self.saturation, 4, 3)
        visual_layout.addWidget(QLabel("暗部提升"), 5, 0)
        visual_layout.addWidget(self.shadow_boost, 5, 1)
        visual_layout.addWidget(QLabel("高光保护"), 5, 2)
        visual_layout.addWidget(self.highlight_protection, 5, 3)
        tabs.addTab(visual, "画面增强")

        timeline = QWidget()
        timeline_layout = QGridLayout(timeline)
        self.transition_type_combo = QComboBox()
        for text, value in (
            ("无转场（硬切）", TransitionType.NONE.value), ("交叉淡化", TransitionType.FADE.value),
            ("向左推拉", TransitionType.SLIDE_LEFT.value), ("向左擦除", TransitionType.WIPE_LEFT.value),
            ("缩放转场", TransitionType.ZOOM_IN.value),
        ):
            self.transition_type_combo.addItem(text, value)
        self.transition_seconds = QDoubleSpinBox()
        self.transition_seconds.setRange(0, 5)
        self.transition_seconds.setDecimals(2)
        self.transition_seconds.setSingleStep(0.1)
        self.transition_seconds.setSuffix(" 秒")
        self.clip_max_duration = QDoubleSpinBox()
        self.clip_max_duration.setRange(0, 3600)
        self.clip_max_duration.setDecimals(2)
        self.clip_max_duration.setSuffix(" 秒（0=不限）")
        self.trim_black = QCheckBox("自动检测并裁掉片尾黑帧（会增加一次检测读取）")
        self.cover_frames = QSpinBox()
        self.cover_frames.setRange(0, 1800)
        self.cover_frames.setSuffix(" 帧")
        self.cover_fadein = QDoubleSpinBox()
        self.cover_fadein.setRange(0, 10)
        self.cover_fadein.setDecimals(2)
        self.cover_fadein.setSuffix(" 秒")
        self.cover_zoom = QSpinBox()
        self.cover_zoom.setRange(100, 160)
        self.cover_zoom.setSuffix("%")
        self.cover_title = QLineEdit()
        self.cover_title.setPlaceholderText("可空；显示在封面中央")
        self.export_cover = QCheckBox("同时导出独立 cover.jpg")
        timeline_layout.addWidget(QLabel("转场类型"), 0, 0)
        timeline_layout.addWidget(self.transition_type_combo, 0, 1)
        timeline_layout.addWidget(QLabel("转场时长"), 0, 2)
        timeline_layout.addWidget(self.transition_seconds, 0, 3)
        timeline_layout.addWidget(QLabel("每段最长"), 1, 0)
        timeline_layout.addWidget(self.clip_max_duration, 1, 1)
        timeline_layout.addWidget(self.trim_black, 1, 2, 1, 2)
        timeline_layout.addWidget(QLabel("封面时长"), 2, 0)
        timeline_layout.addWidget(self.cover_frames, 2, 1)
        timeline_layout.addWidget(QLabel("封面淡入"), 2, 2)
        timeline_layout.addWidget(self.cover_fadein, 2, 3)
        timeline_layout.addWidget(QLabel("封面末帧缩放"), 3, 0)
        timeline_layout.addWidget(self.cover_zoom, 3, 1)
        timeline_layout.addWidget(self.export_cover, 3, 2, 1, 2)
        timeline_layout.addWidget(QLabel("封面标题"), 4, 0)
        timeline_layout.addWidget(self.cover_title, 4, 1, 1, 3)
        tabs.addTab(timeline, "转场/裁剪/封面")

        overlay = QWidget()
        overlay_layout = QGridLayout(overlay)
        self.logo_motion_combo = QComboBox()
        for text, value in (
            ("右上→左下", LogoMotion.TOP_RIGHT_TO_BOTTOM_LEFT.value),
            ("左上→右下", LogoMotion.TOP_LEFT_TO_BOTTOM_RIGHT.value),
            ("左下→右上", LogoMotion.BOTTOM_LEFT_TO_TOP_RIGHT.value),
            ("固定右上", LogoMotion.FIXED_TOP_RIGHT.value), ("固定左上", LogoMotion.FIXED_TOP_LEFT.value),
            ("固定右下", LogoMotion.FIXED_BOTTOM_RIGHT.value), ("固定左下", LogoMotion.FIXED_BOTTOM_LEFT.value),
            ("自定义起止位置", LogoMotion.CUSTOM.value),
        ):
            self.logo_motion_combo.addItem(text, value)
        self.logo_start_frame = QSpinBox()
        self.logo_start_frame.setRange(1, 1_000_000)
        self.logo_end_frame = QSpinBox()
        self.logo_end_frame.setRange(0, 1_000_000)
        self.logo_end_frame.setSpecialValueText("直到结尾")
        self.logo_fade = QDoubleSpinBox()
        self.logo_fade.setRange(0, 10)
        self.logo_fade.setDecimals(2)
        self.logo_fade.setSuffix(" 秒")
        self.logo_start_x = QSpinBox(); self.logo_start_x.setRange(0, 100); self.logo_start_x.setSuffix("%")
        self.logo_start_y = QSpinBox(); self.logo_start_y.setRange(0, 100); self.logo_start_y.setSuffix("%")
        self.logo_end_x = QSpinBox(); self.logo_end_x.setRange(0, 100); self.logo_end_x.setSuffix("%")
        self.logo_end_y = QSpinBox(); self.logo_end_y.setRange(0, 100); self.logo_end_y.setSuffix("%")
        self.subtitle_preset_combo = QComboBox()
        self.subtitle_preset_combo.addItems(["简洁白字", "黄色黑边", "半透明底板"])
        subtitle_apply = QPushButton("应用字幕样式")
        subtitle_apply.clicked.connect(self._apply_subtitle_preset)
        self.subtitle_shadow = QSpinBox(); self.subtitle_shadow.setRange(0, 12)
        self.subtitle_background = QSpinBox(); self.subtitle_background.setRange(0, 100); self.subtitle_background.setSuffix("%")
        self.subtitle_max_chars = QSpinBox(); self.subtitle_max_chars.setRange(4, 60)
        self.subtitle_horizontal_margin = QSpinBox(); self.subtitle_horizontal_margin.setRange(0, 400)
        self.highlight_words = QLineEdit(); self.highlight_words.setPlaceholderText("关键词用逗号分隔")
        self.highlight_color_button = QPushButton(self._highlight_color)
        self.highlight_color_button.clicked.connect(self._choose_highlight_color)
        self.subtitle_sample = QLabel("字幕预览：透明泳池更要重视安全冗余")
        self.subtitle_sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_sample.setMinimumHeight(70)
        overlay_layout.addWidget(QLabel("Logo轨迹"), 0, 0); overlay_layout.addWidget(self.logo_motion_combo, 0, 1)
        overlay_layout.addWidget(QLabel("开始帧"), 0, 2); overlay_layout.addWidget(self.logo_start_frame, 0, 3)
        overlay_layout.addWidget(QLabel("结束帧"), 1, 0); overlay_layout.addWidget(self.logo_end_frame, 1, 1)
        overlay_layout.addWidget(QLabel("淡入淡出"), 1, 2); overlay_layout.addWidget(self.logo_fade, 1, 3)
        overlay_layout.addWidget(QLabel("起点 X/Y"), 2, 0); overlay_layout.addWidget(self.logo_start_x, 2, 1); overlay_layout.addWidget(self.logo_start_y, 2, 2)
        overlay_layout.addWidget(QLabel("终点 X/Y"), 3, 0); overlay_layout.addWidget(self.logo_end_x, 3, 1); overlay_layout.addWidget(self.logo_end_y, 3, 2)
        overlay_layout.addWidget(QLabel("字幕预设"), 4, 0); overlay_layout.addWidget(self.subtitle_preset_combo, 4, 1); overlay_layout.addWidget(subtitle_apply, 4, 2)
        overlay_layout.addWidget(QLabel("字幕阴影"), 5, 0); overlay_layout.addWidget(self.subtitle_shadow, 5, 1)
        overlay_layout.addWidget(QLabel("底板透明度"), 5, 2); overlay_layout.addWidget(self.subtitle_background, 5, 3)
        overlay_layout.addWidget(QLabel("每行最多字符"), 6, 0); overlay_layout.addWidget(self.subtitle_max_chars, 6, 1)
        overlay_layout.addWidget(QLabel("左右安全边距"), 6, 2); overlay_layout.addWidget(self.subtitle_horizontal_margin, 6, 3)
        overlay_layout.addWidget(QLabel("高亮关键词"), 7, 0); overlay_layout.addWidget(self.highlight_words, 7, 1, 1, 2); overlay_layout.addWidget(self.highlight_color_button, 7, 3)
        overlay_layout.addWidget(self.subtitle_sample, 8, 0, 1, 4)
        tabs.addTab(overlay, "Logo/字幕")

        audio = QWidget()
        audio_layout = QGridLayout(audio)
        self.normalize_audio = QCheckBox("响度标准化，减少忽大忽小")
        self.loudness_target = QDoubleSpinBox()
        self.loudness_target.setRange(-24, -8)
        self.loudness_target.setDecimals(1)
        self.loudness_target.setSuffix(" LUFS")
        self.duck_music = QCheckBox("有原声时自动压低 BGM")
        self.music_fadein = QDoubleSpinBox(); self.music_fadein.setRange(0, 10); self.music_fadein.setDecimals(2); self.music_fadein.setSuffix(" 秒")
        self.music_fadeout = QDoubleSpinBox(); self.music_fadeout.setRange(0, 10); self.music_fadeout.setDecimals(2); self.music_fadeout.setSuffix(" 秒")
        audio_layout.addWidget(self.normalize_audio, 0, 0, 1, 2)
        audio_layout.addWidget(QLabel("目标响度"), 0, 2); audio_layout.addWidget(self.loudness_target, 0, 3)
        audio_layout.addWidget(self.duck_music, 1, 0, 1, 2)
        audio_layout.addWidget(QLabel("配乐淡入"), 1, 2); audio_layout.addWidget(self.music_fadein, 1, 3)
        audio_layout.addWidget(QLabel("配乐淡出"), 2, 2); audio_layout.addWidget(self.music_fadeout, 2, 3)
        tabs.addTab(audio, "音频")

        self._apply_settings_to_controls(self._profile_settings)
        for control in (
            self.transition_seconds, self.cover_frames, self.clip_max_duration,
            self.canvas_x, self.canvas_y, self.sharpen, self.denoise,
        ):
            control.valueChanged.connect(self._update_estimate)
        for control in (
            self.subtitle_shadow, self.subtitle_background, self.subtitle_max_chars,
            self.subtitle_horizontal_margin,
        ):
            control.valueChanged.connect(self._update_subtitle_preview)
        self.highlight_words.textChanged.connect(self._update_subtitle_preview)
        self._update_subtitle_preview()
        return group

    def _build_preview_group(self) -> QGroupBox:
        group = QGroupBox("画面位置与效果预览（手动模式）")
        layout = QHBoxLayout(group)
        self.preview_label = PositionPreviewLabel()
        self.preview_label.position_changed.connect(self._on_preview_position_changed)
        side = QVBoxLayout()
        preview_button = QPushButton("生成当前选中视频预览")
        preview_button.clicked.connect(self.generate_preview)
        self.preview_status = QLabel("预览只生成一张静帧，不会编码完整视频。")
        self.preview_status.setObjectName("mutedText")
        self.preview_status.setWordWrap(True)
        side.addWidget(preview_button)
        side.addWidget(self.preview_status)
        side.addStretch(1)
        layout.addWidget(self.preview_label)
        layout.addLayout(side, 1)
        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("输出")
        layout = QGridLayout(group)
        self.output_dir_edit = QLineEdit(self._settings.output_dir)
        browse = QPushButton("选择目录…")
        browse.clicked.connect(self._choose_output_dir)
        self.output_name_label = QLabel("文件名")
        self.filename_edit = QLineEdit(self._manual_filename)
        self.estimate_label = QLabel("预计总时长：请添加视频（最终以 FFprobe 实测为准）")
        self.estimate_label.setObjectName("infoPanel")
        self.estimate_label.setWordWrap(True)
        layout.addWidget(QLabel("输出目录"), 0, 0)
        layout.addWidget(self.output_dir_edit, 0, 1)
        layout.addWidget(browse, 0, 2)
        layout.addWidget(self.output_name_label, 1, 0)
        layout.addWidget(self.filename_edit, 1, 1, 1, 2)
        layout.addWidget(self.estimate_label, 2, 0, 1, 3)
        return group

    def _build_run_group(self) -> QGroupBox:
        group = QGroupBox()
        group.setObjectName("actionPanel")
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        buttons = QHBoxLayout()
        task_heading = QLabel("任务控制")
        task_heading.setObjectName("sectionTitle")
        self.start_button = QPushButton("开始剪辑")
        self.start_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setObjectName("dangerButton")
        self.open_button = QPushButton("打开输出文件夹")
        self.download_log_button = QPushButton("下载日志…")
        self.toggle_log_button = QPushButton("隐藏日志")
        self.retry_button = QPushButton("仅重试失败任务")
        self.cancel_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.download_log_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_render)
        self.cancel_button.clicked.connect(self.cancel_render)
        self.open_button.clicked.connect(self.open_output_folder)
        self.download_log_button.clicked.connect(self.download_logs)
        self.toggle_log_button.clicked.connect(self._toggle_log_view)
        self.retry_button.clicked.connect(self.retry_failed_tasks)
        buttons.addWidget(task_heading)
        buttons.addSpacing(6)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.download_log_button)
        buttons.addWidget(self.toggle_log_button)
        buttons.addWidget(self.retry_button)
        buttons.addStretch(1)
        self.stage_label = QLabel("就绪")
        self.stage_label.setObjectName("stageLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        # Keep the whole current run so “下载日志” never exports a truncated view.
        self.log_view.setMaximumBlockCount(0)
        self.log_view.setFixedHeight(92)
        layout.addLayout(buttons)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view)
        return group

    def _toggle_log_view(self) -> None:
        visible = not self.log_view.isVisible()
        self.log_view.setVisible(visible)
        self.toggle_log_button.setText("隐藏日志" if visible else "显示日志")

    def _on_mode_changed(self, *_args: object) -> None:
        if not hasattr(self, "batch_group"):
            return
        mode = str(self.mode_combo.currentData())
        if self._active_mode == "batch":
            self._batch_prefix = self.filename_edit.text()
            self._batch_template = self.output_template_edit.text()
        elif self._active_mode == "manual":
            self._manual_filename = self.filename_edit.text()
        batch = mode == "batch"
        self.batch_group.setVisible(batch)
        self.video_group.setVisible(not batch)
        for widget in self.manual_asset_widgets:
            widget.setVisible(not batch)
        self.optional_group.setTitle("批量任务统一 Logo" if batch else "封面、Logo、字幕与配乐")
        if hasattr(self, "preview_group"):
            self.preview_group.setVisible(not batch)
        if hasattr(self, "nav_list"):
            preview_item = self.nav_list.item(2)
            preview_item.setHidden(batch)
            compact_preview = self.compact_navigation.model().item(2)
            if compact_preview is not None:
                compact_preview.setEnabled(not batch)
            if batch and self.nav_list.currentRow() == 2:
                self.nav_list.setCurrentRow(0)
        self.output_name_label.setText("文件名前缀" if batch else "文件名")
        self.filename_edit.setText(self._batch_prefix if batch else self._manual_filename)
        self.start_button.setText("开始批量剪辑" if batch else "开始剪辑")
        if batch:
            self.estimate_label.setText(
                "批量输出使用命名模板；可用 {prefix}、{folder}、{index}、{date}。"
            )
        else:
            self._update_estimate()
        self._active_mode = mode

    def _choose_batch_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择批量素材总目录", self.batch_root_edit.text())
        if path:
            self.batch_root_edit.setText(path)
            self.preview_batch()
            if self.watch_checkbox.isChecked():
                self._on_watch_toggled(True)

    def preview_batch(self) -> None:
        root_text = self.batch_root_edit.text().strip()
        if not root_text:
            self.batch_status.setText("请选择包含多个素材子文件夹的总目录。")
            return
        root = Path(root_text).expanduser()
        output = Path(self.output_dir_edit.text()).expanduser() if self.output_dir_edit.text() else None
        scan = scan_batch_root(
            root,
            excluded_dir=output,
            sort_mode=VideoSortMode(self.sort_mode_combo.currentData()),
            first_pattern=self.first_pattern_edit.text().strip(),
            last_pattern=self.last_pattern_edit.text().strip(),
        )
        message = f"可处理 {len(scan.sources)} 个子文件夹；不合格 {len(scan.issues)} 个。"
        if scan.sources:
            first = scan.sources[0]
            try:
                example = batch_output_filename(
                    self.filename_edit.text(), 1, folder_name=first.source_dir.name,
                    template=self.output_template_edit.text(),
                )
                message += f" 示例输出：{example}。"
            except ValueError as exc:
                message += f" 命名模板错误：{exc}。"
        if scan.issues:
            details = "\n".join(f"- {issue.source_dir.name}：{issue.message}" for issue in scan.issues[:5])
            if len(scan.issues) > 5:
                details += f"\n- 另有 {len(scan.issues) - 5} 个问题，请运行后查看完整日志。"
            message += "\n" + details
        self.batch_status.setText(message)

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
        self._update_subtitle_preview()

    def _choose_canvas_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.canvas_color_button.text()), self, "选择画布背景色")
        if color.isValid():
            self.canvas_color_button.setText(color.name().upper())

    def _choose_highlight_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._highlight_color), self, "选择关键词颜色")
        if color.isValid():
            self._highlight_color = color.name().upper()
            self.highlight_color_button.setText(self._highlight_color)
            self._update_subtitle_preview()

    def _refresh_preset_combo(self) -> None:
        current = self.preset_combo.currentText() if hasattr(self, "preset_combo") else ""
        self.preset_combo.clear()
        for name in BUILTIN_PRESETS:
            self.preset_combo.addItem(name, ("builtin", name))
        for name in sorted(self._custom_presets, key=str.casefold):
            self.preset_combo.addItem(f"自定义：{name}", ("custom", name))
        if current:
            index = self.preset_combo.findText(current)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

    def _apply_selected_preset(self) -> None:
        data = self.preset_combo.currentData()
        if not data:
            return
        kind, name = data
        mapping = BUILTIN_PRESETS[name] if kind == "builtin" else self._custom_presets[name]
        settings = render_settings_from_mapping(mapping, RenderSettings())
        self._apply_settings_to_controls(settings)
        self._append_log(f"已应用参数预设：{name}")

    def _save_custom_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "保存参数预设", "预设名称")
        name = name.strip()
        if not accepted or not name:
            return
        self._custom_presets[name[:80]] = render_settings_to_mapping(self._render_settings())
        try:
            self._preset_store.save_custom(self._custom_presets)
        except OSError as exc:
            QMessageBox.critical(self, "预设保存失败", str(exc))
            return
        self._refresh_preset_combo()
        self.preset_combo.setCurrentIndex(self.preset_combo.count() - 1)

    def _delete_custom_preset(self) -> None:
        data = self.preset_combo.currentData()
        if not data or data[0] != "custom":
            QMessageBox.information(self, "不能删除", "内置预设不能删除。")
            return
        self._custom_presets.pop(data[1], None)
        self._preset_store.save_custom(self._custom_presets)
        self._refresh_preset_combo()

    def _apply_subtitle_preset(self) -> None:
        name = self.subtitle_preset_combo.currentText()
        if name == "黄色黑边":
            self._primary_color, self._outline_color = "#FFD400", "#000000"
            self.outline_width.setValue(6)
            self.subtitle_background.setValue(0)
        elif name == "半透明底板":
            self._primary_color, self._outline_color = "#FFFFFF", "#000000"
            self.outline_width.setValue(2)
            self.subtitle_background.setValue(55)
        else:
            self._primary_color, self._outline_color = "#FFFFFF", "#000000"
            self.outline_width.setValue(5)
            self.subtitle_background.setValue(0)
        self.primary_color_button.setText(f"文字 {self._primary_color}")
        self.outline_color_button.setText(f"描边 {self._outline_color}")
        self._update_subtitle_preview()

    def _update_subtitle_preview(self, *_args: object) -> None:
        if not hasattr(self, "subtitle_sample"):
            return
        background = max(0, min(100, self.subtitle_background.value()))
        alpha = round(background * 2.55)
        style = (
            f"font-family: '{self.font_combo.currentFont().family()}';"
            f"font-size: {max(14, self.font_size.value() // 3)}px;"
            f"color: {self._primary_color};"
            f"background-color: rgba(0,0,0,{alpha});"
            f"padding: 8px; border-radius: 4px;"
        )
        self.subtitle_sample.setStyleSheet(style)
        words = [part.strip() for part in self.highlight_words.text().replace("，", ",").split(",") if part.strip()]
        sample = "字幕预览：透明泳池更要重视安全冗余"
        if words:
            sample += f"（关键词：{'、'.join(words[:3])}，成片中显示为 {self._highlight_color}）"
        self.subtitle_sample.setText(sample)

    def _apply_settings_to_controls(self, settings: RenderSettings) -> None:
        if not hasattr(self, "canvas_mode_combo"):
            return
        self._select_combo(self.interpolation_combo, settings.interpolation_mode.value)
        self._select_combo(self.source_audio_combo, settings.source_audio_mode.value)
        self._select_combo(self.music_policy_combo, settings.music_short_policy.value)
        self._select_combo(self.encoder_combo, settings.video_encoder.value)
        self._select_combo(self.quality_combo, settings.output_quality.value)
        self.volume_slider.setValue(round(settings.music_volume * 100))
        self.mirror_second_clip.setChecked(settings.mirror_second_clip)
        self.subtitle_enabled.setChecked(settings.subtitle_enabled)
        self.font_combo.setCurrentFont(QFont(settings.subtitle_style.font_name))
        self.font_size.setValue(settings.subtitle_style.font_size)
        self.outline_width.setValue(settings.subtitle_style.outline_width)
        self.subtitle_margin.setValue(settings.subtitle_style.margin_bottom)
        self._primary_color = settings.subtitle_style.primary_color
        self._outline_color = settings.subtitle_style.outline_color
        self._highlight_color = settings.subtitle_style.highlight_color
        self.primary_color_button.setText(f"文字 {self._primary_color}")
        self.outline_color_button.setText(f"描边 {self._outline_color}")
        self._select_combo(self.canvas_mode_combo, settings.canvas_mode.value)
        self._select_combo(self.canvas_position_combo, settings.canvas_position.value)
        self.canvas_x.setValue(settings.canvas_x_percent)
        self.canvas_y.setValue(settings.canvas_y_percent)
        self.canvas_color_button.setText(settings.canvas_color)
        self.sharpen.setValue(settings.sharpen_amount)
        self.denoise.setValue(settings.denoise_strength)
        self.brightness.setValue(round(settings.brightness * 100))
        self.contrast.setValue(round(settings.contrast * 100))
        self.saturation.setValue(round(settings.saturation * 100))
        self.shadow_boost.setValue(round(settings.shadow_boost * 100))
        self.highlight_protection.setValue(round(settings.highlight_protection * 100))
        self._select_combo(self.transition_type_combo, settings.transition_type.value)
        self.transition_seconds.setValue(settings.transition_frames / settings.fps)
        self.clip_max_duration.setValue(settings.clip_max_duration_seconds)
        self.trim_black.setChecked(settings.trim_trailing_black)
        self.cover_frames.setValue(settings.cover_frames)
        self.cover_fadein.setValue(settings.cover_fadein_seconds)
        self.cover_zoom.setValue(settings.cover_zoom_percent)
        self.cover_title.setText(settings.cover_title)
        self.export_cover.setChecked(settings.export_cover_image)
        self._select_combo(self.logo_motion_combo, settings.logo_motion.value)
        self.logo_start_frame.setValue(settings.logo_start_frame)
        self.logo_end_frame.setValue(settings.logo_end_frame)
        self.logo_fade.setValue(settings.logo_fade_seconds)
        self.logo_start_x.setValue(settings.logo_start_x_percent)
        self.logo_start_y.setValue(settings.logo_start_y_percent)
        self.logo_end_x.setValue(settings.logo_end_x_percent)
        self.logo_end_y.setValue(settings.logo_end_y_percent)
        self.subtitle_shadow.setValue(settings.subtitle_style.shadow_depth)
        self.subtitle_background.setValue(settings.subtitle_style.background_opacity_percent)
        self.subtitle_max_chars.setValue(settings.subtitle_style.max_chars_per_line)
        self.subtitle_horizontal_margin.setValue(settings.subtitle_style.margin_horizontal)
        self.highlight_words.setText("，".join(settings.subtitle_style.highlight_words))
        self.highlight_color_button.setText(self._highlight_color)
        self.normalize_audio.setChecked(settings.normalize_audio)
        self.loudness_target.setValue(settings.loudness_target_lufs)
        self.duck_music.setChecked(settings.duck_music_under_source)
        self.music_fadein.setValue(settings.music_fadein_seconds)
        self.music_fadeout.setValue(settings.music_fadeout_seconds)
        self._update_subtitle_preview()
        self._update_estimate()

    def _load_selected_trim(self) -> None:
        item = self.video_list.current_video()
        if item is None:
            return
        self.trim_start.setValue(item.trim_start_seconds)
        self.trim_end.setValue(item.trim_end_seconds)

    def _apply_selected_trim(self) -> None:
        if self.trim_end.value() > 0 and self.trim_end.value() <= self.trim_start.value():
            QMessageBox.warning(self, "裁剪时间无效", "结束时间必须晚于开始时间，或设为0表示素材结尾。")
            return
        self.video_list.set_selected_trim(self.trim_start.value(), self.trim_end.value())

    def _reset_selected_trim(self) -> None:
        self.trim_start.setValue(0)
        self.trim_end.setValue(0)
        self.video_list.set_selected_trim(0, 0)

    def generate_preview(self) -> None:
        if not self._capabilities:
            QMessageBox.warning(self, "无法预览", "请先完成 FFmpeg 检测。")
            return
        item = self.video_list.current_video()
        if item is None:
            items = self.video_list.video_items()
            item = items[0] if items else None
        if item is None or item.probe is None:
            QMessageBox.information(self, "无法预览", "请先添加并选择一个视频。")
            return
        if self._preview_process and self._preview_process.state() != QProcess.ProcessState.NotRunning:
            self._preview_process.kill()
        settings = replace(self._render_settings(), interpolation_mode=InterpolationMode.FAST)
        try:
            start, end = effective_clip_range(item, item.probe, settings)
        except ValueError as exc:
            QMessageBox.warning(self, "无法预览", str(exc))
            return
        graph = build_normalization_filter(
            item.probe,
            settings,
            clip_start_seconds=start,
            clip_end_seconds=end,
        )
        graph += f",{build_enhancement_filter(settings)}"
        self._preview_path.parent.mkdir(parents=True, exist_ok=True)
        self._preview_path.unlink(missing_ok=True)
        process = QProcess(self)
        process.setProgram(str(self._capabilities.ffmpeg_path))
        process.setArguments([
            "-hide_banner", "-y", "-i", str(item.source_path), "-vf", graph,
            "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2", "-update", "1", "-loglevel", "error",
            str(self._preview_path),
        ])
        process.finished.connect(self._preview_finished)
        process.errorOccurred.connect(lambda _error: self.preview_status.setText("预览进程启动失败。"))
        self._preview_process = process
        self.preview_status.setText("正在生成预览…")
        process.start()

    def _preview_finished(self, exit_code: int, _status: object) -> None:
        if exit_code == 0 and self._preview_path.is_file():
            pixmap = QPixmap(str(self._preview_path))
            self.preview_label.setPixmap(
                pixmap.scaled(
                    self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.preview_status.setText("预览已更新；拖动画面可设置自定义位置，再次点击即可刷新。")
        else:
            detail = ""
            if self._preview_process:
                detail = bytes(self._preview_process.readAllStandardError()).decode("utf-8", "replace")[-500:]
            self.preview_status.setText(f"预览生成失败：{detail or '请查看 FFmpeg 配置'}")

    def _on_preview_position_changed(self, x: int, y: int) -> None:
        self._select_combo(self.canvas_position_combo, CanvasPosition.CUSTOM.value)
        self.canvas_x.setValue(x)
        self.canvas_y.setValue(y)
        self.preview_status.setText(f"自定义位置：X={x}%、Y={y}%；点击“生成预览”刷新。")

    def _on_watch_toggled(self, checked: bool) -> None:
        if not hasattr(self, "_watch_timer"):
            return
        self._watch_timer.stop()
        if not checked:
            return
        root_text = self.batch_root_edit.text().strip()
        if not root_text:
            return
        root = Path(root_text).expanduser()
        output = Path(self.output_dir_edit.text()).expanduser() if self.output_dir_edit.text() else None
        if root.is_dir():
            try:
                self._watch_tracker.arm(root, excluded=output)
            except OSError as exc:
                self._append_log(f"监控文件夹初始化失败：{exc}")
        self._watch_timer.start(self.watch_interval.value() * 1000)

    def _restart_watch_timer(self, *_args: object) -> None:
        if hasattr(self, "_watch_timer") and self.watch_checkbox.isChecked():
            self._watch_timer.start(self.watch_interval.value() * 1000)

    def _poll_watch_folder(self) -> None:
        if self._thread is not None or not self.watch_checkbox.isChecked():
            return
        root_text = self.batch_root_edit.text().strip()
        if not root_text:
            return
        root = Path(root_text).expanduser()
        output = Path(self.output_dir_edit.text()).expanduser() if self.output_dir_edit.text() else None
        try:
            ready = self._watch_tracker.poll(root, excluded=output)
        except OSError as exc:
            self._append_log(f"监控文件夹读取失败：{exc}")
            return
        if ready:
            self._append_log("监控发现稳定的新素材目录：" + "、".join(path.name for path in ready))
            started = self._start_batch_render(only_dirs=set(ready), watch_trigger=True)
            if started:
                processed = tuple(task.source_dir for task in self._current_batch_tasks)
                self._watch_tracker.mark_processed(processed)

    def _update_estimate(self) -> None:
        if hasattr(self, "mode_combo") and self.mode_combo.currentData() == "batch":
            return
        items = self.video_list.video_items()
        if not items or any(item.probe is None for item in items):
            self.estimate_label.setText("预计总时长：请添加视频（最终以 FFprobe 实测为准）")
            return
        try:
            settings = self._render_settings() if hasattr(self, "canvas_mode_combo") else RenderSettings()
            estimate = estimate_export(
                items,
                settings,
                has_cover=bool(self.cover_edit.text()) and settings.cover_frames > 0,
                output_dir=Path(self.output_dir_edit.text()).expanduser() if self.output_dir_edit.text() else None,
                has_audio=bool(self.music_edit.text()) or settings.source_audio_mode == SourceAudioMode.MIX,
            )
            size_label = "目标" if estimate.size_is_targeted else "内容相关估计"
            free = (
                f"；可用磁盘 {estimate.available_free_bytes / 1024**3:.2f} GiB"
                if estimate.available_free_bytes is not None else ""
            )
            warnings = ""
            if estimate.warnings:
                warnings = "\n提示：" + "；".join(estimate.warnings[:3])
            self.estimate_label.setText(
                f"预计：{estimate.duration_seconds:.3f} 秒 / {estimate.total_frames} 帧；"
                f"文件约 {estimate.estimated_bytes / 1_000_000:.1f} MB（{size_label}）；"
                f"建议预留 {estimate.required_free_bytes / 1024**2:.0f} MiB{free}。"
                "最终以 FFprobe 实测为准。" + warnings
            )
        except ValueError as exc:
            self.estimate_label.setText(f"预计时间线无效：{exc}")

    def _render_settings(self) -> RenderSettings:
        transition_type = TransitionType(self.transition_type_combo.currentData())
        transition_frames = 0 if transition_type == TransitionType.NONE else max(
            1, round(self.transition_seconds.value() * 60)
        )
        words = tuple(
            part.strip()
            for part in self.highlight_words.text().replace("，", ",").split(",")
            if part.strip()
        )
        return RenderSettings(
            transition_frames=transition_frames,
            transition_type=transition_type,
            cover_frames=self.cover_frames.value(),
            cover_fadein_seconds=self.cover_fadein.value(),
            cover_zoom_percent=self.cover_zoom.value(),
            cover_title=self.cover_title.text().strip(),
            export_cover_image=self.export_cover.isChecked(),
            interpolation_mode=InterpolationMode(self.interpolation_combo.currentData()),
            source_audio_mode=SourceAudioMode(self.source_audio_combo.currentData()),
            music_short_policy=MusicShortPolicy(self.music_policy_combo.currentData()),
            music_volume=self.volume_slider.value() / 100,
            music_fadein_seconds=self.music_fadein.value(),
            music_fadeout_seconds=self.music_fadeout.value(),
            normalize_audio=self.normalize_audio.isChecked(),
            loudness_target_lufs=self.loudness_target.value(),
            duck_music_under_source=self.duck_music.isChecked(),
            video_encoder=VideoEncoder(self.encoder_combo.currentData()),
            output_quality=OutputQuality(self.quality_combo.currentData()),
            mirror_second_clip=self.mirror_second_clip.isChecked(),
            clip_max_duration_seconds=self.clip_max_duration.value(),
            trim_trailing_black=self.trim_black.isChecked(),
            canvas_mode=CanvasMode(self.canvas_mode_combo.currentData()),
            canvas_position=CanvasPosition(self.canvas_position_combo.currentData()),
            canvas_x_percent=self.canvas_x.value(),
            canvas_y_percent=self.canvas_y.value(),
            canvas_color=self.canvas_color_button.text(),
            sharpen_amount=self.sharpen.value(),
            denoise_strength=self.denoise.value(),
            brightness=self.brightness.value() / 100,
            contrast=self.contrast.value() / 100,
            saturation=self.saturation.value() / 100,
            shadow_boost=self.shadow_boost.value() / 100,
            highlight_protection=self.highlight_protection.value() / 100,
            logo_scale_percent=self.logo_scale.value(),
            logo_opacity_percent=self.logo_opacity.value(),
            logo_start_frame=self.logo_start_frame.value(),
            logo_end_frame=self.logo_end_frame.value(),
            logo_motion=LogoMotion(self.logo_motion_combo.currentData()),
            logo_start_x_percent=self.logo_start_x.value(),
            logo_start_y_percent=self.logo_start_y.value(),
            logo_end_x_percent=self.logo_end_x.value(),
            logo_end_y_percent=self.logo_end_y.value(),
            logo_fade_seconds=self.logo_fade.value(),
            subtitle_enabled=self.subtitle_enabled.isChecked(),
            subtitle_style=SubtitleStyle(
                font_name=self.font_combo.currentFont().family(),
                font_size=self.font_size.value(),
                primary_color=self._primary_color,
                outline_color=self._outline_color,
                outline_width=self.outline_width.value(),
                margin_bottom=self.subtitle_margin.value(),
                margin_horizontal=self.subtitle_horizontal_margin.value(),
                shadow_depth=self.subtitle_shadow.value(),
                background_opacity_percent=self.subtitle_background.value(),
                max_chars_per_line=self.subtitle_max_chars.value(),
                highlight_words=words,
                highlight_color=self._highlight_color,
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
        if self.mode_combo.currentData() == "batch":
            self._start_batch_render()
        else:
            self._start_manual_render()

    def _start_manual_render(self) -> None:
        assert self._capabilities is not None
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
        self._last_manual_job = job
        self._last_manual_failed = False
        self._last_retry_tasks = ()
        self.retry_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备开始")
        self.log_view.clear()
        self.download_log_button.setEnabled(False)
        self._last_result = None
        self._last_output_dir = job.output_dir
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

    def _start_batch_render(
        self,
        *,
        only_dirs: set[Path] | None = None,
        watch_trigger: bool = False,
    ) -> bool:
        assert self._capabilities is not None
        root_text = self.batch_root_edit.text().strip()
        output_text = self.output_dir_edit.text().strip()
        logo_text = self.logo_edit.text().strip()
        if not root_text:
            if not watch_trigger:
                QMessageBox.warning(self, "任务配置有误", "请选择批量素材总目录。")
            return False
        if not output_text:
            if not watch_trigger:
                QMessageBox.warning(self, "任务配置有误", "请选择输出目录。")
            return False
        if not logo_text or not Path(logo_text).is_file():
            if not watch_trigger:
                QMessageBox.warning(self, "任务配置有误", "请选择本批任务统一使用的 Logo 图片。")
            return False

        root = Path(root_text).expanduser()
        output_dir = Path(output_text).expanduser()
        prefix = self.filename_edit.text().strip()
        if not prefix:
            if not watch_trigger:
                QMessageBox.warning(self, "任务配置有误", "请输入输出文件名前缀。")
            return False
        scan = scan_batch_root(
            root,
            excluded_dir=output_dir,
            sort_mode=VideoSortMode(self.sort_mode_combo.currentData()),
            first_pattern=self.first_pattern_edit.text().strip(),
            last_pattern=self.last_pattern_edit.text().strip(),
        )
        if not watch_trigger:
            self.preview_batch()
        resolved_only = {path.resolve(strict=False) for path in only_dirs} if only_dirs else None
        initial_failures = [
            BatchFailure(issue.source_dir.name, issue.message)
            for issue in scan.issues
            if resolved_only is None or issue.source_dir.resolve(strict=False) in resolved_only
        ]
        settings = self._render_settings()
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        records_root = config_dir() / "batch_records" / batch_id
        tasks: list[BatchRenderTask] = []
        planned_targets: set[Path] = set()
        for index, source in enumerate(scan.sources, 1):
            if resolved_only is not None and source.source_dir.resolve(strict=False) not in resolved_only:
                continue
            folder_template = str(
                source.folder_config.get("output_template", self.output_template_edit.text())
                or self.output_template_edit.text()
            )
            explicit_name = str(source.folder_config.get("output_name", "") or "").strip()
            try:
                filename = (
                    sanitize_output_filename(explicit_name)
                    if explicit_name
                    else batch_output_filename(
                        prefix,
                        index,
                        folder_name=source.source_dir.name,
                        template=folder_template,
                    )
                )
            except ValueError as exc:
                initial_failures.append(BatchFailure(source.source_dir.name, str(exc)))
                continue
            target = output_dir / filename
            if target.exists():
                initial_failures.append(
                    BatchFailure(source.source_dir.name, f"输出文件已存在，为防止覆盖已跳过：{target}")
                )
                continue
            normalized_target = target.resolve(strict=False)
            if normalized_target in planned_targets:
                initial_failures.append(
                    BatchFailure(source.source_dir.name, f"批量任务中存在重复输出文件名，已跳过：{target}")
                )
                continue
            planned_targets.add(normalized_target)
            source_settings = settings_for_batch_source(settings, source)
            job = RenderJob(
                video_items=video_items_for_batch_source(source),
                cover_path=source.cover_path,
                subtitle_path=source.subtitle_path,
                music_path=source.music_path,
                output_dir=output_dir,
                output_filename=filename,
                settings=source_settings,
                logo_path=Path(logo_text),
                auxiliary_dir=records_root / f"{index:04d}",
            )
            # Batch probing belongs to the worker thread so a large folder does not
            # freeze the UI. Renderer performs the complete probe and validation.
            errors = [
                issue.message
                for issue in validate_render_job(job)
                if issue.severity == IssueSeverity.ERROR and issue.code != "video_unprobed"
            ]
            if errors:
                initial_failures.append(BatchFailure(source.source_dir.name, "；".join(errors)))
                continue
            tasks.append(BatchRenderTask(source.source_dir, job))

        if not tasks:
            details = "\n".join(
                f"{failure.source_name}：{failure.message}" for failure in initial_failures
            ) or "没有找到可处理的素材子文件夹。"
            self.log_view.clear()
            self.download_log_button.setEnabled(False)
            self._last_output_dir = output_dir
            self._append_log("批量扫描后没有可执行任务：")
            for failure in initial_failures:
                self._append_log(f"跳过：{failure.source_name}：{failure.message}")
            if not watch_trigger:
                QMessageBox.warning(self, "没有可执行任务", details)
            return False

        self.filename_edit.setText(prefix)
        self._batch_prefix = prefix
        self._batch_template = self.output_template_edit.text().strip()
        self._save_current_settings(settings)
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备批量处理")
        self.log_view.clear()
        self.download_log_button.setEnabled(False)
        self._last_result = None
        self._last_retry_tasks = ()
        self.retry_button.setEnabled(False)
        self._last_output_dir = output_dir
        self._set_running(True)
        self._append_log(
            f"批量扫描完成：可执行 {len(tasks)} 个，预先跳过 {len(initial_failures)} 个。"
        )
        for failure in initial_failures:
            self._append_log(f"跳过：{failure.source_name}：{failure.message}")

        thread = QThread(self)
        worker = BatchRenderWorker(
            tuple(tasks),
            tuple(initial_failures),
            self._capabilities,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._append_log)
        worker.completed.connect(self._on_batch_completed)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self._on_cancelled)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        self._current_batch_tasks = tuple(tasks)
        thread.start()
        return True

    def _save_current_settings(self, settings: RenderSettings) -> None:
        self._settings = replace(
            self._settings,
            output_dir=str(Path(self.output_dir_edit.text()).expanduser()),
            batch_input_dir=self.batch_root_edit.text().strip(),
            output_prefix=self._batch_prefix,
            output_template=self.output_template_edit.text().strip() or "{prefix}{index}.mp4",
            video_sort_mode=str(self.sort_mode_combo.currentData()),
            first_video_pattern=self.first_pattern_edit.text().strip(),
            last_video_pattern=self.last_pattern_edit.text().strip(),
            watch_enabled=self.watch_checkbox.isChecked(),
            watch_interval_seconds=self.watch_interval.value(),
            interpolation_mode=settings.interpolation_mode.value,
            source_audio_mode=settings.source_audio_mode.value,
            music_short_policy=settings.music_short_policy.value,
            music_volume=settings.music_volume,
            video_encoder=settings.video_encoder.value,
            output_quality=settings.output_quality.value,
            mirror_second_clip=settings.mirror_second_clip,
            subtitle_font_name=settings.subtitle_style.font_name,
            logo_scale_percent=settings.logo_scale_percent,
            logo_opacity_percent=settings.logo_opacity_percent,
            ffmpeg_path=self.ffmpeg_edit.text(),
            ffprobe_path=self.ffprobe_edit.text(),
            render_profile=render_settings_to_mapping(settings),
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
        self._last_output_dir = result.output_path.parent
        self.stage_label.setText(f"完成：{result.output_path.name}")
        self.progress_bar.setValue(100)
        self.open_button.setEnabled(True)
        self._last_manual_failed = False
        self.retry_button.setEnabled(False)
        QMessageBox.information(self, "剪辑完成", f"成片已核验并保存：\n{result.output_path}")

    def _on_batch_completed(self, summary: BatchRenderSummary) -> None:
        if summary.successes:
            self._last_result = summary.successes[-1]
            self.open_button.setEnabled(True)
        success_count = len(summary.successes)
        failure_count = len(summary.failures)
        self._last_retry_tasks = summary.retry_tasks
        self.retry_button.setEnabled(bool(summary.retry_tasks))
        self.stage_label.setText(f"批量完成：成功 {success_count}，失败/跳过 {failure_count}")
        self.progress_bar.setValue(100)
        self._append_log(f"===== 批量完成：成功 {success_count}，失败/跳过 {failure_count} =====")
        for failure in summary.failures:
            self._append_log(f"未生成：{failure.source_name}：{failure.message}")
        message = f"批量任务已结束。\n成功：{success_count}\n失败/跳过：{failure_count}"
        if failure_count:
            QMessageBox.warning(self, "批量剪辑完成", message + "\n可点击“下载日志”保存详情。")
        else:
            QMessageBox.information(self, "批量剪辑完成", message)

    def _on_failure(self, message: str) -> None:
        self.stage_label.setText("失败")
        self._append_log(message)
        if self._active_mode == "manual" and self._last_manual_job is not None:
            self._last_manual_failed = True
            self.retry_button.setEnabled(True)
        QMessageBox.critical(self, "剪辑失败", message)

    def retry_failed_tasks(self) -> None:
        if self._thread is not None or not self._capabilities:
            return
        if self._last_retry_tasks:
            tasks = self._last_retry_tasks
            self._last_retry_tasks = ()
            self.retry_button.setEnabled(False)
            self.progress_bar.setValue(0)
            self.stage_label.setText("准备重试失败任务")
            self._set_running(True)
            self._append_log(f"===== 用户主动重试 {len(tasks)} 个失败任务 =====")
            thread = QThread(self)
            worker = BatchRenderWorker(tasks, (), self._capabilities)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._on_progress)
            worker.log.connect(self._append_log)
            worker.completed.connect(self._on_batch_completed)
            worker.failed.connect(self._on_failure)
            worker.cancelled.connect(self._on_cancelled)
            worker.done.connect(thread.quit)
            worker.done.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._thread_finished)
            self._thread, self._worker = thread, worker
            self._current_batch_tasks = tasks
            thread.start()
            return
        if self._last_manual_failed and self._last_manual_job is not None:
            job = self._last_manual_job
            self._last_manual_failed = False
            self.retry_button.setEnabled(False)
            self.progress_bar.setValue(0)
            self.stage_label.setText("准备重试")
            self._set_running(True)
            self._append_log("===== 用户主动重试手动任务 =====")
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
            self._thread, self._worker = thread, worker
            thread.start()

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
        elif self._last_result or self._last_output_dir:
            self.open_button.setEnabled(True)

    def open_output_folder(self) -> None:
        output_dir = self._last_output_dir
        if output_dir is None and self._last_result:
            output_dir = self._last_result.output_path.parent
        if output_dir and output_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))

    def download_logs(self) -> None:
        content = self.log_view.toPlainText()
        if not content.strip():
            QMessageBox.information(self, "没有日志", "当前还没有可下载的日志。")
            return
        base = self._last_output_dir if self._last_output_dir and self._last_output_dir.is_dir() else Path.home()
        suggested = base / f"剪辑日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "下载日志", str(suggested), "文本文件 (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(content.rstrip() + "\n", encoding="utf-8-sig", newline="\n")
        except OSError as exc:
            QMessageBox.critical(self, "日志保存失败", str(exc))
            return
        QMessageBox.information(self, "日志已保存", f"完整日志已保存到：\n{path}")

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        self.download_log_button.setEnabled(True)

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is None:
            if hasattr(self, "_watch_timer"):
                self._watch_timer.stop()
            if self._preview_process and self._preview_process.state() != QProcess.ProcessState.NotRunning:
                self._preview_process.kill()
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
