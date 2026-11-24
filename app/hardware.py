"""Detecção real de hardware (GPU, VRAM, RAM, disco) e serviços locais (FFmpeg, Ollama, ComfyUI, TTS, Whisper)."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import psutil

from app.config import (
    BASE_DIR,
    get_blender_executable,
    get_ffmpeg_executable,
    is_colab_environment,
    load_settings,
    resolve_path,
)
from app.models import HardwareReport


def _detect_cpu_name() -> str:
    sys_name = platform.system()
    if sys_name == "Windows":
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
                ],
                text=True,
                timeout=6,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                return out
        except Exception:
            pass
    elif sys_name == "Linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
            for line in cpuinfo.splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    name = line.split(":", 1)[1].strip()
                    if name:
                        return name
        except Exception:
            pass
    return platform.processor() or platform.machine() or "CPU desconhecida"


def _detect_gpu() -> Tuple[str, str, float, bool]:
    """Retorna (gpu_name, gpu_vendor, vram_gb, cuda_available)."""
    # 1. Tenta nvidia-smi (mais preciso para GPUs NVIDIA modernas com CUDA)
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            line = out.splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            name = parts[0]
            vram_mb = float(parts[1]) if len(parts) > 1 else 0.0
            vram_gb = round(vram_mb / 1024.0, 2)
            # GPUs muito antigas (ex.: GT 710/Kepler) não suportam PyTorch CUDA moderno
            legacy_tokens = ("GT 710", "GT 720", "GT 730", "GT 610", "GTX 650", "GTX 660")
            cuda_ok = not any(tok in name.upper() for tok in legacy_tokens) and vram_gb >= 4.0
            return name, "NVIDIA", vram_gb, cuda_ok
    except Exception:
        pass

    # 2. Fallback no Windows via Win32_VideoController (detecta GT 710, AMD, Intel integradas)
    if platform.system() == "Windows":
        try:
            ps_cmd = (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, AdapterRAM, AdapterCompatibility | ConvertTo-Json -Compress"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                text=True,
                timeout=8,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                parsed = json.loads(out)
                gpus = parsed if isinstance(parsed, list) else [parsed]
                best = max(gpus, key=lambda g: int(g.get("AdapterRAM") or 0))
                name = str(best.get("Name") or "GPU desconhecida")
                vendor = str(best.get("AdapterCompatibility") or "Desconhecido")
                ram_bytes = int(best.get("AdapterRAM") or 0)
                vram_gb = round(ram_bytes / (1024 ** 3), 2) if ram_bytes > 0 else 0.0
                if "NVIDIA" in name.upper():
                    vendor = "NVIDIA"
                elif "AMD" in name.upper() or "RADEON" in name.upper():
                    vendor = "AMD"
                elif "INTEL" in name.upper():
                    vendor = "Intel"
                return name, vendor, vram_gb, False
        except Exception:
            pass

    return "Nenhuma GPU dedicada detectada", "Desconhecido", 0.0, False


def _probe_ollama(ollama_url: str) -> Tuple[bool, List[str]]:
    try:
        resp = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=0.8)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return True, models
    except Exception:
        pass
    return False, []


def _probe_comfyui(base_url: str) -> Tuple[bool, List[str], List[str]]:
    checkpoints: List[str] = []
    unets: List[str] = []
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/system_stats", timeout=0.8)
        if resp.status_code != 200:
            return False, [], []
        try:
            ckpt_resp = httpx.get(f"{base_url.rstrip('/')}/object_info/CheckpointLoaderSimple", timeout=3.0)
            if ckpt_resp.status_code == 200:
                info = ckpt_resp.json()
                checkpoints = list(
                    info.get("CheckpointLoaderSimple", {})
                    .get("input", {})
                    .get("required", {})
                    .get("ckpt_name", [[]])[0]
                )
        except Exception:
            pass
        try:
            unet_resp = httpx.get(f"{base_url.rstrip('/')}/object_info/UNETLoader", timeout=3.0)
            if unet_resp.status_code == 200:
                info = unet_resp.json()
                unets = list(
                    info.get("UNETLoader", {})
                    .get("input", {})
                    .get("required", {})
                    .get("unet_name", [[]])[0]
                )
        except Exception:
            pass
        return True, checkpoints, unets
    except Exception:
        return False, [], []


def detect_hardware(settings: Dict[str, Any] | None = None) -> HardwareReport:
    """Inspeciona hardware real e serviços instalados, definindo compatibilidade com segurança."""
    cfg = settings or load_settings()

    cpu_name = _detect_cpu_name()
    cpu_cores = psutil.cpu_count(logical=True) or 1
    vm = psutil.virtual_memory()
    ram_total_gb = round(vm.total / (1024 ** 3), 2)
    ram_available_gb = round(vm.available / (1024 ** 3), 2)
    disk = psutil.disk_usage(str(BASE_DIR))
    disk_free_gb = round(disk.free / (1024 ** 3), 2)

    gpu_name, gpu_vendor, gpu_vram_gb, cuda_available = _detect_gpu()

    ffmpeg_path = get_ffmpeg_executable(cfg)
    ffmpeg_available = bool(ffmpeg_path)

    blender_path = get_blender_executable(cfg)
    blender_available = bool(blender_path)
    blender_version: str | None = None
    if blender_path:
        try:
            ver_out = subprocess.check_output([blender_path, "--version"], text=True, timeout=6, stderr=subprocess.DEVNULL)
            blender_version = ver_out.splitlines()[0].strip() if ver_out else "Blender"
        except Exception:
            blender_version = Path(blender_path).parent.name

    ollama_available, ollama_models = _probe_ollama(cfg["story_ai"]["ollama_url"])
    comfyui_available, comfyui_checkpoints, comfyui_unets = _probe_comfyui(cfg["comfyui"]["base_url"])

    kokoro_model = resolve_path(cfg["tts"]["kokoro_model_file"])
    kokoro_voices = resolve_path(cfg["tts"]["kokoro_voices_file"])
    kokoro_ready = kokoro_model.exists() and kokoro_voices.exists()

    piper_model = resolve_path(cfg["tts"]["piper_model_file"])
    piper_ready = piper_model.exists()

    from app.subtitle_engine import WhisperSubtitleEngine

    whisper_ready = WhisperSubtitleEngine(cfg).is_model_cached()

    wan22_min_vram = float(cfg["comfyui"].get("wan22_min_vram_gb", 12.0))
    img_min_vram = float(cfg["comfyui"].get("local_image_min_vram_gb", 4.0))

    supports_wan22 = (
        cuda_available
        and gpu_vram_gb >= wan22_min_vram
        and ram_total_gb >= 16.0
        and disk_free_gb >= 20.0
    )
    supports_local_image_ai = (
        cuda_available
        and gpu_vram_gb >= img_min_vram
        and ram_total_gb >= 8.0
    )

    if ram_total_gb >= 24.0 and gpu_vram_gb >= 12.0:
        recommended_ollama_model = "gemma3:12b"
    elif ram_total_gb >= 12.0:
        recommended_ollama_model = "gemma3:4b"
    else:
        recommended_ollama_model = "gemma3:1b"

    warnings: List[str] = []
    if not supports_wan22:
        warnings.append(
            f"GPU detectada ({gpu_name}, {gpu_vram_gb:.1f} GB VRAM) não atende ao mínimo de "
            f"{wan22_min_vram:.0f} GB VRAM CUDA para Wan 2.2 TI2V-5B. Execução do Wan 2.2 bloqueada por segurança; "
            f"o Plano Alternativo (imagens animadas / importação Roblox Studio ou Flow) será usado automaticamente."
        )
    if not supports_local_image_ai:
        if blender_available:
            warnings.append(
                f"GPU abaixo de {img_min_vram:.0f} GB VRAM CUDA para difusão ComfyUI, mas {blender_version} foi detectado! "
                "O estúdio usará renderização 3D REAL no Blender (EEVEE/Cycles) com avatares 3D articulados, iluminação PBR e câmeras animadas."
            )
        else:
            warnings.append(
                f"GPU abaixo de {img_min_vram:.0f} GB VRAM CUDA e Blender não encontrado. "
                "Instale o Blender gratuitamente (blender.org) para animação 3D real local, ou use Google Flow / Roblox Studio."
            )
    if not ollama_available and not is_colab_environment():
        warnings.append(
            "Ollama não está ativo em 127.0.0.1:11434. Para roteiros por LLM local offline, instale o Ollama e execute: "
            f"ollama pull {recommended_ollama_model}."
        )
    if not ffmpeg_available:
        warnings.append("FFmpeg não encontrado. Instale o FFmpeg (apt install ffmpeg no Linux/Colab ou install.bat no Windows).")
    if disk_free_gb < 5.0:
        warnings.append(f"Pouco espaço livre em disco ({disk_free_gb:.1f} GB). Libere espaço antes de baixar modelos grandes.")

    env_prefix = "Google Colab + " if is_colab_environment() else ""
    if supports_wan22 and comfyui_available:
        recommended_tier = "comfyui_wan22"
        summary = (
            f"{env_prefix}Alta capacidade ({gpu_name}, {gpu_vram_gb:.1f} GB VRAM): compatível com ComfyUI + Wan 2.2 TI2V-5B local."
        )
    elif blender_available and cfg.get("blender", {}).get("enabled", True):
        recommended_tier = "blender_3d_render"
        gpu_note = f"com aceleração GPU CUDA ({gpu_name}, {gpu_vram_gb:.1f} GB VRAM)" if cuda_available else f"({gpu_name}, {ram_total_gb:.1f} GB RAM)"
        summary = (
            f"{env_prefix}Motor 3D REAL ativo ({blender_version} {gpu_note}): "
            "renderização 3D cinematográfica de Roblox no Blender (avatares 3D articulados, cenários 3D, materiais PBR, "
            "luzes volumétricas e câmeras animadas), além de suporte completo ao Google Flow e Roblox Studio."
        )
    elif supports_local_image_ai and comfyui_available:
        recommended_tier = "comfyui_image_animated"
        summary = (
            f"{env_prefix}Capacidade intermediária ({gpu_name}, {gpu_vram_gb:.1f} GB VRAM): compatível com geração local de imagens 3D "
            "no ComfyUI + animação cinematográfica no FFmpeg (Wan 2.2 desativado para proteger a GPU)."
        )
    else:
        recommended_tier = "fallback_animated_images"
        summary = (
            f"{env_prefix}Modo Emergência CPU ({gpu_name}, {gpu_vram_gb:.1f} GB VRAM): Blender e ComfyUI indisponíveis. "
            "Instale o Blender (gratuito) para animação 3D real ou importe clipes do Google Flow / Roblox Studio."
        )

    return HardwareReport(
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        disk_free_gb=disk_free_gb,
        gpu_name=gpu_name,
        gpu_vendor=gpu_vendor,
        gpu_vram_gb=gpu_vram_gb,
        cuda_available=cuda_available,
        ffmpeg_available=ffmpeg_available,
        ffmpeg_path=ffmpeg_path,
        blender_available=blender_available,
        blender_path=blender_path,
        blender_version=blender_version,
        ollama_available=ollama_available,
        ollama_models=ollama_models,
        comfyui_available=comfyui_available,
        comfyui_checkpoints=comfyui_checkpoints,
        comfyui_unets=comfyui_unets,
        kokoro_ready=kokoro_ready,
        piper_ready=piper_ready,
        whisper_ready=whisper_ready,
        supports_wan22=supports_wan22,
        supports_local_image_ai=supports_local_image_ai,
        recommended_ollama_model=recommended_ollama_model,
        recommended_tier=recommended_tier,
        compatibility_summary=summary,
        warnings=warnings,
    )
