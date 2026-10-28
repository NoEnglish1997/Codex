from __future__ import annotations

import re

from ..models import ProbeInfo, RenderSettings, VideoItem


_BLACK_RANGE = re.compile(
    r"black_start:(?P<start>\d+(?:\.\d+)?)\s+black_end:(?P<end>\d+(?:\.\d+)?)"
)


def effective_clip_range(
    item: VideoItem,
    probe: ProbeInfo,
    settings: RenderSettings,
) -> tuple[float, float]:
    """Return a safe source-time range after per-item and global limits."""
    duration = max(0.0, probe.duration_seconds)
    start = min(duration, max(0.0, item.trim_start_seconds))
    requested_end = item.trim_end_seconds
    end = duration if requested_end <= 0 else min(duration, requested_end)
    if settings.clip_max_duration_seconds > 0:
        end = min(end, start + settings.clip_max_duration_seconds)
    if end <= start:
        raise ValueError(f"{item.display_name} 的裁剪结束时间必须晚于开始时间")
    return start, end


def effective_clip_frames(
    item: VideoItem,
    probe: ProbeInfo,
    settings: RenderSettings,
) -> int:
    start, end = effective_clip_range(item, probe, settings)
    return max(1, int((end - start) * settings.fps + 0.5))


def trailing_black_start(stderr: str, duration_seconds: float, *, tolerance: float = 0.2) -> float | None:
    """Find a trailing black range reported by FFmpeg blackdetect."""
    candidate: float | None = None
    for match in _BLACK_RANGE.finditer(stderr):
        start = float(match.group("start"))
        end = float(match.group("end"))
        if duration_seconds - end <= tolerance and end - start >= 0.2:
            candidate = start
    return candidate
