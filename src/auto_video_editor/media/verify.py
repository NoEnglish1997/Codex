from __future__ import annotations

from pathlib import Path

from ..models import ExpectedOutput, VerificationResult
from .ffprobe import ProbeError, probe_media


def verify_output(path: Path, ffprobe_path: Path, expected: ExpectedOutput) -> VerificationResult:
    errors: list[str] = []
    if not path.is_file() or path.stat().st_size == 0:
        return VerificationResult(False, ("输出文件不存在或为空。",))
    try:
        probe = probe_media(path, ffprobe_path, count_frames=True)
    except ProbeError as exc:
        return VerificationResult(False, (str(exc),))
    if not probe.has_video:
        errors.append("输出没有视频轨。")
    if probe.video_codec != "h264":
        errors.append(f"视频编码应为 H.264，实际为 {probe.video_codec or '未知'}。")
    if (probe.width, probe.height) != (expected.width, expected.height):
        errors.append(f"画面应为 {expected.width}×{expected.height}，实际为 {probe.width}×{probe.height}。")
    if probe.avg_frame_rate.numerator != expected.fps * probe.avg_frame_rate.denominator:
        errors.append(f"帧率应为 {expected.fps}/1，实际为 {probe.avg_frame_rate}。")
    if probe.frame_count is None:
        errors.append("FFprobe 未返回实际视频帧数。")
    elif abs(probe.frame_count - expected.frame_count) > 1:
        errors.append(f"视频应为 {expected.frame_count} 帧，实际为 {probe.frame_count} 帧。")
    if expected.has_audio and not probe.has_audio:
        errors.append("输出缺少预期音轨。")
    if probe.has_audio:
        if probe.audio_codec != "aac":
            errors.append(f"音频编码应为 AAC，实际为 {probe.audio_codec or '未知'}。")
        if probe.audio_sample_rate != 48_000:
            errors.append(f"音频采样率应为 48000 Hz，实际为 {probe.audio_sample_rate}。")
        audio_duration = probe.audio_duration_seconds or probe.duration_seconds
        if abs(audio_duration - expected.duration_seconds) > 0.1:
            errors.append(
                f"音频时长与目标相差超过 100ms：{audio_duration:.3f}s / {expected.duration_seconds:.3f}s。"
            )
    if abs(probe.duration_seconds - expected.duration_seconds) > (1 / expected.fps + 0.1):
        errors.append(
            f"成片时长与目标不符：{probe.duration_seconds:.3f}s / {expected.duration_seconds:.3f}s。"
        )
    return VerificationResult(not errors, tuple(errors), probe)
