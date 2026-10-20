from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _run(args: list[str]) -> None:
    process = subprocess.Popen(
        args,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"测试素材生成失败：{args!r}\n{stdout}\n{stderr}")


def create_test_media(output_dir: Path, ffmpeg: str = "ffmpeg", duration: float = 3.0) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "landscape": output_dir / "01 横屏 有声.mp4",
        "portrait": output_dir / "02 portrait silent.mp4",
        "square": output_dir / "03_square_audio.mp4",
        "cover": output_dir / "封面 image.png",
        "music": output_dir / "短音乐.wav",
        "long_music": output_dir / "长音乐.wav",
        "subtitle": output_dir / "字幕.srt",
    }
    common_video = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"]
    _run(
        [
            ffmpeg, "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=24:duration={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-shortest", *common_video, "-c:a", "aac", "-b:a", "128k", str(files["landscape"]),
        ]
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-y", "-f", "lavfi", "-i",
            "sine=frequency=520:sample_rate=48000:duration=6", "-c:a", "pcm_s16le", str(files["long_music"]),
        ]
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=180x320:rate=30:duration={duration}",
            *common_video, "-an", str(files["portrait"]),
        ]
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=240x240:rate=60:duration={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=660:sample_rate=48000:duration={duration}",
            "-shortest", *common_video, "-c:a", "aac", "-b:a", "128k", str(files["square"]),
        ]
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-y", "-f", "lavfi", "-i", "color=c=0x20a050:s=320x180:d=0.1",
            "-frames:v", "1", "-update", "1", str(files["cover"]),
        ]
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-y", "-f", "lavfi", "-i",
            "sine=frequency=880:sample_rate=48000:duration=0.7", "-c:a", "pcm_s16le", str(files["music"]),
        ]
    )
    files["subtitle"].write_text(
        "1\n00:00:00,200 --> 00:00:01,500\nAuto Video Editor\n\n"
        "2\n00:00:01,600 --> 00:00:02,800\n60 FPS transition test\n",
        encoding="utf-8-sig",
        newline="\n",
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="生成自动视频剪辑集成测试素材")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--duration", type=float, default=3.0)
    args = parser.parse_args()
    create_test_media(args.output_dir, args.ffmpeg, args.duration)
    print(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
