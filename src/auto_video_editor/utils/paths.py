from __future__ import annotations

import os
import sys
import re
from pathlib import Path


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "AutoVideoEditor"


def default_output_dir() -> Path:
    videos = Path.home() / "Videos"
    return videos if videos.is_dir() else Path.home()


_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def sanitize_output_filename(value: str, fallback: str = "edited_video.mp4") -> str:
    name = _WINDOWS_INVALID.sub("_", value).rstrip(" .")
    if not name:
        name = fallback
    stem = Path(name).stem.rstrip(" .") or Path(fallback).stem
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    return f"{stem}.mp4"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为 {path.name} 生成不重复的文件名")
