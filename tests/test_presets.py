from __future__ import annotations

from auto_video_editor.models import CanvasMode, OutputQuality, RenderSettings, SubtitleStyle
from auto_video_editor.presets import (
    PresetStore,
    render_settings_from_mapping,
    render_settings_to_mapping,
)


def test_render_settings_mapping_round_trip_preserves_advanced_options():
    expected = RenderSettings(
        canvas_mode=CanvasMode.CROP,
        sharpen_amount=0.8,
        normalize_audio=True,
        output_quality=OutputQuality.BITRATE_16M,
        subtitle_style=SubtitleStyle(
            background_opacity_percent=55,
            highlight_words=("安全", "结构"),
        ),
    )
    assert render_settings_from_mapping(render_settings_to_mapping(expected)) == expected


def test_invalid_profile_values_are_clamped_and_fixed_output_cannot_be_overridden():
    settings = render_settings_from_mapping({
        "width": 999,
        "sharpen_amount": 99,
        "music_volume": -2,
        "canvas_mode": "magic",
    })
    assert settings.width == 1440
    assert settings.sharpen_amount == 2
    assert settings.music_volume == 0
    assert settings.canvas_mode == CanvasMode.BLUR


def test_custom_preset_store_round_trip(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    payload = {"我的模板": {"output_quality": "ultra", "cover_frames": 30}}
    store.save_custom(payload)
    assert store.load_custom() == payload
    assert not list(tmp_path.glob("*.tmp"))
