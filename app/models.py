"""Modelos de dados validados (Pydantic v2) para histórias, roteiros, personagens, cenas e projetos."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class GenerationMode(str, Enum):
    GOOGLE_FLOW = "google_flow"
    LOCAL_FREE = "local_free"
    AUTO_FLOW_FREE = "auto_flow_free"


class SceneSourceType(str, Enum):
    PENDING = "pending"
    GOOGLE_FLOW_IMPORT = "google_flow_import"
    COMFYUI_WAN22 = "comfyui_wan22"
    COMFYUI_IMAGE_ANIMATED = "comfyui_image_animated"
    BLENDER_3D_RENDER = "blender_3d_render"
    FALLBACK_PROCEDURAL_ANIMATED = "fallback_procedural_animated"
    ROBLOX_STUDIO_IMPORT = "roblox_studio_import"
    USER_IMAGE_ANIMATED = "user_image_animated"


class CharacterProfile(BaseModel):
    id: str = Field(..., description="Identificador curto do personagem, ex.: char_protagonista")
    name: str = Field(..., min_length=1)
    role: str = Field(default="Protagonista")
    visual_description_en: str = Field(
        ...,
        min_length=10,
        description="Descrição consistente em inglês para prompts de geração (aparência Roblox 3D).",
    )
    visual_description_pt: str = Field(default="")
    primary_color_hex: str = Field(default="#2563EB", description="Cor principal da camisa/jaqueta")
    secondary_color_hex: str = Field(default="#1E293B", description="Cor da calça/detalhes")
    skin_color_hex: str = Field(default="#F3C69F", description="Tom de pele/cabeça Roblox")
    hair_color_hex: str = Field(default="#2C1D14", description="Cor do cabelo")
    hair_style: str = Field(default="spiky", description="spiky | cap | bob | hood | crown | short")
    accessory: str = Field(default="backpack", description="backpack | headphones | scarf | cape | glasses | none")
    reference_image_path: Optional[str] = None
    reference_prompt_en: str = Field(default="")


class SceneSpec(BaseModel):
    scene_number: int = Field(..., ge=1, le=20)
    title: str = Field(..., min_length=2)
    story_beat: str = Field(
        default="Desenvolvimento",
        description="Gancho | Situação | Desenvolvimento | Conflito | Clímax | Reviravolta | Final",
    )
    description_pt: str = Field(..., min_length=5)
    narration_pt: str = Field(..., min_length=5)
    visual_prompt_en: str = Field(..., min_length=15)
    negative_prompt_en: str = Field(
        default=(
            "2D illustration, flat cartoon, vector art, paper cutout characters, flat characters, "
            "flat background, simplistic poster design, motion graphics, giant typography, static character poses, "
            "sprites, low-detail environment, lack of depth, fake 3D appearance, watermark, text overlay, "
            "subtitles, giant letters, random logos, distorted limbs, stretched aspect ratio"
        )
    )
    characters: List[str] = Field(default_factory=list)
    setting_pt: str = Field(default="Servidor Roblox")
    setting_theme: str = Field(
        default="city",
        description="city | school | server | forest | castle | neon | lobby | hallway | room | night",
    )
    movements_en: str = Field(default="subtle character movement and expressive gesture")
    expression: str = Field(
        default="neutral",
        description="neutral | curious | happy | worried | scared | angry | shocked | determined",
    )
    camera_movement: str = Field(
        default="slow_zoom_in",
        description="slow_zoom_in | slow_zoom_out | pan_left | pan_right | tilt_up | dramatic_push | parallax_drift",
    )
    duration_seconds: float = Field(default=6.5, ge=2.5, le=18.0)
    sfx_cue: str = Field(default="transition", description="none | transition | surprise | ambient")
    status: Literal["pending", "awaiting_flow", "ready", "error"] = "pending"
    source_type: SceneSourceType = SceneSourceType.PENDING
    video_path: Optional[str] = None
    image_paths: List[str] = Field(default_factory=list)
    flow_prompt_file: Optional[str] = None
    error_message: Optional[str] = None


class StoryDocument(BaseModel):
    title: str = Field(..., min_length=3)
    hook_pt: str = Field(..., min_length=5)
    genre: str = Field(default="Suspense / Mistério")
    opening_style: str = Field(default="Neste servidor...")
    setup_pt: str = Field(default="")
    development_pt: str = Field(default="")
    conflict_pt: str = Field(default="")
    climax_pt: str = Field(default="")
    twist_pt: str = Field(default="")
    ending_pt: str = Field(default="")
    full_narration_pt: str = Field(..., min_length=20)
    suggested_title: str = Field(default="")
    suggested_description: str = Field(default="")
    suggested_hashtags: List[str] = Field(default_factory=list)
    story_provider: str = Field(default="local_structured")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StoryboardDocument(BaseModel):
    project_id: str
    target_duration_seconds: int = Field(default=55, ge=25, le=120)
    visual_style: str = Field(default="roblox_3d_blender_cinematic")
    style_bible_en: str = Field(
        default=(
            "High-quality cinematic 3D Roblox animation, professionally rendered Blender-style 3D environment, "
            "fully modeled three-dimensional Roblox characters, authentic blocky Roblox avatar proportions, "
            "detailed 3D geometry, realistic depth, physically based materials, cinematic global illumination, "
            "ambient occlusion, realistic shadows, volumetric lighting, professional camera composition, "
            "depth of field, smooth character animation, detailed 3D environment, high-quality 3D render."
        )
    )
    characters: List[CharacterProfile] = Field(default_factory=list)
    scenes: List[SceneSpec] = Field(..., min_length=4, max_length=15)
    validated: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("scenes")
    @classmethod
    def check_scene_numbers(cls, scenes: List[SceneSpec]) -> List[SceneSpec]:
        expected = list(range(1, len(scenes) + 1))
        actual = [s.scene_number for s in scenes]
        if actual != expected:
            for idx, scene in enumerate(scenes, start=1):
                scene.scene_number = idx
        return scenes


class HardwareReport(BaseModel):
    cpu_name: str = "Desconhecido"
    cpu_cores: int = 1
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    disk_free_gb: float = 0.0
    gpu_name: str = "Nenhuma GPU dedicada detectada"
    gpu_vendor: str = "Desconhecido"
    gpu_vram_gb: float = 0.0
    cuda_available: bool = False
    ffmpeg_available: bool = False
    ffmpeg_path: Optional[str] = None
    blender_available: bool = False
    blender_path: Optional[str] = None
    blender_version: Optional[str] = None
    ollama_available: bool = False
    ollama_models: List[str] = Field(default_factory=list)
    comfyui_available: bool = False
    comfyui_checkpoints: List[str] = Field(default_factory=list)
    comfyui_unets: List[str] = Field(default_factory=list)
    kokoro_ready: bool = False
    piper_ready: bool = False
    whisper_ready: bool = False
    supports_wan22: bool = False
    supports_local_image_ai: bool = False
    recommended_ollama_model: str = "gemma3:1b"
    recommended_tier: str = "fallback_animated_images"
    compatibility_summary: str = ""
    warnings: List[str] = Field(default_factory=list)


class ProjectState(BaseModel):
    project_id: str
    project_dir: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: GenerationMode = GenerationMode.AUTO_FLOW_FREE
    visual_style: str = "roblox_3d_blender_cinematic"
    flow_credits_available: bool = True
    story_input: str = ""
    genre: str = "Suspense / Mistério"
    opening_style: str = "Neste servidor..."
    duration_seconds: int = 55
    voice: str = "pm_alex"
    speed: float = 1.05
    music_mood: str = "suspense"
    current_stage: str = "initialized"
    status: Literal["idle", "running", "awaiting_flow_import", "completed", "cancelled", "error"] = "idle"
    progress_percent: float = 0.0
    cancelled: bool = False
    step_statuses: Dict[str, str] = Field(
        default_factory=lambda: {
            "story": "pending",
            "storyboard": "pending",
            "references": "pending",
            "prompts": "pending",
            "narration": "pending",
            "subtitles": "pending",
            "scenes": "pending",
            "render": "pending",
        }
    )
    narration_wav_path: Optional[str] = None
    subtitles_srt_path: Optional[str] = None
    subtitles_ass_path: Optional[str] = None
    final_video_path: Optional[str] = None
    last_error: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
