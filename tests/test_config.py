from __future__ import annotations

import json

from auto_video_editor.config import AppSettings, SettingsStore


def test_settings_round_trip_is_atomic(tmp_path):
    path = tmp_path / "设置" / "settings.json"
    store = SettingsStore(path)
    expected = AppSettings(
        output_dir=str(tmp_path),
        interpolation_mode="fast",
        source_audio_mode="mix",
        music_short_policy="silence",
        music_volume=0.42,
        video_encoder="x264",
        mirror_second_clip=False,
        subtitle_font_name="SimHei",
        ffmpeg_path="C:/工具/ffmpeg.exe",
        ffprobe_path="C:/工具/ffprobe.exe",
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
        }),
        encoding="utf-8",
    )
    settings = SettingsStore(path).load().settings
    assert settings.interpolation_mode == "motion"
    assert settings.music_volume == 1.0
    assert settings.mirror_second_clip is True
    assert settings.subtitle_font_name == "Microsoft YaHei"
    assert settings.output_dir != str(tmp_path / "missing")
