from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..models import FFmpegCapabilities, ToolPaths
from ..utils.paths import application_dir


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg or FFprobe cannot be located or executed."""


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0


def _capture(args: list[str], timeout: float = 15.0) -> tuple[int, str]:
    process = subprocess.Popen(
        args,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise RuntimeError(f"外部工具执行超时：{args[0]}") from None
    return process.returncode, output


def _candidate_from_custom(value: str | Path | None, executable: str) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_dir():
        names = [f"{executable}.exe", executable]
        for name in names:
            resolved = candidate / name
            if resolved.is_file():
                return resolved.resolve()
        return None
    return candidate.resolve() if candidate.is_file() else None


def locate_tools(
    custom_ffmpeg: str | Path | None = None,
    custom_ffprobe: str | Path | None = None,
    app_directory: Path | None = None,
) -> ToolPaths:
    ffmpeg = _candidate_from_custom(custom_ffmpeg, "ffmpeg")
    ffprobe = _candidate_from_custom(custom_ffprobe, "ffprobe")

    roots = [app_directory or application_dir(), (app_directory or application_dir()) / "ffmpeg" / "bin"]
    for root in roots:
        if ffmpeg is None:
            ffmpeg = _candidate_from_custom(root, "ffmpeg")
        if ffprobe is None:
            ffprobe = _candidate_from_custom(root, "ffprobe")

    if ffmpeg is None:
        found = shutil.which("ffmpeg")
        ffmpeg = Path(found).resolve() if found else None
    if ffprobe is None:
        found = shutil.which("ffprobe")
        ffprobe = Path(found).resolve() if found else None
    if ffmpeg is None or ffprobe is None:
        missing = "FFmpeg" if ffmpeg is None else "FFprobe"
        raise FFmpegNotFoundError(f"未找到 {missing}。请在设置中选择可执行文件或加入 PATH。")
    return ToolPaths(ffmpeg=ffmpeg, ffprobe=ffprobe)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "未知版本")


def _version_major(line: str) -> int | None:
    match = re.search(r"\bversion\s+(\d+)", line)
    return int(match.group(1)) if match else None


def _parse_named_entries(text: str) -> frozenset[str]:
    names: set[str] = set()
    for line in text.splitlines():
        columns = line.split()
        if len(columns) >= 2 and columns[0] and columns[0][0] in ".TSCAVFDE":
            names.add(columns[1])
    return frozenset(names)


def probe_encoder(ffmpeg: Path, encoder: str) -> bool:
    code, _ = _capture(
        [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=black:s=64x64:r=30:d=0.1", "-frames:v", "1",
            "-c:v", encoder, "-f", "null", "-",
        ],
        timeout=20.0,
    )
    return code == 0


def inspect_capabilities(tools: ToolPaths) -> FFmpegCapabilities:
    ffmpeg_code, ffmpeg_version = _capture([str(tools.ffmpeg), "-version"])
    ffprobe_code, ffprobe_version = _capture([str(tools.ffprobe), "-version"])
    if ffmpeg_code != 0 or ffprobe_code != 0:
        raise FFmpegNotFoundError("FFmpeg 或 FFprobe 无法执行，请检查路径和文件权限。")
    filters_code, filters_text = _capture([str(tools.ffmpeg), "-hide_banner", "-filters"])
    encoders_code, encoders_text = _capture([str(tools.ffmpeg), "-hide_banner", "-encoders"])
    if filters_code != 0 or encoders_code != 0:
        raise RuntimeError("无法读取 FFmpeg 滤镜或编码器列表。")
    filters = _parse_named_entries(filters_text)
    encoders = _parse_named_entries(encoders_text)
    required_groups = {
        "xfade": {"xfade"},
        "minterpolate": {"minterpolate"},
        "模糊滤镜": {"gblur", "boxblur"},
        "overlay": {"overlay"},
        "字幕/libass": {"subtitles", "ass"},
        "libx264": {"libx264"},
    }
    missing_list = [label for label, choices in required_groups.items() if not choices.intersection(filters | encoders)]
    ffmpeg_line = _first_line(ffmpeg_version)
    ffprobe_line = _first_line(ffprobe_version)
    ffmpeg_major = _version_major(ffmpeg_line)
    ffprobe_major = _version_major(ffprobe_line)
    if ffmpeg_major is not None and ffprobe_major is not None and ffmpeg_major != ffprobe_major:
        missing_list.append("FFmpeg/FFprobe 主版本不一致")
    missing = tuple(missing_list)
    nvenc_usable = "h264_nvenc" in encoders and probe_encoder(tools.ffmpeg, "h264_nvenc")
    return FFmpegCapabilities(
        ffmpeg_path=tools.ffmpeg,
        ffprobe_path=tools.ffprobe,
        ffmpeg_version=ffmpeg_line,
        ffprobe_version=ffprobe_line,
        filters=filters,
        encoders=encoders,
        nvenc_usable=nvenc_usable,
        missing_required=missing,
    )


def detect_capabilities(
    custom_ffmpeg: str | Path | None = None,
    custom_ffprobe: str | Path | None = None,
) -> FFmpegCapabilities:
    return inspect_capabilities(locate_tools(custom_ffmpeg, custom_ffprobe))
