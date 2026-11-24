"""
Ponte nativa para o motor 3D profissional `rbx` (roblox-story-kit/engine) rodando no Blender 5.x local,
sem depender de Flashloop — conectado 100% ao Roblox AI Shorts Studio (narração Kokoro PT-BR, Whisper, FFmpeg).
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import bpy


EXPR_MAP = {
    "neutral": "neutral",
    "curious": "confused",
    "happy": "joy",
    "worried": "worried",
    "scared": "scared",
    "angry": "angry",
    "shocked": "shock",
    "determined": "determined",
}

HAIR_MAP = {
    "spiky": "spiky",
    "cap": "cap",
    "hood": "messy",
    "crown": "tophat",
    "bob": "bob",
    "short": "short",
    "bun": "bun",
    "helmet": "helmet",
    "slick": "slick",
}


def _make_rbx_char(chars_mod: Any, cdata: Dict[str, Any], is_antagonist: bool, idx: int) -> Any:
    name = str(cdata.get("name") or f"Char{idx}")
    hair_raw = str(cdata.get("hair_style") or "spiky").lower()
    hair = HAIR_MAP.get(hair_raw, "spiky")

    face_style = "villain" if is_antagonist else "hero"
    if any(k in name.lower() for k in ("ana", "bia", "luna", "maya", "julia", "sofia", "maria", "clara")):
        face_style = "girl"
        if hair == "spiky":
            hair = "bob"

    acc = str(cdata.get("accessory") or "").lower()
    extras: List[str] = []
    if acc == "backpack":
        extras.append("backpack")
    elif acc == "glasses":
        extras.append("glasses")
    elif acc in ("scarf", "cape"):
        extras.append("collar")

    return chars_mod.Char(
        name,
        skin=str(cdata.get("skin_color_hex") or "#f1dfc6"),
        shirt=str(cdata.get("primary_color_hex") or "#2563eb"),
        pants=str(cdata.get("secondary_color_hex") or "#1e293b"),
        hair=hair,
        hair_color=str(cdata.get("hair_color_hex") or "#2b1b12"),
        face=face_style,
        sleeves="long" if is_antagonist else "short",
        bolt="#f2c14e" if not is_antagonist else None,
        vneck="#e2e8f0" if not is_antagonist else None,
        extras=tuple(extras),
        seed=idx + 1,
    )


def _setup_set_and_lighting(
    core: Any,
    W: Any,
    theme: str,
    story_beat: str,
    seed: int,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], float]:
    """
    Constrói o cenário 3D real da biblioteca `rbx.world` e retorna:
    (pos_protagonista, pos_antagonista, yaw_padrao).
    """
    beat = (story_beat or "").lower()
    is_tense = any(k in beat for k in ("conflito", "clímax", "climax"))
    is_twist = "reviravolta" in beat or "twist" in beat

    if theme == "school":
        W.classroom_day(board="chalk_joke.png", open_window=True)
        if is_tense:
            core.light("MoodKey", "AREA", (0.0, 2.0, 9.5), 4500, (1.0, 0.35, 0.35), 10, target=(0, 3, 2))
        elif is_twist:
            core.light("MoodKey", "AREA", (6.0, 2.0, 8.5), 5500, (1.0, 0.85, 0.45), 10, target=(0, 3, 3))
        return (0.0, 2.5, 0.0), (3.6, 5.2, 0.0), 0.0

    if theme == "hallway":
        W.hallway_day()
        if is_tense:
            core.light("MoodRim", "AREA", (0.0, 12.0, 7.0), 5000, (1.0, 0.25, 0.28), 8, target=(0, 0, 3))
        elif is_twist:
            core.light("MoodRim", "AREA", (0.0, 12.0, 7.0), 5500, (1.0, 0.82, 0.35), 8, target=(0, 0, 3))
        return (0.0, -2.0, 0.0), (2.8, 3.5, 0.0), 0.0

    # Cenário externo 3D completo (`W.town`) — cidade/servidor/escola exterior/parque com prédios, céu e nuvens
    if is_tense:
        W.sky(strength=0.45, top=(0.03, 0.02, 0.12), bottom=(0.24, 0.07, 0.16))
        W.sun(strength=1.8, rot=(38, 0, 55))
        core.light("RimDrama", "AREA", (0.0, -18.0, 9.0), 7500, (1.0, 0.22, 0.28), 10, target=(0, -30, 3.5))
    elif is_twist:
        W.sky(strength=0.85, top=(0.14, 0.10, 0.34), bottom=(0.95, 0.52, 0.22))
        W.sun(strength=4.2, rot=(25, 0, 42))
        core.light("GoldRim", "AREA", (4.0, -20.0, 10.0), 6500, (1.0, 0.82, 0.35), 10, target=(0, -30, 3.5))
    else:
        W.sky(strength=0.95, top=(0.04, 0.18, 0.72), bottom=(0.28, 0.56, 0.96))
        W.sun(strength=3.8, rot=(46, 0, 32))

    W.town(school=True, seed=seed)
    W.cloud_field("clouds", (0, 20, 48), spread=(120, 90, 14), n=6, seed=seed)
    # Adiciona carro 3D colorido na rua para profundidade cinematográfica
    W.car("street_car_1", (-11.0, -26.5, 0.0), color="#d9453a", rot=90)
    W.car("street_car_2", (14.5, -33.5, 0.0), color="#2563eb", rot=-90)
    # Luz frontal suave nos personagens para rostos e cores sempre nítidos como na ficha 3D
    core.light("HeroFrontFill", "AREA", (0.0, -39.0, 5.5), 2600, (1.0, 0.97, 0.94), 7, target=(0, -30, 3.2))

    # Personagens posicionados na avenida ampla em frente à escola 3D (z=0, y=-30)
    return (-1.2, -30.0, 0.0), (2.6, -26.2, 0.0), 0.0


def _apply_engine_and_gpu(spec: Dict[str, Any]) -> None:
    """Configura EEVEE ou Cycles GPU (CUDA/OptiX no Google Colab) de forma compatível com Blender 4.2+ e 5.x."""
    scene = bpy.context.scene
    engine = str(spec.get("engine", "BLENDER_EEVEE") or "BLENDER_EEVEE")
    gpu_device = str(spec.get("gpu_device", "auto") or "auto")
    samples = int(spec.get("samples", 16))

    try:
        scene.render.use_persistent_data = True
        scene.render.image_settings.compression = 15
    except Exception:
        pass

    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        used_gpu = False
        if gpu_device.lower() != "cpu":
            try:
                prefs = bpy.context.preferences.addons["cycles"].preferences
                for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
                    try:
                        prefs.compute_device_type = backend
                        prefs.get_devices()
                        gpu_devs = [d for d in prefs.devices if d.type != "CPU"]
                        if gpu_devs:
                            for d in prefs.devices:
                                d.use = d.type != "CPU"
                            scene.cycles.device = "GPU"
                            used_gpu = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        if not used_gpu:
            scene.cycles.device = "CPU"
            # Em CPU desativa compositor pesado por frame para ganhar ~3x de velocidade mantendo PBR + AgX
            scene.render.use_compositing = False
        scene.cycles.samples = max(4, samples)
        scene.cycles.use_denoising = True
        try:
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.08 if used_gpu else 0.10
            scene.cycles.max_bounces = 2
            scene.cycles.diffuse_bounces = 1
            scene.cycles.glossy_bounces = 1
            scene.cycles.transmission_bounces = 1
            scene.cycles.volume_bounces = 0
            scene.cycles.transparent_max_bounces = 3
            scene.cycles.sample_clamp_indirect = 4.0
        except Exception:
            pass
    else:
        for eng in (engine, "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
            try:
                scene.render.engine = eng
                break
            except Exception:
                continue
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = False


def render_reference_rbx(spec: Dict[str, Any]) -> None:
    from rbx import core, chars, acting  # type: ignore

    core.reset()
    res = int(spec.get("resolution", 768))
    core.setup_render(1, 1, res=(res, res), samples=int(spec.get("samples", 16)), pct=100, blur=False)
    _apply_engine_and_gpu(spec)

    core.world(color=(0.14, 0.20, 0.34), strength=0.9)
    # Palco de estúdio limpo
    core.plane("StudioFloor", 40, 40, (0, 0, 0), core.mat("stage_floor", core.hexc("#1e293b"), rough=0.25, metal=0.1))
    core.light("Key", "AREA", (6.0, -8.0, 9.0), 4500, (1.0, 0.97, 0.92), 6, target=(0, 0, 2.8))
    core.light("Fill", "AREA", (-7.0, -5.0, 6.0), 1800, (0.70, 0.82, 1.0), 6, target=(0, 0, 2.8))
    core.light("Rim", "AREA", (0.0, 7.0, 7.5), 3500, (0.35, 0.72, 1.0), 6, target=(0, 0, 3.0))

    ch = _make_rbx_char(chars, spec["character"], is_antagonist=False, idx=0)
    ch.pose(0.0, loc=(0, 0, 0), rot=16.0)
    ch.face(0.0, "happy")

    cam = core.Cam("RefCam", lens=42)
    cam.key(0.0, (2.2, -10.5, 3.4), (0.0, 0.0, 2.9), lens=42, focus=(0, 0, 3.2), fstop=4.0)

    bpy.context.scene.render.filepath = str(spec["output_path"])
    bpy.ops.render.render(write_still=True)


def render_scene_rbx(spec: Dict[str, Any]) -> None:
    from rbx import core, chars, acting, world as W  # type: ignore

    core.reset()
    width = int(spec.get("width", 540))
    height = int(spec.get("height", 960))
    duration = max(2.5, float(spec.get("duration_seconds", 5.0)))
    t0, t1 = 0.0, duration
    f0, f1 = core.F(t0), core.F(t1)

    core.setup_render(f0, f1, res=(width, height), samples=int(spec.get("samples", 16)), pct=100, blur=False)
    _apply_engine_and_gpu(spec)
    # Renderiza 10 ou 15 fps efetivos (frame_step=3 ou 2 sobre timeline de 30 fps) -> muito mais rápido!
    target_fps = int(spec.get("fps", 15))
    bpy.context.scene.frame_step = 3 if target_fps <= 10 else (2 if target_fps <= 15 else 1)

    seed = int(spec.get("seed", 42))
    random.seed(seed)

    p1, p2, base_yaw = _setup_set_and_lighting(
        core=core,
        W=W,
        theme=str(spec.get("setting_theme", "city")),
        story_beat=str(spec.get("story_beat", "Desenvolvimento")),
        seed=seed,
    )

    char_specs: List[Dict[str, Any]] = spec.get("characters") or []
    raw_expr = str(spec.get("expression", "curious")).lower()
    rbx_expr = EXPR_MAP.get(raw_expr, "neutral")
    movements = str(spec.get("movements_en", "")).lower()

    is_run = any(k in movements for k in ("sprint", "run", "chase", "escape", "correndo"))
    is_walk = any(k in movements for k in ("walk", "enter", "step", "andando"))

    lead_ch = None
    built_chars: List[Any] = []

    if len(char_specs) >= 2:
        c1 = _make_rbx_char(chars, char_specs[0], is_antagonist=False, idx=0)
        c2 = _make_rbx_char(chars, char_specs[1], is_antagonist=True, idx=1)

        if is_run or is_walk:
            dest1 = (p1[0] + 1.2, p1[1] - (5.5 if is_run else 3.0), p1[2])
            c1.walk(t0, t1, p1, dest1, rate=3.2 if is_run else 2.2, swing=44 if is_run else 28)
            dest2 = (p2[0] - 0.8, p2[1] - (4.5 if is_run else 2.0), p2[2])
            c2.walk(t0, t1, p2, dest2, rate=2.6 if is_run else 1.8, swing=36 if is_run else 24)
        else:
            c1.pose(t0, loc=p1, rot=base_yaw - 18.0)
            c2.pose(t0, loc=p2, rot=base_yaw + 22.0)
            if rbx_expr in ("shock", "scared"):
                c1.panic(t0, t1, rate=4.0)
            else:
                c1.pose(t0, armL=(22, -8), armR=(-14, 10))
                c1.pose(t1, armL=(-12, 8), armR=(36, -12))
            c2.pose(t0, armL=(38, -14), armR=(38, -14))

        c1.face(t0, rbx_expr)
        c1.blink(t0, t1)
        c1.breathe(0.8)
        c1.talk(t0, min(t1, t0 + duration * 0.75))

        c2.face(t0, "angry")
        c2.blink(t0, t1)
        c2.breathe(0.6)
        lead_ch = c1
        built_chars = [c1, c2]
    elif len(char_specs) == 1:
        c1 = _make_rbx_char(chars, char_specs[0], is_antagonist=False, idx=0)
        center_p = (0.0, p1[1], p1[2])
        if is_run or is_walk:
            dest1 = (0.0, p1[1] - (6.0 if is_run else 3.2), p1[2])
            c1.walk(t0, t1, center_p, dest1, rate=3.2 if is_run else 2.2, swing=44 if is_run else 28)
        else:
            c1.pose(t0, loc=center_p, rot=base_yaw + 10.0)
            if rbx_expr in ("shock", "scared"):
                c1.panic(t0, t1, rate=4.2)
            else:
                c1.pose(t0, torso=(0, 4, 0), armL=(18, -6), armR=(-12, 10))
                c1.pose(t1, torso=(0, -4, 0), armL=(-14, 8), armR=(34, -10))

        c1.face(t0, rbx_expr)
        c1.blink(t0, t1)
        c1.breathe(0.8)
        c1.talk(t0, min(t1, t0 + duration * 0.8))
        lead_ch = c1
        built_chars = [c1]

    # Câmera cinematográfica 3D usando rbx.core.Cam
    cam = core.Cam("StudioCam", lens=32)
    cam_move = str(spec.get("camera_movement", "slow_zoom_in"))
    tgt_x = (p1[0] + p2[0]) * 0.45 if len(built_chars) >= 2 else 0.0
    tgt_y = p1[1]
    target = (tgt_x, tgt_y, 3.8)
    base_d = 14.0 if len(built_chars) >= 2 else 11.2

    if is_run or is_walk:
        cam.track(lead_ch, t0, t1, offset=(4.2, -9.5, 4.6), look_up=3.8, lens=30, step=0.35, fstop=3.2)
    elif cam_move == "slow_zoom_out":
        cam.push(t0, t1, target, base_d - 2.5, base_d + 3.2, yaw=-10, yaw1=12, pitch=8, pitch1=14, lens=32, fstop=3.2)
    elif cam_move == "pan_left":
        cam.orbit(t0, t1, target, base_d, yaw0=26, yaw1=-26, pitch=9, lens=32, steps=4, fstop=3.0)
    elif cam_move == "pan_right":
        cam.orbit(t0, t1, target, base_d, yaw0=-26, yaw1=26, pitch=9, lens=32, steps=4, fstop=3.0)
    elif cam_move == "tilt_up":
        cam.push(t0, t1, target, base_d, base_d - 1.5, yaw=8, yaw1=-6, pitch=-6, pitch1=18, lens=30, fstop=3.0)
    elif cam_move == "dramatic_push":
        cam.push(t0, t1, target, base_d + 1.5, base_d - 4.2, yaw=-14, yaw1=6, pitch=6, pitch1=10, lens=30, lens1=42, fstop=2.4)
    elif cam_move == "parallax_drift":
        cam.orbit(t0, t1, target, base_d - 0.8, yaw0=-22, yaw1=22, pitch=6, pitch1=14, lens=30, steps=5, fstop=2.8)
    else:  # slow_zoom_in
        cam.push(t0, t1, target, base_d + 1.5, base_d - 2.6, yaw=-8, yaw1=10, pitch=10, pitch1=7, lens=32, fstop=2.8)

    cam.handheld(0.55)
    cam.euler_fix()
    core.ensure_motion(cam.ob, t0, t1)

    frames_dir = Path(spec["frames_dir"])
    frames_dir.mkdir(parents=True, exist_ok=True)

    if spec.get("mode") == "keyframes":
        # Renderiza 3 keyframes 3D reais (início, meio e ápice da ação) — ultra-rápido mesmo sem GPU,
        # mantendo 100% dos personagens 3D rbx, rostos expressivos e cenários 3D reais!
        key_count = max(2, min(5, int(spec.get("keyframe_count", 3))))
        span = max(1, f1 - f0)
        key_frames = [
            int(round(f0 + span * (i / max(1, key_count - 1))))
            for i in range(key_count)
        ]
        for idx_k, kf in enumerate(key_frames, start=1):
            bpy.context.scene.frame_set(kf)
            bpy.context.scene.render.filepath = str(frames_dir / f"keyframe_{idx_k:02d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        bpy.context.scene.render.filepath = str(frames_dir / "frame_")
        bpy.ops.render.render(animation=True)


def main() -> None:
    if "--" not in sys.argv:
        raise RuntimeError("Passe '-- <spec.json>' ao executar rbx_blender_bridge.py")
    spec_path = Path(sys.argv[sys.argv.index("--") + 1])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    engine_dir = spec.get("rbx_engine_dir")
    if not engine_dir or not Path(engine_dir).exists():
        raise FileNotFoundError(f"Motor rbx não encontrado em: {engine_dir}")
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    if spec.get("mode") == "reference":
        render_reference_rbx(spec)
    else:
        render_scene_rbx(spec)


if __name__ == "__main__":
    main()
