from __future__ import annotations

import json

from auto_video_editor.config import AppSettings, SettingsStore


def test_settings_round_trip_is_atomic(tmp_path):
    path = tmp_path / "设置" / "settings.json"
    store = SettingsStore(path)
    expected = AppSettings(
        output_dir=str(tmp_path),
        batch_input_dir="C:/素材总目录",
        output_prefix="成片测试_",
        output_template="{date}_{folder}_{index}.mp4",
        video_sort_mode="modified",
        first_video_pattern="片头*",
        last_video_pattern="*片尾.mp4",
        watch_enabled=True,
        watch_interval_seconds=12,
        interpolation_mode="fast",
        source_audio_mode="mix",
        music_short_policy="silence",
        music_volume=0.42,
        video_encoder="x264",
        output_quality="bitrate_16m",
        mirror_second_clip=False,
        subtitle_font_name="SimHei",
        logo_scale_percent=175,
        logo_opacity_percent=65,
        ffmpeg_path="C:/工具/ffmpeg.exe",
        ffprobe_path="C:/工具/ffprobe.exe",
        render_profile={"transition_type": "wipeleft", "normalize_audio": True},
    )
    store.save(expected)
    loaded = store.load()
    assert loaded.warning is None
    assert loaded.settings == expected
    assert not list(path.parent.glob("*.tmp"))


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not-json", encoding="utf-8")
    loaded = SettingsStore(path).load()
    assert loaded.warning
    assert loaded.settings.interpolation_mode == "motion"
    assert loaded.settings.music_volume == 0.35


def test_invalid_values_are_sanitized(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({
            "output_dir": str(tmp_path / "missing"),
            "interpolation_mode": "magic",
            "music_volume": 4,
            "mirror_second_clip": "yes",
            "subtitle_font_name": "bad\nfont",
            "logo_scale_percent": 999,
            "logo_opacity_percent": -20,
            "output_prefix": "bad\nprefix",
            "output_quality": "huge",
        }),
        encoding="utf-8",
    )
    settings = SettingsStore(path).load().settings
    assert settings.interpolation_mode == "motion"
    assert settings.music_volume == 1.0
    assert settings.mirror_second_clip is True
    assert settings.subtitle_font_name == "Microsoft YaHei"
    assert settings.logo_scale_percent == 300
    assert settings.logo_opacity_percent == 0
    assert settings.output_prefix == "成片_"
    assert settings.output_quality == "standard"
    assert settings.output_dir != str(tmp_path / "missing")
