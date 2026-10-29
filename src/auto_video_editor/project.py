from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import RenderSettings, VideoItem
from .presets import render_settings_from_mapping, render_settings_to_mapping


PROJECT_FORMAT = "autocut-studio-project"
PROJECT_VERSION = 1


@dataclass(frozen=True)
class ProjectClip:
    source_path: Path
    trim_start_seconds: float = 0.0
    trim_end_seconds: float = 0.0

    @classmethod
    def from_video_item(cls, item: VideoItem) -> "ProjectClip":
        return cls(item.source_path, item.trim_start_seconds, item.trim_end_seconds)


@dataclass(frozen=True)
class ProjectDocument:
    clips: tuple[ProjectClip, ...]
    settings: RenderSettings
    cover_path: Path | None = None
    subtitle_path: Path | None = None
    music_path: Path | None = None
    logo_path: Path | None = None
    output_dir: Path | None = None
    output_filename: str = "edited_video.mp4"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "format": PROJECT_FORMAT,
            "version": PROJECT_VERSION,
            "clips": [
                {
                    "source_path": str(clip.source_path),
                    "trim_start_seconds": clip.trim_start_seconds,
                    "trim_end_seconds": clip.trim_end_seconds,
                }
                for clip in self.clips
            ],
            "assets": {
                "cover": str(self.cover_path) if self.cover_path else "",
                "subtitle": str(self.subtitle_path) if self.subtitle_path else "",
                "music": str(self.music_path) if self.music_path else "",
                "logo": str(self.logo_path) if self.logo_path else "",
            },
            "output": {
                "directory": str(self.output_dir) if self.output_dir else "",
                "filename": self.output_filename,
            },
            "settings": render_settings_to_mapping(self.settings),
        }

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProjectDocument":
        if data.get("format") != PROJECT_FORMAT:
            raise ValueError("不是有效的 AutoCut Studio 项目文件。")
        if data.get("version") != PROJECT_VERSION:
            raise ValueError(f"不支持的项目版本：{data.get('version')!r}")
        raw_clips = data.get("clips")
        if not isinstance(raw_clips, list):
            raise ValueError("项目中的 clips 字段无效。")
        clips: list[ProjectClip] = []
        for raw in raw_clips:
            if not isinstance(raw, dict) or not raw.get("source_path"):
                raise ValueError("项目包含无效的素材记录。")
            start = max(0.0, float(raw.get("trim_start_seconds", 0.0)))
            end = max(0.0, float(raw.get("trim_end_seconds", 0.0)))
            if end > 0 and end <= start:
                raise ValueError(f"素材裁剪范围无效：{raw['source_path']}")
            clips.append(ProjectClip(Path(str(raw["source_path"])), start, end))
        assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
        output = data.get("output") if isinstance(data.get("output"), dict) else {}

        def optional_path(value: object) -> Path | None:
            text = str(value or "").strip()
            return Path(text) if text else None

        return cls(
            clips=tuple(clips),
            settings=render_settings_from_mapping(data.get("settings", {})),
            cover_path=optional_path(assets.get("cover")),
            subtitle_path=optional_path(assets.get("subtitle")),
            music_path=optional_path(assets.get("music")),
            logo_path=optional_path(assets.get("logo")),
            output_dir=optional_path(output.get("directory")),
            output_filename=str(output.get("filename") or "edited_video.mp4"),
        )


class ProjectStore:
    """Atomic UTF-8 project persistence with a versioned JSON format."""

    @staticmethod
    def save(path: Path, document: ProjectDocument) -> None:
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.to_mapping(), ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def load(path: Path) -> ProjectDocument:
        try:
            data = json.loads(path.expanduser().read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取项目文件：{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("项目文件顶层必须是 JSON 对象。")
        return ProjectDocument.from_mapping(data)
