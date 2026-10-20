from __future__ import annotations

from pathlib import Path

import pytest

from auto_video_editor.media.batch import batch_output_filename, natural_sort_key, scan_batch_root


def _touch(folder: Path, name: str) -> Path:
    path = folder / name
    path.write_bytes(b"test")
    return path


def _valid_folder(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    for filename in ("片段10.mp4", "片段2.MP4", "封面.PNG", "字幕.srt", "配乐.MP3"):
        _touch(folder, filename)
    return folder


def test_scan_batch_root_naturally_sorts_folders_and_videos(tmp_path):
    source10 = _valid_folder(tmp_path, "任务10")
    source2 = _valid_folder(tmp_path, "任务2")

    result = scan_batch_root(tmp_path)

    assert not result.issues
    assert [item.source_dir for item in result.sources] == [source2, source10]
    assert [path.name for path in result.sources[0].video_paths] == ["片段2.MP4", "片段10.mp4"]


def test_scan_reports_invalid_folders_and_excludes_output_directory(tmp_path):
    output = _valid_folder(tmp_path, "输出")
    invalid = tmp_path / "缺素材"
    invalid.mkdir()
    _touch(invalid, "唯一视频.mp4")
    valid = _valid_folder(tmp_path, "有效")

    result = scan_batch_root(tmp_path, excluded_dir=output)

    assert [item.source_dir for item in result.sources] == [valid]
    assert len(result.issues) == 1
    assert result.issues[0].source_dir == invalid
    assert "至少需要 2 个" in result.issues[0].message
    assert "PNG 封面" in result.issues[0].message
    assert "SRT 字幕" in result.issues[0].message
    assert "MP3 背景音乐" in result.issues[0].message


def test_scan_requires_exactly_one_auxiliary_file(tmp_path):
    folder = _valid_folder(tmp_path, "重复封面")
    _touch(folder, "另一个.png")

    result = scan_batch_root(tmp_path)

    assert not result.sources
    assert "PNG 封面数量为 2" in result.issues[0].message


@pytest.mark.parametrize(
    ("prefix", "index", "expected"),
    [
        ("成片_", 1, "成片_1.mp4"),
        ("广告.mp4", 12, "广告12.mp4"),
        ("a:b", 2, "a_b2.mp4"),
        ("   ", 3, "成片_3.mp4"),
    ],
)
def test_batch_output_filename(prefix, index, expected):
    assert batch_output_filename(prefix, index) == expected


def test_batch_output_index_is_one_based():
    with pytest.raises(ValueError, match="从 1 开始"):
        batch_output_filename("成片_", 0)


def test_natural_sort_key_is_case_insensitive():
    names = [Path("B10"), Path("b2"), Path("A1")]
    assert [path.name for path in sorted(names, key=natural_sort_key)] == ["A1", "b2", "B10"]
