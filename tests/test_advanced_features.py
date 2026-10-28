from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from auto_video_editor.media.clips import (
    effective_clip_frames,
    effective_clip_range,
    trailing_black_start,
)
from auto_video_editor.media.estimates import estimate_export
from auto_video_editor.models import OutputQuality, ProbeInfo, RenderSettings, VideoItem


def _item(tmp_path: Path, duration: float = 10.0) -> VideoItem:
    path = tmp_path / "素材.mp4"
    path.write_bytes(b"x")
    probe = ProbeInfo(
        path,
        duration,
        1280,
        720,
        1280,
        720,
        Fraction(30, 1),
        Fraction(30, 1),
        has_video=True,
    )
    return VideoItem(path, path.name, probe, trim_start_seconds=1.0, trim_end_seconds=8.0)


def test_per_clip_trim_and_global_limit_use_integer_output_frames(tmp_path):
    item = _item(tmp_path)
    settings = RenderSettings(clip_max_duration_seconds=3.5)
    assert effective_clip_range(item, item.probe, settings) == (1.0, 4.5)
    assert effective_clip_frames(item, item.probe, settings) == 210


def test_invalid_trim_is_rejected(tmp_path):
    item = _item(tmp_path)
    item = VideoItem(item.source_path, item.display_name, item.probe, 5.0, 4.0)
    with pytest.raises(ValueError, match="结束时间"):
        effective_clip_range(item, item.probe, RenderSettings())


def test_trailing_black_parser_only_uses_range_at_end():
    stderr = (
        "black_start:1 black_end:1.4 black_duration:0.4\n"
        "black_start:8.5 black_end:10 black_duration:1.5\n"
    )
    assert trailing_black_start(stderr, 10.0) == 8.5
    assert trailing_black_start(stderr, 12.0) is None


def test_export_estimate_reports_size_disk_and_low_resolution_warning(tmp_path):
    item = _item(tmp_path, 10.0)
    estimate = estimate_export(
        (item,),
        RenderSettings(output_quality=OutputQuality.BITRATE_16M),
        has_cover=True,
        output_dir=tmp_path,
    )
    assert estimate.size_is_targeted
    assert estimate.total_frames == 425
    assert 13_000_000 < estimate.estimated_bytes < 15_000_000
    assert estimate.available_free_bytes is not None
    assert any("低于1080" in warning for warning in estimate.warnings)
