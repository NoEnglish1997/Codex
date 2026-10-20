from __future__ import annotations

import os
from pathlib import Path

from ..models import IssueSeverity, RenderJob, ValidationIssue
from ..utils.paths import sanitize_output_filename


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LOGO_EXTENSIONS = COVER_EXTENSIONS
SUBTITLE_EXTENSIONS = {".srt", ".ass"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


def _path_issue(path: Path, code: str, label: str, extensions: set[str]) -> ValidationIssue | None:
    if not path.is_file():
        return ValidationIssue(code, f"{label}不存在或不是文件：{path}")
    if path.suffix.lower() not in extensions:
        return ValidationIssue(code, f"{label}格式不支持：{path.suffix}")
    if not os.access(path, os.R_OK):
        return ValidationIssue(code, f"{label}不可读：{path}")
    return None


def _subtitle_decodable(path: Path) -> bool:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            data.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def validate_render_job(job: RenderJob) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not job.video_items:
        issues.append(ValidationIssue("no_video", "请至少添加一个视频。"))
    for index, item in enumerate(job.video_items, 1):
        issue = _path_issue(item.source_path, "video_path", f"第 {index} 个视频", VIDEO_EXTENSIONS)
        if issue:
            issues.append(issue)
            continue
        if item.probe is None:
            issues.append(ValidationIssue("video_unprobed", f"第 {index} 个视频尚未读取元信息。"))
            continue
        if not item.probe.has_video:
            issues.append(ValidationIssue("no_video_stream", f"{item.display_name} 没有视频轨。"))
        if item.probe.duration_seconds < 2.0:
            issues.append(ValidationIssue("video_too_short", f"{item.display_name} 短于 2 秒，无法安全叠化。"))
    if job.cover_path:
        issue = _path_issue(job.cover_path, "cover_path", "封面", COVER_EXTENSIONS)
        if issue:
            issues.append(issue)
    if job.logo_path:
        issue = _path_issue(job.logo_path, "logo_path", "Logo", LOGO_EXTENSIONS)
        if issue:
            issues.append(issue)
    if job.subtitle_path:
        issue = _path_issue(job.subtitle_path, "subtitle_path", "字幕", SUBTITLE_EXTENSIONS)
        if issue:
            issues.append(issue)
        elif not _subtitle_decodable(job.subtitle_path):
            issues.append(ValidationIssue("subtitle_encoding", "字幕编码无法识别，请转换为 UTF-8、GB18030 或 GBK。"))
    if job.music_path:
        issue = _path_issue(job.music_path, "music_path", "音乐", MUSIC_EXTENSIONS)
        if issue:
            issues.append(issue)
    output_dir = job.output_dir
    if output_dir.exists():
        if not output_dir.is_dir() or not os.access(output_dir, os.W_OK):
            issues.append(ValidationIssue("output_dir", f"输出目录不可写：{output_dir}"))
    else:
        parent = next((candidate for candidate in (output_dir, *output_dir.parents) if candidate.exists()), None)
        if parent is None or not parent.is_dir() or not os.access(parent, os.W_OK):
            issues.append(ValidationIssue("output_dir", f"无法创建输出目录：{output_dir}"))
    sanitized = sanitize_output_filename(job.output_filename)
    if sanitized != job.output_filename:
        issues.append(ValidationIssue(
            "output_name_sanitized",
            f"输出文件名将调整为：{sanitized}",
            IssueSeverity.WARNING,
        ))
    if (output_dir / sanitized).exists():
        issues.append(ValidationIssue(
            "output_exists",
            "目标文件已存在，将自动使用带编号的新文件名。",
            IssueSeverity.WARNING,
        ))
    if not 0.0 <= job.settings.music_volume <= 1.0:
        issues.append(ValidationIssue("music_volume", "音乐音量必须在 0% 到 100% 之间。"))
    return issues
