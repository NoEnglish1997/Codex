from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from ..models import (
    CanvasMode,
    CanvasPosition,
    InterpolationMode,
    LogoMotion,
    ProbeInfo,
    RenderSettings,
    TimelinePlan,
    TransitionType,
)
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


def _overlay_position(settings: RenderSettings) -> tuple[str, str]:
    if settings.canvas_position == CanvasPosition.LEFT:
        return "0", "(H-h)/2"
    if settings.canvas_position == CanvasPosition.RIGHT:
        return "W-w", "(H-h)/2"
    if settings.canvas_position == CanvasPosition.TOP:
        return "(W-w)/2", "0"
    if settings.canvas_position == CanvasPosition.BOTTOM:
        return "(W-w)/2", "H-h"
    if settings.canvas_position == CanvasPosition.CUSTOM:
        return (
            f"(W-w)*{settings.canvas_x_percent / 100:.6f}",
            f"(H-h)*{settings.canvas_y_percent / 100:.6f}",
        )
    return "(W-w)/2", "(H-h)/2"


def _crop_position(settings: RenderSettings) -> tuple[str, str]:
    if settings.canvas_position == CanvasPosition.LEFT:
        return "0", "(ih-oh)/2"
    if settings.canvas_position == CanvasPosition.RIGHT:
        return "iw-ow", "(ih-oh)/2"
    if settings.canvas_position == CanvasPosition.TOP:
        return "(iw-ow)/2", "0"
    if settings.canvas_position == CanvasPosition.BOTTOM:
        return "(iw-ow)/2", "ih-oh"
    if settings.canvas_position == CanvasPosition.CUSTOM:
        return (
            f"(iw-ow)*{settings.canvas_x_percent / 100:.6f}",
            f"(ih-oh)*{settings.canvas_y_percent / 100:.6f}",
        )
    return "(iw-ow)/2", "(ih-oh)/2"


def build_enhancement_filter(settings: RenderSettings) -> str:
    filters: list[str] = []
    if settings.denoise_strength > 0:
        strength = min(20.0, max(0.0, settings.denoise_strength))
        filters.append(f"hqdn3d={strength:.3f}:{strength * 0.75:.3f}:{strength * 1.5:.3f}:{strength * 1.125:.3f}")
    gamma = 1.0 + min(1.0, max(0.0, settings.shadow_boost)) * 0.35
    if (
        abs(settings.brightness) > 0.0001
        or abs(settings.contrast - 1.0) > 0.0001
        or abs(settings.saturation - 1.0) > 0.0001
        or abs(gamma - 1.0) > 0.0001
    ):
        filters.append(
            f"eq=brightness={settings.brightness:.4f}:contrast={settings.contrast:.4f}:"
            f"saturation={settings.saturation:.4f}:gamma={gamma:.4f}"
        )
    if settings.highlight_protection > 0:
        white = 1.0 - min(1.0, settings.highlight_protection) * 0.08
        filters.append(f"curves=all='0/0 0.75/0.75 1/{white:.4f}'")
    if settings.sharpen_amount > 0:
        filters.append(f"unsharp=5:5:{min(2.0, settings.sharpen_amount):.2f}:5:5:0.0")
    return ",".join(filters) or "null"


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
    if settings.canvas_mode == CanvasMode.CROP:
        crop_x, crop_y = _crop_position(settings)
        return (
            f"{prefix}scale=w={width}:h={height}:flags=lanczos:"
            "force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop=w={width}:h={height}:x='{crop_x}':y='{crop_y}',{finalize}"
        )
    bgsrc = f"{label_prefix}bgsrc"
    fgsrc = f"{label_prefix}fgsrc"
    background = f"{label_prefix}background"
    foreground = f"{label_prefix}foreground"
    overlay_x, overlay_y = _overlay_position(settings)
    overlay = (
        "overlay=(W-w)/2:(H-h)/2:shortest=1"
        if settings.canvas_position == CanvasPosition.CENTER
        else f"overlay=x='{overlay_x}':y='{overlay_y}':shortest=1"
    )
    if settings.canvas_mode == CanvasMode.SOLID:
        color = settings.canvas_color if settings.canvas_color.startswith("#") else "#000000"
        return (
            f"{prefix}scale=w={width}:h={height}:flags=lanczos:"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
            f"[{foreground}];color=c={color}:s={width}x{height}:r={settings.fps}[{background}];"
            f"[{background}][{foreground}]{overlay},"
            f"{finalize}"
        )
    return (
        f"{prefix}split=2[{bgsrc}][{fgsrc}];"
        f"[{bgsrc}]scale=w={width}:h={height}:flags=lanczos:"
        "force_original_aspect_ratio=increase:"
        f"force_divisible_by=2,crop={width}:{height},gblur=sigma=30,"
        f"eq=brightness=-0.08[{background}];"
        f"[{fgsrc}]scale=w={width}:h={height}:flags=lanczos:"
        "force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2[{foreground}];"
        f"[{background}][{foreground}]{overlay},"
        f"{finalize}"
    )


def build_normalization_filter(
    probe: ProbeInfo,
    settings: RenderSettings,
    *,
    horizontal_flip: bool = False,
    label_prefix: str = "",
    clip_start_seconds: float = 0.0,
    clip_end_seconds: float | None = None,
) -> str:
    target_frames = normalized_frame_count(
        probe,
        settings,
        clip_start_seconds=clip_start_seconds,
        clip_end_seconds=clip_end_seconds,
    )
    flip = "hflip," if horizontal_flip else ""
    trim = ""
    if clip_start_seconds > 0 or clip_end_seconds is not None:
        end = probe.duration_seconds if clip_end_seconds is None else clip_end_seconds
        trim = f"trim=start={clip_start_seconds:.9f}:end={end:.9f},"
    prefix = (
        f"{trim}setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=0.100000000,"
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


def normalized_frame_count(
    probe: ProbeInfo,
    settings: RenderSettings,
    *,
    clip_start_seconds: float = 0.0,
    clip_end_seconds: float | None = None,
) -> int:
    end = probe.duration_seconds if clip_end_seconds is None else min(probe.duration_seconds, clip_end_seconds)
    duration = max(0.0, end - max(0.0, clip_start_seconds))
    return max(1, int(duration * settings.fps + 0.5))


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
    clip_ranges: tuple[tuple[float, float], ...] | None = None,
    cover_title_path: Path | None = None,
) -> tuple[str, str]:
    """Build one graph from original clips through overlays without intermediate video encoding."""
    if not probes:
        raise ValueError("至少需要一个视频探测结果")
    if len(probes) != len(timeline.frame_counts):
        raise ValueError("素材探测数量与时间线不一致")

    chains: list[str] = []
    for index, probe in enumerate(probes):
        clip_start, clip_end = clip_ranges[index] if clip_ranges else (0.0, None)
        normalized = build_normalization_filter(
            probe,
            settings,
            horizontal_flip=settings.mirror_second_clip and index == 1,
            label_prefix=f"clip{index}_",
            clip_start_seconds=clip_start,
            clip_end_seconds=clip_end,
        )
        # xfade negotiates a common high-chroma working format. Put fps after
        # that conversion so its inputs retain an explicit constant frame rate.
        chains.append(
            f"[{index}:v]{normalized},format=yuv444p,fps={settings.fps}[clip{index}]"
        )

    if len(probes) > 1 and (
        settings.transition_type == TransitionType.NONE or settings.transition_frames == 0
    ):
        inputs = "".join(f"[clip{index}]" for index in range(len(probes)))
        chains.append(f"{inputs}concat=n={len(probes)}:v=1:a=0[concat_body]")
        current = "concat_body"
    else:
        current = "clip0"
        duration = settings.transition_frames / settings.fps
        for index, offset_frames in enumerate(timeline.transition_offsets_frames, 1):
            output = f"xf{index}"
            offset = offset_frames / settings.fps
            chains.append(
                f"[{current}][clip{index}]xfade=transition={settings.transition_type.value}:"
                f"duration={duration:.9f}:offset={offset:.9f}[{output}]"
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
        cover_label = "cover"
        if settings.cover_zoom_percent > 100 or settings.cover_fadein_seconds > 0 or cover_title_path:
            chains.append(f"[{input_index}:v]{cover_filter}[cover_base]")
            cover_label = "cover_base"
            if settings.cover_zoom_percent > 100:
                delta = (settings.cover_zoom_percent - 100) / 100
                denominator = max(1, settings.cover_frames - 1)
                chains.append(
                    f"[{cover_label}]zoompan=z='1+{delta:.6f}*on/{denominator}':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                    f"s={settings.width}x{settings.height}:fps={settings.fps}[cover_zoom]"
                )
                cover_label = "cover_zoom"
            if settings.cover_fadein_seconds > 0:
                chains.append(
                    f"[{cover_label}]fade=t=in:st=0:d={settings.cover_fadein_seconds:.6f}[cover_fade]"
                )
                cover_label = "cover_fade"
            if cover_title_path:
                chains.append(
                    f"[{cover_label}]subtitles=filename='{escape_filter_path(cover_title_path)}'[cover_title]"
                )
                cover_label = "cover_title"
        else:
            chains.append(f"[{input_index}:v]{cover_filter}[cover]")
        chains.append(
            f"[{cover_label}][{current}]concat=n=2:v=1:a=0,"
            f"trim=end_frame={timeline.total_frames},setpts=PTS-STARTPTS[with_cover]"
        )
        current = "with_cover"

    chains.append(
        f"[{current}]fps={settings.fps},tpad=stop_mode=clone:stop_duration=0.100000000,"
        f"trim=end_frame={timeline.total_frames},setpts=PTS-STARTPTS[visual_base]"
    )
    # A restrained luma-only sharpen recovers edge contrast lost during scaling
    # without using an AI model or adding chroma ringing to text and logos.
    chains.append(f"[visual_base]{build_enhancement_filter(settings)}[enhanced_base]")
    current = "enhanced_base"

    if logo_input_index is not None:
        scale_percent = min(300, max(10, settings.logo_scale_percent))
        opacity = min(100, max(0, settings.logo_opacity_percent)) / 100
        logo_width = max(1, round(settings.logo_max_width * scale_percent / 100))
        logo_height = max(1, round(settings.logo_max_height * scale_percent / 100))
        start_index, end_index, x, y = _logo_geometry(settings, timeline.total_frames)
        logo_filters = [
            f"scale=w={logo_width}:h={logo_height}:flags=lanczos:force_original_aspect_ratio=decrease",
            "format=rgba",
            f"colorchannelmixer=aa={opacity:.6f}",
        ]
        if settings.logo_fade_seconds > 0:
            start_seconds = start_index / settings.fps
            fade = settings.logo_fade_seconds
            logo_filters.append(f"fade=t=in:st={start_seconds:.6f}:d={fade:.6f}:alpha=1")
            out_start = max(start_seconds, (end_index + 1) / settings.fps - fade)
            logo_filters.append(f"fade=t=out:st={out_start:.6f}:d={fade:.6f}:alpha=1")
        logo_filters.append("setpts=PTS-STARTPTS")
        chains.append(
            f"[{logo_input_index}:v]{','.join(logo_filters)}[logo]"
        )
        enable = f"between(n,{start_index},{end_index})"
        chains.append(
            f"[{current}][logo]overlay=x='{x}':y='{y}':enable='{enable}':"
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


def _logo_geometry(settings: RenderSettings, total_frames: int) -> tuple[int, int, str, str]:
    start = max(0, settings.logo_start_frame - 1)
    end = total_frames - 1 if settings.logo_end_frame <= 0 else min(total_frames - 1, settings.logo_end_frame - 1)
    end = max(start, end)
    margin = settings.logo_margin
    travel = max(1, end - start)
    progress = f"clip((n-{start})/{travel},0,1)"
    if settings.logo_motion == LogoMotion.TOP_RIGHT_TO_BOTTOM_LEFT:
        return (
            start, end,
            f"W-w-{margin}-(W-w-{margin * 2})*{progress}",
            f"{margin}+(H-h-{margin * 2})*{progress}",
        )
    points = {
        LogoMotion.TOP_LEFT_TO_BOTTOM_RIGHT: (0, 0, 100, 100),
        LogoMotion.BOTTOM_LEFT_TO_TOP_RIGHT: (0, 100, 100, 0),
        LogoMotion.FIXED_TOP_RIGHT: (100, 0, 100, 0),
        LogoMotion.FIXED_TOP_LEFT: (0, 0, 0, 0),
        LogoMotion.FIXED_BOTTOM_RIGHT: (100, 100, 100, 100),
        LogoMotion.FIXED_BOTTOM_LEFT: (0, 100, 0, 100),
        LogoMotion.CUSTOM: (
            settings.logo_start_x_percent, settings.logo_start_y_percent,
            settings.logo_end_x_percent, settings.logo_end_y_percent,
        ),
    }
    sx, sy, ex, ey = points[settings.logo_motion]
    span_x = f"(W-w-{margin * 2})"
    span_y = f"(H-h-{margin * 2})"
    x = f"{margin}+{span_x}*({sx / 100:.6f}+({(ex - sx) / 100:.6f})*{progress})"
    y = f"{margin}+{span_y}*({sy / 100:.6f}+({(ey - sy) / 100:.6f})*{progress})"
    return start, end, x, y


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
                f"[{current}][{index}:v]xfade=transition={settings.transition_type.value}:duration={duration:.9f}:"
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
