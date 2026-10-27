from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from ..models import InterpolationMode, ProbeInfo, RenderSettings, TimelinePlan
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
    label_prefix: str = "",
) -> str:
    width, height = settings.width, settings.height
    finalize = _finalize_video(settings, end_frames)
    if _is_near_target_aspect(source_width, source_height, width, height):
        return (
            f"{prefix}scale=w={width}:h={height}:flags=lanczos:"
            "force_original_aspect_ratio=increase:"
            f"force_divisible_by=2,crop={width}:{height},{finalize}"
        )
    bgsrc = f"{label_prefix}bgsrc"
    fgsrc = f"{label_prefix}fgsrc"
    background = f"{label_prefix}background"
    foreground = f"{label_prefix}foreground"
    return (
        f"{prefix}split=2[{bgsrc}][{fgsrc}];"
        f"[{bgsrc}]scale=w={width}:h={height}:flags=lanczos:"
        "force_original_aspect_ratio=increase:"
        f"force_divisible_by=2,crop={width}:{height},gblur=sigma=30,"
        f"eq=brightness=-0.08[{background}];"
        f"[{fgsrc}]scale=w={width}:h={height}:flags=lanczos:"
        "force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2[{foreground}];"
        f"[{background}][{foreground}]overlay=(W-w)/2:(H-h)/2:shortest=1,"
        f"{finalize}"
    )


def build_normalization_filter(
    probe: ProbeInfo,
    settings: RenderSettings,
    *,
    horizontal_flip: bool = False,
    label_prefix: str = "",
) -> str:
    target_frames = normalized_frame_count(probe, settings)
    flip = "hflip," if horizontal_flip else ""
    prefix = (
        "setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.100000000,"
        f"{_rate_filter(probe, settings)},{flip}"
    )
    return build_canvas_filter(
        probe.display_width or probe.width,
        probe.display_height or probe.height,
        settings,
        prefix=prefix,
        end_frames=target_frames,
        label_prefix=label_prefix,
    )


def normalized_frame_count(probe: ProbeInfo, settings: RenderSettings) -> int:
    return max(1, int(probe.duration_seconds * settings.fps + 0.5))


def build_cover_filter(
    width: int,
    height: int,
    settings: RenderSettings,
    *,
    end_frames: int | None = None,
    label_prefix: str = "",
) -> str:
    return build_canvas_filter(
        width,
        height,
        settings,
        prefix="setpts=PTS-STARTPTS,",
        end_frames=end_frames,
        label_prefix=label_prefix,
    )


def build_single_pass_video_filtergraph(
    probes: tuple[ProbeInfo, ...],
    settings: RenderSettings,
    timeline: TimelinePlan,
    subtitle_path: Path | None,
    *,
    cover_input: tuple[int, int, int] | None = None,
    logo_input_index: int | None = None,
) -> tuple[str, str]:
    """Build one graph from original clips through overlays without intermediate video encoding."""
    if not probes:
        raise ValueError("至少需要一个视频探测结果")
    if len(probes) != len(timeline.frame_counts):
        raise ValueError("素材探测数量与时间线不一致")

    chains: list[str] = []
    for index, probe in enumerate(probes):
        normalized = build_normalization_filter(
            probe,
            settings,
            horizontal_flip=settings.mirror_second_clip and index == 1,
            label_prefix=f"clip{index}_",
        )
        # xfade negotiates a common high-chroma working format. Put fps after
        # that conversion so its inputs retain an explicit constant frame rate.
        chains.append(
            f"[{index}:v]{normalized},format=yuv444p,fps={settings.fps}[clip{index}]"
        )

    current = "clip0"
    duration = settings.transition_frames / settings.fps
    for index, offset_frames in enumerate(timeline.transition_offsets_frames, 1):
        output = f"xf{index}"
        offset = offset_frames / settings.fps
        chains.append(
            f"[{current}][clip{index}]xfade=transition=fade:duration={duration:.9f}:"
            f"offset={offset:.9f}[{output}]"
        )
        current = output
    chains.append(
        f"[{current}]fps={settings.fps},tpad=stop_mode=clone:stop_duration=0.100000000,"
        f"trim=end_frame={timeline.body_frames},setpts=PTS-STARTPTS,"
        "setsar=1,format=yuv420p[body]"
    )
    current = "body"

    if cover_input is not None:
        input_index, width, height = cover_input
        cover_filter = build_cover_filter(
            width,
            height,
            settings,
            end_frames=settings.cover_frames,
            label_prefix="cover_",
        )
        chains.append(f"[{input_index}:v]{cover_filter}[cover]")
        chains.append(
            f"[cover][{current}]concat=n=2:v=1:a=0,"
            f"trim=end_frame={timeline.total_frames},setpts=PTS-STARTPTS[with_cover]"
        )
        current = "with_cover"

    chains.append(
        f"[{current}]fps={settings.fps},tpad=stop_mode=clone:stop_duration=0.100000000,"
        f"trim=end_frame={timeline.total_frames},setpts=PTS-STARTPTS[visual_base]"
    )
    # A restrained luma-only sharpen recovers edge contrast lost during scaling
    # without using an AI model or adding chroma ringing to text and logos.
    chains.append(
        "[visual_base]unsharp=5:5:0.45:5:5:0.0[enhanced_base]"
    )
    current = "enhanced_base"

    if logo_input_index is not None:
        scale_percent = min(300, max(10, settings.logo_scale_percent))
        opacity = min(100, max(0, settings.logo_opacity_percent)) / 100
        logo_width = max(1, round(settings.logo_max_width * scale_percent / 100))
        logo_height = max(1, round(settings.logo_max_height * scale_percent / 100))
        start_index = max(0, settings.logo_start_frame - 1)
        travel_frames = max(1, timeline.total_frames - start_index - 1)
        progress = f"clip((n-{start_index})/{travel_frames},0,1)"
        x = f"W-w-{settings.logo_margin}-(W-w-{settings.logo_margin * 2})*{progress}"
        y = f"{settings.logo_margin}+(H-h-{settings.logo_margin * 2})*{progress}"
        chains.append(
            f"[{logo_input_index}:v]scale=w={logo_width}:h={logo_height}:"
            "flags=lanczos:force_original_aspect_ratio=decrease,format=rgba,"
            f"colorchannelmixer=aa={opacity:.6f},setpts=PTS-STARTPTS[logo]"
        )
        chains.append(
            f"[{current}][logo]overlay=x='{x}':y='{y}':enable='gte(n,{start_index})':"
            "shortest=1[with_logo]"
        )
        current = "with_logo"

    if subtitle_path is not None:
        chains.append(
            f"[{current}]subtitles=filename='{escape_filter_path(subtitle_path)}'[with_subtitles]"
        )
        current = "with_subtitles"

    chains.append(
        f"[{current}]fps={settings.fps},trim=end_frame={timeline.total_frames},"
        "setsar=1,format=yuv420p,setpts=PTS-STARTPTS[vout]"
    )
    return ";".join(chains), "[vout]"


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
    logo_input_index: int | None = None,
) -> tuple[str, str]:
    chains = [
        f"[0:v]fps={settings.fps},trim=end_frame={total_frames},"
        "setpts=PTS-STARTPTS[base]"
    ]
    current = "base"
    if logo_input_index is not None:
        scale_percent = min(300, max(10, settings.logo_scale_percent))
        opacity = min(100, max(0, settings.logo_opacity_percent)) / 100
        logo_width = max(1, round(settings.logo_max_width * scale_percent / 100))
        logo_height = max(1, round(settings.logo_max_height * scale_percent / 100))
        start_index = max(0, settings.logo_start_frame - 1)
        travel_frames = max(1, total_frames - start_index - 1)
        progress = f"clip((n-{start_index})/{travel_frames},0,1)"
        x = (
            f"W-w-{settings.logo_margin}-(W-w-{settings.logo_margin * 2})*{progress}"
        )
        y = f"{settings.logo_margin}+(H-h-{settings.logo_margin * 2})*{progress}"
        chains.append(
            f"[{logo_input_index}:v]scale=w={logo_width}:h={logo_height}:"
            "flags=lanczos:force_original_aspect_ratio=decrease,format=rgba,"
            f"colorchannelmixer=aa={opacity:.6f},setpts=PTS-STARTPTS[logo]"
        )
        chains.append(
            f"[{current}][logo]overlay=x='{x}':y='{y}':enable='gte(n,{start_index})':"
            "shortest=1[with_logo]"
        )
        current = "with_logo"
    if subtitle_path is not None:
        chains.append(
            f"[{current}]subtitles=filename='{escape_filter_path(subtitle_path)}'[with_subtitles]"
        )
        current = "with_subtitles"
    chains.append(f"[{current}]format=yuv420p[vout]")
    return ";".join(chains), "[vout]"
