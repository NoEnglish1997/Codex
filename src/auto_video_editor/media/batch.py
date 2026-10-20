from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..utils.paths import sanitize_output_filename


@dataclass(frozen=True)
class BatchSource:
    source_dir: Path
    video_paths: tuple[Path, ...]
    cover_path: Path
    subtitle_path: Path
    music_path: Path


@dataclass(frozen=True)
class BatchScanIssue:
    source_dir: Path
    message: str


@dataclass(frozen=True)
class BatchScanResult:
    sources: tuple[BatchSource, ...]
    issues: tuple[BatchScanIssue, ...]


def natural_sort_key(path: Path) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    )


def batch_output_filename(prefix: str, index: int) -> str:
    """Build the deterministic output name for a one-based batch item."""
    if index < 1:
        raise ValueError("批量输出序号必须从 1 开始")
    clean_prefix = prefix.strip()
    if clean_prefix.lower().endswith(".mp4"):
        clean_prefix = clean_prefix[:-4].rstrip()
    if not clean_prefix:
        clean_prefix = "成片_"
    return sanitize_output_filename(f"{clean_prefix}{index}.mp4")


def _single_file(files: list[Path], suffix: str, label: str) -> tuple[Path | None, str | None]:
    matches = sorted((path for path in files if path.suffix.lower() == suffix), key=natural_sort_key)
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"缺少 {label}（需要恰好 1 个 {suffix} 文件）"
    return None, f"{label}数量为 {len(matches)}（需要恰好 1 个 {suffix} 文件）"


def scan_batch_root(root: Path, *, excluded_dir: Path | None = None) -> BatchScanResult:
    root = root.expanduser()
    if not root.is_dir():
        return BatchScanResult((), (BatchScanIssue(root, "批量素材总目录不存在或不是文件夹"),))

    excluded = excluded_dir.expanduser().resolve(strict=False) if excluded_dir else None
    try:
        folders = sorted(
            (
                path
                for path in root.iterdir()
                if path.is_dir() and (excluded is None or path.resolve(strict=False) != excluded)
            ),
            key=natural_sort_key,
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

        videos = tuple(sorted((path for path in files if path.suffix.lower() == ".mp4"), key=natural_sort_key))
        errors: list[str] = []
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
        sources.append(BatchSource(folder, videos, cover, subtitle, music))

    return BatchScanResult(tuple(sources), tuple(issues))
