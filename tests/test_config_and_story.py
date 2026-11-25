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
