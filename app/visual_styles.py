"""Configuração global de ESTILO VISUAL 3D Roblox (padrão Blender Cinematic) aplicada a todos os geradores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


MANDATORY_BLENDER_3D_CORE = (
    "High-quality cinematic 3D Roblox animation, professionally rendered Blender-style 3D environment, "
    "fully modeled three-dimensional Roblox characters, authentic blocky Roblox avatar proportions, "
    "detailed 3D geometry, realistic depth, physically based materials, cinematic global illumination, "
    "ambient occlusion, realistic shadows, volumetric lighting, professional camera composition, "
    "depth of field, smooth character animation, detailed 3D environment, high-quality 3D render."
)

MANDATORY_NEGATIVE_PROMPT = (
    "2D illustration, flat cartoon, vector art, paper cutout characters, flat characters, "
    "flat background, simplistic poster design, motion graphics, giant typography, static character poses, "
    "sprites, low-detail environment, lack of depth, fake 3D appearance, watermark, text overlay, "
    "subtitles, giant letters, random logos, distorted limbs, extra arms, melted face, stretched aspect ratio"
)


@dataclass(frozen=True)
class VisualStylePreset:
    id: str
    label: str
    description_pt: str
    positive_prefix_en: str
    render_directives_en: str
    negative_prompt_en: str
    blender_roughness_bias: float
    blender_bloom_strength: float
    blender_color_look: str


VISUAL_STYLES: Dict[str, VisualStylePreset] = {
    "roblox_3d_blender_cinematic": VisualStylePreset(
        id="roblox_3d_blender_cinematic",
        label="Roblox 3D Blender Cinematic (Padrão)",
        description_pt=(
            "Animação 3D cinematográfica de Roblox com aparência de renderização profissional no Blender "
            "(Cycles/Eevee): materiais PBR, iluminação global, sombras suaves, ambient occlusion, "
            "luzes volumétricas e profundidade de campo."
        ),
        positive_prefix_en=MANDATORY_BLENDER_3D_CORE,
        render_directives_en=(
            "Blender Cycles/EEVEE cinematic look, physically based specular reflections, soft realistic shadows, "
            "subtle surface bevels on Roblox R15 limbs and torso, articulated 3D character motion, "
            "volumetric light shafts, cinematic color grading, vertical 9:16 framing, no on-screen text."
        ),
        negative_prompt_en=MANDATORY_NEGATIVE_PROMPT,
        blender_roughness_bias=0.32,
        blender_bloom_strength=0.18,
        blender_color_look="AgX - Medium High Contrast",
    ),
    "roblox_3d_realistic": VisualStylePreset(
        id="roblox_3d_realistic",
        label="Roblox 3D Realista",
        description_pt=(
            "Avatares Roblox 3D com proporções autênticas em cenários hiperdetalhados com texturas PBR "
            "realistas, reflexos intensos em pisos molhados/metais e iluminação cinematográfica realista."
        ),
        positive_prefix_en=(
            MANDATORY_BLENDER_3D_CORE
            + " Photorealistic PBR surface textures, ray-traced reflections, micro-detailed clothing fabrics, "
            "realistic wet asphalt and glass reflections, physically accurate atmospheric fog and lens bokeh."
        ),
        render_directives_en=(
            "Unreal Engine 5 / Blender Cycles photorealistic lighting with authentic 3D blocky Roblox avatars, "
            "high dynamic range shadows, dramatic rim light, natural motion blur, vertical 9:16 portrait."
        ),
        negative_prompt_en=MANDATORY_NEGATIVE_PROMPT + ", cel shading, anime, comic outline, plastic toy look",
        blender_roughness_bias=0.20,
        blender_bloom_strength=0.12,
        blender_color_look="AgX - High Contrast",
    ),
    "roblox_3d_cartoon_cinematic": VisualStylePreset(
        id="roblox_3d_cartoon_cinematic",
        label="Roblox 3D Cartoon Cinematográfico",
        description_pt=(
            "Animação 3D estilizada nível filme animado (Pixar/Blender 3D): geometria 3D volumosa, "
            "cores vibrantes, iluminação global rica e expressões 3D marcantes — nunca 2D chapado."
        ),
        positive_prefix_en=(
            MANDATORY_BLENDER_3D_CORE
            + " Stylized feature-film 3D animation aesthetic, expressive 3D sculpted eyebrows and eyes, "
            "rich subsurface scattering on plastic-glossy Roblox avatars, vibrant cinematic rim lights, "
            "deep layered 3D sets."
        ),
        render_directives_en=(
            "Feature-film 3D Blender animation polish, smooth articulated body animation, lively camera travelling, "
            "soft global illumination, crisp ambient occlusion, vertical 9:16 composition, strictly 3D not 2D."
        ),
        negative_prompt_en=MANDATORY_NEGATIVE_PROMPT + ", gritty photorealistic horror grain",
        blender_roughness_bias=0.38,
        blender_bloom_strength=0.24,
        blender_color_look="AgX - Medium High Contrast",
    ),
}

DEFAULT_VISUAL_STYLE_ID = "roblox_3d_blender_cinematic"

STYLE_LABEL_TO_ID: Dict[str, str] = {preset.label: preset.id for preset in VISUAL_STYLES.values()}
STYLE_ID_TO_LABEL: Dict[str, str] = {preset.id: preset.label for preset in VISUAL_STYLES.values()}


def get_visual_style(style_id_or_label: str | None) -> VisualStylePreset:
    if not style_id_or_label:
        return VISUAL_STYLES[DEFAULT_VISUAL_STYLE_ID]
    if style_id_or_label in VISUAL_STYLES:
        return VISUAL_STYLES[style_id_or_label]
    if style_id_or_label in STYLE_LABEL_TO_ID:
        return VISUAL_STYLES[STYLE_LABEL_TO_ID[style_id_or_label]]
    return VISUAL_STYLES[DEFAULT_VISUAL_STYLE_ID]


def list_visual_style_labels() -> List[str]:
    return [preset.label for preset in VISUAL_STYLES.values()]


def get_emotional_lighting_en(story_beat: str, genre: str = "") -> str:
    """Retorna diretriz de iluminação cinematográfica 3D alinhada à emoção da cena."""
    beat = (story_beat or "").lower()
    gen = (genre or "").lower()
    if any(k in beat for k in ("conflito", "clímax", "climax")):
        return (
            "dramatic high-contrast nocturnal lighting, deep atmospheric shadows, intense crimson and cold cyan "
            "rim lights, volumetric fog beams cutting through the 3D scene"
        )
    if "reviravolta" in beat or "twist" in beat:
        return (
            "cinematic golden volumetric breakthrough light, dramatic god-rays illuminating the 3D characters, "
            "rich specular reflections and emotional contrast"
        )
    if "final" in beat or "ending" in beat:
        return (
            "moody twilight cinematic lighting, glowing portal backlight, soft atmospheric haze, "
            "shallow depth of field focusing on the character silhouette"
        )
    if any(k in gen for k in ("suspense", "terror", "mistério", "misterio")):
        return (
            "cinematic nocturnal suspense lighting, cool moonlight blue key light, warm practical streetlights, "
            "soft ambient occlusion shadows and volumetric depth"
        )
    if any(k in gen for k in ("coméd", "comed", "avent")):
        return (
            "vibrant golden-hour cinematic 3D global illumination, crisp soft shadows, glossy PBR reflections, "
            "bright atmospheric depth"
        )
    return (
        "cinematic three-point 3D global illumination, realistic soft shadows, volumetric rim lighting, "
        "shallow depth of field"
    )


def get_camera_language_en(camera_movement: str) -> str:
    mapping = {
        "slow_zoom_in": "smooth cinematic dolly-in camera movement with shallow depth of field",
        "slow_zoom_out": "cinematic dolly-out pull-back revealing the full 3D environment depth",
        "pan_left": "smooth horizontal 3D travelling pan to the left across the detailed set",
        "pan_right": "smooth horizontal 3D travelling pan to the right following character motion",
        "tilt_up": "dramatic low-angle upward 3D camera tilt emphasizing architectural scale",
        "dramatic_push": "dynamic tense close-up push-in camera movement locking onto character expression",
        "parallax_drift": "cinematic 3D orbiting tracking shot with strong foreground-background parallax",
    }
    return mapping.get(camera_movement, "dynamic cinematic 3D tracking camera movement with depth of field")


def compose_3d_scene_prompt(
    raw_scene_prompt: str,
    style_id: str,
    story_beat: str,
    genre: str,
    camera_movement: str,
    character_anchors: str = "",
) -> str:
    """
    Garante que TODOS os prompts (Flow, Wan 2.2, ComfyUI, Gemini/Ollama) obedeçam
    estritamente ao ESTILO VISUAL 3D Blender selecionado, sem desvio para 2D chapado.
    """
    preset = get_visual_style(style_id)
    lighting = get_emotional_lighting_en(story_beat, genre)
    camera = get_camera_language_en(camera_movement)

    # Evita duplicar o bloco obrigatório caso já esteja presente
    body = raw_scene_prompt.strip()
    if MANDATORY_BLENDER_3D_CORE[:45].lower() in body.lower():
        core_prefix = ""
    else:
        core_prefix = f"{preset.positive_prefix_en} "

    anchor_part = f"Consistent 3D Roblox characters: {character_anchors}. " if character_anchors and character_anchors not in body else ""
    return (
        f"{core_prefix}"
        f"{anchor_part}"
        f"{body}. "
        f"Lighting: {lighting}. "
        f"Camera: {camera}. "
        f"{preset.render_directives_en}"
    ).strip()
