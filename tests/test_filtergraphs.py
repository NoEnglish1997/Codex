from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from auto_video_editor.media.video_filters import (
    build_final_video_filter,
    build_normalization_filter,
    build_xfade_filtergraph,
)
from auto_video_editor.models import InterpolationMode, ProbeInfo, RenderSettings


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
    assert "gblur=sigma=30" in graph
    assert "force_original_aspect_ratio=decrease" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph


def test_native_vertical_uses_fast_aspect_path():
    graph = build_normalization_filter(_probe(720, 1280), RenderSettings())
    assert "gblur" not in graph
    assert "crop=1440:2560" in graph


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
