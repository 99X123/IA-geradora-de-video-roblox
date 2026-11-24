"""Integração real com Blender 3D (headless) para renderizar animações 3D de Roblox e fichas de referência 3D."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BASE_DIR, get_blender_executable, get_ffmpeg_executable, load_settings
from app.models import CharacterProfile, SceneSpec, StoryboardDocument
from app.visual_styles import get_visual_style

BLENDER_SCRIPT = BASE_DIR / "app" / "blender_scene_script.py"
RBX_BRIDGE_SCRIPT = BASE_DIR / "app" / "rbx_blender_bridge.py"


def get_rbx_engine_dir(settings: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Detecta a pasta `engine/` do roblox-story-kit (biblioteca Blender 3D `rbx`) quando disponível."""
    cfg = settings or load_settings()
    raw = str(cfg.get("blender", {}).get("roblox_story_kit_engine", "") or "").strip()

    candidates: List[Path] = []
    if raw and raw.lower() != "auto":
        candidates.append(Path(raw))
    candidates.append(BASE_DIR / "engine")
    candidates.append(Path.home() / "Documents" / "roblox skill" / "roblox-story-kit" / "engine")

    for p in candidates:
        if p.exists() and (p / "rbx" / "__init__.py").exists():
            return p
    return None


def _has_nvidia_gpu() -> bool:
    """Detecta rapidamente se existe uma GPU NVIDIA CUDA disponível (ex.: T4/L4/A100 no Colab)."""
    for smi in ("nvidia-smi", "/usr/bin/nvidia-smi", "/usr/local/nvidia/bin/nvidia-smi"):
        try:
            out = subprocess.check_output(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                timeout=4,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                parts = [p.strip() for p in out.splitlines()[0].split(",")]
                vram_mb = float(parts[1]) if len(parts) > 1 else 0.0
                if vram_mb >= 3500:
                    return True
        except Exception:
            continue
    return False


def resolve_blender_render_engine(cfg: Dict[str, Any]) -> str:
    """
    Escolhe o motor ideal do Blender conforme o ambiente:
    - GPU NVIDIA no Colab/Linux headless: tenta BLENDER_EEVEE (EGL super rápido ~5-10s/cena)
      com fallback automático para CYCLES CUDA/OptiX GPU caso EGL não abra.
    - Linux headless SEM GPU (Colab CPU): usa CYCLES CPU ultra-otimizado com denoiser.
    - Windows / Desktop com tela: usa BLENDER_EEVEE.
    """
    bcfg = cfg.get("blender", {})
    requested = str(bcfg.get("render_engine", "auto") or "auto").strip()
    if requested.lower() != "auto":
        return requested

    is_headless_linux = platform.system() == "Linux" and not os.environ.get("DISPLAY")
    if is_headless_linux:
        return "BLENDER_EEVEE" if _has_nvidia_gpu() else "CYCLES"
    return "BLENDER_EEVEE"


def _effective_blender_profile(cfg: Dict[str, Any], render_engine: str) -> Dict[str, int | bool]:
    """Ajusta resolução, FPS e samples automaticamente para velocidade máxima na GPU ou CPU."""
    bcfg = cfg.get("blender", {})
    has_gpu = _has_nvidia_gpu()
    is_headless_linux = platform.system() == "Linux" and not os.environ.get("DISPLAY")

    width = int(bcfg.get("render_width", 540))
    height = int(bcfg.get("render_height", 960))
    fps = int(bcfg.get("animation_fps", 15))
    samples = int(bcfg.get("samples", 16))

    # Modo CPU-only no Colab/Linux (2 threads): reduz carga em ~12x mantendo boa nitidez após upscale Lanczos
    if is_headless_linux and not has_gpu and render_engine.upper() == "CYCLES":
        width = min(width, 360)
        height = min(height, 640)
        fps = min(fps, 10)
        samples = min(samples, 4)
    elif has_gpu and render_engine.upper() == "CYCLES":
        samples = min(samples, 12)

    return {
        "has_gpu": has_gpu,
        "width": width,
        "height": height,
        "fps": fps,
        "samples": samples,
    }


def _run_blender_with_fallback(
    blender_exe: str,
    script_to_run: Path,
    spec_path: Path,
    spec: Dict[str, Any],
    timeout_seconds: int,
    check_success: Any,
) -> subprocess.CompletedProcess[str]:
    """Executa o Blender e, se EEVEE falhar em ambiente headless Linux, tenta automaticamente com CYCLES."""
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [blender_exe, "--background", "--factory-startup", "--python", str(script_to_run), "--", str(spec_path)],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if proc.returncode == 0 and check_success():
        return proc

    current_engine = str(spec.get("engine", "")).upper()
    if current_engine != "CYCLES":
        has_gpu = bool(spec.get("has_gpu", False))
        spec_retry = dict(spec)
        spec_retry["engine"] = "CYCLES"
        spec_retry["samples"] = 12 if has_gpu else 4
        if not has_gpu and "width" in spec_retry and "height" in spec_retry:
            spec_retry["width"] = min(int(spec_retry["width"]), 360)
            spec_retry["height"] = min(int(spec_retry["height"]), 640)
            spec_retry["fps"] = min(int(spec_retry.get("fps", 15)), 10)
        spec_path.write_text(json.dumps(spec_retry, indent=2, ensure_ascii=False), encoding="utf-8")
        proc_retry = subprocess.run(
            [blender_exe, "--background", "--factory-startup", "--python", str(script_to_run), "--", str(spec_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc_retry.returncode == 0 and check_success():
            return proc_retry
        return proc_retry
    return proc


class BlenderRenderError(RuntimeError):
    """Erro na renderização 3D via Blender."""


def render_character_reference_3d(
    character: CharacterProfile,
    dest_png: Path,
    visual_style_id: str = "roblox_3d_blender_cinematic",
    settings: Optional[Dict[str, Any]] = None,
) -> Path:
    """Renderiza ficha de referência 3D real do personagem no Blender (iluminação PBR de estúdio)."""
    cfg = settings or load_settings()
    blender_exe = get_blender_executable(cfg)
    if not blender_exe:
        raise BlenderRenderError("Blender não encontrado para renderizar referência 3D.")

    bcfg = cfg.get("blender", {})
    preset = get_visual_style(visual_style_id)
    dest_png = dest_png.resolve()
    dest_png.parent.mkdir(parents=True, exist_ok=True)
    spec_path = dest_png.with_suffix(".spec.json")

    rbx_dir = get_rbx_engine_dir(cfg)
    script_to_run = RBX_BRIDGE_SCRIPT if rbx_dir else BLENDER_SCRIPT
    render_engine = resolve_blender_render_engine(cfg)
    prof = _effective_blender_profile(cfg, render_engine)

    spec = {
        "mode": "reference",
        "rbx_engine_dir": str(rbx_dir) if rbx_dir else None,
        "character": character.model_dump(mode="json"),
        "output_path": str(dest_png),
        "resolution": min(int(bcfg.get("reference_resolution", 768)), 512 if (not prof["has_gpu"] and render_engine == "CYCLES") else 768),
        "engine": render_engine,
        "has_gpu": bool(prof["has_gpu"]),
        "gpu_device": str(bcfg.get("gpu_device", "auto")),
        "samples": int(prof["samples"]),
        "roughness_bias": preset.blender_roughness_bias,
        "color_look": preset.blender_color_look,
    }

    try:
        proc = _run_blender_with_fallback(
            blender_exe=blender_exe,
            script_to_run=script_to_run,
            spec_path=spec_path,
            spec=spec,
            timeout_seconds=int(bcfg.get("timeout_seconds", 300)),
            check_success=lambda: dest_png.exists(),
        )
        if proc.returncode != 0 or not dest_png.exists():
            tail = (proc.stderr or proc.stdout or "")[-800:]
            raise BlenderRenderError(f"Blender falhou ao renderizar referência 3D:\n{tail}")
        return dest_png
    finally:
        spec_path.unlink(missing_ok=True)


def render_scene_3d_blender(
    scene: SceneSpec,
    storyboard: StoryboardDocument,
    dest_mp4: Path,
    visual_style_id: str = "roblox_3d_blender_cinematic",
    settings: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Renderiza uma cena inteira em 3D real no Blender (avatares 3D articulados, cenário 3D,
    iluminação PBR, Depth of Field e câmera animada) e codifica em MP4 1080x1920 30fps via FFmpeg.
    """
    cfg = settings or load_settings()
    blender_exe = get_blender_executable(cfg)
    ffmpeg_exe = get_ffmpeg_executable(cfg)
    if not blender_exe:
        raise BlenderRenderError("Blender não encontrado.")
    if not ffmpeg_exe:
        raise BlenderRenderError("FFmpeg não encontrado para codificar os quadros 3D do Blender.")

    bcfg = cfg.get("blender", {})
    preset = get_visual_style(visual_style_id)

    char_map = {c.name.lower(): c for c in storyboard.characters}
    scene_chars: List[Dict[str, Any]] = []
    for cname in scene.characters:
        if cname.lower() in char_map:
            scene_chars.append(char_map[cname.lower()].model_dump(mode="json"))
    if not scene_chars and storyboard.characters:
        scene_chars = [storyboard.characters[0].model_dump(mode="json")]

    dest_mp4 = dest_mp4.resolve()
    work_dir = dest_mp4.parent / f"_blender_scene_{scene.scene_number:02d}"
    frames_dir = work_dir / "frames"
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    rbx_dir = get_rbx_engine_dir(cfg)
    script_to_run = RBX_BRIDGE_SCRIPT if rbx_dir else BLENDER_SCRIPT
    render_engine = resolve_blender_render_engine(cfg)
    prof = _effective_blender_profile(cfg, render_engine)

    anim_fps = int(prof["fps"])
    spec_path = work_dir / "scene_spec.json"
    spec = {
        "mode": "scene",
        "rbx_engine_dir": str(rbx_dir) if rbx_dir else None,
        "scene_number": scene.scene_number,
        "story_beat": scene.story_beat,
        "setting_theme": scene.setting_theme,
        "expression": scene.expression,
        "camera_movement": scene.camera_movement,
        "movements_en": scene.movements_en,
        "duration_seconds": float(scene.duration_seconds),
        "characters": scene_chars,
        "frames_dir": str(frames_dir),
        "width": int(prof["width"]),
        "height": int(prof["height"]),
        "fps": anim_fps,
        "engine": render_engine,
        "has_gpu": bool(prof["has_gpu"]),
        "gpu_device": str(bcfg.get("gpu_device", "auto")),
        "samples": int(prof["samples"]),
        "roughness_bias": preset.blender_roughness_bias,
        "color_look": preset.blender_color_look,
        "seed": scene.scene_number * 131 + (hash(storyboard.project_id) % 997),
    }

    try:
        proc = _run_blender_with_fallback(
            blender_exe=blender_exe,
            script_to_run=script_to_run,
            spec_path=spec_path,
            spec=spec,
            timeout_seconds=int(bcfg.get("timeout_seconds", 360)),
            check_success=lambda: bool(list(frames_dir.glob("frame_*.png"))),
        )
        pngs = sorted(frames_dir.glob("frame_*.png"))
        if proc.returncode != 0 or not pngs:
            tail = (proc.stderr or proc.stdout or "")[-1000:]
            raise BlenderRenderError(f"Blender falhou na cena {scene.scene_number:02d}:\n{tail}")

        # Renomeia sequencialmente (frame_0001, frame_0003... quando frame_step=2 -> seq_0001, seq_0002...)
        for seq_idx, png_file in enumerate(pngs, start=1):
            seq_target = frames_dir / f"seq_{seq_idx:04d}.png"
            png_file.rename(seq_target)

        out_w = int(cfg["video"].get("width", 1080))
        out_h = int(cfg["video"].get("height", 1920))
        out_fps = int(cfg["video"].get("fps", 30))

        dest_mp4.parent.mkdir(parents=True, exist_ok=True)
        # Upscale nítido Lanczos para 1080x1920 + 30fps suave preservando 100% da proporção 9:16
        from app.video_editor import get_video_encode_args

        enc_args = get_video_encode_args(
            ffmpeg_exe=ffmpeg_exe,
            preset="veryfast",
            crf=19,
            use_gpu=bool(cfg["video"].get("use_gpu_acceleration", True)),
        )
        cmd = [
            ffmpeg_exe,
            "-y",
            "-framerate",
            str(anim_fps),
            "-i",
            str(frames_dir / "seq_%04d.png"),
            "-vf",
            f"scale={out_w}:{out_h}:flags=lanczos,fps={out_fps},format=yuv420p",
            *enc_args,
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest_mp4),
        ]
        ff = subprocess.run(cmd, capture_output=True, text=True)
        if ff.returncode != 0 or not dest_mp4.exists():
            raise BlenderRenderError(f"FFmpeg falhou ao codificar cena 3D {scene.scene_number:02d}: {ff.stderr[-600:]}")
        return dest_mp4
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
