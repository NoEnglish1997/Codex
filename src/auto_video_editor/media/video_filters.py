from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from ..models import InterpolationMode, ProbeInfo, RenderSettings
from .timeline import calculate_timeline


def _is_near_target_aspect(width: int, height: int, target_width: int, target_height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    source_ratio = width / height
    target_ratio = target_width / target_height
    return abs(source_ratio - target_ratio) / target_ratio <= 0.003


def _rate_filter(probe: ProbeInfo, settings: RenderSettings) -> str:
    source_rate = probe.avg_frame_rate
    if settings.interpolation_mode == InterpolationMode.FAST:
        return f"fps={settings.fps}"
    if source_rate >= Fraction(settings.fps, 1) and not probe.is_vfr:
        return f"fps={settings.fps}"
    return (
        f"minterpolate=fps={settings.fps}:mi_mode=mci:mc_mode=aobmc:"
        "me_mode=bidir:vsbmc=1"
    )


def _finalize_video(settings: RenderSettings, end_frames: int | None = None) -> str:
    filters = [f"fps={settings.fps}"]
    if end_frames is not None:
        filters.append(f"trim=end_frame={end_frames}")
    filters.extend(["setsar=1", "format=yuv420p", "setpts=PTS-STARTPTS"])
    return ",".join(filters)


def build_canvas_filter(
    source_width: int,
    source_height: int,
    settings: RenderSettings,
    *,
    prefix: str = "",
    end_frames: int | None = None,
) -> str:
    width, height = settings.width, settings.height
    finalize = _finalize_video(settings, end_frames)
    if _is_near_target_aspect(source_width, source_height, width, height):
        return (
            f"{prefix}scale={width}:{height}:force_original_aspect_ratio=increase:"
            f"force_divisible_by=2,crop={width}:{height},{finalize}"
        )
    return (
        f"{prefix}split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase:"
        f"force_divisible_by=2,crop={width}:{height},gblur=sigma=30,"
        "eq=brightness=-0.08[background];"
        f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease:"
        "force_divisible_by=2[foreground];"
        "[background][foreground]overlay=(W-w)/2:(H-h)/2:shortest=1,"
        f"{finalize}"
    )


def build_normalization_filter(probe: ProbeInfo, settings: RenderSettings) -> str:
    target_frames = max(1, int(probe.duration_seconds * settings.fps + 0.5))
    prefix = (
        "setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.100000000,"
        f"{_rate_filter(probe, settings)},"
    )
    return build_canvas_filter(
        probe.display_width or probe.width,
        probe.display_height or probe.height,
        settings,
        prefix=prefix,
        end_frames=target_frames,
    )


def build_cover_filter(width: int, height: int, settings: RenderSettings) -> str:
    return build_canvas_filter(width, height, settings, prefix="setpts=PTS-STARTPTS,")


def build_xfade_filtergraph(frame_counts: list[int] | tuple[int, ...], settings: RenderSettings) -> tuple[str, str]:
    plan = calculate_timeline(
        frame_counts,
        False,
        fps=settings.fps,
        transition_frames=settings.transition_frames,
        cover_frames=settings.cover_frames,
    )
    chains: list[str] = []
    if len(frame_counts) == 1:
        current = "0:v"
    else:
        current = "0:v"
        duration = settings.transition_frames / settings.fps
        for index, offset_frames in enumerate(plan.transition_offsets_frames, 1):
            output = f"xf{index}"
            offset = offset_frames / settings.fps
            chains.append(
                f"[{current}][{index}:v]xfade=transition=fade:duration={duration:.9f}:"
                f"offset={offset:.9f}[{output}]"
            )
            current = output
    chains.append(
        f"[{current}]trim=end_frame={plan.body_frames},setpts=PTS-STARTPTS,format=yuv420p[vout]"
    )
    return ";".join(chains), "[vout]"


def build_cover_concat_filtergraph(body_frames: int, settings: RenderSettings) -> tuple[str, str]:
    total = body_frames + settings.cover_frames
    graph = (
        f"[0:v]trim=end_frame={settings.cover_frames},setpts=PTS-STARTPTS[cover];"
        f"[1:v]trim=end_frame={body_frames},setpts=PTS-STARTPTS[body];"
        "[cover][body]concat=n=2:v=1:a=0[joined];"
        f"[joined]trim=end_frame={total},setpts=PTS-STARTPTS,format=yuv420p[vout]"
    )
    return graph, "[vout]"


def escape_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_final_video_filter(
    settings: RenderSettings,
    total_frames: int,
    subtitle_path: Path | None,
) -> tuple[str, str]:
    first = "[0:v]"
    filters: list[str] = []
    if subtitle_path is not None:
        filters.append(f"subtitles=filename='{escape_filter_path(subtitle_path)}'")
    filters.extend(
        [
            f"fps={settings.fps}",
            f"trim=end_frame={total_frames}",
            "setpts=PTS-STARTPTS",
            "format=yuv420p",
        ]
    )
    return f"{first}{','.join(filters)}[vout]", "[vout]"
