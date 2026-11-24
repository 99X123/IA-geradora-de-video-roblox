"""Sistema de modos de geração (Google Flow, 100% Gratuito, Automático Flow+Gratuito) e importação de clipes."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import av

from app.config import load_settings, save_settings
from app.models import (
    GenerationMode,
    ProjectState,
    SceneSourceType,
    StoryboardDocument,
    StoryDocument,
)
from app.project_manager import ProjectManager

SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def probe_video_metadata(video_path: Path) -> Dict[str, float | int]:
    """Valida e lê metadados reais (largura, altura, fps, duração) usando PyAV (sem depender de ffprobe)."""
    with av.open(str(video_path)) as container:
        vstreams = [s for s in container.streams if s.type == "video"]
        if not vstreams:
            raise ValueError(f"Arquivo '{video_path.name}' não contém faixa de vídeo válida.")
        vs = vstreams[0]
        duration = 0.0
        if container.duration is not None:
            duration = float(container.duration) / 1_000_000.0
        elif vs.duration is not None and vs.time_base is not None:
            duration = float(vs.duration * vs.time_base)
        fps = float(vs.average_rate) if vs.average_rate else 30.0
        return {
            "width": int(vs.width or 0),
            "height": int(vs.height or 0),
            "fps": round(fps, 2),
            "duration": round(duration, 2),
        }


def should_use_flow(state: ProjectState) -> bool:
    """Determina se o projeto deve preparar/aguardar cenas do Google Flow."""
    if state.mode == GenerationMode.GOOGLE_FLOW:
        return True
    if state.mode == GenerationMode.AUTO_FLOW_FREE:
        return bool(state.flow_credits_available)
    return False


def prepare_flow_package(
    project_dir: Path,
    story: StoryDocument,
    storyboard: StoryboardDocument,
    flow_url: str = "https://labs.google/fx/tools/flow",
) -> Tuple[Path, List[Path]]:
    """
    Prepara todos os prompts, referências de personagens e instruções organizadas
    para uso na interface oficial do Google Flow (sem cookies, scraping ou API privada).
    """
    prompts_dir = project_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    scene_files: List[Path] = []
    pack_scenes = []

    md_lines: List[str] = [
        f"# Pacote Google Flow + Veo — {story.title}",
        "",
        f"**Site oficial do Google Flow:** {flow_url}",
        "",
        "> **Segurança e conformidade:** Gere e baixe os clipes exclusivamente pela interface oficial do Google Flow na conta autorizada. "
        "Este aplicativo nunca automatiza login, nunca lê cookies e nunca solicita compra de créditos.",
        "",
        "## 1. Consistência de Personagens (Referências)",
        "Use as imagens geradas na pasta `references/` como imagem de referência (*Ingredients / Reference Frame*) no Flow sempre que disponível:",
        "",
    ]

    for ch in storyboard.characters:
        ref_name = Path(ch.reference_image_path).name if ch.reference_image_path else "N/A"
        md_lines.append(f"- **{ch.name}** ({ch.role}) — Arquivo: `references/{ref_name}`")
        md_lines.append(f"  - Descrição visual (EN): `{ch.visual_description_en}`")

    md_lines.extend(
        [
            "",
            "## 2. Como importar os clipes gerados",
            f"1. Abra {flow_url} na conta autorizada e configure proporção **9:16 (Vertical)**.",
            "2. Gere cada cena abaixo usando o prompt em inglês correspondente.",
            f"3. Salve os vídeos baixados como `scene_01.mp4`, `scene_02.mp4`, ... na pasta `{videos_dir}` ou envie pelo botão de importação na interface.",
            "4. Se os créditos acabarem no meio do projeto, clique em **MEUS CRÉDITOS DO FLOW ACABARAM**: as cenas já importadas serão mantidas e as restantes serão concluídas no modo 100% gratuito local!",
            "",
            "## 3. Prompts por Cena",
            "",
        ]
    )

    for scene in storyboard.scenes:
        txt_path = prompts_dir / f"scene_{scene.scene_number:02d}_flow.txt"
        txt_content = (
            f"=== CENA {scene.scene_number:02d} — {scene.title} ({scene.story_beat}) ===\n"
            f"Duração sugerida: {scene.duration_seconds:.1f}s | Proporção: 9:16 Vertical\n"
            f"Personagens: {', '.join(scene.characters)}\n"
            f"Expressão: {scene.expression} | Movimento de câmera: {scene.camera_movement}\n"
            f"Narração (PT-BR): {scene.narration_pt}\n\n"
            f"PROMPT PARA COPIAR NO GOOGLE FLOW (EN):\n"
            f"{scene.visual_prompt_en}\n\n"
            f"EVITAR / NEGATIVE GUIDANCE:\n"
            f"{scene.negative_prompt_en}\n\n"
            f"NOME DO ARQUIVO AO EXPORTAR:\n"
            f"scene_{scene.scene_number:02d}.mp4\n"
        )
        txt_path.write_text(txt_content, encoding="utf-8")
        scene.flow_prompt_file = str(txt_path)
        scene_files.append(txt_path)

        md_lines.extend(
            [
                f"### Cena {scene.scene_number:02d} — {scene.title} (`scene_{scene.scene_number:02d}.mp4`)",
                f"- **Trecho da narração:** {scene.narration_pt}",
                f"- **Câmera / Expressão:** `{scene.camera_movement}` / `{scene.expression}` (~{scene.duration_seconds:.1f}s)",
                "```text",
                scene.visual_prompt_en,
                "```",
                "",
            ]
        )

        pack_scenes.append(
            {
                "scene_number": scene.scene_number,
                "expected_filename": f"scene_{scene.scene_number:02d}.mp4",
                "title": scene.title,
                "narration_pt": scene.narration_pt,
                "visual_prompt_en": scene.visual_prompt_en,
                "camera_movement": scene.camera_movement,
                "expression": scene.expression,
                "duration_seconds": scene.duration_seconds,
            }
        )

    instructions_md = prompts_dir / "flow_instructions.md"
    instructions_md.write_text("\n".join(md_lines), encoding="utf-8")

    pack_json = prompts_dir / "flow_pack.json"
    pack_json.write_text(
        json.dumps(
            {
                "title": story.title,
                "official_url": flow_url,
                "characters": [c.model_dump(mode="json") for c in storyboard.characters],
                "scenes": pack_scenes,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return instructions_md, scene_files


def import_scene_video(
    project_dir: Path,
    storyboard: StoryboardDocument,
    scene_number: int,
    source_file: str | Path,
    source_type: SceneSourceType = SceneSourceType.GOOGLE_FLOW_IMPORT,
) -> Dict[str, object]:
    """Importa e valida um vídeo (Google Flow ou gravação do Roblox Studio) para uma cena específica."""
    src = Path(source_file)
    if not src.exists():
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {src}")
    if src.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
        raise ValueError(f"Formato não suportado ({src.suffix}). Use MP4, MOV, MKV ou WEBM.")

    meta = probe_video_metadata(src)
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    dest = videos_dir / f"scene_{scene_number:02d}{src.suffix.lower()}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    target = next((s for s in storyboard.scenes if s.scene_number == scene_number), None)
    if target is None:
        raise ValueError(f"Cena {scene_number} não existe neste storyboard.")

    target.video_path = str(dest)
    target.status = "ready"
    target.source_type = source_type
    target.error_message = None
    return {"scene_number": scene_number, "dest": str(dest), "metadata": meta}


def scan_and_import_video_folder(
    project_dir: Path,
    storyboard: StoryboardDocument,
    source_type: SceneSourceType = SceneSourceType.GOOGLE_FLOW_IMPORT,
) -> List[int]:
    """Detecta automaticamente clipes salvos pelo usuário em `projects/<id>/videos/` (ex.: scene_01.mp4, cena_02.mp4, 03.mp4)."""
    videos_dir = project_dir / "videos"
    if not videos_dir.exists():
        return []

    imported: List[int] = []
    for file_path in sorted(videos_dir.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
            continue
        m = re.search(r"(?:scene|cena|clip)?[_-]?(\d{1,2})", file_path.stem, flags=re.IGNORECASE)
        if not m:
            continue
        scene_num = int(m.group(1))
        scene = next((s for s in storyboard.scenes if s.scene_number == scene_num), None)
        if scene is None:
            continue
        if scene.status == "ready" and scene.video_path and Path(scene.video_path).exists():
            continue
        try:
            probe_video_metadata(file_path)
            scene.video_path = str(file_path)
            scene.status = "ready"
            scene.source_type = source_type
            scene.error_message = None
            imported.append(scene_num)
        except Exception:
            continue
    return imported


def mark_flow_credits_exhausted(
    pm: ProjectManager,
    state: Optional[ProjectState] = None,
    persist_global: bool = True,
) -> Tuple[Optional[ProjectState], str]:
    """
    Ação do botão 'MEUS CRÉDITOS DO FLOW ACABARAM'.
    Alterna imediatamente para o modo 100% gratuito sem interromper nem perder cenas já prontas.
    """
    if persist_global:
        cfg = load_settings()
        cfg["generation"]["flow_credits_available"] = False
        save_settings(cfg)

    if state is not None:
        state.flow_credits_available = False
        if state.mode == GenerationMode.GOOGLE_FLOW:
            state.mode = GenerationMode.LOCAL_FREE
        if state.status == "awaiting_flow_import":
            state.status = "idle"
        pm.append_log(
            state,
            "Créditos do Google Flow marcados como esgotados. Alternado automaticamente para modo 100% GRATUITO LOCAL "
            "(cenas já importadas foram preservadas; custo adicional: R$ 0).",
        )
        pm.save_state(state)

    return state, (
        "Modo 100% GRATUITO LOCAL ativado! Nenhuma compra ou assinatura é necessária. "
        "As cenas já prontas foram preservadas e o projeto continuará localmente."
    )


def get_flow_import_summary(storyboard: Optional[StoryboardDocument]) -> str:
    if storyboard is None:
        return "Nenhum storyboard carregado ainda."
    total = len(storyboard.scenes)
    ready = sum(1 for s in storyboard.scenes if s.status == "ready" and s.video_path and Path(s.video_path).exists())
    flow_count = sum(1 for s in storyboard.scenes if s.source_type == SceneSourceType.GOOGLE_FLOW_IMPORT)
    local_count = ready - flow_count
    pending = [f"Cena {s.scene_number:02d}" for s in storyboard.scenes if s.status != "ready"]
    pending_txt = ", ".join(pending) if pending else "Nenhuma — todas as cenas estão prontas!"
    return (
        f"Cenas prontas: {ready}/{total} (Flow: {flow_count} | Local/Importadas: {local_count})\n"
        f"Pendentes: {pending_txt}"
    )
