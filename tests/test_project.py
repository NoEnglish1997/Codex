from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_video_editor.models import OutputQuality, RenderSettings, VideoItem
from auto_video_editor.project import ProjectClip, ProjectDocument, ProjectStore


def test_project_round_trip_preserves_unicode_order_duplicates_and_settings(tmp_path: Path):
    source = tmp_path / "中文 素材.mp4"
    clip = VideoItem(source, source.name, trim_start_seconds=0.5, trim_end_seconds=2.75)
    document = ProjectDocument(
        clips=(ProjectClip.from_video_item(clip), ProjectClip.from_video_item(clip)),
        settings=RenderSettings(output_quality=OutputQuality.ULTRA, mirror_second_clip=False),
        cover_path=tmp_path / "封面.png",
        output_dir=tmp_path / "输出",
        output_filename="成片 01.mp4",
    )
    path = tmp_path / "项目.autocut.json"

    ProjectStore.save(path, document)
    loaded = ProjectStore.load(path)

    assert [item.source_path for item in loaded.clips] == [source, source]
    assert loaded.clips[0].trim_start_seconds == 0.5
    assert loaded.clips[0].trim_end_seconds == 2.75
    assert loaded.settings.output_quality == OutputQuality.ULTRA
    assert loaded.settings.mirror_second_clip is False
    assert loaded.cover_path == tmp_path / "封面.png"
    assert loaded.output_filename == "成片 01.mp4"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"format": "wrong", "version": 1, "clips": []},
        {"format": "autocut-studio-project", "version": 99, "clips": []},
        {
            "format": "autocut-studio-project",
            "version": 1,
            "clips": [{"source_path": "a.mp4", "trim_start_seconds": 3, "trim_end_seconds": 2}],
        },
    ),
)
def test_project_rejects_invalid_or_unknown_documents(tmp_path: Path, payload: dict):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        ProjectStore.load(path)
