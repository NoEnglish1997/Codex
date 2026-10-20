from __future__ import annotations

from pathlib import Path

from auto_video_editor.media.validation import validate_render_job
from auto_video_editor.models import ProbeInfo, RenderJob, VideoItem


def _video(path: Path, duration: float = 3.0) -> VideoItem:
    path.write_bytes(b"placeholder")
    return VideoItem(path, path.name, ProbeInfo(path=path, duration_seconds=duration, has_video=True))


def test_empty_video_list_is_rejected(tmp_path):
    job = RenderJob((), None, None, None, tmp_path, "out.mp4")
    assert {issue.code for issue in validate_render_job(job)} == {"no_video"}


def test_short_video_is_rejected(tmp_path):
    item = _video(tmp_path / "short.mp4", 1.5)
    job = RenderJob((item,), None, None, None, tmp_path, "out.mp4")
    assert "video_too_short" in {issue.code for issue in validate_render_job(job)}


def test_chinese_space_paths_and_duplicate_items_are_allowed(tmp_path):
    item = _video(tmp_path / "中文 视频 (1).mp4")
    job = RenderJob((item, item), None, None, None, tmp_path, "成片.mp4")
    assert not [issue for issue in validate_render_job(job) if issue.severity.value == "error"]


def test_output_is_sanitized_and_never_overwritten(tmp_path):
    item = _video(tmp_path / "source.mp4")
    (tmp_path / "bad_name.mp4").write_bytes(b"existing")
    job = RenderJob((item,), None, None, None, tmp_path, "bad:name.mp4")
    codes = {issue.code for issue in validate_render_job(job)}
    assert {"output_name_sanitized", "output_exists"}.issubset(codes)


def test_missing_logo_is_rejected(tmp_path):
    item = _video(tmp_path / "source.mp4")
    job = RenderJob(
        (item,), None, None, None, tmp_path, "out.mp4", logo_path=tmp_path / "missing.png"
    )
    assert "logo_path" in {issue.code for issue in validate_render_job(job)}
