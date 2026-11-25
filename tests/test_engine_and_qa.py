"""Integration tests for Three.js WebGL probe, still rendering, and QA gate."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import AutoShortsConfig, PROJECT_ROOT
from src.quality_checker import run_quality_check
from src.story_generator import generate_story
from src.storyboard_generator import build_storyboard, render_visual_storyboard
from src.video_orchestrator import VideoOrchestrator, probe_render_environment


def test_webgl_environment_probe(tmp_path: Path):
    report = probe_render_environment(out_path=tmp_path / "probe.json")
    assert (tmp_path / "probe.json").exists()
    assert "chromium_webgl" in report
    webgl = report["chromium_webgl"]["webgl"]
    assert webgl["classification"] in ("gpu_hardware", "software_swiftshader", "software_other")
    # Truthfulness invariant: hardware_accelerated must be False whenever isSoftware is True
    if webgl["isSoftware"]:
        assert report["gpu_webgl_confirmed"] is False
    else:
        assert report["gpu_webgl_confirmed"] is True


def test_end_to_end_mini_render_and_qa_gate(tmp_path: Path):
    """Render a compact 5-second vertical 3D toon short end-to-end and verify EVERY QA gate."""
    cfg = AutoShortsConfig.load(
        overrides={
            "video": {
                "width": 540,
                "height": 960,
                "fps": 24,
                "num_parts": 2,
                "workers": 1,
                "crf": 22,
                "preset": "ultrafast",
                "target_duration_sec": 6,
            },
            "quality": {
                "enable_vision_review": False,
                "contact_sheet_interval_sec": 1.5,
            },
        }
    )

    orch = VideoOrchestrator(config=cfg, work_root=tmp_path / "work")
    result = orch.produce(
        theme="meu robô trocou o açúcar por glitter",
        project_id="test_mini_short",
        duration_sec=12,
        tts_provider="local_synth_test",
        story_provider="local_template",
        enable_drive_sync=True,
        drive_root_override=tmp_path / "drive",
    )

    assert result["status"] == "completed", f"QA falhou: {json.dumps(result['quality_report'], indent=2)}"
    assert result["approved"] is True
    mp4_path = Path(result["video_mp4"])
    assert mp4_path.exists() and mp4_path.stat().st_size > 10_000

    qa = result["quality_report"]
    assert qa["technical_passed"] is True
    assert qa["visual_algorithmic_passed"] is True
    assert Path(qa["visual_checks"]["contact_sheet"]).exists()
    assert result["drive_sync"]["files_copied_count"] > 0

    # Verify visual storyboard board render works too
    sb_path = Path(result["storyboard_path"])
    sync_path = Path(result["sync_json_path"])
    board = render_visual_storyboard(sb_path, sync_path, tmp_path / "board_check")
    assert Path(board["contact_sheet"]).exists()
    assert Path(board["review_html"]).exists()
    # Confirm framing audit overshoot is zero or negligible across all shots
    for fr in board["manifest"]["frames"]:
        assert fr["framing_overshoot"] <= 0.05, f"Enquadramento excedeu área segura em {fr}"
