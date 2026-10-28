from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from auto_video_editor.media.video_filters import (
    build_final_video_filter,
    build_normalization_filter,
    build_single_pass_video_filtergraph,
    build_xfade_filtergraph,
    normalized_frame_count,
)
from auto_video_editor.media.timeline import calculate_timeline
from auto_video_editor.models import (
    CanvasMode,
    CanvasPosition,
    InterpolationMode,
    LogoMotion,
    ProbeInfo,
    RenderSettings,
    TransitionType,
)


def _probe(width=1920, height=1080, fps=Fraction(30, 1)):
    return ProbeInfo(
        path=Path("source.mp4"),
        duration_seconds=3,
        width=width,
        height=height,
        display_width=width,
        display_height=height,
        avg_frame_rate=fps,
        real_frame_rate=fps,
        has_video=True,
    )


def test_motion_and_fast_modes_use_different_real_filters():
    motion = build_normalization_filter(_probe(), RenderSettings(interpolation_mode=InterpolationMode.MOTION))
    fast = build_normalization_filter(_probe(), RenderSettings(interpolation_mode=InterpolationMode.FAST))
    assert "minterpolate=fps=60" in motion
    assert "minterpolate" not in fast
    assert "fps=60" in fast


def test_native_60fps_does_not_run_motion_interpolation_twice():
    graph = build_normalization_filter(_probe(fps=Fraction(60, 1)), RenderSettings())
    assert "minterpolate" not in graph
    assert "fps=60" in graph


def test_landscape_gets_blurred_background_and_full_foreground():
    graph = build_normalization_filter(_probe(), RenderSettings())
    assert "split=2" in graph
    assert graph.count("flags=lanczos") == 2
    assert "gblur=sigma=30" in graph
    assert "force_original_aspect_ratio=decrease" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph


def test_native_vertical_uses_fast_aspect_path():
    graph = build_normalization_filter(_probe(720, 1280), RenderSettings())
    assert "gblur" not in graph
    assert "crop=1440:2560" in graph
    assert "scale=w=1440:h=2560:flags=lanczos" in graph


def test_second_clip_can_be_mirrored_before_canvas_composition():
    graph = build_normalization_filter(_probe(), RenderSettings(), horizontal_flip=True)
    assert ",hflip," in graph
    assert graph.index("hflip") < graph.index("split=2")


def test_xfade_uses_integer_frame_offsets():
    graph, label = build_xfade_filtergraph([600, 600, 600], RenderSettings())
    assert "duration=1.000000000:offset=9.000000000" in graph
    assert "duration=1.000000000:offset=18.000000000" in graph
    assert "trim=end_frame=1680" in graph
    assert label == "[vout]"


def test_subtitle_filter_is_omitted_or_included():
    without, _ = build_final_video_filter(RenderSettings(), 120, None)
    with_subtitles, _ = build_final_video_filter(RenderSettings(), 120, Path("C:/临时 目录/sub.ass"))
    assert "subtitles=" not in without
    assert "subtitles=" in with_subtitles
    assert "C\\:" in with_subtitles


def test_logo_moves_diagonally_from_top_right_to_bottom_left_after_five_frames():
    graph, label = build_final_video_filter(RenderSettings(), 600, None, logo_input_index=1)
    assert "[1:v]scale=w=240:h=240" in graph
    assert "enable='gte(n,4)'" in graph
    assert "x='W-w-48-(W-w-96)*clip((n-4)/595,0,1)'" in graph
    assert "y='48+(H-h-96)*clip((n-4)/595,0,1)'" in graph
    assert label == "[vout]"


def test_logo_scale_percentage_changes_bounding_box_and_is_clamped():
    larger, _ = build_final_video_filter(
        RenderSettings(logo_scale_percent=150), 600, None, logo_input_index=1
    )
    clamped, _ = build_final_video_filter(
        RenderSettings(logo_scale_percent=999), 600, None, logo_input_index=1
    )
    assert "scale=w=360:h=360" in larger
    assert "scale=w=720:h=720" in clamped


def test_logo_opacity_percentage_controls_alpha_and_is_clamped():
    translucent, _ = build_final_video_filter(
        RenderSettings(logo_opacity_percent=35), 600, None, logo_input_index=1
    )
    invisible, _ = build_final_video_filter(
        RenderSettings(logo_opacity_percent=-10), 600, None, logo_input_index=1
    )
    assert "colorchannelmixer=aa=0.350000" in translucent
    assert "colorchannelmixer=aa=0.000000" in invisible


def test_single_pass_graph_combines_original_clips_cover_logo_and_transitions():
    settings = RenderSettings(interpolation_mode=InterpolationMode.FAST)
    probes = (_probe(), _probe(width=1080, height=1920))
    timeline = calculate_timeline([180, 180], True)

    graph, label = build_single_pass_video_filtergraph(
        probes,
        settings,
        timeline,
        None,
        cover_input=(2, 320, 180),
        logo_input_index=3,
    )

    assert "[0:v]" in graph and "[1:v]" in graph
    assert "[clip0_bgsrc]" in graph and "[clip0]" in graph and "[clip1]" in graph
    assert "[1:v]setpts=PTS-STARTPTS" in graph
    assert "hflip" in graph
    assert "[clip0][clip1]xfade=" in graph
    assert "[2:v]" in graph and "[cover][body]concat=" in graph
    assert "[3:v]scale=w=240:h=240" in graph
    assert "[visual_base]unsharp=5:5:0.45:5:5:0.0[enhanced_base]" in graph
    assert "[enhanced_base][logo]overlay=" in graph
    assert "trim=end_frame=305" in graph
    assert label == "[vout]"


def test_normalized_frame_count_matches_filter_trim_rule():
    settings = RenderSettings(fps=60)
    probe = _probe()
    assert normalized_frame_count(probe, settings) == 180
    graph = build_normalization_filter(probe, settings)
    assert "trim=end_frame=180" in graph


def test_trim_crop_position_and_non_ai_enhancement_are_in_single_graph():
    settings = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        canvas_mode=CanvasMode.CROP,
        canvas_position=CanvasPosition.CUSTOM,
        canvas_x_percent=25,
        canvas_y_percent=75,
        denoise_strength=2,
        brightness=0.05,
        contrast=1.1,
        saturation=1.2,
        shadow_boost=0.4,
        highlight_protection=0.5,
        sharpen_amount=0.8,
    )
    probe = _probe()
    timeline = calculate_timeline([120], False)
    graph, _ = build_single_pass_video_filtergraph(
        (probe,), settings, timeline, None, clip_ranges=((0.5, 2.5),)
    )
    assert "trim=start=0.500000000:end=2.500000000" in graph
    assert "crop=w=1440:h=2560" in graph
    assert "(iw-ow)*0.250000" in graph
    assert "hqdn3d=" in graph
    assert "eq=brightness=0.0500:contrast=1.1000:saturation=1.2000" in graph
    assert "curves=" in graph
    assert "unsharp=5:5:0.80" in graph


def test_no_transition_uses_concat_and_custom_transition_uses_xfade_name():
    probes = (_probe(), _probe())
    no_transition = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        transition_type=TransitionType.NONE,
        transition_frames=0,
    )
    graph, _ = build_single_pass_video_filtergraph(
        probes, no_transition, calculate_timeline([180, 180], False, transition_frames=0), None
    )
    assert "concat=n=2:v=1:a=0" in graph
    assert "xfade=" not in graph
    wipe = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        transition_type=TransitionType.WIPE_LEFT,
        transition_frames=30,
    )
    graph, _ = build_single_pass_video_filtergraph(
        probes, wipe, calculate_timeline([180, 180], False, transition_frames=30), None
    )
    assert "xfade=transition=wipeleft:duration=0.500000000" in graph


def test_cover_animation_title_and_logo_custom_path_are_real_filters():
    settings = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        cover_frames=30,
        cover_zoom_percent=110,
        cover_fadein_seconds=0.2,
        logo_motion=LogoMotion.CUSTOM,
        logo_start_frame=10,
        logo_end_frame=100,
        logo_start_x_percent=10,
        logo_start_y_percent=20,
        logo_end_x_percent=80,
        logo_end_y_percent=90,
        logo_fade_seconds=0.2,
    )
    graph, _ = build_single_pass_video_filtergraph(
        (_probe(),),
        settings,
        calculate_timeline([180], True, cover_frames=30),
        None,
        cover_input=(1, 320, 180),
        logo_input_index=2,
        cover_title_path=Path("C:/tmp/title.ass"),
    )
    assert "zoompan=" in graph
    assert "fade=t=in:st=0:d=0.200000" in graph
    assert "subtitles=filename='" in graph and "title.ass" in graph
    assert "enable='between(n,9,99)'" in graph
    assert "fade=t=in:st=0.150000:d=0.200000:alpha=1" in graph
    assert "(0.100000+(0.700000)*clip((n-9)/90,0,1))" in graph
