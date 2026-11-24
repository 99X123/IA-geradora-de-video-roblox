"""Suíte de testes obrigatórios (Seção 18) para o ROBLOX AI SHORTS STUDIO."""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

import av
import pytest
import soundfile as sf

from app.audio_assets import ensure_default_audio_assets
from app.comfyui_client import ComfyUIClient, ComfyUIError
from app.config import BASE_DIR, get_ffmpeg_executable, load_settings
from app.hardware import detect_hardware
from app.models import GenerationMode, HardwareReport, SceneSourceType
from app.pipeline import ProductionPipeline
from app.project_manager import ProjectManager
from app.story_engine import build_master_llm_prompt, parse_and_validate_llm_payload
from app.ui import build_ui
from app.video_modes import (
    import_scene_video,
    mark_flow_credits_exhausted,
    probe_video_metadata,
)


def _create_sample_mp4(dest: Path, width: int = 1280, height: int = 720, duration: float = 3.0) -> Path:
    """Cria um clipe MP4 real (ex.: simulando exportação do Flow ou gravação 16:9 do Roblox Studio)."""
    ffmpeg_exe = get_ffmpeg_executable()
    assert ffmpeg_exe, "FFmpeg deve estar disponível"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size={width}x{height}:rate=30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def test_01_hardware_detection_and_wan22_safety_guard() -> None:
    """Testa detecção real de hardware e bloqueio de segurança do Wan 2.2 em GPUs incompatíveis."""
    hw = detect_hardware()
    assert hw.cpu_cores >= 1
    assert hw.ram_total_gb > 0
    assert hw.disk_free_gb > 0
    assert hw.ffmpeg_available is True

    # Garante que hardware com <12 GB VRAM bloqueia Wan 2.2 com segurança
    weak_hw = HardwareReport(
        gpu_name="NVIDIA GeForce GT 710",
        gpu_vram_gb=2.0,
        cuda_available=False,
        supports_wan22=False,
        supports_local_image_ai=False,
    )
    client = ComfyUIClient()
    from app.models import SceneSpec

    dummy_scene = SceneSpec(
        scene_number=1,
        title="Teste",
        description_pt="Cena de teste de hardware.",
        narration_pt="Cena de teste de hardware.",
        visual_prompt_en="3D cinematic Roblox test scene vertical 9:16",
    )
    with pytest.raises(ComfyUIError, match="Hardware incompatível"):
        client.generate_scene_video_wan22(dummy_scene, BASE_DIR / "temp" / "never.mp4", weak_hw)


def test_02_comfyui_workflows_valid_json() -> None:
    """Valida que todos os workflows JSON do ComfyUI estão íntegros e estruturados."""
    wf_dir = BASE_DIR / "workflows" / "comfyui"
    for name in ("wan22_ti2v_5b.json", "wan22_i2v_character_ref.json", "image_gen_roblox_scene.json"):
        p = wf_dir / name
        assert p.exists(), f"Workflow ausente: {name}"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and len(data) >= 6


def test_03_gemini_web_pro_json_import_validation() -> None:
    """Valida geração de prompt para Gemini Web (Google AI Pro) e validação estrita de JSON."""
    prompt = build_master_llm_prompt(
        story_input="Um jogador acha uma porta invisível na escola do Roblox.",
        genre="Suspense / Mistério",
        opening_style="Nesta escola...",
        duration_seconds=50,
        scene_count=6,
    )
    assert "Nesta escola..." in prompt
    assert "visual_prompt_en" in prompt

    sample_json = json.dumps(
        {
            "story": {
                "title": "A Porta Invisível da Escola",
                "hook_pt": "Nesta escola do Roblox, ninguém pode abrir o armário treze.",
                "genre": "Suspense / Mistério",
                "opening_style": "Nesta escola...",
            },
            "characters": [
                {
                    "id": "char_1",
                    "name": "Bia",
                    "role": "Protagonista",
                    "visual_description_en": "Roblox 3D R15 girl avatar wearing yellow hoodie and dark jeans",
                    "primary_color_hex": "#EAB308",
                    "secondary_color_hex": "#1E293B",
                }
            ],
            "scenes": [
                {
                    "scene_number": i,
                    "title": f"Cena {i}",
                    "story_beat": "Desenvolvimento",
                    "description_pt": f"Descrição visual da cena {i}.",
                    "narration_pt": f"Frase de narração número {i} em português brasileiro.",
                    "visual_prompt_en": f"3D Roblox school hallway scene {i}, cinematic lighting, vertical 9:16",
                    "characters": ["Bia"],
                    "setting_theme": "school",
                    "expression": "curious",
                    "camera_movement": "slow_zoom_in",
                    "duration_seconds": 6.0,
                    "sfx_cue": "transition",
                }
                for i in range(1, 7)
            ],
        }
    )
    story, sb = parse_and_validate_llm_payload(
        sample_json, "proj_test", "Suspense / Mistério", "Nesta escola...", 50, "google_gemini_web_pro"
    )
    assert story.story_provider == "google_gemini_web_pro"
    assert len(sb.scenes) == 6
    assert sb.characters[0].name == "Bia"


def test_04_audio_assets_generation() -> None:
    """Garante geração local de músicas instrumentais e SFX 100% originais."""
    assets = ensure_default_audio_assets()
    for key, path in assets.items():
        assert path.exists(), f"Asset ausente: {key}"
        info = sf.info(str(path))
        assert info.duration > 0.3


def test_05_flow_mode_import_and_credit_exhaustion_switch(tmp_path: Path) -> None:
    """
    Testa o sistema de troca automática Flow -> 100% Gratuito:
    1. Inicia em Modo Automático com créditos Flow ativos -> pausa em awaiting_flow_import.
    2. Importa clipe real (simulação de Flow / Roblox Studio 16:9) na Cena 1.
    3. Aciona 'MEUS CRÉDITOS DO FLOW ACABARAM' -> muda para local_free preservando Cena 1.
    4. Continua e renderiza MP4 final 1080x1920 validado (sem esticar o vídeo 16:9 importado).
    """
    cfg = load_settings()
    cfg["paths"]["projects_dir"] = str(tmp_path / "projects")
    cfg["paths"]["logs_dir"] = str(tmp_path / "logs")
    cfg["generation"]["min_scenes"] = 6
    cfg["generation"]["max_scenes"] = 6

    pipeline = ProductionPipeline(settings=cfg)
    pm = pipeline.pm

    state = pm.create_project(
        story_input=(
            "Neste servidor secreto de Roblox, quem encosta na sombra azul congela na hora. "
            "Lucas correu pelo mapa tentando salvar os amigos. "
            "Um Admin Sombrio fechou o portão principal. "
            "No final, Lucas usou o próprio reflexo no piso para destravar a saída."
        ),
        genre="Suspense / Mistério",
        opening_style="Neste servidor...",
        duration_seconds=45,
        mode=GenerationMode.AUTO_FLOW_FREE,
        flow_credits_available=True,
        voice="pm_alex",
        speed=1.10,
        music_mood="suspense",
    )

    # Execução 1: deve preparar roteiro, referências, prompts, narração, legendas e pausar aguardando Flow
    state, story, sb = pipeline.run_project(state.project_id, offline_only=True)
    assert state.status == "awaiting_flow_import"
    assert story is not None and sb is not None
    assert len(sb.scenes) == 6
    assert (Path(state.project_dir) / "prompts" / "flow_instructions.md").exists()
    assert (Path(state.project_dir) / "audio" / "narration.wav").exists()
    assert (Path(state.project_dir) / "subtitles" / "captions.srt").exists()
    assert (Path(state.project_dir) / "subtitles" / "captions.ass").exists()
    assert all(Path(c.reference_image_path).exists() for c in sb.characters if c.reference_image_path)

    # Importa clipe real 16:9 (simulando Flow / Roblox Studio) na Cena 1
    fake_flow_clip = _create_sample_mp4(tmp_path / "flow_scene_01.mp4", width=1280, height=720, duration=4.0)
    import_scene_video(
        Path(state.project_dir),
        sb,
        scene_number=1,
        source_file=fake_flow_clip,
        source_type=SceneSourceType.GOOGLE_FLOW_IMPORT,
    )
    pm.save_storyboard(state.project_id, sb)

    # Simula clique em "MEUS CRÉDITOS DO FLOW ACABARAM" (sem alterar settings global do workspace)
    state, msg = mark_flow_credits_exhausted(pm, state=state, persist_global=False)
    assert state is not None
    assert state.flow_credits_available is False
    assert "100% GRATUITO" in msg

    # Continua a produção 100% local e offline (bloqueando conexões de rede externas para comprovar offline real!)
    orig_create_conn = socket.create_connection

    def _forbid_network(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Rede bloqueada no teste offline!")

    socket.create_connection = _forbid_network  # type: ignore[assignment]
    try:
        state, story, sb = pipeline.run_project(state.project_id, offline_only=True)
    finally:
        socket.create_connection = orig_create_conn  # type: ignore[assignment]

    assert state.status == "completed"
    assert sb is not None
    # Confirma que a Cena 1 importada do Flow foi PRESERVADA e não regenerada!
    assert sb.scenes[0].source_type == SceneSourceType.GOOGLE_FLOW_IMPORT
    assert sb.scenes[1].source_type in (
        SceneSourceType.BLENDER_3D_RENDER,
        SceneSourceType.FALLBACK_PROCEDURAL_ANIMATED,
    )
    assert "High-quality cinematic 3D Roblox animation" in sb.scenes[1].visual_prompt_en
    assert "2D illustration, flat cartoon, vector art" in sb.scenes[1].negative_prompt_en

    final_mp4 = Path(state.final_video_path or "")
    assert final_mp4.exists() and final_mp4.stat().st_size > 100_000
    meta = probe_video_metadata(final_mp4)
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert float(meta["duration"]) >= 12.0


def test_06_interrupted_project_recovery_and_scene_caching(tmp_path: Path) -> None:
    """Testa cancelamento/interrupção no meio das cenas e retomada preservando cenas em cache."""
    cfg = load_settings()
    cfg["paths"]["projects_dir"] = str(tmp_path / "projects")
    cfg["paths"]["logs_dir"] = str(tmp_path / "logs")
    cfg["generation"]["min_scenes"] = 6
    cfg["generation"]["max_scenes"] = 6

    pipeline = ProductionPipeline(settings=cfg)
    pm = pipeline.pm

    state = pm.create_project(
        story_input="Nesta cidade do Roblox, toda noite as casas trocam de lugar e ninguém encontra a própria rua.",
        genre="Suspense / Mistério",
        opening_style="Nesta cidade...",
        duration_seconds=45,
        mode=GenerationMode.LOCAL_FREE,
        flow_credits_available=False,
        voice="pf_dora",
        speed=1.05,
        music_mood="emocionante",
    )

    # Interrompe deliberadamente após produzir a Cena 2
    orig_produce = pipeline._produce_local_scene
    produced_calls: list[int] = []

    def _produce_then_cancel(project_dir: Path, sb: Any, scene: Any, hw: Any, st: Any) -> None:
        produced_calls.append(scene.scene_number)
        orig_produce(project_dir, sb, scene, hw, st)
        if scene.scene_number == 2:
            pm.request_cancel(st.project_id)

    pipeline._produce_local_scene = _produce_then_cancel  # type: ignore[method-assign]
    state, _, sb_partial = pipeline.run_project(state.project_id, offline_only=True)
    assert state.status == "cancelled"
    assert produced_calls == [1, 2]
    assert sb_partial is not None
    assert sb_partial.scenes[0].status == "ready"
    assert sb_partial.scenes[1].status == "ready"
    assert sb_partial.scenes[2].status == "pending"

    # Retoma projeto: NÃO deve regenerar Cenas 1 e 2!
    produced_after_resume: list[int] = []

    def _track_resume(project_dir: Path, sb: Any, scene: Any, hw: Any, st: Any) -> None:
        produced_after_resume.append(scene.scene_number)
        orig_produce(project_dir, sb, scene, hw, st)

    pipeline._produce_local_scene = _track_resume  # type: ignore[method-assign]
    state, _, sb_done = pipeline.run_project(state.project_id, offline_only=True)
    assert state.status == "completed"
    assert produced_after_resume == [3, 4, 5, 6]
    assert sb_done is not None
    assert Path(state.final_video_path or "").exists()


def test_07_gradio_ui_builds_and_serves_http() -> None:
    """Testa inicialização real da interface gráfica Gradio em localhost."""
    demo = build_ui()
    assert demo is not None

    # Sobe servidor em porta temporária e confirma HTTP 200
    import threading

    port = 7869
    server_thread = threading.Thread(
        target=lambda: demo.launch(
            server_name="127.0.0.1",
            server_port=port,
            inbrowser=False,
            share=False,
            quiet=True,
            prevent_thread_lock=False,
        ),
        daemon=True,
    )
    server_thread.start()

    ok = False
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8", errors="ignore")
                    assert "ROBLOX AI SHORTS STUDIO" in body
                    ok = True
                    break
        except Exception:
            time.sleep(0.5)
    try:
        demo.close()
    except Exception:
        pass
    assert ok, "Interface Gradio não respondeu HTTP 200 em http://127.0.0.1:7869/"


def test_08_colab_env_overrides_and_drive_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida redirecionamento de caminhos para Google Drive e exportação automática de final.mp4 + metadados."""
    drive_root = tmp_path / "MyDrive" / "RobloxAIShortsStudio"
    monkeypatch.setenv("STUDIO_COLAB_MODE", "1")
    monkeypatch.setenv("STUDIO_PROJECTS_DIR", str(drive_root / "projects"))
    monkeypatch.setenv("STUDIO_MODELS_DIR", str(drive_root / "models"))
    monkeypatch.setenv("STUDIO_DRIVE_EXPORT_DIR", str(drive_root / "Videos_Prontos"))

    from app.config import get_drive_export_dir, is_colab_environment
    from app.models import StoryDocument

    assert is_colab_environment() is True
    cfg = load_settings()
    assert cfg["paths"]["projects_dir"] == str(drive_root / "projects")
    assert cfg["paths"]["models_dir"] == str(drive_root / "models")
    assert Path(cfg["tts"]["kokoro_model_file"]).parent.parent == drive_root / "models"
    export_dir = get_drive_export_dir(cfg)
    assert export_dir == (drive_root / "Videos_Prontos").resolve()

    pipeline = ProductionPipeline(settings=cfg)
    state = pipeline.pm.create_project(story_input="Teste Drive Colab", mode=GenerationMode.LOCAL_FREE)
    dummy_mp4 = Path(state.project_dir) / "output" / "final.mp4"
    dummy_mp4.write_bytes(b"fake-mp4-content-for-drive-sync")
    dummy_srt = Path(state.project_dir) / "subtitles" / "captions.srt"
    dummy_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nOi!\n", encoding="utf-8")
    dummy_story = StoryDocument(
        title="O Portal do Servidor",
        hook_pt="Neste servidor secreto ninguém pode piscar!",
        full_narration_pt="Neste servidor secreto ninguém pode piscar durante a contagem regressiva.",
        suggested_title="O Portal do Servidor #Shorts",
        suggested_description="História 3D de Roblox.",
        suggested_hashtags=["#roblox", "#shorts"],
    )

    copied = pipeline._export_to_google_drive(dummy_mp4, state, dummy_story, dummy_srt)
    assert copied is not None and copied.exists()
    assert copied.parent == export_dir
    assert copied.with_suffix(".srt").exists()
    assert (export_dir / f"{copied.stem}_post.txt").exists()
