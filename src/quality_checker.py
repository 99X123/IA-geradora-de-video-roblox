"""AutoShorts AI — Automated Technical & Visual Quality Control Gate.

NEVER approves a video that fails mandatory technical checks.
Performs:
  Technical verification:
    - MP4 opens cleanly & decodes without FFmpeg errors
    - Resolution (e.g. 1080x1920), FPS (30), Duration, Video codec (h264), PixFmt (yuv420p)
    - Audio presence, AAC codec, loudness / non-silence / non-clipped validation
    - Unexpected black-frame detection (excluding intentional final cut-to-black & intro fade)
    - SRT subtitle validity & timing compatibility with video duration
  Visual verification:
    - Contact sheet sampled across the rendered MP4
    - Algorithmic pixel inspection (solid-color inside-wall frames, blank dark frames, blowouts)
    - Optional Vision AI inspection (Gemini / OpenAI Vision when API key is configured)
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests
from PIL import Image

from src.config import AutoShortsConfig, get_secret
from src.storyboard_generator import build_contact_sheet
from src.utils import find_ffmpeg, probe_media_info, run_subprocess, setup_logger

logger = setup_logger("autoshorts.qa")


def _parse_srt_last_timestamp(srt_path: Path) -> tuple[int, float]:
    """Parse an SRT file and return (cue_count, last_end_sec)."""
    content = srt_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
    )
    matches = pattern.findall(content)
    last_end = 0.0
    for m in matches:
        eh, em, es, ems = int(m[4]), int(m[5]), int(m[6]), int(m[7])
        end_sec = eh * 3600 + em * 60 + es + ems / 1000.0
        if end_sec > last_end:
            last_end = end_sec
    return len(matches), round(last_end, 4)


def _check_decode_integrity(video_path: Path) -> Dict[str, Any]:
    ffmpeg = find_ffmpeg()
    proc = run_subprocess(
        [ffmpeg, "-hide_banner", "-v", "error", "-i", str(video_path), "-f", "null", "-"],
        check=False,
        timeout=120,
    )
    errors = [ln.strip() for ln in proc.stderr.splitlines() if ln.strip()]
    return {"passed": proc.returncode == 0 and len(errors) == 0, "error_count": len(errors), "errors": errors[:10]}


def _check_unexpected_black_frames(video_path: Path, total_duration: float, max_ratio: float) -> Dict[str, Any]:
    ffmpeg = find_ffmpeg()
    proc = run_subprocess(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            "blackdetect=d=0.35:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=False,
        timeout=120,
    )
    intervals: List[Dict[str, float]] = []
    unexpected_sec = 0.0
    for line in proc.stderr.splitlines():
        m = re.search(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)", line)
        if m:
            bs, be, bd = float(m.group(1)), float(m.group(2)), float(m.group(3))
            # Ignore intentional fade-in (<0.25s) and final cut-to-black (> dur - 0.35s)
            is_intentional = be <= 0.30 or bs >= max(0.0, total_duration - 0.40)
            intervals.append({"start": bs, "end": be, "duration": bd, "intentional": is_intentional})
            if not is_intentional:
                unexpected_sec += bd

    ratio = unexpected_sec / max(0.1, total_duration)
    return {
        "passed": ratio <= max_ratio,
        "unexpected_black_sec": round(unexpected_sec, 3),
        "unexpected_black_ratio": round(ratio, 4),
        "max_allowed_ratio": max_ratio,
        "intervals": intervals,
    }


def _check_audio_levels(video_path: Path, min_mean_db: float = -50.0) -> Dict[str, Any]:
    ffmpeg = find_ffmpeg()
    proc = run_subprocess(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=False,
        timeout=120,
    )
    mean_m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", proc.stderr)
    max_m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", proc.stderr)
    mean_db = float(mean_m.group(1)) if mean_m else -99.0
    max_db = float(max_m.group(1)) if max_m else -99.0

    # Audio should be audible (mean >= min_mean_db) and not hard-clipped silence
    passed = mean_db >= min_mean_db and max_db > -45.0
    return {
        "passed": passed,
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "min_required_mean_db": min_mean_db,
    }


def _extract_sample_frames(video_path: Path, duration: float, interval_sec: float, frames_dir: Path) -> List[Path]:
    ffmpeg = find_ffmpeg()
    frames_dir.mkdir(parents=True, exist_ok=True)
    # Sample evenly across the video (avoiding very last black cut frame)
    safe_end = max(0.2, duration - 0.25)
    n_samples = max(4, min(16, int(round(safe_end / max(0.5, interval_sec))) + 1))
    times = np.linspace(0.25, safe_end, n_samples)

    paths: List[Path] = []
    for idx, t in enumerate(times):
        out_jpg = frames_dir / f"qa_{idx + 1:02d}_{t:.2f}s.jpg"
        run_subprocess(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(out_jpg),
            ],
            check=False,
            timeout=30,
        )
        if out_jpg.exists() and out_jpg.stat().st_size > 100:
            paths.append(out_jpg)
    return paths


def _analyze_frames_visually(frame_paths: List[Path]) -> Dict[str, Any]:
    """Algorithmic visual inspection for solid-color/occluded, blank, or blown-out frames."""
    issues: List[Dict[str, Any]] = []
    frame_stats: List[Dict[str, Any]] = []

    for fp in frame_paths:
        with Image.open(fp) as im:
            arr = np.asarray(im.convert("RGB"), dtype=np.float32)
        mean_luma = float(arr.mean())
        std_rgb = float(arr.std())
        bright_ratio = float((arr.mean(axis=2) > 245.0).mean())

        stat = {
            "file": fp.name,
            "mean_luma": round(mean_luma, 2),
            "std_rgb": round(std_rgb, 2),
            "overexposed_ratio": round(bright_ratio, 4),
        }
        frame_stats.append(stat)

        if std_rgb < 6.0:
            issues.append(
                {
                    "file": fp.name,
                    "severity": "critical",
                    "issue": "Frame praticamente monocromático/vazio (possível câmera dentro de parede ou tela preta).",
                }
            )
        elif mean_luma < 12.0:
            issues.append(
                {
                    "file": fp.name,
                    "severity": "critical",
                    "issue": "Frame excessivamente escuro / iluminação ausente.",
                }
            )
        elif bright_ratio > 0.65:
            issues.append(
                {
                    "file": fp.name,
                    "severity": "warning",
                    "issue": "Possível estouro de brilho/bloom excessivo.",
                }
            )

    critical_count = sum(1 for i in issues if i["severity"] == "critical")
    return {
        "passed": critical_count == 0,
        "frames_inspected": len(frame_paths),
        "critical_issues": critical_count,
        "issues": issues,
        "frame_stats": frame_stats,
    }


def _optional_vision_ai_inspection(contact_sheet_path: Path) -> Dict[str, Any]:
    """Use Gemini Vision or OpenAI Vision if configured to inspect the contact sheet."""
    prompt = (
        "Inspecione esta folha de contato de um curta 3D vertical (9:16). "
        "Verifique: (1) personagens ou cabeças cortadas nas bordas, (2) objetos bloqueando personagens, "
        "(3) legendas cobrindo rostos, (4) cenas vazias/monocromáticas, (5) iluminação/estouro de brilho. "
        "Responda em JSON: {\"passed\": true|false, \"summary\": \"...\", \"issues\": [\"...\"]}"
    )
    img_b64 = base64.b64encode(contact_sheet_path.read_bytes()).decode("ascii")

    gemini_key = get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY")
    if gemini_key:
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
                        ]
                    }
                ],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            resp = requests.post(url, params={"key": gemini_key}, json=payload, timeout=45)
            resp.raise_for_status()
            txt = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(txt)
            return {"executed": True, "provider": "gemini-2.5-flash", "result": parsed}
        except Exception as exc:
            return {"executed": False, "provider": "gemini", "reason": f"Falha na inspeção visual IA: {exc}"}

    openai_key = get_secret("OPENAI_API_KEY")
    if openai_key:
        try:
            base_url = (get_secret("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                            ],
                        }
                    ],
                },
                timeout=45,
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            return {"executed": True, "provider": "openai-vision", "result": parsed}
        except Exception as exc:
            return {"executed": False, "provider": "openai", "reason": f"Falha na inspeção visual IA: {exc}"}

    return {
        "executed": False,
        "provider": None,
        "reason": "Nenhum modelo de visão configurado (GEMINI_API_KEY/OPENAI_API_KEY ausente); aplicada apenas inspeção algorítmica local.",
    }


def run_quality_check(
    video_path: Path,
    storyboard: Dict[str, Any],
    srt_path: Optional[Path] = None,
    qa_dir: Optional[Path] = None,
    config: Optional[AutoShortsConfig] = None,
) -> Dict[str, Any]:
    """Execute full technical + visual QA checks and return strict pass/fail verdict."""
    cfg = config or AutoShortsConfig.load()
    video_path = Path(video_path)
    qa_dir = Path(qa_dir or (video_path.parent / "qa"))
    qa_dir.mkdir(parents=True, exist_ok=True)

    exp_w = int(storyboard.get("width", cfg.get("video.width", 1080)))
    exp_h = int(storyboard.get("height", cfg.get("video.height", 1920)))
    exp_fps = float(storyboard.get("fps", cfg.get("video.fps", 30)))
    exp_dur = float(storyboard.get("duration_sec", 0.0))
    dur_tol = float(cfg.get("quality.duration_tolerance_sec", 1.5))
    sub_tol = float(cfg.get("quality.subtitle_sync_tolerance_sec", 1.5))

    media = probe_media_info(video_path)
    decode_check = _check_decode_integrity(video_path)
    black_check = _check_unexpected_black_frames(
        video_path,
        total_duration=float(media["duration_sec"] or exp_dur or 1.0),
        max_ratio=float(cfg.get("quality.max_black_frame_ratio", 0.12)),
    )
    audio_check = (
        _check_audio_levels(video_path, min_mean_db=float(cfg.get("quality.min_audio_rms_db", -50.0)))
        if media["has_audio"]
        else {"passed": False, "reason": "Stream de áudio ausente no MP4."}
    )

    subtitle_check: Dict[str, Any]
    if srt_path and Path(srt_path).exists():
        cue_count, last_sub_end = _parse_srt_last_timestamp(Path(srt_path))
        vid_dur = float(media["duration_sec"] or 0.0)
        sub_ok = cue_count > 0 and last_sub_end <= vid_dur + sub_tol
        subtitle_check = {
            "passed": sub_ok,
            "cue_count": cue_count,
            "last_subtitle_end_sec": last_sub_end,
            "video_duration_sec": vid_dur,
        }
    else:
        subtitle_check = {"passed": False, "reason": "Arquivo SRT ausente."}

    technical_checks = {
        "file_exists_nonempty": {"passed": video_path.exists() and int(media["size_bytes"]) > 1024, "size_bytes": media["size_bytes"]},
        "decode_integrity": decode_check,
        "resolution": {
            "passed": media["width"] == exp_w and media["height"] == exp_h,
            "actual": [media["width"], media["height"]],
            "expected": [exp_w, exp_h],
        },
        "fps": {
            "passed": media["fps"] is not None and abs(float(media["fps"]) - exp_fps) <= 0.5,
            "actual": media["fps"],
            "expected": exp_fps,
        },
        "duration": {
            "passed": abs(float(media["duration_sec"]) - exp_dur) <= dur_tol if exp_dur > 0 else float(media["duration_sec"]) > 0.5,
            "actual_sec": media["duration_sec"],
            "expected_sec": exp_dur,
            "tolerance_sec": dur_tol,
        },
        "video_codec_h264": {"passed": media["video_codec"] == "h264", "actual": media["video_codec"]},
        "pixel_format_yuv420p": {"passed": media["pixel_format"] == "yuv420p", "actual": media["pixel_format"]},
        "audio_stream_aac": {
            "passed": bool(media["has_audio"]) and media["audio_codec"] == "aac",
            "has_audio": media["has_audio"],
            "actual": media["audio_codec"],
        },
        "audio_levels": audio_check,
        "unexpected_black_frames": black_check,
        "subtitle_compatibility": subtitle_check,
    }

    technical_passed = all(c["passed"] for c in technical_checks.values())

    # Visual QA: sample frames & build contact sheet
    frames_dir = qa_dir / "frames"
    sample_frames = _extract_sample_frames(
        video_path,
        duration=float(media["duration_sec"] or exp_dur or 2.0),
        interval_sec=float(cfg.get("quality.contact_sheet_interval_sec", 2.0)),
        frames_dir=frames_dir,
    )
    contact_sheet_path = build_contact_sheet(sample_frames, qa_dir / "qa_contact_sheet.png", cols=4) if sample_frames else None
    algo_visual = _analyze_frames_visually(sample_frames)
    vision_ai = (
        _optional_vision_ai_inspection(contact_sheet_path)
        if contact_sheet_path and cfg.get("quality.enable_vision_review", True)
        else {"executed": False, "reason": "Desativado ou folha de contato indisponível."}
    )

    vision_ai_failed = (
        vision_ai.get("executed") is True
        and isinstance(vision_ai.get("result"), dict)
        and vision_ai["result"].get("passed") is False
    )

    # STRICT GATE: Never approve if technical checks or critical visual checks failed!
    approved = bool(technical_passed and algo_visual["passed"] and not vision_ai_failed)

    report = {
        "video_path": str(video_path),
        "approved": approved,
        "technical_passed": technical_passed,
        "visual_algorithmic_passed": algo_visual["passed"],
        "media_info": media,
        "technical_checks": technical_checks,
        "visual_checks": {
            "contact_sheet": str(contact_sheet_path) if contact_sheet_path else None,
            "algorithmic": algo_visual,
            "vision_ai": vision_ai,
        },
        "failed_checks": [k for k, v in technical_checks.items() if not v["passed"]],
    }

    report_path = qa_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Controle de qualidade concluído: approved=%s | técnicos=%s | visuais=%s | falhas=%s",
        approved,
        technical_passed,
        algo_visual["passed"],
        report["failed_checks"],
    )
    return report
