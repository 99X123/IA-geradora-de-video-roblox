"""Gerenciamento de projetos, persistência atômica, fila/cache de cenas, logs e recuperação de falhas."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar

from app.config import ensure_base_directories, load_settings, resolve_path
from app.models import (
    GenerationMode,
    ProjectState,
    SceneSpec,
    StoryboardDocument,
    StoryDocument,
)

T = TypeVar("T")

PROJECT_SUBDIRS = (
    "prompts",
    "references",
    "images",
    "videos",
    "audio",
    "subtitles",
    "output",
)


class ProjectCancelledError(RuntimeError):
    """Sinaliza cancelamento solicitado pelo usuário preservando progresso salvo."""


class ProjectManager:
    """Controla criação, salvamento automático, recuperação, logs e cache de projetos."""

    def __init__(self, settings: Optional[Dict] = None) -> None:
        self.settings = settings or load_settings()
        ensure_base_directories(self.settings)
        self.projects_root = resolve_path(self.settings["paths"]["projects_dir"])
        self.logs_root = resolve_path(self.settings["paths"]["logs_dir"])
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("roblox_ai_shorts_studio")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            log_file = self.logs_root / "studio.log"
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(fh)
        return logger

    def next_project_id(self) -> str:
        existing_nums: List[int] = []
        if self.projects_root.exists():
            for child in self.projects_root.iterdir():
                if child.is_dir():
                    m = re.match(r"^project_(\d+)$", child.name)
                    if m:
                        existing_nums.append(int(m.group(1)))
        next_num = (max(existing_nums) + 1) if existing_nums else 1
        return f"project_{next_num:03d}"

    def create_project(
        self,
        story_input: str,
        genre: str = "Suspense / Mistério",
        opening_style: str = "Neste servidor...",
        duration_seconds: int = 55,
        mode: GenerationMode = GenerationMode.AUTO_FLOW_FREE,
        visual_style: str = "roblox_3d_blender_cinematic",
        flow_credits_available: bool = True,
        voice: str = "pm_alex",
        speed: float = 1.05,
        music_mood: str = "suspense",
        project_id: Optional[str] = None,
    ) -> ProjectState:
        pid = project_id or self.next_project_id()
        project_dir = self.projects_root / pid
        project_dir.mkdir(parents=True, exist_ok=True)
        for sub in PROJECT_SUBDIRS:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

        state = ProjectState(
            project_id=pid,
            project_dir=str(project_dir),
            mode=mode,
            visual_style=visual_style,
            flow_credits_available=flow_credits_available,
            story_input=story_input.strip(),
            genre=genre,
            opening_style=opening_style,
            duration_seconds=duration_seconds,
            voice=voice,
            speed=speed,
            music_mood=music_mood,
            current_stage="initialized",
            status="idle",
            progress_percent=0.0,
        )
        self.save_state(state)
        self.append_log(state, f"Projeto {pid} criado em {project_dir}")
        return state

    def get_project_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def list_projects(self) -> List[str]:
        if not self.projects_root.exists():
            return []
        ids = [
            d.name
            for d in self.projects_root.iterdir()
            if d.is_dir() and (d / "project_state.json").exists()
        ]
        return sorted(ids, reverse=True)

    def _atomic_write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            tmp = path.with_suffix(f"{path.suffix}.{threading.get_ident()}.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            for attempt in range(6):
                try:
                    tmp.replace(path)
                    return
                except PermissionError:
                    if attempt == 5:
                        # Fallback seguro em Windows quando outro processo lê o arquivo no mesmo instante
                        with path.open("w", encoding="utf-8") as fh:
                            json.dump(payload, fh, indent=2, ensure_ascii=False)
                        tmp.unlink(missing_ok=True)
                        return
                    time.sleep(0.06 * (attempt + 1))

    def save_state(self, state: ProjectState) -> None:
        state.updated_at = datetime.now(timezone.utc).isoformat()
        state_file = Path(state.project_dir) / "project_state.json"
        self._atomic_write_json(state_file, state.model_dump(mode="json"))

    def load_state(self, project_id: str) -> ProjectState:
        state_file = self.get_project_dir(project_id) / "project_state.json"
        if not state_file.exists():
            raise FileNotFoundError(f"Estado do projeto '{project_id}' não encontrado em {state_file}")
        with state_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        state = ProjectState.model_validate(data)
        # Garante diretório atualizado caso a pasta tenha sido movida
        state.project_dir = str(self.get_project_dir(project_id))
        return state

    def save_story(self, project_id: str, story: StoryDocument) -> Path:
        story_file = self.get_project_dir(project_id) / "story.json"
        self._atomic_write_json(story_file, story.model_dump(mode="json"))
        return story_file

    def load_story(self, project_id: str) -> Optional[StoryDocument]:
        story_file = self.get_project_dir(project_id) / "story.json"
        if not story_file.exists():
            return None
        with story_file.open("r", encoding="utf-8") as fh:
            return StoryDocument.model_validate(json.load(fh))

    def save_storyboard(self, project_id: str, storyboard: StoryboardDocument) -> Path:
        sb_file = self.get_project_dir(project_id) / "storyboard.json"
        self._atomic_write_json(sb_file, storyboard.model_dump(mode="json"))
        return sb_file

    def load_storyboard(self, project_id: str) -> Optional[StoryboardDocument]:
        sb_file = self.get_project_dir(project_id) / "storyboard.json"
        if not sb_file.exists():
            return None
        with sb_file.open("r", encoding="utf-8") as fh:
            return StoryboardDocument.model_validate(json.load(fh))

    def append_log(self, state: ProjectState, message: str, level: str = "INFO") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] [{level}] {message}"
        state.logs.append(line)
        if len(state.logs) > 250:
            state.logs = state.logs[-250:]
        self.save_state(state)
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{state.project_id}] {message}")

    def is_scene_ready(self, scene: SceneSpec) -> bool:
        """Verifica cache real: a cena só é reaproveitada se o arquivo de vídeo existir e não estiver vazio."""
        if scene.status != "ready" or not scene.video_path:
            return False
        p = Path(scene.video_path)
        return p.exists() and p.is_file() and p.stat().st_size > 1024

    def request_cancel(self, project_id: str) -> None:
        with self._lock:
            ev = self._cancel_events.setdefault(project_id, threading.Event())
            ev.set()
        try:
            state = self.load_state(project_id)
            state.cancelled = True
            if state.status == "running":
                state.status = "cancelled"
            self.append_log(state, "Cancelamento solicitado pelo usuário. Progresso preservado.", level="WARNING")
        except Exception:
            pass

    def reset_cancel(self, project_id: str) -> None:
        with self._lock:
            ev = self._cancel_events.setdefault(project_id, threading.Event())
            ev.clear()

    def check_cancelled(self, state: ProjectState) -> None:
        with self._lock:
            ev = self._cancel_events.get(state.project_id)
            if (ev and ev.is_set()) or state.cancelled:
                state.status = "cancelled"
                self.save_state(state)
                raise ProjectCancelledError(f"Geração do projeto {state.project_id} cancelada pelo usuário.")

    def run_with_retries(
        self,
        state: ProjectState,
        task_name: str,
        fn: Callable[[], T],
        max_retries: int = 2,
    ) -> T:
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 2):
            self.check_cancelled(state)
            try:
                return fn()
            except ProjectCancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                self.append_log(
                    state,
                    f"Tentativa {attempt}/{max_retries + 1} falhou em '{task_name}': {exc}",
                    level="WARNING",
                )
        assert last_exc is not None
        raise last_exc
