"""Ponto de entrada do ROBLOX AI SHORTS STUDIO (interface web local/Colab e comandos CLI)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.audio_assets import ensure_default_audio_assets
from app.blender_renderer import get_rbx_engine_dir
from app.config import ensure_base_directories, get_drive_export_dir, is_colab_environment, load_settings
from app.hardware import detect_hardware
from app.models import GenerationMode
from app.subtitle_engine import WhisperSubtitleEngine
from app.tts_engine import LocalTTSEngine


def _configure_drive_root(drive_dir: str | None) -> None:
    """Configura automaticamente pastas persistentes no Google Drive (projetos, modelos em cache e vídeos prontos)."""
    if not drive_dir or not drive_dir.strip():
        return
    root = Path(drive_dir.strip())
    (root / "projects").mkdir(parents=True, exist_ok=True)
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "Videos_Prontos").mkdir(parents=True, exist_ok=True)
    os.environ["STUDIO_PROJECTS_DIR"] = str(root / "projects")
    os.environ["STUDIO_MODELS_DIR"] = str(root / "models")
    os.environ["STUDIO_DRIVE_EXPORT_DIR"] = str(root / "Videos_Prontos")


def cmd_doctor() -> int:
    ensure_base_directories()
    ensure_default_audio_assets()
    cfg = load_settings()
    hw = detect_hardware(cfg)
    print("=== ROBLOX AI SHORTS STUDIO — DIAGNÓSTICO DE HARDWARE E FERRAMENTAS ===")
    print(f"Ambiente:  {'Google Colab' if is_colab_environment() else 'Local'}")
    print(f"CPU:       {hw.cpu_name} ({hw.cpu_cores} threads)")
    print(f"GPU:       {hw.gpu_name} ({hw.gpu_vendor}) | VRAM: {hw.gpu_vram_gb:.2f} GB | CUDA: {hw.cuda_available}")
    print(f"RAM:       {hw.ram_total_gb:.1f} GB total ({hw.ram_available_gb:.1f} GB livre)")
    print(f"Disco:     {hw.disk_free_gb:.1f} GB livres")
    print(f"FFmpeg:    {'OK -> ' + str(hw.ffmpeg_path) if hw.ffmpeg_available else 'NÃO ENCONTRADO'}")
    print(f"Blender3D: {'OK -> ' + str(hw.blender_version) + ' (' + str(hw.blender_path) + ')' if hw.blender_available else 'NÃO INSTALADO (instale em blender.org para 3D real)'}")
    rbx_dir = get_rbx_engine_dir(cfg)
    print(f"Motor rbx: {'OK (embutido) -> ' + str(rbx_dir) if rbx_dir else 'Usando blender_scene_script.py interno'}")
    print(f"Ollama:    {'ATIVO -> ' + str(hw.ollama_models) if hw.ollama_available else 'INATIVO (opcional para LLM local)'}")
    print(f"ComfyUI:   {'ATIVO' if hw.comfyui_available else 'INATIVO (opcional para vídeo/imagem GPU)'}")
    print(f"KokoroTTS: {'PRONTO OFFLINE' if hw.kokoro_ready else 'PENDENTE (~115 MB)'}")
    print(f"Whisper:   {'PRONTO OFFLINE' if hw.whisper_ready else 'PENDENTE (~145 MB)'}")
    print(f"Wan 2.2:   {'COMPATÍVEL' if hw.supports_wan22 else 'BLOQUEADO (requer GPU CUDA >= 12 GB VRAM)'}")
    print(f"Projetos:  {cfg['paths']['projects_dir']}")
    drive_exp = get_drive_export_dir(cfg)
    if drive_exp:
        print(f"Drive Out: {drive_exp}")
    print(f"Plano:     {hw.recommended_tier}")
    print(f"Resumo:    {hw.compatibility_summary}")
    if hw.warnings:
        print("\nAvisos:")
        for w in hw.warnings:
            print(f"  - {w}")
    return 0


def cmd_download_small_models() -> int:
    ensure_base_directories()
    tts = LocalTTSEngine()
    print("[1/2] Baixando Kokoro TTS v1.0 INT8 (~115 MB total, licença Apache-2.0)...")
    tts.download_kokoro_models(progress_cb=print)
    sub = WhisperSubtitleEngine()
    w_model = load_settings()["subtitles"].get("whisper_model", "base")
    print(f"[2/2] Baixando Faster-Whisper '{w_model}' (~145 MB, licença MIT)...")
    sub.ensure_model_downloaded(w_model)
    print("Modelos locais leves prontos para funcionamento 100% offline!")
    return 0


def cmd_generate_headless(args: argparse.Namespace) -> int:
    """Gera um vídeo completo 9:16 diretamente pelo terminal / célula do Google Colab (salva direto no Drive)."""
    from app.pipeline import ProductionPipeline

    cfg = load_settings()
    ensure_base_directories(cfg)
    ensure_default_audio_assets(cfg)

    pipeline = ProductionPipeline(settings=cfg)
    state = pipeline.pm.create_project(
        story_input=args.generate,
        genre=args.genre,
        opening_style=args.opening,
        duration_seconds=int(args.duration),
        mode=GenerationMode.LOCAL_FREE,
        visual_style=args.style,
        flow_credits_available=False,
        voice=args.voice,
        speed=float(args.speed),
        music_mood=args.music,
    )

    print(f"=== Iniciando produção headless: {state.project_id} ===")
    state, story, _sb = pipeline.run_project(
        project_id=state.project_id,
        story_provider=args.provider,
        gemini_api_key=args.gemini_key or None,
        offline_only=False,
        auto_download_small_models=True,
        progress_cb=lambda pct, msg: print(f"[{pct:5.1f}%] {msg}", flush=True),
    )

    print("\n=== PRODUÇÃO FINALIZADA ===")
    print(f"Projeto: {state.project_id}")
    print(f"Status:  {state.status}")
    if story:
        print(f"Título:  {story.suggested_title or story.title}")
    if state.final_video_path:
        print(f"Vídeo:   {state.final_video_path}")
    drive_exp = get_drive_export_dir(cfg)
    if drive_exp:
        print(f"Drive:   {drive_exp}")
    return 0 if state.status == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ROBLOX AI SHORTS STUDIO")
    parser.add_argument("--host", default=None, help="Endereço (padrão: 127.0.0.1 local ou 0.0.0.0 no Colab)")
    parser.add_argument("--port", type=int, default=None, help="Porta (padrão: 7860)")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir navegador automaticamente")
    parser.add_argument("--share", action="store_true", help="Gerar link público Gradio (ideal para Google Colab)")
    parser.add_argument("--colab", action="store_true", help="Ativar modo Google Colab (--share, --no-browser, host 0.0.0.0)")
    parser.add_argument(
        "--drive-dir",
        default=None,
        help="Pasta raiz no Google Drive (ex.: /content/drive/MyDrive/RobloxAIShortsStudio) para salvar vídeos, projetos e modelos",
    )
    parser.add_argument("--doctor", action="store_true", help="Executar diagnóstico de hardware e dependências")
    parser.add_argument(
        "--download-small-models",
        action="store_true",
        help="Baixar modelos leves locais (Kokoro TTS ~115 MB e Whisper base ~145 MB)",
    )
    # Modo CLI direto (ótimo para rodar 1-clique numa célula do Colab sem abrir UI)
    parser.add_argument("--generate", default=None, help="Gerar vídeo diretamente via CLI passando o texto da história")
    parser.add_argument("--genre", default="Suspense / Mistério", help="Gênero da história")
    parser.add_argument("--opening", default="Neste servidor...", help="Estilo de abertura")
    parser.add_argument("--duration", type=int, default=55, help="Duração alvo em segundos (45-60)")
    parser.add_argument("--voice", default="pm_alex", help="Voz PT-BR (pm_alex, pf_dora, pm_santa)")
    parser.add_argument("--speed", type=float, default=1.05, help="Velocidade da narração")
    parser.add_argument("--music", default="suspense", help="Música instrumental (suspense, divertida, emocionante, none)")
    parser.add_argument("--style", default="roblox_3d_blender_cinematic", help="ID do estilo visual")
    parser.add_argument("--provider", default="auto", help="Provedor de roteiro (auto, ollama, gemini_api)")
    parser.add_argument("--gemini-key", default=None, help="Chave opcional da API Gemini (apenas em memória)")
    args = parser.parse_args()

    if args.colab:
        os.environ["STUDIO_COLAB_MODE"] = "1"
    _configure_drive_root(args.drive_dir)

    ensure_base_directories()
    ensure_default_audio_assets()

    if args.doctor:
        return cmd_doctor()
    if args.download_small_models:
        return cmd_download_small_models()
    if args.generate:
        return cmd_generate_headless(args)

    from app.ui import launch_studio

    launch_studio(
        host=args.host,
        port=args.port,
        open_browser=(False if (args.no_browser or args.colab) else None),
        share=(True if (args.share or args.colab) else None),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
