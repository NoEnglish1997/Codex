from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from ..models import OutputQuality, RenderSettings, VideoItem
from .clips import effective_clip_frames
from .timeline import calculate_timeline


_ESTIMATED_MBPS = {
    OutputQuality.STANDARD: 8.0,
    OutputQuality.HIGH: 12.0,
    OutputQuality.ULTRA: 16.0,
    OutputQuality.BITRATE_12M: 12.0,
    OutputQuality.BITRATE_16M: 16.0,
    OutputQuality.BITRATE_20M: 20.0,
}


@dataclass(frozen=True)
class ExportEstimate:
    duration_seconds: float
    total_frames: int
    estimated_bytes: int
    required_free_bytes: int
    available_free_bytes: int | None
    warnings: tuple[str, ...]
    size_is_targeted: bool


def estimate_export(
    items: tuple[VideoItem, ...],
    settings: RenderSettings,
    *,
    has_cover: bool,
    output_dir: Path | None = None,
    has_audio: bool = True,
) -> ExportEstimate:
    if not items or any(item.probe is None for item in items):
        raise ValueError("素材元信息尚未读取完整")
    counts = [effective_clip_frames(item, item.probe, settings) for item in items if item.probe]
    plan = calculate_timeline(
        counts,
        has_cover,
        fps=settings.fps,
        transition_frames=settings.transition_frames,
        cover_frames=settings.cover_frames,
    )
    video_mbps = _ESTIMATED_MBPS[settings.output_quality]
    audio_mbps = 0.192 if has_audio else 0.0
    estimated = round(plan.duration_seconds * (video_mbps + audio_mbps) * 1_000_000 / 8)
    required = max(256 * 1024 * 1024, round(estimated * 1.35))
    free: int | None = None
    if output_dir:
        existing = next((path for path in (output_dir, *output_dir.parents) if path.exists()), None)
        if existing:
            free = shutil.disk_usage(existing).free
    warnings: list[str] = []
    for item in items:
        probe = item.probe
        assert probe is not None
        if probe.display_width < 1080 or probe.display_height < 1080:
            warnings.append(f"{item.display_name} 低于1080级清晰度，放大不会产生真实细节")
        if probe.is_vfr:
            warnings.append(f"{item.display_name} 是可变帧率，将转换为60FPS")
        elif probe.avg_frame_rate and float(probe.avg_frame_rate) < 24:
            warnings.append(f"{item.display_name} 原始帧率低于24FPS")
    if free is not None and free < required:
        warnings.append("预计可用磁盘空间不足")
    targeted = settings.output_quality in {
        OutputQuality.BITRATE_12M,
        OutputQuality.BITRATE_16M,
        OutputQuality.BITRATE_20M,
    }
    return ExportEstimate(
        plan.duration_seconds,
        plan.total_frames,
        estimated,
        required,
        free,
        tuple(dict.fromkeys(warnings)),
        targeted,
    )
