from __future__ import annotations

from fractions import Fraction

import pytest

from auto_video_editor.media.timeline import calculate_timeline


def test_three_clips_with_cover():
    plan = calculate_timeline([600, 600, 600], True)
    assert plan.body_frames == 1680
    assert plan.total_frames == 1685
    assert plan.transition_offsets_frames == (540, 1080)
    assert plan.duration == Fraction(1685, 60)
    assert plan.subtitle_offset_seconds == pytest.approx(5 / 60)


def test_three_clips_without_cover():
    assert calculate_timeline([600, 600, 600], False).total_frames == 1680


def test_single_clip_has_no_transition():
    plan = calculate_timeline([600], True)
    assert plan.total_frames == 605
    assert plan.transition_offsets_frames == ()


def test_two_short_valid_clips():
    plan = calculate_timeline([120, 120], True)
    assert plan.total_frames == 185
    assert plan.transition_offsets_frames == (60,)


@pytest.mark.parametrize("counts", [[], [0], [60, 120]])
def test_invalid_frame_counts(counts):
    with pytest.raises(ValueError):
        calculate_timeline(counts, False)
