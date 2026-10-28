from __future__ import annotations

import pytest

from auto_video_editor.media.subtitles import (
    SubtitleError,
    apply_ass_font,
    prepare_cover_title,
    shift_ass,
    srt_to_ass,
)
from auto_video_editor.models import SubtitleStyle


def test_srt_conversion_applies_five_frame_offset_and_style():
    text = "1\n00:00:00,000 --> 00:00:01,000\n你好，世界\n"
    ass = srt_to_ass(text, SubtitleStyle(font_name="Microsoft YaHei", font_size=70), 5 / 60)
    assert "Style: Default,Microsoft YaHei,70" in ass
    assert "Dialogue: 0,0:00:00.08,0:00:01.08" in ass
    assert "你好，世界" in ass


def test_srt_without_cover_has_no_offset():
    ass = srt_to_ass("00:00:00,500 --> 00:00:01,500\nText", SubtitleStyle(), 0)
    assert "0:00:00.50,0:00:01.50" in ass


def test_ass_preserves_style_and_shifts_dialogue():
    source = """[V4+ Styles]
Style: Fancy,Arial,42,&H00FFFFFF,&H0,&H0,&H0,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Dialogue: 0,0:00:01.00,0:00:02.00,Fancy,,0,0,0,,Hello
"""
    shifted = shift_ass(source, 5 / 60)
    assert "Style: Fancy,Arial,42" in shifted
    assert "0:00:01.08,0:00:02.08,Fancy" in shifted


def test_ass_font_can_be_overridden_without_changing_other_style_fields():
    source = "Style: Fancy,Arial,42,&H00FFFFFF\nStyle: Alt,Times New Roman,36,&H00FFFFFF"
    changed = apply_ass_font(source, "Microsoft YaHei")
    assert "Style: Fancy,Microsoft YaHei,42,&H00FFFFFF" in changed
    assert "Style: Alt,Microsoft YaHei,36,&H00FFFFFF" in changed


def test_invalid_srt_is_rejected():
    with pytest.raises(SubtitleError):
        srt_to_ass("1\nnot a time\nText", SubtitleStyle(), 0)


def test_srt_wrap_background_shadow_and_keyword_highlight():
    source = "1\n00:00:00,000 --> 00:00:02,000\n透明泳池结构安全非常重要\n"
    style = SubtitleStyle(
        background_opacity_percent=55,
        shadow_depth=3,
        max_chars_per_line=6,
        highlight_words=("安全",),
        highlight_color="#FFD400",
    )
    ass = srt_to_ass(source, style, 0)
    assert ",3,5,3,2,60,60,180,1" in ass
    assert r"\N" in ass
    assert r"{\c&H00D4FF&}安全{\r}" in ass


def test_cover_title_creates_centered_ass(tmp_path):
    path = prepare_cover_title("结构安全", tmp_path, duration_seconds=0.5, font_name="SimHei")
    assert path is not None
    text = path.read_text(encoding="utf-8-sig")
    assert "Style: CoverTitle,SimHei" in text
    assert "0:00:00.50" in text
    assert "结构安全" in text
