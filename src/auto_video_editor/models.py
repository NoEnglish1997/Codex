from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from fractions import Fraction


class InterpolationMode(str, Enum):
    MOTION = "motion"
    FAST = "fast"


class SourceAudioMode(str, Enum):
    MUTE = "mute"
    MIX = "mix"


class MusicShortPolicy(str, Enum):
    LOOP = "loop"
    SILENCE = "silence"


class VideoEncoder(str, Enum):
    AUTO = "auto"
    NVENC = "nvenc"
    X264 = "x264"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ProbeInfo:
    path: Path
    duration_seconds: float
    width: int = 0
    height: int = 0
    display_width: int = 0
    display_height: int = 0
    avg_frame_rate: Fraction = Fraction(0, 1)
    real_frame_rate: Fraction = Fraction(0, 1)
    frame_count: int | None = None
    has_video: bool = False
    has_audio: bool = False
    audio_duration_seconds: float | None = None
    rotation: int = 0
    video_codec: str = ""
    audio_codec: str = ""
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    pixel_format: str = ""
    format_name: str = ""
    start_time_seconds: float = 0.0

    @property
    def is_vfr(self) -> bool:
        if not self.has_video or not self.real_frame_rate:
            return False
        return not self.avg_frame_rate or self.avg_frame_rate != self.real_frame_rate


@dataclass(frozen=True)
class VideoItem:
    source_path: Path
    display_name: str
    probe: ProbeInfo | None = None


@dataclass(frozen=True)
class SubtitleStyle:
    font_name: str = "Microsoft YaHei"
    font_size: int = 68
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 5
    margin_bottom: int = 180


@dataclass(frozen=True)
class RenderSettings:
    width: int = 1440
    height: int = 2560
    fps: int = 60
    transition_frames: int = 60
    cover_frames: int = 5
    interpolation_mode: InterpolationMode = InterpolationMode.MOTION
    source_audio_mode: SourceAudioMode = SourceAudioMode.MUTE
    music_short_policy: MusicShortPolicy = MusicShortPolicy.LOOP
    music_volume: float = 0.35
    music_fadeout_seconds: float = 1.0
    video_encoder: VideoEncoder = VideoEncoder.AUTO
    mirror_second_clip: bool = True
    subtitle_enabled: bool = True
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    logo_start_frame: int = 5
    logo_max_width: int = 240
    logo_max_height: int = 240
    logo_margin: int = 48


@dataclass(frozen=True)
class RenderJob:
    video_items: tuple[VideoItem, ...]
    cover_path: Path | None
    subtitle_path: Path | None
    music_path: Path | None
    output_dir: Path
    output_filename: str
    settings: RenderSettings = field(default_factory=RenderSettings)
    logo_path: Path | None = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR


@dataclass(frozen=True)
class TimelinePlan:
    frame_counts: tuple[int, ...]
    transition_offsets_frames: tuple[int, ...]
    body_frames: int
    cover_frames: int
    total_frames: int
    fps: int

    @property
    def duration(self) -> Fraction:
        return Fraction(self.total_frames, self.fps)

    @property
    def duration_seconds(self) -> float:
        return float(self.duration)

    @property
    def subtitle_offset_seconds(self) -> float:
        return self.cover_frames / self.fps


@dataclass(frozen=True)
class AudioPlan:
    include_source: bool
    include_music: bool
    loop_music: bool
    total_duration_seconds: float
    source_delay_samples: int
    music_volume: float
    fadeout_start_seconds: float | None
    fadeout_duration_seconds: float


@dataclass(frozen=True)
class ProcessResult:
    args: tuple[str, ...]
    return_code: int
    stderr: str
    cancelled: bool

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and not self.cancelled


@dataclass(frozen=True)
class ExpectedOutput:
    width: int
    height: int
    fps: int
    frame_count: int
    has_audio: bool
    duration_seconds: float


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    errors: tuple[str, ...]
    probe: ProbeInfo | None = None


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    cover_path: Path | None
    report_path: Path
    log_path: Path
    timeline: TimelinePlan
    encoder: str
    verification: VerificationResult


@dataclass(frozen=True)
class FFmpegCapabilities:
    ffmpeg_path: Path
    ffprobe_path: Path
    ffmpeg_version: str
    ffprobe_version: str
    filters: frozenset[str]
    encoders: frozenset[str]
    nvenc_usable: bool
    missing_required: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.missing_required


@dataclass(frozen=True)
class ToolPaths:
    ffmpeg: Path
    ffprobe: Path
