from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from pathlib import Path

import pytest

from auto_video_editor.media.ffmpeg_locator import detect_capabilities
from auto_video_editor.media.progress import CancellationToken
from auto_video_editor.media.renderer import RenderCancelled, Renderer
from auto_video_editor.models import (
    CanvasMode,
    CanvasPosition,
    InterpolationMode,
    MusicShortPolicy,
    LogoMotion,
    OutputQuality,
    RenderJob,
    RenderSettings,
    SourceAudioMode,
    SubtitleStyle,
    TransitionType,
    VideoEncoder,
    VideoItem,
)


def _load_media_factory():
    path = Path(__file__).parents[1] / "scripts" / "create_test_media.py"
    spec = importlib.util.spec_from_file_location("create_test_media", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_test_media


def _pixel_samples(ffmpeg: Path, video: Path, frames: tuple[int, ...], x: int, y: int) -> list[bytes]:
    select = "+".join(f"eq(n\\,{frame})" for frame in frames)
    args = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"select={select},crop=2:2:{x}:{y},format=rgb24", "-fps_mode", "passthrough",
        "-frames:v", str(len(frames)), "-f", "rawvideo", "pipe:1",
    ]
    process = subprocess.Popen(args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")
    size = 2 * 2 * 3
    assert len(stdout) == size * len(frames)
    return [stdout[index * size:(index + 1) * size] for index in range(len(frames))]


def _is_red(sample: bytes) -> bool:
    pixels = [sample[index:index + 3] for index in range(0, len(sample), 3)]
    red = sum(pixel[0] for pixel in pixels) / len(pixels)
    green = sum(pixel[1] for pixel in pixels) / len(pixels)
    blue = sum(pixel[2] for pixel in pixels) / len(pixels)
    return red > 180 and red > green + 100 and red > blue + 100


def _is_blue(sample: bytes) -> bool:
    pixels = [sample[index:index + 3] for index in range(0, len(sample), 3)]
    red = sum(pixel[0] for pixel in pixels) / len(pixels)
    green = sum(pixel[1] for pixel in pixels) / len(pixels)
    blue = sum(pixel[2] for pixel in pixels) / len(pixels)
    return blue > 180 and blue > red + 100 and blue > green + 100


def _video_timestamps(ffprobe: Path, video: Path) -> list[float]:
    args = [
        str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(video),
    ]
    process = subprocess.Popen(args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")
    payload = json.loads(stdout.decode("utf-8"))
    return [
        float(frame["best_effort_timestamp_time"])
        for frame in payload.get("frames", [])
        if "best_effort_timestamp_time" in frame
    ]


@pytest.fixture(scope="module")
def ffmpeg_capabilities():
    try:
        capabilities = detect_capabilities()
    except Exception as exc:
        pytest.skip(f"FFmpeg unavailable: {exc}")
    if not capabilities.ready:
        pytest.skip(f"FFmpeg missing required features: {capabilities.missing_required}")
    return capabilities


@pytest.mark.integration
def test_real_three_clip_render_with_cover_subtitles_music_and_audio(tmp_path, ffmpeg_capabilities):
    create_media = _load_media_factory()
    media = create_media(tmp_path / "中文 素材", str(ffmpeg_capabilities.ffmpeg_path), duration=2.2)
    output_dir = tmp_path / "输出 目录"
    settings = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        source_audio_mode=SourceAudioMode.MIX,
        music_short_policy=MusicShortPolicy.LOOP,
        video_encoder=VideoEncoder.X264,
        output_quality=OutputQuality.BITRATE_12M,
        logo_scale_percent=150,
        logo_opacity_percent=80,
    )
    job = RenderJob(
        video_items=(
            VideoItem(media["landscape"], media["landscape"].name),
            VideoItem(media["portrait"], media["portrait"].name),
            VideoItem(media["square"], media["square"].name),
        ),
        cover_path=media["cover"],
        subtitle_path=media["subtitle"],
        music_path=media["music"],
        output_dir=output_dir,
        output_filename="集成:成片.mp4",
        settings=settings,
        logo_path=media["logo"],
    )
    progress: list[tuple[str, int]] = []
    renderer = Renderer(ffmpeg_capabilities, cache_root=tmp_path / "cache")
    result = renderer.render(job, CancellationToken(), lambda stage, value: progress.append((stage, value)))

    assert result.output_path.is_file()
    assert result.output_path.name == "集成_成片.mp4"
    assert result.cover_path and result.cover_path.is_file()
    assert result.report_path.is_file()
    assert result.verification.valid
    assert result.verification.probe is not None
    assert result.verification.probe.frame_count == result.timeline.total_frames
    assert result.verification.probe.has_audio
    assert progress[-1] == ("完成", 100)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["source_order"] == [
        media["landscape"].name,
        media["portrait"].name,
        media["square"].name,
    ]
    assert report["timeline"]["cover_frames"] == 5
    assert report["logo"] == media["logo"].name
    assert report["settings"]["mirrored_clip_indices"] == [2]
    assert report["settings"]["logo_scale_percent"] == 150
    assert report["settings"]["logo_opacity_percent"] == 80
    assert report["settings"]["output_quality"] == "bitrate_12m"
    assert report["pipeline"] == "single_pass"
    assert report["video_encode_passes"] == 1
    render_log = result.log_path.read_text(encoding="utf-8")
    assert "单次视频编码模式" in render_log
    assert render_log.count("'-c:v', 'libx264'") == 1
    assert "'-minrate', '12M', '-maxrate', '12M'" in render_log
    assert "clip_0001.mp4" not in render_log
    expected_video_bytes = result.timeline.duration_seconds * 12_000_000 / 8
    assert result.output_path.stat().st_size >= expected_video_bytes * 0.8

    pure_second_body_frame = report["timeline"]["transition_offsets_frames"][0] + 65
    pure_second_output_frame = report["timeline"]["cover_frames"] + pure_second_body_frame
    (mirrored_left,) = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (pure_second_output_frame,),
        360,
        1280,
    )
    (mirrored_right,) = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (pure_second_output_frame,),
        1080,
        1280,
    )
    assert _is_blue(mirrored_left)
    assert _is_red(mirrored_right)

    first, fifth, sixth = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (0, 4, 5),
        720,
        1280,
    )
    distance_same_cover = sum(abs(a - b) for a, b in zip(first, fifth))
    distance_to_first_video = sum(abs(a - b) for a, b in zip(fifth, sixth))
    assert distance_same_cover < 40
    assert distance_to_first_video > 80
    before_logo, logo_at_start = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (3, 4),
        1272,
        128,
    )
    assert not _is_red(before_logo)
    assert _is_red(logo_at_start)
    (logo_at_end,) = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (result.timeline.total_frames - 1,),
        168,
        2432,
    )
    assert _is_red(logo_at_end)
    (corner,) = _pixel_samples(
        ffmpeg_capabilities.ffmpeg_path,
        result.output_path,
        (60,),
        0,
        0,
    )
    assert sum(corner) > 20, "blurred background must not leave a pure black border"


@pytest.mark.integration
def test_cancelled_render_cleans_temporary_files(tmp_path, ffmpeg_capabilities):
    create_media = _load_media_factory()
    media = create_media(tmp_path / "media", str(ffmpeg_capabilities.ffmpeg_path), duration=3.0)
    output_dir = tmp_path / "cancelled-output"
    token = CancellationToken()
    job = RenderJob(
        (VideoItem(media["landscape"], "long.mp4"),),
        None,
        None,
        None,
        output_dir,
        "cancelled.mp4",
        RenderSettings(interpolation_mode=InterpolationMode.MOTION, video_encoder=VideoEncoder.X264),
    )
    timer = threading.Timer(0.15, token.cancel)
    timer.start()
    try:
        with pytest.raises(RenderCancelled):
            Renderer(ffmpeg_capabilities, cache_root=tmp_path / "cancel-cache").render(job, token)
    finally:
        timer.cancel()
    assert not list(output_dir.glob("*.mp4"))
    assert not list((tmp_path / "cancel-cache").glob("job_*"))


@pytest.mark.integration
def test_real_motion_interpolation_without_optional_tracks(tmp_path, ffmpeg_capabilities):
    create_media = _load_media_factory()
    media = create_media(tmp_path / "motion-media", str(ffmpeg_capabilities.ffmpeg_path), duration=2.1)
    output_dir = tmp_path / "motion-output"
    job = RenderJob(
        (VideoItem(media["portrait"], media["portrait"].name),),
        None,
        None,
        None,
        output_dir,
        "motion.mp4",
        RenderSettings(
            interpolation_mode=InterpolationMode.MOTION,
            source_audio_mode=SourceAudioMode.MUTE,
            video_encoder=VideoEncoder.X264,
        ),
    )
    from auto_video_editor.media.ffprobe import probe_media

    source_probe = probe_media(media["portrait"], ffmpeg_capabilities.ffprobe_path)
    result = Renderer(ffmpeg_capabilities, cache_root=tmp_path / "motion-cache").render(
        job, CancellationToken()
    )
    assert result.verification.valid
    assert result.verification.probe is not None
    assert result.verification.probe.avg_frame_rate.numerator == 60
    assert result.verification.probe.avg_frame_rate.denominator == 1
    assert not result.verification.probe.has_audio
    assert result.timeline.cover_frames == 0
    assert result.timeline.frame_counts == (int(source_probe.duration_seconds * 60 + 0.5),)


@pytest.mark.integration
def test_real_advanced_non_ai_pipeline_with_trim_cover_audio_and_custom_overlays(
    tmp_path, ffmpeg_capabilities
):
    create_media = _load_media_factory()
    media = create_media(tmp_path / "advanced-media", str(ffmpeg_capabilities.ffmpeg_path), duration=2.6)
    settings = RenderSettings(
        interpolation_mode=InterpolationMode.FAST,
        source_audio_mode=SourceAudioMode.MIX,
        video_encoder=VideoEncoder.X264,
        output_quality=OutputQuality.STANDARD,
        transition_type=TransitionType.WIPE_LEFT,
        transition_frames=30,
        cover_frames=18,
        cover_fadein_seconds=0.1,
        cover_zoom_percent=105,
        cover_title="结构安全",
        canvas_mode=CanvasMode.SOLID,
        canvas_position=CanvasPosition.CUSTOM,
        canvas_x_percent=30,
        canvas_y_percent=60,
        sharpen_amount=0.7,
        denoise_strength=1.0,
        brightness=0.02,
        contrast=1.05,
        saturation=1.08,
        shadow_boost=0.2,
        highlight_protection=0.2,
        normalize_audio=True,
        duck_music_under_source=True,
        music_fadein_seconds=0.1,
        music_fadeout_seconds=0.2,
        logo_motion=LogoMotion.CUSTOM,
        logo_start_frame=8,
        logo_end_frame=180,
        logo_start_x_percent=10,
        logo_start_y_percent=10,
        logo_end_x_percent=80,
        logo_end_y_percent=80,
        logo_fade_seconds=0.1,
        subtitle_style=SubtitleStyle(
            background_opacity_percent=45,
            max_chars_per_line=8,
            highlight_words=("字幕",),
        ),
    )
    job = RenderJob(
        (
            VideoItem(media["landscape"], "a.mp4", trim_start_seconds=0.1, trim_end_seconds=2.4),
            VideoItem(media["portrait"], "b.mp4", trim_start_seconds=0.2, trim_end_seconds=2.5),
        ),
        media["cover"],
        media["subtitle"],
        media["music"],
        tmp_path / "advanced-output",
        "advanced.mp4",
        settings,
        media["logo"],
    )
    result = Renderer(ffmpeg_capabilities, cache_root=tmp_path / "advanced-cache").render(
        job, CancellationToken()
    )
    assert result.verification.valid
    assert result.timeline.frame_counts == (138, 138)
    assert result.timeline.total_frames == 264
    assert result.cover_path and result.cover_path.is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["settings"]["transition_type"] == "wipeleft"
    assert report["settings"]["normalize_audio"] is True
    assert report["settings"]["duck_music_under_source"] is True
    assert report["settings"]["logo_motion"] == "custom"
    log = result.log_path.read_text(encoding="utf-8")
    assert log.count("'-c:v', 'libx264'") == 1


def test_nvenc_fallback_detection_is_limited_to_initialization_errors():
    assert Renderer._is_nvenc_initialization_failure("Cannot load libcuda.so.1")
    assert Renderer._is_nvenc_initialization_failure("Error while opening encoder")
    assert not Renderer._is_nvenc_initialization_failure("Error initializing filter 'subtitles'")
    assert not Renderer._is_nvenc_initialization_failure("Invalid data found when processing input")


@pytest.mark.integration
def test_rotation_metadata_is_autorotated_once(tmp_path, ffmpeg_capabilities):
    base = tmp_path / "rotation-base.mp4"
    rotated = tmp_path / "手机旋转 90.mp4"
    create_args = [
        str(ffmpeg_capabilities.ffmpeg_path), "-hide_banner", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=320x180:rate=30:duration=2.1", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-an", str(base),
    ]
    process = subprocess.Popen(create_args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")
    rotate_args = [
        str(ffmpeg_capabilities.ffmpeg_path), "-hide_banner", "-y", "-display_rotation:v:0", "90",
        "-i", str(base), "-c", "copy", str(rotated),
    ]
    process = subprocess.Popen(rotate_args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")
    from auto_video_editor.media.ffprobe import probe_media

    source_probe = probe_media(rotated, ffmpeg_capabilities.ffprobe_path)
    assert source_probe.rotation == 90
    assert (source_probe.display_width, source_probe.display_height) == (180, 320)
    job = RenderJob(
        (VideoItem(rotated, rotated.name),),
        None,
        None,
        None,
        tmp_path / "rotation-output",
        "rotation.mp4",
        RenderSettings(interpolation_mode=InterpolationMode.FAST, video_encoder=VideoEncoder.X264),
    )
    result = Renderer(ffmpeg_capabilities, cache_root=tmp_path / "rotation-cache").render(
        job, CancellationToken()
    )
    assert result.verification.valid
    assert result.verification.probe is not None
    assert (result.verification.probe.width, result.verification.probe.height) == (1440, 2560)


@pytest.mark.integration
def test_odd_vfr_nonzero_pts_source_is_normalized(tmp_path, ffmpeg_capabilities):
    source = tmp_path / "奇数尺寸 VFR 非零起点.mkv"
    args = [
        str(ffmpeg_capabilities.ffmpeg_path), "-hide_banner", "-y", "-f", "lavfi", "-i",
        "testsrc=size=321x181:rate=24:duration=2.4", "-vf",
        "select='not(mod(n,2))+not(mod(n,3))',setpts=PTS+1/TB", "-fps_mode", "vfr",
        "-c:v", "ffv1", "-pix_fmt", "yuv444p", "-an", str(source),
    ]
    process = subprocess.Popen(args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")
    from auto_video_editor.media.ffprobe import probe_media

    source_probe = probe_media(source, ffmpeg_capabilities.ffprobe_path)
    assert (source_probe.width, source_probe.height) == (321, 181)
    assert source_probe.start_time_seconds == pytest.approx(1.0)
    timestamps = _video_timestamps(ffmpeg_capabilities.ffprobe_path, source)
    frame_intervals = {round(current - previous, 3) for previous, current in zip(timestamps, timestamps[1:])}
    assert len(frame_intervals) > 1, "source fixture must contain variable frame intervals"
    job = RenderJob(
        (VideoItem(source, source.name),),
        None,
        None,
        None,
        tmp_path / "odd-output",
        "odd.mp4",
        RenderSettings(interpolation_mode=InterpolationMode.FAST, video_encoder=VideoEncoder.X264),
    )
    result = Renderer(ffmpeg_capabilities, cache_root=tmp_path / "odd-cache").render(
        job, CancellationToken()
    )
    assert result.verification.valid
    assert result.timeline.frame_counts == (int(source_probe.duration_seconds * 60 + 0.5),)
