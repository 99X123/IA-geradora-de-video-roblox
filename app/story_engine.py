"""Motor de criação de histórias e storyboards estruturados (Ollama + Gemma 3, Gemini API/Web e fallback local)."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_gemini_api_key, load_settings
from app.models import CharacterProfile, SceneSpec, StoryboardDocument, StoryDocument
from app.visual_styles import (
    DEFAULT_VISUAL_STYLE_ID,
    MANDATORY_BLENDER_3D_CORE,
    compose_3d_scene_prompt,
    get_visual_style,
)

STORY_OPENINGS = [
    "Neste servidor...",
    "Nesta cidade...",
    "Neste mundo...",
    "Nesta escola...",
    "Neste lugar, existia uma regra...",
    "Todos os jogadores precisavam...",
]

STORY_GENRES = [
    "Suspense / Mistério",
    "Terror Leve / Sobrevivência",
    "Aventura / Ação",
    "Reviravolta / Drama",
    "Comédia / Caos no Servidor",
    "Ficção Científica / Regra Secreta",
]

CAMERA_CYCLE = [
    "slow_zoom_in",
    "pan_right",
    "dramatic_push",
    "pan_left",
    "tilt_up",
    "parallax_drift",
    "slow_zoom_out",
    "dramatic_push",
]

THEME_KEYWORDS: Dict[str, List[str]] = {
    "school": ["escola", "sala", "professor", "aula", "recreio", "corredor", "diretor", "colégio"],
    "city": ["cidade", "rua", "prédio", "shopping", "praça", "carro", "bairro", "vizinho"],
    "forest": ["floresta", "mata", "árvore", "acampamento", "trilha", "cabana", "neblina"],
    "castle": ["castelo", "masmorra", "rei", "torre", "medieval", "espada", "caverna", "portal"],
    "neon": ["futuro", "robô", "cyber", "neon", "laboratório", "holograma", "laser", "espaço"],
    "hallway": ["porta", "elevador", "hotel", "hospital", "corredor", "quarto", "porão", "casa"],
    "server": ["servidor", "admin", "jogo", "jogador", "roblox", "mapa", "lobby", "banido", "hacker", "regra"],
}

THEME_ENV_ENGLISH: Dict[str, str] = {
    "school": "stylized 3D Roblox high school hallway and classroom with lockers, dramatic shafts of window light, detailed desks",
    "city": "vibrant yet atmospheric 3D Roblox Brookhaven-style modern city street with blocky skyscrapers, glowing streetlights, reflections",
    "forest": "mysterious 3D Roblox blocky pine forest at twilight with volumetric mist, glowing fireflies, wooden cabin in background",
    "castle": "epic 3D Roblox fantasy stone fortress and glowing ancient portal with torches, cobblestone ground, dramatic sky",
    "neon": "cinematic 3D Roblox futuristic cyber-neon plaza with glowing cyan and magenta signs, sleek glossy blocky architecture",
    "hallway": "tense 3D Roblox dimly lit long corridor with numbered doors, flickering overhead lights, dramatic shadows",
    "server": "cinematic 3D Roblox game server plaza with floating leaderboard holograms, glowing spawn pad, dramatic skybox and volumetric fog",
}

DEFAULT_CHARACTER_PALETTES = [
    ("#2563EB", "#1E293B", "#F3C69F", "#2B1B12", "spiky", "backpack", "blue hoodie jacket, dark navy pants, white sneakers, dark spiky hair, black backpack"),
    ("#DC2626", "#111827", "#F2C29B", "#18181B", "hood", "headphones", "red streetwear jacket, black cargo pants, neon red headphones, confident look"),
    ("#16A34A", "#1F2937", "#E6B28A", "#4A321F", "cap", "scarf", "emerald green vest over white shirt, dark jeans, backwards cap, yellow scarf"),
    ("#9333EA", "#0F172A", "#F6D0B1", "#1F2937", "crown", "cape", "purple glowing admin cloak, obsidian armor trim, floating golden visor crown"),
]


def _extract_json_block(raw_text: str) -> Dict[str, Any]:
    """Extrai objeto JSON válido mesmo quando o modelo envolve a saída em ```json ... ```."""
    cleaned = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def build_master_llm_prompt(
    story_input: str,
    genre: str,
    opening_style: str,
    duration_seconds: int,
    scene_count: int = 8,
    visual_style: str = DEFAULT_VISUAL_STYLE_ID,
) -> str:
    """Constrói o prompt mestre usado no Ollama (Gemma 3), na API Gemini ou no Gemini Web (Google AI Pro)."""
    style_preset = get_visual_style(visual_style)
    return f"""Você é um roteirista profissional e diretor de animação 3D de YouTube Shorts e TikTok especializado em histórias cinematográficas 3D de Roblox (estilo Blender Cycles/EEVEE) em Português do Brasil.

TAREFA:
Transforme a ideia/história do usuário em um roteiro completo, dinâmico e viciante para vídeo vertical 9:16 com duração alvo de {duration_seconds} segundos e exatamente {scene_count} cenas.

ESTILO VISUAL GLOBAL OBRIGATÓRIO (BLOQUEADO — NÃO ALTERAR ENTRE CENAS):
- Estilo selecionado: {style_preset.label}
- Padrão obrigatório: {style_preset.positive_prefix_en}
- PROIBIDO: ilustração 2D, desenho chapado, arte vetorial, personagens estáticos ou textos/letras dentro da cena.

REGRAS OBRIGATÓRIAS:
1. Toda a história, narração, título, descrição e hashtags devem estar em PORTUGUÊS DO BRASIL natural, expressivo e sem repetições.
2. O gancho inicial DEVE começar com ou seguir fortemente o estilo "{opening_style}" e prender a atenção nos primeiros 2 segundos.
3. Sem introduções lentas, sem diálogos vazios, sem enrolação. Cada cena precisa avançar a trama.
4. Estrutura obrigatória: Gancho -> Situação -> Desenvolvimento -> Conflito -> Clímax -> Reviravolta -> Final surpreendente.
5. TODOS os prompts visuais (`visual_prompt_en`) devem ser escritos em INGLÊS cinematográfico de animação 3D Blender de Roblox (com cenários 3D profundos, avatares 3D articulados andando/correndo/gesticulando, iluminação PBR e movimento de câmera), mantendo o MESMO estilo visual e os MESMOS personagens em todas as cenas.
6. NUNCA inclua textos, títulos, placas com letras gigantes ou legendas nos prompts visuais — as legendas serão adicionadas depois pelo editor.
7. Retorne APENAS um JSON válido seguindo EXATAMENTE o esquema abaixo (sem comentários extras fora do JSON).

IDEIA DO USUÁRIO:
\"\"\"{story_input.strip()}\"\"\"

GÊNERO ESCOLHIDO: {genre}
ESTILO DE ABERTURA: {opening_style}
ESTILO VISUAL BLOQUEADO: {style_preset.label}
DURAÇÃO ALVO: {duration_seconds} segundos
QUANTIDADE DE CENAS: {scene_count}

ESQUEMA JSON OBRIGATÓRIO:
{{
  "story": {{
    "title": "Título curto e chamativo em PT-BR",
    "hook_pt": "Primeira frase de alto impacto",
    "genre": "{genre}",
    "opening_style": "{opening_style}",
    "setup_pt": "Apresentação rápida da situação",
    "development_pt": "Desenvolvimento da tensão",
    "conflict_pt": "Conflito central",
    "climax_pt": "Ponto máximo de tensão",
    "twist_pt": "Reviravolta inesperada",
    "ending_pt": "Final impactante",
    "suggested_title": "Título otimizado para YouTube Shorts / TikTok",
    "suggested_description": "Descrição curta para postagem",
    "suggested_hashtags": ["#Roblox", "#RobloxBrasil", "#HistoriasRoblox", "#Shorts"]
  }},
  "style_bible_en": "{style_preset.positive_prefix_en}",
  "characters": [
    {{
      "id": "char_1",
      "name": "Nome do personagem",
      "role": "Protagonista",
      "visual_description_en": "Fully modeled 3D Blender-style Roblox R15 avatar in English (3D sculpted hair, voluminous PBR clothing, exact colors and accessories kept identical in every scene)",
      "visual_description_pt": "Descrição curta em PT-BR",
      "primary_color_hex": "#2563EB",
      "secondary_color_hex": "#1E293B",
      "skin_color_hex": "#F3C69F",
      "hair_color_hex": "#2B1B12",
      "hair_style": "spiky",
      "accessory": "backpack"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "title": "Título curto da cena",
      "story_beat": "Gancho",
      "description_pt": "O que acontece visualmente nesta cena",
      "narration_pt": "Trecho exato narrado nesta cena (natural, 1 a 2 frases curtas)",
      "visual_prompt_en": "{MANDATORY_BLENDER_3D_CORE} Detailed 3D Roblox environment and articulated character movement in English, dramatic lighting, dynamic camera, vertical 9:16, no text",
      "characters": ["Nome do personagem"],
      "setting_pt": "Cenário 3D em PT-BR",
      "setting_theme": "server",
      "movements_en": "Dynamic 3D character action (walking, running, turning, gesturing) in English",
      "expression": "curious",
      "camera_movement": "slow_zoom_in",
      "duration_seconds": 6.5,
      "sfx_cue": "transition"
    }}
  ]
}}
Valores válidos para setting_theme: city, school, server, forest, castle, neon, hallway.
Valores válidos para expression: neutral, curious, happy, worried, scared, angry, shocked, determined.
Valores válidos para camera_movement: slow_zoom_in, slow_zoom_out, pan_left, pan_right, tilt_up, dramatic_push, parallax_drift.
Valores válidos para sfx_cue: none, transition, surprise, ambient.
"""


def parse_and_validate_llm_payload(
    raw_text: str,
    project_id: str,
    genre: str,
    opening_style: str,
    duration_seconds: int,
    provider_label: str,
    visual_style: str = DEFAULT_VISUAL_STYLE_ID,
) -> Tuple[StoryDocument, StoryboardDocument]:
    """Valida JSON vindo de Ollama, Gemini API ou colado do Gemini Web (Google AI Pro), travando o Estilo Visual 3D."""
    style_preset = get_visual_style(visual_style)
    data = _extract_json_block(raw_text)
    story_raw = data.get("story") or {}
    chars_raw = data.get("characters") or []
    scenes_raw = data.get("scenes") or []

    if not scenes_raw or len(scenes_raw) < 4:
        raise ValueError("O JSON retornado contém menos de 4 cenas válidas.")

    characters: List[CharacterProfile] = []
    for idx, ch in enumerate(chars_raw[:4], start=1):
        pal = DEFAULT_CHARACTER_PALETTES[(idx - 1) % len(DEFAULT_CHARACTER_PALETTES)]
        characters.append(
            CharacterProfile(
                id=str(ch.get("id") or f"char_{idx}"),
                name=str(ch.get("name") or f"Jogador {idx}").strip(),
                role=str(ch.get("role") or ("Protagonista" if idx == 1 else "Personagem")),
                visual_description_en=str(
                    ch.get("visual_description_en")
                    or f"Roblox 3D R15 blocky avatar wearing {pal[6]}"
                ),
                visual_description_pt=str(ch.get("visual_description_pt") or "Personagem estilizado Roblox 3D"),
                primary_color_hex=_safe_hex(ch.get("primary_color_hex"), pal[0]),
                secondary_color_hex=_safe_hex(ch.get("secondary_color_hex"), pal[1]),
                skin_color_hex=_safe_hex(ch.get("skin_color_hex"), pal[2]),
                hair_color_hex=_safe_hex(ch.get("hair_color_hex"), pal[3]),
                hair_style=str(ch.get("hair_style") or pal[4]),
                accessory=str(ch.get("accessory") or pal[5]),
            )
        )

    if not characters:
        pal = DEFAULT_CHARACTER_PALETTES[0]
        characters.append(
            CharacterProfile(
                id="char_1",
                name="Lucas",
                role="Protagonista",
                visual_description_en=f"Young Roblox 3D R15 protagonist avatar wearing {pal[6]}",
                visual_description_pt="Protagonista Roblox com moletom azul, calça escura e mochila preta",
                primary_color_hex=pal[0],
                secondary_color_hex=pal[1],
                skin_color_hex=pal[2],
                hair_color_hex=pal[3],
                hair_style=pal[4],
                accessory=pal[5],
            )
        )

    scenes: List[SceneSpec] = []
    valid_themes = set(THEME_ENV_ENGLISH.keys())
    valid_exprs = {"neutral", "curious", "happy", "worried", "scared", "angry", "shocked", "determined"}
    valid_cams = set(CAMERA_CYCLE)
    valid_sfx = {"none", "transition", "surprise", "ambient"}

    avg_dur = max(4.0, min(10.0, round(duration_seconds / max(len(scenes_raw), 1), 1)))
    for idx, sc in enumerate(scenes_raw[:10], start=1):
        theme = str(sc.get("setting_theme") or "server").lower()
        if theme not in valid_themes:
            theme = _infer_theme(str(sc.get("setting_pt") or "") + " " + str(sc.get("description_pt") or ""))
        expr = str(sc.get("expression") or "curious").lower()
        if expr not in valid_exprs:
            expr = "curious"
        cam = str(sc.get("camera_movement") or CAMERA_CYCLE[(idx - 1) % len(CAMERA_CYCLE)]).lower()
        if cam not in valid_cams:
            cam = CAMERA_CYCLE[(idx - 1) % len(CAMERA_CYCLE)]
        sfx = str(sc.get("sfx_cue") or ("surprise" if idx in (len(scenes_raw) - 1, len(scenes_raw)) else "transition")).lower()
        if sfx not in valid_sfx:
            sfx = "transition"

        dur_val = sc.get("duration_seconds")
        try:
            dur = max(3.5, min(12.0, float(dur_val))) if dur_val else avg_dur
        except Exception:
            dur = avg_dur

        raw_prompt = str(
            sc.get("visual_prompt_en")
            or f"{THEME_ENV_ENGLISH[theme]}, articulated 3D Roblox avatar movement, vertical 9:16"
        ).strip()
        enforced_prompt = compose_3d_scene_prompt(
            raw_scene_prompt=raw_prompt,
            style_id=style_preset.id,
            story_beat=str(sc.get("story_beat") or "Desenvolvimento"),
            genre=genre,
            camera_movement=cam,
        )

        scenes.append(
            SceneSpec(
                scene_number=idx,
                title=str(sc.get("title") or f"Cena {idx}").strip(),
                story_beat=str(sc.get("story_beat") or "Desenvolvimento"),
                description_pt=str(sc.get("description_pt") or sc.get("narration_pt") or f"Cena {idx} da história"),
                narration_pt=str(sc.get("narration_pt") or sc.get("description_pt") or "").strip(),
                visual_prompt_en=enforced_prompt,
                negative_prompt_en=style_preset.negative_prompt_en,
                characters=[str(c) for c in (sc.get("characters") or [characters[0].name])],
                setting_pt=str(sc.get("setting_pt") or "Servidor Roblox"),
                setting_theme=theme,
                movements_en=str(sc.get("movements_en") or "articulated 3D character walking and expressive gesture"),
                expression=expr,
                camera_movement=cam,
                duration_seconds=dur,
                sfx_cue=sfx,
            )
        )

    full_narration = " ".join(s.narration_pt.strip() for s in scenes if s.narration_pt.strip())
    hashtags = story_raw.get("suggested_hashtags") or [
        "#Roblox",
        "#RobloxBrasil",
        "#HistoriasDeRoblox",
        "#Shorts",
        "#TikTokRoblox",
    ]
    if isinstance(hashtags, str):
        hashtags = [h.strip() for h in hashtags.split() if h.strip()]

    title = str(story_raw.get("title") or "A Regra Secreta do Servidor").strip()
    story_doc = StoryDocument(
        title=title,
        hook_pt=str(story_raw.get("hook_pt") or scenes[0].narration_pt),
        genre=str(story_raw.get("genre") or genre),
        opening_style=str(story_raw.get("opening_style") or opening_style),
        setup_pt=str(story_raw.get("setup_pt") or (scenes[1].narration_pt if len(scenes) > 1 else "")),
        development_pt=str(story_raw.get("development_pt") or (scenes[2].narration_pt if len(scenes) > 2 else "")),
        conflict_pt=str(story_raw.get("conflict_pt") or (scenes[3].narration_pt if len(scenes) > 3 else "")),
        climax_pt=str(story_raw.get("climax_pt") or (scenes[-3].narration_pt if len(scenes) >= 4 else "")),
        twist_pt=str(story_raw.get("twist_pt") or (scenes[-2].narration_pt if len(scenes) >= 3 else "")),
        ending_pt=str(story_raw.get("ending_pt") or scenes[-1].narration_pt),
        full_narration_pt=full_narration,
        suggested_title=str(story_raw.get("suggested_title") or f"{title} | História de Roblox"),
        suggested_description=str(
            story_raw.get("suggested_description")
            or f"{story_raw.get('hook_pt') or title} Assista até o final para ver a reviravolta!"
        ),
        suggested_hashtags=[str(h) for h in hashtags[:10]],
        story_provider=provider_label,
    )

    storyboard = StoryboardDocument(
        project_id=project_id,
        target_duration_seconds=duration_seconds,
        visual_style=style_preset.id,
        style_bible_en=style_preset.positive_prefix_en,
        characters=characters,
        scenes=scenes,
        validated=True,
    )
    return story_doc, storyboard


def _safe_hex(val: Any, fallback: str) -> str:
    if isinstance(val, str) and re.match(r"^#[0-9A-Fa-f]{6}$", val.strip()):
        return val.strip()
    return fallback


def _infer_theme(text: str) -> str:
    low = text.lower()
    best_theme = "server"
    best_score = 0
    for theme, keywords in THEME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in low)
        if score > best_score:
            best_score = score
            best_theme = theme
    return best_theme


def _extract_character_names(text: str) -> List[str]:
    stopwords = {
        "Neste", "Nesta", "Todos", "Todas", "Quando", "Depois", "Antes", "Então", "Mas", "Porém",
        "Roblox", "Servidor", "Cidade", "Escola", "Mundo", "Regra", "Noite", "Dia", "Um", "Uma",
        "Ele", "Ela", "Eles", "Elas", "Você", "Ninguém", "Alguém", "Tudo", "Nada", "Onde", "Como",
        "Porque", "Até", "Sem", "Com", "Para", "Sobre", "Meia", "Final", "História", "Porta", "Jogo",
    }
    found: List[str] = []
    # Busca nomes próprios capitalizados após o início das frases ou após "chamado/a"
    for m in re.finditer(r"(?:chamado|chamada|jogador|amiga|amigo|admin|misterioso)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,14})", text, flags=re.IGNORECASE):
        cand = m.group(1).capitalize()
        if cand not in stopwords and cand not in found:
            found.append(cand)
    for m in re.finditer(r"(?<!^)(?<![.!?]\s)\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,14})\b", text):
        cand = m.group(1)
        if cand not in stopwords and cand not in found:
            found.append(cand)
    return found[:3]


def _split_user_sentences(text: str) -> List[str]:
    clean = re.sub(r"\s+", " ", text.strip())
    if not clean:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", clean) if p.strip()]
    return parts


def _build_local_structured_story(
    story_input: str,
    project_id: str,
    genre: str,
    opening_style: str,
    duration_seconds: int,
    scene_count: int = 8,
    visual_style: str = DEFAULT_VISUAL_STYLE_ID,
) -> Tuple[StoryDocument, StoryboardDocument]:
    """
    Estruturador narrativo local 100% offline (determinístico) usado quando o Ollama
    não está ativo e nenhuma chave de API Gemini foi informada.
    Preserva a história do usuário, organiza em 6 a 10 cenas com arco dramático completo
    e gera prompts consistentes em inglês 3D Blender para Flow/ComfyUI/Blender.
    """
    style_preset = get_visual_style(visual_style)
    raw = story_input.strip()
    if not raw:
        raw = "Um jogador descobre que ninguém pode olhar para trás depois da meia-noite no servidor secreto."

    theme = _infer_theme(raw)
    names = _extract_character_names(raw)
    protagonist_name = names[0] if names else "Lucas"
    secondary_name = names[1] if len(names) > 1 else "Admin Sombrio"

    pal1 = DEFAULT_CHARACTER_PALETTES[0]
    pal2 = DEFAULT_CHARACTER_PALETTES[3] if "admin" in secondary_name.lower() or "sombrio" in secondary_name.lower() else DEFAULT_CHARACTER_PALETTES[1]

    characters = [
        CharacterProfile(
            id="char_protagonista",
            name=protagonist_name,
            role="Protagonista",
            visual_description_en=(
                f"Roblox 3D R15 protagonist avatar named {protagonist_name}, wearing {pal1[6]}, "
                "expressive glossy stylized face, consistent outfit in every scene"
            ),
            visual_description_pt=f"{protagonist_name}: avatar Roblox com moletom azul, calça azul-marinho, tênis branco e mochila preta.",
            primary_color_hex=pal1[0],
            secondary_color_hex=pal1[1],
            skin_color_hex=pal1[2],
            hair_color_hex=pal1[3],
            hair_style=pal1[4],
            accessory=pal1[5],
        ),
        CharacterProfile(
            id="char_antagonista",
            name=secondary_name,
            role="Figura Misteriosa / Rival",
            visual_description_en=(
                f"Mysterious Roblox 3D R15 character named {secondary_name}, wearing {pal2[6]}, "
                "dramatic rim lighting, unmistakable silhouette kept consistent in every scene"
            ),
            visual_description_pt=f"{secondary_name}: figura misteriosa com capa escura/roxa e detalhes brilhantes.",
            primary_color_hex=pal2[0],
            secondary_color_hex=pal2[1],
            skin_color_hex=pal2[2],
            hair_color_hex=pal2[3],
            hair_style=pal2[4],
            accessory=pal2[5],
        ),
    ]

    user_sentences = _split_user_sentences(raw)
    premise = user_sentences[0].rstrip(".!?")
    opening_prefix = opening_style.rstrip(". ")
    if premise.lower().startswith(opening_prefix.lower()):
        hook_line = premise + "."
    else:
        first_char = premise[0].lower() + premise[1:] if len(premise) > 1 else premise.lower()
        hook_line = f"{opening_prefix}, {first_char}."

    # Preenche os 8 beats aproveitando frases reais da história do usuário quando presentes
    extra = user_sentences[1:]
    beat_templates = [
        (
            "Gancho",
            "A Regra Impossível",
            hook_line,
            "curious",
            "slow_zoom_in",
            "transition",
            [protagonist_name],
            f"{protagonist_name} enters the scene looking amazed and alert, floating mysterious rule sign glowing ahead",
        ),
        (
            "Situação",
            "O Primeiro Sinal",
            extra[0] if len(extra) > 0 else f"{protagonist_name} achou que era só uma brincadeira do jogo, até as luzes do mapa piscarem de repente.",
            "neutral",
            "pan_right",
            "ambient",
            [protagonist_name],
            f"{protagonist_name} walks forward cautiously inspecting the surroundings as ambient lights flicker dramatically",
        ),
        (
            "Desenvolvimento",
            "Algo Mudou",
            extra[1] if len(extra) > 1 else f"Um aviso vermelho apareceu na tela de todos os jogadores e o botão de sair simplesmente desapareceu.",
            "worried",
            "dramatic_push",
            "transition",
            [protagonist_name],
            f"close-up of {protagonist_name} reacting to a glowing red holographic alert hovering in front of him",
        ),
        (
            "Conflito",
            "A Aparição",
            extra[2] if len(extra) > 2 else f"Foi então que {secondary_name} surgiu no fim do caminho observando cada movimento em silêncio.",
            "scared",
            "pan_left",
            "surprise",
            [protagonist_name, secondary_name],
            f"{secondary_name} stands menacingly across the path with glowing dramatic backlight while {protagonist_name} freezes in shock",
        ),
        (
            "Escalada",
            "Contra o Tempo",
            extra[3] if len(extra) > 3 else f"A contagem regressiva começou a cair rápido e só restava uma única chance para escapar sem quebrar a regra.",
            "determined",
            "parallax_drift",
            "transition",
            [protagonist_name, secondary_name],
            f"dynamic action shot of {protagonist_name} sprinting past obstacles while glowing sparks and countdown hologram flash",
        ),
        (
            "Clímax",
            "A Escolha Decisiva",
            extra[4] if len(extra) > 4 else f"Encurralado no último segundo, {protagonist_name} percebeu um detalhe escondido que ninguém tinha notado antes.",
            "shocked",
            "dramatic_push",
            "surprise",
            [protagonist_name, secondary_name],
            f"intense cinematic close-up of {protagonist_name} reaching toward a glowing hidden switch while {secondary_name} closes in",
        ),
        (
            "Reviravolta",
            "A Verdade Revelada",
            extra[5] if len(extra) > 5 else f"Mas quando o segredo se abriu, ele descobriu a verdade: {secondary_name} não estava perseguindo ninguém, estava tentando protegê-lo.",
            "shocked",
            "tilt_up",
            "surprise",
            [protagonist_name, secondary_name],
            f"dramatic golden beam illuminates the whole set as {secondary_name} lowers guard and reveals the hidden truth behind the server",
        ),
        (
            "Final",
            "A Última Mensagem",
            extra[6] if len(extra) > 6 else f"{protagonist_name} escapou a tempo, mas na tela inicial apareceu uma mensagem dizendo: amanhã a regra muda de novo. Você entraria?",
            "curious",
            "slow_zoom_out",
            "transition",
            [protagonist_name],
            f"{protagonist_name} stands at the glowing exit portal looking back over shoulder toward camera with mysterious cliffhanger glow",
        ),
    ]

    target_scenes = max(6, min(10, scene_count))
    selected_beats = beat_templates[:target_scenes]
    # Ajusta duração por cena proporcionalmente ao tamanho do texto narrado
    word_counts = [max(4, len(b[2].split())) for b in selected_beats]
    total_words = sum(word_counts)
    env_en = THEME_ENV_ENGLISH.get(theme, THEME_ENV_ENGLISH["server"])
    setting_pt_map = {
        "school": "Escola misteriosa no Roblox",
        "city": "Cidade movimentada no Roblox",
        "forest": "Floresta nebulosa no Roblox",
        "castle": "Castelo antigo no Roblox",
        "neon": "Arena futurista neon no Roblox",
        "hallway": "Corredor iluminado por luzes piscando",
        "server": "Servidor secreto no Roblox",
    }

    scenes: List[SceneSpec] = []
    for idx, (beat, stitle, narration, expr, cam, sfx, ch_names, action_en) in enumerate(selected_beats, start=1):
        dur = round(max(4.5, min(9.5, duration_seconds * (word_counts[idx - 1] / total_words))), 1)
        raw_scene_desc = (
            f"Vertical 9:16 3D Blender Roblox scene in {env_en}. "
            f"{action_en}. Character facial expression: {expr}."
        )
        visual_prompt = compose_3d_scene_prompt(
            raw_scene_prompt=raw_scene_desc,
            style_id=style_preset.id,
            story_beat=beat,
            genre=genre,
            camera_movement=cam,
        )
        scenes.append(
            SceneSpec(
                scene_number=idx,
                title=stitle,
                story_beat=beat,
                description_pt=f"[{beat}] {narration}",
                narration_pt=narration,
                visual_prompt_en=visual_prompt,
                negative_prompt_en=style_preset.negative_prompt_en,
                characters=ch_names,
                setting_pt=setting_pt_map.get(theme, "Servidor Roblox"),
                setting_theme=theme,
                movements_en=action_en,
                expression=expr,
                camera_movement=cam,
                duration_seconds=dur,
                sfx_cue=sfx,
            )
        )

    short_title = premise[:54].strip()
    if len(premise) > 54:
        short_title = short_title.rsplit(" ", 1)[0] + "..."
    title_clean = short_title[0].upper() + short_title[1:] if short_title else "O Segredo do Servidor Roblox"

    story_doc = StoryDocument(
        title=title_clean,
        hook_pt=scenes[0].narration_pt,
        genre=genre,
        opening_style=opening_style,
        setup_pt=scenes[1].narration_pt,
        development_pt=scenes[2].narration_pt,
        conflict_pt=scenes[3].narration_pt,
        climax_pt=scenes[-3].narration_pt,
        twist_pt=scenes[-2].narration_pt,
        ending_pt=scenes[-1].narration_pt,
        full_narration_pt=" ".join(s.narration_pt for s in scenes),
        suggested_title=f"{title_clean} 😱 | História de Roblox",
        suggested_description=(
            f"{scenes[0].narration_pt}\n\n"
            "Assista até o último segundo para descobrir a reviravolta! "
            "Comente o que você faria nesse servidor."
        ),
        suggested_hashtags=[
            "#Roblox",
            "#RobloxBrasil",
            "#HistoriasDeRoblox",
            "#Shorts",
            "#TikTokRoblox",
            "#RobloxStory",
        ],
        story_provider="local_structured_offline",
    )

    storyboard = StoryboardDocument(
        project_id=project_id,
        target_duration_seconds=duration_seconds,
        visual_style=style_preset.id,
        style_bible_en=style_preset.positive_prefix_en,
        characters=characters,
        scenes=scenes,
        validated=True,
    )
    return story_doc, storyboard


def _generate_via_ollama(
    prompt: str,
    ollama_url: str,
    model_name: str,
    timeout_seconds: int = 120,
) -> str:
    """Chama Ollama localmente (ex.: Gemma 3) para geração 100% gratuita e offline."""
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": "Você responde estritamente em JSON válido seguindo o esquema solicitado, com narrativa em Português do Brasil e prompts visuais em inglês.",
            },
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.75},
    }
    resp = httpx.post(
        f"{ollama_url.rstrip('/')}/api/chat",
        json=payload,
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Ollama retornou resposta vazia.")
    return content


def _generate_via_gemini_api(
    prompt: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash",
) -> str:
    """Chama a API oficial do Google Gemini via SDK google-genai usando chave fornecida pelo usuário."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.75,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("A API Gemini retornou resposta vazia.")
    return text


def generate_story_and_storyboard(
    story_input: str,
    project_id: str,
    genre: str = "Suspense / Mistério",
    opening_style: str = "Neste servidor...",
    duration_seconds: int = 55,
    visual_style: str = DEFAULT_VISUAL_STYLE_ID,
    preferred_provider: str = "auto",
    force_local_only: bool = False,
    gemini_api_key: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[StoryDocument, StoryboardDocument, List[str]]:
    """
    Gera história e storyboard validados.
    Ordem de prioridade:
      - Se `force_local_only=True` (Modo 100% Gratuito): usa apenas Ollama + Gemma 3 local ou estruturador local offline.
      - Caso contrário (`auto` / `gemini_api` / `ollama`): tenta provedor selecionado, faz fallback seguro para Ollama local e, por fim, estruturador offline.
    Retorna (StoryDocument, StoryboardDocument, notas_de_execucao).
    """
    cfg = settings or load_settings()
    notes: List[str] = []
    scene_count = max(
        int(cfg["generation"].get("min_scenes", 6)),
        min(int(cfg["generation"].get("max_scenes", 10)), int(round(duration_seconds / 7.0))),
    )
    prompt = build_master_llm_prompt(
        story_input=story_input,
        genre=genre,
        opening_style=opening_style,
        duration_seconds=duration_seconds,
        scene_count=scene_count,
        visual_style=visual_style,
    )

    ollama_url = cfg["story_ai"]["ollama_url"]
    ollama_model = cfg["story_ai"]["ollama_model"]
    timeout_sec = int(cfg["story_ai"].get("timeout_seconds", 120))
    api_key = None if force_local_only else get_gemini_api_key(gemini_api_key)

    # 1. Tenta API Gemini se explicitamente solicitada ou disponível fora do modo 100% local
    if not force_local_only and preferred_provider in ("auto", "gemini_api") and api_key:
        try:
            raw = _generate_via_gemini_api(
                prompt=prompt,
                api_key=api_key,
                model_name=cfg["story_ai"].get("gemini_model", "gemini-2.5-flash"),
            )
            story_doc, sb_doc = parse_and_validate_llm_payload(
                raw,
                project_id,
                genre,
                opening_style,
                duration_seconds,
                provider_label="google_gemini_api",
                visual_style=visual_style,
            )
            notes.append("Roteiro gerado com sucesso via API oficial Google Gemini.")
            return story_doc, sb_doc, notes
        except Exception as exc:
            notes.append(f"API Gemini indisponível ({exc}). Alternando automaticamente para IA local (Ollama).")

    # 2. Tenta Ollama + Gemma 3 local (100% gratuito e offline)
    if preferred_provider in ("auto", "ollama", "gemini_api"):
        try:
            tags_resp = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=0.8)
            if tags_resp.status_code == 200:
                installed = [m.get("name", "") for m in tags_resp.json().get("models", [])]
                chosen_model = ollama_model
                if installed and chosen_model not in installed:
                    gemma_matches = [m for m in installed if "gemma" in m.lower()]
                    chosen_model = gemma_matches[0] if gemma_matches else installed[0]
                if installed:
                    raw = _generate_via_ollama(prompt, ollama_url, chosen_model, timeout_seconds=timeout_sec)
                    story_doc, sb_doc = parse_and_validate_llm_payload(
                        raw,
                        project_id,
                        genre,
                        opening_style,
                        duration_seconds,
                        provider_label=f"ollama:{chosen_model}",
                        visual_style=visual_style,
                    )
                    notes.append(f"Roteiro gerado localmente via Ollama ({chosen_model}) — 100% gratuito e offline.")
                    return story_doc, sb_doc, notes
                notes.append("Ollama ativo, mas sem modelos baixados. Execute: ollama pull gemma3:4b")
        except Exception as exc:
            notes.append(f"Ollama local não detectado em {ollama_url} ({exc}).")

    # 3. Estruturador narrativo local offline (garante continuidade sem travar o projeto)
    story_doc, sb_doc = _build_local_structured_story(
        story_input=story_input,
        project_id=project_id,
        genre=genre,
        opening_style=opening_style,
        duration_seconds=duration_seconds,
        scene_count=scene_count,
        visual_style=visual_style,
    )
    notes.append(
        "Usado estruturador narrativo local offline (determinístico) para organizar a história em cenas válidas. "
        "Dica: instale o Ollama + Gemma 3 para criação com LLM local ou use a aba Gemini Web (Google AI Pro)."
    )
    return story_doc, sb_doc, notes
