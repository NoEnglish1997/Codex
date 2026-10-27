from __future__ import annotations

from pathlib import Path

import pytest

from auto_video_editor.media.encoding import build_filtergraph_args, build_video_encoding_args
from auto_video_editor.models import OutputQuality


@pytest.mark.parametrize(
    ("quality", "expected_value"),
    [
        (OutputQuality.STANDARD, "19"),
        (OutputQuality.HIGH, "16"),
        (OutputQuality.ULTRA, "14"),
    ],
)
def test_x264_constant_quality_profiles_use_expected_crf(quality, expected_value):
    args = build_video_encoding_args("libx264", quality)
    assert args == ["-c:v", "libx264", "-preset", "veryfast", "-crf", expected_value]


def test_nvenc_high_quality_uses_cq_without_target_bitrate():
    args = build_video_encoding_args("h264_nvenc", OutputQuality.HIGH)
    assert args == [
        "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "16", "-b:v", "0",
    ]


@pytest.mark.parametrize(
    ("quality", "bitrate", "maxrate", "bufsize"),
    [
        (OutputQuality.BITRATE_12M, "12M", "15M", "24M"),
        (OutputQuality.BITRATE_16M, "16M", "20M", "32M"),
        (OutputQuality.BITRATE_20M, "20M", "25M", "40M"),
    ],
)
def test_target_bitrate_profiles_apply_rate_controls(quality, bitrate, maxrate, bufsize):
    for encoder in ("libx264", "h264_nvenc"):
        args = build_video_encoding_args(encoder, quality)
        assert args[args.index("-b:v") + 1] == bitrate
        assert args[args.index("-maxrate") + 1] == maxrate
        assert args[args.index("-bufsize") + 1] == bufsize
        assert "-crf" not in args
        assert "-cq" not in args


def test_unknown_encoder_is_rejected():
    with pytest.raises(ValueError, match="不支持"):
        build_video_encoding_args("unknown", OutputQuality.STANDARD)


def test_filtergraph_file_uses_ffmpeg_7_plus_option_from_file_syntax():
    path = Path("C:/临时目录/single_pass.ffgraph")
    assert build_filtergraph_args(path) == ["-/filter_complex", str(path)]
    assert build_filtergraph_args("[0:v]null[vout]") == [
        "-filter_complex", "[0:v]null[vout]",
    ]
