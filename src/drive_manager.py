"""AutoShorts AI — Google Drive Mounting, Folder Tree Management & Safe Artifact Sync.

Creates the standard hierarchy inside `Meu Drive/AutoShorts AI/`:
  Videos/ Projects/ Audio/ Scripts/ Storyboards/ Subtitles/ Logs/ Reports/ Backups/

Security guarantee: NEVER copies API keys, `.env`, credentials JSON, keys, or tokens
to Google Drive, and redacts any secret strings from text/JSON logs before uploading.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import AutoShortsConfig, redact_secrets
from src.utils import is_colab, setup_logger

logger = setup_logger("autoshorts.drive")

REQUIRED_SUBFOLDERS = (
    "Videos",
    "Projects",
    "Audio",
    "Scripts",
    "Storyboards",
    "Subtitles",
    "Logs",
    "Reports",
    "Backups",
)

FORBIDDEN_NAME_PATTERNS = (
    ".env",
    "credential",
    "secret",
    "service_account",
    "token",
    "api_key",
)
FORBIDDEN_EXTENSIONS = {".key", ".pem", ".p12", ".pfx"}
TEXT_REDACT_EXTENSIONS = {".json", ".log", ".txt", ".md", ".srt", ".html"}


def is_sensitive_file(path: Path) -> bool:
    """Return True if a file looks like a credential or secret that must NEVER be uploaded."""
    low = path.name.lower()
    if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
        return True
    return any(pat in low for pat in FORBIDDEN_NAME_PATTERNS)


def _safe_copy_file(src: Path, dst: Path) -> bool:
    """Copy a single file while blocking credentials and redacting secrets from text files."""
    if not src.exists() or not src.is_file():
        return False
    if is_sensitive_file(src):
        logger.warning("Bloqueado upload de arquivo sensível para o Drive: %s", src.name)
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in TEXT_REDACT_EXTENSIONS:
        text = src.read_text(encoding="utf-8", errors="replace")
        dst.write_text(redact_secrets(text), encoding="utf-8")
    else:
        shutil.copy2(src, dst)
    return True


class DriveManager:
    """Manages Google Drive mount and organized delivery for AutoShorts AI."""

    def __init__(
        self,
        config: Optional[AutoShortsConfig] = None,
        root_override: Optional[Path | str] = None,
    ) -> None:
        self.cfg = config or AutoShortsConfig.load()
        self.root_override = Path(root_override) if root_override else None
        self.mounted = False
        self.base_dir: Optional[Path] = None

    def mount_if_colab(self, force_remount: bool = False) -> Path:
        """Mount Google Drive via official google.colab.drive API when running in Colab."""
        if self.root_override is not None:
            self.base_dir = self.root_override / self.cfg.get("drive.root_folder", "AutoShorts AI")
            self.mounted = True
            return self.ensure_structure()

        mount_point = Path(self.cfg.get("drive.mount_point", "/content/drive"))
        my_drive = self.cfg.get("drive.my_drive_subpath", "MyDrive")
        root_folder = self.cfg.get("drive.root_folder", "AutoShorts AI")

        if is_colab():
            from google.colab import drive  # type: ignore

            drive.mount(str(mount_point), force_remount=force_remount)
            self.base_dir = mount_point / my_drive / root_folder
            self.mounted = True
            logger.info("Google Drive montado oficialmente em: %s", self.base_dir)
            return self.ensure_structure()

        raise RuntimeError(
            "Ambiente atual não é Google Colab e nenhum `root_override` foi fornecido. "
            "No Colab, execute o notebook oficial para montar o Google Drive."
        )

    def ensure_structure(self) -> Path:
        """Create the required AutoShorts AI directory hierarchy inside Drive."""
        if self.base_dir is None:
            raise RuntimeError("Drive não inicializado. Chame mount_if_colab() primeiro.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        subfolders = self.cfg.get("drive.folders") or list(REQUIRED_SUBFOLDERS)
        for folder in subfolders:
            (self.base_dir / folder).mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def sync_project(
        self,
        project_id: str,
        local_project_dir: Path,
        deliverables: Dict[str, Optional[Path]],
    ) -> Dict[str, Any]:
        """Bulk-copy finished project deliverables from fast local Colab disk to Google Drive."""
        base = self.ensure_structure()
        local_project_dir = Path(local_project_dir)
        drive_project_dir = base / "Projects" / project_id
        drive_project_dir.mkdir(parents=True, exist_ok=True)

        copied: List[str] = []
        blocked: List[str] = []

        # 1. Organized top-level category copies
        category_map = [
            ("video_mp4", base / "Videos" / f"{project_id}.mp4"),
            ("story_json", base / "Scripts" / f"{project_id}_story.json"),
            ("mix_wav", base / "Audio" / f"{project_id}_mix.wav"),
            ("vo_wav", base / "Audio" / f"{project_id}_vo.wav"),
            ("storyboard_json", base / "Storyboards" / f"{project_id}_storyboard.json"),
            ("storyboard_sheet", base / "Storyboards" / f"{project_id}_storyboard.png"),
            ("srt_path", base / "Subtitles" / f"{project_id}.srt"),
            ("sync_json", base / "Subtitles" / f"{project_id}_sync.json"),
            ("quality_report", base / "Reports" / f"{project_id}_quality_report.json"),
            ("qa_contact_sheet", base / "Reports" / f"{project_id}_qa_contact_sheet.png"),
            ("log_file", base / "Logs" / f"{project_id}.log"),
        ]

        for key, dst_path in category_map:
            src = deliverables.get(key)
            if src is None:
                continue
            src_path = Path(src)
            if is_sensitive_file(src_path):
                blocked.append(str(src_path))
                continue
            if _safe_copy_file(src_path, dst_path):
                copied.append(str(dst_path))

        # 2. Dedicated per-video project folder snapshot (excluding heavy temp `parts/` folder)
        for item in local_project_dir.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(local_project_dir)
            # Skip intermediate part chunks to avoid redundant Drive traffic
            if rel.parts and rel.parts[0] in ("parts", "tmp", "__pycache__"):
                continue
            if is_sensitive_file(item):
                blocked.append(str(item))
                continue
            dst = drive_project_dir / rel
            if _safe_copy_file(item, dst):
                copied.append(str(dst))

        summary = {
            "drive_root": str(base),
            "drive_project_dir": str(drive_project_dir),
            "files_copied_count": len(copied),
            "blocked_sensitive_files": blocked,
            "video_drive_path": str(base / "Videos" / f"{project_id}.mp4"),
        }
        logger.info(
            "Sincronização Google Drive concluída: %d arquivos enviados para %s",
            len(copied),
            drive_project_dir,
        )
        return summary
