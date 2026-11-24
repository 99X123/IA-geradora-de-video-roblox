"""Gerenciamento de configurações, caminhos e descoberta de executáveis (FFmpeg)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "settings.json"


DEFAULT_SETTINGS: Dict[str, Any] = {
    "app_name": "Roblox AI Shorts Studio",
    "version": "1.0.0",
    "language": "pt-BR",
    "ui": {"host": "127.0.0.1", "port": 7860, "open_browser": True},
    "generation": {
        "default_mode": "local_free",
        "default_visual_style": "roblox_3d_blender_cinematic",
        "flow_credits_available": False,
        "flow_official_url": "https://labs.google/fx/tools/flow",
        "gemini_web_url": "https://gemini.google.com",
        "default_duration_seconds": 55,
        "min_scenes": 6,
        "max_scenes": 10,
        "default_genre": "Suspense / Mistério",
        "default_story_opening": "Neste servidor...",
    },
    "blender": {
        "enabled": True,
        "strict_3d_no_2d_fallback": True,
        "executable_path": "auto",
        "roblox_story_kit_engine": "auto",
        "render_engine": "auto",
        "gpu_device": "auto",
        "samples": 16,
        "animation_fps": 15,
        "render_width": 540,
        "render_height": 960,
        "reference_resolution": 768,
        "timeout_seconds": 600,
    },
    "story_ai": {
        "provider": "auto",
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "gemma3:4b",
        "gemini_model": "gemini-2.5-flash",
        "timeout_seconds": 120,
        "max_retries": 2,
    },
    "comfyui": {
        "enabled": True,
        "base_url": "http://127.0.0.1:8188",
        "timeout_seconds": 600,
        "wan22_min_vram_gb": 12.0,
        "local_image_min_vram_gb": 4.0,
        "wan22_unet": "wan2.2_ti2v_5B_fp16.safetensors",
        "wan22_clip": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "wan22_vae": "wan2.2_vae.safetensors",
        "image_checkpoint": "sd_xl_base_1.0.safetensors",
        "wan22_width": 480,
        "wan22_height": 832,
        "wan22_fps": 24,
        "wan22_steps": 20,
        "image_width": 768,
        "image_height": 1344,
        "image_steps": 22,
    },
    "tts": {
        "engine": "auto",
        "default_voice": "pm_alex",
        "default_speed": 1.05,
        "kokoro_model_file": "models/kokoro/kokoro-v1.0.int8.onnx",
        "kokoro_voices_file": "models/kokoro/voices-v1.0.bin",
        "kokoro_model_url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
        "kokoro_voices_url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        "piper_model_file": "models/piper/pt_BR-faber-medium.onnx",
        "sample_rate": 24000,
    },
    "subtitles": {
        "engine": "faster-whisper",
        "whisper_model": "base",
        "whisper_compute_type": "int8",
        "whisper_device": "auto",
        "language": "pt",
        "font_name": "Arial Black",
        "font_size": 74,
        "max_words_per_line": 4,
        "margin_v": 340,
        "highlight_color_ass": "&H0000D7FF&",
        "primary_color_ass": "&H00FFFFFF&",
        "outline_color_ass": "&H00000000&",
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "video_codec": "libx264",
        "use_gpu_acceleration": True,
        "cleanup_temp_work": True,
        "crf": 20,
        "preset": "medium",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "music_volume": 0.16,
        "sfx_volume": 0.42,
        "transition_duration": 0.35,
        "ffmpeg_path": "auto",
    },
    "paths": {
        "projects_dir": "projects",
        "models_dir": "models",
        "workflows_dir": "workflows/comfyui",
        "assets_dir": "assets",
        "logs_dir": "logs",
        "temp_dir": "temp",
        "drive_export_dir": "",
    },
}


def is_colab_environment() -> bool:
    """Detecta se o estúdio está rodando dentro do Google Colab."""
    if os.environ.get("COLAB_RELEASE_TAG") or os.environ.get("COLAB_GPU") or os.environ.get("STUDIO_COLAB_MODE") == "1":
        return True
    try:
        import google.colab  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica variáveis de ambiente (essenciais no Google Colab + Google Drive) sem alterar settings.json."""
    env_map = [
        ("STUDIO_PROJECTS_DIR", ("paths", "projects_dir")),
        ("STUDIO_MODELS_DIR", ("paths", "models_dir")),
        ("STUDIO_LOGS_DIR", ("paths", "logs_dir")),
        ("STUDIO_TEMP_DIR", ("paths", "temp_dir")),
        ("STUDIO_DRIVE_EXPORT_DIR", ("paths", "drive_export_dir")),
        ("BLENDER_PATH", ("blender", "executable_path")),
        ("BLENDER_ENGINE", ("blender", "render_engine")),
        ("RBX_ENGINE_DIR", ("blender", "roblox_story_kit_engine")),
        ("FFMPEG_PATH", ("video", "ffmpeg_path")),
        ("WHISPER_MODEL", ("subtitles", "whisper_model")),
    ]
    for env_key, path_keys in env_map:
        val = os.environ.get(env_key)
        if val is not None and val.strip():
            section, key = path_keys
            cfg.setdefault(section, {})[key] = val.strip()

    # Se STUDIO_MODELS_DIR estiver no Drive, redireciona também os caminhos do Kokoro/Piper para lá
    models_override = os.environ.get("STUDIO_MODELS_DIR", "").strip()
    if models_override:
        mroot = Path(models_override)
        tts_cfg = cfg.setdefault("tts", {})
        if not Path(str(tts_cfg.get("kokoro_model_file", ""))).is_absolute():
            tts_cfg["kokoro_model_file"] = str(mroot / "kokoro" / "kokoro-v1.0.int8.onnx")
        if not Path(str(tts_cfg.get("kokoro_voices_file", ""))).is_absolute():
            tts_cfg["kokoro_voices_file"] = str(mroot / "kokoro" / "voices-v1.0.bin")
        if not Path(str(tts_cfg.get("piper_model_file", ""))).is_absolute():
            tts_cfg["piper_model_file"] = str(mroot / "piper" / "pt_BR-faber-medium.onnx")

    return cfg


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Carrega config/settings.json aplicando valores padrão e variáveis de ambiente (Colab/Drive)."""
    target = config_path or CONFIG_FILE
    if not target.exists():
        save_settings(DEFAULT_SETTINGS, target)
        return _apply_env_overrides(json.loads(json.dumps(DEFAULT_SETTINGS)))
    try:
        with target.open("r", encoding="utf-8") as fh:
            user_data = json.load(fh)
        return _apply_env_overrides(_deep_merge(DEFAULT_SETTINGS, user_data))
    except Exception:
        return _apply_env_overrides(json.loads(json.dumps(DEFAULT_SETTINGS)))


def save_settings(settings: Dict[str, Any], config_path: Optional[Path] = None) -> None:
    """Salva configurações de forma segura (sem nunca persistir chaves de API)."""
    target = config_path or CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    sanitized = json.loads(json.dumps(settings))
    # Garantia de segurança: nunca gravar segredos em disco
    sanitized.pop("gemini_api_key", None)
    if "story_ai" in sanitized and isinstance(sanitized["story_ai"], dict):
        sanitized["story_ai"].pop("api_key", None)
        sanitized["story_ai"].pop("gemini_api_key", None)
    tmp_path = target.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(sanitized, fh, indent=2, ensure_ascii=False)
    tmp_path.replace(target)


def resolve_path(rel_or_abs: str | Path) -> Path:
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def ensure_base_directories(settings: Optional[Dict[str, Any]] = None) -> None:
    cfg = settings or load_settings()
    for key in ("projects_dir", "models_dir", "workflows_dir", "assets_dir", "logs_dir", "temp_dir"):
        resolve_path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)
    assets_root = resolve_path(cfg["paths"]["assets_dir"])
    for sub in ("music", "sounds", "fonts"):
        (assets_root / sub).mkdir(parents=True, exist_ok=True)
    models_root = resolve_path(cfg["paths"]["models_dir"])
    for sub in ("kokoro", "piper", "whisper"):
        (models_root / sub).mkdir(parents=True, exist_ok=True)


def get_ffmpeg_executable(settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Localiza FFmpeg na configuração, no PATH do sistema ou no binário embutido do imageio-ffmpeg."""
    cfg = settings or load_settings()
    configured = cfg.get("video", {}).get("ffmpeg_path", "auto")
    if configured and configured != "auto":
        p = Path(configured)
        if p.exists():
            return str(p)

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass

    return None


def get_drive_export_dir(settings: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Retorna a pasta extra de exportação no Google Drive (se configurada), onde cópias prontas de final.mp4 são salvas."""
    cfg = settings or load_settings()
    raw = str(cfg.get("paths", {}).get("drive_export_dir") or "").strip()
    if not raw:
        return None
    p = resolve_path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_blender_executable(settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Localiza o executável real do Blender (env BLENDER_PATH, configuração, PATH, Linux/Colab ou Windows)."""
    cfg = settings or load_settings()
    configured = cfg.get("blender", {}).get("executable_path", "auto")
    if configured and configured != "auto":
        p = Path(configured)
        if p.exists():
            return str(p)

    sys_blender = shutil.which("blender")
    if sys_blender:
        return sys_blender

    # Busca versões instaladas no Linux / Google Colab
    linux_candidates: list[Path] = [
        Path("/opt/blender/blender"),
        Path("/usr/local/blender/blender"),
        Path("/content/blender/blender"),
        Path("/usr/local/bin/blender"),
        Path("/usr/bin/blender"),
        Path("/snap/bin/blender"),
    ]
    for root in (Path("/opt"), Path("/content"), Path("/usr/local")):
        if root.exists():
            linux_candidates.extend(sorted(root.glob("blender*/blender"), reverse=True))
    for cand in linux_candidates:
        if cand.exists() and cand.is_file():
            return str(cand)

    # Busca versões instaladas do Blender no Windows (priorizando a mais recente)
    search_roots = [
        Path("C:/Program Files/Blender Foundation"),
        Path("C:/Program Files (x86)/Blender Foundation"),
    ]
    candidates: list[Path] = []
    for root in search_roots:
        if root.exists():
            candidates.extend(root.glob("Blender*/blender.exe"))
    if candidates:
        candidates.sort(key=lambda p: p.parent.name, reverse=True)
        return str(candidates[0])

    return None


def get_gemini_api_key(override_key: Optional[str] = None) -> Optional[str]:
    """Obtém a chave da API Gemini apenas da memória ou variável de ambiente (nunca de arquivo)."""
    if override_key and override_key.strip():
        return override_key.strip()
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return env_key.strip() if env_key and env_key.strip() else None
