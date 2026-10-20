from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..models import SubtitleStyle


class SubtitleError(ValueError):
    """Raised for undecodable or structurally invalid subtitle input."""


@dataclass(frozen=True)
class DecodedSubtitle:
    text: str
    encoding: str


_SRT_TIME = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)


def decode_subtitle(path: Path) -> DecodedSubtitle:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return DecodedSubtitle(data.decode(encoding), encoding)
        except UnicodeDecodeError:
            continue
    raise SubtitleError("字幕编码无法识别，请转换为 UTF-8、GB18030 或 GBK。")


def _parse_srt_time(value: str) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise SubtitleError(f"无效 SRT 时间码：{value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise SubtitleError(f"无效 SRT 时间码：{value}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _format_ass_time(milliseconds: int) -> str:
    centiseconds = max(0, int(round(milliseconds / 10)))
    seconds_total, centis = divmod(centiseconds, 100)
    minutes_total, seconds = divmod(seconds_total, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _ass_color(hex_color: str, alpha: str = "00") -> str:
    value = hex_color.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        raise SubtitleError(f"无效字幕颜色：{hex_color}")
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H{alpha}{blue}{green}{red}".upper()


def _escape_ass_text(lines: list[str]) -> str:
    text = r"\N".join(line.strip().replace("{", r"\{").replace("}", r"\}") for line in lines)
    return text.replace("<i>", r"{\i1}").replace("</i>", r"{\i0}").replace("<b>", r"{\b1}").replace("</b>", r"{\b0}")


def srt_to_ass(text: str, style: SubtitleStyle, offset_seconds: float) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n\s*\n", normalized) if normalized else []
    events: list[str] = []
    offset_ms = int(round(offset_seconds * 1000))
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if len(lines) < 2:
            raise SubtitleError("SRT 字幕块缺少时间码或正文。")
        match = _SRT_TIME.match(lines[0].strip())
        if not match:
            raise SubtitleError(f"无效 SRT 时间行：{lines[0]}")
        start = _parse_srt_time(match.group("start")) + offset_ms
        end = _parse_srt_time(match.group("end")) + offset_ms
        if end <= start:
            raise SubtitleError("字幕结束时间必须晚于开始时间。")
        body = _escape_ass_text(lines[1:])
        events.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{body}"
        )
    if not events:
        raise SubtitleError("字幕中没有可用事件。")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 2560
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{_ass_color(style.primary_color)},&H000000FF,{_ass_color(style.outline_color)},&H64000000,0,0,0,0,100,100,0,0,1,{style.outline_width},0,2,60,60,{style.margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + "\n"


def _parse_ass_time(value: str) -> int:
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[.](\d{2})", value.strip())
    if not match:
        raise SubtitleError(f"无效 ASS 时间码：{value}")
    hours, minutes, seconds, centis = (int(part) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + centis * 10


def shift_ass(text: str, offset_seconds: float) -> str:
    offset_ms = int(round(offset_seconds * 1000))
    output: list[str] = []
    event_count = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            if len(fields) != 10:
                raise SubtitleError("ASS Dialogue 行字段不足。")
            fields[1] = _format_ass_time(_parse_ass_time(fields[1]) + offset_ms)
            fields[2] = _format_ass_time(_parse_ass_time(fields[2]) + offset_ms)
            line = ",".join(fields)
            event_count += 1
        output.append(line)
    if event_count == 0:
        raise SubtitleError("ASS 字幕中没有 Dialogue 事件。")
    return "\n".join(output)


def prepare_subtitles(
    source_path: Path,
    destination_dir: Path,
    *,
    offset_seconds: float,
    style: SubtitleStyle,
) -> Path:
    decoded = decode_subtitle(source_path)
    if source_path.suffix.lower() == ".srt":
        content = srt_to_ass(decoded.text, style, offset_seconds)
    elif source_path.suffix.lower() == ".ass":
        content = shift_ass(decoded.text, offset_seconds) if offset_seconds else shift_ass(decoded.text, 0.0)
    else:
        raise SubtitleError(f"不支持的字幕格式：{source_path.suffix}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "subtitles.ass"
    destination.write_text(content, encoding="utf-8-sig", newline="\n")
    return destination
