from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..media.progress import CancellationToken
from ..media.renderer import RenderCancelled, Renderer
from ..models import FFmpegCapabilities, RenderJob


class RenderWorker(QObject):
    progress = Signal(str, int)
    log = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()

    def __init__(self, job: RenderJob, capabilities: FFmpegCapabilities, cache_root: Path | None = None) -> None:
        super().__init__()
        self.job = job
        self.renderer = Renderer(capabilities, cache_root=cache_root)
        self.token = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            result = self.renderer.render(
                self.job,
                self.token,
                lambda stage, value: self.progress.emit(stage, value),
                self.log.emit,
            )
            self.succeeded.emit(result)
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.done.emit()

    def cancel(self) -> None:
        self.token.cancel()
