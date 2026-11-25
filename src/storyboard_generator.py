"""AutoShorts AI — Cinematic Shot Planner & Visual Storyboard Generator."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from src.config import AutoShortsConfig, PROJECT_ROOT
from src.utils import find_node, run_subprocess, setup_logger

logger = setup_logger("autoshorts.storyboard")

# Cinematic move catalog categorized by angle family so consecutive shots NEVER repeat angles
MOVE_CATALOG: List[Dict[str, Any]] = [
    {"move": "pushIn", "family": "front_eye", "yaw_side": "front", "framing": "body"},
    {"move": "orbit", "family": "side_orbit", "yaw_side": "left", "framing": "body"},
    {"move": "lowHero", "family": "low_angle", "yaw_side": "right", "framing": "body"},
    {"move": "craneUp", "family": "crane_rise", "yaw_side": "left", "framing": "body"},
    {"move": "pullOut", "family": "wide_pull", "yaw_side": "right", "framing": "body"},
    {"move": "arc", "family": "arc_sweep", "yaw_side": "left", "framing": "body"},
    {"move": "highDefeat", "family": "high_angle", "yaw_side": "right", "framing": "body"},
    {"move": "dolly", "family": "dolly_slide", "yaw_side": "front", "framing": "body"},
    {"move": "craneDown", "family": "crane_drop", "yaw_side": "right", "framing": "body"},
    {"move": "revealBehind", "family": "behind", "yaw_side": "back", "framing": "body"},
    {"move": "topDown", "family": "top_down", "yaw_side": "top", "framing": "body"},
    {"move": "dutchPanic", "family": "dutch_roll", "yaw_side": "left", "framing": "head"},
    {"move": "vertigo", "family": "vertigo", "yaw_side": "front", "framing": "head"},
    {"move": "track", "family": "track", "yaw_side": "left", "framing": "body"},
    {"move": "pan", "family": "pan", "yaw_side": "right", "framing": "body"},
]


def _pick_camera_for_beat(
    beat_type: str,
    emotion: str,
    action: str,
    shot_idx: int,
    prev_family: Optional[str],
    prev_side: Optional[str],
    is_split_reaction: bool = False,
) -> Dict[str, Any]:
    """Select a dynamic camera move tailored to emotion/beat without repeating prior angle."""
    preferred: List[str]
    if is_split_reaction:
        preferred = ["pushIn", "dutchPanic", "vertigo", "arc", "highDefeat"]
    elif beat_type == "hook":
        preferred = ["pushIn", "lowHero", "vertigo"]
    elif beat_type == "twist":
        preferred = ["pullOut", "highDefeat", "topDown", "vertigo"]
    elif emotion in ("panic", "shock") or action in ("panic", "shock"):
        preferred = ["dutchPanic", "vertigo", "craneUp", "arc"]
    elif action in ("run", "walk"):
        preferred = ["track", "dolly", "orbit"]
    elif emotion in ("sad", "deadpan") or action == "defeat":
        preferred = ["highDefeat", "topDown", "pullOut"]
    elif beat_type in ("climax",) or action == "celebrate":
        preferred = ["orbit", "craneUp", "lowHero"]
    elif beat_type == "turning_point":
        preferred = ["revealBehind", "craneDown", "dutchPanic", "orbit"]
    else:
        preferred = ["dolly", "arc", "craneDown", "orbit", "pushIn", "pan", "lowHero"]

    by_name = {m["move"]: m for m in MOVE_CATALOG}
    candidates = [by_name[name] for name in preferred if name in by_name] + MOVE_CATALOG

    chosen = None
    for cand in candidates:
        if cand["family"] != prev_family and cand["yaw_side"] != prev_side:
            chosen = cand
            break
    if chosen is None:
        for cand in MOVE_CATALOG:
            if cand["family"] != prev_family:
                chosen = cand
                break
    chosen = chosen or MOVE_CATALOG[shot_idx % len(MOVE_CATALOG)]

    # Alternate yaw sign gently for variety while keeping clear sightlines
    side_sign = -1 if shot_idx % 2 == 0 else 1
    framing = "head" if (is_split_reaction or chosen["framing"] == "head") else "body"

    cam: Dict[str, Any] = {
        "move": chosen["move"],
        "family": chosen["family"],
        "yaw_side": chosen["yaw_side"],
        "framing": framing,
        "zoom": 1.12 if framing == "head" else 1.2,
    }

    if chosen["move"] in ("orbit", "arc", "dolly"):
        cam["yaw0"] = round(side_sign * 0.48, 3)
        cam["yaw1"] = round(-side_sign * 0.42, 3)
    elif chosen["move"] == "pushIn":
        cam["yaw0"] = round(side_sign * 0.22, 3)
        cam["yaw1"] = round(-side_sign * 0.06, 3)
        cam["zoom0"] = 1.42
        cam["zoom1"] = 1.06
    elif chosen["move"] == "pullOut":
        cam["yaw0"] = round(-side_sign * 0.14, 3)
        cam["yaw1"] = round(side_sign * 0.28, 3)
        cam["zoom0"] = 1.06
        cam["zoom1"] = 1.48
    elif chosen["move"] == "lowHero":
        cam["yaw0"] = round(side_sign * 0.35, 3)
        cam["yaw1"] = round(-side_sign * 0.22, 3)

    return cam


def _stage_characters(
    characters: List[Dict[str, Any]],
    speaker_code: str,
    action: str,
    emotion: str,
    shot_idx: int,
    framing: str,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Depth-stage characters for narrow 9:16 vertical framing (never cramped side-by-side)."""
    placements: List[Dict[str, Any]] = []
    speaker_char = next((c for c in characters if c["speaker_code"] == speaker_code), characters[0])
    others = [c for c in characters if c["id"] != speaker_char["id"]]

    # Primary speaker centered slightly forward
    primary_pl: Dict[str, Any] = {
        "id": speaker_char["id"],
        "x": -0.35 if (len(others) > 0 and framing != "head") else 0.0,
        "y": 0.0,
        "z": 0.85,
        "ry": 0.18 if len(others) > 0 else 0.0,
        "action": action,
        "emotion": emotion,
        "lip_sync": speaker_code != "N",
    }
    if action in ("walk", "run"):
        primary_pl["x"] = -1.6
        primary_pl["x1"] = 1.4
        primary_pl["ry"] = 1.25

    placements.append(primary_pl)

    # Depth staging for co-star & secondary characters (placed behind & offset so 9:16 reads cleanly)
    reaction_emotion = "shock" if emotion in ("panic", "angry") else ("smug" if speaker_code == "N" else "confused")
    for idx, ch in enumerate(others):
        side = 1 if (idx + shot_idx) % 2 == 0 else -1
        placements.append(
            {
                "id": ch["id"],
                "x": round(side * (1.25 + idx * 0.45), 2),
                "y": 0.0,
                "z": round(-0.75 - idx * 0.65, 2),
                "ry": round(-side * 0.35, 2),
                "action": "idle" if action != "celebrate" else "celebrate",
                "emotion": reaction_emotion,
                "lip_sync": False,
            }
        )

    focus_ids = [speaker_char["id"]] if framing == "head" else [p["id"] for p in placements[:2]]
    return placements, focus_ids


def build_storyboard(
    story: Dict[str, Any],
    aligned_lines: List[Dict[str, Any]],
    total_duration_sec: float,
    config: Optional[AutoShortsConfig] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate a complete deterministic shot timeline synchronized to aligned voice timestamps."""
    cfg = config or AutoShortsConfig.load()
    max_shot_dur = float(cfg.get("story.max_shot_duration_sec", 4.5))
    # Target ~22-26 shots/min -> keep individual shots snappy (~1.8s to 3.4s when splitting long lines)
    ideal_split_threshold = min(max_shot_dur, 3.2)

    story_lines = story["lines"]
    characters = story["characters"]
    shots: List[Dict[str, Any]] = []

    prev_family: Optional[str] = None
    prev_side: Optional[str] = None
    cut_lead = 0.05

    for idx, aligned in enumerate(aligned_lines):
        meta = story_lines[min(idx, len(story_lines) - 1)]
        t0 = max(0.0, float(aligned["start"]) - (cut_lead if idx > 0 else 0.0))
        if idx + 1 < len(aligned_lines):
            t1 = max(t0 + 0.4, float(aligned_lines[idx + 1]["start"]) - cut_lead)
        else:
            t1 = max(t0 + 0.6, float(total_duration_sec))

        span = t1 - t0
        # Split longer lines into 2 dynamic shots to hit 18-30 shots/min pacing
        n_sub = max(1, int(math.ceil(span / ideal_split_threshold)))
        if span / n_sub < 1.15 and n_sub > 1:
            n_sub -= 1

        for sub in range(n_sub):
            st0 = round(t0 + (span * sub) / n_sub, 4)
            st1 = round(t0 + (span * (sub + 1)) / n_sub, 4)
            if shots and st0 < shots[-1]["end"]:
                st0 = shots[-1]["end"]
            if st1 <= st0 + 0.15:
                st1 = round(st0 + 0.2, 4)

            is_reaction = sub > 0
            cam = _pick_camera_for_beat(
                beat_type=meta.get("beat_type", "setup"),
                emotion=meta.get("emotion", "neutral"),
                action=meta.get("action", "talk"),
                shot_idx=len(shots),
                prev_family=prev_family,
                prev_side=prev_side,
                is_split_reaction=is_reaction,
            )
            prev_family = cam["family"]
            prev_side = cam["yaw_side"]

            placements, focus_ids = _stage_characters(
                characters=characters,
                speaker_code=meta["speaker"],
                action=meta.get("action", "talk"),
                emotion=meta.get("emotion", "neutral"),
                shot_idx=len(shots),
                framing=cam["framing"],
            )

            props_list: List[Dict[str, Any]] = []
            if meta.get("prop"):
                props_list.append(
                    {
                        "name": meta["prop"],
                        "attach_to": placements[0]["id"] if meta.get("prop") not in ("box", "ice_block") else None,
                        "hand": "right",
                        "pos": [0.0, 0.0, 0.1] if meta.get("prop") not in ("box", "ice_block") else [0.8, 0.35, 0.6],
                        "rot": [0.0, 0.0, 0.0],
                        "scale": 1.0,
                        "focus": False,
                    }
                )

            fx: Dict[str, Any] = {"vignette": 0.22}
            if meta.get("emotion") in ("shock", "panic") or meta.get("beat_type") == "hook":
                fx["speed_lines"] = 0.55
            if meta.get("beat_type") in ("climax",) and meta.get("action") == "celebrate":
                fx["confetti"] = True
                fx["sparks"] = True
            if meta.get("sfx") in ("thunder", "bass_hit") and sub == 0:
                fx["flash"] = True
                fx["screen_shake"] = 0.45
            if meta.get("impact_text") and sub == 0:
                fx["impact_text"] = meta["impact_text"]

            set_state: Dict[str, Any] = {}
            if meta.get("set") == "entry_hall":
                set_state["doorOpen"] = 0.75
            elif meta.get("set") == "kitchen":
                set_state["fridgeOpen"] = 0.65

            shots.append(
                {
                    "shot_id": len(shots) + 1,
                    "line_index": idx,
                    "start": st0,
                    "end": st1,
                    "speaker": meta["speaker"],
                    "dialogue": meta["text"],
                    "beat_type": meta.get("beat_type", "setup"),
                    "set": meta.get("set", "town_square"),
                    "set_state": set_state,
                    "characters": placements,
                    "focus_ids": focus_ids,
                    "props": props_list,
                    "camera": cam,
                    "effects": fx,
                    "sfx": meta.get("sfx") if sub == 0 else None,
                }
            )

    # Ensure seamless coverage from 0.0 to total_duration_sec
    if shots:
        shots[0]["start"] = 0.0
        shots[-1]["end"] = round(float(total_duration_sec), 4)

    shots_per_min = round(len(shots) / max(0.05, total_duration_sec / 60.0), 1)
    storyboard: Dict[str, Any] = {
        "title": story["title"],
        "theme": story["theme"],
        "premise": story["premise"],
        "width": int(cfg.get("video.width", 1080)),
        "height": int(cfg.get("video.height", 1920)),
        "fps": int(cfg.get("video.fps", 30)),
        "duration_sec": round(float(total_duration_sec), 4),
        "jpeg_quality": float(cfg.get("video.jpeg_quality", 0.93)),
        "captions_enabled": True,
        "caption_style": {
            "fontSizePx": int(cfg.get("subtitles.font_size_px", 92)),
            "strokeWidthPx": int(cfg.get("subtitles.stroke_width_px", 18)),
            "strokeColor": cfg.get("subtitles.stroke_color", "#0B0D14"),
            "baseColor": cfg.get("subtitles.base_color", "#FFFFFF"),
            "speakerColors": cfg.get("subtitles.speaker_colors", {"N": "#FFE44D", "C": "#4DF0FF", "S": "#FF7AE6"}),
        },
        "visual": cfg.get("visual", {}),
        "characters": characters,
        "metrics": {
            "shot_count": len(shots),
            "shots_per_minute": shots_per_min,
            "max_shot_duration_sec": round(max((s["end"] - s["start"] for s in shots), default=0.0), 3),
        },
        "shots": shots,
    }

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8")

    return storyboard


def build_contact_sheet(image_paths: List[Path], output_path: Path, cols: int = 4, thumb_w: int = 270) -> Path:
    """Stitch rendered storyboard or QA frames into an annotated contact sheet PNG."""
    valid = [p for p in image_paths if p.exists()]
    if not valid:
        raise ValueError("Nenhuma imagem válida para gerar folha de contato.")

    with Image.open(valid[0]) as first:
        aspect = first.height / max(1, first.width)
    thumb_h = int(round(thumb_w * aspect))
    rows = math.ceil(len(valid) / cols)
    pad = 12
    sheet_w = cols * thumb_w + (cols + 1) * pad
    sheet_h = rows * thumb_h + (rows + 1) * pad

    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 20, 28))
    draw = ImageDraw.Draw(sheet)

    for idx, img_path in enumerate(valid):
        r = idx // cols
        c = idx % cols
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + pad)
        with Image.open(img_path) as im:
            resized = im.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(resized, (x, y))
        label = f"#{idx + 1:02d} {img_path.stem}"
        draw.rectangle([x, y, x + thumb_w, y + 26], fill=(10, 12, 18))
        draw.text((x + 8, y + 6), label[:32], fill=(255, 228, 77))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")
    return output_path


def render_visual_storyboard(
    storyboard_path: Path,
    sync_path: Optional[Path],
    out_dir: Path,
) -> Dict[str, Any]:
    """Render 1 mid-shot frame per shot via Chromium + build contact sheet & HTML review page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    node_bin = find_node()
    worker = PROJECT_ROOT / "engine" / "render_worker.mjs"
    cmd = [
        node_bin,
        str(worker),
        "board",
        "--storyboard",
        str(storyboard_path),
        "--out-dir",
        str(out_dir),
    ]
    if sync_path and sync_path.exists():
        cmd.extend(["--sync", str(sync_path)])

    run_subprocess(cmd, cwd=PROJECT_ROOT, timeout=300)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    sb = json.loads(storyboard_path.read_text(encoding="utf-8"))
    frame_paths = [Path(f["file"]) for f in manifest["frames"]]
    sheet_path = build_contact_sheet(frame_paths, out_dir / "storyboard_contact_sheet.png", cols=4)

    # Build HTML review page with each frame beside time range, voice-over line, action & camera move
    cards = []
    for idx, shot in enumerate(sb["shots"]):
        img_name = frame_paths[idx].name if idx < len(frame_paths) else ""
        overshoot = manifest["frames"][idx]["framing_overshoot"] if idx < len(manifest["frames"]) else 0.0
        cards.append(
            f"""
            <div class="card">
              <img src="{html.escape(img_name)}" alt="Shot {shot['shot_id']}" />
              <div class="meta">
                <h3>Tomada #{shot['shot_id']} ({shot['start']:.2f}s – {shot['end']:.2f}s)</h3>
                <p><strong>Personagem [{html.escape(shot['speaker'])}]:</strong> {html.escape(shot['dialogue'])}</p>
                <p><strong>Cenário:</strong> {html.escape(shot['set'])} | <strong>Câmera:</strong> {html.escape(shot['camera']['move'])} ({html.escape(shot['camera']['framing'])})</p>
                <p><strong>Enquadramento audit():</strong> {overshoot:.4f}</p>
              </div>
            </div>
            """
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<title>Storyboard — {html.escape(sb['title'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #10131d; color: #f0f4ff; padding: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }}
  .card {{ background: #1a2030; border-radius: 12px; overflow: hidden; border: 1px solid #2c3550; }}
  .card img {{ width: 100%; display: block; }}
  .meta {{ padding: 12px 14px; font-size: 14px; line-height: 1.45; }}
</style>
</head>
<body>
  <h1>Storyboard Visual — {html.escape(sb['title'])}</h1>
  <p>{html.escape(sb['premise'])} | {sb['metrics']['shot_count']} tomadas ({sb['metrics']['shots_per_minute']} tomadas/min)</p>
  <div class="grid">{''.join(cards)}</div>
</body>
</html>"""

    html_path = out_dir / "storyboard_review.html"
    html_path.write_text(html_doc, encoding="utf-8")

    return {
        "board_dir": str(out_dir),
        "contact_sheet": str(sheet_path),
        "review_html": str(html_path),
        "manifest": manifest,
    }
