"""Editor automático de vídeo 9:16 (1080x1920) com FFmpeg: montagem, transições, áudio ducking, SFX e legendas ASS."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import functools
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import soundfile as sf

from app.audio_assets import resolve_music_track, resolve_sfx_path
from app.config import get_ffmpeg_executable, load_settings
from app.models import StoryboardDocument
from app.video_modes import probe_video_metadata

logger = logging.getLogger("roblox_ai_shorts_studio")

TRANSITION_CYCLE = ["fade", "slideleft", "wipeleft", "smoothleft", "dissolve"]


class VideoEditorError(RuntimeError):
    """Erro durante a montagem ou exportação no FFmpeg."""


@functools.lru_cache(maxsize=4)
def _check_nvenc_available(ffmpeg_exe: str) -> bool:
    """Testa rapidamente se o encoder NVIDIA NVENC (h264_nvenc) está operacional nesta GPU/FFmpeg."""
    try:
        proc = subprocess.run(
            [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=128x128:d=0.1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=6,
        )
        return proc.returncode == 0
    except Exception:
        return False


def get_video_encode_args(
    ffmpeg_exe: str,
    preset: str = "fast",
    crf: int = 20,
    use_gpu: bool = True,
    codec: str = "libx264",
) -> List[str]:
    """Retorna argumentos otimizados de codificação (NVENC em GPU NVIDIA/Colab ou libx264 multi-thread)."""
    if use_gpu and codec == "libx264" and _check_nvenc_available(ffmpeg_exe):
        nv_preset = "p1" if preset in ("ultrafast", "superfast") else ("p4" if preset in ("veryfast", "fast") else "p5")
        return ["-c:v", "h264_nvenc", "-preset", nv_preset, "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    return ["-c:v", codec, "-preset", preset, "-crf", str(crf), "-threads", "0"]


def _run_ffmpeg(cmd: List[str], cwd: Optional[Path] = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "")[-1200:]
        raise VideoEditorError(f"FFmpeg retornou erro ({proc.returncode}):\n{err_tail}")


def normalize_scene_clip(
    ffmpeg_exe: str,
    src_video: Path,
    dest_video: Path,
    target_duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    use_gpu: bool = True,
) -> Path:
    """
    Padroniza cada clipe de cena para 1080x1920 (9:16) sem esticar ou deformar os personagens,
    ajustando exatamente para a duração da cena (corta sobra ou aplica loop suave se o clipe for menor).
    """
    meta = probe_video_metadata(src_video)
    src_dur = float(meta.get("duration") or 0.0)
    needs_loop = src_dur > 0.1 and src_dur < (target_duration - 0.05)

    cmd = [ffmpeg_exe, "-y"]
    if needs_loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(["-i", str(src_video)])

    # Enquadramento vertical 9:16 sem distorção (mantém proporção original com corte centralizado limpo)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p"
    )
    # Clipe intermediário temporário: preset ultrafast + crf 17 preserva qualidade máxima e acelera 3x!
    enc_args = get_video_encode_args(ffmpeg_exe, preset="ultrafast", crf=17, use_gpu=use_gpu)
    cmd.extend(
        [
            "-t",
            f"{target_duration:.3f}",
            "-vf",
            vf,
            *enc_args,
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest_video),
        ]
    )
    dest_video.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(cmd)
    return dest_video


def assemble_video_scenes(
    ffmpeg_exe: str,
    normalized_clips: List[Path],
    clip_durations: List[float],
    dest_video: Path,
    transition_duration: float = 0.30,
    use_gpu: bool = True,
) -> Path:
    """Concatena as cenas padronizadas aplicando transições xfade limpas entre cortes."""
    if not normalized_clips:
        raise VideoEditorError("Nenhum clipe de cena disponível para montagem.")

    if len(normalized_clips) == 1:
        _run_ffmpeg([ffmpeg_exe, "-y", "-i", str(normalized_clips[0]), "-c", "copy", str(dest_video)])
        return dest_video

    inputs: List[str] = []
    for p in normalized_clips:
        inputs.extend(["-i", str(p)])

    filter_parts: List[str] = []
    for idx in range(len(normalized_clips)):
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,format=yuv420p[s{idx}]")

    prev = "s0"
    running_offset = clip_durations[0] - transition_duration
    for idx in range(1, len(normalized_clips)):
        trans = TRANSITION_CYCLE[(idx - 1) % len(TRANSITION_CYCLE)]
        out_lbl = f"m{idx}"
        safe_offset = max(0.1, running_offset)
        filter_parts.append(
            f"[{prev}][s{idx}]xfade=transition={trans}:duration={transition_duration:.2f}:offset={safe_offset:.3f}[{out_lbl}]"
        )
        prev = out_lbl
        running_offset = safe_offset + clip_durations[idx] - transition_duration

    enc_args = get_video_encode_args(ffmpeg_exe, preset="ultrafast", crf=17, use_gpu=use_gpu)
    cmd = [
        ffmpeg_exe,
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        f"[{prev}]",
        *enc_args,
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dest_video),
    ]
    _run_ffmpeg(cmd)
    return dest_video


def mix_audio_tracks(
    ffmpeg_exe: str,
    narration_wav: Path,
    storyboard: StoryboardDocument,
    scene_timings: List[Dict[str, float | int]],
    music_mood: str,
    dest_audio_wav: Path,
    settings: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Mixa narração em primeiro plano + música instrumental gratuita em volume baixo + efeitos sonoros sincronizados.
    """
    cfg = settings or load_settings()
    music_vol = float(cfg["video"].get("music_volume", 0.16))
    sfx_vol = float(cfg["video"].get("sfx_volume", 0.42))

    info = sf.info(str(narration_wav))
    total_dur = max(1.0, float(info.duration))

    music_path = resolve_music_track(music_mood, cfg)

    inputs: List[str] = ["-i", str(narration_wav)]
    filters: List[str] = ["[0:a]aresample=44100,aformat=channel_layouts=stereo,volume=1.0[narr]"]
    mix_labels: List[str] = ["[narr]"]
    in_idx = 1

    if music_path and music_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])
        fade_out_start = max(0.0, total_dur - 1.5)
        filters.append(
            f"[{in_idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"atrim=0:{total_dur:.3f},volume={music_vol:.2f},"
            f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.2f}:d=1.5[bgm]"
        )
        mix_labels.append("[bgm]")
        in_idx += 1

    # Posiciona efeitos sonoros (transições e impactos de surpresa) exatamente nos cortes reais das cenas
    timing_map = {int(t["scene_number"]): float(t["start"]) for t in scene_timings}
    for scene in storyboard.scenes:
        if scene.scene_number == 1 and scene.sfx_cue == "transition":
            continue
        sfx_path = resolve_sfx_path(scene.sfx_cue, cfg)
        if not sfx_path or not sfx_path.exists():
            continue
        start_ms = max(0, int(round(timing_map.get(scene.scene_number, 0.0) * 1000)))
        if start_ms >= int(total_dur * 1000) - 150:
            continue
        inputs.extend(["-i", str(sfx_path)])
        vol = sfx_vol if scene.sfx_cue == "surprise" else (sfx_vol * 0.65)
        lbl = f"sfx{in_idx}"
        filters.append(
            f"[{in_idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"volume={vol:.2f},adelay={start_ms}|{start_ms}[{lbl}]"
        )
        mix_labels.append(f"[{lbl}]")
        in_idx += 1

    if len(mix_labels) == 1:
        filters.append("[narr]alimiter=limit=0.95[aout]")
    else:
        filters.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )

    dest_audio_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[aout]",
        "-t",
        f"{total_dur:.3f}",
        "-c:a",
        "pcm_s16le",
        str(dest_audio_wav),
    ]
    _run_ffmpeg(cmd)
    return dest_audio_wav


def render_final_short(
    project_dir: Path,
    storyboard: StoryboardDocument,
    narration_wav: Path,
    subtitles_ass: Optional[Path],
    scene_timings: List[Dict[str, float | int]],
    music_mood: str = "suspense",
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, Dict[str, float | int]]:
    """
    Pipeline completo do Editor Automático FFmpeg:
    1. Normaliza todos os clipes para 1080x1920 9:16 sem distorcer personagens.
    2. Aplica transições sincronizadas com os tempos reais da narração.
    3. Mixa narração + música em volume reduzido + SFX nos cortes.
    4. Queima legendas ASS sincronizadas (se fornecidas).
    5. Exporta `output/final.mp4` em H.264 + AAC pronto para YouTube Shorts e TikTok.
    """
    cfg = settings or load_settings()
    ffmpeg_exe = get_ffmpeg_executable(cfg)
    if not ffmpeg_exe:
        raise VideoEditorError("FFmpeg não encontrado no sistema ou no ambiente virtual.")

    vid_cfg = cfg["video"]
    width = int(vid_cfg.get("width", 1080))
    height = int(vid_cfg.get("height", 1920))
    fps = int(vid_cfg.get("fps", 30))
    trans_dur = float(vid_cfg.get("transition_duration", 0.30))
    use_gpu = bool(vid_cfg.get("use_gpu_acceleration", True))
    cleanup_temp = bool(vid_cfg.get("cleanup_temp_work", True))

    temp_dir = project_dir / "output" / "_work"
    temp_dir.mkdir(parents=True, exist_ok=True)

    timing_by_scene = {int(t["scene_number"]): t for t in scene_timings}
    num_scenes = len(storyboard.scenes)
    norm_tasks: List[Tuple[int, Path, Path, float]] = []

    for idx, scene in enumerate(storyboard.scenes):
        if not scene.video_path or not Path(scene.video_path).exists():
            raise VideoEditorError(f"Clipe da cena {scene.scene_number:02d} ausente: {scene.video_path}")
        tinfo = timing_by_scene.get(scene.scene_number)
        base_dur = float(tinfo["duration"]) if tinfo else float(scene.duration_seconds)
        # Compensa a sobreposição do xfade para manter a sincronia exata com a narração
        extra = trans_dur if idx < (num_scenes - 1) else 0.0
        target_dur = max(1.0, base_dur + extra)
        norm_path = temp_dir / f"norm_{scene.scene_number:02d}.mp4"
        norm_tasks.append((idx, Path(scene.video_path), norm_path, target_dur))

    # Normaliza cenas em paralelo (2-4x mais rápido em CPU multi-core e Colab)
    max_workers = min(4, max(1, (os.cpu_count() or 2)), len(norm_tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                normalize_scene_clip,
                ffmpeg_exe,
                src_p,
                norm_p,
                target_dur,
                width,
                height,
                fps,
                use_gpu,
            )
            for _, src_p, norm_p, target_dur in norm_tasks
        ]
        for fut in futures:
            fut.result()

    normalized_clips = [norm_p for _, _, norm_p, _ in norm_tasks]
    clip_durations = [target_dur for _, _, _, target_dur in norm_tasks]

    assembled_video = temp_dir / "assembled_silent.mp4"
    assemble_video_scenes(
        ffmpeg_exe=ffmpeg_exe,
        normalized_clips=normalized_clips,
        clip_durations=clip_durations,
        dest_video=assembled_video,
        transition_duration=trans_dur,
        use_gpu=use_gpu,
    )

    mixed_audio = temp_dir / "mixed_audio.wav"
    mix_audio_tracks(
        ffmpeg_exe=ffmpeg_exe,
        narration_wav=narration_wav,
        storyboard=storyboard,
        scene_timings=scene_timings,
        music_mood=music_mood,
        dest_audio_wav=mixed_audio,
        settings=cfg,
    )

    final_mp4 = project_dir / "output" / "final.mp4"
    final_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Usa caminho relativo a partir de project_dir para o filtro ass= funcionar sem erros de barra/dois-pontos no Windows
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(assembled_video),
        "-i",
        str(mixed_audio),
    ]
    if subtitles_ass and subtitles_ass.exists():
        try:
            rel_ass = subtitles_ass.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            rel_ass = subtitles_ass.as_posix().replace(":", "\\:")
        cmd.extend(["-vf", f"ass={rel_ass}"])

    final_enc_args = get_video_encode_args(
        ffmpeg_exe=ffmpeg_exe,
        preset=str(vid_cfg.get("preset", "medium")),
        crf=int(vid_cfg.get("crf", 20)),
        use_gpu=use_gpu,
        codec=str(vid_cfg.get("video_codec", "libx264")),
    )
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *final_enc_args,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            str(vid_cfg.get("audio_codec", "aac")),
            "-b:a",
            str(vid_cfg.get("audio_bitrate", "192k")),
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            "-shortest",
            str(final_mp4),
        ]
    )
    _run_ffmpeg(cmd, cwd=project_dir)

    meta = probe_video_metadata(final_mp4)
    if cleanup_temp:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return final_mp4, meta
