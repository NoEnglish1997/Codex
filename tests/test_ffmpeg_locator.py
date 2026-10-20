from __future__ import annotations

import shutil

import pytest

from auto_video_editor.media.ffmpeg_locator import detect_capabilities, locate_tools


def test_locate_tools_from_path():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg is not installed")
    tools = locate_tools()
    assert tools.ffmpeg.is_file()
    assert tools.ffprobe.is_file()


@pytest.mark.integration
def test_installed_ffmpeg_has_required_capabilities():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg is not installed")
    capabilities = detect_capabilities()
    assert capabilities.ready, capabilities.missing_required
    assert "xfade" in capabilities.filters
    assert "minterpolate" in capabilities.filters
    assert "libx264" in capabilities.encoders
