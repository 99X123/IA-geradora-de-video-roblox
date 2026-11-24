"""Interface gráfica moderna em Gradio para o ROBLOX AI SHORTS STUDIO."""

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from app.config import (
    BASE_DIR,
    ensure_base_directories,
    get_drive_export_dir,
    is_colab_environment,
    load_settings,
    resolve_path,
    save_settings,
)
from app.hardware import detect_hardware
from app.models import GenerationMode, ProjectState, SceneSourceType, StoryboardDocument, StoryDocument
from app.pipeline import ProductionPipeline
from app.story_engine import (
    STORY_GENRES,
    STORY_OPENINGS,
    build_master_llm_prompt,
    parse_and_validate_llm_payload,
)
from app.tts_engine import PT_BR_VOICES
from app.video_modes import (
    get_flow_import_summary,
    import_scene_video,
    mark_flow_credits_exhausted,
    scan_and_import_video_folder,
)
from app.visual_styles import (
    DEFAULT_VISUAL_STYLE_ID,
    STYLE_ID_TO_LABEL,
    STYLE_LABEL_TO_ID,
    list_visual_style_labels,
)

MODE_LABELS: Dict[str, GenerationMode] = {
    "Automático — Flow + Gratuito": GenerationMode.AUTO_FLOW_FREE,
    "Google Flow": GenerationMode.GOOGLE_FLOW,
    "100% Gratuito": GenerationMode.LOCAL_FREE,
}
MODE_TO_LABEL: Dict[GenerationMode, str] = {v: k for k, v in MODE_LABELS.items()}

STORY_PROVIDER_LABELS: Dict[str, str] = {
    "Automático (Ollama Local / Gemini API / Offline)": "auto",
    "Ollama Local (Gemma 3 — 100% Gratuito)": "ollama",
    "Google Gemini API (chave opcional)": "gemini_api",
}

MUSIC_CHOICES = [
    ("Suspense (Instrumental Original)", "suspense"),
    ("Divertida / Dinâmica (Instrumental Original)", "divertida"),
    ("Emocionante / Épica (Instrumental Original)", "emocionante"),
    ("Sem música de fundo", "none"),
]

SAMPLE_STORY = (
    "Neste servidor secreto de Roblox, todo jogador nasce com um número brilhando em cima da cabeça. "
    "O Lucas entrou achando que era um minigame comum, mas percebeu que quem falava a palavra 'sair' perdia metade da contagem na hora. "
    "Quando o relógio chegou perto de zero, um Admin Sombrio apareceu bloqueando a única ponte do mapa. "
    "No último segundo, Lucas descobriu que o número não era uma contagem de eliminação, mas a energia para abrir o portal de saída para todos os jogadores presos."
)

CUSTOM_CSS = """
.studio-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #312e81 100%);
    border: 1px solid rgba(96, 165, 250, 0.35);
    border-radius: 16px;
    padding: 20px 26px;
    margin-bottom: 14px;
    color: #f8fafc !important;
}
.studio-header h1, .studio-header p {
    color: #f8fafc !important;
    margin: 0;
}
.studio-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    background: rgba(16, 185, 129, 0.22);
    border: 1px solid rgba(52, 211, 153, 0.5);
    color: #a7f3d0;
    margin-top: 8px;
}
.flow-exhausted-btn button {
    background: linear-gradient(90deg, #dc2626, #ea580c) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    border: none !important;
}
.primary-generate-btn button {
    background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 16px !important;
}
"""


def _format_hardware_markdown() -> str:
    hw = detect_hardware()
    ollama_list = ", ".join(hw.ollama_models) if hw.ollama_models else "Nenhum instalado / Ollama inativo"
    comfy_ckpts = ", ".join(hw.comfyui_checkpoints[:5]) if hw.comfyui_checkpoints else "ComfyUI inativo ou sem checkpoints"
    comfy_unets = ", ".join(hw.comfyui_unets[:5]) if hw.comfyui_unets else "Nenhum UNET Wan 2.2 detectado"
    warn_block = "\n".join(f"- ⚠️ {w}" for w in hw.warnings) if hw.warnings else "- ✅ Nenhum alerta crítico."

    return f"""### Diagnóstico Real do Computador
| Componente | Status / Valor |
|---|---|
| **CPU** | {hw.cpu_name} ({hw.cpu_cores} threads) |
| **GPU Detectada** | {hw.gpu_name} ({hw.gpu_vendor}) |
| **Memória VRAM** | {hw.gpu_vram_gb:.2f} GB {'(CUDA pronta)' if hw.cuda_available else '(Modo CPU / Fallback seguro)'} |
| **RAM Total / Livre** | {hw.ram_total_gb:.1f} GB / {hw.ram_available_gb:.1f} GB |
| **Espaço Livre em Disco** | {hw.disk_free_gb:.1f} GB |
| **FFmpeg** | {'✅ Pronto (' + Path(hw.ffmpeg_path).name + ')' if hw.ffmpeg_available and hw.ffmpeg_path else '❌ Não encontrado'} |
| **Blender 3D (Motor Real 3D)** | {'✅ ' + str(hw.blender_version) + ' pronto (EEVEE/Cycles PBR)' if hw.blender_available else '⚠️ Não instalado (instale gratuitamente em blender.org para animação 3D real)'} |
| **Ollama (Roteiro Local)** | {'✅ Ativo' if hw.ollama_available else '⏸️ Inativo'} — Modelos: `{ollama_list}` |
| **ComfyUI (Vídeo/Imagem Local)** | {'✅ Ativo' if hw.comfyui_available else '⏸️ Inativo'} |
| **Wan 2.2 TI2V-5B** | {'✅ Compatível com GPU' if hw.supports_wan22 else '🛡️ Bloqueado por segurança (exige GPU CUDA >= 12 GB VRAM)'} |
| **Difusão Imagem Local (ComfyUI)** | {'✅ Compatível' if hw.supports_local_image_ai else '🛡️ Usando renderizador Roblox CPU + FFmpeg'} |
| **Kokoro TTS (Voz PT-BR)** | {'✅ Instalado e pronto offline' if hw.kokoro_ready else '⬇️ Aguardando download (~115 MB)'} |
| **Whisper Local (Legendas)** | {'✅ Modelo em cache offline' if hw.whisper_ready else '⬇️ Aguardando primeiro download (~145 MB)'} |

**Resumo de Compatibilidade:** {hw.compatibility_summary}

**Modelos ComfyUI:** Checkpoints: `{comfy_ckpts}` | UNETs: `{comfy_unets}`

**Avisos e Recomendações:**
{warn_block}

> **Transparência de custos:** O modo **100% Gratuito** tem **R$ 0 em taxas de API, créditos ou assinaturas adicionais** — todo o processamento usa o seu computador (energia elétrica, hardware e espaço local).
"""


def _format_story_markdown(story: Optional[StoryDocument]) -> str:
    if not story:
        return "_Nenhum roteiro gerado ainda._"
    return (
        f"### {story.title}\n"
        f"**Provedor:** `{story.story_provider}` | **Gênero:** {story.genre} | **Abertura:** {story.opening_style}\n\n"
        f"- **Gancho:** {story.hook_pt}\n"
        f"- **Situação:** {story.setup_pt}\n"
        f"- **Desenvolvimento:** {story.development_pt}\n"
        f"- **Conflito:** {story.conflict_pt}\n"
        f"- **Clímax:** {story.climax_pt}\n"
        f"- **Reviravolta:** {story.twist_pt}\n"
        f"- **Final:** {story.ending_pt}\n\n"
        f"#### Narração Completa (PT-BR)\n> {story.full_narration_pt}"
    )


def _format_storyboard_table(storyboard: Optional[StoryboardDocument]) -> List[List[Any]]:
    if not storyboard:
        return []
    rows: List[List[Any]] = []
    for s in storyboard.scenes:
        rows.append(
            [
                s.scene_number,
                s.story_beat,
                s.title,
                s.narration_pt,
                s.expression,
                s.camera_movement,
                f"{s.duration_seconds:.1f}s",
                s.status,
                s.source_type.value,
            ]
        )
    return rows


def _format_flow_prompts_markdown(storyboard: Optional[StoryboardDocument], project_dir: Optional[str]) -> str:
    if not storyboard:
        return "_Gere ou carregue um projeto para visualizar os prompts do Google Flow._"
    cfg = load_settings()
    flow_url = cfg["generation"].get("flow_official_url", "https://labs.google/fx/tools/flow")
    refs_hint = str(Path(project_dir) / "references") if project_dir else "references"
    vids_hint = str(Path(project_dir) / "videos") if project_dir else "videos"
    lines = [
        f"### Instruções Oficiais do Google Flow",
        f"1. Acesse a interface oficial na conta autorizada: **{flow_url}**",
        f"2. Selecione formato **9:16 (Vertical)** e use as fichas em `{refs_hint}` como referência de personagem quando disponível.",
        f"3. Salve os vídeos gerados como `scene_01.mp4`, `scene_02.mp4`... em `{vids_hint}` ou faça upload abaixo.",
        "4. Acabaram os créditos? Clique no botão **MEUS CRÉDITOS DO FLOW ACABARAM** para continuar 100% grátis localmente sem perder as cenas já importadas!",
        "",
        "---",
    ]
    for s in storyboard.scenes:
        status_icon = "✅" if s.status == "ready" else "⏳"
        lines.extend(
            [
                f"#### {status_icon} Cena {s.scene_number:02d} — {s.title} (`scene_{s.scene_number:02d}.mp4` | ~{s.duration_seconds:.1f}s)",
                f"**Narração:** {s.narration_pt}",
                "```text",
                s.visual_prompt_en,
                "```",
            ]
        )
    return "\n".join(lines)


def _collect_reference_images(storyboard: Optional[StoryboardDocument]) -> List[Tuple[str, str]]:
    if not storyboard:
        return []
    items: List[Tuple[str, str]] = []
    for ch in storyboard.characters:
        if ch.reference_image_path and Path(ch.reference_image_path).exists():
            items.append((ch.reference_image_path, f"{ch.name} ({ch.role})"))
    return items


def _read_text_safe(path_str: Optional[str]) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


def build_ui() -> gr.Blocks:
    ensure_base_directories()
    pipeline = ProductionPipeline()
    pm = pipeline.pm
    cfg = load_settings()

    voice_choices = [(info["label"], code) for code, info in PT_BR_VOICES.items()]
    initial_projects = pm.list_projects()
    initial_flow_credits = bool(cfg["generation"].get("flow_credits_available", True))
    initial_mode_label = MODE_TO_LABEL.get(
        GenerationMode(cfg["generation"].get("default_mode", "local_free")),
        "100% Gratuito",
    )
    initial_style_label = STYLE_ID_TO_LABEL.get(
        cfg["generation"].get("default_visual_style", DEFAULT_VISUAL_STYLE_ID),
        list_visual_style_labels()[0],
    )

    def _pack_project_outputs(
        state: Optional[ProjectState],
        story: Optional[StoryDocument],
        storyboard: Optional[StoryboardDocument],
        banner_msg: str = "",
    ) -> Tuple[Any, ...]:
        projects = pm.list_projects()
        pid = state.project_id if state else (projects[0] if projects else None)
        flow_avail = state.flow_credits_available if state else bool(load_settings()["generation"]["flow_credits_available"])
        flow_badge = (
            "🟢 Créditos do Google Flow: **DISPONÍVEIS (SIM)**"
            if flow_avail
            else "🟠 Créditos do Google Flow: **ESGOTADOS (NÃO)** — Operando em modo 100% Gratuito Local (R$ 0)"
        )
        status_text = banner_msg or (
            f"Projeto `{state.project_id}` | Etapa: `{state.current_stage}` | Status: `{state.status}` | Progresso: {state.progress_percent:.0f}%"
            if state
            else "Pronto para criar um novo vídeo."
        )
        logs_text = "\n".join(state.logs[-60:]) if state and state.logs else ""
        sb_json = storyboard.model_dump_json(indent=2) if storyboard else ""
        narr_audio = state.narration_wav_path if (state and state.narration_wav_path and Path(state.narration_wav_path).exists()) else None
        srt_text = _read_text_safe(state.subtitles_srt_path if state else None)
        final_vid = state.final_video_path if (state and state.final_video_path and Path(state.final_video_path).exists()) else None
        output_folder = str(Path(state.project_dir) / "output") if state else ""

        sug_title = story.suggested_title if story else ""
        sug_desc = story.suggested_description if story else ""
        sug_tags = " ".join(story.suggested_hashtags) if story else ""

        return (
            gr.update(choices=projects, value=pid),
            status_text,
            logs_text,
            _format_story_markdown(story),
            _format_storyboard_table(storyboard),
            sb_json,
            _collect_reference_images(storyboard),
            flow_badge,
            flow_avail,
            _format_flow_prompts_markdown(storyboard, state.project_dir if state else None),
            get_flow_import_summary(storyboard),
            narr_audio,
            srt_text,
            final_vid,
            final_vid,
            output_folder,
            sug_title,
            sug_desc,
            sug_tags,
        )

    def on_generate_new_video(
        story_input: str,
        genre: str,
        opening_style: str,
        duration_sec: int,
        voice: str,
        speed: float,
        music_mood: str,
        visual_style_label: str,
        mode_label: str,
        flow_credits: bool,
        story_provider_label: str,
        gemini_api_key: str,
        offline_only: bool,
        auto_download_small: bool,
        progress: gr.Progress = gr.Progress(),
    ) -> Tuple[Any, ...]:
        if not story_input or not story_input.strip():
            return _pack_project_outputs(None, None, None, "⚠️ Digite ou cole uma história antes de gerar o vídeo.")

        mode = MODE_LABELS.get(mode_label, GenerationMode.AUTO_FLOW_FREE)
        visual_style_id = STYLE_LABEL_TO_ID.get(visual_style_label, DEFAULT_VISUAL_STYLE_ID)
        provider = STORY_PROVIDER_LABELS.get(story_provider_label, "auto")
        state = pm.create_project(
            story_input=story_input,
            genre=genre,
            opening_style=opening_style,
            duration_seconds=int(duration_sec),
            mode=mode,
            visual_style=visual_style_id,
            flow_credits_available=bool(flow_credits),
            voice=voice,
            speed=float(speed),
            music_mood=music_mood,
        )

        def cb(pct: float, msg: str) -> None:
            progress(min(1.0, max(0.0, pct / 100.0)), desc=msg)

        try:
            state, story, sb = pipeline.run_project(
                project_id=state.project_id,
                story_provider=provider,
                gemini_api_key=gemini_api_key or None,
                offline_only=bool(offline_only),
                auto_download_small_models=bool(auto_download_small),
                progress_cb=cb,
            )
            msg = (
                f"✅ Projeto {state.project_id} concluído! Vídeo 3D salvo em {state.final_video_path}"
                if state.status == "completed"
                else (
                    f"⏸️ PAUSADO aguardando vídeos do Google Flow ({state.project_id})! "
                    "Para gerar o vídeo AUTOMATICAMENTE agora em 3D no Blender, mude 'Modo de Geração' para '100% Gratuito' "
                    "ou clique no botão vermelho 'MEUS CRÉDITOS DO FLOW ACABARAM'."
                    if state.status == "awaiting_flow_import"
                    else f"⏸️ Projeto {state.project_id}: {state.status} — confira Logs."
                )
            )
            return _pack_project_outputs(state, story, sb, msg)
        except Exception as exc:
            st = pm.load_state(state.project_id)
            return _pack_project_outputs(
                st,
                pm.load_story(state.project_id),
                pm.load_storyboard(state.project_id),
                f"❌ Erro na geração ({state.project_id}): {exc}",
            )

    def on_resume_project(
        project_id: Optional[str],
        visual_style_label: str,
        mode_label: str,
        flow_credits: bool,
        story_provider_label: str,
        gemini_api_key: str,
        offline_only: bool,
        auto_download_small: bool,
        force_regen_scenes: bool,
        progress: gr.Progress = gr.Progress(),
    ) -> Tuple[Any, ...]:
        if not project_id:
            return _pack_project_outputs(None, None, None, "⚠️ Selecione um projeto salvo para continuar.")
        state = pm.load_state(project_id)
        state.mode = MODE_LABELS.get(mode_label, state.mode)
        state.visual_style = STYLE_LABEL_TO_ID.get(visual_style_label, state.visual_style)
        state.flow_credits_available = bool(flow_credits)
        pm.save_state(state)

        def cb(pct: float, msg: str) -> None:
            progress(min(1.0, max(0.0, pct / 100.0)), desc=msg)

        try:
            state, story, sb = pipeline.run_project(
                project_id=project_id,
                story_provider=STORY_PROVIDER_LABELS.get(story_provider_label, "auto"),
                gemini_api_key=gemini_api_key or None,
                offline_only=bool(offline_only),
                auto_download_small_models=bool(auto_download_small),
                force_regenerate_scenes=bool(force_regen_scenes),
                progress_cb=cb,
            )
            resume_msg = (
                f"✅ Projeto {project_id} concluído em 3D! Vídeo salvo em {state.final_video_path}"
                if state.status == "completed"
                else (
                    f"⏸️ PAUSADO aguardando clipes do Google Flow ({project_id})! "
                    "Para gerar AGORA em 3D no Blender sem esperar o Flow, selecione '100% Gratuito' em Modo de Geração "
                    "ou clique em 'MEUS CRÉDITOS DO FLOW ACABARAM'."
                    if state.status == "awaiting_flow_import"
                    else f"✅ Retomada de {project_id} finalizada (status: {state.status})."
                )
            )
            return _pack_project_outputs(
                state,
                story,
                sb,
                resume_msg,
            )
        except Exception as exc:
            st = pm.load_state(project_id)
            return _pack_project_outputs(
                st,
                pm.load_story(project_id),
                pm.load_storyboard(project_id),
                f"❌ Erro ao retomar {project_id}: {exc}",
            )

    def on_load_project(project_id: Optional[str]) -> Tuple[Any, ...]:
        if not project_id:
            return _pack_project_outputs(None, None, None, "Nenhum projeto selecionado.")
        try:
            st = pm.load_state(project_id)
            return _pack_project_outputs(
                st,
                pm.load_story(project_id),
                pm.load_storyboard(project_id),
                f"📂 Projeto `{project_id}` carregado (status: {st.status}, progresso: {st.progress_percent:.0f}%).",
            )
        except Exception as exc:
            return _pack_project_outputs(None, None, None, f"❌ Não foi possível carregar {project_id}: {exc}")

    def on_flow_credits_exhausted(
        project_id: Optional[str],
        offline_only: bool,
        auto_download_small: bool,
        progress: gr.Progress = gr.Progress(),
    ) -> Tuple[Any, ...]:
        state = pm.load_state(project_id) if project_id else None
        state, note = mark_flow_credits_exhausted(pm, state=state, persist_global=True)
        if state is None:
            return _pack_project_outputs(None, None, None, f"🔄 {note}")

        def cb(pct: float, msg: str) -> None:
            progress(min(1.0, max(0.0, pct / 100.0)), desc=msg)

        try:
            state, story, sb = pipeline.run_project(
                project_id=state.project_id,
                offline_only=bool(offline_only),
                auto_download_small_models=bool(auto_download_small),
                progress_cb=cb,
            )
            return _pack_project_outputs(
                state,
                story,
                sb,
                f"🔄 {note} Projeto `{state.project_id}` continuado automaticamente no modo local!",
            )
        except Exception as exc:
            st = pm.load_state(state.project_id)
            return _pack_project_outputs(
                st,
                pm.load_story(state.project_id),
                pm.load_storyboard(state.project_id),
                f"🔄 Modo gratuito ativado, mas ocorreu erro ao continuar: {exc}",
            )

    def on_cancel_generation(project_id: Optional[str]) -> str:
        if not project_id:
            return "Nenhum projeto ativo selecionado para cancelar."
        pm.request_cancel(project_id)
        return f"🛑 Cancelamento solicitado para `{project_id}`. Todas as etapas já concluídas permanecem salvas."

    def on_preview_voice(voice: str, speed: float, sample_text: str) -> Tuple[Optional[str], str]:
        txt = sample_text.strip() or "Neste servidor de Roblox existia uma regra que ninguém tinha coragem de quebrar!"
        preview_wav = resolve_path(load_settings()["paths"]["temp_dir"]) / f"preview_{voice}.wav"
        try:
            out, dur, _sr = pipeline.tts.synthesize_text(
                text=txt,
                output_wav=preview_wav,
                voice=voice,
                speed=float(speed),
                auto_download_if_missing=False,
            )
            return str(out), f"✅ Prévia gerada localmente ({dur:.1f}s) com a voz `{voice}`."
        except Exception as exc:
            return None, f"⚠️ {exc}"

    def on_import_single_clip(
        project_id: Optional[str],
        scene_num: int,
        uploaded_file: Optional[str],
        source_kind_label: str,
    ) -> Tuple[Any, ...]:
        if not project_id or not uploaded_file:
            return _pack_project_outputs(
                pm.load_state(project_id) if project_id else None,
                pm.load_story(project_id) if project_id else None,
                pm.load_storyboard(project_id) if project_id else None,
                "⚠️ Selecione um projeto e envie um arquivo de vídeo válido (MP4/MOV/MKV/WEBM).",
            )
        state = pm.load_state(project_id)
        sb = pm.load_storyboard(project_id)
        if sb is None:
            return _pack_project_outputs(state, pm.load_story(project_id), None, "⚠️ Gere o storyboard primeiro.")
        stype = (
            SceneSourceType.ROBLOX_STUDIO_IMPORT
            if "Roblox Studio" in source_kind_label
            else SceneSourceType.GOOGLE_FLOW_IMPORT
        )
        try:
            res = import_scene_video(Path(state.project_dir), sb, int(scene_num), uploaded_file, source_type=stype)
            pm.save_storyboard(project_id, sb)
            pm.append_log(state, f"Cena {int(scene_num):02d} importada ({stype.value}): {res['metadata']}")
            return _pack_project_outputs(
                state,
                pm.load_story(project_id),
                sb,
                f"✅ Cena {int(scene_num):02d} importada com sucesso ({res['metadata']})!",
            )
        except Exception as exc:
            return _pack_project_outputs(state, pm.load_story(project_id), sb, f"❌ Erro ao importar clipe: {exc}")

    def on_scan_videos_folder(project_id: Optional[str]) -> Tuple[Any, ...]:
        if not project_id:
            return _pack_project_outputs(None, None, None, "⚠️ Selecione um projeto primeiro.")
        state = pm.load_state(project_id)
        sb = pm.load_storyboard(project_id)
        if sb is None:
            return _pack_project_outputs(state, pm.load_story(project_id), None, "⚠️ Storyboard ainda não existe.")
        found = scan_and_import_video_folder(Path(state.project_dir), sb)
        pm.save_storyboard(project_id, sb)
        msg = (
            f"✅ Encontradas e importadas cenas: {found}"
            if found
            else f"ℹ️ Nenhum clipe novo encontrado em {Path(state.project_dir) / 'videos'}."
        )
        pm.append_log(state, msg)
        return _pack_project_outputs(state, pm.load_story(project_id), sb, msg)

    def on_download_local_models(progress: gr.Progress = gr.Progress()) -> Tuple[str, str]:
        msgs: List[str] = []
        try:
            progress(0.1, desc="Baixando Kokoro TTS PT-BR (~115 MB)...")
            pipeline.tts.download_kokoro_models(progress_cb=lambda m: msgs.append(m))
            progress(0.55, desc="Baixando modelo Whisper local (~145 MB)...")
            w_size = pipeline.subtitles.ensure_model_downloaded()
            msgs.append(f"Whisper local '{w_size}' pronto para uso 100% offline em models/whisper/.")
            progress(1.0, desc="Concluído!")
            return "\n".join(msgs), _format_hardware_markdown()
        except Exception as exc:
            return f"❌ Erro durante download dos modelos leves: {exc}", _format_hardware_markdown()

    def on_build_gemini_web_prompt(
        story_input: str,
        genre: str,
        opening_style: str,
        duration_sec: int,
        visual_style_label: str,
    ) -> str:
        visual_style_id = STYLE_LABEL_TO_ID.get(visual_style_label, DEFAULT_VISUAL_STYLE_ID)
        return build_master_llm_prompt(
            story_input=story_input or SAMPLE_STORY,
            genre=genre,
            opening_style=opening_style,
            duration_seconds=int(duration_sec),
            scene_count=max(6, min(10, int(round(int(duration_sec) / 7.0)))),
            visual_style=visual_style_id,
        )

    def on_import_gemini_web_json(
        raw_json: str,
        genre: str,
        opening_style: str,
        duration_sec: int,
        voice: str,
        speed: float,
        music_mood: str,
        visual_style_label: str,
        mode_label: str,
        flow_credits: bool,
    ) -> Tuple[Any, ...]:
        if not raw_json or not raw_json.strip():
            return _pack_project_outputs(None, None, None, "⚠️ Cole o JSON retornado pelo Gemini Web antes de importar.")
        try:
            visual_style_id = STYLE_LABEL_TO_ID.get(visual_style_label, DEFAULT_VISUAL_STYLE_ID)
            state = pm.create_project(
                story_input="Importado via Gemini Web (Google AI Pro)",
                genre=genre,
                opening_style=opening_style,
                duration_seconds=int(duration_sec),
                mode=MODE_LABELS.get(mode_label, GenerationMode.AUTO_FLOW_FREE),
                visual_style=visual_style_id,
                flow_credits_available=bool(flow_credits),
                voice=voice,
                speed=float(speed),
                music_mood=music_mood,
            )
            story_doc, sb_doc = parse_and_validate_llm_payload(
                raw_json,
                project_id=state.project_id,
                genre=genre,
                opening_style=opening_style,
                duration_seconds=int(duration_sec),
                provider_label="google_gemini_web_pro",
                visual_style=visual_style_id,
            )
            from app.character_consistency import apply_character_consistency, generate_character_reference_sheets
            from app.video_modes import prepare_flow_package

            sb_doc = apply_character_consistency(sb_doc, genre=genre)
            generate_character_reference_sheets(Path(state.project_dir), sb_doc)
            prepare_flow_package(Path(state.project_dir), story_doc, sb_doc)
            pm.save_story(state.project_id, story_doc)
            pm.save_storyboard(state.project_id, sb_doc)
            state.story_input = story_doc.full_narration_pt
            state.step_statuses["story"] = "done"
            state.step_statuses["storyboard"] = "done"
            state.step_statuses["references"] = "done"
            state.step_statuses["prompts"] = "done"
            pm.append_log(state, "Roteiro JSON do Gemini Web (Google AI Pro) validado e importado com sucesso!")
            return _pack_project_outputs(
                state,
                story_doc,
                sb_doc,
                f"✅ Roteiro do Gemini Web importado no projeto `{state.project_id}`! Clique em 'Continuar / Retomar Projeto' para narrar e renderizar.",
            )
        except Exception as exc:
            return _pack_project_outputs(None, None, None, f"❌ JSON inválido do Gemini Web: {exc}")

    drive_dir = get_drive_export_dir(cfg)
    colab_mode = is_colab_environment()
    drive_badge_html = (
        f'<span class="studio-badge" style="margin-left:8px;">☁️ Google Drive ativo: {drive_dir}</span>'
        if drive_dir
        else (
            '<span class="studio-badge" style="margin-left:8px;">☁️ Google Colab GPU ativo</span>'
            if colab_mode
            else ""
        )
    )

    with gr.Blocks(title="ROBLOX AI SHORTS STUDIO") as demo:
        gr.HTML(
            f"""
            <div class="studio-header">
              <h1>🎬 ROBLOX AI SHORTS STUDIO</h1>
              <p>Fábrica automatizada de vídeos verticais 9:16 de histórias de Roblox para YouTube Shorts e TikTok — Google Flow + 100% Gratuito Local</p>
              <span class="studio-badge">R$ 0 em APIs obrigatórias • Troca Automática Flow → Local • Português Brasileiro</span>
              {drive_badge_html}
            </div>
            """
        )

        with gr.Row():
            project_dropdown = gr.Dropdown(
                label="Projeto Ativo / Recuperar Projeto Salvo",
                choices=initial_projects,
                value=initial_projects[0] if initial_projects else None,
                scale=3,
            )
            btn_load_project = gr.Button("📂 Carregar Projeto", scale=1)
            btn_resume_project = gr.Button("▶️ Continuar / Retomar Projeto", variant="secondary", scale=2)
            btn_cancel = gr.Button("🛑 Cancelar Geração", variant="stop", scale=1)

        status_banner = gr.Textbox(
            label="Estado Atual da Produção",
            value="Pronto! Insira sua história abaixo e clique em GERAR VÍDEO.",
            interactive=False,
        )

        with gr.Tabs():
            # ================= ABA 1: PAINEL PRINCIPAL =================
            with gr.Tab("🎬 Painel Principal"):
                with gr.Row():
                    with gr.Column(scale=3):
                        story_input = gr.Textbox(
                            label="Sua História ou Ideia de Roblox (PT-BR)",
                            placeholder="Ex.: Neste servidor secreto, todos os jogadores recebem um número na cabeça e ninguém pode olhar para trás depois da meia-noite...",
                            lines=6,
                        )
                        btn_fill_sample = gr.Button("✨ Preencher com História de Exemplo", size="sm")

                        with gr.Row():
                            genre_dd = gr.Dropdown(label="Gênero / Estilo", choices=STORY_GENRES, value=STORY_GENRES[0])
                            opening_dd = gr.Dropdown(label="Estilo de Abertura", choices=STORY_OPENINGS, value=STORY_OPENINGS[0])
                            duration_slider = gr.Slider(
                                label="Duração Alvo (segundos)",
                                minimum=45,
                                maximum=60,
                                step=1,
                                value=int(cfg["generation"].get("default_duration_seconds", 55)),
                            )

                        with gr.Row():
                            voice_dd = gr.Dropdown(label="Voz da Narração (Local PT-BR)", choices=voice_choices, value=cfg["tts"].get("default_voice", "pm_alex"))
                            speed_slider = gr.Slider(label="Velocidade da Voz", minimum=0.80, maximum=1.35, step=0.05, value=float(cfg["tts"].get("default_speed", 1.05)))
                            music_dd = gr.Dropdown(label="Música Instrumental Gratuita", choices=MUSIC_CHOICES, value="suspense")

                        with gr.Row():
                            preview_text = gr.Textbox(
                                label="Texto para Prévia de Voz (opcional)",
                                value="Neste servidor existia uma regra que ninguém podia quebrar depois da meia-noite!",
                                scale=3,
                            )
                            btn_preview_voice = gr.Button("🔊 Gerar Prévia de Voz", scale=1)
                        preview_audio = gr.Audio(label="Prévia da Narração Local", type="filepath")
                        preview_status = gr.Markdown("")

                    with gr.Column(scale=2):
                        visual_style_dd = gr.Dropdown(
                            label="ESTILO VISUAL (Global — Padrão 3D Blender)",
                            choices=list_visual_style_labels(),
                            value=initial_style_label,
                        )
                        mode_radio = gr.Radio(
                            label="Modo de Geração",
                            choices=list(MODE_LABELS.keys()),
                            value=initial_mode_label,
                        )
                        flow_credits_chk = gr.Checkbox(
                            label="Créditos do Google Flow disponíveis (SIM / NÃO)",
                            value=initial_flow_credits,
                        )
                        with gr.Row(elem_classes=["flow-exhausted-btn"]):
                            btn_flow_exhausted_main = gr.Button("🚨 MEUS CRÉDITOS DO FLOW ACABARAM")

                        story_provider_dd = gr.Dropdown(
                            label="IA para Criação de Roteiro",
                            choices=list(STORY_PROVIDER_LABELS.keys()),
                            value=list(STORY_PROVIDER_LABELS.keys())[0],
                        )
                        gemini_key_tb = gr.Textbox(
                            label="Chave API Gemini (Opcional — apenas em memória, nunca salva em disco)",
                            type="password",
                            placeholder="Deixe vazio para usar Ollama + Gemma 3 ou modo offline",
                        )
                        gr.Markdown(
                            "_Nota: assinatura **Google AI Pro** no navegador é diferente de cota ilimitada na API Gemini. "
                            "Para usar sua assinatura Google AI Pro sem API, utilize a aba **Gemini Web (Google AI Pro)**._"
                        )
                        offline_chk = gr.Checkbox(label="Modo 100% Offline (usar somente modelos já instalados localmente)", value=False)
                        auto_dl_small_chk = gr.Checkbox(
                            label="Autorizar download automático dos modelos leves de voz/legendas (Kokoro ~115 MB + Whisper ~145 MB) se ausentes",
                            value=colab_mode,
                        )
                        force_regen_chk = gr.Checkbox(
                            label="Ao retomar projeto, regenerar cenas locais já prontas",
                            value=False,
                        )
                        with gr.Row(elem_classes=["primary-generate-btn"]):
                            btn_generate = gr.Button("🚀 GERAR VÍDEO", size="lg")

            # ================= ABA 2: CONTROLE DO FLOW =================
            with gr.Tab("🌊 Controle do Flow & Importação"):
                flow_status_md = gr.Markdown(
                    "🟢 Créditos do Google Flow: **DISPONÍVEIS (SIM)**"
                    if initial_flow_credits
                    else "🟠 Créditos do Google Flow: **ESGOTADOS (NÃO)** — Modo 100% Gratuito Local"
                )
                with gr.Row():
                    with gr.Column(elem_classes=["flow-exhausted-btn"]):
                        btn_flow_exhausted_tab = gr.Button("🚨 MEUS CRÉDITOS DO FLOW ACABARAM (Mudar para 100% Gratuito e Continuar)")
                    btn_scan_folder = gr.Button("🔍 Escanear Pasta videos/ do Projeto")

                flow_import_summary = gr.Textbox(label="Estado da Importação das Cenas", interactive=False, lines=2)

                with gr.Row():
                    import_scene_num = gr.Number(label="Número da Cena", value=1, minimum=1, maximum=15, precision=0)
                    import_source_type = gr.Radio(
                        label="Origem do Clipe",
                        choices=["Google Flow (Exportação Oficial)", "Gravação do Roblox Studio"],
                        value="Google Flow (Exportação Oficial)",
                    )
                    import_video_file = gr.File(label="Enviar Clipe da Cena (MP4/MOV/MKV/WEBM)", file_types=["video"])
                    btn_import_clip = gr.Button("📥 Importar Clipe para Cena")

                refs_gallery = gr.Gallery(label="Referências Visuais dos Personagens (Consistência)", columns=3, height=320)
                flow_prompts_md = gr.Markdown("_Os prompts organizados para o Google Flow aparecerão aqui._")

            # ================= ABA 3: GEMINI WEB (GOOGLE AI PRO) =================
            with gr.Tab("✨ Gemini Web (Google AI Pro)"):
                gr.Markdown(
                    "### Aproveite sua assinatura Google AI Pro pela interface oficial\n"
                    "Sem scraping, sem cookies e sem precisar pagar API:\n"
                    "1. Clique em **Gerar Prompt para Gemini Web**.\n"
                    "2. Copie e cole o prompt em [https://gemini.google.com](https://gemini.google.com).\n"
                    "3. Cole o JSON retornado abaixo e clique em **Validar e Importar Roteiro**."
                )
                btn_make_gemini_prompt = gr.Button("📋 Gerar Prompt para Gemini Web")
                gemini_prompt_out = gr.Code(label="Prompt Mestre para Copiar no Gemini Web", language="markdown")
                gemini_json_in = gr.Code(label="Cole aqui o JSON retornado pelo Gemini", language="json")
                btn_import_gemini_json = gr.Button("✅ Validar e Importar Roteiro do Gemini Web", variant="primary")

            # ================= ABA 4: PAINEL DE PRODUÇÃO =================
            with gr.Tab("📋 Painel de Produção"):
                story_md = gr.Markdown("_Nenhum roteiro gerado ainda._")
                storyboard_df = gr.Dataframe(
                    label="Storyboard das Cenas",
                    headers=["Cena", "Momento", "Título", "Narração (PT-BR)", "Expressão", "Câmera", "Duração", "Status", "Origem"],
                    interactive=False,
                )
                with gr.Row():
                    narration_audio_out = gr.Audio(label="Narração Completa (WAV)", type="filepath")
                    subtitles_preview = gr.Textbox(label="Legendas Sincronizadas (SRT)", lines=10, interactive=False)
                with gr.Accordion("Storyboard JSON Validado", open=False):
                    storyboard_json_out = gr.Code(language="json")
                logs_box = gr.Textbox(label="Logs de Execução em Tempo Real", lines=10, interactive=False)

            # ================= ABA 5: RESULTADO FINAL =================
            with gr.Tab("🏆 Resultado Final"):
                with gr.Row():
                    with gr.Column(scale=2):
                        final_video_player = gr.Video(label="Prévia do Vídeo Final (9:16 — 1080x1920)")
                        final_download_file = gr.File(label="Baixar MP4 Pronto para Publicar")
                    with gr.Column(scale=2):
                        output_dir_tb = gr.Textbox(label="Pasta onde o Vídeo foi Salvo", interactive=False)
                        suggested_title_tb = gr.Textbox(label="Título Sugerido (Shorts / TikTok)", interactive=True)
                        suggested_desc_tb = gr.Textbox(label="Descrição Sugerida", lines=4, interactive=True)
                        suggested_tags_tb = gr.Textbox(label="Hashtags Sugeridas", interactive=True)

            # ================= ABA 6: CONTROLE DO COMPUTADOR =================
            with gr.Tab("🖥️ Controle do Computador & Modelos"):
                hw_md = gr.Markdown(_format_hardware_markdown())
                with gr.Row():
                    btn_refresh_hw = gr.Button("🔄 Atualizar Diagnóstico de Hardware")
                    btn_download_models = gr.Button(
                        "⬇️ Baixar Modelos Locais Leves (Kokoro TTS ~115 MB + Whisper ~145 MB)",
                        variant="primary",
                    )
                model_download_status = gr.Textbox(
                    label="Status de Download dos Modelos Locais",
                    value="Os modelos só são baixados quando você clica no botão acima ou confirma no install.bat.",
                    interactive=False,
                    lines=4,
                )

        common_outputs = [
            project_dropdown,
            status_banner,
            logs_box,
            story_md,
            storyboard_df,
            storyboard_json_out,
            refs_gallery,
            flow_status_md,
            flow_credits_chk,
            flow_prompts_md,
            flow_import_summary,
            narration_audio_out,
            subtitles_preview,
            final_video_player,
            final_download_file,
            output_dir_tb,
            suggested_title_tb,
            suggested_desc_tb,
            suggested_tags_tb,
        ]

        btn_fill_sample.click(fn=lambda: SAMPLE_STORY, outputs=[story_input])
        btn_preview_voice.click(
            fn=on_preview_voice,
            inputs=[voice_dd, speed_slider, preview_text],
            outputs=[preview_audio, preview_status],
        )
        btn_generate.click(
            fn=on_generate_new_video,
            inputs=[
                story_input,
                genre_dd,
                opening_dd,
                duration_slider,
                voice_dd,
                speed_slider,
                music_dd,
                visual_style_dd,
                mode_radio,
                flow_credits_chk,
                story_provider_dd,
                gemini_key_tb,
                offline_chk,
                auto_dl_small_chk,
            ],
            outputs=common_outputs,
        )
        btn_load_project.click(fn=on_load_project, inputs=[project_dropdown], outputs=common_outputs)
        btn_resume_project.click(
            fn=on_resume_project,
            inputs=[
                project_dropdown,
                visual_style_dd,
                mode_radio,
                flow_credits_chk,
                story_provider_dd,
                gemini_key_tb,
                offline_chk,
                auto_dl_small_chk,
                force_regen_chk,
            ],
            outputs=common_outputs,
        )
        btn_cancel.click(fn=on_cancel_generation, inputs=[project_dropdown], outputs=[status_banner])

        btn_flow_exhausted_main.click(
            fn=on_flow_credits_exhausted,
            inputs=[project_dropdown, offline_chk, auto_dl_small_chk],
            outputs=common_outputs,
        )
        btn_flow_exhausted_tab.click(
            fn=on_flow_credits_exhausted,
            inputs=[project_dropdown, offline_chk, auto_dl_small_chk],
            outputs=common_outputs,
        )
        btn_import_clip.click(
            fn=on_import_single_clip,
            inputs=[project_dropdown, import_scene_num, import_video_file, import_source_type],
            outputs=common_outputs,
        )
        btn_scan_folder.click(fn=on_scan_videos_folder, inputs=[project_dropdown], outputs=common_outputs)

        btn_make_gemini_prompt.click(
            fn=on_build_gemini_web_prompt,
            inputs=[story_input, genre_dd, opening_dd, duration_slider, visual_style_dd],
            outputs=[gemini_prompt_out],
        )
        btn_import_gemini_json.click(
            fn=on_import_gemini_web_json,
            inputs=[
                gemini_json_in,
                genre_dd,
                opening_dd,
                duration_slider,
                voice_dd,
                speed_slider,
                music_dd,
                visual_style_dd,
                mode_radio,
                flow_credits_chk,
            ],
            outputs=common_outputs,
        )

        btn_refresh_hw.click(fn=_format_hardware_markdown, outputs=[hw_md])
        btn_download_models.click(fn=on_download_local_models, outputs=[model_download_status, hw_md])

    return demo


def launch_studio(
    host: Optional[str] = None,
    port: Optional[int] = None,
    open_browser: Optional[bool] = None,
    share: Optional[bool] = None,
) -> None:
    cfg = load_settings()
    colab = is_colab_environment()
    h = host or ("0.0.0.0" if colab else cfg["ui"].get("host", "127.0.0.1"))
    p = int(port or cfg["ui"].get("port", 7860))
    use_share = colab if share is None else bool(share)
    auto_open = (False if (colab or use_share) else cfg["ui"].get("open_browser", True)) if open_browser is None else open_browser

    allowed = {
        str(BASE_DIR),
        str(resolve_path(cfg["paths"]["projects_dir"])),
        str(resolve_path(cfg["paths"]["temp_dir"])),
    }
    drive_export = get_drive_export_dir(cfg)
    if drive_export:
        allowed.add(str(drive_export))

    demo = build_ui()
    if auto_open:
        threading.Timer(1.6, lambda: webbrowser.open(f"http://{h}:{p}")).start()

    demo.launch(
        server_name=h,
        server_port=p,
        inbrowser=False,
        share=use_share,
        allowed_paths=sorted(allowed),
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="indigo"),
        css=CUSTOM_CSS,
    )
