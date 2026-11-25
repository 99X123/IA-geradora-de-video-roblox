"""AutoShorts AI — Pluggable Multi-Voice PT-BR Text-to-Speech Engine.

Supports swapping TTS providers cleanly without touching downstream modules:
  - GoogleCloudTTSProvider (Google Cloud Text-to-Speech API)
  - EdgeTTSProvider (Microsoft Edge Neural PT-BR voices + real WordBoundary timestamps)
  - OpenAITTSProvider (OpenAI TTS API)
  - LocalSynthTestTTSProvider (offline deterministic prosody test provider)

Never requires manual voice recording and never clones real people's voices.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import numpy as np
import requests

from src.config import AutoShortsConfig, get_secret
from src.utils import find_ffmpeg, run_subprocess, setup_logger

logger = setup_logger("autoshorts.tts")


@dataclass
class SynthesizedLine:
    index: int
    speaker: str
    character_id: str
    text: str
    audio_path: Path
    duration_sec: float
    provider: str
    voice_id: str
    word_boundaries: List[Dict[str, Any]] = field(default_factory=list)


class TTSProvider(ABC):
    """Abstract interface for interchangeable TTS providers."""

    name: str = "base"

    @abstractmethod
    def synthesize_line(
        self,
        text: str,
        voice_cfg: Dict[str, Any],
        out_path: Path,
    ) -> tuple[Path, List[Dict[str, Any]], str]:
        """Synthesize one line to an audio file.

        Returns:
            (audio_file_path, word_boundaries_list, actual_voice_id)
        """


class EdgeTTSProvider(TTSProvider):
    """Natural PT-BR Neural voices via edge-tts with real acoustic WordBoundary timestamps."""

    name = "edge_tts"

    async def _run_async(
        self, text: str, voice: str, rate: str, pitch: str, out_mp3: Path
    ) -> List[Dict[str, Any]]:
        import edge_tts

        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch, boundary="WordBoundary")
        boundaries: List[Dict[str, Any]] = []
        audio_chunks: List[bytes] = []

        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                audio_chunks.append(chunk["data"])
            elif ctype == "WordBoundary":
                # Edge-tts returns offset & duration in 100-nanosecond ticks
                start_sec = float(chunk["offset"]) / 10_000_000.0
                dur_sec = float(chunk["duration"]) / 10_000_000.0
                boundaries.append(
                    {
                        "word": str(chunk["text"]).strip(),
                        "start": round(start_sec, 4),
                        "end": round(start_sec + max(0.04, dur_sec), 4),
                        "source": "edge_tts_word_boundary",
                    }
                )

        if not audio_chunks:
            raise RuntimeError(f"Edge TTS retornou áudio vazio para voz '{voice}'.")
        out_mp3.parent.mkdir(parents=True, exist_ok=True)
        out_mp3.write_bytes(b"".join(audio_chunks))
        return boundaries

    def synthesize_line(
        self, text: str, voice_cfg: Dict[str, Any], out_path: Path
    ) -> tuple[Path, List[Dict[str, Any]], str]:
        voice = str(voice_cfg.get("edge") or "pt-BR-AntonioNeural")
        rate = str(voice_cfg.get("rate") or "+6%")
        pitch = str(voice_cfg.get("pitch") or "+0Hz")
        mp3_path = out_path.with_suffix(".mp3")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Inside Jupyter / Google Colab an event loop may already be active
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                boundaries = pool.submit(
                    lambda: asyncio.run(self._run_async(text, voice, rate, pitch, mp3_path))
                ).result()
        else:
            boundaries = asyncio.run(self._run_async(text, voice, rate, pitch, mp3_path))

        return mp3_path, boundaries, voice


class GoogleCloudTTSProvider(TTSProvider):
    """Google Cloud Text-to-Speech API (Neural2 / WaveNet PT-BR voices)."""

    name = "google_cloud"

    def synthesize_line(
        self, text: str, voice_cfg: Dict[str, Any], out_path: Path
    ) -> tuple[Path, List[Dict[str, Any]], str]:
        voice_name = str(voice_cfg.get("google_cloud") or "pt-BR-Neural2-B")
        rate_str = str(voice_cfg.get("rate") or "+6%").replace("%", "")
        try:
            speaking_rate = max(0.5, min(2.0, 1.0 + float(rate_str) / 100.0))
        except ValueError:
            speaking_rate = 1.05

        wav_path = out_path.with_suffix(".wav")
        creds_path = get_secret("GOOGLE_APPLICATION_CREDENTIALS")

        if creds_path and Path(creds_path).exists():
            from google.cloud import texttospeech  # type: ignore

            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code="pt-BR",
                name=voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=44100,
                speaking_rate=speaking_rate,
            )
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(response.audio_content)
            return wav_path, [], voice_name

        # REST API fallback using GOOGLE_API_KEY
        api_key = get_secret("GOOGLE_API_KEY") or get_secret("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Google Cloud TTS requer GOOGLE_APPLICATION_CREDENTIALS ou GOOGLE_API_KEY configurado."
            )
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "pt-BR", "name": voice_name},
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 44100,
                "speakingRate": speaking_rate,
            },
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        import base64

        audio_bytes = base64.b64decode(resp.json()["audioContent"])
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(audio_bytes)
        return wav_path, [], voice_name


class OpenAITTSProvider(TTSProvider):
    """OpenAI TTS API provider (swappable backend)."""

    name = "openai"

    def synthesize_line(
        self, text: str, voice_cfg: Dict[str, Any], out_path: Path
    ) -> tuple[Path, List[Dict[str, Any]], str]:
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI TTS requer OPENAI_API_KEY configurado.")
        voice = str(voice_cfg.get("openai") or "onyx")
        base_url = (get_secret("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        resp = requests.post(
            f"{base_url}/audio/speech",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "response_format": "wav"},
            timeout=45,
        )
        resp.raise_for_status()
        wav_path = out_path.with_suffix(".wav")
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(resp.content)
        return wav_path, [], voice


class LocalSynthTestTTSProvider(TTSProvider):
    """Offline deterministic speech-cadence audio synthesizer for CI/local testing without internet.

    Produces clear syllable-modulated pitched vocal-formant tones with real silent gaps
    between words so forced alignment, lip-sync RMS envelopes, and audio quality checks
    can run 100% offline.
    """

    name = "local_synth_test"

    def synthesize_line(
        self, text: str, voice_cfg: Dict[str, Any], out_path: Path
    ) -> tuple[Path, List[Dict[str, Any]], str]:
        sr = 44100
        role_pitch = str(voice_cfg.get("pitch") or "+0Hz")
        base_f0 = 155.0 if "-" in role_pitch else (210.0 if "+2" in role_pitch else 180.0)

        words = [w for w in text.strip().split() if w]
        if not words:
            words = ["ola"]

        segments: List[np.ndarray] = []
        boundaries: List[Dict[str, Any]] = []
        cursor_sec = 0.06
        segments.append(np.zeros(int(sr * cursor_sec), dtype=np.float32))

        for idx, word in enumerate(words):
            dur = max(0.14, min(0.55, 0.08 + len(word) * 0.045))
            n = int(sr * dur)
            t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)

            # Formant-like prosody contour so RMS envelope fluctuates realistically per syllable
            f0 = base_f0 * (1.0 + 0.12 * math.sin(idx * 1.3) - 0.08 * (t / dur))
            phase = 2.0 * np.pi * np.cumsum(f0) / sr
            sig = (
                0.55 * np.sin(phase)
                + 0.28 * np.sin(2.0 * phase)
                + 0.14 * np.sin(3.0 * phase)
                + 0.08 * np.sin(5.0 * phase)
            )
            # Syllable amplitude envelope
            syllables = max(1, len(word) // 3)
            env = np.sin(np.pi * t / dur) ** 0.55 * (0.65 + 0.35 * np.abs(np.sin(np.pi * syllables * t / dur)))
            sig = (sig * env * 0.42).astype(np.float32)

            boundaries.append(
                {
                    "word": word,
                    "start": round(cursor_sec, 4),
                    "end": round(cursor_sec + dur, 4),
                    "source": "local_synth_test_boundary",
                }
            )
            segments.append(sig)
            cursor_sec += dur

            # Brief inter-word pause (longer after punctuation)
            gap = 0.18 if word[-1] in ".!?" else (0.11 if word[-1] in ",;:" else 0.045)
            segments.append(np.zeros(int(sr * gap), dtype=np.float32))
            cursor_sec += gap

        audio = np.concatenate(segments)
        pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)

        wav_path = out_path.with_suffix(".wav")
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())

        return wav_path, boundaries, f"synth_f0_{int(base_f0)}hz"


PROVIDER_REGISTRY: Dict[str, Type[TTSProvider]] = {
    "edge_tts": EdgeTTSProvider,
    "edge": EdgeTTSProvider,
    "google_cloud": GoogleCloudTTSProvider,
    "google": GoogleCloudTTSProvider,
    "openai": OpenAITTSProvider,
    "local_synth_test": LocalSynthTestTTSProvider,
    "test": LocalSynthTestTTSProvider,
}


def register_tts_provider(name: str, provider_cls: Type[TTSProvider]) -> None:
    """Allow users to plug in custom TTS providers without modifying pipeline code."""
    PROVIDER_REGISTRY[name.lower()] = provider_cls


def _convert_to_pcm_wav(src_path: Path, dst_wav: Path, sample_rate: int = 44100) -> float:
    """Convert any audio format to clean 44.1 kHz 16-bit mono PCM WAV and return exact duration."""
    ffmpeg = find_ffmpeg()
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    run_subprocess(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            str(dst_wav),
        ]
    )
    with wave.open(str(dst_wav), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def _select_provider_chain(provider_name: str) -> List[TTSProvider]:
    key = provider_name.lower()
    if key != "auto":
        if key not in PROVIDER_REGISTRY:
            raise ValueError(f"Provedor TTS desconhecido: '{provider_name}'. Opções: {list(PROVIDER_REGISTRY)}")
        return [PROVIDER_REGISTRY[key]()]

    chain: List[TTSProvider] = []
    if get_secret("GOOGLE_APPLICATION_CREDENTIALS"):
        chain.append(GoogleCloudTTSProvider())
    chain.append(EdgeTTSProvider())
    if get_secret("OPENAI_API_KEY"):
        chain.append(OpenAITTSProvider())
    chain.append(LocalSynthTestTTSProvider())
    return chain


def synthesize_story_audio(
    story: Dict[str, Any],
    out_dir: Path,
    config: Optional[AutoShortsConfig] = None,
    provider_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Synthesize every dialogue line with character-specific voices and concatenate into `vo.wav`."""
    cfg = config or AutoShortsConfig.load()
    sample_rate = int(cfg.get("audio.sample_rate", 44100))
    pause_ms = int(cfg.get("tts.pause_between_lines_ms", 140))
    provider_pref = provider_override or str(cfg.get("tts.provider", "auto"))
    voices_cfg = cfg.get("tts.voices", {})

    out_dir = Path(out_dir)
    lines_dir = out_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    char_voice_role = {
        c["speaker_code"]: c.get("voice_role", "narrator" if c["speaker_code"] == "N" else "costar")
        for c in story["characters"]
    }

    chain = _select_provider_chain(provider_pref)
    synthesized: List[SynthesizedLine] = []
    fallback_warnings: List[str] = []

    for ln in story["lines"]:
        idx = int(ln["index"])
        spk = ln["speaker"]
        role = char_voice_role.get(spk, "narrator" if spk == "N" else "costar")
        vcfg = voices_cfg.get(role) or voices_cfg.get("narrator") or {}

        raw_out = lines_dir / f"line_{idx:03d}_{spk}"
        pcm_wav = lines_dir / f"line_{idx:03d}_{spk}_pcm.wav"

        chosen_provider: Optional[TTSProvider] = None
        raw_audio_path: Optional[Path] = None
        boundaries: List[Dict[str, Any]] = []
        voice_id = ""
        last_err: Optional[Exception] = None

        for prov in chain:
            try:
                raw_audio_path, boundaries, voice_id = prov.synthesize_line(ln["text"], vcfg, raw_out)
                chosen_provider = prov
                break
            except Exception as exc:
                last_err = exc
                msg = f"Provedor TTS '{prov.name}' falhou na fala {idx}: {exc}"
                logger.warning(msg)
                fallback_warnings.append(msg)

        if chosen_provider is None or raw_audio_path is None:
            raise RuntimeError(f"Todos os provedores TTS falharam na fala {idx}: {last_err}")

        dur_sec = _convert_to_pcm_wav(raw_audio_path, pcm_wav, sample_rate=sample_rate)
        synthesized.append(
            SynthesizedLine(
                index=idx,
                speaker=spk,
                character_id=ln["character_id"],
                text=ln["text"],
                audio_path=pcm_wav,
                duration_sec=round(dur_sec, 4),
                provider=chosen_provider.name,
                voice_id=voice_id,
                word_boundaries=boundaries,
            )
        )

    # Concatenate all PCM WAV segments with clean controlled inter-line pauses into `vo.wav`
    pause_samples = np.zeros(int(sample_rate * (pause_ms / 1000.0)), dtype=np.int16)
    lead_silence = np.zeros(int(sample_rate * 0.08), dtype=np.int16)
    all_pcm: List[np.ndarray] = [lead_silence]
    cursor_sec = len(lead_silence) / float(sample_rate)

    segment_manifest: List[Dict[str, Any]] = []
    for i, item in enumerate(synthesized):
        with wave.open(str(item.audio_path), "rb") as wf:
            frames = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        seg_start = cursor_sec
        seg_end = cursor_sec + len(frames) / float(sample_rate)

        shifted_bounds = []
        for wb in item.word_boundaries:
            shifted_bounds.append(
                {
                    "word": wb["word"],
                    "start": round(seg_start + float(wb["start"]), 4),
                    "end": round(seg_start + float(wb["end"]), 4),
                    "speaker": item.speaker,
                    "source": wb.get("source", item.provider),
                }
            )

        segment_manifest.append(
            {
                "index": item.index,
                "speaker": item.speaker,
                "character_id": item.character_id,
                "text": item.text,
                "audio_path": str(item.audio_path),
                "start": round(seg_start, 4),
                "end": round(seg_end, 4),
                "duration_sec": round(seg_end - seg_start, 4),
                "provider": item.provider,
                "voice_id": item.voice_id,
                "word_boundaries": shifted_bounds,
            }
        )
        all_pcm.append(frames)
        cursor_sec = seg_end

        if i + 1 < len(synthesized):
            all_pcm.append(pause_samples)
            cursor_sec += len(pause_samples) / float(sample_rate)

    vo_wav_path = out_dir / "vo.wav"
    concatenated = np.concatenate(all_pcm)
    with wave.open(str(vo_wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(concatenated.tobytes())

    total_vo_dur = len(concatenated) / float(sample_rate)
    providers_used = sorted({s.provider for s in synthesized})

    metadata = {
        "vo_wav": str(vo_wav_path),
        "sample_rate": sample_rate,
        "duration_sec": round(total_vo_dur, 4),
        "providers_used": providers_used,
        "fallback_warnings": fallback_warnings,
        "segments": segment_manifest,
    }
    meta_path = out_dir / "tts_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "TTS concluído: %d falas, duração %.2fs, provedores=%s",
        len(synthesized),
        total_vo_dur,
        providers_used,
    )
    return metadata
