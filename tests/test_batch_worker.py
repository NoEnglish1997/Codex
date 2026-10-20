from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from auto_video_editor.models import (
    BatchFailure,
    BatchRenderTask,
    FFmpegCapabilities,
    RenderJob,
)
from auto_video_editor.ui.batch_render_worker import BatchRenderWorker


def _task(tmp_path: Path, index: int) -> BatchRenderTask:
    source = tmp_path / f"素材{index}"
    source.mkdir()
    job = RenderJob((), None, None, None, tmp_path, f"成片_{index}.mp4")
    return BatchRenderTask(source, job)


def test_batch_worker_continues_after_one_render_failure(tmp_path):
    capabilities = FFmpegCapabilities(
        Path("ffmpeg"),
        Path("ffprobe"),
        "ffmpeg test",
        "ffprobe test",
        frozenset(),
        frozenset(),
        False,
    )
    worker = BatchRenderWorker(
        tuple(_task(tmp_path, index) for index in range(1, 4)),
        (BatchFailure("预检失败目录", "缺少字幕"),),
        capabilities,
    )

    class FakeRenderer:
        def render(self, job, token, progress, log):
            progress("模拟处理", 50)
            if job.output_filename == "成片_2.mp4":
                raise RuntimeError("模拟 FFmpeg 失败")
            return SimpleNamespace(output_path=tmp_path / job.output_filename)

    worker.renderer = FakeRenderer()
    completed = []
    failed = []
    done = []
    progress = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failed.append)
    worker.done.connect(lambda: done.append(True))
    worker.progress.connect(lambda stage, value: progress.append((stage, value)))

    worker.run()

    assert not failed
    assert done == [True]
    assert len(completed) == 1
    assert len(completed[0].successes) == 2
    assert [(item.source_name, item.message) for item in completed[0].failures] == [
        ("预检失败目录", "缺少字幕"),
        ("素材2", "模拟 FFmpeg 失败"),
    ]
    assert progress[-1] == ("批量任务完成", 100)
