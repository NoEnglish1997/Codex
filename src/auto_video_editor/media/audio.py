from __future__ import annotations

from ..models import AudioPlan, MusicShortPolicy, RenderJob, SourceAudioMode, TimelinePlan


def build_audio_plan(job: RenderJob, timeline: TimelinePlan) -> AudioPlan:
    settings = job.settings
    include_source = settings.source_audio_mode == SourceAudioMode.MIX
    include_music = job.music_path is not None
    fade_duration = min(settings.music_fadeout_seconds, timeline.duration_seconds) if include_music else 0.0
    fade_start = max(0.0, timeline.duration_seconds - fade_duration) if fade_duration > 0 else None
    return AudioPlan(
        include_source=include_source,
        include_music=include_music,
        loop_music=include_music and settings.music_short_policy == MusicShortPolicy.LOOP,
        total_duration_seconds=timeline.duration_seconds,
        source_delay_samples=timeline.cover_frames * 48_000 // timeline.fps,
        music_volume=settings.music_volume,
        fadeout_start_seconds=fade_start,
        fadeout_duration_seconds=fade_duration,
    )


def build_source_acrossfade_filtergraph(
    input_count: int,
    body_duration_seconds: float,
    transition_seconds: float = 1.0,
) -> tuple[str, str]:
    if input_count <= 0:
        raise ValueError("至少需要一个原声音轨")
    chains = [
        f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:"
        f"channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
        for index in range(input_count)
    ]
    current = "a0"
    for index in range(1, input_count):
        output = f"ax{index}"
        chains.append(
            f"[{current}][a{index}]acrossfade=d={transition_seconds:.9f}:c1=tri:c2=tri[{output}]"
        )
        current = output
    chains.append(
        f"[{current}]atrim=duration={body_duration_seconds:.9f},asetpts=N/SR/TB[aout]"
    )
    return ";".join(chains), "[aout]"


def build_final_audio_filtergraph(
    plan: AudioPlan,
    *,
    source_input_index: int | None,
    music_input_index: int | None,
) -> tuple[str, str] | None:
    chains: list[str] = []
    labels: list[str] = []
    duration = plan.total_duration_seconds
    if source_input_index is not None:
        delay = f"adelay=delays={plan.source_delay_samples}S:all=1," if plan.source_delay_samples else ""
        chains.append(
            f"[{source_input_index}:a]{delay}aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"atrim=duration={duration:.9f},asetpts=N/SR/TB[source]"
        )
        labels.append("source")
    if music_input_index is not None:
        music_filters = [
            "aresample=48000",
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        ]
        if not plan.loop_music:
            music_filters.append("apad")
        music_filters.extend([f"volume={plan.music_volume:.6f}", f"atrim=duration={duration:.9f}"])
        if plan.fadeout_start_seconds is not None and plan.fadeout_duration_seconds > 0:
            music_filters.append(
                f"afade=t=out:st={plan.fadeout_start_seconds:.9f}:d={plan.fadeout_duration_seconds:.9f}"
            )
        music_filters.append("asetpts=N/SR/TB")
        chains.append(f"[{music_input_index}:a]{','.join(music_filters)}[music]")
        labels.append("music")
    if not labels:
        return None
    if len(labels) == 1:
        chains.append(
            f"[{labels[0]}]atrim=duration={duration:.9f},asetpts=N/SR/TB[aout]"
        )
    else:
        inputs = "".join(f"[{label}]" for label in labels)
        chains.append(
            f"{inputs}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={duration:.9f},asetpts=N/SR/TB[aout]"
        )
    return ";".join(chains), "[aout]"
