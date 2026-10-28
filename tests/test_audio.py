from __future__ import annotations

from pathlib import Path

import pytest

from auto_video_editor.media.audio import (
    build_audio_plan,
    build_final_audio_filtergraph,
    build_single_pass_audio_filtergraph,
)
from auto_video_editor.media.timeline import calculate_timeline
from auto_video_editor.models import (
    MusicShortPolicy,
    RenderJob,
    RenderSettings,
    SourceAudioMode,
    TransitionType,
    VideoItem,
)


@pytest.mark.parametrize(
    ("source_mode", "music", "expected_source", "expected_music"),
    [
        (SourceAudioMode.MUTE, None, False, False),
        (SourceAudioMode.MIX, None, True, False),
        (SourceAudioMode.MUTE, Path("music.mp3"), False, True),
        (SourceAudioMode.MIX, Path("music.mp3"), True, True),
    ],
)
def test_audio_plan_covers_four_combinations(source_mode, music, expected_source, expected_music, tmp_path):
    settings = RenderSettings(source_audio_mode=source_mode)
    job = RenderJob((VideoItem(Path("v.mp4"), "v"),), None, None, music, tmp_path, "out.mp4", settings)
    timeline = calculate_timeline([600], True)
    plan = build_audio_plan(job, timeline)
    assert plan.include_source is expected_source
    assert plan.include_music is expected_music
    assert plan.source_delay_samples == 4000
    if expected_music:
        assert plan.fadeout_start_seconds == pytest.approx(timeline.duration_seconds - 1)


def test_short_music_policy_changes_looping(tmp_path):
    loop_job = RenderJob(
        (VideoItem(Path("v.mp4"), "v"),), None, None, Path("m.mp3"), tmp_path, "o.mp4",
        RenderSettings(music_short_policy=MusicShortPolicy.LOOP),
    )
    silence_job = RenderJob(
        loop_job.video_items, None, None, loop_job.music_path, tmp_path, "o.mp4",
        RenderSettings(music_short_policy=MusicShortPolicy.SILENCE),
    )
    timeline = calculate_timeline([120], False)
    assert build_audio_plan(loop_job, timeline).loop_music
    plan = build_audio_plan(silence_job, timeline)
    assert not plan.loop_music
    graph, label = build_final_audio_filtergraph(plan, source_input_index=None, music_input_index=1)
    assert "apad" in graph
    assert "volume=0.350000" in graph
    assert label == "[aout]"


def test_single_pass_audio_uses_original_tracks_silence_crossfade_and_music(tmp_path):
    settings = RenderSettings(source_audio_mode=SourceAudioMode.MIX)
    job = RenderJob(
        (VideoItem(Path("first.mp4"), "first"), VideoItem(Path("silent.mp4"), "silent")),
        Path("cover.png"),
        None,
        Path("music.mp3"),
        tmp_path,
        "out.mp4",
        settings,
    )
    timeline = calculate_timeline([120, 120], True)
    plan = build_audio_plan(job, timeline)

    graph, label = build_single_pass_audio_filtergraph(
        plan,
        timeline,
        source_input_indices=(0, None),
        music_input_index=3,
    )

    assert "[0:a]aresample=48000" in graph
    assert "anullsrc=r=48000:cl=stereo" in graph
    assert "acrossfade=d=1.000000000" in graph
    assert "adelay=delays=4000S:all=1" in graph
    assert "[3:a]aresample=48000" in graph
    assert "amix=inputs=2" in graph
    assert label == "[aout]"


def test_audio_trim_normalization_ducking_fades_and_no_transition_concat(tmp_path):
    settings = RenderSettings(
        source_audio_mode=SourceAudioMode.MIX,
        transition_type=TransitionType.NONE,
        transition_frames=0,
        normalize_audio=True,
        duck_music_under_source=True,
        music_fadein_seconds=0.4,
        music_fadeout_seconds=0.6,
    )
    job = RenderJob(
        (VideoItem(Path("a.mp4"), "a"), VideoItem(Path("b.mp4"), "b")),
        None, None, Path("music.mp3"), tmp_path, "out.mp4", settings,
    )
    timeline = calculate_timeline([120, 120], False, transition_frames=0)
    plan = build_audio_plan(job, timeline)
    graph, _ = build_single_pass_audio_filtergraph(
        plan,
        timeline,
        source_input_indices=(0, 1),
        music_input_index=2,
        clip_ranges=((0.2, 2.2), (0.4, 2.4)),
    )
    assert "atrim=start=0.200000000:end=2.200000000" in graph
    assert "concat=n=2:v=0:a=1" in graph
    assert "loudnorm=I=-16.0" in graph
    assert "afade=t=in:st=0:d=0.400000000" in graph
    assert "sidechaincompress=" in graph
