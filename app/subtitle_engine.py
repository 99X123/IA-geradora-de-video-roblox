"""Motor de legendas automáticas locais usando Whisper (faster-whisper) com timestamps reais do áudio."""

from __future__ import annotations

import logging
import math
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from app.config import load_settings, resolve_path

logger = logging.getLogger("roblox_ai_shorts_studio")


@dataclass
class WordTiming:
    text: str
    start: float
    end: float


@dataclass
class SubtitleChunk:
    index: int
    start: float
    end: float
    words: List[WordTiming]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()


def _format_srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hrs = ms_total // 3_600_000
    mins = (ms_total % 3_600_000) // 60_000
    secs = (ms_total % 60_000) // 1000
    ms = ms_total % 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    cs_total = max(0, int(round(seconds * 100)))
    hrs = cs_total // 360_000
    mins = (cs_total % 360_000) // 6000
    secs = (cs_total % 6000) // 100
    cs = cs_total % 100
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


class WhisperSubtitleEngine:
    """
    Transcreve o áudio real de narração localmente com faster-whisper (MIT / 100% offline após cache)
    e produz arquivos SRT e ASS estilizados para YouTube Shorts e TikTok (9:16).
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        self.settings = settings or load_settings()
        configured_dir = resolve_path(self.settings["paths"]["models_dir"]) / "whisper"
        # Google Drive FUSE (/content/drive) nao suporta symlinks do HuggingFace Hub,
        # fazendo model.bin virar texto "../../blobs/..." (erro CTranslate2 binary version v774843950).
        # No Colab, usamos o SSD local rapido para o cache do Whisper (baixa ~145 MB em ~2s sem corromper).
        if self._is_google_drive_fuse(configured_dir):
            self.models_dir = Path(tempfile.gettempdir()) / "roblox_ai_shorts_whisper_cache"
        else:
            self.models_dir = configured_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._model_cache: Dict[str, Any] = {}

    @staticmethod
    def _is_google_drive_fuse(path: Path) -> bool:
        norm = path.as_posix().lower()
        return norm.startswith("/content/drive/") or "/gdrive/" in norm

    @staticmethod
    def _is_valid_model_bin(bin_file: Path) -> bool:
        """Verifica se model.bin é um binário CTranslate2 válido (e não um symlink quebrado '../../blobs/...')."""
        try:
            if not bin_file.exists() or bin_file.stat().st_size < 1_000_000:
                return False
            with bin_file.open("rb") as fh:
                head = fh.read(16)
            # Symlink gravado como texto puro no Drive FUSE ou ponteiro Git LFS
            if head.startswith((b"../", b"..\\", b"version https://")):
                return False
            # Versão binária CTranslate2 (uint32 little-endian) deve ser razoável (1..100)
            if len(head) >= 4:
                ver = int.from_bytes(head[:4], byteorder="little", signed=False)
                if ver == 0 or ver > 100:
                    return False
            return True
        except Exception:
            return False

    def _purge_corrupted_whisper_cache(self) -> None:
        """Remove caches corrompidos de model.bin para forçar um download limpo."""
        if not self.models_dir.exists():
            return
        for bin_file in list(self.models_dir.rglob("model.bin")):
            if not self._is_valid_model_bin(bin_file):
                # Remove a pasta inteira do modelo HuggingFace corrompido (models--Systran--*)
                target = bin_file.parent
                while target.parent != self.models_dir and target != self.models_dir:
                    if target.name.startswith("models--"):
                        break
                    target = target.parent
                shutil.rmtree(target, ignore_errors=True)

    def is_model_cached(self, model_size: Optional[str] = None) -> bool:
        size = model_size or self.settings["subtitles"].get("whisper_model", "base")
        if not self.models_dir.exists():
            return False
        for bin_file in self.models_dir.rglob("model.bin"):
            if size in str(bin_file.parent).lower() or size in str(bin_file.parent.parent).lower():
                if self._is_valid_model_bin(bin_file):
                    return True
        return False

    @staticmethod
    def _detect_whisper_device_and_compute(device_cfg: str, compute_cfg: str) -> Tuple[str, str]:
        """Usa GPU CUDA (float16/int8_float16) automaticamente no Google Colab/NVIDIA e CPU int8 nos demais."""
        if device_cfg != "auto":
            return device_cfg, compute_cfg
        try:
            import ctranslate2  # type: ignore

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "float16"
        except Exception:
            pass
        return "cpu", compute_cfg

    def _load_model(self, model_size: Optional[str] = None, local_files_only: bool = False) -> Any:
        from faster_whisper import WhisperModel  # type: ignore

        self._purge_corrupted_whisper_cache()

        size = model_size or self.settings["subtitles"].get("whisper_model", "base")
        compute_cfg = self.settings["subtitles"].get("whisper_compute_type", "int8")
        device_cfg = self.settings["subtitles"].get("whisper_device", "auto")
        device, compute_type = self._detect_whisper_device_and_compute(device_cfg, compute_cfg)

        cache_key = f"{size}:{device}:{compute_type}:{local_files_only}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        def _instantiate(dev: str, ctype: str, root_dir: Path, local_only: bool) -> Any:
            return WhisperModel(
                size,
                device=dev,
                compute_type=ctype,
                download_root=str(root_dir),
                local_files_only=local_only,
            )

        try:
            model = _instantiate(device, compute_type, self.models_dir, local_files_only)
        except Exception as exc:
            err_msg = str(exc).lower()
            # Recuperação automática se o cache tiver sido corrompido (ex.: symlink quebrado / binary version inválida)
            if ("binary version" in err_msg or "failed to open" in err_msg or "corrupt" in err_msg) and not local_files_only:
                logger.warning("Cache Whisper corrompido detectado (%s). Recriando em pasta local limpa...", exc)
                self.models_dir = Path(tempfile.gettempdir()) / "roblox_ai_shorts_whisper_cache"
                shutil.rmtree(self.models_dir, ignore_errors=True)
                self.models_dir.mkdir(parents=True, exist_ok=True)
                try:
                    model = _instantiate(device, compute_type, self.models_dir, False)
                except Exception:
                    device, compute_type = "cpu", "int8"
                    model = _instantiate(device, compute_type, self.models_dir, False)
            elif device != "cpu":
                # Fallback seguro se CUDA/cuDNN estiver indisponível no container
                device, compute_type = "cpu", "int8"
                cache_key = f"{size}:{device}:{compute_type}:{local_files_only}"
                if cache_key in self._model_cache:
                    return self._model_cache[cache_key]
                model = _instantiate(device, compute_type, self.models_dir, local_files_only)
            else:
                raise

        cache_key = f"{size}:{device}:{compute_type}:{local_files_only}"
        self._model_cache[cache_key] = model
        return model

    def ensure_model_downloaded(self, model_size: Optional[str] = None) -> str:
        size = model_size or self.settings["subtitles"].get("whisper_model", "base")
        self._load_model(model_size=size, local_files_only=False)
        return size

    @staticmethod
    def _load_audio_16k_mono(audio_wav: Path) -> np.ndarray:
        """Carrega o WAV real em float32 mono 16 kHz (compatível com PyAV 19+ e faster-whisper)."""
        data, sr = sf.read(str(audio_wav), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1).astype(np.float32)
        if sr != 16000:
            g = math.gcd(int(sr), 16000)
            up = 16000 // g
            down = int(sr) // g
            data = resample_poly(data, up, down).astype(np.float32)
        return np.ascontiguousarray(data, dtype=np.float32)

    def transcribe_audio(
        self,
        audio_wav: Path,
        model_size: Optional[str] = None,
        offline_only: bool = False,
        initial_prompt: Optional[str] = None,
    ) -> List[WordTiming]:
        """Obtém timestamps reais palavra-por-palavra diretamente do áudio via Whisper local."""
        if not audio_wav.exists():
            raise FileNotFoundError(f"Áudio para legendas não encontrado: {audio_wav}")

        # Em modo offline estrito ou quando já existe cache, carrega localmente sem acessar internet
        use_local = offline_only or self.is_model_cached(model_size)
        try:
            model = self._load_model(model_size=model_size, local_files_only=use_local)
        except Exception:
            if offline_only:
                raise
            model = self._load_model(model_size=model_size, local_files_only=False)

        audio_16k = self._load_audio_16k_mono(audio_wav)
        lang = self.settings["subtitles"].get("language", "pt")
        segments, _info = model.transcribe(
            audio_16k,
            language=lang,
            word_timestamps=True,
            vad_filter=True,
            beam_size=3,
            initial_prompt=initial_prompt[:400] if initial_prompt else None,
        )

        words: List[WordTiming] = []
        for seg in segments:
            seg_words = getattr(seg, "words", None)
            if seg_words:
                for w in seg_words:
                    token = (w.word or "").strip()
                    if not token:
                        continue
                    start = max(0.0, float(w.start))
                    end = max(start + 0.06, float(w.end))
                    words.append(WordTiming(text=token, start=start, end=end))
            else:
                # Se um segmento raro não tiver word-level, divide proporcionalmente no intervalo REAL do segmento
                tokens = (seg.text or "").strip().split()
                if not tokens:
                    continue
                seg_dur = max(0.2, float(seg.end) - float(seg.start))
                step = seg_dur / len(tokens)
                for i, tok in enumerate(tokens):
                    words.append(
                        WordTiming(
                            text=tok,
                            start=float(seg.start) + i * step,
                            end=float(seg.start) + (i + 1) * step,
                        )
                    )

        # Corrige eventuais sobreposições de milissegundos mantendo ordem cronológica estrita
        for i in range(1, len(words)):
            if words[i].start < words[i - 1].end:
                words[i].start = words[i - 1].end
            if words[i].end <= words[i].start:
                words[i].end = words[i].start + 0.08

        return words

    def group_words_into_chunks(
        self,
        words: List[WordTiming],
        max_words: int = 4,
        max_chars: int = 26,
    ) -> List[SubtitleChunk]:
        """Agrupa palavras em blocos curtos e legíveis para vídeos verticais 9:16."""
        chunks: List[SubtitleChunk] = []
        buf: List[WordTiming] = []

        def flush() -> None:
            if not buf:
                return
            chunks.append(
                SubtitleChunk(
                    index=len(chunks) + 1,
                    start=buf[0].start,
                    end=max(buf[-1].end, buf[0].start + 0.25),
                    words=list(buf),
                )
            )
            buf.clear()

        for w in words:
            projected_len = len(" ".join(x.text for x in buf + [w]))
            big_gap = bool(buf and (w.start - buf[-1].end) > 0.45)
            ends_sentence = bool(buf and buf[-1].text.endswith((".", "!", "?", ";")))
            if buf and (len(buf) >= max_words or projected_len > max_chars or big_gap or ends_sentence):
                flush()
            buf.append(w)
        flush()
        return chunks

    def write_srt(self, chunks: List[SubtitleChunk], dest_srt: Path) -> Path:
        lines: List[str] = []
        for ch in chunks:
            lines.append(str(ch.index))
            lines.append(f"{_format_srt_time(ch.start)} --> {_format_srt_time(ch.end)}")
            lines.append(ch.text)
            lines.append("")
        dest_srt.parent.mkdir(parents=True, exist_ok=True)
        dest_srt.write_text("\n".join(lines), encoding="utf-8")
        return dest_srt

    @staticmethod
    def _resolve_ass_font_name(configured_font: str) -> str:
        """No Linux/Colab, substitui Arial Black por uma fonte bold garantida se não estiver instalada."""
        if platform.system() != "Linux":
            return configured_font
        if shutil.which("fc-list"):
            try:
                out = subprocess.check_output(["fc-list", ":family"], text=True, timeout=3, stderr=subprocess.DEVNULL)
                families = {line.strip().lower() for line in out.splitlines() if line.strip()}
                if configured_font.lower() in families:
                    return configured_font
                for fallback in ("DejaVu Sans", "Liberation Sans", "Noto Sans", "FreeSans"):
                    if fallback.lower() in families:
                        return fallback
            except Exception:
                pass
        return "DejaVu Sans"

    def write_ass(self, chunks: List[SubtitleChunk], dest_ass: Path) -> Path:
        """
        Gera arquivo ASS vertical 1080x1920 com letras grandes brancas, contorno escuro forte,
        animação pop-in e destaque dinâmico palavra por palavra em amarelo ouro.
        """
        sub_cfg = self.settings["subtitles"]
        font_name = self._resolve_ass_font_name(sub_cfg.get("font_name", "Arial Black"))
        font_size = int(sub_cfg.get("font_size", 74))
        margin_v = int(sub_cfg.get("margin_v", 340))
        primary = sub_cfg.get("primary_color_ass", "&H00FFFFFF&")
        highlight = sub_cfg.get("highlight_color_ass", "&H0000D7FF&")
        outline = sub_cfg.get("outline_color_ass", "&H00000000&")

        header = f"""[Script Info]
Title: Roblox AI Shorts Studio Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ShortsMain,{font_name},{font_size},{primary},{highlight},{outline},&H90000000&,1,0,0,0,100,100,0,0,1,6,3,2,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []
        for chunk in chunks:
            # Gera um evento por palavra ativa dentro do bloco para destaque nítido + pop-in na entrada do bloco
            for w_idx, active_word in enumerate(chunk.words):
                ev_start = active_word.start
                ev_end = chunk.words[w_idx + 1].start if (w_idx + 1) < len(chunk.words) else chunk.end
                ev_end = max(ev_start + 0.05, ev_end)

                styled_tokens: List[str] = []
                for j, token in enumerate(chunk.words):
                    upper_txt = _escape_ass(token.text.upper())
                    if j == w_idx:
                        styled_tokens.append(f"{{\\c{highlight}\\fscx108\\fscy108}}{upper_txt}{{\\rShortsMain}}")
                    else:
                        styled_tokens.append(upper_txt)

                pop_anim = (
                    "{\\fscx90\\fscy90\\t(0,80,\\fscx103\\fscy103)\\t(80,150,\\fscx100\\fscy100)}"
                    if w_idx == 0
                    else ""
                )
                line_text = pop_anim + " ".join(styled_tokens)
                events.append(
                    f"Dialogue: 0,{_format_ass_time(ev_start)},{_format_ass_time(ev_end)},ShortsMain,,0,0,0,,{line_text}"
                )

        dest_ass.parent.mkdir(parents=True, exist_ok=True)
        dest_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        return dest_ass

    def generate_subtitles(
        self,
        audio_wav: Path,
        subtitles_dir: Path,
        script_hint: Optional[str] = None,
        model_size: Optional[str] = None,
        offline_only: bool = False,
    ) -> Tuple[Path, Path, List[SubtitleChunk]]:
        """Executa transcrição Whisper real no áudio e grava SRT + ASS."""
        words = self.transcribe_audio(
            audio_wav=audio_wav,
            model_size=model_size,
            offline_only=offline_only,
            initial_prompt=script_hint,
        )
        if not words:
            raise RuntimeError("Whisper não detectou fala no arquivo de narração.")

        max_words = int(self.settings["subtitles"].get("max_words_per_line", 4))
        chunks = self.group_words_into_chunks(words, max_words=max_words)
        srt_path = self.write_srt(chunks, subtitles_dir / "captions.srt")
        ass_path = self.write_ass(chunks, subtitles_dir / "captions.ass")
        return srt_path, ass_path, chunks
