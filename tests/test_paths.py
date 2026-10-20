from __future__ import annotations

from auto_video_editor.utils.paths import sanitize_output_filename, unique_path


def test_windows_filename_is_sanitized():
    assert sanitize_output_filename('bad<>:"/\\|?* name') == "bad_________ name.mp4"
    assert sanitize_output_filename("CON.mp4") == "_CON.mp4"


def test_unique_path_never_overwrites(tmp_path):
    original = tmp_path / "output.mp4"
    original.write_bytes(b"old")
    assert unique_path(original).name == "output_001.mp4"
