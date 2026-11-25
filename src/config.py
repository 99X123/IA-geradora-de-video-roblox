"""Central configuration loader and secure credential resolution for AutoShorts AI."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"

SENSITIVE_ENV_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENCODE_API_KEY",
    "ELEVENLABS_API_KEY",
)

QUALITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "draft": {
        "width": 540,
        "height": 960,
        "fps": 24,
        "crf": 23,
        "preset": "ultrafast",
        "jpeg_quality": 0.85,
        "num_parts": 4,
    },
    "preview": {
        "width": 720,
        "height": 1280,
        "fps": 30,
        "crf": 20,
        "preset": "veryfast",
        "jpeg_quality": 0.90,
        "num_parts": 6,
    },
    "production": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "crf": 18,
        "preset": "veryfast",
        "jpeg_quality": 0.93,
        "num_parts": 10,
    },
    "ultra": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "crf": 15,
        "preset": "medium",
        "jpeg_quality": 0.96,
        "num_parts": 10,
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries without mutating inputs."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a secret from environment variables or Google Colab userdata.

    Never persists credentials to disk or Google Drive.
    """
    env_val = os.environ.get(name)
    if env_val and env_val.strip():
        return env_val.strip()

    # Try Google Colab Secrets (userdata) when running inside Colab
    try:
        from google.colab import userdata  # type: ignore

        colab_val = userdata.get(name)
        if colab_val and str(colab_val).strip():
            return str(colab_val).strip()
    except Exception:
        pass

    return default


def redact_secrets(text: str) -> str:
    """Scrub known secret values from logs or reports."""
    if not text:
        return text
    sanitized = text
    for key in SENSITIVE_ENV_KEYS:
        val = os.environ.get(key)
        if val and len(val) >= 8:
            sanitized = sanitized.replace(val, f"<REDACTED:{key}>")
    return sanitized


@dataclass
class AutoShortsConfig:
    """Typed wrapper around the central JSON configuration."""

    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        config_path: Optional[Path | str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "AutoShortsConfig":
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if overrides:
            data = deep_merge(data, overrides)

        # Apply quality preset if explicitly requested and dimensions weren't overridden
        preset_name = data.get("video", {}).get("quality_preset", "production")
        if preset_name in QUALITY_PRESETS:
            preset_vals = QUALITY_PRESETS[preset_name]
            override_video = (overrides or {}).get("video", {})
            for k, v in preset_vals.items():
                if k not in override_video:
                    data["video"][k] = v

        # Allow environment variable to set OpenCode model without storing in repo
        env_oc_model = get_secret("OPENCODE_MODEL")
        if env_oc_model and not data.get("opencode", {}).get("model"):
            data.setdefault("opencode", {})["model"] = env_oc_model

        return cls(raw=data)

    def get(self, dotted_path: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted_path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.raw)

    def save_safe_snapshot(self, dest: Path) -> Path:
        """Save configuration without any secrets."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as fh:
            json.dump(self.raw, fh, indent=2, ensure_ascii=False)
        return dest
