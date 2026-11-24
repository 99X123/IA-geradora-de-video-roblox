"""Biblioteca local de músicas instrumentais e efeitos sonoros 100% originais e livres de direitos autorais."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt

from app.config import load_settings, resolve_path

SAMPLE_RATE = 44100


def _lowpass(sig: np.ndarray, cutoff_hz: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    b, a = butter(4, min(0.95, cutoff_hz / (sr * 0.5)), btype="low")
    return filtfilt(b, a, sig).astype(np.float32)


def _normalize(sig: np.ndarray, peak: float = 0.72) -> np.ndarray:
    m = float(np.max(np.abs(sig))) if sig.size else 0.0
    return (sig * (peak / m)).astype(np.float32) if m > 1e-6 else sig.astype(np.float32)


def _synth_suspense_track(duration: float = 65.0) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False, dtype=np.float32)
    # Drone grave em Lá menor + pulso tenso + arpejo sutil
    drone = (
        0.35 * np.sin(2 * np.pi * 55.0 * t)
        + 0.25 * np.sin(2 * np.pi * 110.0 * t + 0.4 * np.sin(2 * np.pi * 0.2 * t))
        + 0.16 * np.sin(2 * np.pi * 130.81 * t)
        + 0.14 * np.sin(2 * np.pi * 164.81 * t)
    )
    pulse = 0.55 + 0.45 * np.sin(2 * np.pi * 1.45 * t)
    pad = drone * pulse

    # Notas de suspense espaçadas (A3, C4, E4, F4, E4, C4)
    notes = [220.0, 261.63, 329.63, 349.23, 329.63, 261.63, 246.94, 220.0]
    arp = np.zeros_like(t)
    step = 0.75
    for idx in range(int(duration / step)):
        f = notes[idx % len(notes)]
        s0 = int(idx * step * SAMPLE_RATE)
        n_len = min(int(step * SAMPLE_RATE), len(t) - s0)
        if n_len <= 0:
            break
        lt = np.linspace(0, n_len / SAMPLE_RATE, n_len, endpoint=False, dtype=np.float32)
        env = np.exp(-lt * 4.5) * (1.0 - np.exp(-lt * 80.0))
        arp[s0 : s0 + n_len] += 0.22 * env * (np.sin(2 * np.pi * f * lt) + 0.35 * np.sin(4 * np.pi * f * lt))

    mix = _lowpass(pad + arp, 1800.0)
    # Fade in/out suave
    fade = int(SAMPLE_RATE * 1.5)
    mix[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    mix[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return _normalize(mix, peak=0.68)


def _synth_fun_track(duration: float = 65.0) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False, dtype=np.float32)
    # Acordes alegres em Dó maior (C - G - Am - F) estilo marimba / synth gamer
    chords = [
        (130.81, [261.63, 329.63, 392.00, 523.25]),
        (196.00, [293.66, 392.00, 493.88, 587.33]),
        (220.00, [261.63, 329.63, 440.00, 523.25]),
        (174.61, [261.63, 349.23, 440.00, 523.25]),
    ]
    mix = np.zeros_like(t)
    beat = 0.25  # 120 BPM colcheias
    for step_idx in range(int(duration / beat)):
        chord_idx = (step_idx // 8) % len(chords)
        bass_f, notes = chords[chord_idx]
        s0 = int(step_idx * beat * SAMPLE_RATE)
        n_len = min(int(beat * SAMPLE_RATE * 1.4), len(t) - s0)
        if n_len <= 0:
            break
        lt = np.linspace(0, n_len / SAMPLE_RATE, n_len, endpoint=False, dtype=np.float32)
        env = np.exp(-lt * 8.5) * (1.0 - np.exp(-lt * 120.0))
        nf = notes[step_idx % len(notes)]
        pluck = 0.28 * env * (np.sin(2 * np.pi * nf * lt) + 0.3 * np.sin(4 * np.pi * nf * lt))
        mix[s0 : s0 + n_len] += pluck
        if step_idx % 2 == 0:
            b_env = np.exp(-lt * 5.0)
            mix[s0 : s0 + n_len] += 0.30 * b_env * np.sin(2 * np.pi * bass_f * lt)

    mix = _lowpass(mix, 3200.0)
    fade = int(SAMPLE_RATE * 1.2)
    mix[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    mix[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return _normalize(mix, peak=0.70)


def _synth_emotional_track(duration: float = 65.0) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False, dtype=np.float32)
    # Progressão cinematográfica calorosa (Em - C - G - D)
    prog = [
        [164.81, 246.94, 329.63, 392.00],
        [130.81, 261.63, 329.63, 392.00],
        [196.00, 246.94, 293.66, 392.00],
        [146.83, 220.00, 293.66, 369.99],
    ]
    mix = np.zeros_like(t)
    bar = 4.0
    for bar_idx in range(int(duration / bar) + 1):
        chord = prog[bar_idx % len(prog)]
        s0 = int(bar_idx * bar * SAMPLE_RATE)
        n_len = min(int(bar * SAMPLE_RATE), len(t) - s0)
        if n_len <= 0:
            break
        lt = np.linspace(0, n_len / SAMPLE_RATE, n_len, endpoint=False, dtype=np.float32)
        swell = np.sin(np.pi * lt / max(0.1, n_len / SAMPLE_RATE)) ** 0.7
        pad = sum(np.sin(2 * np.pi * f * lt) + 0.25 * np.sin(4 * np.pi * f * lt) for f in chord) / len(chord)
        mix[s0 : s0 + n_len] += 0.45 * swell * pad

    mix = _lowpass(mix, 2400.0)
    fade = int(SAMPLE_RATE * 1.5)
    mix[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    mix[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return _normalize(mix, peak=0.68)


def _synth_whoosh_sfx(duration: float = 0.45) -> np.ndarray:
    rng = np.random.default_rng(42)
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
    noise = rng.standard_normal(n).astype(np.float32)
    env = np.sin(np.pi * t / duration) ** 1.6
    sweep = np.sin(2 * np.pi * (180 + 520 * (t / duration)) * t) * 0.25
    sig = _lowpass(noise * env * 0.7 + sweep * env, 2600.0)
    return _normalize(sig, peak=0.75)


def _synth_surprise_sfx(duration: float = 0.85) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
    # Impacto cinematográfico grave + brilho metálico curto
    freq_drop = 150.0 * np.exp(-t * 5.2) + 38.0
    phase = 2 * np.pi * np.cumsum(freq_drop) / SAMPLE_RATE
    boom = np.sin(phase) * np.exp(-t * 3.6)
    sting = (np.sin(2 * np.pi * 660.0 * t) + 0.6 * np.sin(2 * np.pi * 987.7 * t)) * np.exp(-t * 7.5) * 0.35
    sig = _lowpass(boom + sting, 3400.0)
    return _normalize(sig, peak=0.85)


def _synth_ambient_sfx(duration: float = 4.0) -> np.ndarray:
    rng = np.random.default_rng(7)
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
    wind = _lowpass(rng.standard_normal(n).astype(np.float32), 450.0) * 0.35
    hum = 0.25 * np.sin(2 * np.pi * 98.0 * t) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.4 * t))
    env = np.sin(np.pi * t / duration) ** 0.5
    return _normalize((wind + hum) * env, peak=0.45)


def ensure_default_audio_assets(settings: Optional[Dict] = None) -> Dict[str, Path]:
    """
    Garante que `assets/music/` e `assets/sounds/` contenham trilhas e efeitos sonoros
    originais gerados localmente (sem baixar conteúdo protegido por direitos autorais).
    """
    cfg = settings or load_settings()
    assets_root = resolve_path(cfg["paths"]["assets_dir"])
    music_dir = assets_root / "music"
    sounds_dir = assets_root / "sounds"
    music_dir.mkdir(parents=True, exist_ok=True)
    sounds_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        "music_suspense": (music_dir / "suspense.wav", _synth_suspense_track),
        "music_divertida": (music_dir / "divertida.wav", _synth_fun_track),
        "music_emocionante": (music_dir / "emocionante.wav", _synth_emotional_track),
        "sfx_transicao": (sounds_dir / "transicao.wav", _synth_whoosh_sfx),
        "sfx_surpresa": (sounds_dir / "surpresa.wav", _synth_surprise_sfx),
        "sfx_ambiente": (sounds_dir / "ambiente.wav", _synth_ambient_sfx),
    }
    paths: Dict[str, Path] = {}
    for key, (path, builder) in targets.items():
        if not path.exists() or path.stat().st_size < 4096:
            audio = builder()
            sf.write(str(path), audio, SAMPLE_RATE, subtype="PCM_16")
        paths[key] = path
    return paths


def resolve_music_track(mood: str, settings: Optional[Dict] = None) -> Optional[Path]:
    assets = ensure_default_audio_assets(settings)
    low = (mood or "").lower()
    if "nenhum" in low or low == "none":
        return None
    if "divert" in low or "coméd" in low or "comed" in low or "fun" in low:
        return assets["music_divertida"]
    if "emocion" in low or "drama" in low or "avent" in low:
        return assets["music_emocionante"]
    return assets["music_suspense"]


def resolve_sfx_path(cue: str, settings: Optional[Dict] = None) -> Optional[Path]:
    cfg = settings or load_settings()
    assets = ensure_default_audio_assets(cfg)
    low = (cue or "").lower()

    # Se o pacote de SFX do roblox-story-kit estiver instalado localmente, usa os efeitos reais de alta qualidade!
    kit_engine = cfg.get("blender", {}).get("roblox_story_kit_engine", "")
    if kit_engine:
        kit_sfx = Path(kit_engine) / "sfx"
        if kit_sfx.exists():
            kit_map = {
                "surprise": kit_sfx / "boom.wav",
                "transition": kit_sfx / "whoosh.wav",
                "ambient": kit_sfx / "wind.wav",
            }
            cand = kit_map.get(low)
            if cand and cand.exists():
                return cand

    if low == "surprise":
        return assets["sfx_surpresa"]
    if low == "transition":
        return assets["sfx_transicao"]
    if low == "ambient":
        return assets["sfx_ambiente"]
    return None


def list_available_audio_assets(settings: Optional[Dict] = None) -> Dict[str, List[str]]:
    cfg = settings or load_settings()
    ensure_default_audio_assets(cfg)
    assets_root = resolve_path(cfg["paths"]["assets_dir"])
    music = sorted(p.name for p in (assets_root / "music").glob("*.*") if p.suffix.lower() in {".wav", ".mp3", ".ogg"})
    sounds = sorted(p.name for p in (assets_root / "sounds").glob("*.*") if p.suffix.lower() in {".wav", ".mp3", ".ogg"})
    return {"music": music, "sounds": sounds}
