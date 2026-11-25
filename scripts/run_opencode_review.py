#!/usr/bin/env python3
"""CLI entry point to trigger an independent OpenCode code review & test run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import AutoShortsConfig
from src.opencode_reviewer import OpenCodeReviewer


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoShorts AI — Revisão Independente de Código via OpenCode CLI")
    parser.add_argument("--model", default=None, help="Modelo OpenCode no formato provider/model (ver `opencode models`)")
    parser.add_argument("--files", nargs="*", default=None, help="Lista opcional de arquivos específicos para revisar")
    parser.add_argument("--timeout", type=int, default=None, help="Timeout em segundos para o OpenCode CLI")
    parser.add_argument("--allow-edits", action="store_true", help="Permitir que o OpenCode aplique correções seguras")
    parser.add_argument("--report", default="logs/opencode_review_report.json", help="Caminho do relatório JSON")
    args = parser.parse_args()

    oc_overrides: dict = {}
    if args.model:
        oc_overrides["model"] = args.model
    if args.timeout:
        oc_overrides["timeout_sec"] = args.timeout
    overrides = {"opencode": oc_overrides} if oc_overrides else None
    cfg = AutoShortsConfig.load(overrides=overrides)
    reviewer = OpenCodeReviewer(config=cfg)
    report = reviewer.review_project(
        target_files=args.files,
        allow_edits=args.allow_edits,
        report_path=PROJECT_ROOT / args.report,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
