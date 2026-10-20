from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..models import ProbeInfo


class ProbeError(RuntimeError):
    """Raised when FFprobe cannot return usable media metadata."""


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0


def parse_fraction(value: object) -> Fraction:
    if value in (None, "", "0/0", "N/A"):
        return Fraction(0, 1)
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return Fraction(0, 1)


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "", "N/A") else default
    except (TypeError, ValueError):
        return default


def _rotation(video: dict[str, Any]) -> int:
    for data in video.get("side_data_list", []):
        if "rotation" in data:
            try:
                return int(round(float(data["rotation"]))) % 360
            except (TypeError, ValueError):
                continue
    try:
        return int(round(float(video.get("tags", {}).get("rotate", 0)))) % 360
    except (TypeError, ValueError):
        return 0


def parse_probe_json(path: Path, payload: dict[str, Any]) -> ProbeInfo:
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    format_info = payload.get("format") or {}
    stream_duration = _as_float((video or {}).get("duration"), -1.0)
    format_duration = _as_float(format_info.get("duration"))
    start_time = _as_float((video or {}).get("start_time"), _as_float(format_info.get("start_time")))
    duration = stream_duration if stream_duration >= 0 else max(0.0, format_duration - max(0.0, start_time))
    width = int((video or {}).get("width") or 0)
    height = int((video or {}).get("height") or 0)
    rotation = _rotation(video or {})
    display_width, display_height = (height, width) if rotation in {90, 270} else (width, height)
    raw_frames = (video or {}).get("nb_read_frames") or (video or {}).get("nb_frames")
    try:
        frame_count = int(raw_frames) if raw_frames not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        frame_count = None
    return ProbeInfo(
        path=path,
        duration_seconds=duration,
        width=width,
        height=height,
        display_width=display_width,
        display_height=display_height,
        avg_frame_rate=parse_fraction((video or {}).get("avg_frame_rate")),
        real_frame_rate=parse_fraction((video or {}).get("r_frame_rate")),
        frame_count=frame_count,
        has_video=video is not None,
        has_audio=audio is not None,
        audio_duration_seconds=_as_float(audio.get("duration"), duration) if audio else None,
        rotation=rotation,
        video_codec=str((video or {}).get("codec_name") or ""),
        audio_codec=str((audio or {}).get("codec_name") or ""),
        audio_sample_rate=int(audio["sample_rate"]) if audio and str(audio.get("sample_rate", "")).isdigit() else None,
        audio_channels=int(audio["channels"]) if audio and str(audio.get("channels", "")).isdigit() else None,
        pixel_format=str((video or {}).get("pix_fmt") or ""),
        format_name=str(format_info.get("format_name") or ""),
        start_time_seconds=start_time,
    )


def probe_media(path: Path, ffprobe_path: Path, *, count_frames: bool = False) -> ProbeInfo:
    args = [
        str(ffprobe_path), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams",
    ]
    if count_frames:
        args.append("-count_frames")
    args.append(str(path))
    process = subprocess.Popen(
        args,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
    )
    try:
        stdout, stderr = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ProbeError(f"FFprobe 超时：{path}") from None
    if process.returncode != 0:
        raise ProbeError(f"无法读取媒体文件 {path.name}：{stderr.strip() or '未知错误'}")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"FFprobe 返回了无效 JSON：{exc}") from exc
    return parse_probe_json(path, payload)
