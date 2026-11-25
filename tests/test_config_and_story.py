"""Unit tests for central configuration, secret redaction, and story generation."""

from __future__ import annotations

import os
from pathlib import Path

from src.config import AutoShortsConfig, redact_secrets
from src.story_generator import AVAILABLE_RIGS, AVAILABLE_SETS, generate_story


def test_config_loads_and_applies_presets():
    cfg = AutoShortsConfig.load()
    assert cfg.get("video.width") == 1080
    assert cfg.get("video.height") == 1920
    assert cfg.get("video.fps") == 30
    assert cfg.get("video.pixel_format") == "yuv420p"

    draft_cfg = AutoShortsConfig.load(overrides={"video": {"quality_preset": "draft"}})
    assert draft_cfg.get("video.width") == 540
    assert draft_cfg.get("video.height") == 960


def test_secret_redaction(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSySuperSecretKey123456789")
    scrubbed = redact_secrets("Error using key AIzaSySuperSecretKey123456789 in request")
    assert "AIzaSySuperSecretKey123456789" not in scrubbed
    assert "<REDACTED:GEMINI_API_KEY>" in scrubbed


def test_story_generator_offline_structure(tmp_path: Path):
    out_file = tmp_path / "story.json"
    story = generate_story(
        theme="meu robô decidiu cozinhar feijoada",
        duration_sec=60,
        provider="local_template",
        output_path=out_file,
    )
    assert out_file.exists()
    assert story["language"] == "pt-BR"
    assert len(story["characters"]) >= 2
    assert len(story["lines"]) >= 10
    assert story["lines"][0]["beat_type"] == "hook"
    assert story["lines"][-1]["beat_type"] == "twist"
    assert len(story["script_pairs"]) == len(story["lines"])

    for ch in story["characters"]:
        assert ch["rig"] in AVAILABLE_RIGS
    for ln in story["lines"]:
        assert ln["set"] in AVAILABLE_SETS
        assert ln["speaker"] in ("N", "C", "S")
        assert ln["text"].strip()


def test_story_generator_compact_short_and_3_characters():
    cfg = AutoShortsConfig.load(overrides={"story": {"num_characters": 3}})
    story = generate_story(
        theme="um pombo virou síndico do prédio",
        config=cfg,
        duration_sec=14,
        provider="local_template",
    )
    assert len(story["characters"]) == 3
    assert any(c["rig"] == "pigeon" for c in story["characters"])
    assert 4 <= len(story["lines"]) <= 8


def test_custom_user_script_preserves_exact_dialogue_and_tags():
    roteiro = """
    # Meu roteiro exato
    [sala] N: Eu só queria dormir cedo, até meu robô aparecer com uma panela gigante.
    [cozinha] C: Calma Leo! Isso aqui vai virar o melhor brigadeiro da galáxia.
    [praca] S: Ei, por que tem fumaça brilhante saindo da sua janela?
    N: Alguém sabe como mudar de planeta antes de segunda-feira?
    """
    story = generate_story(
        theme="brigadeiro galáctico",
        custom_script=roteiro,
        costar_rig="bot",
    )
    assert story["provider_used"] == "custom_script_user"
    assert len(story["lines"]) == 4
    assert len(story["characters"]) == 3
    assert story["characters"][1]["rig"] == "bot"
    assert story["lines"][0]["speaker"] == "N"
    assert story["lines"][0]["set"] == "living_room"
    assert story["lines"][0]["text"] == "Eu só queria dormir cedo, até meu robô aparecer com uma panela gigante."
    assert story["lines"][1]["speaker"] == "C"
    assert story["lines"][1]["set"] == "kitchen"
    assert story["lines"][2]["speaker"] == "S"
    assert story["lines"][2]["set"] == "town_square"
    assert story["lines"][3]["beat_type"] == "twist"


def test_custom_user_script_plain_text_with_quotes():
    plain = 'Eu abri a geladeira de madrugada. "Você não devia comer bolo às três da manhã!" Eu fechei a porta bem devagar.'
    story = generate_story(theme="bolo de madrugada", custom_script=plain, costar_rig="phantom")
    assert story["provider_used"] == "custom_script_user"
    assert len(story["lines"]) == 3
    assert story["lines"][0]["speaker"] == "N"
    assert story["lines"][1]["speaker"] == "C"
    assert story["lines"][2]["speaker"] == "N"
    assert story["characters"][1]["rig"] == "phantom"
