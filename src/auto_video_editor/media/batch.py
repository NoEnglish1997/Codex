from __future__ import annotations

import re
import json
import hashlib
import fnmatch
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import RenderSettings, VideoItem, VideoSortMode
from ..presets import render_settings_from_mapping
from ..utils.paths import sanitize_output_filename


@dataclass(frozen=True)
class BatchSource:
    source_dir: Path
    video_paths: tuple[Path, ...]
    cover_path: Path
    subtitle_path: Path
    music_path: Path
    folder_config: dict[str, Any]


@dataclass(frozen=True)
class BatchScanIssue:
    source_dir: Path
    message: str


@dataclass(frozen=True)
class BatchScanResult:
    sources: tuple[BatchSource, ...]
    issues: tuple[BatchScanIssue, ...]


def settings_for_batch_source(base: RenderSettings, source: BatchSource) -> RenderSettings:
    raw = source.folder_config.get("settings", {})
    return render_settings_from_mapping(raw, base)


def video_items_for_batch_source(source: BatchSource) -> tuple[VideoItem, ...]:
    raw_trims = source.folder_config.get("trims", {})
    trims = raw_trims if isinstance(raw_trims, dict) else {}
    items: list[VideoItem] = []
    for path in source.video_paths:
        raw = trims.get(path.name, trims.get(path.name.casefold(), {}))
        if not isinstance(raw, dict):
            raw = {}
        try:
            start = max(0.0, float(raw.get("start", 0.0)))
        except (TypeError, ValueError):
            start = 0.0
        try:
            end = max(0.0, float(raw.get("end", 0.0)))
        except (TypeError, ValueError):
            end = 0.0
        items.append(VideoItem(path, path.name, trim_start_seconds=start, trim_end_seconds=end))
    return tuple(items)


def natural_sort_key(path: Path) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    )


def batch_output_filename(
    prefix: str,
    index: int,
    *,
    folder_name: str = "",
    template: str = "{prefix}{index}.mp4",
    date_text: str | None = None,
) -> str:
    """Build the deterministic output name for a one-based batch item."""
    if index < 1:
        raise ValueError("批量输出序号必须从 1 开始")
    clean_prefix = prefix.strip()
    if clean_prefix.lower().endswith(".mp4"):
        clean_prefix = clean_prefix[:-4].rstrip()
    if not clean_prefix:
        clean_prefix = "成片_"
    values = {
        "prefix": clean_prefix,
        "index": index,
        "folder": folder_name,
        "date": date_text or datetime.now().strftime("%Y%m%d"),
    }
    pattern = template.strip() or "{prefix}{index}.mp4"
    try:
        rendered = pattern.format_map(values)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"输出命名模板无效：{exc}") from exc
    if not rendered.lower().endswith(".mp4"):
        rendered += ".mp4"
    return sanitize_output_filename(rendered)


def _single_file(files: list[Path], suffix: str, label: str) -> tuple[Path | None, str | None]:
    matches = sorted((path for path in files if path.suffix.lower() == suffix), key=natural_sort_key)
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"缺少 {label}（需要恰好 1 个 {suffix} 文件）"
    return None, f"{label}数量为 {len(matches)}（需要恰好 1 个 {suffix} 文件）"


def _sort_paths(paths: list[Path], mode: VideoSortMode, *, seed: str = "") -> list[Path]:
    if mode == VideoSortMode.CREATED:
        return sorted(paths, key=lambda path: (path.stat().st_ctime_ns, natural_sort_key(path)))
    if mode == VideoSortMode.MODIFIED:
        return sorted(paths, key=lambda path: (path.stat().st_mtime_ns, natural_sort_key(path)))
    if mode == VideoSortMode.RANDOM:
        return sorted(
            paths,
            key=lambda path: hashlib.sha256(f"{seed}\0{path.name}".encode("utf-8")).digest(),
        )
    return sorted(paths, key=natural_sort_key)


def _ordered_from_config(paths: list[Path], config: dict[str, Any]) -> list[Path]:
    requested = config.get("video_order", [])
    if not isinstance(requested, list):
        raise ValueError("config.json 的 video_order 必须是文件名数组")
    by_name = {path.name.casefold(): path for path in paths}
    ordered: list[Path] = []
    for raw_name in requested:
        name = str(raw_name).casefold()
        if name not in by_name:
            raise ValueError(f"config.json 指定的视频不存在：{raw_name}")
        path = by_name[name]
        if path not in ordered:
            ordered.append(path)
    ordered.extend(path for path in sorted(paths, key=natural_sort_key) if path not in ordered)
    return ordered


def _pin_first_last(paths: list[Path], first_pattern: str, last_pattern: str) -> list[Path]:
    result = list(paths)
    if first_pattern:
        match = next((path for path in result if fnmatch.fnmatch(path.name.casefold(), first_pattern.casefold())), None)
        if match:
            result.remove(match)
            result.insert(0, match)
    if last_pattern:
        match = next((path for path in result if fnmatch.fnmatch(path.name.casefold(), last_pattern.casefold())), None)
        if match:
            result.remove(match)
            result.append(match)
    return result


def _load_folder_config(files: list[Path]) -> dict[str, Any]:
    matches = [path for path in files if path.name.casefold() == "config.json"]
    if not matches:
        return {}
    try:
        raw = json.loads(matches[0].read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"config.json 无法读取：{exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config.json 根节点必须是对象")
    return raw


def scan_batch_root(
    root: Path,
    *,
    excluded_dir: Path | None = None,
    sort_mode: VideoSortMode = VideoSortMode.NATURAL,
    first_pattern: str = "",
    last_pattern: str = "",
) -> BatchScanResult:
    root = root.expanduser()
    if not root.is_dir():
        return BatchScanResult((), (BatchScanIssue(root, "批量素材总目录不存在或不是文件夹"),))

    excluded = excluded_dir.expanduser().resolve(strict=False) if excluded_dir else None
    try:
        folders = _sort_paths(
            list(
                path
                for path in root.iterdir()
                if path.is_dir() and (excluded is None or path.resolve(strict=False) != excluded)
            ),
            sort_mode,
            seed=str(root),
        )
    except OSError as exc:
        return BatchScanResult((), (BatchScanIssue(root, f"无法读取批量素材总目录：{exc}"),))
    if not folders:
        return BatchScanResult((), (BatchScanIssue(root, "总目录中没有可处理的子文件夹"),))

    sources: list[BatchSource] = []
    issues: list[BatchScanIssue] = []
    for folder in folders:
        try:
            files = [path for path in folder.iterdir() if path.is_file()]
        except OSError as exc:
            issues.append(BatchScanIssue(folder, f"无法读取文件夹：{exc}"))
            continue

        video_files = [path for path in files if path.suffix.lower() == ".mp4"]
        errors: list[str] = []
        try:
            folder_config = _load_folder_config(files)
        except ValueError as exc:
            folder_config = {}
            errors.append(str(exc))
        try:
            if sort_mode == VideoSortMode.CONFIG:
                ordered = _ordered_from_config(video_files, folder_config)
            else:
                ordered = _sort_paths(video_files, sort_mode, seed=str(folder))
            config_first = str(folder_config.get("first_video", first_pattern) or "")
            config_last = str(folder_config.get("last_video", last_pattern) or "")
            videos = tuple(_pin_first_last(ordered, config_first, config_last))
        except (OSError, ValueError) as exc:
            videos = tuple(sorted(video_files, key=natural_sort_key))
            errors.append(str(exc))
        if len(videos) < 2:
            errors.append(f"MP4 视频数量为 {len(videos)}（至少需要 2 个）")
        cover, error = _single_file(files, ".png", "PNG 封面")
        if error:
            errors.append(error)
        subtitle, error = _single_file(files, ".srt", "SRT 字幕")
        if error:
            errors.append(error)
        music, error = _single_file(files, ".mp3", "MP3 背景音乐")
        if error:
            errors.append(error)
        if errors:
            issues.append(BatchScanIssue(folder, "；".join(errors)))
            continue
        assert cover is not None and subtitle is not None and music is not None
        sources.append(BatchSource(folder, videos, cover, subtitle, music, folder_config))

    return BatchScanResult(tuple(sources), tuple(issues))
