from __future__ import annotations

from pathlib import Path

from auto_video_editor.media.ffprobe import parse_probe_json


def test_parse_probe_json_with_rotation_and_audio():
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30/1",
                "duration": "3.5",
                "nb_frames": "105",
                "side_data_list": [{"rotation": -90}],
                "pix_fmt": "yuv420p",
            },
            {"codec_type": "audio", "codec_name": "aac", "duration": "3.48"},
        ],
        "format": {"duration": "3.5", "format_name": "mov,mp4"},
    }
    info = parse_probe_json(Path("手机 视频.mp4"), payload)
    assert info.has_video and info.has_audio
    assert (info.display_width, info.display_height) == (1080, 1920)
    assert info.rotation == 270
    assert info.frame_count == 105
    assert info.is_vfr


def test_parse_audio_only_is_safe():
    info = parse_probe_json(
        Path("music.mp3"),
        {"streams": [{"codec_type": "audio", "codec_name": "mp3"}], "format": {"duration": "4.2"}},
    )
    assert not info.has_video
    assert info.has_audio
    assert info.duration_seconds == 4.2


def test_nonzero_start_is_not_counted_as_content_duration():
    info = parse_probe_json(
        Path("offset.mkv"),
        {
            "streams": [{"codec_type": "video", "width": 321, "height": 181, "start_time": "1.0"}],
            "format": {"start_time": "1.0", "duration": "3.375"},
        },
    )
    assert info.start_time_seconds == 1.0
    assert info.duration_seconds == 2.375
