from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def folder_signature(folder: Path) -> tuple[int, int, int]:
    files = [path for path in folder.iterdir() if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)
    latest = max((path.stat().st_mtime_ns for path in files), default=0)
    return len(files), total_size, latest


@dataclass
class FolderStabilityTracker:
    seen: set[Path] = field(default_factory=set)
    candidates: dict[Path, tuple[int, int, int]] = field(default_factory=dict)

    def arm(self, root: Path, *, excluded: Path | None = None) -> None:
        excluded_resolved = excluded.resolve(strict=False) if excluded else None
        self.seen = {
            path.resolve(strict=False)
            for path in root.iterdir()
            if path.is_dir()
            and (excluded_resolved is None or path.resolve(strict=False) != excluded_resolved)
        }
        self.candidates.clear()

    def poll(self, root: Path, *, excluded: Path | None = None) -> tuple[Path, ...]:
        if not root.is_dir():
            return ()
        excluded_resolved = excluded.resolve(strict=False) if excluded else None
        ready: list[Path] = []
        present: set[Path] = set()
        for raw_path in root.iterdir():
            if not raw_path.is_dir():
                continue
            path = raw_path.resolve(strict=False)
            if excluded_resolved is not None and path == excluded_resolved:
                continue
            present.add(path)
            if path in self.seen:
                continue
            try:
                signature = folder_signature(path)
            except OSError:
                continue
            previous = self.candidates.get(path)
            self.candidates[path] = signature
            if previous == signature and signature[0] > 0:
                ready.append(path)
        self.candidates = {
            path: signature for path, signature in self.candidates.items() if path in present and path not in self.seen
        }
        return tuple(sorted(ready, key=lambda path: path.name.casefold()))

    def mark_processed(self, paths: tuple[Path, ...]) -> None:
        for path in paths:
            resolved = path.resolve(strict=False)
            self.seen.add(resolved)
            self.candidates.pop(resolved, None)
