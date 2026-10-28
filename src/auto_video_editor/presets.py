from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from .models import (
    CanvasMode,
    CanvasPosition,
    InterpolationMode,
    LogoMotion,
    MusicShortPolicy,
    OutputQuality,
    RenderSettings,
    SourceAudioMode,
    SubtitleStyle,
    TransitionType,
    VideoEncoder,
)
from .utils.paths import config_dir


BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "默认自动剪辑": {},
    "抖音2K高清": {
        "output_quality": "bitrate_16m",
        "interpolation_mode": "motion",
        "sharpen_amount": 0.45,
        "normalize_audio": True,
    },
    "快速预览": {
        "output_quality": "standard",
        "interpolation_mode": "fast",
        "sharpen_amount": 0.25,
        "denoise_strength": 0.0,
    },
    "20秒约40MB": {"output_quality": "bitrate_16m"},
    "静音原声＋35%配乐": {"source_audio_mode": "mute", "music_volume": 0.35},
}


_ENUM_FIELDS = {
    "interpolation_mode": InterpolationMode,
    "source_audio_mode": SourceAudioMode,
    "music_short_policy": MusicShortPolicy,
    "video_encoder": VideoEncoder,
    "output_quality": OutputQuality,
    "transition_type": TransitionType,
    "canvas_mode": CanvasMode,
    "canvas_position": CanvasPosition,
    "logo_motion": LogoMotion,
}


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def render_settings_to_mapping(settings: RenderSettings) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in asdict(settings).items()}


def _number(raw: Any, default: float, low: float, high: float) -> float:
    try:
        return min(high, max(low, float(raw)))
    except (TypeError, ValueError):
        return default


def _integer(raw: Any, default: int, low: int, high: int) -> int:
    return int(round(_number(raw, default, low, high)))


def _color(raw: Any, default: str) -> str:
    value = str(raw).upper()
    return value if re.fullmatch(r"#[0-9A-F]{6}", value) else default


def subtitle_style_from_mapping(raw: Any, base: SubtitleStyle | None = None) -> SubtitleStyle:
    base = base or SubtitleStyle()
    if not isinstance(raw, dict):
        return base
    words = raw.get("highlight_words", base.highlight_words)
    if isinstance(words, str):
        words = tuple(part.strip() for part in re.split(r"[,，]", words) if part.strip())
    elif isinstance(words, list):
        words = tuple(str(part).strip() for part in words if str(part).strip())
    else:
        words = base.highlight_words
    return SubtitleStyle(
        font_name=str(raw.get("font_name", base.font_name)).replace("\n", " ")[:128] or base.font_name,
        font_size=_integer(raw.get("font_size"), base.font_size, 24, 140),
        primary_color=_color(raw.get("primary_color"), base.primary_color),
        outline_color=_color(raw.get("outline_color"), base.outline_color),
        outline_width=_integer(raw.get("outline_width"), base.outline_width, 0, 12),
        margin_bottom=_integer(raw.get("margin_bottom"), base.margin_bottom, 0, 800),
        margin_horizontal=_integer(raw.get("margin_horizontal"), base.margin_horizontal, 0, 400),
        shadow_depth=_integer(raw.get("shadow_depth"), base.shadow_depth, 0, 12),
        background_opacity_percent=_integer(
            raw.get("background_opacity_percent"), base.background_opacity_percent, 0, 100
        ),
        max_chars_per_line=_integer(raw.get("max_chars_per_line"), base.max_chars_per_line, 4, 60),
        highlight_words=words[:30],
        highlight_color=_color(raw.get("highlight_color"), base.highlight_color),
    )


def render_settings_from_mapping(
    raw: Any,
    base: RenderSettings | None = None,
) -> RenderSettings:
    base = base or RenderSettings()
    if not isinstance(raw, dict):
        return base
    allowed = {item.name for item in fields(RenderSettings)} - {"width", "height", "fps"}
    values: dict[str, Any] = {}
    for name, enum_type in _ENUM_FIELDS.items():
        if name in raw:
            try:
                values[name] = enum_type(str(raw[name]))
            except ValueError:
                pass
    bool_fields = {
        "export_cover_image", "normalize_audio", "duck_music_under_source",
        "mirror_second_clip", "trim_trailing_black", "subtitle_enabled",
    }
    for name in bool_fields:
        if name in raw and isinstance(raw[name], bool):
            values[name] = raw[name]
    int_limits = {
        "transition_frames": (0, 300), "cover_frames": (0, 1800),
        "cover_zoom_percent": (100, 160), "canvas_x_percent": (0, 100),
        "canvas_y_percent": (0, 100), "logo_start_frame": (1, 1_000_000),
        "logo_end_frame": (0, 1_000_000), "logo_start_x_percent": (0, 100),
        "logo_start_y_percent": (0, 100), "logo_end_x_percent": (0, 100),
        "logo_end_y_percent": (0, 100), "logo_max_width": (1, 1440),
        "logo_max_height": (1, 2560), "logo_scale_percent": (10, 300),
        "logo_opacity_percent": (0, 100), "logo_margin": (0, 500),
    }
    for name, (low, high) in int_limits.items():
        if name in raw:
            values[name] = _integer(raw[name], getattr(base, name), low, high)
    float_limits = {
        "cover_fadein_seconds": (0.0, 10.0), "music_volume": (0.0, 1.0),
        "music_fadein_seconds": (0.0, 10.0), "music_fadeout_seconds": (0.0, 10.0),
        "loudness_target_lufs": (-24.0, -8.0), "clip_max_duration_seconds": (0.0, 3600.0),
        "sharpen_amount": (0.0, 2.0), "denoise_strength": (0.0, 20.0),
        "brightness": (-1.0, 1.0), "contrast": (0.5, 2.0),
        "saturation": (0.0, 3.0), "shadow_boost": (0.0, 1.0),
        "highlight_protection": (0.0, 1.0), "logo_fade_seconds": (0.0, 10.0),
    }
    for name, (low, high) in float_limits.items():
        if name in raw:
            values[name] = _number(raw[name], getattr(base, name), low, high)
    if "cover_title" in raw:
        values["cover_title"] = str(raw["cover_title"]).replace("\r", " ").replace("\n", " ")[:200]
    if "canvas_color" in raw:
        values["canvas_color"] = _color(raw["canvas_color"], base.canvas_color)
    if "subtitle_style" in raw:
        values["subtitle_style"] = subtitle_style_from_mapping(raw["subtitle_style"], base.subtitle_style)
    return replace(base, **{key: value for key, value in values.items() if key in allowed})


class PresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / "presets.json")

    def load_custom(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(name): mapping
            for name, mapping in raw.items()
            if isinstance(name, str) and isinstance(mapping, dict)
        }

    def save_custom(self, presets: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                json.dump(presets, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
