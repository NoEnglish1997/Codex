from __future__ import annotations

from auto_video_editor.media.watcher import FolderStabilityTracker


def test_watcher_only_returns_new_folder_after_two_stable_polls(tmp_path):
    existing = tmp_path / "已有"
    existing.mkdir()
    (existing / "a.mp4").write_bytes(b"old")
    tracker = FolderStabilityTracker()
    tracker.arm(tmp_path)

    new = tmp_path / "新增"
    new.mkdir()
    (new / "a.mp4").write_bytes(b"1")
    assert tracker.poll(tmp_path) == ()
    (new / "a.mp4").write_bytes(b"12")
    assert tracker.poll(tmp_path) == ()
    assert tracker.poll(tmp_path) == (new.resolve(),)
    tracker.mark_processed((new,))
    assert tracker.poll(tmp_path) == ()
