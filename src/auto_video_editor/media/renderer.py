from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ..models import (
    ExpectedOutput,
    FFmpegCapabilities,
    IssueSeverity,
    OutputQuality,
    RenderJob,
    RenderResult,
    SourceAudioMode,
    TimelinePlan,
    VideoEncoder,
    VideoItem,
)
from ..utils.paths import sanitize_output_filename, unique_path
from .audio import build_audio_plan, build_final_audio_filtergraph, build_source_acrossfade_filtergraph
from .encoding import build_video_encoding_args
from .ffprobe import ProbeError, probe_media
from .progress import CancellationToken, run_ffmpeg
from .subtitles import prepare_subtitles
from .timeline import calculate_timeline
from .validation import validate_render_job
from .verify import verify_output
from .video_filters import (
    build_cover_concat_filtergraph,
    build_cover_filter,
    build_final_video_filter,
    build_normalization_filter,
    build_xfade_filtergraph,
)


class RenderError(RuntimeError):
    """Raised when a render stage fails or its output does not verify."""


class RenderCancelled(RenderError):
    """Raised after a user cancellation has stopped active processing."""


ProgressCallback = Callable[[str, int], None]
LogCallback = Callable[[str], None]


class Renderer:
    def __init__(
        self,
        capabilities: FFmpegCapabilities,
        *,
        cache_root: Path | None = None,
    ) -> None:
        self.capabilities = capabilities
        self.cache_root = cache_root or (Path(tempfile.gettempdir()) / "AutoVideoEditor")

    def render(
        self,
        job: RenderJob,
        cancel_token: CancellationToken,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
    ) -> RenderResult:
        started = time.monotonic()
        job.output_dir.mkdir(parents=True, exist_ok=True)
        auxiliary_dir = job.auxiliary_dir or job.output_dir
        auxiliary_dir.mkdir(parents=True, exist_ok=True)
        log_path = unique_path(
            auxiliary_dir / f"auto_video_editor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        log_handle = log_path.open("w", encoding="utf-8", newline="\n")

        def log(message: str) -> None:
            line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
            log_handle.write(line + "\n")
            log_handle.flush()
            if log_callback:
                log_callback(line)

        def emit(stage: str, percent: float) -> None:
            if progress_callback:
                progress_callback(stage, max(0, min(100, int(round(percent)))))

        target = unique_path(job.output_dir / sanitize_output_filename(job.output_filename))
        part_path = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.part.mp4")
        temporary_dir: Path | None = None
        cover_output: Path | None = None
        report_path = auxiliary_dir / f"{target.stem}.job_report.json"
        try:
            emit("预检", 0)
            if not self.capabilities.ready:
                raise RenderError(f"FFmpeg 缺少必需能力：{', '.join(self.capabilities.missing_required)}")
            prepared_job = self._probe_job(job, log)
            errors = [
                issue.message
                for issue in validate_render_job(prepared_job)
                if issue.severity == IssueSeverity.ERROR
            ]
            if errors:
                raise RenderError("预检失败：\n" + "\n".join(f"- {message}" for message in errors))
            self._check_cancel(cancel_token)
            self.cache_root.mkdir(parents=True, exist_ok=True)
            self._check_disk_space(prepared_job, log)
            temporary_dir = Path(tempfile.mkdtemp(prefix="job_", dir=self.cache_root))
            log(f"任务临时目录：{temporary_dir}")
            emit("预检完成", 5)

            normalized, frame_counts, source_audio_files = self._normalize_clips(
                prepared_job, temporary_dir, cancel_token, emit, log
            )
            timeline_without_cover = calculate_timeline(
                frame_counts,
                False,
                fps=prepared_job.settings.fps,
                transition_frames=prepared_job.settings.transition_frames,
                cover_frames=prepared_job.settings.cover_frames,
            )
            body_video = self._combine_video(
                normalized,
                timeline_without_cover,
                prepared_job,
                temporary_dir,
                cancel_token,
                emit,
                log,
            )
            body_audio = self._combine_source_audio(
                source_audio_files,
                timeline_without_cover,
                prepared_job,
                temporary_dir,
                cancel_token,
                log,
            )
            visual_video, cover_jpg = self._add_cover(
                body_video,
                timeline_without_cover,
                prepared_job,
                temporary_dir,
                cancel_token,
                emit,
                log,
            )
            timeline = calculate_timeline(
                frame_counts,
                prepared_job.cover_path is not None,
                fps=prepared_job.settings.fps,
                transition_frames=prepared_job.settings.transition_frames,
                cover_frames=prepared_job.settings.cover_frames,
            )
            subtitle_path = None
            if prepared_job.subtitle_path and prepared_job.settings.subtitle_enabled:
                subtitle_path = prepare_subtitles(
                    prepared_job.subtitle_path,
                    temporary_dir,
                    offset_seconds=timeline.subtitle_offset_seconds,
                    style=prepared_job.settings.subtitle_style,
                )
                log(f"字幕已准备，时间偏移 {timeline.subtitle_offset_seconds:.9f} 秒。")
            encoder = self._encode_final(
                visual_video,
                body_audio,
                subtitle_path,
                timeline,
                prepared_job,
                part_path,
                cancel_token,
                emit,
                log,
            )
            emit("核验输出", 99)
            expected = ExpectedOutput(
                width=prepared_job.settings.width,
                height=prepared_job.settings.height,
                fps=prepared_job.settings.fps,
                frame_count=timeline.total_frames,
                has_audio=body_audio is not None or prepared_job.music_path is not None,
                duration_seconds=timeline.duration_seconds,
            )
            verification = verify_output(part_path, self.capabilities.ffprobe_path, expected)
            if not verification.valid:
                raise RenderError("成片核验失败：\n" + "\n".join(verification.errors))
            self._check_cancel(cancel_token)
            os.replace(part_path, target)
            if cover_jpg is not None:
                cover_output = unique_path(auxiliary_dir / "cover.jpg")
                cover_part = cover_output.with_name(f".{cover_output.name}.{uuid.uuid4().hex}.part")
                shutil.copy2(cover_jpg, cover_part)
                os.replace(cover_part, cover_output)
            report_path = unique_path(auxiliary_dir / f"{target.stem}.job_report.json")
            self._write_report(
                report_path,
                prepared_job,
                target,
                cover_output,
                timeline,
                encoder,
                verification,
                time.monotonic() - started,
            )
            emit("完成", 100)
            log(f"输出核验通过：{target}")
            return RenderResult(target, cover_output, report_path, log_path, timeline, encoder, verification)
        except RenderCancelled:
            log("任务已由用户取消。")
            raise
        except Exception as exc:
            log(f"任务失败：{exc}")
            if isinstance(exc, RenderError):
                raise
            raise RenderError(str(exc)) from exc
        finally:
            if part_path.exists():
                part_path.unlink(missing_ok=True)
            if temporary_dir is not None and temporary_dir.exists():
                shutil.rmtree(temporary_dir, ignore_errors=True)
            log_handle.close()

    def _probe_job(self, job: RenderJob, log: LogCallback) -> RenderJob:
        items: list[VideoItem] = []
        for item in job.video_items:
            probe = probe_media(item.source_path, self.capabilities.ffprobe_path)
            items.append(replace(item, probe=probe))
            log(
                f"素材：{item.display_name}，{probe.display_width}×{probe.display_height}，"
                f"{probe.duration_seconds:.3f}s，{probe.avg_frame_rate} FPS，音轨={'有' if probe.has_audio else '无'}"
            )
        if job.cover_path:
            cover_probe = probe_media(job.cover_path, self.capabilities.ffprobe_path)
            if not cover_probe.has_video or cover_probe.width <= 0 or cover_probe.height <= 0:
                raise RenderError("封面图片无法解码。")
        if job.logo_path:
            logo_probe = probe_media(job.logo_path, self.capabilities.ffprobe_path)
            if not logo_probe.has_video or logo_probe.width <= 0 or logo_probe.height <= 0:
                raise RenderError("Logo 图片无法解码。")
            log(f"Logo：{job.logo_path.name}，{logo_probe.width}×{logo_probe.height}")
        if job.music_path:
            music_probe = probe_media(job.music_path, self.capabilities.ffprobe_path)
            if not music_probe.has_audio:
                raise RenderError("配乐文件没有可解码音轨。")
            log(f"配乐：{job.music_path.name}，{music_probe.duration_seconds:.3f}s")
        return replace(job, video_items=tuple(items))

    def _check_disk_space(self, job: RenderJob, log: LogCallback) -> None:
        source_bytes = sum(item.source_path.stat().st_size for item in job.video_items if item.source_path.exists())
        required = max(512 * 1024 * 1024, source_bytes * 4)
        free = shutil.disk_usage(self.cache_root.parent if not self.cache_root.exists() else self.cache_root).free
        log(f"临时空间估计至少 {required / 1024**3:.2f} GiB；当前可用 {free / 1024**3:.2f} GiB。")
        if free < required:
            raise RenderError("临时磁盘空间不足，请释放空间或缩短素材。")

    def _normalize_clips(
        self,
        job: RenderJob,
        temporary_dir: Path,
        token: CancellationToken,
        emit: Callable[[str, float], None],
        log: LogCallback,
    ) -> tuple[list[Path], list[int], list[Path]]:
        outputs: list[Path] = []
        counts: list[int] = []
        audio_outputs: list[Path] = []
        total = len(job.video_items)
        for index, item in enumerate(job.video_items):
            self._check_cancel(token)
            assert item.probe is not None
            output = temporary_dir / f"clip_{index + 1:04d}.mp4"
            mirror = job.settings.mirror_second_clip and index == 1
            video_filter = build_normalization_filter(
                item.probe,
                job.settings,
                horizontal_flip=mirror,
            )
            args = [
                str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-i", str(item.source_path),
                "-map", "0:v:0", "-vf", video_filter, "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                "-pix_fmt", "yuv420p", "-r", str(job.settings.fps), "-fps_mode", "cfr", "-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
            ]
            start = 5 + 60 * index / total
            span = 60 / total
            self._run(
                args,
                token,
                item.probe.duration_seconds,
                lambda fraction, s=start, p=span, n=item.display_name: emit(f"标准化：{n}", s + p * fraction * 0.82),
                log,
            )
            normalized_probe = probe_media(output, self.capabilities.ffprobe_path, count_frames=True)
            if (
                not normalized_probe.has_video
                or normalized_probe.width != job.settings.width
                or normalized_probe.height != job.settings.height
                or normalized_probe.avg_frame_rate.numerator
                != job.settings.fps * normalized_probe.avg_frame_rate.denominator
                or not normalized_probe.frame_count
            ):
                raise RenderError(f"标准化结果不符合固定输出规格：{item.display_name}")
            outputs.append(output)
            counts.append(normalized_probe.frame_count)
            mirror_note = "，已水平镜像" if mirror else ""
            log(f"标准化完成：{item.display_name}，实测 {normalized_probe.frame_count} 帧{mirror_note}。")
            if job.settings.source_audio_mode == SourceAudioMode.MIX:
                audio = temporary_dir / f"audio_{index + 1:04d}.wav"
                duration = normalized_probe.frame_count / job.settings.fps
                self._extract_or_create_audio(item, audio, duration, token, log)
                audio_outputs.append(audio)
            emit(f"标准化完成：{item.display_name}", start + span)
        return outputs, counts, audio_outputs

    def _extract_or_create_audio(
        self,
        item: VideoItem,
        output: Path,
        duration: float,
        token: CancellationToken,
        log: LogCallback,
    ) -> None:
        assert item.probe is not None
        if item.probe.has_audio:
            args = [
                str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-i", str(item.source_path),
                "-map", "0:a:0", "-vn", "-af",
                "aresample=48000,aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,apad,atrim=duration={duration:.9f}",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
            ]
        else:
            args = [
                str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.9f}",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
            ]
        self._run(args, token, duration, None, log)

    def _combine_video(
        self,
        clips: list[Path],
        timeline: TimelinePlan,
        job: RenderJob,
        temporary_dir: Path,
        token: CancellationToken,
        emit: Callable[[str, float], None],
        log: LogCallback,
    ) -> Path:
        output = temporary_dir / "body.mp4"
        if len(clips) == 1:
            shutil.copy2(clips[0], output)
            emit("单片段，无需转场", 80)
            return output
        graph, label = build_xfade_filtergraph(list(timeline.frame_counts), job.settings)
        args = [str(self.capabilities.ffmpeg_path), "-hide_banner", "-y"]
        for clip in clips:
            args.extend(["-i", str(clip)])
        args.extend(
            [
                "-filter_complex", graph, "-map", label, "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
                "-r", str(job.settings.fps), "-fps_mode", "cfr", "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
            ]
        )
        self._run(
            args,
            token,
            timeline.duration_seconds,
            lambda fraction: emit("合成片段转场", 65 + 15 * fraction),
            log,
        )
        probe = probe_media(output, self.capabilities.ffprobe_path, count_frames=True)
        if probe.frame_count is None or abs(probe.frame_count - timeline.body_frames) > 1:
            raise RenderError(f"转场合成帧数错误：期望 {timeline.body_frames}，实际 {probe.frame_count}")
        log(f"转场合成完成：{probe.frame_count} 帧，{len(clips) - 1} 个 1 秒叠化。")
        return output

    def _combine_source_audio(
        self,
        audio_files: list[Path],
        timeline: TimelinePlan,
        job: RenderJob,
        temporary_dir: Path,
        token: CancellationToken,
        log: LogCallback,
    ) -> Path | None:
        if job.settings.source_audio_mode != SourceAudioMode.MIX:
            return None
        output = temporary_dir / "body_audio.wav"
        if len(audio_files) == 1:
            shutil.copy2(audio_files[0], output)
            return output
        graph, label = build_source_acrossfade_filtergraph(
            len(audio_files),
            timeline.duration_seconds,
            job.settings.transition_frames / job.settings.fps,
        )
        args = [str(self.capabilities.ffmpeg_path), "-hide_banner", "-y"]
        for audio in audio_files:
            args.extend(["-i", str(audio)])
        args.extend(
            [
                "-filter_complex", graph, "-map", label, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
            ]
        )
        self._run(args, token, timeline.duration_seconds, None, log)
        return output

    def _add_cover(
        self,
        body_video: Path,
        body_timeline: TimelinePlan,
        job: RenderJob,
        temporary_dir: Path,
        token: CancellationToken,
        emit: Callable[[str, float], None],
        log: LogCallback,
    ) -> tuple[Path, Path | None]:
        if job.cover_path is None:
            emit("无封面", 85)
            return body_video, None
        cover_probe = probe_media(job.cover_path, self.capabilities.ffprobe_path)
        cover_filter = build_cover_filter(cover_probe.width, cover_probe.height, job.settings)
        cover_clip = temporary_dir / "cover.mp4"
        args = [
            str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-loop", "1", "-framerate", str(job.settings.fps),
            "-i", str(job.cover_path), "-vf", cover_filter, "-frames:v", str(job.settings.cover_frames), "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
            "-r", str(job.settings.fps), "-fps_mode", "cfr",
            "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(cover_clip),
        ]
        self._run(args, token, job.settings.cover_frames / job.settings.fps, None, log)
        cover_count = probe_media(cover_clip, self.capabilities.ffprobe_path, count_frames=True).frame_count
        if cover_count != job.settings.cover_frames:
            raise RenderError(f"封面片段应为 {job.settings.cover_frames} 帧，实际为 {cover_count}")
        cover_jpg = temporary_dir / "cover.jpg"
        still_filter = build_cover_filter(cover_probe.width, cover_probe.height, job.settings)
        still_args = [
            str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-i", str(job.cover_path),
            "-vf", still_filter, "-frames:v", "1", "-q:v", "2", "-update", "1",
            "-loglevel", "error", str(cover_jpg),
        ]
        self._run(still_args, token, None, None, log)
        output = temporary_dir / "visual_with_cover.mp4"
        graph, label = build_cover_concat_filtergraph(body_timeline.body_frames, job.settings)
        concat_args = [
            str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", "-i", str(cover_clip), "-i", str(body_video),
            "-filter_complex", graph, "-map", label, "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(job.settings.fps), "-fps_mode", "cfr",
            "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(output),
        ]
        duration = (body_timeline.body_frames + job.settings.cover_frames) / job.settings.fps
        self._run(concat_args, token, duration, lambda fraction: emit("添加五帧封面", 80 + 5 * fraction), log)
        combined_count = probe_media(output, self.capabilities.ffprobe_path, count_frames=True).frame_count
        expected = body_timeline.body_frames + job.settings.cover_frames
        if combined_count is None or abs(combined_count - expected) > 1:
            raise RenderError(f"封面合并帧数错误：期望 {expected}，实际 {combined_count}")
        return output, cover_jpg

    def _encode_final(
        self,
        visual_video: Path,
        body_audio: Path | None,
        subtitle_path: Path | None,
        timeline: TimelinePlan,
        job: RenderJob,
        part_path: Path,
        token: CancellationToken,
        emit: Callable[[str, float], None],
        log: LogCallback,
    ) -> str:
        audio_plan = build_audio_plan(job, timeline)
        logo_index: int | None = None
        source_index: int | None = None
        music_index: int | None = None
        inputs = ["-i", str(visual_video)]
        next_index = 1
        if job.logo_path is not None:
            logo_index = next_index
            inputs.extend(
                [
                    "-loop", "1", "-framerate", str(job.settings.fps),
                    "-i", str(job.logo_path),
                ]
            )
            next_index += 1
        if body_audio is not None:
            source_index = next_index
            inputs.extend(["-i", str(body_audio)])
            next_index += 1
        if job.music_path is not None:
            music_index = next_index
            if audio_plan.loop_music:
                inputs.extend(["-stream_loop", "-1"])
            inputs.extend(["-i", str(job.music_path)])
        video_graph, video_label = build_final_video_filter(
            job.settings,
            timeline.total_frames,
            subtitle_path,
            logo_input_index=logo_index,
        )
        audio_graph = build_final_audio_filtergraph(
            audio_plan,
            source_input_index=source_index,
            music_input_index=music_index,
        )
        graph = video_graph
        audio_label: str | None = None
        if audio_graph:
            graph = f"{graph};{audio_graph[0]}"
            audio_label = audio_graph[1]
        requested = self._select_encoder(job)
        if requested == "libx264" and job.settings.video_encoder != VideoEncoder.X264:
            log("NVENC 实际探测不可用，最终视频编码使用 libx264；补帧模式保持不变。")
        encoder = requested
        log(f"输出质量：{job.settings.output_quality.value}")
        result = self._run_final_command(
            inputs,
            graph,
            video_label,
            audio_label,
            requested,
            job.settings.output_quality,
            timeline,
            part_path,
            token,
            emit,
            log,
            allow_failure=requested == "h264_nvenc",
        )
        if not result.succeeded:
            if result.cancelled:
                raise RenderCancelled("任务已取消")
            if requested == "h264_nvenc" and self._is_nvenc_initialization_failure(result.stderr):
                log("NVENC 编码器初始化失败，按规则仅将最终编码回退到 libx264；补帧模式保持不变。")
                part_path.unlink(missing_ok=True)
                encoder = "libx264"
                self._run_final_command(
                    inputs,
                    graph,
                    video_label,
                    audio_label,
                    encoder,
                    job.settings.output_quality,
                    timeline,
                    part_path,
                    token,
                    emit,
                    log,
                    allow_failure=False,
                )
            else:
                raise RenderError(self._ffmpeg_error("最终编码失败", result.stderr))
        return encoder

    def _run_final_command(
        self,
        inputs: list[str],
        graph: str,
        video_label: str,
        audio_label: str | None,
        encoder: str,
        output_quality: OutputQuality,
        timeline: TimelinePlan,
        part_path: Path,
        token: CancellationToken,
        emit: Callable[[str, float], None],
        log: LogCallback,
        *,
        allow_failure: bool,
    ):
        args = [str(self.capabilities.ffmpeg_path), "-hide_banner", "-y", *inputs, "-filter_complex", graph]
        args.extend(["-map", video_label])
        if audio_label:
            args.extend(["-map", audio_label, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
        args.extend(build_video_encoding_args(encoder, output_quality))
        args.extend(
            [
                "-pix_fmt", "yuv420p", "-r", str(timeline.fps), "-fps_mode", "cfr",
                "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", "-loglevel", "error",
                str(part_path),
            ]
        )
        result = run_ffmpeg(
            args,
            token,
            lambda fraction: emit("字幕、配乐与成片编码", 85 + 14 * fraction),
            expected_duration_seconds=timeline.duration_seconds,
            log_callback=log,
        )
        if not allow_failure:
            self._ensure_success(result, "最终编码失败")
        return result

    def _select_encoder(self, job: RenderJob) -> str:
        if job.settings.video_encoder == VideoEncoder.X264:
            return "libx264"
        if self.capabilities.nvenc_usable:
            return "h264_nvenc"
        return "libx264"

    @staticmethod
    def _is_nvenc_initialization_failure(stderr: str) -> bool:
        lowered = stderr.lower()
        markers = (
            "cannot load libcuda",
            "no capable devices found",
            "failed to initialize nvenc",
            "openencodesessionex failed",
            "error while opening encoder",
            "unsupported device",
        )
        return any(marker in lowered for marker in markers)

    def _run(
        self,
        args: list[str],
        token: CancellationToken,
        duration: float | None,
        progress: Callable[[float], None] | None,
        log: LogCallback,
    ) -> None:
        result = run_ffmpeg(
            args,
            token,
            progress,
            expected_duration_seconds=duration,
            log_callback=log,
        )
        self._ensure_success(result, "FFmpeg 处理失败")

    @staticmethod
    def _ensure_success(result: object, prefix: str) -> None:
        if result.cancelled:  # type: ignore[attr-defined]
            raise RenderCancelled("任务已取消")
        if not result.succeeded:  # type: ignore[attr-defined]
            raise RenderError(Renderer._ffmpeg_error(prefix, result.stderr))  # type: ignore[attr-defined]

    @staticmethod
    def _ffmpeg_error(prefix: str, stderr: str) -> str:
        lines = [line for line in stderr.splitlines() if line.strip()]
        detail = "\n".join(lines[-20:]) or "没有错误输出"
        return f"{prefix}（请查看任务日志）：\n{detail}"

    @staticmethod
    def _check_cancel(token: CancellationToken) -> None:
        if token.cancelled:
            raise RenderCancelled("任务已取消")

    @staticmethod
    def _write_report(
        report_path: Path,
        job: RenderJob,
        output_path: Path,
        cover_path: Path | None,
        timeline: TimelinePlan,
        encoder: str,
        verification: object,
        elapsed_seconds: float,
    ) -> None:
        payload = {
            "output": output_path.name,
            "cover": cover_path.name if cover_path else None,
            "logo": job.logo_path.name if job.logo_path else None,
            "source_order": [item.display_name for item in job.video_items],
            "encoder": encoder,
            "settings": {
                "width": job.settings.width,
                "height": job.settings.height,
                "fps": job.settings.fps,
                "transition_frames": job.settings.transition_frames,
                "cover_frames": timeline.cover_frames,
                "interpolation_mode": job.settings.interpolation_mode.value,
                "source_audio_mode": job.settings.source_audio_mode.value,
                "music_volume": job.settings.music_volume,
                "output_quality": job.settings.output_quality.value,
                "mirror_second_clip": job.settings.mirror_second_clip,
                "mirrored_clip_indices": [2]
                if job.settings.mirror_second_clip and len(job.video_items) >= 2
                else [],
                "subtitle_font_name": job.settings.subtitle_style.font_name,
                "logo_start_frame": job.settings.logo_start_frame if job.logo_path else None,
                "logo_scale_percent": job.settings.logo_scale_percent if job.logo_path else None,
                "logo_opacity_percent": job.settings.logo_opacity_percent if job.logo_path else None,
            },
            "timeline": {
                "clip_frames": list(timeline.frame_counts),
                "transition_offsets_frames": list(timeline.transition_offsets_frames),
                "body_frames": timeline.body_frames,
                "cover_frames": timeline.cover_frames,
                "total_frames": timeline.total_frames,
                "duration_seconds": timeline.duration_seconds,
            },
            "verified": verification.valid,  # type: ignore[attr-defined]
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
        temporary = report_path.with_name(f".{report_path.name}.{uuid.uuid4().hex}.part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, report_path)
