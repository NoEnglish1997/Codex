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


def _wrap_lines(lines: list[str], max_chars: int) -> list[str]:
    wrapped: list[str] = []
    limit = max(4, max_chars)
    for line in lines:
        value = line.strip()
        if not value:
            wrapped.append("")
            continue
        while len(value) > limit:
            split = max(value.rfind(" ", 0, limit + 1), value.rfind("，", 0, limit + 1))
            if split < max(1, limit // 2):
                split = limit
            wrapped.append(value[:split].strip())
            value = value[split:].strip()
        if value:
            wrapped.append(value)
    return wrapped


def _ass_tag_color(hex_color: str) -> str:
    value = _ass_color(hex_color)
    return "&H" + value[4:] + "&"


def _highlight_words(text: str, style: SubtitleStyle) -> str:
    color = _ass_tag_color(style.highlight_color)
    result = text
    for word in sorted(set(style.highlight_words), key=len, reverse=True):
        safe = word.strip()
        if safe:
            result = result.replace(safe, rf"{{\c{color}}}{safe}{{\r}}")
    return result


def _safe_font_name(font_name: str) -> str:
    value = font_name.replace("\r", " ").replace("\n", " ").replace(",", " ").strip()
    return value or "Microsoft YaHei"


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
        body = _escape_ass_text(_wrap_lines(lines[1:], style.max_chars_per_line))
        body = _highlight_words(body, style)
        events.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{body}"
        )
    if not events:
        raise SubtitleError("字幕中没有可用事件。")
    font_name = _safe_font_name(style.font_name)
    background_alpha = round(255 * (1 - min(100, max(0, style.background_opacity_percent)) / 100))
    border_style = 3 if style.background_opacity_percent > 0 else 1
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 2560
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{style.font_size},{_ass_color(style.primary_color)},&H000000FF,{_ass_color(style.outline_color)},{_ass_color(style.outline_color, f'{background_alpha:02X}')},0,0,0,0,100,100,0,0,{border_style},{style.outline_width},{style.shadow_depth},2,{style.margin_horizontal},{style.margin_horizontal},{style.margin_bottom},1

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


def apply_ass_font(text: str, font_name: str) -> str:
    """Override ASS style fonts while preserving every other style field."""
    safe_name = _safe_font_name(font_name)
    output: list[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith("Style:"):
            leading = line[: len(line) - len(line.lstrip())]
            value = line.lstrip()[len("Style:"):]
            fields = value.split(",")
            if len(fields) >= 2:
                fields[1] = safe_name
                line = f"{leading}Style:{','.join(fields)}"
        output.append(line)
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
        content = apply_ass_font(shift_ass(decoded.text, offset_seconds), style.font_name)
    else:
        raise SubtitleError(f"不支持的字幕格式：{source_path.suffix}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "subtitles.ass"
    destination.write_text(content, encoding="utf-8-sig", newline="\n")
    return destination


def prepare_cover_title(
    title: str,
    destination_dir: Path,
    *,
    duration_seconds: float,
    font_name: str,
) -> Path | None:
    value = title.replace("\r", " ").replace("\n", " ").strip()
    if not value or duration_seconds <= 0:
        return None
    safe_title = _escape_ass_text([value])
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 2560
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CoverTitle,{_safe_font_name(font_name)},92,&H00FFFFFF,&H000000FF,&H00000000,&H70000000,1,0,0,0,100,100,0,0,3,5,0,5,80,80,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{_format_ass_time(round(duration_seconds * 1000))},CoverTitle,,0,0,0,,{safe_title}
"""
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "cover_title.ass"
    destination.write_text(content, encoding="utf-8-sig", newline="\n")
    return destination
