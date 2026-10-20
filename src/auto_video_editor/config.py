from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import InterpolationMode, MusicShortPolicy, SourceAudioMode, VideoEncoder
from .utils.paths import config_dir, default_output_dir


@dataclass(frozen=True)
class AppSettings:
    output_dir: str = ""
    interpolation_mode: str = InterpolationMode.MOTION.value
    source_audio_mode: str = SourceAudioMode.MUTE.value
    music_short_policy: str = MusicShortPolicy.LOOP.value
    music_volume: float = 0.35
    video_encoder: str = VideoEncoder.AUTO.value
    mirror_second_clip: bool = True
    subtitle_font_name: str = "Microsoft YaHei"
    logo_scale_percent: int = 100
    logo_opacity_percent: int = 100
    ffmpeg_path: str = ""
    ffprobe_path: str = ""

    @classmethod
    def defaults(cls) -> "AppSettings":
        return cls(output_dir=str(default_output_dir()))

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "AppSettings":
        defaults = cls.defaults()
        output = Path(str(raw.get("output_dir", defaults.output_dir))).expanduser()
        if not output.is_dir():
            output = Path(defaults.output_dir)
        interpolation = str(raw.get("interpolation_mode", defaults.interpolation_mode))
        if interpolation not in {item.value for item in InterpolationMode}:
            interpolation = defaults.interpolation_mode
        source_audio = str(raw.get("source_audio_mode", defaults.source_audio_mode))
        if source_audio not in {item.value for item in SourceAudioMode}:
            source_audio = defaults.source_audio_mode
        music_policy = str(raw.get("music_short_policy", defaults.music_short_policy))
        if music_policy not in {item.value for item in MusicShortPolicy}:
            music_policy = defaults.music_short_policy
        encoder = str(raw.get("video_encoder", defaults.video_encoder))
        if encoder not in {item.value for item in VideoEncoder}:
            encoder = defaults.video_encoder
        try:
            volume = min(1.0, max(0.0, float(raw.get("music_volume", defaults.music_volume))))
        except (TypeError, ValueError):
            volume = defaults.music_volume
        mirror_second = raw.get("mirror_second_clip", defaults.mirror_second_clip)
        if not isinstance(mirror_second, bool):
            mirror_second = defaults.mirror_second_clip
        font_name = str(raw.get("subtitle_font_name", defaults.subtitle_font_name)).strip()
        if not font_name or len(font_name) > 128 or "\n" in font_name or "\r" in font_name:
            font_name = defaults.subtitle_font_name
        try:
            logo_scale = min(300, max(10, int(raw.get("logo_scale_percent", defaults.logo_scale_percent))))
        except (TypeError, ValueError):
            logo_scale = defaults.logo_scale_percent
        try:
            logo_opacity = min(
                100,
                max(0, int(raw.get("logo_opacity_percent", defaults.logo_opacity_percent))),
            )
        except (TypeError, ValueError):
            logo_opacity = defaults.logo_opacity_percent
        return cls(
            output_dir=str(output),
            interpolation_mode=interpolation,
            source_audio_mode=source_audio,
            music_short_policy=music_policy,
            music_volume=volume,
            video_encoder=encoder,
            mirror_second_clip=mirror_second,
            subtitle_font_name=font_name,
            logo_scale_percent=logo_scale,
            logo_opacity_percent=logo_opacity,
            ffmpeg_path=str(raw.get("ffmpeg_path", "") or ""),
            ffprobe_path=str(raw.get("ffprobe_path", "") or ""),
        )


@dataclass(frozen=True)
class ConfigLoadResult:
    settings: AppSettings
    warning: str | None = None


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "settings.json")

    def load(self) -> ConfigLoadResult:
        if not self.path.exists():
            return ConfigLoadResult(AppSettings.defaults())
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("配置根节点必须是 JSON 对象")
            return ConfigLoadResult(AppSettings.from_mapping(raw))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return ConfigLoadResult(AppSettings.defaults(), f"配置文件损坏，已恢复默认值：{exc}")

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(asdict(settings), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
