"""AutoShorts AI — End-to-End Automated Video Production Orchestrator.

Takes a single theme (plus optional configuration overrides) and automates:
  1. Environment + real WebGL GPU vs SwiftShader probe
  2. Original PT-BR story, character & dialogue generation
  3. Multi-voice TTS synthesis
  4. Real forced audio alignment + 30fps lip-sync envelope
  5. Word-by-word dynamic subtitles + SRT
  6. Cinematic 3D storyboard planning (18-30 shots/min, non-repeating angles)
  7. Optional visual storyboard approval pause gate
  8. Procedural NumPy SFX + original background music + FFmpeg audio mix
  9. Resumable chunked Three.js/Playwright -> FFmpeg image2pipe MP4 rendering
 10. Technical + visual QA gate
 11. Automatic Google Drive delivery (when enabled)
 12. Optional OpenCode failure diagnosis hook (max 3 cycles)
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.audio_processor import align_audio_and_script
from src.config import AutoShortsConfig, PROJECT_ROOT
from src.drive_manager import DriveManager
from src.opencode_reviewer import OpenCodeReviewer
from src.quality_checker import run_quality_check
from src.sfx_synthesizer import mix_final_audio, synthesize_background_music, synthesize_sfx_track
from src.story_generator import generate_story
from src.storyboard_generator import build_storyboard, render_visual_storyboard
from src.subtitle_generator import generate_subtitles
from src.tts_engine import synthesize_story_audio
from src.utils import (
    detect_nvidia_gpu,
    find_ffmpeg,
    find_node,
    run_subprocess,
    setup_logger,
    slugify,
    timestamp_id,
)


def probe_render_environment(out_path: Optional[Path] = None) -> Dict[str, Any]:
    """Verify Node, FFmpeg, NVIDIA GPU, and REAL Chromium WebGL renderer (GPU vs SwiftShader)."""
    node_bin = find_node()
    ffmpeg_bin = find_ffmpeg()
    nvidia = detect_nvidia_gpu()

    worker = PROJECT_ROOT / "engine" / "render_worker.mjs"
    cmd = [node_bin, str(worker), "probe"]
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--out", str(out_path)])

    proc = run_subprocess(cmd, cwd=PROJECT_ROOT, timeout=60)
    # Extract JSON block from stdout
    stdout = proc.stdout
    json_start = stdout.find("{")
    webgl_probe = json.loads(stdout[json_start:]) if json_start != -1 else {"raw": stdout}

    env_report = {
        "node_binary": node_bin,
        "ffmpeg_binary": ffmpeg_bin,
        "nvidia_system_gpu": nvidia,
        "chromium_webgl": webgl_probe,
        "gpu_webgl_confirmed": bool(webgl_probe.get("hardware_accelerated")),
        "warning": (
            None
            if webgl_probe.get("hardware_accelerated")
            else "ATENÇÃO: WebGL do Chromium NÃO está acelerado por GPU (usando software/SwiftShader). "
            "A renderização funcionará em fallback seguro porém mais lenta."
        ),
    }
    if out_path is not None:
        out_path.write_text(json.dumps(env_report, indent=2, ensure_ascii=False), encoding="utf-8")
    return env_report


class VideoOrchestrator:
    """High-level controller for automated end-to-end AutoShorts AI production."""

    def __init__(
        self,
        config: Optional[AutoShortsConfig] = None,
        work_root: Optional[Path | str] = None,
    ) -> None:
        self.cfg = config or AutoShortsConfig.load()
        self.work_root = Path(work_root) if work_root else (PROJECT_ROOT / "output")
        self.work_root.mkdir(parents=True, exist_ok=True)

    def produce(
        self,
        theme: str,
        project_id: Optional[str] = None,
        duration_sec: Optional[float] = None,
        tts_provider: Optional[str] = None,
        story_provider: Optional[str] = None,
        require_storyboard_approval: Optional[bool] = None,
        approved: bool = False,
        enable_drive_sync: Optional[bool] = None,
        drive_root_override: Optional[Path | str] = None,
        run_opencode_on_error: bool = False,
    ) -> Dict[str, Any]:
        """Run the full video production factory from a single theme."""
        pid = project_id or f"{timestamp_id()}_{slugify(theme)}"
        proj_dir = self.work_root / pid
        proj_dir.mkdir(parents=True, exist_ok=True)
        log_file = proj_dir / "production.log"
        logger = setup_logger(f"autoshorts.run.{pid}", log_file=log_file)

        # Save credential-free snapshot of active config
        self.cfg.save_safe_snapshot(proj_dir / "config_snapshot.json")

        try:
            logger.info("=== INICIANDO PRODUÇÃO AUTOSHORTS AI: %s (tema='%s') ===", pid, theme)

            # 1. Environment & Real WebGL Probe
            env_probe = probe_render_environment(proj_dir / "environment_probe.json")
            webgl_meta = (env_probe.get("chromium_webgl") or {}).get("webgl") or {}
            logger.info(
                "WebGL Probe: hardware_accelerated=%s | renderer=%s",
                env_probe["gpu_webgl_confirmed"],
                webgl_meta.get("unmaskedRenderer") or webgl_meta.get("renderer"),
            )
            if env_probe["warning"]:
                logger.warning(env_probe["warning"])

            # 2. Story & Characters Generation (resume if already present)
            story_path = proj_dir / "story.json"
            if story_path.exists():
                story = json.loads(story_path.read_text(encoding="utf-8"))
                logger.info("Reaproveitando roteiro existente em cache: %s", story_path)
            else:
                story = generate_story(
                    theme=theme,
                    config=self.cfg,
                    duration_sec=duration_sec,
                    provider=story_provider,
                    output_path=story_path,
                )
            script_pairs_path = proj_dir / "script.json"
            script_pairs_path.write_text(
                json.dumps(story["script_pairs"], indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # 3. Multi-voice TTS Synthesis (resume if vo.wav & metadata exist)
            audio_dir = proj_dir / "audio"
            tts_meta_path = audio_dir / "tts_metadata.json"
            if tts_meta_path.exists() and (audio_dir / "vo.wav").exists():
                tts_meta = json.loads(tts_meta_path.read_text(encoding="utf-8"))
                logger.info("Reaproveitando áudios TTS em cache: %s", tts_meta_path)
            else:
                tts_meta = synthesize_story_audio(
                    story=story,
                    out_dir=audio_dir,
                    config=self.cfg,
                    provider_override=tts_provider,
                )

            # 4. Forced Word Alignment + Lip-Sync Envelope
            sync_data = align_audio_and_script(tts_meta, config=self.cfg, out_dir=proj_dir / "subtitles")

            # 5. Dynamic Word-by-Word Captions & SRT
            sub_info = generate_subtitles(sync_data, out_dir=proj_dir / "subtitles", config=self.cfg)
            sync_json_path = Path(sub_info["sync_json_path"])
            srt_path = Path(sub_info["srt_path"])

            # 6. Cinematic Storyboard (18-30 shots/min, non-repeating angles)
            storyboard_path = proj_dir / "storyboard.json"
            storyboard = build_storyboard(
                story=story,
                aligned_lines=sync_data["lines"],
                total_duration_sec=sync_data["duration_sec"],
                config=self.cfg,
                output_path=storyboard_path,
            )

            # 7. Optional Visual Storyboard Approval Gate
            pause_for_approval = (
                require_storyboard_approval
                if require_storyboard_approval is not None
                else bool(self.cfg.get("story.require_storyboard_approval", False))
            )
            board_info = None
            if pause_for_approval and not approved:
                logger.info("Gerando storyboard visual para aprovação manual antes da renderização completa...")
                board_info = render_visual_storyboard(storyboard_path, sync_json_path, proj_dir / "storyboard_preview")
                return {
                    "status": "awaiting_storyboard_approval",
                    "project_id": pid,
                    "project_dir": str(proj_dir),
                    "storyboard_path": str(storyboard_path),
                    "storyboard_preview": board_info,
                    "message": "Storyboard visual gerado. Revise as imagens e chame produce(..., project_id=..., approved=True) para renderizar.",
                }

            # 8. Procedural SFX + Original Background Music + Final Audio Mix
            sfx_wav: Optional[Path] = None
            if self.cfg.get("audio.enable_sfx", True):
                sfx_wav = synthesize_sfx_track(storyboard, audio_dir / "sfx.wav")

            music_wav: Optional[Path] = None
            if self.cfg.get("audio.enable_music", True):
                music_wav = synthesize_background_music(sync_data["duration_sec"], audio_dir / "music.wav")

            mix_wav = mix_final_audio(
                vo_wav=Path(tts_meta["vo_wav"]),
                duration_sec=sync_data["duration_sec"],
                out_mix_wav=audio_dir / "mix.wav",
                sfx_wav=sfx_wav,
                music_wav=music_wav,
                config=self.cfg,
            )

            # 9. Chunked Parallel Three.js + Playwright -> FFmpeg Render (resumable!)
            final_mp4 = proj_dir / f"{pid}.mp4"
            self.render_video_parts(
                storyboard_path=storyboard_path,
                sync_json_path=sync_json_path,
                audio_path=mix_wav,
                parts_dir=proj_dir / "parts",
                out_mp4=final_mp4,
            )

            # 10. Automated Technical + Visual Quality Control Gate
            qa_report = run_quality_check(
                video_path=final_mp4,
                storyboard=storyboard,
                srt_path=srt_path,
                qa_dir=proj_dir / "qa",
                config=self.cfg,
            )

            # 11. Optional Google Drive Delivery
            drive_summary = None
            should_sync = enable_drive_sync if enable_drive_sync is not None else bool(self.cfg.get("drive.enabled", False))
            if should_sync:
                dm = DriveManager(config=self.cfg, root_override=drive_root_override)
                dm.mount_if_colab()
                drive_summary = dm.sync_project(
                    project_id=pid,
                    local_project_dir=proj_dir,
                    deliverables={
                        "video_mp4": final_mp4,
                        "story_json": story_path,
                        "mix_wav": mix_wav,
                        "vo_wav": Path(tts_meta["vo_wav"]),
                        "storyboard_json": storyboard_path,
                        "storyboard_sheet": Path(board_info["contact_sheet"]) if board_info else None,
                        "srt_path": srt_path,
                        "sync_json": sync_json_path,
                        "quality_report": proj_dir / "qa" / "quality_report.json",
                        "qa_contact_sheet": Path(qa_report["visual_checks"]["contact_sheet"])
                        if qa_report["visual_checks"].get("contact_sheet")
                        else None,
                        "log_file": log_file,
                    },
                )

            result = {
                "status": "completed" if qa_report["approved"] else "qa_failed",
                "approved": qa_report["approved"],
                "project_id": pid,
                "project_dir": str(proj_dir),
                "video_mp4": str(final_mp4),
                "story_path": str(story_path),
                "storyboard_path": str(storyboard_path),
                "srt_path": str(srt_path),
                "sync_json_path": str(sync_json_path),
                "mix_wav": str(mix_wav),
                "environment_probe": env_probe,
                "alignment_method": sync_data["alignment_method"],
                "alignment_fallback_used": sync_data["fallback_used"],
                "storyboard_metrics": storyboard["metrics"],
                "quality_report": qa_report,
                "drive_sync": drive_summary,
            }
            (proj_dir / "production_summary.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("=== PRODUÇÃO FINALIZADA: status=%s | video=%s ===", result["status"], final_mp4)
            return result

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Falha crítica na produção '%s': %s\n%s", pid, exc, tb)
            if run_opencode_on_error:
                reviewer = OpenCodeReviewer(config=self.cfg)
                reviewer.diagnose_and_fix_failure(
                    error_log=tb,
                    relevant_files=[
                        PROJECT_ROOT / "src" / "video_orchestrator.py",
                        PROJECT_ROOT / "engine" / "render_worker.mjs",
                        PROJECT_ROOT / "engine" / "film_runtime.js",
                    ],
                    report_path=proj_dir / "opencode_error_diagnosis.json",
                )
            raise

    def render_video_parts(
        self,
        storyboard_path: Path,
        sync_json_path: Path,
        audio_path: Path,
        parts_dir: Path,
        out_mp4: Path,
        only_parts: Optional[List[int]] = None,
        force: bool = False,
    ) -> Path:
        """Invoke chunked parallel renderer (`engine/render_all.mjs`) with resume & partial re-render support."""
        node_bin = find_node()
        ffmpeg_bin = find_ffmpeg()
        render_all = PROJECT_ROOT / "engine" / "render_all.mjs"

        cmd = [
            node_bin,
            str(render_all),
            "--storyboard",
            str(storyboard_path),
            "--sync",
            str(sync_json_path),
            "--audio",
            str(audio_path),
            "--parts-dir",
            str(parts_dir),
            "--out",
            str(out_mp4),
            "--parts",
            str(int(self.cfg.get("video.num_parts", 10))),
            "--workers",
            str(int(self.cfg.get("video.workers", 2))),
            "--crf",
            str(int(self.cfg.get("video.crf", 18))),
            "--preset",
            str(self.cfg.get("video.preset", "veryfast")),
            "--ffmpeg",
            ffmpeg_bin,
        ]
        if only_parts:
            cmd.extend(["--only-parts", ",".join(str(i) for i in only_parts)])
        if force:
            cmd.append("--force")

        env = {"FFMPEG_BINARY": ffmpeg_bin}
        if os.environ.get("CPU"):
            env["CPU"] = os.environ["CPU"]

        run_subprocess(cmd, cwd=PROJECT_ROOT, env=env, timeout=3600)
        return out_mp4

    def rerender_scene_parts(self, project_dir: Path, part_indices: List[int]) -> Path:
        """Re-render ONLY the specified failed parts and re-mux final MP4 cleanly.

        Works even when an earlier production crashed before writing `production_summary.json`.
        """
        project_dir = Path(project_dir)
        summary_path = project_dir / "production_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            sb_path = Path(summary["storyboard_path"])
            sync_path = Path(summary["sync_json_path"])
            mix_path = Path(summary["mix_wav"])
            out_mp4 = Path(summary["video_mp4"])
        else:
            sb_path = project_dir / "storyboard.json"
            sync_path = project_dir / "subtitles" / "sync_data.json"
            mix_path = project_dir / "audio" / "mix.wav"
            out_mp4 = project_dir / f"{project_dir.name}.mp4"
            if not sb_path.exists():
                raise FileNotFoundError(
                    f"Não foi possível retomar re-renderização: '{sb_path}' ausente em {project_dir}"
                )

        return self.render_video_parts(
            storyboard_path=sb_path,
            sync_json_path=sync_path,
            audio_path=mix_path,
            parts_dir=project_dir / "parts",
            out_mp4=out_mp4,
            only_parts=part_indices,
        )
