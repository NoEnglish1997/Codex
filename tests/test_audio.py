from __future__ import annotations

from pathlib import Path

import pytest

from auto_video_editor.media.audio import build_audio_plan, build_final_audio_filtergraph
from auto_video_editor.media.timeline import calculate_timeline
from auto_video_editor.models import (
    MusicShortPolicy,
    RenderJob,
    RenderSettings,
    SourceAudioMode,
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
