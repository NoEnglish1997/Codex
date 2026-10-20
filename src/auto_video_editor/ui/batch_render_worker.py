from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..media.progress import CancellationToken
from ..media.renderer import RenderCancelled, Renderer
from ..models import (
    BatchFailure,
    BatchRenderSummary,
    BatchRenderTask,
    FFmpegCapabilities,
    RenderResult,
)


class BatchRenderWorker(QObject):
    progress = Signal(str, int)
    log = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()

    def __init__(
        self,
        tasks: tuple[BatchRenderTask, ...],
        initial_failures: tuple[BatchFailure, ...],
        capabilities: FFmpegCapabilities,
        cache_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.tasks = tasks
        self.initial_failures = initial_failures
        self.renderer = Renderer(capabilities, cache_root=cache_root)
        self.token = CancellationToken()

    @Slot()
    def run(self) -> None:
        successes: list[RenderResult] = []
        failures = list(self.initial_failures)
        total = len(self.tasks)
        try:
            for index, task in enumerate(self.tasks, 1):
                if self.token.cancelled:
                    raise RenderCancelled("任务已取消")
                self.log.emit(
                    f"===== [{index}/{total}] {task.source_dir.name} → "
                    f"{task.job.output_filename} ====="
                )

                def emit_progress(stage: str, value: int, *, current: int = index) -> None:
                    overall = round(((current - 1) + value / 100) / total * 100)
                    self.progress.emit(f"[{current}/{total}] {task.source_dir.name}：{stage}", overall)

                try:
                    result = self.renderer.render(
                        task.job,
                        self.token,
                        emit_progress,
                        self.log.emit,
                    )
                    successes.append(result)
                    self.log.emit(f"成功：{result.output_path}")
                except RenderCancelled:
                    raise
                except Exception as exc:
                    message = str(exc)
                    failures.append(BatchFailure(task.source_dir.name, message))
                    self.log.emit(f"失败：{task.source_dir.name}：{message}")
                    continue

            self.progress.emit("批量任务完成", 100)
            self.completed.emit(BatchRenderSummary(tuple(successes), tuple(failures)))
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.done.emit()

    def cancel(self) -> None:
        self.token.cancel()
