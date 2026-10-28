from __future__ import annotations

from auto_video_editor.ui.theme import THEME_COLORS


def _luminance(value: str) -> float:
    channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_editor_text_pairs_meet_wcag_normal_text_contrast():
    assert _contrast(THEME_COLORS["text"], THEME_COLORS["surface"]) >= 4.5
    assert _contrast(THEME_COLORS["text_muted"], THEME_COLORS["surface"]) >= 4.5
    assert _contrast(THEME_COLORS["text_subtle"], THEME_COLORS["surface"]) >= 4.5
    assert _contrast("#FFFFFF", THEME_COLORS["cta"]) >= 4.5


def test_focus_and_brand_states_have_visible_non_text_contrast():
    assert _contrast(THEME_COLORS["focus"], THEME_COLORS["surface_input"]) >= 3
    assert _contrast(THEME_COLORS["brand"], THEME_COLORS["surface"]) >= 3
