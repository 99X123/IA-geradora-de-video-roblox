"""Tests for TTS engine, forced alignment, lip-sync envelope, subtitles, and SFX/music synthesis."""

from __future__ import annotations

import wave
from pathlib import Path

from src.audio_processor import align_audio_and_script
from src.config import AutoShortsConfig
from src.sfx_synthesizer import (
    SFX_GENERATORS,
    mix_final_audio,
    synthesize_background_music,
    synthesize_sfx_track,
)
from src.story_generator import generate_story
from src.storyboard_generator import build_storyboard
from src.subtitle_generator import format_srt_timestamp, generate_subtitles
from src.tts_engine import synthesize_story_audio


def test_tts_alignment_subtitles_and_mix_pipeline(tmp_path: Path):
    cfg = AutoShortsConfig.load()
    story = generate_story(
        theme="um despertador que dá conselhos filosóficos",
        config=cfg,
        duration_sec=14,
        provider="local_template",
    )

    tts_meta = synthesize_story_audio(story, out_dir=tmp_path / "audio", config=cfg, provider_override="local_synth_test")
    vo_path = Path(tts_meta["vo_wav"])
    assert vo_path.exists()
    assert tts_meta["duration_sec"] > 2.0
    assert len(tts_meta["segments"]) == len(story["lines"])

    sync_data = align_audio_and_script(tts_meta, config=cfg, out_dir=tmp_path / "subtitles")
    assert len(sync_data["words"]) >= 20
    assert len(sync_data["lines"]) == len(story["lines"])
    assert len(sync_data["env"]) >= int(sync_data["duration_sec"] * 30) - 2
    assert max(sync_data["env"]) > 0.25  # real acoustic modulation for lip-sync

    sub_info = generate_subtitles(sync_data, out_dir=tmp_path / "subtitles", config=cfg)
    srt_path = Path(sub_info["srt_path"])
    assert srt_path.exists()
    assert "-->" in srt_path.read_text(encoding="utf-8")
    assert sub_info["chunk_count"] >= len(story["lines"])
    for ch in sub_info["chunks"]:
        assert 1 <= len(ch["words"]) <= 3
        assert ch["end"] >= ch["start"]

    # Test acoustic fallback explicitly when word_boundaries are stripped
    stripped_meta = {
        **tts_meta,
        "segments": [{**seg, "word_boundaries": []} for seg in tts_meta["segments"]],
    }
    fallback_cfg = AutoShortsConfig.load(overrides={"alignment": {"primary_engine": "acoustic_only"}})
    fb_sync = align_audio_and_script(stripped_meta, config=fallback_cfg)
    assert fb_sync["fallback_used"] is True
    assert fb_sync["alignment_method"] == "acoustic_energy_fallback"
    assert len(fb_sync["warnings"]) >= 1
    assert len(fb_sync["words"]) >= 20

    # Test SFX, music, and final FFmpeg mix
    sb = build_storyboard(story, sync_data["lines"], sync_data["duration_sec"], config=cfg)
    sfx_wav = synthesize_sfx_track(sb, tmp_path / "audio" / "sfx.wav")
    music_wav = synthesize_background_music(sync_data["duration_sec"], tmp_path / "audio" / "music.wav")
    mix_wav = mix_final_audio(
        vo_wav=vo_path,
        duration_sec=sync_data["duration_sec"],
        out_mix_wav=tmp_path / "audio" / "mix.wav",
        sfx_wav=sfx_wav,
        music_wav=music_wav,
        config=cfg,
    )
    assert mix_wav.exists()
    with wave.open(str(mix_wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 44100
        mix_dur = wf.getnframes() / float(wf.getframerate())
        assert abs(mix_dur - sync_data["duration_sec"]) < 0.35


def test_all_sfx_generators_produce_valid_audio():
    assert len(SFX_GENERATORS) >= 18
    for name, fn in SFX_GENERATORS.items():
        samples = fn()
        assert len(samples) > 500, f"SFX {name} muito curto"
        assert float(abs(samples).max()) > 0.01, f"SFX {name} silencioso"


def test_srt_timestamp_formatting():
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(65.432) == "00:01:05,432"
    assert format_srt_timestamp(3661.005) == "01:01:01,005"
