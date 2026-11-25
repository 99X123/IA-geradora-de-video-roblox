"""AutoShorts AI — Dynamic Word-by-Word Subtitle Chunker & SRT Generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import AutoShortsConfig
from src.utils import setup_logger

logger = setup_logger("autoshorts.subtitles")


def format_srt_timestamp(seconds: float) -> str:
    """Convert float seconds into standard SRT `HH:MM:SS,mmm` format."""
    ms_total = max(0, int(round(seconds * 1000.0)))
    hours = ms_total // 3_600_000
    ms_total %= 3_600_000
    minutes = ms_total // 60_000
    ms_total %= 60_000
    secs = ms_total // 1000
    millis = ms_total % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_caption_chunks(
    aligned_words: List[Dict[str, Any]],
    max_words_per_chunk: int = 3,
    max_chars_per_chunk: int = 24,
) -> List[Dict[str, Any]]:
    """Group aligned words into snappy vertical caption chunks (up to 3 words, single speaker)."""
    chunks: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []

    def flush() -> None:
        if not cur:
            return
        chunks.append(
            {
                "speaker": cur[0].get("speaker", "N"),
                "start": round(float(cur[0]["start"]), 4),
                "end": round(float(cur[-1]["end"]), 4),
                "text": " ".join(w["word"] for w in cur),
                "words": [
                    {
                        "word": w["word"],
                        "start": round(float(w["start"]), 4),
                        "end": round(float(w["end"]), 4),
                    }
                    for w in cur
                ],
            }
        )
        cur.clear()

    for w in aligned_words:
        word_text = str(w.get("word", "")).strip()
        if not word_text:
            continue
        spk = w.get("speaker", "N")

        if cur:
            prev = cur[-1]
            same_speaker = prev.get("speaker", "N") == spk
            same_line = prev.get("line_index") == w.get("line_index")
            gap = float(w["start"]) - float(prev["end"])
            next_chars = sum(len(x["word"]) for x in cur) + len(word_text) + len(cur)
            prev_ends_sentence = prev["word"][-1:] in ".!?"

            if (
                not same_speaker
                or not same_line
                or len(cur) >= max_words_per_chunk
                or next_chars > max_chars_per_chunk
                or gap > 0.35
                or prev_ends_sentence
            ):
                flush()

        cur.append(w)

    flush()

    # Ensure strictly monotonic non-overlapping chunk times
    for i in range(1, len(chunks)):
        if chunks[i]["start"] < chunks[i - 1]["end"]:
            chunks[i - 1]["end"] = chunks[i]["start"]

    return chunks


def write_srt(chunks: List[Dict[str, Any]], srt_path: Path) -> Path:
    """Write standard UTF-8 SubRip (.srt) file from caption chunks."""
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    for idx, ch in enumerate(chunks, start=1):
        start_ts = format_srt_timestamp(ch["start"])
        end_ts = format_srt_timestamp(max(ch["start"] + 0.08, ch["end"]))
        blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{ch['text']}\n")
    srt_path.write_text("\n".join(blocks), encoding="utf-8")
    return srt_path


def generate_subtitles(
    sync_data: Dict[str, Any],
    out_dir: Path,
    config: Optional[AutoShortsConfig] = None,
) -> Dict[str, Any]:
    """Build dynamic caption chunks, update `sync_data.json`, write `data.js` and `subtitles.srt`."""
    cfg = config or AutoShortsConfig.load()
    max_words = int(cfg.get("subtitles.max_words_per_chunk", 3))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = build_caption_chunks(sync_data.get("words", []), max_words_per_chunk=max_words)
    sync_data["chunks"] = chunks

    srt_path = write_srt(chunks, out_dir / "subtitles.srt")
    sync_json_path = out_dir / "sync_data.json"
    sync_json_path.write_text(json.dumps(sync_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also export SKILL.md-compatible ES module data.js for direct browser use if needed
    data_js_path = out_dir / "data.js"
    js_content = (
        f"export const CHUNKS = {json.dumps(chunks, ensure_ascii=False)};\n"
        f"export const ENV = {json.dumps(sync_data.get('env', []))};\n"
        f"export const LINES = {json.dumps(sync_data.get('lines', []), ensure_ascii=False)};\n"
    )
    data_js_path.write_text(js_content, encoding="utf-8")

    last_sub_end = chunks[-1]["end"] if chunks else 0.0
    logger.info("Legendas geradas: %d blocos, último fim em %.2fs -> %s", len(chunks), last_sub_end, srt_path)

    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "srt_path": str(srt_path),
        "sync_json_path": str(sync_json_path),
        "data_js_path": str(data_js_path),
        "last_subtitle_end_sec": round(last_sub_end, 4),
    }
