"""Cross-platform runtime helpers (FFmpeg/FFprobe discovery, logging, slugify, subprocess)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import PROJECT_ROOT, redact_secrets


def setup_logger(name: str, log_file: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Create a structured logger with secret redaction."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    class RedactingFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return redact_secrets(super().format(record))

    fmt = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def slugify(text: str, max_length: int = 48) -> str:
    """Convert an arbitrary Portuguese/Unicode string into a clean filesystem slug."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    if not slug:
        slug = "autoshorts_video"
    return slug[:max_length].rstrip("_")


def timestamp_id() -> str:
    """UTC timestamp suitable for unique project folder names."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def find_ffmpeg() -> str:
    """Locate ffmpeg binary across PATH, env override, or imageio-ffmpeg bundle."""
    env_bin = os.environ.get("FFMPEG_BINARY")
    if env_bin and Path(env_bin).exists():
        return env_bin

    which_bin = shutil.which("ffmpeg")
    if which_bin:
        return which_bin

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass

    raise FileNotFoundError(
        "FFmpeg não encontrado. Instale via 'apt-get install -y ffmpeg' (Colab/Linux), "
        "'winget install Gyan.FFmpeg' (Windows) ou 'pip install imageio-ffmpeg'."
    )


def find_ffprobe() -> Optional[str]:
    """Locate ffprobe binary if installed (optional fallback to ffmpeg parsing exists)."""
    env_bin = os.environ.get("FFPROBE_BINARY")
    if env_bin and Path(env_bin).exists():
        return env_bin
    return shutil.which("ffprobe")


def find_node() -> str:
    """Locate Node.js binary."""
    node_bin = shutil.which("node")
    if not node_bin:
        raise FileNotFoundError("Node.js não encontrado no PATH. Instale Node.js >= 18.")
    return node_bin


def is_colab() -> bool:
    """Return True if executing inside Google Colab."""
    try:
        import google.colab  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def detect_nvidia_gpu() -> Dict[str, object]:
    """Detect NVIDIA GPU availability via nvidia-smi (does NOT imply WebGL GPU)."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False, "name": None, "memory_mb": None, "note": "nvidia-smi não encontrado"}
    try:
        proc = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            first_line = proc.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in first_line.split(",")]
            return {
                "available": True,
                "name": parts[0],
                "memory_mb": int(float(parts[1])) if len(parts) > 1 else None,
                "note": "GPU CUDA/sistema detectada. Verifique separadamente se o WebGL do Chromium está usando aceleração por hardware.",
            }
    except Exception as exc:
        return {"available": False, "name": None, "memory_mb": None, "note": str(exc)}
    return {"available": False, "name": None, "memory_mb": None, "note": "Nenhuma GPU reportada"}


def run_subprocess(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess safely with UTF-8 decoding and clear error messages."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        env=merged_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Comando falhou (exit={proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
        )
    return proc


def probe_media_info(media_path: Path | str) -> Dict[str, object]:
    """Inspect video/audio metadata via ffprobe, with ffmpeg stderr fallback."""
    path = Path(media_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de mídia não encontrado: {path}")

    ffprobe = find_ffprobe()
    if ffprobe:
        proc = run_subprocess(
            [
                ffprobe,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            check=True,
        )
        import json

        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        fps = None
        if v_stream:
            rate_str = v_stream.get("avg_frame_rate") or v_stream.get("r_frame_rate") or "0/1"
            num, _, den = rate_str.partition("/")
            try:
                fps = float(num) / float(den) if float(den) else 0.0
            except ValueError:
                fps = 0.0

        return {
            "tool": "ffprobe",
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "duration_sec": float(fmt.get("duration") or 0.0),
            "has_video": v_stream is not None,
            "has_audio": a_stream is not None,
            "width": int(v_stream["width"]) if v_stream and "width" in v_stream else None,
            "height": int(v_stream["height"]) if v_stream and "height" in v_stream else None,
            "fps": round(fps, 3) if fps is not None else None,
            "video_codec": v_stream.get("codec_name") if v_stream else None,
            "pixel_format": v_stream.get("pix_fmt") if v_stream else None,
            "audio_codec": a_stream.get("codec_name") if a_stream else None,
            "audio_sample_rate": int(a_stream["sample_rate"]) if a_stream and a_stream.get("sample_rate") else None,
            "audio_channels": int(a_stream["channels"]) if a_stream and a_stream.get("channels") else None,
            "nb_frames": int(v_stream["nb_frames"]) if v_stream and str(v_stream.get("nb_frames", "")).isdigit() else None,
        }

    # Fallback: parse `ffmpeg -i` stderr when ffprobe is not installed (e.g. imageio-ffmpeg only)
    ffmpeg = find_ffmpeg()
    proc = run_subprocess([ffmpeg, "-hide_banner", "-i", str(path)], check=False)
    stderr = proc.stderr

    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    duration_sec = 0.0
    if dur_match:
        h, m, s = dur_match.groups()
        duration_sec = int(h) * 3600 + int(m) * 60 + float(s)

    v_match = re.search(
        r"Stream #\d+:\d+.*Video:\s*([a-zA-Z0-9_]+).*?,\s*([a-zA-Z0-9_]+)(?:\([^)]*\))?,\s*(\d+)x(\d+).*?,\s*(\d+(?:\.\d+)?)\s*fps",
        stderr,
    )
    a_match = re.search(
        r"Stream #\d+:\d+.*Audio:\s*([a-zA-Z0-9_]+).*?,\s*(\d+)\s*Hz,\s*([^,]+)",
        stderr,
    )

    channels = None
    if a_match:
        ch_str = a_match.group(3).strip().lower()
        if "mono" in ch_str:
            channels = 1
        elif "stereo" in ch_str:
            channels = 2
        else:
            m_ch = re.search(r"(\d+)\s*channels", ch_str)
            channels = int(m_ch.group(1)) if m_ch else 2

    return {
        "tool": "ffmpeg_fallback",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "duration_sec": round(duration_sec, 4),
        "has_video": v_match is not None,
        "has_audio": a_match is not None,
        "width": int(v_match.group(3)) if v_match else None,
        "height": int(v_match.group(4)) if v_match else None,
        "fps": round(float(v_match.group(5)), 3) if v_match else None,
        "video_codec": v_match.group(1) if v_match else None,
        "pixel_format": v_match.group(2) if v_match else None,
        "audio_codec": a_match.group(1) if a_match else None,
        "audio_sample_rate": int(a_match.group(2)) if a_match else None,
        "audio_channels": channels,
        "nb_frames": int(round(duration_sec * float(v_match.group(5)))) if v_match and duration_sec else None,
    }


def detect_ffmpeg_silences(
    audio_path: Path | str,
    noise_db: float = -38.0,
    min_duration: float = 0.18,
) -> List[Tuple[float, float]]:
    """Run FFmpeg silencedetect and return list of (start_sec, end_sec) intervals."""
    ffmpeg = find_ffmpeg()
    proc = run_subprocess(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_duration}",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    silences: List[Tuple[float, float]] = []
    cur_start: Optional[float] = None
    for line in proc.stderr.splitlines():
        m_start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m_start:
            cur_start = float(m_start.group(1))
        m_end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m_end and cur_start is not None:
            silences.append((cur_start, float(m_end.group(1))))
            cur_start = None
    return silences
