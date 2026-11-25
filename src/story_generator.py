"""AutoShorts AI — Pluggable AI Story, Character & Dialogue Generator (PT-BR & Multi-language)."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.config import AutoShortsConfig, PROJECT_ROOT, get_secret
from src.utils import setup_logger

logger = setup_logger("autoshorts.story")

AVAILABLE_SETS = (
    "living_room",
    "living_room_night",
    "kitchen",
    "kitchen_night",
    "entry_hall",
    "town_square",
    "town_square_golden",
    "town_square_attack",
    "studio",
)

AVAILABLE_RIGS = ("human", "bot", "pigeon", "phantom", "mech", "rock")

AVAILABLE_EMOTIONS = (
    "neutral",
    "happy",
    "excited",
    "shock",
    "panic",
    "angry",
    "deadpan",
    "sad",
    "smug",
    "confused",
)

AVAILABLE_ACTIONS = (
    "idle",
    "walk",
    "run",
    "talk",
    "explain",
    "shock",
    "panic",
    "celebrate",
    "jump",
    "point",
    "sit",
    "defeat",
    "flap",
    "hold_prop",
)

AVAILABLE_PROPS = (
    "phone",
    "laptop",
    "scroll",
    "box",
    "coffee_mug",
    "clock",
    "briefcase",
    "papers",
    "party_hat",
    "cape",
    "flame",
    "ice_block",
    "medal",
    "trophy",
    "megaphone",
)


def _select_costar_archetype(theme: str) -> Dict[str, Any]:
    """Choose a fitting original stylized co-star based on the user's theme."""
    t = theme.lower()
    if any(k in t for k in ("pombo", "passaro", "pássaro", "ave", "voar", "pigeon", "cidade", "praca", "praça")):
        return {
            "id": "costar",
            "speaker_code": "C",
            "name": "Pipo",
            "role": "co-protagonista",
            "rig": "pigeon",
            "description": "Um pombo urbano extremamente sarcástico e confiante.",
            "voice_role": "costar",
        }
    if any(k in t for k in ("tempo", "relogio", "relógio", "fantasma", "noite", "sombra", "aluguel", "quarto", "morte")):
        return {
            "id": "costar",
            "speaker_code": "C",
            "name": "Crono",
            "role": "co-protagonista",
            "rig": "phantom",
            "robeColor": "#1E2235",
            "glowColor": "#5BF0FF",
            "description": "Um guardião encapuzado do tempo com olhos luminosos e humor seco.",
            "voice_role": "costar",
        }
    if any(k in t for k in ("pedra", "rocha", "pet", "poder", "magia", "escola", "academia")):
        return {
            "id": "costar",
            "speaker_code": "C",
            "name": "Pedrinho",
            "role": "co-protagonista",
            "rig": "rock",
            "color": "#8E94A0",
            "description": "Uma pedra aparentemente comum com olhar inexpressivo e poderes inesperados.",
            "voice_role": "costar",
        }
    # Default versatile original co-star: comic helper robot
    return {
        "id": "costar",
        "speaker_code": "C",
        "name": "Bip",
        "role": "co-protagonista",
        "rig": "bot",
        "bodyColor": "#E5EEF8",
        "accentColor": "#35D4FF",
        "description": "Um robô assistente super literal e cheio de confiança duvidosa.",
        "voice_role": "costar",
    }


def _build_default_characters(
    theme: str,
    num_characters: int = 2,
    costar_rig: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rig_choice = (costar_rig or "auto").strip().lower()
    if rig_choice == "pigeon":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Pipo",
            "role": "co-protagonista",
            "rig": "pigeon",
            "description": "Um pombo urbano extremamente sarcástico e confiante.",
            "voice_role": "costar",
        }
    elif rig_choice == "phantom":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Crono",
            "role": "co-protagonista",
            "rig": "phantom",
            "robeColor": "#1E2235",
            "glowColor": "#5BF0FF",
            "description": "Um guardião encapuzado do tempo com olhos luminosos e humor seco.",
            "voice_role": "costar",
        }
    elif rig_choice == "rock":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Pedrinho",
            "role": "co-protagonista",
            "rig": "rock",
            "color": "#8E94A0",
            "description": "Uma pedra aparentemente comum com olhar inexpressivo.",
            "voice_role": "costar",
        }
    elif rig_choice == "bot":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Bip",
            "role": "co-protagonista",
            "rig": "bot",
            "bodyColor": "#E5EEF8",
            "accentColor": "#35D4FF",
            "description": "Um robô assistente super literal e cheio de confiança duvidosa.",
            "voice_role": "costar",
        }
    elif rig_choice == "human":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Rafa",
            "role": "co-protagonista",
            "rig": "human",
            "skin": "#F2BD94",
            "shirt": "#2AC98B",
            "pants": "#283045",
            "shoe": "#FFFFFF",
            "hairColor": "#3A261B",
            "hairStyle": "slick",
            "voice_role": "costar",
        }
    elif rig_choice == "mech":
        costar = {
            "id": "costar",
            "speaker_code": "C",
            "name": "Titã",
            "role": "co-protagonista",
            "rig": "mech",
            "color": "#5A6782",
            "trim": "#E64B55",
            "voice_role": "costar",
        }
    else:
        costar = _select_costar_archetype(theme)

    chars: List[Dict[str, Any]] = [
        {
            "id": "narrator",
            "speaker_code": "N",
            "name": "Leo",
            "role": "protagonista",
            "rig": "human",
            "skin": "#FFCCA4",
            "shirt": "#3B7BFF",
            "pants": "#2A314A",
            "shoe": "#EEF2FA",
            "hairColor": "#231D28",
            "hairStyle": "messy",
            "voice_role": "narrator",
        },
        costar,
    ]
    if num_characters >= 3:
        chars.append(
            {
                "id": "secondary",
                "speaker_code": "S",
                "name": "Maya",
                "role": "secundario",
                "rig": "human",
                "skin": "#F0B98C",
                "shirt": "#FF5C8A",
                "pants": "#292E42",
                "shoe": "#FFFFFF",
                "hairColor": "#3B232B",
                "hairStyle": "bun",
                "glasses": True,
                "voice_role": "secondary",
            }
        )
    return chars


def _extract_json_block(text: str) -> Dict[str, Any]:
    """Robustly parse a JSON object from raw LLM output (with or without markdown fences)."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            cleaned = cleaned[first : last + 1]
    return json.loads(cleaned)


def _build_llm_prompt(theme: str, cfg: AutoShortsConfig, duration_sec: float, num_chars: int) -> str:
    target_words = max(32, int(round((duration_sec / 60.0) * cfg.get("story.target_words_per_minute", 150))))
    min_lines = max(6, int(round(duration_sec / 3.8)))
    max_lines = max(min_lines + 4, int(round(duration_sec / 2.2)))
    lang = cfg.get("story.language", "pt-BR")
    style = cfg.get("story.style", "comedia-absurda")

    return f"""Você é roteirista sênior de curtas animados 3D verticais (estilo comédia viral de 60 segundos).
Crie um roteiro 100% ORIGINAL em {lang} sobre o tema: "{theme}".
NÃO use nenhum personagem protegido por direitos autorais. Crie personagens originais.

ESTRUTURA OBRIGATÓRIA:
- Duração alvo: {duration_sec:.0f} segundos (~{target_words} palavras no total, dividido em {min_lines} a {max_lines} falas curtas e ágeis).
- Primeiros 3 segundos (fala 1): gancho chocante em primeira pessoa que prende atenção imediata.
- Desenvolvimento (regra de três): 3 acontecimentos escalando o absurdo com diálogos naturais entre narrador (N) e co-protagonista (C){" e personagem secundário (S)" if num_chars >= 3 else ""}.
- Virada dramática / caos no meio para o fim.
- Conclusão irônica e inesperada na última fala.
- Estilo: {style}.

RETORNE APENAS UM JSON VÁLIDO no formato exato:
{{
  "title": "Título curto e chamativo",
  "premise": "Resumo em 1 frase da premissa",
  "characters": [
    {{
      "id": "narrator",
      "speaker_code": "N",
      "name": "Leo",
      "rig": "human",
      "shirt": "#3B7BFF",
      "hairStyle": "messy"
    }},
    {{
      "id": "costar",
      "speaker_code": "C",
      "name": "Nome original",
      "rig": "bot|pigeon|phantom|rock|human"
    }}
  ],
  "lines": [
    {{
      "speaker": "N",
      "text": "Fala curta e natural em português brasileiro.",
      "beat_type": "hook|setup|mishap|escalation|turning_point|climax|twist",
      "set": "living_room|living_room_night|kitchen|entry_hall|town_square|town_square_golden|town_square_attack|studio",
      "emotion": "neutral|happy|excited|shock|panic|angry|deadpan|sad|smug|confused",
      "action": "idle|walk|run|talk|explain|shock|panic|celebrate|jump|point|sit|defeat|hold_prop",
      "prop": null,
      "sfx": "whoosh|pop|bass_hit|ding|boing|thunder|knock|slap|riser|sting|trombone|footsteps|null",
      "impact_text": null
    }}
  ]
}}"""


def _generate_via_opencode(prompt: str, model: str, cli_cmd: str = "opencode", timeout_sec: int = 120) -> Dict[str, Any]:
    """Generate story JSON using the locally installed OpenCode CLI (uses account login, no API key needed)."""
    exe = shutil.which(cli_cmd)
    if not exe:
        raise FileNotFoundError(f"OpenCode CLI ('{cli_cmd}') não encontrado no PATH.")
    if not model:
        raise ValueError("Nenhum modelo OpenCode especificado (selecione um modelo listado em `opencode models`).")

    single_line_prompt = " ".join(line.strip() for line in prompt.splitlines() if line.strip())
    cmd = [exe, "run", "--standalone", "--model", model, "--archived", "--format", "default", single_line_prompt]

    popen_kwargs: Dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
        raise TimeoutError(f"OpenCode excedeu o limite de {timeout_sec}s ao gerar o roteiro.")

    if proc.returncode != 0 or not (stdout or "").strip():
        raise RuntimeError(f"OpenCode falhou (exit={proc.returncode}): {(stderr or '')[-500:]}")
    return _extract_json_block(stdout)


def _generate_via_gemini(prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "responseMimeType": "application/json",
        },
    }
    resp = requests.post(url, params={"key": api_key}, json=payload, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json_block(text)


def _generate_via_openai(prompt: str, model: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    endpoint = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.85,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Você retorna apenas JSON válido em português brasileiro."},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return _extract_json_block(text)


def _generate_offline_story(theme: str, duration_sec: float, num_characters: int = 2) -> Dict[str, Any]:
    """Deterministic high-energy PT-BR comedy generator tailored to the theme & duration.

    Used automatically when no external LLM API key is configured or in offline test runs.
    """
    clean_theme = theme.strip().rstrip(".!?") or "um assistente atrapalhado"
    chars = _build_default_characters(clean_theme, num_characters=num_characters)
    hero_name = chars[0]["name"]
    costar_name = chars[1]["name"]
    has_third = len(chars) >= 3
    third_name = chars[2]["name"] if has_third else None

    full_beats: List[Dict[str, Any]] = [
        {
            "speaker": "N",
            "text": f"Eu só queria um dia normal, até {clean_theme} aparecer na minha sala.",
            "beat_type": "hook",
            "set": "living_room",
            "emotion": "shock",
            "action": "shock",
            "prop": "coffee_mug",
            "sfx": "bass_hit",
            "impact_text": "COMO ASSIM?!",
        },
        {
            "speaker": "C",
            "text": f"Calma, {hero_name}. Eu tenho um plano totalmente científico e sem chance de dar errado.",
            "beat_type": "setup",
            "set": "living_room",
            "emotion": "smug",
            "action": "explain",
            "prop": "scroll",
            "sfx": "pop",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": "A primeira regra quando alguém fala isso é correr, mas eu resolvi confiar.",
            "beat_type": "setup",
            "set": "living_room",
            "emotion": "deadpan",
            "action": "talk",
            "prop": None,
            "sfx": "whoosh",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": f"No primeiro minuto, {costar_name} tentou resolver tudo na cozinha e transformou meu café em espuma brilhante.",
            "beat_type": "mishap",
            "set": "kitchen",
            "emotion": "panic",
            "action": "panic",
            "prop": "coffee_mug",
            "sfx": "boing",
            "impact_text": "OPS!",
        },
        {
            "speaker": "C",
            "text": "Tecnicamente, espuma brilhante tem o dobro de energia. Você deveria agradecer.",
            "beat_type": "mishap",
            "set": "kitchen",
            "emotion": "happy",
            "action": "point",
            "prop": None,
            "sfx": "ding",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": "Na segunda tentativa, a porta abriu sozinha e a caixa misteriosa começou a tremer no corredor.",
            "beat_type": "mishap",
            "set": "entry_hall",
            "emotion": "shock",
            "action": "shock",
            "prop": "box",
            "sfx": "knock",
            "impact_text": "TOC TOC!",
        },
        {
            "speaker": "S" if has_third else "C",
            "text": (
                f"Espera, {hero_name}, por que a praça inteira está olhando para a sua janela agora?"
                if has_third
                else "Relaxa, isso é só o modo turbo ativando antes da hora prevista."
            ),
            "beat_type": "escalation",
            "set": "entry_hall",
            "emotion": "confused" if has_third else "excited",
            "action": "point",
            "prop": "phone",
            "sfx": "whoosh",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": f"Quando fomos para a praça central, o assunto sobre {clean_theme} já tinha virado o maior caos da cidade.",
            "beat_type": "escalation",
            "set": "town_square",
            "emotion": "panic",
            "action": "run",
            "prop": None,
            "sfx": "footsteps",
            "impact_text": "CAOS TOTAL!",
        },
        {
            "speaker": "C",
            "text": "Olha pelo lado positivo: todo mundo finalmente prestou atenção na gente!",
            "beat_type": "escalation",
            "set": "town_square",
            "emotion": "excited",
            "action": "celebrate",
            "prop": "megaphone",
            "sfx": "pop",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": "Então o céu escureceu, o alarme disparou e eu percebi que não tinha botão de cancelar.",
            "beat_type": "turning_point",
            "set": "town_square_attack",
            "emotion": "panic",
            "action": "panic",
            "prop": "clock",
            "sfx": "thunder",
            "impact_text": "ALERTA!",
        },
        {
            "speaker": "C",
            "text": "Espera! Se a gente apertar o botão errado ao contrário, talvez tudo volte ao normal!",
            "beat_type": "turning_point",
            "set": "town_square_attack",
            "emotion": "shock",
            "action": "jump",
            "prop": "laptop",
            "sfx": "riser",
            "impact_text": None,
        },
        {
            "speaker": "N",
            "text": "Eu fechei os olhos, respirei fundo e apertei o único botão vermelho que sobrou.",
            "beat_type": "climax",
            "set": "studio",
            "emotion": "shock",
            "action": "hold_prop",
            "prop": "flame",
            "sfx": "bass_hit",
            "impact_text": "CLIQUE!",
        },
        {
            "speaker": "N",
            "text": "Em vez de explodir, a praça inteira aplaudiu e me entregou um troféu de maior invenção do ano.",
            "beat_type": "climax",
            "set": "town_square_golden",
            "emotion": "happy",
            "action": "celebrate",
            "prop": "trophy",
            "sfx": "bell",
            "impact_text": "VITÓRIA!",
        },
        {
            "speaker": "C",
            "text": f"Eu disse que era científico, {hero_name}! Agora só falta testar a versão dois amanhã.",
            "beat_type": "twist",
            "set": "town_square_golden",
            "emotion": "smug",
            "action": "talk",
            "prop": "papers",
            "sfx": "sting",
            "impact_text": "VERSÃO 2?!",
        },
        {
            "speaker": "N",
            "text": "Alguém sabe como mudar de planeta antes de segunda-feira?",
            "beat_type": "twist",
            "set": "living_room_night",
            "emotion": "deadpan",
            "action": "defeat",
            "prop": None,
            "sfx": "trombone",
            "impact_text": None,
        },
    ]

    # Adapt number of beats cleanly to target_duration_sec (works for 12s quick tests up to 90s shorts!)
    if duration_sec <= 16:
        # Compact 5-beat arc: hook -> mishap -> turning point -> climax -> twist
        chosen = [full_beats[0], full_beats[1], full_beats[7], full_beats[12], full_beats[14]]
    elif duration_sec <= 30:
        chosen = [
            full_beats[0],
            full_beats[1],
            full_beats[3],
            full_beats[7],
            full_beats[9],
            full_beats[11],
            full_beats[12],
            full_beats[13],
            full_beats[14],
        ]
    else:
        chosen = full_beats

    return {
        "title": f"O Dia em que {clean_theme.capitalize()} Saiu do Controle",
        "premise": f"{hero_name} precisa sobreviver ao caos causado por {clean_theme} com a ajuda duvidosa de {costar_name}.",
        "theme": clean_theme,
        "characters": chars,
        "lines": chosen,
        "third_character": third_name,
    }


def _normalize_story(raw: Dict[str, Any], theme: str, duration_sec: float, num_chars: int, provider_used: str) -> Dict[str, Any]:
    """Validate and sanitize every field of a generated story so downstream modules never crash."""
    chars = raw.get("characters") or _build_default_characters(theme, num_chars)
    sanitized_chars: List[Dict[str, Any]] = []
    seen_codes = set()
    defaults = _build_default_characters(theme, max(num_chars, len(chars)))

    for idx, ch in enumerate(chars):
        base = defaults[min(idx, len(defaults) - 1)]
        code = str(ch.get("speaker_code") or base["speaker_code"]).upper()[:1]
        if code in seen_codes:
            code = "S" if "S" not in seen_codes else "C"
        seen_codes.add(code)
        rig = str(ch.get("rig") or base["rig"]).lower()
        if rig not in AVAILABLE_RIGS:
            rig = "human" if idx == 0 else "bot"
        merged = {**base, **ch, "speaker_code": code, "rig": rig}
        sanitized_chars.append(merged)

    code_to_id = {c["speaker_code"]: c["id"] for c in sanitized_chars}
    valid_lines: List[Dict[str, Any]] = []
    for idx, ln in enumerate(raw.get("lines") or []):
        text = str(ln.get("text") or "").strip()
        if not text:
            continue
        spk = str(ln.get("speaker") or "N").upper()[:1]
        if spk not in code_to_id:
            spk = sanitized_chars[0]["speaker_code"]
        set_name = str(ln.get("set") or "town_square")
        if set_name not in AVAILABLE_SETS:
            set_name = "town_square"
        emotion = str(ln.get("emotion") or "neutral")
        if emotion not in AVAILABLE_EMOTIONS:
            emotion = "neutral"
        action = str(ln.get("action") or "talk")
        if action not in AVAILABLE_ACTIONS:
            action = "talk"
        prop = ln.get("prop")
        if prop not in AVAILABLE_PROPS:
            prop = None
        sfx = ln.get("sfx")
        if sfx in (None, "", "null", "none"):
            sfx = None
        impact_text = ln.get("impact_text")
        if impact_text in (None, "", "null"):
            impact_text = None

        valid_lines.append(
            {
                "index": idx,
                "speaker": spk,
                "character_id": code_to_id[spk],
                "text": text,
                "beat_type": str(ln.get("beat_type") or "setup"),
                "set": set_name,
                "emotion": emotion,
                "action": action,
                "prop": prop,
                "sfx": sfx,
                "impact_text": impact_text,
            }
        )

    if not valid_lines:
        raise ValueError("Roteiro gerado não contém falas válidas.")

    script_pairs = [[ln["speaker"], ln["text"]] for ln in valid_lines]
    total_words = sum(len(ln["text"].split()) for ln in valid_lines)

    return {
        "title": str(raw.get("title") or f"AutoShorts: {theme}"),
        "theme": theme,
        "premise": str(raw.get("premise") or theme),
        "language": "pt-BR",
        "provider_used": provider_used,
        "target_duration_sec": duration_sec,
        "word_count": total_words,
        "characters": sanitized_chars,
        "lines": valid_lines,
        "script_pairs": script_pairs,
    }


def _infer_staging_from_ptbr_line(text: str, idx: int, total: int, prev_set: str) -> Dict[str, Any]:
    """Infer fitting 3D set, emotion, action, prop, and SFX from a Portuguese script line."""
    low = text.lower()

    # Optional explicit set tag at start like [cozinha] or [praca] handled before this helper
    set_name = prev_set
    if any(k in low for k in ("cozinha", "café", "cafe", "fogão", "fogao", "geladeira", "panela", "brigadeiro", "feijoada", "bolo", "comida")):
        set_name = "kitchen"
    elif any(k in low for k in ("porta", "corredor", "campainha", "toc toc", "bateu", "chegou", "caixa", "entrega")):
        set_name = "entry_hall"
    elif any(k in low for k in ("vitória", "vitoria", "troféu", "trofeu", "aplaud", "prêmio", "premio", "medalha", "venci", "ganhou")):
        set_name = "town_square_golden"
    elif any(k in low for k in ("alerta", "explod", "escureceu", "alarme", "perigo", "ataque", "monstro", "destru")):
        set_name = "town_square_attack"
    elif any(k in low for k in ("praça", "praca", "rua", "cidade", "academia", "parque", "multidão", "multidao", "todo mundo")):
        set_name = "town_square"
    elif any(k in low for k in ("noite", "dormir", "madrugada", "segunda-feira", "planeta")):
        set_name = "living_room_night"
    elif any(k in low for k in ("sala", "sofá", "sofa", "casa", "janela", "quarto")):
        set_name = "living_room"
    elif idx == 0:
        set_name = "living_room"

    # Beat type along narrative arc
    if idx == 0:
        beat_type = "hook"
    elif idx == total - 1:
        beat_type = "twist"
    elif idx >= max(1, int(total * 0.75)):
        beat_type = "climax"
    elif idx >= max(1, int(total * 0.5)):
        beat_type = "turning_point"
    else:
        beat_type = "mishap" if idx % 2 == 1 else "escalation"

    # Emotion, action, SFX
    emotion = "neutral"
    action = "talk"
    sfx: Optional[str] = "whoosh" if idx > 0 and set_name != prev_set else None
    impact_text: Optional[str] = None

    if any(k in low for k in ("como assim", "socorro", "explod", "caos", "fogo", "alerta", "meu deus", "impossível", "impossivel")) or "?!" in text:
        emotion = "shock" if idx == 0 else "panic"
        action = "shock" if idx == 0 else "panic"
        sfx = "bass_hit" if idx == 0 else "thunder"
        impact_text = "COMO ASSIM?!" if idx == 0 else "CAOS!"
    elif any(k in low for k in ("corri", "correr", "corre", "fugir", "fugi", "dispar")):
        emotion = "panic"
        action = "run"
        sfx = "footsteps"
    elif any(k in low for k in ("vitória", "vitoria", "aplaud", "troféu", "trofeu", "feliz", "consegui", "incrível", "incrivel", "genial")):
        emotion = "happy"
        action = "celebrate"
        sfx = "bell"
        impact_text = "VITÓRIA!" if beat_type == "climax" else None
    elif any(k in low for k in ("calma", "plano", "científic", "cientific", "técnic", "tecnic", "relaxa", "fácil", "facil")):
        emotion = "smug"
        action = "explain"
        sfx = "pop"
    elif any(k in low for k in ("raiva", "odeio", "pare", "chega", "culpa", "idiota")):
        emotion = "angry"
        action = "point"
        sfx = "slap"
    elif any(k in low for k in ("triste", "desist", "perdi", "nunca mais", "socorro", "mudar de planeta", "adeus")) or idx == total - 1:
        emotion = "deadpan" if idx == total - 1 else "sad"
        action = "defeat"
        sfx = "trombone" if idx == total - 1 else "sting"
    elif "?" in text:
        emotion = "confused"
        action = "talk"
        sfx = sfx or "ding"
    elif "!" in text:
        emotion = "excited"
        action = "point"
        sfx = sfx or "pop"

    # Prop inference
    prop: Optional[str] = None
    if any(k in low for k in ("café", "cafe", "xícara", "xicara")):
        prop = "coffee_mug"
    elif any(k in low for k in ("celular", "telefone", "mensagem", "whatsapp")):
        prop = "phone"
    elif any(k in low for k in ("notebook", "computador", "laptop", "código", "codigo")):
        prop = "laptop"
    elif any(k in low for k in ("troféu", "trofeu", "prêmio", "premio")):
        prop = "trophy"
    elif any(k in low for k in ("medalha",)):
        prop = "medal"
    elif any(k in low for k in ("relógio", "relogio", "tempo", "hora", "alarme")):
        prop = "clock"
    elif any(k in low for k in ("caixa", "pacote", "entrega")):
        prop = "box"
    elif any(k in low for k in ("plano", "lista", "pergaminho", "contrato", "regra")):
        prop = "scroll"
    elif any(k in low for k in ("fogo", "chama", "queim", "explod")):
        prop = "flame"
    elif any(k in low for k in ("gelo", "congel")):
        prop = "ice_block"
    elif any(k in low for k in ("megafone", "grit", "anunci")):
        prop = "megaphone"

    return {
        "beat_type": beat_type,
        "set": set_name,
        "emotion": emotion,
        "action": action,
        "prop": prop,
        "sfx": sfx,
        "impact_text": impact_text,
    }


def parse_custom_script(
    custom_script: str,
    theme: str = "",
    config: Optional[AutoShortsConfig] = None,
    title: Optional[str] = None,
    costar_rig: Optional[str] = None,
    duration_sec: float = 60.0,
) -> Dict[str, Any]:
    """Parse a user-written PT-BR script verbatim into a full AutoShorts story payload.

    Supported formats:
      1. Prefixed lines:
         N: Fala do narrador...
         C: Fala do co-protagonista...
         S: Fala do terceiro personagem (opcional)...
         (Also accepts Narrador:, Leo:, Robo:, Bip:, Pombo:, Personagem:, [cenario] tags.)
      2. Plain text without prefixes (splits sentences; quoted "..." text becomes speaker C).
    """
    cfg = config or AutoShortsConfig.load()
    raw_text = custom_script.strip()
    if not raw_text:
        raise ValueError("O roteiro personalizado está vazio.")

    set_aliases = {
        "sala": "living_room",
        "sala_noite": "living_room_night",
        "cozinha": "kitchen",
        "cozinha_noite": "kitchen_night",
        "corredor": "entry_hall",
        "porta": "entry_hall",
        "praca": "town_square",
        "praça": "town_square",
        "praca_dourada": "town_square_golden",
        "praça_dourada": "town_square_golden",
        "praca_caos": "town_square_attack",
        "praça_caos": "town_square_attack",
        "estudio": "studio",
        "estúdio": "studio",
    }

    speaker_prefix_re = re.compile(
        r"^(?:\[(?P<tag>[^\]]+)\]\s*)?(?P<spk>[A-Za-zÀ-ÿ0-9_ -]{1,20})\s*:\s*(?P<line>.+)$"
    )

    parsed_entries: List[Dict[str, Any]] = []
    non_empty_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip() and not ln.strip().startswith("#")]

    def _map_speaker(label: str) -> str:
        low = label.strip().lower()
        if low in ("n", "narrador", "leo", "eu", "protagonista", "p1", "1"):
            return "N"
        if low in ("s", "secundario", "secundário", "maya", "p3", "3"):
            return "S"
        return "C"

    has_any_prefix = any(speaker_prefix_re.match(ln) for ln in non_empty_lines)

    if has_any_prefix:
        for ln in non_empty_lines:
            m = speaker_prefix_re.match(ln)
            if m:
                spk = _map_speaker(m.group("spk"))
                line_text = m.group("line").strip()
                tag = (m.group("tag") or "").strip().lower()
                explicit_set = set_aliases.get(tag) or (tag if tag in AVAILABLE_SETS else None)
            else:
                spk = "N"
                line_text = ln
                explicit_set = None
            if line_text:
                parsed_entries.append({"speaker": spk, "text": line_text, "explicit_set": explicit_set})
    else:
        # Plain text mode: split by lines or sentences; quoted text becomes C, narration becomes N
        for ln in non_empty_lines:
            parts = re.split(r'(?<=[.!?])\s+', ln)
            for p in parts:
                seg = p.strip()
                if not seg:
                    continue
                is_quote = (seg.startswith('"') and seg.endswith('"')) or (seg.startswith("“") and seg.endswith("”"))
                clean = seg.strip('"“”').strip()
                if clean:
                    parsed_entries.append({"speaker": "C" if is_quote else "N", "text": clean, "explicit_set": None})

    if not parsed_entries:
        raise ValueError("Nenhuma fala válida encontrada no roteiro personalizado.")

    has_third = any(e["speaker"] == "S" for e in parsed_entries)
    num_chars = 3 if has_third else max(2, int(cfg.get("story.num_characters", 2)))
    inferred_theme = theme.strip() or parsed_entries[0]["text"][:60]
    chars = _build_default_characters(inferred_theme, num_characters=num_chars, costar_rig=costar_rig)

    lines_out: List[Dict[str, Any]] = []
    prev_set = "living_room"
    total = len(parsed_entries)
    for idx, entry in enumerate(parsed_entries):
        staging = _infer_staging_from_ptbr_line(entry["text"], idx, total, prev_set)
        chosen_set = entry["explicit_set"] or staging["set"]
        prev_set = chosen_set
        lines_out.append(
            {
                "speaker": entry["speaker"],
                "text": entry["text"],
                "beat_type": staging["beat_type"],
                "set": chosen_set,
                "emotion": staging["emotion"],
                "action": staging["action"],
                "prop": staging["prop"],
                "sfx": staging["sfx"],
                "impact_text": staging["impact_text"],
            }
        )

    raw_story = {
        "title": title or (f"AutoShorts: {inferred_theme}" if theme.strip() else "Roteiro Personalizado"),
        "premise": inferred_theme,
        "characters": chars,
        "lines": lines_out,
    }
    return _normalize_story(raw_story, inferred_theme, duration_sec, num_chars, provider_used="custom_script_user")


def generate_story(
    theme: str,
    config: Optional[AutoShortsConfig] = None,
    duration_sec: Optional[float] = None,
    provider: Optional[str] = None,
    output_path: Optional[Path] = None,
    custom_script: Optional[str] = None,
    costar_rig: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a full structured story script from a theme OR parse a user-supplied custom script."""
    cfg = config or AutoShortsConfig.load()
    target_dur = float(duration_sec or cfg.get("video.target_duration_sec", 60))
    num_chars = int(cfg.get("story.num_characters", 2))
    selected_provider = (provider or cfg.get("story.provider", "auto")).lower()
    model = str(cfg.get("story.model", "gemini-2.5-flash"))

    if custom_script and custom_script.strip():
        logger.info("Usando ROTEIRO PERSONALIZADO do usuário (texto preservado integralmente).")
        story = parse_custom_script(
            custom_script=custom_script,
            theme=theme,
            config=cfg,
            costar_rig=costar_rig,
            duration_sec=target_dur,
        )
        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
        return story

    prompt = _build_llm_prompt(theme, cfg, target_dur, num_chars)
    raw_story: Optional[Dict[str, Any]] = None
    used_provider = "local_template"

    gemini_key = get_secret("GEMINI_API_KEY") or get_secret("GOOGLE_API_KEY")
    openai_key = get_secret("OPENAI_API_KEY")
    openai_base = get_secret("OPENAI_BASE_URL")
    opencode_model = str(cfg.get("opencode.model") or get_secret("OPENCODE_MODEL") or "").strip()
    opencode_cli = str(cfg.get("opencode.cli_command", "opencode"))

    # Prefer local OpenCode CLI (account login, zero API key!) when selected or configured
    if selected_provider in ("opencode", "auto") and opencode_model and shutil.which(opencode_cli):
        try:
            logger.info("Gerando roteiro via OpenCode CLI local (%s)...", opencode_model)
            raw_story = _generate_via_opencode(prompt, opencode_model, cli_cmd=opencode_cli)
            used_provider = f"opencode:{opencode_model}"
        except Exception as exc:
            logger.warning("OpenCode CLI falhou ao gerar roteiro (%s). Usando alternativa.", exc)
            if selected_provider == "opencode":
                logger.warning("Fallback para gerador local PT-BR após falha do OpenCode.")

    if raw_story is None and selected_provider in ("auto", "gemini") and gemini_key:
        try:
            logger.info("Gerando roteiro via Gemini API (%s)...", model)
            raw_story = _generate_via_gemini(prompt, model, gemini_key)
            used_provider = f"gemini:{model}"
        except Exception as exc:
            logger.warning("Gemini falhou (%s). Tentando alternativa.", exc)
            if selected_provider == "gemini":
                raise

    if raw_story is None and selected_provider in ("auto", "openai") and openai_key:
        try:
            oa_model = model if not model.startswith("gemini") else "gpt-4o-mini"
            logger.info("Gerando roteiro via OpenAI-compatible API (%s)...", oa_model)
            raw_story = _generate_via_openai(prompt, oa_model, openai_key, openai_base)
            used_provider = f"openai:{oa_model}"
        except Exception as exc:
            logger.warning("OpenAI API falhou (%s). Usando gerador estruturado local.", exc)
            if selected_provider == "openai":
                raise

    if raw_story is None:
        logger.info(
            "Usando gerador de histórias estruturado local em pt-BR "
            "(defina GEMINI_API_KEY ou OPENAI_API_KEY para geração via LLM remoto)."
        )
        raw_story = _generate_offline_story(theme, target_dur, num_chars)
        used_provider = "local_template_ptbr"

    story = _normalize_story(raw_story, theme, target_dur, num_chars, used_provider)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")

    return story
