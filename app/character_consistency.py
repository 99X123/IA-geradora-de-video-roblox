"""Sistema de consistência visual de personagens: bíblia visual, injeção de âncoras e fichas de referência PNG."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.config import get_blender_executable, load_settings
from app.models import CharacterProfile, StoryboardDocument
from app.visual_styles import compose_3d_scene_prompt, get_visual_style


def _hex_to_rgb(hex_color: str, fallback: Tuple[int, int, int] = (37, 99, 235)) -> Tuple[int, int, int]:
    try:
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return fallback


def _shade(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)  # type: ignore[return-value]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_roblox_avatar(
    draw: ImageDraw.ImageDraw,
    character: CharacterProfile,
    center_x: int,
    feet_y: int,
    scale: float = 1.0,
    expression: str = "neutral",
    pose: str = "idle",
) -> None:
    """
    Desenha um avatar estilizado Roblox R15/R6 com sombreamento 2.5D consistente
    (mesmas cores, cabelo, roupa e acessório em todas as cenas).
    """
    skin = _hex_to_rgb(character.skin_color_hex, (243, 198, 159))
    primary = _hex_to_rgb(character.primary_color_hex, (37, 99, 235))
    secondary = _hex_to_rgb(character.secondary_color_hex, (30, 41, 59))
    hair = _hex_to_rgb(character.hair_color_hex, (43, 27, 18))

    s = scale
    # Sombra no chão
    shadow_w = int(130 * s)
    shadow_h = int(28 * s)
    draw.ellipse(
        [center_x - shadow_w // 2, feet_y - shadow_h // 2, center_x + shadow_w // 2, feet_y + shadow_h // 2],
        fill=(10, 14, 24, 150),
    )

    # Capa (se acessório for cape)
    if character.accessory == "cape":
        cape_top_y = int(feet_y - 265 * s)
        cape_pts = [
            (int(center_x - 62 * s), cape_top_y),
            (int(center_x + 62 * s), cape_top_y),
            (int(center_x + 95 * s), int(feet_y - 35 * s)),
            (int(center_x - 95 * s), int(feet_y - 35 * s)),
        ]
        draw.polygon(cape_pts, fill=_shade(primary, 0.65), outline=_shade(primary, 0.4))

    # Pernas
    leg_w = int(46 * s)
    leg_h = int(125 * s)
    leg_gap = int(8 * s)
    leg_top = feet_y - leg_h
    stride = int(14 * s) if pose == "run" else 0

    for side in (-1, 1):
        lx = center_x + (side * (leg_w // 2 + leg_gap // 2)) - leg_w // 2
        ly = leg_top - (stride if side == 1 else 0)
        draw.rounded_rectangle(
            [lx, ly, lx + leg_w, ly + leg_h],
            radius=int(8 * s),
            fill=secondary,
            outline=_shade(secondary, 0.55),
            width=max(2, int(3 * s)),
        )
        # Luz lateral 3D na perna
        draw.rectangle([lx + int(5 * s), ly + int(6 * s), lx + int(14 * s), ly + leg_h - int(22 * s)], fill=_shade(secondary, 1.25))
        # Tênis
        shoe_h = int(24 * s)
        draw.rounded_rectangle(
            [lx - int(2 * s), ly + leg_h - shoe_h, lx + leg_w + int(2 * s), ly + leg_h + int(2 * s)],
            radius=int(6 * s),
            fill=(235, 240, 248),
            outline=(60, 70, 88),
            width=max(1, int(2 * s)),
        )

    # Tronco (bloco Roblox com brilho 3D)
    torso_w = int(116 * s)
    torso_h = int(134 * s)
    torso_x = center_x - torso_w // 2
    torso_y = leg_top - torso_h + int(4 * s)
    draw.rounded_rectangle(
        [torso_x, torso_y, torso_x + torso_w, torso_y + torso_h],
        radius=int(14 * s),
        fill=primary,
        outline=_shade(primary, 0.5),
        width=max(2, int(4 * s)),
    )
    # Brilho superior e faixa de jaqueta
    draw.rounded_rectangle(
        [torso_x + int(8 * s), torso_y + int(8 * s), torso_x + int(34 * s), torso_y + torso_h - int(10 * s)],
        radius=int(8 * s),
        fill=_shade(primary, 1.2),
    )
    draw.line(
        [(center_x, torso_y + int(6 * s)), (center_x, torso_y + torso_h - int(6 * s))],
        fill=_shade(primary, 0.65),
        width=max(2, int(4 * s)),
    )

    # Alças da mochila / cachecol
    if character.accessory == "backpack":
        for side in (-1, 1):
            sx = center_x + int(side * 34 * s)
            draw.rectangle(
                [sx - int(7 * s), torso_y + int(4 * s), sx + int(7 * s), torso_y + torso_h - int(16 * s)],
                fill=(30, 35, 45),
            )
    elif character.accessory == "scarf":
        draw.rounded_rectangle(
            [torso_x + int(10 * s), torso_y - int(8 * s), torso_x + torso_w - int(10 * s), torso_y + int(24 * s)],
            radius=int(10 * s),
            fill=(250, 204, 21),
            outline=(161, 98, 7),
            width=max(1, int(2 * s)),
        )

    # Braços (pose reativa à expressão)
    arm_w = int(38 * s)
    arm_h = int(120 * s)
    raised = expression in ("shocked", "scared", "angry")
    for side in (-1, 1):
        ax = torso_x - arm_w - int(4 * s) if side == -1 else torso_x + torso_w + int(4 * s)
        ay = torso_y - (int(28 * s) if (raised and side == 1) else 0)
        draw.rounded_rectangle(
            [ax, ay, ax + arm_w, ay + arm_h],
            radius=int(10 * s),
            fill=primary,
            outline=_shade(primary, 0.5),
            width=max(2, int(3 * s)),
        )
        # Mão
        draw.rounded_rectangle(
            [ax + int(3 * s), ay + arm_h - int(26 * s), ax + arm_w - int(3 * s), ay + arm_h + int(2 * s)],
            radius=int(8 * s),
            fill=skin,
            outline=_shade(skin, 0.65),
            width=max(1, int(2 * s)),
        )

    # Cabeça clássica Roblox (cilindro arredondado com brilho especular)
    head_w = int(96 * s)
    head_h = int(94 * s)
    head_x = center_x - head_w // 2
    head_y = torso_y - head_h - int(6 * s)
    draw.rounded_rectangle(
        [head_x, head_y, head_x + head_w, head_y + head_h],
        radius=int(24 * s),
        fill=skin,
        outline=_shade(skin, 0.6),
        width=max(2, int(4 * s)),
    )
    # Brilho especular estilo plástico 3D Roblox
    draw.rounded_rectangle(
        [head_x + int(10 * s), head_y + int(10 * s), head_x + int(26 * s), head_y + int(44 * s)],
        radius=int(8 * s),
        fill=_shade(skin, 1.12),
    )

    # Cabelo / chapéu / capuz / coroa
    if character.hair_style == "cap":
        draw.rounded_rectangle(
            [head_x - int(6 * s), head_y - int(14 * s), head_x + head_w + int(6 * s), head_y + int(26 * s)],
            radius=int(16 * s),
            fill=primary,
            outline=_shade(primary, 0.5),
            width=max(2, int(3 * s)),
        )
        draw.rectangle(
            [head_x + int(35 * s), head_y + int(14 * s), head_x + head_w + int(28 * s), head_y + int(25 * s)],
            fill=_shade(primary, 0.75),
        )
    elif character.hair_style == "crown":
        crown_pts = [
            (head_x + int(8 * s), head_y + int(12 * s)),
            (head_x + int(14 * s), head_y - int(22 * s)),
            (head_x + int(34 * s), head_y - int(2 * s)),
            (center_x, head_y - int(28 * s)),
            (head_x + head_w - int(34 * s), head_y - int(2 * s)),
            (head_x + head_w - int(14 * s), head_y - int(22 * s)),
            (head_x + head_w - int(8 * s), head_y + int(12 * s)),
        ]
        draw.polygon(crown_pts, fill=(250, 204, 21), outline=(161, 98, 7))
    elif character.hair_style == "hood":
        draw.rounded_rectangle(
            [head_x - int(10 * s), head_y - int(12 * s), head_x + head_w + int(10 * s), head_y + int(34 * s)],
            radius=int(24 * s),
            fill=_shade(primary, 0.8),
            outline=_shade(primary, 0.45),
            width=max(2, int(3 * s)),
        )
    else:
        # Cabelo estilizado em blocos/pontas
        draw.rounded_rectangle(
            [head_x - int(5 * s), head_y - int(14 * s), head_x + head_w + int(5 * s), head_y + int(26 * s)],
            radius=int(18 * s),
            fill=hair,
            outline=_shade(hair, 0.45),
            width=max(2, int(3 * s)),
        )
        if character.hair_style == "spiky":
            for offset in (-26, -6, 16, 32):
                px = center_x + int(offset * s)
                draw.polygon(
                    [(px - int(12 * s), head_y + int(4 * s)), (px, head_y - int(24 * s)), (px + int(12 * s), head_y + int(4 * s))],
                    fill=hair,
                )

    # Fones de ouvido (acessório)
    if character.accessory == "headphones":
        for side in (-1, 1):
            hx = head_x - int(12 * s) if side == -1 else head_x + head_w - int(2 * s)
            draw.rounded_rectangle(
                [hx, head_y + int(28 * s), hx + int(16 * s), head_y + int(66 * s)],
                radius=int(6 * s),
                fill=(239, 68, 68),
                outline=(127, 29, 29),
                width=max(1, int(2 * s)),
            )

    # Rosto expressivo Roblox
    eye_y = head_y + int(45 * s)
    eye_dx = int(20 * s)
    eye_r = int((9 if expression in ("shocked", "scared") else 7) * s)
    for side in (-1, 1):
        ex = center_x + side * eye_dx
        draw.ellipse([ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r], fill=(20, 22, 28))
        # Brilho no olho
        br = max(2, int(2.5 * s))
        draw.ellipse([ex - eye_r // 2, eye_y - eye_r // 2, ex - eye_r // 2 + br, eye_y - eye_r // 2 + br], fill=(255, 255, 255))

    # Sobrancelhas conforme emoção
    brow_y = eye_y - int(15 * s)
    bw = max(2, int(4 * s))
    if expression in ("angry", "determined"):
        draw.line([(center_x - int(32 * s), brow_y - int(5 * s)), (center_x - int(10 * s), brow_y + int(5 * s))], fill=hair, width=bw)
        draw.line([(center_x + int(32 * s), brow_y - int(5 * s)), (center_x + int(10 * s), brow_y + int(5 * s))], fill=hair, width=bw)
    elif expression in ("worried", "scared"):
        draw.line([(center_x - int(32 * s), brow_y + int(5 * s)), (center_x - int(10 * s), brow_y - int(5 * s))], fill=hair, width=bw)
        draw.line([(center_x + int(32 * s), brow_y + int(5 * s)), (center_x + int(10 * s), brow_y - int(5 * s))], fill=hair, width=bw)
    elif expression in ("shocked", "curious"):
        draw.line([(center_x - int(30 * s), brow_y - int(6 * s)), (center_x - int(10 * s), brow_y - int(8 * s))], fill=hair, width=bw)
        draw.line([(center_x + int(10 * s), brow_y - int(8 * s)), (center_x + int(30 * s), brow_y - int(6 * s))], fill=hair, width=bw)

    # Boca conforme emoção
    mouth_y = head_y + int(69 * s)
    if expression in ("shocked", "scared"):
        mr = int(11 * s)
        draw.ellipse([center_x - mr, mouth_y - mr, center_x + mr, mouth_y + mr], fill=(35, 20, 28), outline=(20, 20, 20), width=max(1, int(2 * s)))
    elif expression == "happy":
        draw.arc([center_x - int(18 * s), mouth_y - int(12 * s), center_x + int(18 * s), mouth_y + int(12 * s)], start=15, end=165, fill=(25, 25, 30), width=max(2, int(4 * s)))
    elif expression in ("worried", "angry"):
        draw.arc([center_x - int(16 * s), mouth_y, center_x + int(16 * s), mouth_y + int(16 * s)], start=200, end=340, fill=(25, 25, 30), width=max(2, int(4 * s)))
    else:
        draw.line([(center_x - int(14 * s), mouth_y), (center_x + int(14 * s), mouth_y)], fill=(25, 25, 30), width=max(2, int(4 * s)))


def apply_character_consistency(storyboard: StoryboardDocument, genre: str = "") -> StoryboardDocument:
    """
    Garante que toda cena contenha a âncora visual 3D exata dos personagens presentes
    e obedeça estritamente ao ESTILO VISUAL 3D Blender + Negative Prompt global.
    """
    style_preset = get_visual_style(storyboard.visual_style)
    storyboard.style_bible_en = style_preset.positive_prefix_en
    char_map: Dict[str, CharacterProfile] = {c.name.lower(): c for c in storyboard.characters}

    for ch in storyboard.characters:
        ch.reference_prompt_en = (
            f"{style_preset.positive_prefix_en} Character 3D turnaround reference render, "
            f"{ch.visual_description_en}. Fully modeled 3D Roblox R15 avatar, neutral Blender studio lighting, "
            "clean glossy studio floor, crisp PBR details, full body three-quarter view, no text."
        )

    for scene in storyboard.scenes:
        anchors: List[str] = []
        for cname in scene.characters:
            profile = char_map.get(cname.lower())
            if profile:
                anchors.append(f"[{profile.name}: {profile.visual_description_en}]")
        if not anchors and storyboard.characters:
            lead = storyboard.characters[0]
            scene.characters = [lead.name]
            anchors.append(f"[{lead.name}: {lead.visual_description_en}]")

        anchor_block = " ".join(anchors)
        scene.visual_prompt_en = compose_3d_scene_prompt(
            raw_scene_prompt=scene.visual_prompt_en,
            style_id=style_preset.id,
            story_beat=scene.story_beat,
            genre=genre,
            camera_movement=scene.camera_movement,
            character_anchors=anchor_block,
        )
        scene.negative_prompt_en = style_preset.negative_prompt_en
    return storyboard


def generate_character_reference_sheets(
    project_dir: Path,
    storyboard: StoryboardDocument,
    settings: Optional[Dict[str, Any]] = None,
) -> List[Path]:
    """
    Gera fichas visuais de referência PNG para cada personagem em `references/`.
    Prioriza renderização 3D REAL no Blender (EEVEE/Cycles PBR) quando instalado;
    caso o Blender não esteja disponível, gera ficha de referência simplificada via Pillow.
    """
    cfg = settings or load_settings()
    ref_dir = project_dir / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    generated: List[Path] = []
    blender_exe = get_blender_executable(cfg) if cfg.get("blender", {}).get("enabled", True) else None

    if blender_exe:
        from app.blender_renderer import render_character_reference_3d

        for idx, ch in enumerate(storyboard.characters, start=1):
            out_path = ref_dir / f"ref_{idx:02d}_{ch.id}.png"
            try:
                render_character_reference_3d(
                    character=ch,
                    dest_png=out_path,
                    visual_style_id=storyboard.visual_style,
                    settings=cfg,
                )
                ch.reference_image_path = str(out_path)
                generated.append(out_path)
            except Exception:
                pass
        if len(generated) == len(storyboard.characters):
            return generated

    title_font = _load_font(44)
    sub_font = _load_font(26)
    body_font = _load_font(22)

    for idx, ch in enumerate(storyboard.characters, start=1):
        out_path = ref_dir / f"ref_{idx:02d}_{ch.id}.png"
        img = Image.new("RGBA", (1024, 1024), (15, 23, 42, 255))
        draw = ImageDraw.Draw(img)

        # Fundo estúdio gradiente sutil
        for y in range(1024):
            ratio = y / 1024.0
            r = int(18 + 18 * ratio)
            g = int(26 + 22 * ratio)
            b = int(48 + 30 * ratio)
            draw.line([(0, y), (1024, y)], fill=(r, g, b, 255))

        # Grade de estúdio
        for gx in range(0, 1024, 64):
            draw.line([(gx, 0), (gx, 1024)], fill=(255, 255, 255, 16), width=1)
        for gy in range(0, 1024, 64):
            draw.line([(0, gy), (1024, gy)], fill=(255, 255, 255, 16), width=1)

        # Cabeçalho
        draw.rounded_rectangle([40, 32, 984, 130], radius=20, fill=(30, 41, 59, 230), outline=(59, 130, 246, 180), width=2)
        draw.text((70, 50), f"REFERÊNCIA DE PERSONAGEM: {ch.name.upper()}", fill=(248, 250, 252, 255), font=title_font)
        draw.text((70, 96), f"Papel: {ch.role}  |  Estilo Roblox 3D Consistente", fill=(148, 163, 184, 255), font=sub_font)

        # Personagem principal em destaque + variações de expressão
        draw_roblox_avatar(draw, ch, center_x=310, feet_y=760, scale=1.45, expression="curious")
        draw_roblox_avatar(draw, ch, center_x=640, feet_y=590, scale=0.82, expression="shocked")
        draw_roblox_avatar(draw, ch, center_x=845, feet_y=590, scale=0.82, expression="determined")
        draw.text((575, 610), "Choque", fill=(203, 213, 225, 255), font=body_font)
        draw.text((770, 610), "Determinação", fill=(203, 213, 225, 255), font=body_font)

        # Cartão de paleta e características
        draw.rounded_rectangle([40, 795, 984, 986], radius=18, fill=(15, 23, 42, 235), outline=(71, 85, 105, 220), width=2)
        swatches = [
            ("Principal", ch.primary_color_hex),
            ("Secundária", ch.secondary_color_hex),
            ("Pele", ch.skin_color_hex),
            ("Cabelo", ch.hair_color_hex),
        ]
        for s_idx, (label, hx) in enumerate(swatches):
            sx = 70 + s_idx * 225
            draw.rounded_rectangle([sx, 818, sx + 48, 866], radius=10, fill=_hex_to_rgb(hx) + (255,), outline=(255, 255, 255, 200), width=2)
            draw.text((sx + 58, 820), label, fill=(226, 232, 240, 255), font=body_font)
            draw.text((sx + 58, 845), hx, fill=(148, 163, 184, 255), font=body_font)

        desc_line = (ch.visual_description_en[:108] + "...") if len(ch.visual_description_en) > 108 else ch.visual_description_en
        draw.text((70, 895), f"Prompt base (EN): {desc_line}", fill=(203, 213, 225, 255), font=body_font)
        draw.text((70, 932), f"Cabelo: {ch.hair_style}  |  Acessório: {ch.accessory}  |  Manter idêntico em todas as cenas", fill=(148, 163, 184, 255), font=body_font)

        img.convert("RGB").save(out_path, format="PNG")
        ch.reference_image_path = str(out_path)
        generated.append(out_path)

    return generated
