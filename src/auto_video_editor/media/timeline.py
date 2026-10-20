from __future__ import annotations

from collections.abc import Iterable

from ..models import TimelinePlan


def calculate_timeline(
    frame_counts: Iterable[int],
    has_cover: bool,
    *,
    fps: int = 60,
    transition_frames: int = 60,
    cover_frames: int = 5,
) -> TimelinePlan:
    counts = tuple(int(value) for value in frame_counts)
    if not counts:
        raise ValueError("至少需要一个视频片段")
    if fps <= 0 or transition_frames < 0 or cover_frames < 0:
        raise ValueError("帧率和帧数配置无效")
    if any(value <= 0 for value in counts):
        raise ValueError("片段帧数必须大于零")
    if len(counts) > 1 and any(value <= transition_frames for value in counts):
        raise ValueError("参与转场的片段必须长于转场本身")
    offsets: list[int] = []
    accumulated = counts[0]
    for index in range(1, len(counts)):
        offset = accumulated - transition_frames
        if offset < 0:
            raise ValueError("转场起点不能为负数")
        offsets.append(offset)
        accumulated = accumulated + counts[index] - transition_frames
    body_frames = sum(counts) - max(0, len(counts) - 1) * transition_frames
    actual_cover = cover_frames if has_cover else 0
    return TimelinePlan(
        frame_counts=counts,
        transition_offsets_frames=tuple(offsets),
        body_frames=body_frames,
        cover_frames=actual_cover,
        total_frames=body_frames + actual_cover,
        fps=fps,
    )
