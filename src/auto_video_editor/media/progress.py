from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence

from ..models import ProcessResult


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def _reader(stream: object, kind: str, messages: queue.Queue[tuple[str, str | None]]) -> None:
    try:
        for line in stream:  # type: ignore[union-attr]
            messages.put((kind, line.rstrip("\r\n")))
    finally:
        messages.put((f"{kind}_eof", None))


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if process.stdin:
            process.stdin.write("q\n")
            process.stdin.flush()
        process.wait(timeout=2.0)
        return
    except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
        if process.poll() is not None:
            return
    if sys.platform == "win32":
        killer = subprocess.Popen(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        try:
            killer.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            killer.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3.0)


def run_ffmpeg(
    args: Sequence[str],
    cancel_token: CancellationToken,
    progress_callback: Callable[[float], None] | None = None,
    *,
    expected_duration_seconds: float | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> ProcessResult:
    command = tuple(str(value) for value in args)
    if not command:
        raise ValueError("FFmpeg 命令不能为空")
    if log_callback:
        log_callback(f"执行参数：{list(command)!r}")
    process = subprocess.Popen(
        list(command),
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_creation_flags(),
    )
    assert process.stdout is not None and process.stderr is not None
    messages: queue.Queue[tuple[str, str | None]] = queue.Queue()
    stdout_thread = threading.Thread(target=_reader, args=(process.stdout, "stdout", messages), daemon=True)
    stderr_thread = threading.Thread(target=_reader, args=(process.stderr, "stderr", messages), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    stderr_lines: list[str] = []
    eof = set()
    cancelled = False
    last_fraction = 0.0
    while process.poll() is None or len(eof) < 2:
        if cancel_token.cancelled and not cancelled:
            cancelled = True
            _stop_process(process)
        try:
            kind, line = messages.get(timeout=0.1)
        except queue.Empty:
            continue
        if kind.endswith("_eof"):
            eof.add(kind)
            continue
        if line is None:
            continue
        if kind == "stderr":
            stderr_lines.append(line)
            if log_callback:
                log_callback(line)
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"out_time_us", "out_time_ms"} and expected_duration_seconds and expected_duration_seconds > 0:
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                continue
            fraction = min(0.99, max(last_fraction, seconds / expected_duration_seconds))
            if fraction > last_fraction:
                last_fraction = fraction
                if progress_callback:
                    progress_callback(fraction)
    return_code = process.wait()
    stdout_thread.join(timeout=1.0)
    stderr_thread.join(timeout=1.0)
    if progress_callback and return_code == 0 and not cancelled:
        progress_callback(1.0)
    result = ProcessResult(command, return_code, "\n".join(stderr_lines), cancelled)
    if log_callback:
        log_callback(f"FFmpeg 返回码：{return_code}")
    return result
