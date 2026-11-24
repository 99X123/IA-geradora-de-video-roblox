"""Cliente HTTP real para ComfyUI (Wan 2.2 TI2V-5B e geração de imagens locais) com trava de hardware."""

from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx

from app.config import load_settings, resolve_path
from app.models import HardwareReport, SceneSpec
from app.visual_styles import MANDATORY_NEGATIVE_PROMPT


class ComfyUIError(RuntimeError):
    """Erro de execução ou indisponibilidade do ComfyUI."""


class ComfyUIClient:
    """Comunicação oficial via API HTTP do ComfyUI local (sem scraping ou serviços pagos)."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        self.settings = settings or load_settings()
        self.base_url = self.settings["comfyui"]["base_url"].rstrip("/")
        self.timeout_seconds = int(self.settings["comfyui"].get("timeout_seconds", 600))
        self.workflows_dir = resolve_path(self.settings["paths"]["workflows_dir"])

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/system_stats", timeout=2.5)
            return resp.status_code == 200
        except Exception:
            return False

    def upload_image(self, image_path: Path) -> str:
        """Envia imagem de referência de personagem para a pasta input do ComfyUI via /upload/image."""
        with image_path.open("rb") as fh:
            files = {"image": (image_path.name, fh, "image/png")}
            data = {"overwrite": "true"}
            resp = httpx.post(f"{self.base_url}/upload/image", files=files, data=data, timeout=30.0)
        resp.raise_for_status()
        payload = resp.json()
        return str(payload.get("name") or image_path.name)

    def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        resp = httpx.post(f"{self.base_url}/prompt", json={"prompt": workflow}, timeout=30.0)
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI rejeitou o workflow ({resp.status_code}): {resp.text[:300]}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise ComfyUIError("ComfyUI não retornou prompt_id.")
        return str(prompt_id)

    def wait_and_download(
        self,
        prompt_id: str,
        dest_path: Path,
        expected_media: str = "video",
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> Path:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            if cancel_check:
                cancel_check()
            resp = httpx.get(f"{self.base_url}/history/{prompt_id}", timeout=10.0)
            if resp.status_code == 200:
                history = resp.json()
                if prompt_id in history:
                    entry = history[prompt_id]
                    outputs = entry.get("outputs", {})
                    for node_out in outputs.values():
                        for key in ("videos", "gifs", "images"):
                            items = node_out.get(key)
                            if items:
                                item = items[0]
                                filename = item["filename"]
                                subfolder = item.get("subfolder", "")
                                folder_type = item.get("type", "output")
                                return self._download_file(filename, subfolder, folder_type, dest_path)
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        raise ComfyUIError(f"Workflow {prompt_id} falhou no ComfyUI: {status}")
            time.sleep(2.0)
        raise ComfyUIError(f"Tempo limite ({self.timeout_seconds}s) excedido aguardando ComfyUI ({expected_media}).")

    def _download_file(self, filename: str, subfolder: str, folder_type: str, dest_path: Path) -> Path:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        resp = httpx.get(f"{self.base_url}/view", params=params, timeout=60.0)
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(resp.content)
        return dest_path

    def generate_scene_video_wan22(
        self,
        scene: SceneSpec,
        dest_mp4: Path,
        hardware: HardwareReport,
        reference_image: Optional[Path] = None,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> Path:
        """
        Gera vídeo local com Wan 2.2 TI2V-5B via ComfyUI.
        Trava de segurança: recusa execução se a GPU não atender ao mínimo de VRAM.
        """
        if not hardware.supports_wan22:
            raise ComfyUIError(
                f"Hardware incompatível com Wan 2.2 TI2V-5B ({hardware.gpu_name}, {hardware.gpu_vram_gb:.1f} GB VRAM). "
                "Execução bloqueada para evitar travamento da GPU."
            )
        if not self.is_available():
            raise ComfyUIError(f"ComfyUI não está ativo em {self.base_url}.")

        cfg_c = self.settings["comfyui"]
        use_ref = reference_image is not None and reference_image.exists()
        wf_name = "wan22_i2v_character_ref.json" if use_ref else "wan22_ti2v_5b.json"
        wf_path = self.workflows_dir / wf_name
        with wf_path.open("r", encoding="utf-8") as fh:
            workflow = copy.deepcopy(json.load(fh))

        fps = int(cfg_c.get("wan22_fps", 24))
        # Wan 2.2 usa comprimento 4n+1 frames (ex.: 81 frames ~ 3.4s, 121 frames ~ 5s)
        raw_frames = max(49, min(121, int(scene.duration_seconds * fps)))
        length = ((raw_frames - 1) // 4) * 4 + 1

        workflow["1"]["inputs"]["unet_name"] = cfg_c.get("wan22_unet", "wan2.2_ti2v_5B_fp16.safetensors")
        workflow["2"]["inputs"]["clip_name"] = cfg_c.get("wan22_clip", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
        workflow["3"]["inputs"]["vae_name"] = cfg_c.get("wan22_vae", "wan2.2_vae.safetensors")
        workflow["4"]["inputs"]["text"] = scene.visual_prompt_en
        workflow["5"]["inputs"]["text"] = scene.negative_prompt_en or MANDATORY_NEGATIVE_PROMPT
        workflow["6"]["inputs"]["width"] = int(cfg_c.get("wan22_width", 480))
        workflow["6"]["inputs"]["height"] = int(cfg_c.get("wan22_height", 832))
        workflow["6"]["inputs"]["length"] = length
        workflow["8"]["inputs"]["seed"] = random.randint(1, 2**31 - 1)
        workflow["8"]["inputs"]["steps"] = int(cfg_c.get("wan22_steps", 20))
        workflow["10"]["inputs"]["fps"] = fps
        workflow["11"]["inputs"]["filename_prefix"] = f"roblox_scene_{scene.scene_number:02d}"

        if use_ref and reference_image is not None:
            uploaded_name = self.upload_image(reference_image)
            workflow["12"]["inputs"]["image"] = uploaded_name

        prompt_id = self.queue_prompt(workflow)
        return self.wait_and_download(prompt_id, dest_mp4, expected_media="video", cancel_check=cancel_check)

    def generate_scene_image(
        self,
        scene: SceneSpec,
        dest_png: Path,
        hardware: HardwareReport,
        seed_offset: int = 0,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> Path:
        """Gera imagem de cena local via ComfyUI para o plano alternativo (GPUs 4-11 GB VRAM)."""
        if not hardware.supports_local_image_ai:
            raise ComfyUIError(
                f"GPU ({hardware.gpu_name}, {hardware.gpu_vram_gb:.1f} GB VRAM) abaixo do mínimo para difusão local."
            )
        if not self.is_available():
            raise ComfyUIError(f"ComfyUI não está ativo em {self.base_url}.")

        cfg_c = self.settings["comfyui"]
        wf_path = self.workflows_dir / "image_gen_roblox_scene.json"
        with wf_path.open("r", encoding="utf-8") as fh:
            workflow = copy.deepcopy(json.load(fh))

        ckpt = cfg_c.get("image_checkpoint", "sd_xl_base_1.0.safetensors")
        if hardware.comfyui_checkpoints and ckpt not in hardware.comfyui_checkpoints:
            ckpt = hardware.comfyui_checkpoints[0]

        workflow["1"]["inputs"]["ckpt_name"] = ckpt
        workflow["2"]["inputs"]["text"] = scene.visual_prompt_en
        workflow["3"]["inputs"]["text"] = scene.negative_prompt_en or MANDATORY_NEGATIVE_PROMPT
        workflow["4"]["inputs"]["width"] = int(cfg_c.get("image_width", 768))
        workflow["4"]["inputs"]["height"] = int(cfg_c.get("image_height", 1344))
        workflow["5"]["inputs"]["seed"] = random.randint(1, 2**31 - 1) + seed_offset
        workflow["5"]["inputs"]["steps"] = int(cfg_c.get("image_steps", 22))
        workflow["7"]["inputs"]["filename_prefix"] = f"roblox_img_{scene.scene_number:02d}"

        prompt_id = self.queue_prompt(workflow)
        return self.wait_and_download(prompt_id, dest_png, expected_media="image", cancel_check=cancel_check)
