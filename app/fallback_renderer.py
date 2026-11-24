"""Plano alternativo para computadores fracos: renderização local de cenas estilizadas Roblox + animação cinematográfica FFmpeg."""

from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from app.character_consistency import draw_roblox_avatar
from app.config import get_ffmpeg_executable, load_settings
from app.models import CharacterProfile, SceneSpec, StoryboardDocument

THEME_PALETTES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "server": {
        "sky_top": (12, 18, 44),
        "sky_bot": (34, 62, 118),
        "floor": (26, 34, 56),
        "accent": (56, 189, 248),
        "prop": (30, 41, 72),
    },
    "city": {
        "sky_top": (18, 28, 66),
        "sky_bot": (88, 62, 128),
        "floor": (34, 38, 50),
        "accent": (250, 204, 21),
        "prop": (44, 54, 82),
    },
    "school": {
        "sky_top": (32, 46, 82),
        "sky_bot": (78, 102, 146),
        "floor": (74, 64, 58),
        "accent": (251, 146, 60),
        "prop": (52, 74, 112),
    },
    "forest": {
        "sky_top": (10, 26, 30),
        "sky_bot": (28, 72, 68),
        "floor": (22, 44, 34),
        "accent": (74, 222, 128),
        "prop": (18, 52, 40),
    },
    "castle": {
        "sky_top": (24, 14, 42),
        "sky_bot": (72, 34, 96),
        "floor": (44, 40, 56),
        "accent": (192, 132, 252),
        "prop": (58, 52, 74),
    },
    "neon": {
        "sky_top": (10, 8, 28),
        "sky_bot": (48, 16, 88),
        "floor": (16, 14, 34),
        "accent": (232, 121, 249),
        "prop": (26, 22, 58),
    },
    "hallway": {
        "sky_top": (14, 16, 26),
        "sky_bot": (44, 26, 38),
        "floor": (30, 28, 36),
        "accent": (248, 113, 113),
        "prop": (38, 36, 48),
    },
}


def _lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _draw_environment_backdrop(
    img: Image.Image,
    theme: str,
    story_beat: str,
    seed: int,
    variant: int = 0,
) -> None:
    """Desenha cenário 2.5D estilizado Roblox com profundidade, arquitetura em blocos e iluminação volumétrica."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(seed + variant * 97)
    pal = THEME_PALETTES.get(theme, THEME_PALETTES["server"])

    sky_top = pal["sky_top"]
    sky_bot = pal["sky_bot"]
    accent = pal["accent"]
    prop = pal["prop"]
    floor_c = pal["floor"]

    # Mood lighting shifts em beats de tensão ou reviravolta
    if story_beat in ("Conflito", "Clímax"):
        accent = (248, 113, 113)
        sky_bot = _lerp_color(sky_bot, (120, 24, 38), 0.45)
    elif story_beat == "Reviravolta":
        accent = (250, 204, 21)
        sky_bot = _lerp_color(sky_bot, (140, 102, 34), 0.4)

    horizon_y = int(h * (0.64 if variant == 0 else 0.68))

    # 1. Céu em gradiente suave
    for y in range(0, horizon_y, 2):
        ratio = y / max(1, horizon_y)
        col = _lerp_color(sky_top, sky_bot, ratio)
        draw.rectangle([0, y, w, y + 2], fill=col + (255,))

    # 2. Estrelas / lua / feixe de luz volumétrico
    orb_x = int(w * (0.76 if variant == 0 else 0.28))
    orb_y = int(h * 0.17)
    for r in range(210, 20, -25):
        alpha = int(12 + (210 - r) * 0.22)
        draw.ellipse([orb_x - r, orb_y - r, orb_x + r, orb_y + r], fill=accent + (min(90, alpha),))
    draw.ellipse([orb_x - 42, orb_y - 42, orb_x + 42, orb_y + 42], fill=(245, 250, 255, 220))

    # Raios volumétricos diagonais
    for ray_i in range(3):
        rx = int(w * (0.15 + ray_i * 0.34)) + (variant * 40)
        poly = [(rx - 40, 0), (rx + 90, 0), (rx + 260, horizon_y + 180), (rx - 140, horizon_y + 180)]
        draw.polygon(poly, fill=accent + (18,))

    # 3. Arquitetura / cenário em blocos estilo Roblox
    if theme in ("city", "server", "neon"):
        # Prédios / torres Roblox ao fundo
        for b_idx in range(9):
            bx = int(b_idx * (w / 8.2)) - 30 + rng.randint(-15, 15)
            bw = rng.randint(110, 195)
            bh = rng.randint(360, 760)
            by = horizon_y - bh + 25
            bcol = _lerp_color(prop, (15, 20, 35), rng.uniform(0.0, 0.45))
            draw.rounded_rectangle([bx, by, bx + bw, horizon_y + 20], radius=10, fill=bcol + (245,), outline=accent + (70,), width=2)
            # Janelas brilhantes em grade
            for wy in range(by + 30, horizon_y - 35, 52):
                for wx in range(bx + 18, bx + bw - 28, 36):
                    if rng.random() > 0.35:
                        wcol = accent if rng.random() > 0.65 else (226, 232, 240)
                        draw.rectangle([wx, wy, wx + 18, wy + 24], fill=wcol + (185,))
        # Portal / holograma de servidor ao centro
        px, py = w // 2, horizon_y - 240
        draw.rounded_rectangle([px - 170, py - 110, px + 170, py + 110], radius=24, fill=(10, 18, 36, 175), outline=accent + (220,), width=5)
        for line_i in range(4):
            ly = py - 58 + line_i * 36
            lw = rng.randint(140, 260)
            draw.rounded_rectangle([px - lw // 2, ly, px + lw // 2, ly + 14], radius=7, fill=accent + (190,))

    elif theme == "forest":
        # Árvores blocadas estilo Roblox em camadas
        for t_idx in range(11):
            tx = int(t_idx * (w / 10.0)) + rng.randint(-20, 20)
            trunk_h = rng.randint(200, 420)
            ty = horizon_y - trunk_h
            draw.rectangle([tx - 16, ty, tx + 16, horizon_y + 30], fill=(64, 42, 28, 255))
            for layer in range(3):
                cw = 115 - layer * 24
                ch = 85 - layer * 10
                cy = ty - layer * 62
                leaf_col = _lerp_color((22, 88, 58), (44, 130, 82), layer / 3.0)
                draw.rounded_rectangle([tx - cw, cy, tx + cw, cy + ch], radius=16, fill=leaf_col + (240,), outline=(14, 48, 34, 200), width=2)

    elif theme == "school" or theme == "hallway":
        # Corredor em perspectiva com armários e portas Roblox
        draw.polygon([(0, 0), (w // 2 - 190, horizon_y - 260), (w // 2 - 190, horizon_y + 20), (0, h)], fill=_lerp_color(prop, (25, 32, 48), 0.35) + (240,))
        draw.polygon([(w, 0), (w // 2 + 190, horizon_y - 260), (w // 2 + 190, horizon_y + 20), (w, h)], fill=_lerp_color(prop, (25, 32, 48), 0.45) + (240,))
        # Armários/portas laterais
        for idx in range(4):
            lx = 35 + idx * 78
            ly = 260 + idx * 60
            draw.rounded_rectangle([lx, ly, lx + 62, horizon_y + 100 - idx * 35], radius=8, fill=prop + (245,), outline=accent + (130,), width=3)
            rx = w - lx - 62
            draw.rounded_rectangle([rx, ly, rx + 62, horizon_y + 100 - idx * 35], radius=8, fill=prop + (245,), outline=accent + (130,), width=3)
        # Porta misteriosa ao fundo
        draw.rounded_rectangle([w // 2 - 120, horizon_y - 310, w // 2 + 120, horizon_y + 10], radius=14, fill=(18, 22, 34, 250), outline=accent + (230,), width=5)

    else:
        # Castelo / masmorra com torres e portal brilhante
        for sx in (60, w - 260):
            draw.rectangle([sx, horizon_y - 540, sx + 200, horizon_y + 20], fill=prop + (245,), outline=(120, 110, 150, 140), width=3)
            for cr in range(0, 200, 50):
                draw.rectangle([sx + cr, horizon_y - 580, sx + cr + 32, horizon_y - 540], fill=prop + (255,))
        # Portal central brilhante
        draw.ellipse([w // 2 - 170, horizon_y - 380, w // 2 + 170, horizon_y + 40], fill=accent + (65,), outline=accent + (240,), width=8)
        draw.ellipse([w // 2 - 115, horizon_y - 320, w // 2 + 115, horizon_y + 20], fill=(245, 240, 255, 115))

    # 4. Piso em perspectiva 3D estilo Roblox baseplate/studs
    for y in range(horizon_y, h, 3):
        ratio = (y - horizon_y) / max(1, h - horizon_y)
        col = _lerp_color(floor_c, _lerp_color(floor_c, (8, 10, 18), 0.55), ratio)
        draw.rectangle([0, y, w, y + 3], fill=col + (255,))

    # Linhas de grade em perspectiva
    vp_x = w // 2
    for ray in range(-8, 9):
        bx = vp_x + ray * 220
        draw.line([(vp_x + ray * 30, horizon_y), (bx, h)], fill=accent + (55,), width=2)
    for k in range(1, 11):
        gy = horizon_y + int(((k / 10.0) ** 1.8) * (h - horizon_y))
        draw.line([(0, gy), (w, gy)], fill=accent + (48,), width=2)

    # 5. Partículas atmosféricas brilhantes
    for _ in range(36):
        px = rng.randint(20, w - 20)
        py = rng.randint(60, h - 220)
        pr = rng.randint(3, 10)
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=accent + (rng.randint(70, 180),))


def _apply_cinematic_vignette(img: Image.Image) -> Image.Image:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Escurece suavemente as bordas superior/inferior para dar contraste cinematográfico e destacar legendas
    for step in range(40):
        alpha_top = int((1.0 - step / 40.0) * 95)
        y_top = int(step * (h * 0.14 / 40.0))
        d.rectangle([0, y_top, w, y_top + 8], fill=(4, 8, 18, alpha_top))

        alpha_bot = int((1.0 - step / 40.0) * 145)
        y_bot = h - int(step * (h * 0.28 / 40.0))
        d.rectangle([0, y_bot - 14, w, y_bot], fill=(4, 8, 18, alpha_bot))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render_procedural_roblox_scene_images(
    scene: SceneSpec,
    storyboard: StoryboardDocument,
    images_dir: Path,
    frames_per_scene: int = 2,
) -> List[Path]:
    """
    Gera imagens verticais (1080x1920) estilizadas de alta nitidez mantendo
    os personagens consistentes do storyboard para animação cinematográfica no FFmpeg.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    char_map: Dict[str, CharacterProfile] = {c.name.lower(): c for c in storyboard.characters}
    scene_chars: List[CharacterProfile] = []
    for cname in scene.characters:
        if cname.lower() in char_map:
            scene_chars.append(char_map[cname.lower()])
    if not scene_chars and storyboard.characters:
        scene_chars = [storyboard.characters[0]]

    output_paths: List[Path] = []
    width, height = 1080, 1920

    for variant in range(max(1, frames_per_scene)):
        out_path = images_dir / f"scene_{scene.scene_number:02d}_frame_{variant + 1:02d}.png"
        canvas = Image.new("RGBA", (width, height), (14, 18, 34, 255))
        _draw_environment_backdrop(
            canvas,
            theme=scene.setting_theme,
            story_beat=scene.story_beat,
            seed=scene.scene_number * 101 + hash(storyboard.project_id) % 997,
            variant=variant,
        )

        # Leve desfoque de profundidade no fundo antes de posicionar os personagens nítidos em primeiro plano
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=1.2 if variant == 0 else 2.2))
        fg_draw = ImageDraw.Draw(canvas, "RGBA")

        pose = "run" if any(k in scene.movements_en.lower() for k in ("sprint", "run", "chase", "escape")) else "idle"

        if len(scene_chars) == 1:
            scale = 1.65 if variant == 0 else 2.15
            cx = width // 2 + (-35 if variant == 0 else 20)
            feet_y = int(height * (0.76 if variant == 0 else 0.84))
            draw_roblox_avatar(
                fg_draw,
                scene_chars[0],
                center_x=cx,
                feet_y=feet_y,
                scale=scale,
                expression=scene.expression,
                pose=pose,
            )
        else:
            # Dois personagens interagindo com escala cinematográfica
            if variant == 0:
                draw_roblox_avatar(
                    fg_draw,
                    scene_chars[1],
                    center_x=int(width * 0.69),
                    feet_y=int(height * 0.72),
                    scale=1.32,
                    expression="angry" if scene.story_beat in ("Conflito", "Clímax") else "neutral",
                    pose="idle",
                )
                draw_roblox_avatar(
                    fg_draw,
                    scene_chars[0],
                    center_x=int(width * 0.34),
                    feet_y=int(height * 0.78),
                    scale=1.58,
                    expression=scene.expression,
                    pose=pose,
                )
            else:
                # Plano fechado dramático no protagonista + silhueta do rival atrás
                draw_roblox_avatar(
                    fg_draw,
                    scene_chars[1],
                    center_x=int(width * 0.74),
                    feet_y=int(height * 0.73),
                    scale=1.18,
                    expression="determined",
                    pose="idle",
                )
                draw_roblox_avatar(
                    fg_draw,
                    scene_chars[0],
                    center_x=int(width * 0.42),
                    feet_y=int(height * 0.85),
                    scale=2.0,
                    expression=scene.expression,
                    pose=pose,
                )

        final_img = _apply_cinematic_vignette(canvas)
        final_img.save(out_path, format="PNG")
        output_paths.append(out_path)

    return output_paths


def _zoompan_expr(camera_movement: str, total_frames: int) -> Tuple[str, str, str]:
    """Retorna expressões (z, x, y) suaves para movimento cinematográfico Ken Burns / parallax no FFmpeg."""
    n = max(2, total_frames)
    progress = f"(on/{n})"
    if camera_movement == "slow_zoom_out":
        z = f"max(1.0,1.16-0.16*{progress})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif camera_movement == "pan_left":
        z = "1.14"
        x = f"(iw-iw/zoom)*(1-{progress})"
        y = "ih/2-(ih/zoom/2)"
    elif camera_movement == "pan_right":
        z = "1.14"
        x = f"(iw-iw/zoom)*{progress}"
        y = "ih/2-(ih/zoom/2)"
    elif camera_movement == "tilt_up":
        z = "1.15"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(1-{progress})"
    elif camera_movement == "dramatic_push":
        z = f"min(1.24,1.0+0.24*{progress})"
        x = "iw/2-(iw/zoom/2)"
        y = f"ih*0.44-(ih/zoom/2)"
    elif camera_movement == "parallax_drift":
        z = f"min(1.18,1.06+0.12*{progress})"
        x = f"(iw-iw/zoom)*(0.2+0.6*{progress})"
        y = f"(ih-ih/zoom)*(0.45+0.1*sin(on*0.08))"
    else:  # slow_zoom_in
        z = f"min(1.16,1.0+0.16*{progress})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    return z, x, y


def animate_images_to_clip(
    image_paths: List[Path],
    dest_mp4: Path,
    duration_seconds: float,
    camera_movement: str = "slow_zoom_in",
    settings: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Transforma 1 ou mais imagens de cena em um clipe MP4 vertical 1080x1920 fluido
    com zoom cinematográfico, panorâmica, parallax e transição suave via FFmpeg.
    """
    cfg = settings or load_settings()
    ffmpeg_exe = get_ffmpeg_executable(cfg)
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg não encontrado para animar imagens da cena.")

    if not image_paths:
        raise ValueError("Nenhuma imagem fornecida para animação da cena.")

    width = int(cfg["video"].get("width", 1080))
    height = int(cfg["video"].get("height", 1920))
    fps = int(cfg["video"].get("fps", 30))
    dest_mp4.parent.mkdir(parents=True, exist_ok=True)

    valid_imgs = [p for p in image_paths if p.exists()]
    if not valid_imgs:
        raise FileNotFoundError("Imagens da cena não existem em disco.")

    # Anima cada imagem em um sub-clipe com movimento distinto e aplica crossfade entre eles
    if len(valid_imgs) == 1:
        frames = max(fps * 2, int(math.ceil(duration_seconds * fps)))
        z_expr, x_expr, y_expr = _zoompan_expr(camera_movement, frames)
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps={fps},"
            "format=yuv420p"
        )
        cmd = [
            ffmpeg_exe,
            "-y",
            "-loop",
            "1",
            "-i",
            str(valid_imgs[0]),
            "-vf",
            vf,
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-an",
            str(dest_mp4),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return dest_mp4

    # Múltiplas imagens por cena com crossfade suave (ex.: plano geral -> reação)
    n_imgs = len(valid_imgs)
    xfade_dur = 0.35
    per_img_dur = (duration_seconds + xfade_dur * (n_imgs - 1)) / n_imgs
    per_img_dur = max(1.2, per_img_dur)
    frames_each = max(fps, int(math.ceil(per_img_dur * fps)))

    alt_moves = [camera_movement, "dramatic_push" if camera_movement != "dramatic_push" else "slow_zoom_out", "pan_right"]
    inputs: List[str] = []
    filter_parts: List[str] = []

    for i, img_p in enumerate(valid_imgs):
        inputs.extend(["-loop", "1", "-t", f"{per_img_dur:.3f}", "-i", str(img_p)])
        move = alt_moves[i % len(alt_moves)]
        z_expr, x_expr, y_expr = _zoompan_expr(move, frames_each)
        filter_parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames_each}:s={width}x{height}:fps={fps},"
            f"trim=duration={per_img_dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )

    prev = "v0"
    offset = per_img_dur - xfade_dur
    for i in range(1, n_imgs):
        out_lbl = f"xf{i}"
        filter_parts.append(
            f"[{prev}][v{i}]xfade=transition=fade:duration={xfade_dur:.2f}:offset={max(0.1, offset):.3f}[{out_lbl}]"
        )
        prev = out_lbl
        offset += per_img_dur - xfade_dur

    filter_complex = ";".join(filter_parts)
    cmd = [
        ffmpeg_exe,
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{prev}]",
        "-t",
        f"{duration_seconds:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dest_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return dest_mp4
