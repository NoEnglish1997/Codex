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
        fadein_duration_seconds=min(settings.music_fadein_seconds, timeline.duration_seconds),
        normalize_audio=settings.normalize_audio,
        loudness_target_lufs=settings.loudness_target_lufs,
        duck_music_under_source=settings.duck_music_under_source,
    )


def _loudness_filter(plan: AudioPlan) -> str:
    return (
        f"loudnorm=I={plan.loudness_target_lufs:.1f}:LRA=11:TP=-1.5,"
        if plan.normalize_audio
        else ""
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
            f"{_loudness_filter(plan)}atrim=duration={duration:.9f},asetpts=N/SR/TB[source]"
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
        if plan.normalize_audio:
            music_filters.insert(2, _loudness_filter(plan).rstrip(","))
        if plan.fadein_duration_seconds > 0:
            music_filters.append(f"afade=t=in:st=0:d={plan.fadein_duration_seconds:.9f}")
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
    elif plan.duck_music_under_source and set(labels) == {"source", "music"}:
        chains.append("[source]asplit=2[source_mix][source_side]")
        chains.append(
            "[music][source_side]sidechaincompress=threshold=0.05:ratio=8:"
            "attack=20:release=300[ducked_music]"
        )
        chains.append(
            f"[source_mix][ducked_music]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={duration:.9f},asetpts=N/SR/TB[aout]"
        )
    else:
        inputs = "".join(f"[{label}]" for label in labels)
        chains.append(
            f"{inputs}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={duration:.9f},asetpts=N/SR/TB[aout]"
        )
    return ";".join(chains), "[aout]"


def build_single_pass_audio_filtergraph(
    plan: AudioPlan,
    timeline: TimelinePlan,
    *,
    source_input_indices: tuple[int | None, ...],
    music_input_index: int | None,
    clip_ranges: tuple[tuple[float, float], ...] | None = None,
) -> tuple[str, str] | None:
    """Build source crossfades and music mixing directly from original inputs."""
    chains: list[str] = []
    labels: list[str] = []
    if plan.include_source:
        if len(source_input_indices) != len(timeline.frame_counts):
            raise ValueError("原声音轨数量与视频时间线不一致")
        for index, (input_index, frame_count) in enumerate(
            zip(source_input_indices, timeline.frame_counts, strict=True)
        ):
            duration = frame_count / timeline.fps
            if input_index is None:
                chains.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.9f},"
                    f"asetpts=N/SR/TB[source_clip{index}]"
                )
            else:
                source_trim = ""
                if clip_ranges:
                    start, end = clip_ranges[index]
                    source_trim = f"atrim=start={start:.9f}:end={end:.9f},"
                chains.append(
                    f"[{input_index}:a]{source_trim}aresample=48000,"
                    "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                    f"asetpts=PTS-STARTPTS,apad,atrim=duration={duration:.9f},"
                    f"asetpts=N/SR/TB[source_clip{index}]"
                )
        current = "source_clip0"
        transition_seconds = 0.0
        if len(timeline.frame_counts) > 1:
            transition_frames = (
                sum(timeline.frame_counts) - timeline.body_frames
            ) / (len(timeline.frame_counts) - 1)
            transition_seconds = transition_frames / timeline.fps
        if transition_seconds <= 0 and len(source_input_indices) > 1:
            inputs = "".join(f"[source_clip{index}]" for index in range(len(source_input_indices)))
            chains.append(f"{inputs}concat=n={len(source_input_indices)}:v=0:a=1[source_concat]")
            current = "source_concat"
        else:
            for index in range(1, len(source_input_indices)):
                output = f"source_xf{index}"
                chains.append(
                    f"[{current}][source_clip{index}]acrossfade=d={transition_seconds:.9f}:"
                    f"c1=tri:c2=tri[{output}]"
                )
                current = output
        body_duration = timeline.body_frames / timeline.fps
        delay = f"adelay=delays={plan.source_delay_samples}S:all=1," if plan.source_delay_samples else ""
        chains.append(
            f"[{current}]atrim=duration={body_duration:.9f},asetpts=N/SR/TB,"
            f"{_loudness_filter(plan)}{delay}apad,atrim=duration={plan.total_duration_seconds:.9f},"
            "asetpts=N/SR/TB[source]"
        )
        labels.append("source")

    if music_input_index is not None:
        music_filters = [
            "aresample=48000",
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        ]
        if not plan.loop_music:
            music_filters.append("apad")
        music_filters.extend(
            [
                f"volume={plan.music_volume:.6f}",
                f"atrim=duration={plan.total_duration_seconds:.9f}",
            ]
        )
        if plan.normalize_audio:
            music_filters.insert(2, _loudness_filter(plan).rstrip(","))
        if plan.fadein_duration_seconds > 0:
            music_filters.append(f"afade=t=in:st=0:d={plan.fadein_duration_seconds:.9f}")
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
            f"[{labels[0]}]atrim=duration={plan.total_duration_seconds:.9f},"
            "asetpts=N/SR/TB[aout]"
        )
    elif plan.duck_music_under_source and set(labels) == {"source", "music"}:
        chains.append("[source]asplit=2[source_mix][source_side]")
        chains.append(
            "[music][source_side]sidechaincompress=threshold=0.05:ratio=8:"
            "attack=20:release=300[ducked_music]"
        )
        chains.append(
            f"[source_mix][ducked_music]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={plan.total_duration_seconds:.9f},"
            "asetpts=N/SR/TB[aout]"
        )
    else:
        inputs = "".join(f"[{label}]" for label in labels)
        chains.append(
            f"{inputs}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={plan.total_duration_seconds:.9f},"
            "asetpts=N/SR/TB[aout]"
        )
    return ";".join(chains), "[aout]"
