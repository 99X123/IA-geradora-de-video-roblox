"""Tests for Storyboard camera variety, Google Drive safe sync, and OpenCode reviewer guards."""

from __future__ import annotations

from pathlib import Path

from src.config import AutoShortsConfig
from src.drive_manager import DriveManager, REQUIRED_SUBFOLDERS, is_sensitive_file
from src.opencode_reviewer import OpenCodeReviewer
from src.story_generator import generate_story
from src.storyboard_generator import build_storyboard


def test_storyboard_non_repeating_camera_angles_and_pacing():
    cfg = AutoShortsConfig.load()
    story = generate_story("um relógio que atrasa o tempo da cidade", config=cfg, duration_sec=60, provider="local_template")

    # Simulated 60s aligned line intervals
    n = len(story["lines"])
    step = 59.5 / n
    aligned_lines = [
        {
            "index": i,
            "speaker": ln["speaker"],
            "character_id": ln["character_id"],
            "text": ln["text"],
            "start": round(i * step, 3),
            "end": round((i + 1) * step - 0.1, 3),
        }
        for i, ln in enumerate(story["lines"])
    ]

    sb = build_storyboard(story, aligned_lines, total_duration_sec=60.0, config=cfg)
    shots = sb["shots"]
    assert 18 <= len(shots) <= 38
    assert sb["metrics"]["max_shot_duration_sec"] <= 4.6

    # Consecutive shots must NEVER repeat the same camera angle family
    for i in range(1, len(shots)):
        assert shots[i]["camera"]["family"] != shots[i - 1]["camera"]["family"], (
            f"Tomadas consecutivas {i} e {i + 1} repetiram família de câmera!"
        )
        assert shots[i]["start"] >= shots[i - 1]["end"] - 0.01


def test_drive_manager_structure_and_credential_blocking(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-never-upload-99999")
    drive_root = tmp_path / "mock_drive"
    proj_dir = tmp_path / "local_project"
    proj_dir.mkdir(parents=True)

    # Normal project files + a forbidden credential file + a log containing a secret
    mp4 = proj_dir / "demo.mp4"
    mp4.write_bytes(b"fake-mp4-bytes")
    log_f = proj_dir / "production.log"
    log_f.write_text("Token leaked: sk-secret-value-never-upload-99999\n", encoding="utf-8")
    env_f = proj_dir / ".env"
    env_f.write_text("OPENAI_API_KEY=sk-secret-value-never-upload-99999\n", encoding="utf-8")
    cred_f = proj_dir / "service_account.json"
    cred_f.write_text('{"private_key": "secret"}', encoding="utf-8")

    assert is_sensitive_file(env_f) is True
    assert is_sensitive_file(cred_f) is True
    assert is_sensitive_file(mp4) is False

    dm = DriveManager(root_override=drive_root)
    base = dm.mount_if_colab()
    for folder in REQUIRED_SUBFOLDERS:
        assert (base / folder).is_dir()

    summary = dm.sync_project(
        project_id="demo_01",
        local_project_dir=proj_dir,
        deliverables={"video_mp4": mp4, "log_file": log_f},
    )
    assert (base / "Videos" / "demo_01.mp4").exists()
    assert not (base / "Projects" / "demo_01" / ".env").exists()
    assert not (base / "Projects" / "demo_01" / "service_account.json").exists()
    assert len(summary["blocked_sensitive_files"]) >= 2

    copied_log = (base / "Logs" / "demo_01.log").read_text(encoding="utf-8")
    assert "sk-secret-value-never-upload-99999" not in copied_log
    assert "<REDACTED:OPENAI_API_KEY>" in copied_log


def test_opencode_reviewer_never_fabricates_when_unconfigured(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    cfg = AutoShortsConfig.load(overrides={"opencode": {"model": "", "max_fix_cycles": 5}})
    reviewer = OpenCodeReviewer(config=cfg)
    # Hard safety cap at 3 cycles regardless of config
    assert reviewer.max_fix_cycles == 3

    # With no model configured, must NOT claim OpenCode verified anything
    status = reviewer.detect_cli()
    assert status["ready"] is False
    report = reviewer.diagnose_and_fix_failure(
        error_log="Sample error",
        relevant_files=["src/config.py"],
        verify_cmd=["python", "-c", "print('ok')"],
        report_path=tmp_path / "oc_report.json",
    )
    assert report["executed"] is False
    assert report["verified_by_opencode"] is False
    assert (tmp_path / "oc_report.json").exists()
