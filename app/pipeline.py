"""Orquestrador principal do pipeline automatizado com fila, cache, auto-salvamento, retentativas e recuperação."""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.audio_assets import ensure_default_audio_assets
from app.blender_renderer import render_scene_3d_blender
from app.character_consistency import apply_character_consistency, generate_character_reference_sheets
from app.comfyui_client import ComfyUIClient
from app.config import get_drive_export_dir, load_settings
from app.fallback_renderer import animate_images_to_clip, render_procedural_roblox_scene_images
from app.hardware import detect_hardware
from app.models import (
    GenerationMode,
    HardwareReport,
    ProjectState,
    SceneSourceType,
    StoryboardDocument,
    StoryDocument,
)
from app.project_manager import ProjectCancelledError, ProjectManager
from app.story_engine import generate_story_and_storyboard
from app.subtitle_engine import WhisperSubtitleEngine
from app.tts_engine import LocalTTSEngine
from app.video_editor import render_final_short
from app.video_modes import (
    prepare_flow_package,
    scan_and_import_video_folder,
    should_use_flow,
)

ProgressCallback = Callable[[float, str], None]


class ProductionPipeline:
    """
    Controla ponta a ponta toda a produção de um vídeo de Roblox Shorts:
    História -> Storyboard -> Referências -> Prompts Flow -> Narração Local ->
    Legendas Whisper -> Cenas (Flow / Wan 2.2 / ComfyUI Img / Fallback CPU) -> Edição FFmpeg MP4.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        self.settings = settings or load_settings()
        self.pm = ProjectManager(self.settings)
        self.tts = LocalTTSEngine(self.settings)
        self.subtitles = WhisperSubtitleEngine(self.settings)
        self.comfyui = ComfyUIClient(self.settings)
        ensure_default_audio_assets(self.settings)

    def _emit(
        self,
        state: ProjectState,
        percent: float,
        message: str,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> None:
        state.progress_percent = round(percent, 1)
        self.pm.append_log(state, message)
        if progress_cb:
            progress_cb(percent, message)

    def _load_or_init_timings(self, project_dir: Path, storyboard: StoryboardDocument) -> List[Dict[str, float | int]]:
        timings_file = project_dir / "audio" / "scene_timings.json"
        if timings_file.exists():
            try:
                return json.loads(timings_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        cursor = 0.0
        fallback_timings: List[Dict[str, float | int]] = []
        for s in storyboard.scenes:
            dur = float(s.duration_seconds)
            fallback_timings.append(
                {
                    "scene_number": s.scene_number,
                    "start": round(cursor, 3),
                    "end": round(cursor + dur, 3),
                    "duration": round(dur, 3),
                }
            )
            cursor += dur
        return fallback_timings

    def run_project(
        self,
        project_id: str,
        story_provider: str = "auto",
        gemini_api_key: Optional[str] = None,
        offline_only: bool = False,
        auto_download_small_models: bool = False,
        force_regenerate_scenes: bool = False,
        hardware: Optional[HardwareReport] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> Tuple[ProjectState, Optional[StoryDocument], Optional[StoryboardDocument]]:
        """
        Executa ou retoma um projeto a partir do último ponto salvo.
        Nunca regenera etapas ou cenas já prontas em cache, salvo solicitação explícita.
        """
        self.pm.reset_cancel(project_id)
        state = self.pm.load_state(project_id)
        state.cancelled = False
        state.status = "running"
        state.last_error = None
        self.pm.save_state(state)

        project_dir = Path(state.project_dir)
        hw = hardware or detect_hardware(self.settings)

        try:
            # --- ETAPA 1 & 2: HISTÓRIA + STORYBOARD ---
            self.pm.check_cancelled(state)
            story = self.pm.load_story(project_id)
            storyboard = self.pm.load_storyboard(project_id)

            if story is None or storyboard is None:
                state.current_stage = "story"
                self._emit(state, 8.0, "Gerando roteiro estruturado e storyboard de cenas...", progress_cb)
                force_local = offline_only or (state.mode == GenerationMode.LOCAL_FREE)
                story, storyboard, notes = self.pm.run_with_retries(
                    state,
                    "geração de roteiro",
                    lambda: generate_story_and_storyboard(
                        story_input=state.story_input,
                        project_id=project_id,
                        genre=state.genre,
                        opening_style=state.opening_style,
                        duration_seconds=state.duration_seconds,
                        visual_style=state.visual_style,
                        preferred_provider=story_provider,
                        force_local_only=force_local,
                        gemini_api_key=gemini_api_key,
                        settings=self.settings,
                    ),
                    max_retries=int(self.settings["story_ai"].get("max_retries", 2)),
                )
                for note in notes:
                    self.pm.append_log(state, note)

                storyboard = apply_character_consistency(storyboard, genre=state.genre)
                self.pm.save_story(project_id, story)
                self.pm.save_storyboard(project_id, storyboard)
                state.step_statuses["story"] = "done"
                state.step_statuses["storyboard"] = "done"
                self.pm.save_state(state)
            else:
                self._emit(state, 12.0, "Roteiro e storyboard recuperados do cache do projeto.", progress_cb)
                state.step_statuses["story"] = "done"
                state.step_statuses["storyboard"] = "done"

            # --- ETAPA 3: REFERÊNCIAS VISUAIS DOS PERSONAGENS ---
            self.pm.check_cancelled(state)
            state.current_stage = "references"
            refs_missing = any(
                not ch.reference_image_path or not Path(ch.reference_image_path).exists()
                for ch in storyboard.characters
            )
            if refs_missing or state.step_statuses.get("references") != "done":
                self._emit(state, 18.0, "Gerando fichas visuais 3D de consistência dos personagens...", progress_cb)
                refs = generate_character_reference_sheets(project_dir, storyboard, settings=self.settings)
                self.pm.save_storyboard(project_id, storyboard)
                state.step_statuses["references"] = "done"
                self._emit(state, 22.0, f"{len(refs)} ficha(s) de referência salvas em references/.", progress_cb)
            else:
                self._emit(state, 22.0, "Referências visuais de personagens recuperadas do cache.", progress_cb)

            # --- ETAPA 4: PACOTE DE PROMPTS (SEMPRE GERADO PARA TRANSPARÊNCIA E FLOW) ---
            self.pm.check_cancelled(state)
            state.current_stage = "prompts"
            instructions_md = project_dir / "prompts" / "flow_instructions.md"
            if not instructions_md.exists() or state.step_statuses.get("prompts") != "done":
                self._emit(state, 26.0, "Preparando prompts individuais e instruções para Google Flow...", progress_cb)
                prepare_flow_package(
                    project_dir=project_dir,
                    story=story,
                    storyboard=storyboard,
                    flow_url=self.settings["generation"].get("flow_official_url", "https://labs.google/fx/tools/flow"),
                )
                self.pm.save_storyboard(project_id, storyboard)
                state.step_statuses["prompts"] = "done"
                self.pm.save_state(state)

            # --- ETAPA 5: NARRAÇÃO LOCAL EM PT-BR (KOKORO TTS) ---
            self.pm.check_cancelled(state)
            state.current_stage = "narration"
            narration_wav = project_dir / "audio" / "narration.wav"
            timings_file = project_dir / "audio" / "scene_timings.json"

            if not narration_wav.exists() or not timings_file.exists() or state.step_statuses.get("narration") != "done":
                self._emit(state, 32.0, f"Gerando narração local em PT-BR (voz: {state.voice})...", progress_cb)
                narration_wav, scene_timings = self.pm.run_with_retries(
                    state,
                    "narração local TTS",
                    lambda: self.tts.synthesize_storyboard_narration(
                        storyboard=storyboard,
                        audio_dir=project_dir / "audio",
                        voice=state.voice,
                        base_speed=state.speed,
                        auto_download_if_missing=(auto_download_small_models and not offline_only),
                    ),
                    max_retries=1,
                )
                timings_file.write_text(json.dumps(scene_timings, indent=2), encoding="utf-8")
                self.pm.save_storyboard(project_id, storyboard)
                state.narration_wav_path = str(narration_wav)
                state.step_statuses["narration"] = "done"
                self._emit(state, 42.0, f"Narração concluída: {narration_wav.name}", progress_cb)
            else:
                scene_timings = self._load_or_init_timings(project_dir, storyboard)
                state.narration_wav_path = str(narration_wav)
                self._emit(state, 42.0, "Narração local recuperada do cache.", progress_cb)

            # --- ETAPA 6: LEGENDAS AUTOMÁTICAS LOCAIS (WHISPER) ---
            self.pm.check_cancelled(state)
            state.current_stage = "subtitles"
            srt_path = project_dir / "subtitles" / "captions.srt"
            ass_path = project_dir / "subtitles" / "captions.ass"

            if not srt_path.exists() or not ass_path.exists() or state.step_statuses.get("subtitles") != "done":
                self._emit(state, 48.0, "Transcrevendo áudio real com Whisper local para gerar legendas SRT/ASS...", progress_cb)
                srt_path, ass_path, chunks = self.pm.run_with_retries(
                    state,
                    "legendas locais Whisper",
                    lambda: self.subtitles.generate_subtitles(
                        audio_wav=narration_wav,
                        subtitles_dir=project_dir / "subtitles",
                        script_hint=story.full_narration_pt,
                        offline_only=offline_only,
                    ),
                    max_retries=1,
                )
                state.subtitles_srt_path = str(srt_path)
                state.subtitles_ass_path = str(ass_path)
                state.step_statuses["subtitles"] = "done"
                self._emit(state, 56.0, f"Legendas sincronizadas geradas ({len(chunks)} blocos em SRT e ASS).", progress_cb)
            else:
                state.subtitles_srt_path = str(srt_path)
                state.subtitles_ass_path = str(ass_path)
                self._emit(state, 56.0, "Legendas SRT e ASS recuperadas do cache.", progress_cb)

            # --- ETAPA 7: PRODUÇÃO / IMPORTAÇÃO DAS CENAS ---
            self.pm.check_cancelled(state)
            state.current_stage = "scenes"
            newly_found = scan_and_import_video_folder(project_dir, storyboard)
            if newly_found:
                self.pm.save_storyboard(project_id, storyboard)
                self.pm.append_log(state, f"Clipes importados automaticamente da pasta videos/: cenas {newly_found}")

            if force_regenerate_scenes:
                for sc in storyboard.scenes:
                    if sc.source_type not in (SceneSourceType.GOOGLE_FLOW_IMPORT, SceneSourceType.ROBLOX_STUDIO_IMPORT):
                        sc.status = "pending"
                        sc.video_path = None

            # Se o Blender 3D está ativo e strict_3d_no_2d_fallback=True, substitui automaticamente
            # quaisquer cenas antigas geradas no fallback 2D feio por renderização 3D REAL do Blender!
            strict_3d = bool(self.settings.get("blender", {}).get("strict_3d_no_2d_fallback", True))
            if strict_3d and hw.blender_available and self.settings.get("blender", {}).get("enabled", True):
                upgraded_2d = []
                for sc in storyboard.scenes:
                    if sc.source_type == SceneSourceType.FALLBACK_PROCEDURAL_ANIMATED:
                        sc.status = "pending"
                        sc.video_path = None
                        upgraded_2d.append(sc.scene_number)
                if upgraded_2d:
                    self.pm.append_log(
                        state,
                        f"Cenas antigas em 2D detectadas ({upgraded_2d}): marcadas para refazer em 3D REAL no Blender!",
                    )
                    self.pm.save_storyboard(project_id, storyboard)

            pending_scenes = [s for s in storyboard.scenes if not self.pm.is_scene_ready(s)]

            # Se modo Google Flow está ativo (Modo A ou Modo C com créditos disponíveis) e ainda faltam cenas:
            if should_use_flow(state) and pending_scenes:
                for sc in pending_scenes:
                    sc.status = "awaiting_flow"
                self.pm.save_storyboard(project_id, storyboard)
                state.status = "awaiting_flow_import"
                state.step_statuses["scenes"] = "awaiting_flow"
                pending_nums = ", ".join(f"{s.scene_number:02d}" for s in pending_scenes)
                self._emit(
                    state,
                    65.0,
                    f"Pacote Google Flow pronto! Aguardando importação das cenas [{pending_nums}] em {project_dir / 'videos'}. "
                    "Gere na interface oficial do Flow e importe os clipes — ou clique em 'MEUS CRÉDITOS DO FLOW ACABARAM' para concluir no modo 100% gratuito local.",
                    progress_cb,
                )
                return state, story, storyboard

            # Caso contrário: gera TODAS as cenas pendentes localmente (100% Gratuito) respeitando limites do hardware!
            total_to_gen = len(pending_scenes)
            for idx, scene in enumerate(pending_scenes, start=1):
                self.pm.check_cancelled(state)
                pct = 58.0 + (26.0 * (idx - 1) / max(1, total_to_gen))
                self._emit(
                    state,
                    pct,
                    f"Produzindo cena {scene.scene_number:02d}/{len(storyboard.scenes):02d} localmente ({hw.recommended_tier})...",
                    progress_cb,
                )
                self._produce_local_scene(project_dir, storyboard, scene, hw, state)
                self.pm.save_storyboard(project_id, storyboard)

            state.step_statuses["scenes"] = "done"
            self.pm.save_state(state)

            # --- ETAPA 8: EDITOR AUTOMÁTICO FFMPEG + EXPORTAÇÃO MP4 ---
            self.pm.check_cancelled(state)
            state.current_stage = "render"
            self._emit(state, 88.0, "Montando vídeo final 1080x1920 (9:16) no FFmpeg com áudio, efeitos e legendas...", progress_cb)

            final_mp4, meta = self.pm.run_with_retries(
                state,
                "renderização final FFmpeg",
                lambda: render_final_short(
                    project_dir=project_dir,
                    storyboard=storyboard,
                    narration_wav=narration_wav,
                    subtitles_ass=ass_path,
                    scene_timings=scene_timings,
                    music_mood=state.music_mood,
                    settings=self.settings,
                ),
                max_retries=1,
            )

            state.final_video_path = str(final_mp4)
            drive_copy = self._export_to_google_drive(final_mp4, state, story, srt_path)
            state.step_statuses["render"] = "done"
            state.current_stage = "completed"
            state.status = "completed"
            drive_note = f" | Cópia no Google Drive: {drive_copy}" if drive_copy else ""
            self._emit(
                state,
                100.0,
                f"Vídeo finalizado com sucesso! {final_mp4.name} "
                f"({meta.get('width')}x{meta.get('height')}, {meta.get('duration')}s, {meta.get('fps')} fps).{drive_note}",
                progress_cb,
            )
            return state, story, storyboard

        except ProjectCancelledError as exc:
            state.status = "cancelled"
            state.last_error = str(exc)
            self.pm.save_state(state)
            return state, self.pm.load_story(project_id), self.pm.load_storyboard(project_id)
        except Exception as exc:
            state.status = "error"
            state.last_error = str(exc)
            self.pm.append_log(state, f"Erro no pipeline: {exc}", level="ERROR")
            self.pm.save_state(state)
            raise

    def _export_to_google_drive(
        self,
        final_mp4: Path,
        state: ProjectState,
        story: Optional[StoryDocument],
        srt_path: Optional[Path],
    ) -> Optional[Path]:
        """Copia o MP4 pronto e um arquivo .txt com título/descrição/hashtags para a pasta do Google Drive."""
        export_dir = get_drive_export_dir(self.settings)
        if not export_dir or not final_mp4.exists():
            return None
        try:
            raw_title = (story.title if story else state.project_id) or state.project_id
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_title.strip()).strip("_")[:48] or "video"
            dest_mp4 = export_dir / f"{state.project_id}_{slug}.mp4"
            shutil.copy2(final_mp4, dest_mp4)

            info_txt = export_dir / f"{state.project_id}_{slug}_post.txt"
            info_lines = [
                f"Projeto: {state.project_id}",
                f"Título sugerido: {story.suggested_title if story else raw_title}",
                "",
                "Descrição sugerida:",
                story.suggested_description if story else "",
                "",
                "Hashtags:",
                " ".join(story.suggested_hashtags) if story else "",
                "",
                "Narração completa (PT-BR):",
                story.full_narration_pt if story else "",
            ]
            info_txt.write_text("\n".join(info_lines), encoding="utf-8")
            if srt_path and srt_path.exists():
                shutil.copy2(srt_path, export_dir / f"{state.project_id}_{slug}.srt")
            self.pm.append_log(state, f"Vídeo salvo automaticamente no Google Drive: {dest_mp4}")
            return dest_mp4
        except Exception as exc:
            self.pm.append_log(state, f"Aviso: falha ao copiar vídeo para pasta Drive ({exc}).", level="WARNING")
            return None

    def _produce_local_scene(
        self,
        project_dir: Path,
        storyboard: StoryboardDocument,
        scene: Any,
        hw: HardwareReport,
        state: ProjectState,
    ) -> None:
        dest_mp4 = project_dir / "videos" / f"scene_{scene.scene_number:02d}.mp4"
        images_dir = project_dir / "images"

        # Tier 2: ComfyUI + Wan 2.2 TI2V-5B (somente se GPU suportar >= 12 GB VRAM CUDA)
        if hw.supports_wan22 and hw.comfyui_available:
            try:
                lead_ref: Optional[Path] = None
                if storyboard.characters and storyboard.characters[0].reference_image_path:
                    p = Path(storyboard.characters[0].reference_image_path)
                    if p.exists():
                        lead_ref = p
                self.comfyui.generate_scene_video_wan22(
                    scene=scene,
                    dest_mp4=dest_mp4,
                    hardware=hw,
                    reference_image=lead_ref,
                    cancel_check=lambda: self.pm.check_cancelled(state),
                )
                scene.video_path = str(dest_mp4)
                scene.status = "ready"
                scene.source_type = SceneSourceType.COMFYUI_WAN22
                return
            except Exception as exc:
                self.pm.append_log(
                    state,
                    f"Wan 2.2 indisponível na cena {scene.scene_number:02d} ({exc}). Alternando para plano de imagens animadas.",
                    level="WARNING",
                )

        # Tier 2B: Renderização 3D REAL no Blender (EEVEE/Cycles/3D Keyframes) — NUNCA cai em 2D feio!
        blender_cfg = self.settings.get("blender", {})
        strict_3d = bool(blender_cfg.get("strict_3d_no_2d_fallback", True))
        if hw.blender_available and blender_cfg.get("enabled", True):
            try:
                render_scene_3d_blender(
                    scene=scene,
                    storyboard=storyboard,
                    dest_mp4=dest_mp4,
                    visual_style_id=state.visual_style,
                    settings=self.settings,
                )
                scene.video_path = str(dest_mp4)
                scene.status = "ready"
                scene.source_type = SceneSourceType.BLENDER_3D_RENDER
                return
            except Exception as exc:
                self.pm.append_log(
                    state,
                    f"Renderização 3D Blender falhou na cena {scene.scene_number:02d}: {exc}",
                    level="ERROR" if strict_3d else "WARNING",
                )
                if strict_3d:
                    raise RuntimeError(
                        f"Modo 3D obrigatório ativo (sem fallback 2D): Blender 3D falhou na cena {scene.scene_number:02d}. "
                        f"Detalhe: {exc}"
                    ) from exc

        # Tier 3: ComfyUI imagem local (GPUs 4–11 GB VRAM) + animação FFmpeg
        generated_images: List[Path] = []
        if hw.supports_local_image_ai and hw.comfyui_available:
            try:
                for f_idx in range(2):
                    img_out = images_dir / f"scene_{scene.scene_number:02d}_ai_{f_idx + 1:02d}.png"
                    self.comfyui.generate_scene_image(
                        scene=scene,
                        dest_png=img_out,
                        hardware=hw,
                        seed_offset=f_idx * 17,
                        cancel_check=lambda: self.pm.check_cancelled(state),
                    )
                    generated_images.append(img_out)
                animate_images_to_clip(
                    image_paths=generated_images,
                    dest_mp4=dest_mp4,
                    duration_seconds=float(scene.duration_seconds),
                    camera_movement=scene.camera_movement,
                    settings=self.settings,
                )
                scene.image_paths = [str(p) for p in generated_images]
                scene.video_path = str(dest_mp4)
                scene.status = "ready"
                scene.source_type = SceneSourceType.COMFYUI_IMAGE_ANIMATED
                return
            except Exception as exc:
                self.pm.append_log(
                    state,
                    f"Geração de imagem ComfyUI falhou na cena {scene.scene_number:02d} ({exc}). Usando renderizador CPU.",
                    level="WARNING",
                )

        # Tier 4: Plano Alternativo Computador Fraco (CPU local + animação cinematográfica FFmpeg)
        # Reaproveita imagens customizadas já existentes se o usuário tiver importado imagens para a cena
        existing_imgs = [Path(p) for p in scene.image_paths if Path(p).exists()]
        if existing_imgs:
            img_paths = existing_imgs
            source_kind = SceneSourceType.USER_IMAGE_ANIMATED
        else:
            img_paths = render_procedural_roblox_scene_images(
                scene=scene,
                storyboard=storyboard,
                images_dir=images_dir,
                frames_per_scene=2,
            )
            source_kind = SceneSourceType.FALLBACK_PROCEDURAL_ANIMATED

        animate_images_to_clip(
            image_paths=img_paths,
            dest_mp4=dest_mp4,
            duration_seconds=float(scene.duration_seconds),
            camera_movement=scene.camera_movement,
            settings=self.settings,
        )
        scene.image_paths = [str(p) for p in img_paths]
        scene.video_path = str(dest_mp4)
        scene.status = "ready"
        scene.source_type = source_kind


class ProductionQueue:
    """Fila leve de produção em segundo plano em Python puro (sem exigir n8n)."""

    def __init__(self, pipeline: ProductionPipeline) -> None:
        self.pipeline = pipeline
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._history: List[Dict[str, Any]] = []
        self._worker = threading.Thread(target=self._run_loop, daemon=True, name="studio-queue-worker")
        self._worker.start()

    def enqueue(self, project_id: str, **kwargs: Any) -> Dict[str, Any]:
        item = {"project_id": project_id, "status": "queued", "kwargs": kwargs}
        self._history.append(item)
        self._queue.put(item)
        return item

    def list_items(self) -> List[Dict[str, Any]]:
        return [{"project_id": i["project_id"], "status": i["status"]} for i in self._history[-20:]]

    def _run_loop(self) -> None:
        while True:
            item = self._queue.get()
            item["status"] = "running"
            try:
                self.pipeline.run_project(item["project_id"], **item["kwargs"])
                item["status"] = "done"
            except Exception as exc:
                item["status"] = f"error: {exc}"
            finally:
                self._queue.task_done()
