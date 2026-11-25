#!/usr/bin/env python3
"""CLI entry point for end-to-end AutoShorts AI video production."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import AutoShortsConfig
from src.video_orchestrator import VideoOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoShorts AI — Fábrica Automatizada de Vídeos 3D Verticais")
    parser.add_argument("--theme", required=True, help="Tema ou título do vídeo curto")
    parser.add_argument("--script-file", default=None, help="Arquivo .txt com o SEU roteiro próprio (ex.: linhas N: / C:)")
    parser.add_argument("--script-text", default=None, help="Texto do SEU roteiro próprio diretamente pela linha de comando")
    parser.add_argument("--costar-rig", choices=["auto", "bot", "pigeon", "phantom", "rock", "human", "mech"], default="auto")
    parser.add_argument("--duration", type=float, default=None, help="Duração desejada em segundos (padrão: 60)")
    parser.add_argument("--quality", choices=["draft", "preview", "production", "ultra"], default=None)
    parser.add_argument("--tts-provider", default=None, help="auto | edge_tts | google_cloud | openai | local_synth_test")
    parser.add_argument("--story-provider", default=None, help="auto | gemini | openai | local_template")
    parser.add_argument("--workers", type=int, default=None, help="Número de workers paralelos do Chromium")
    parser.add_argument("--parts", type=int, default=None, help="Número de partes de renderização")
    parser.add_argument("--project-id", default=None, help="ID fixo do projeto (útil para retomar renderização)")
    parser.add_argument("--pause-storyboard", action="store_true", help="Pausar para aprovação visual do storyboard")
    parser.add_argument("--approved", action="store_true", help="Aprovar e continuar a partir do storyboard")
    parser.add_argument("--drive-sync", action="store_true", help="Sincronizar resultados finais no Google Drive")
    parser.add_argument("--drive-root", default=None, help="Pasta local opcional simulando raiz do Google Drive")
    parser.add_argument("--work-root", default=None, help="Pasta local de saída")
    args = parser.parse_args()

    overrides: dict = {"video": {}, "story": {}}
    if args.quality:
        overrides["video"]["quality_preset"] = args.quality
    if args.workers:
        overrides["video"]["workers"] = args.workers
    if args.parts:
        overrides["video"]["num_parts"] = args.parts
    if args.duration:
        overrides["video"]["target_duration_sec"] = args.duration

    custom_script = args.script_text
    if args.script_file:
        custom_script = Path(args.script_file).read_text(encoding="utf-8")

    cfg = AutoShortsConfig.load(overrides=overrides)
    orch = VideoOrchestrator(config=cfg, work_root=args.work_root)
    result = orch.produce(
        theme=args.theme,
        project_id=args.project_id,
        duration_sec=args.duration,
        tts_provider=args.tts_provider,
        story_provider=args.story_provider,
        custom_script=custom_script,
        costar_rig=args.costar_rig,
        require_storyboard_approval=args.pause_storyboard,
        approved=args.approved,
        enable_drive_sync=args.drive_sync,
        drive_root_override=args.drive_root,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in ("completed", "awaiting_storyboard_approval") else 1


if __name__ == "__main__":
    raise SystemExit(main())
