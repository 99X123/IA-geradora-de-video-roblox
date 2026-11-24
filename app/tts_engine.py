"""Motor de narração automática local em Português Brasileiro (Kokoro TTS ONNX + alternativa local Piper)."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import numpy as np
import soundfile as sf

from app.config import load_settings, resolve_path
from app.models import StoryboardDocument

logger = logging.getLogger("roblox_ai_shorts_studio")

PT_BR_VOICES: Dict[str, Dict[str, str]] = {
    "pm_alex": {
        "label": "Alex (Masculina PT-BR — Dinâmica / Recomendada)",
        "engine": "kokoro",
        "lang": "pt-br",
    },
    "pf_dora": {
        "label": "Dora (Feminina PT-BR — Expressiva / Clara)",
        "engine": "kokoro",
        "lang": "pt-br",
    },
    "pm_santa": {
        "label": "Henrique (Masculina Grave PT-BR — Suspense / Terror)",
        "engine": "kokoro",
        "lang": "pt-br",
    },
}

EXPRESSION_SPEED_FACTOR: Dict[str, float] = {
    "neutral": 1.00,
    "curious": 1.02,
    "happy": 1.05,
    "worried": 0.98,
    "scared": 1.06,
    "angry": 1.07,
    "shocked": 1.04,
    "determined": 1.05,
}


class TTSError(RuntimeError):
    """Erro na síntese de voz local."""


class LocalTTSEngine:
    """
    Gera narração expressiva em PT-BR 100% local (R$ 0 em APIs):
    1. Kokoro TTS v1.0 via kokoro-onnx + espeakng-loader (Apache-2.0 / MIT).
    2. Piper TTS local ONNX (MIT) como alternativa open source se configurado.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        self.settings = settings or load_settings()
        self._kokoro_instance: Any = None
        self.model_path = resolve_path(self.settings["tts"]["kokoro_model_file"])
        self.voices_path = resolve_path(self.settings["tts"]["kokoro_voices_file"])
        self.piper_model_path = resolve_path(self.settings["tts"]["piper_model_file"])

    def is_kokoro_installed(self) -> bool:
        return (
            self.model_path.exists()
            and self.model_path.stat().st_size > 10_000_000
            and self.voices_path.exists()
            and self.voices_path.stat().st_size > 1_000_000
        )

    def download_kokoro_models(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Path, Path]:
        """Baixa os arquivos leves do Kokoro v1.0 INT8 (~88 MB + ~27 MB) quando autorizado pelo usuário."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        downloads = [
            (self.settings["tts"]["kokoro_model_url"], self.model_path, "kokoro-v1.0.int8.onnx (~88 MB)"),
            (self.settings["tts"]["kokoro_voices_url"], self.voices_path, "voices-v1.0.bin (~27 MB)"),
        ]
        for url, target, desc in downloads:
            if target.exists() and target.stat().st_size > 1_000_000:
                if progress_cb:
                    progress_cb(f"Já disponível localmente: {target.name}")
                continue
            if progress_cb:
                progress_cb(f"Baixando {desc}...")
            tmp = target.with_suffix(target.suffix + ".part")
            with httpx.stream("GET", url, follow_redirects=True, timeout=180.0) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        fh.write(chunk)
            tmp.replace(target)
            if progress_cb:
                progress_cb(f"Download concluído: {target.name}")
        return self.model_path, self.voices_path

    def _get_kokoro(self) -> Any:
        if self._kokoro_instance is not None:
            return self._kokoro_instance
        if not self.is_kokoro_installed():
            raise TTSError(
                "Modelos do Kokoro TTS não encontrados em models/kokoro/. "
                "Execute o download pelo botão 'Baixar Modelos Locais (Kokoro + Whisper)' ou via install.bat."
            )
        import espeakng_loader  # type: ignore
        from kokoro_onnx import Kokoro  # type: ignore
        from kokoro_onnx.config import EspeakConfig  # type: ignore

        espeak_cfg = EspeakConfig(
            lib_path=espeakng_loader.get_library_path(),
            data_path=espeakng_loader.get_data_path(),
        )
        self._kokoro_instance = Kokoro(
            str(self.model_path),
            str(self.voices_path),
            espeak_config=espeak_cfg,
        )
        return self._kokoro_instance

    @staticmethod
    def _clean_text_for_tts(text: str) -> str:
        # Remove emojis e símbolos que prejudicam a pronúncia em PT-BR
        cleaned = re.sub(r"[^\w\sáàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ.,!?;:\-–—'\"()]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        return cleaned

    @staticmethod
    def _normalize_audio(samples: np.ndarray, peak_target: float = 0.88) -> np.ndarray:
        arr = np.asarray(samples, dtype=np.float32)
        if arr.size == 0:
            return arr
        max_abs = float(np.max(np.abs(arr)))
        if max_abs > 1e-6:
            arr = arr * (peak_target / max_abs)
        return arr

    def _synthesize_piper_cli(self, text: str, output_wav: Path, speed: float = 1.0) -> Tuple[np.ndarray, int]:
        """Alternativa open source local via Piper caso configurado em models/piper/."""
        if not self.piper_model_path.exists():
            raise TTSError("Modelo Piper PT-BR não encontrado em models/piper/.")
        length_scale = max(0.6, min(1.5, 1.0 / max(0.5, speed)))
        cmd = [
            "piper",
            "--model",
            str(self.piper_model_path),
            "--output_file",
            str(output_wav),
            "--length_scale",
            f"{length_scale:.2f}",
        ]
        subprocess.run(cmd, input=text, text=True, check=True, timeout=60)
        data, sr = sf.read(str(output_wav), dtype="float32")
        return np.asarray(data, dtype=np.float32), int(sr)

    def synthesize_text(
        self,
        text: str,
        output_wav: Path,
        voice: str = "pm_alex",
        speed: float = 1.05,
        auto_download_if_missing: bool = False,
    ) -> Tuple[Path, float, int]:
        """Gera narração em WAV para qualquer trecho em Português Brasileiro."""
        clean = self._clean_text_for_tts(text)
        if not clean:
            raise TTSError("Texto vazio para síntese de narração.")

        chosen_voice = voice if voice in PT_BR_VOICES else "pm_alex"
        speed_clamped = max(0.75, min(1.45, float(speed)))
        output_wav.parent.mkdir(parents=True, exist_ok=True)

        if not self.is_kokoro_installed() and auto_download_if_missing:
            self.download_kokoro_models()

        if self.is_kokoro_installed():
            kokoro = self._get_kokoro()
            samples, sample_rate = kokoro.create(
                clean,
                voice=chosen_voice,
                speed=speed_clamped,
                lang="pt-br",
                trim=True,
            )
            samples = self._normalize_audio(samples)
            sf.write(str(output_wav), samples, sample_rate, subtype="PCM_16")
            duration = float(len(samples)) / float(sample_rate)
            return output_wav, round(duration, 3), int(sample_rate)

        if self.piper_model_path.exists():
            samples, sample_rate = self._synthesize_piper_cli(clean, output_wav, speed_clamped)
            samples = self._normalize_audio(samples)
            sf.write(str(output_wav), samples, sample_rate, subtype="PCM_16")
            duration = float(len(samples)) / float(sample_rate)
            return output_wav, round(duration, 3), int(sample_rate)

        raise TTSError(
            "Nenhum motor local de TTS instalado (Kokoro ONNX ou Piper). "
            "Clique em 'Baixar Modelos Locais (Kokoro + Whisper)' ou execute install.bat."
        )

    def synthesize_storyboard_narration(
        self,
        storyboard: StoryboardDocument,
        audio_dir: Path,
        voice: str = "pm_alex",
        base_speed: float = 1.05,
        auto_download_if_missing: bool = False,
    ) -> Tuple[Path, List[Dict[str, float | int]]]:
        """
        Sintetiza a narração cena a cena com variação emocional de ritmo, salva cada cena
        e gera `audio/narration.wav` unificado + lista exata de tempos por cena para sincronia perfeita.
        """
        audio_dir.mkdir(parents=True, exist_ok=True)
        chunks: List[np.ndarray] = []
        timings: List[Dict[str, float | int]] = []
        sample_rate = int(self.settings["tts"].get("sample_rate", 24000))
        cursor = 0.0

        for idx, scene in enumerate(storyboard.scenes):
            factor = EXPRESSION_SPEED_FACTOR.get(scene.expression, 1.0)
            scene_speed = max(0.8, min(1.38, base_speed * factor))
            scene_wav = audio_dir / f"scene_{scene.scene_number:02d}_voice.wav"

            _, dur, sr = self.synthesize_text(
                text=scene.narration_pt,
                output_wav=scene_wav,
                voice=voice,
                speed=scene_speed,
                auto_download_if_missing=auto_download_if_missing,
            )
            sample_rate = sr
            data, _ = sf.read(str(scene_wav), dtype="float32")
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            # Pequena pausa dramática entre cenas (maior antes da reviravolta)
            pause_sec = 0.28 if scene.story_beat in ("Clímax", "Reviravolta") else 0.16
            if idx == len(storyboard.scenes) - 1:
                pause_sec = 0.35
            pause_samples = np.zeros(int(sample_rate * pause_sec), dtype=np.float32)

            start_t = cursor
            end_t = cursor + (len(data) + len(pause_samples)) / float(sample_rate)
            timings.append(
                {
                    "scene_number": scene.scene_number,
                    "start": round(start_t, 3),
                    "end": round(end_t, 3),
                    "duration": round(end_t - start_t, 3),
                    "speech_duration": round(dur, 3),
                }
            )
            # Atualiza duração real da cena no storyboard para corte exato na edição
            scene.duration_seconds = round(max(2.5, end_t - start_t), 2)

            chunks.append(data.astype(np.float32))
            chunks.append(pause_samples)
            cursor = end_t

        full_audio = np.concatenate(chunks) if chunks else np.zeros(sample_rate, dtype=np.float32)
        full_audio = self._normalize_audio(full_audio, peak_target=0.90)
        final_wav = audio_dir / "narration.wav"
        sf.write(str(final_wav), full_audio, sample_rate, subtype="PCM_16")
        return final_wav, timings
