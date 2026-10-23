from __future__ import annotations

from ..models import OutputQuality


_CONSTANT_QUALITY = {
    OutputQuality.STANDARD: 19,
    OutputQuality.HIGH: 16,
    OutputQuality.ULTRA: 14,
}

_TARGET_BITRATES_MBPS = {
    OutputQuality.BITRATE_12M: 12,
    OutputQuality.BITRATE_16M: 16,
    OutputQuality.BITRATE_20M: 20,
}


def build_video_encoding_args(encoder: str, quality: OutputQuality) -> list[str]:
    """Return final H.264 encoder arguments for the selected quality profile."""
    if encoder not in {"libx264", "h264_nvenc"}:
        raise ValueError(f"不支持的视频编码器：{encoder}")

    if quality in _CONSTANT_QUALITY:
        value = str(_CONSTANT_QUALITY[quality])
        if encoder == "h264_nvenc":
            return ["-c:v", encoder, "-preset", "p5", "-rc", "vbr", "-cq", value, "-b:v", "0"]
        return ["-c:v", encoder, "-preset", "veryfast", "-crf", value]

    bitrate = _TARGET_BITRATES_MBPS[quality]
    maxrate = round(bitrate * 1.25)
    shared = [
        "-b:v", f"{bitrate}M",
        "-maxrate", f"{maxrate}M",
        "-bufsize", f"{bitrate * 2}M",
    ]
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p5", "-rc", "vbr", *shared]
    return ["-c:v", encoder, "-preset", "veryfast", *shared]
