"""AutoShorts AI — Procedural Python/NumPy Sound Effects, Original Background Music & FFmpeg Audio Mixer.

Synthesizes crisp cartoon/cinematic SFX at 44.1 kHz (stereo 16-bit WAV with tanh soft clipping)
using NumPy (and optional SciPy lfilter with exact pure-NumPy 1-pole fallback so every Python
version from 3.10 to 3.15 works out of the box).
"""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src.config import AutoShortsConfig
from src.utils import find_ffmpeg, run_subprocess, setup_logger

logger = setup_logger("autoshorts.sfx")

SR = 44100

try:
    from scipy.signal import lfilter as _scipy_lfilter  # type: ignore
except ImportError:
    _scipy_lfilter = None


def _one_pole_lowpass(x: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    """Fast 1-pole lowpass filter (SciPy accelerated when available, exact NumPy fallback)."""
    alpha = math.exp(-2.0 * math.pi * max(20.0, min(cutoff_hz, sr * 0.45)) / sr)
    if _scipy_lfilter is not None:
        return _scipy_lfilter([1.0 - alpha], [1.0, -alpha], x).astype(np.float32)
    y = np.empty_like(x, dtype=np.float32)
    acc = 0.0
    b = 1.0 - alpha
    for i in range(len(x)):
        acc = b * float(x[i]) + alpha * acc
        y[i] = acc
    return y


def _one_pole_highpass(x: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    return (x - _one_pole_lowpass(x, cutoff_hz, sr)).astype(np.float32)


def _seeded_noise(n: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, n).astype(np.float32)


def _env_exp(n: int, decay: float = 6.0) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    return np.exp(-decay * t).astype(np.float32)


# ---------- SKILL.md Procedural Sound Effect Generators ----------

def sfx_whoosh(dur: float = 0.42) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    noise = _seeded_noise(n, 101)
    filt = _one_pole_lowpass(noise, 1400.0)
    filt = _one_pole_highpass(filt, 220.0)
    env = np.maximum(0.0, np.sin(np.pi * t / dur)) ** 1.6
    return (filt * env * 1.4).astype(np.float32)


def sfx_swish(dur: float = 0.24) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    noise = _one_pole_highpass(_seeded_noise(n, 102), 1200.0)
    env = np.maximum(0.0, np.sin(np.pi * t / dur)) ** 1.3
    return (noise * env * 0.9).astype(np.float32)


def sfx_bass_hit(dur: float = 0.55) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 140.0 * np.exp(-6.5 * t) + 38.0
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    sub = np.sin(phase) * _env_exp(n, 4.5)
    punch = _one_pole_lowpass(_seeded_noise(n, 103), 650.0) * _env_exp(n, 24.0) * 0.7
    return (sub * 0.95 + punch).astype(np.float32)


def sfx_knock(dur: float = 0.45) -> np.ndarray:
    out = np.zeros(int(SR * dur), dtype=np.float32)
    for offset in (0.0, 0.16):
        k_n = int(SR * 0.11)
        t = np.linspace(0.0, 0.11, k_n, dtype=np.float32)
        wood = (np.sin(2 * np.pi * 240 * t) + 0.5 * np.sin(2 * np.pi * 510 * t)) * _env_exp(k_n, 22.0)
        wood += _one_pole_lowpass(_seeded_noise(k_n, 104), 1200.0) * _env_exp(k_n, 35.0) * 0.4
        i0 = int(offset * SR)
        out[i0 : i0 + k_n] += wood
    return out


def sfx_thunder(dur: float = 1.4) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    rumble = _one_pole_lowpass(_seeded_noise(n, 105), 180.0) * (1.0 - np.exp(-25.0 * t)) * _env_exp(n, 2.2)
    crack = _one_pole_highpass(_seeded_noise(n, 106), 900.0) * _env_exp(n, 18.0) * 0.45
    return (rumble * 2.4 + crack).astype(np.float32)


def sfx_pop(dur: float = 0.14) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 280.0 + 920.0 * np.exp(-28.0 * t)
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    return (np.sin(phase) * _env_exp(n, 16.0) * 0.85).astype(np.float32)


def sfx_boing(dur: float = 0.52) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 190.0 + 180.0 * np.sin(2 * np.pi * 9.0 * t) * _env_exp(n, 3.0) + 140.0 * t
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    return (np.sin(phase) * _env_exp(n, 4.2) * 0.8).astype(np.float32)


def sfx_ding(dur: float = 0.65) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    sig = (
        0.65 * np.sin(2 * np.pi * 1318.5 * t)
        + 0.35 * np.sin(2 * np.pi * 2637.0 * t)
        + 0.15 * np.sin(2 * np.pi * 3955.5 * t)
    )
    return (sig * _env_exp(n, 5.5) * 0.75).astype(np.float32)


def sfx_bell(dur: float = 1.1) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    sig = (
        0.6 * np.sin(2 * np.pi * 880.0 * t)
        + 0.4 * np.sin(2 * np.pi * 1320.0 * t)
        + 0.25 * np.sin(2 * np.pi * 2112.0 * t)
    )
    return (sig * _env_exp(n, 3.2) * 0.75).astype(np.float32)


def sfx_slap(dur: float = 0.2) -> np.ndarray:
    n = int(SR * dur)
    noise = _one_pole_highpass(_seeded_noise(n, 107), 850.0) * _env_exp(n, 28.0)
    thud = np.sin(2 * np.pi * 160 * np.linspace(0, dur, n, dtype=np.float32)) * _env_exp(n, 20.0)
    return (noise * 0.95 + thud * 0.5).astype(np.float32)


def sfx_riser(dur: float = 0.95) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 180.0 * (2.0 ** (2.5 * t / dur))
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    env = (t / dur) ** 1.5 * np.clip((dur - t) * 25.0, 0.0, 1.0)
    return (np.sin(phase) * env * 0.65).astype(np.float32)


def sfx_sting(dur: float = 0.75) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    # Dramatic minor-second / diminished comedy sting
    sig = (
        0.5 * np.sin(2 * np.pi * 440.0 * t)
        + 0.45 * np.sin(2 * np.pi * 466.16 * t)
        + 0.35 * np.sin(2 * np.pi * 622.25 * t)
    )
    return (sig * _env_exp(n, 4.0) * 0.75).astype(np.float32)


def sfx_trombone(dur: float = 1.05) -> np.ndarray:
    """Classic comic 'wah-wah-waaaah' downward pitch bend."""
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = np.where(t < 0.28, 311.1, np.where(t < 0.56, 293.7, 277.2 - 38.0 * (t - 0.56)))
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    brass = np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.25 * np.sin(3 * phase)
    env = np.where(t < 0.26, 0.85, np.where(t < 0.28, 0.1, np.where(t < 0.54, 0.85, np.where(t < 0.56, 0.1, _env_exp(n, 2.2)))))
    return (brass * env * 0.45).astype(np.float32)


def sfx_footsteps(dur: float = 0.85) -> np.ndarray:
    out = np.zeros(int(SR * dur), dtype=np.float32)
    for idx, step_t in enumerate((0.0, 0.21, 0.42, 0.63)):
        sn = int(SR * 0.09)
        t = np.linspace(0.0, 0.09, sn, dtype=np.float32)
        thump = np.sin(2 * np.pi * (105 + (idx % 2) * 18) * t) * _env_exp(sn, 26.0)
        grit = _one_pole_lowpass(_seeded_noise(sn, 120 + idx), 900.0) * _env_exp(sn, 30.0) * 0.35
        i0 = int(step_t * SR)
        if i0 + sn <= len(out):
            out[i0 : i0 + sn] += (thump + grit) * 0.8
    return out


def sfx_click(dur: float = 0.06) -> np.ndarray:
    n = int(SR * dur)
    return (_one_pole_highpass(_seeded_noise(n, 108), 1800.0) * _env_exp(n, 55.0) * 0.9).astype(np.float32)


def sfx_clank(dur: float = 0.35) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    sig = np.sin(2 * np.pi * 620 * t) + 0.7 * np.sin(2 * np.pi * 1140 * t) + 0.5 * np.sin(2 * np.pi * 1790 * t)
    return (sig * _env_exp(n, 12.0) * 0.5).astype(np.float32)


def sfx_creak(dur: float = 0.55) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 280.0 + 180.0 * np.sin(2 * np.pi * 3.5 * t)
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    return (np.sign(np.sin(phase)) * 0.25 * np.sin(np.pi * t / dur)).astype(np.float32)


def sfx_heartbeat(dur: float = 0.6) -> np.ndarray:
    out = np.zeros(int(SR * dur), dtype=np.float32)
    for offset, gain in ((0.0, 0.9), (0.2, 0.65)):
        hn = int(SR * 0.14)
        t = np.linspace(0.0, 0.14, hn, dtype=np.float32)
        beat = np.sin(2 * np.pi * 58 * t) * _env_exp(hn, 16.0) * gain
        i0 = int(offset * SR)
        out[i0 : i0 + hn] += beat
    return out


def sfx_blip(dur: float = 0.12) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    return (np.sign(np.sin(2 * np.pi * 880.0 * t)) * _env_exp(n, 18.0) * 0.35).astype(np.float32)


def sfx_buzz(dur: float = 0.35) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    return (np.sign(np.sin(2 * np.pi * 110.0 * t)) * 0.3 * _env_exp(n, 5.0)).astype(np.float32)


def sfx_shing(dur: float = 0.45) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    sig = np.sin(2 * np.pi * 2400 * t) * 0.4 + np.sin(2 * np.pi * 3850 * t) * 0.3
    return (sig * _env_exp(n, 9.0)).astype(np.float32)


def sfx_squeak(dur: float = 0.18) -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    freq = 900.0 + 1100.0 * np.sin(np.pi * t / dur)
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    return (np.sin(phase) * np.sin(np.pi * t / dur) * 0.55).astype(np.float32)


SFX_GENERATORS = {
    "whoosh": sfx_whoosh,
    "swish": sfx_swish,
    "bass_hit": sfx_bass_hit,
    "knock": sfx_knock,
    "thunder": sfx_thunder,
    "pop": sfx_pop,
    "boing": sfx_boing,
    "ding": sfx_ding,
    "bell": sfx_bell,
    "slap": sfx_slap,
    "riser": sfx_riser,
    "sting": sfx_sting,
    "trombone": sfx_trombone,
    "footsteps": sfx_footsteps,
    "click": sfx_click,
    "clank": sfx_clank,
    "creak": sfx_creak,
    "heartbeat": sfx_heartbeat,
    "blip": sfx_blip,
    "buzz": sfx_buzz,
    "shing": sfx_shing,
    "squeak": sfx_squeak,
}


def _write_stereo_wav(path: Path, left: np.ndarray, right: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    l_soft = np.tanh(np.nan_to_num(left, nan=0.0, posinf=1.0, neginf=-1.0))
    r_soft = np.tanh(np.nan_to_num(right, nan=0.0, posinf=1.0, neginf=-1.0))
    interleaved = np.empty(len(l_soft) * 2, dtype=np.int16)
    interleaved[0::2] = np.clip(l_soft * 32767.0, -32768, 32767).astype(np.int16)
    interleaved[1::2] = np.clip(r_soft * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved.tobytes())
    return path


def synthesize_sfx_track(
    storyboard: Dict[str, Any],
    out_wav: Path,
) -> Path:
    """Synthesize all storyboard SFX cues + subtle scene transition whooshes & light room tone."""
    dur = float(storyboard["duration_sec"])
    n_total = max(SR, int(math.ceil(dur * SR)))
    left = np.zeros(n_total, dtype=np.float32)
    right = np.zeros(n_total, dtype=np.float32)

    def add(time_sec: float, samples: np.ndarray, gain: float = 0.85, pan: float = 0.0) -> None:
        i0 = max(0, int(round(time_sec * SR)))
        if i0 >= n_total:
            return
        seg = samples[: n_total - i0]
        l_gain = gain * math.sqrt(0.5 * (1.0 - max(-1.0, min(1.0, pan))))
        r_gain = gain * math.sqrt(0.5 * (1.0 + max(-1.0, min(1.0, pan))))
        left[i0 : i0 + len(seg)] += seg * l_gain
        right[i0 : i0 + len(seg)] += seg * r_gain

    # Very soft ambient bed so transitions never feel sterile
    ambient = _one_pole_lowpass(_seeded_noise(n_total, 777), 320.0) * 0.015
    left += ambient
    right += ambient

    prev_set = None
    for idx, shot in enumerate(storyboard.get("shots", [])):
        t0 = float(shot["start"])
        cur_set = shot.get("set")
        if prev_set is not None and cur_set != prev_set:
            add(max(0.0, t0 - 0.08), sfx_swish(), gain=0.45, pan=-0.2 if idx % 2 == 0 else 0.2)
        prev_set = cur_set

        sfx_name = shot.get("sfx")
        if sfx_name and sfx_name in SFX_GENERATORS:
            samples = SFX_GENERATORS[sfx_name]()
            pan = 0.0 if sfx_name in ("bass_hit", "thunder", "trombone") else (-0.25 if idx % 2 == 0 else 0.25)
            add(t0, samples, gain=0.9, pan=pan)

    return _write_stereo_wav(out_wav, left, right, sr=SR)


def synthesize_background_music(duration_sec: float, out_wav: Path, bpm: float = 112.0) -> Path:
    """Generate a 100% original playful cartoon marimba + warm synth bass backing track."""
    n_total = max(SR, int(math.ceil(duration_sec * SR)))
    left = np.zeros(n_total, dtype=np.float32)
    right = np.zeros(n_total, dtype=np.float32)

    beat_sec = 60.0 / bpm
    # C major / A minor quirky upbeat progression (Hz)
    chords = [
        (261.63, 329.63, 392.00, 130.81),  # C
        (220.00, 261.63, 329.63, 110.00),  # Am
        (174.61, 220.00, 261.63, 87.31),   # F
        (196.00, 246.94, 293.66, 98.00),   # G
    ]
    melody_pattern = [0, 1, 2, 1, 2, 0, 1, 2]

    step = 0
    t_cur = 0.0
    while t_cur < duration_sec:
        chord = chords[(step // 4) % len(chords)]
        # Plucky marimba note every half-beat
        note_freq = chord[melody_pattern[step % len(melody_pattern)]] * (2.0 if step % 4 == 2 else 1.0)
        note_dur = min(0.32, duration_sec - t_cur)
        if note_dur > 0.02:
            nn = int(note_dur * SR)
            tt = np.linspace(0.0, note_dur, nn, dtype=np.float32)
            pluck = (np.sin(2 * np.pi * note_freq * tt) + 0.22 * np.sin(4 * np.pi * note_freq * tt)) * _env_exp(nn, 11.0)
            i0 = int(t_cur * SR)
            seg = pluck[: n_total - i0] * 0.24
            pan_l = 0.65 if step % 2 == 0 else 0.45
            left[i0 : i0 + len(seg)] += seg * pan_l
            right[i0 : i0 + len(seg)] += seg * (1.1 - pan_l)

        # Warm soft bass on downbeats
        if step % 2 == 0:
            b_dur = min(beat_sec * 0.9, duration_sec - t_cur)
            bn = int(b_dur * SR)
            bt = np.linspace(0.0, b_dur, bn, dtype=np.float32)
            bass = np.sin(2 * np.pi * chord[3] * bt) * _env_exp(bn, 3.8) * 0.28
            i0 = int(t_cur * SR)
            seg = bass[: n_total - i0]
            left[i0 : i0 + len(seg)] += seg
            right[i0 : i0 + len(seg)] += seg

        t_cur += beat_sec * 0.5
        step += 1

    # Smooth fade-out on final 0.8s
    fade_n = min(n_total, int(0.8 * SR))
    if fade_n > 0:
        fade = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
        left[-fade_n:] *= fade
        right[-fade_n:] *= fade

    return _write_stereo_wav(out_wav, left, right, sr=SR)


def mix_final_audio(
    vo_wav: Path,
    duration_sec: float,
    out_mix_wav: Path,
    sfx_wav: Optional[Path] = None,
    music_wav: Optional[Path] = None,
    config: Optional[AutoShortsConfig] = None,
) -> Path:
    """Mix normalized voice-over, synchronized SFX, and optional background music via FFmpeg.

    Voice clarity always takes priority (loudnorm I=-15, TP=-1.5, SFX at 0.42, music at 0.12, alimiter 0.95).
    """
    cfg = config or AutoShortsConfig.load()
    ffmpeg = find_ffmpeg()
    out_mix_wav.parent.mkdir(parents=True, exist_ok=True)

    sfx_vol = float(cfg.get("audio.sfx_volume", 0.42))
    music_vol = float(cfg.get("audio.music_volume", 0.12))
    ln_i = float(cfg.get("audio.voice_loudnorm_i", -15.0))
    ln_tp = float(cfg.get("audio.voice_loudnorm_tp", -1.5))
    ln_lra = float(cfg.get("audio.voice_loudnorm_lra", 11.0))
    limiter = float(cfg.get("audio.limiter_limit", 0.95))

    inputs = ["-i", str(vo_wav)]
    filter_parts = [
        f"[0:a]aformat=channel_layouts=stereo,aresample=44100,apad=whole_dur={duration_sec:.3f},"
        f"loudnorm=I={ln_i}:TP={ln_tp}:LRA={ln_lra}[v]"
    ]
    mix_labels = ["[v]"]

    idx = 1
    if sfx_wav and sfx_wav.exists():
        inputs.extend(["-i", str(sfx_wav)])
        filter_parts.append(f"[{idx}:a]aformat=channel_layouts=stereo,aresample=44100,volume={sfx_vol:.3f}[s]")
        mix_labels.append("[s]")
        idx += 1

    if music_wav and music_wav.exists():
        inputs.extend(["-i", str(music_wav)])
        filter_parts.append(f"[{idx}:a]aformat=channel_layouts=stereo,aresample=44100,volume={music_vol:.3f}[m]")
        mix_labels.append("[m]")
        idx += 1

    if len(mix_labels) == 1:
        filter_parts.append(f"[v]alimiter=limit={limiter:.2f}[a]")
    else:
        filter_parts.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0:duration=longest,"
            f"alimiter=limit={limiter:.2f}[a]"
        )

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[a]",
        "-t",
        f"{duration_sec:.3f}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(out_mix_wav),
    ]
    run_subprocess(cmd)
    logger.info("Mixagem final gerada: %s (%.2fs)", out_mix_wav, duration_sec)
    return out_mix_wav
