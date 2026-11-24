"""
Script nativo do Blender (executado em modo headless via `blender --background --python`).
Constrói avatares Roblox 3D completos (geometria chanfrada, materiais PBR, cabelo/acessórios 3D,
expressões 3D, animação articulada de corpo/braços/pernas/cabeça), cenários 3D reais com profundidade,
iluminação cinematográfica por emoção e câmeras 3D animadas com Depth of Field.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import bpy
from mathutils import Euler, Vector


def _hex_to_rgba(hex_str: str, fallback: Tuple[float, float, float] = (0.15, 0.38, 0.92)) -> Tuple[float, float, float, float]:
    try:
        h = hex_str.lstrip("#")
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        # Conversão sRGB -> Linear aproximada para fidelidade PBR no Blender
        return (r ** 2.2, g ** 2.2, b ** 2.2, 1.0)
    except Exception:
        return (fallback[0], fallback[1], fallback[2], 1.0)


def _clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _make_pbr_material(
    name: str,
    color_rgba: Tuple[float, float, float, float],
    roughness: float = 0.35,
    metallic: float = 0.0,
    emission_strength: float = 0.0,
    emission_color: Tuple[float, float, float, float] | None = None,
    coat_weight: float = 0.0,
    noise_bump: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name=name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color_rgba
    bsdf.inputs["Roughness"].default_value = max(0.04, min(0.98, roughness))
    bsdf.inputs["Metallic"].default_value = max(0.0, min(1.0, metallic))
    if "Coat Weight" in bsdf.inputs and coat_weight > 0:
        bsdf.inputs["Coat Weight"].default_value = coat_weight
    if emission_strength > 0 and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = emission_color or color_rgba
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if noise_bump > 0:
        tex_coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 18.0
        noise.inputs["Detail"].default_value = 4.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise_bump
        nt.links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _add_beveled_box(
    name: str,
    size_xyz: Tuple[float, float, float],
    location: Tuple[float, float, float],
    material: bpy.types.Material,
    parent: bpy.types.Object | None = None,
    bevel_width: float = 0.04,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size_xyz[0], size_xyz[1], size_xyz[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel_width > 0:
        bev = obj.modifiers.new(name="Bevel", type="BEVEL")
        bev.width = bevel_width
        bev.segments = 3
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    if parent is not None:
        obj.parent = parent
    return obj


def _add_cylinder(
    name: str,
    radius: float,
    depth: float,
    location: Tuple[float, float, float],
    material: bpy.types.Material,
    parent: bpy.types.Object | None = None,
    vertices: int = 24,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.active_object
    obj.name = name
    bev = obj.modifiers.new(name="Bevel", type="BEVEL")
    bev.width = min(0.06, radius * 0.22)
    bev.segments = 3
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    if parent is not None:
        obj.parent = parent
    return obj


def _add_empty(name: str, location: Tuple[float, float, float], parent: bpy.types.Object | None = None) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(empty)
    empty.location = location
    if parent is not None:
        empty.parent = parent
    return empty


def build_roblox_character_3d(
    char_data: Dict[str, Any],
    base_location: Tuple[float, float, float],
    yaw_deg: float,
    expression: str,
    roughness_bias: float = 0.32,
) -> Dict[str, bpy.types.Object]:
    """
    Constrói um avatar Roblox R15 tridimensional completo e articulado (pivôs de quadril,
    ombros, pescoço e raiz para animação fluida de corrida, caminhada, gestos e expressões).
    """
    cid = char_data.get("id", "char")
    skin_rgba = _hex_to_rgba(char_data.get("skin_color_hex", "#F3C69F"))
    primary_rgba = _hex_to_rgba(char_data.get("primary_color_hex", "#2563EB"))
    secondary_rgba = _hex_to_rgba(char_data.get("secondary_color_hex", "#1E293B"))
    hair_rgba = _hex_to_rgba(char_data.get("hair_color_hex", "#2B1B12"))

    mat_skin = _make_pbr_material(f"{cid}_skin", skin_rgba, roughness=max(0.22, roughness_bias - 0.04), coat_weight=0.25)
    mat_primary = _make_pbr_material(f"{cid}_primary", primary_rgba, roughness=roughness_bias + 0.12, noise_bump=0.06)
    mat_secondary = _make_pbr_material(f"{cid}_secondary", secondary_rgba, roughness=roughness_bias + 0.16, noise_bump=0.08)
    mat_hair = _make_pbr_material(f"{cid}_hair", hair_rgba, roughness=roughness_bias + 0.08, coat_weight=0.15)
    mat_shoe = _make_pbr_material(f"{cid}_shoe", (0.88, 0.90, 0.94, 1.0), roughness=0.28)
    mat_eye = _make_pbr_material(f"{cid}_eye", (0.02, 0.02, 0.03, 1.0), roughness=0.06, coat_weight=0.9)
    mat_white = _make_pbr_material(f"{cid}_white", (0.98, 0.98, 1.0, 1.0), roughness=0.05, emission_strength=0.4)
    mat_gold = _make_pbr_material(f"{cid}_gold", (0.95, 0.72, 0.12, 1.0), roughness=0.18, metallic=0.88)
    mat_accent = _make_pbr_material(f"{cid}_accent", (0.92, 0.14, 0.18, 1.0), roughness=0.22, metallic=0.35, emission_strength=0.6)

    root = _add_empty(f"{cid}_root", base_location)
    root.rotation_euler = Euler((0.0, 0.0, math.radians(yaw_deg)), "XYZ")

    pelvis = _add_empty(f"{cid}_pelvis", (0.0, 0.0, 0.95), parent=root)

    # Pernas articuladas (esquerda e direita)
    leg_l_piv = _add_empty(f"{cid}_leg_l_piv", (-0.23, 0.0, 0.0), parent=pelvis)
    leg_r_piv = _add_empty(f"{cid}_leg_r_piv", (0.23, 0.0, 0.0), parent=pelvis)
    for side, piv in (("L", leg_l_piv), ("R", leg_r_piv)):
        _add_beveled_box(f"{cid}_leg_{side}", (0.40, 0.42, 0.78), (0.0, 0.0, -0.40), mat_secondary, parent=piv, bevel_width=0.045)
        _add_beveled_box(f"{cid}_shoe_{side}", (0.42, 0.50, 0.18), (0.0, -0.04, -0.86), mat_shoe, parent=piv, bevel_width=0.04)

    # Tronco 3D com volume de jaqueta/gola
    torso_piv = _add_empty(f"{cid}_torso_piv", (0.0, 0.0, 0.04), parent=pelvis)
    _add_beveled_box(f"{cid}_torso", (0.92, 0.48, 0.96), (0.0, 0.0, 0.50), mat_primary, parent=torso_piv, bevel_width=0.055)
    # Gola / detalhe frontal 3D da roupa
    _add_beveled_box(f"{cid}_collar", (0.56, 0.50, 0.14), (0.0, 0.0, 0.94), mat_secondary, parent=torso_piv, bevel_width=0.03)
    _add_beveled_box(f"{cid}_zipper", (0.06, 0.51, 0.86), (0.0, -0.01, 0.48), mat_secondary, parent=torso_piv, bevel_width=0.015)

    # Braços articulados com mãos separadas
    arm_l_piv = _add_empty(f"{cid}_arm_l_piv", (-0.68, 0.0, 0.90), parent=torso_piv)
    arm_r_piv = _add_empty(f"{cid}_arm_r_piv", (0.68, 0.0, 0.90), parent=torso_piv)
    for side, piv in (("L", arm_l_piv), ("R", arm_r_piv)):
        _add_beveled_box(f"{cid}_arm_{side}", (0.36, 0.38, 0.72), (0.0, 0.0, -0.36), mat_primary, parent=piv, bevel_width=0.045)
        _add_beveled_box(f"{cid}_hand_{side}", (0.34, 0.34, 0.22), (0.0, 0.0, -0.81), mat_skin, parent=piv, bevel_width=0.05)

    # Cabeça clássica Roblox 3D (cilindro chanfrado com brilho PBR)
    head_piv = _add_empty(f"{cid}_head_piv", (0.0, 0.0, 1.02), parent=torso_piv)
    _add_cylinder(f"{cid}_head", radius=0.36, depth=0.66, location=(0.0, 0.0, 0.34), material=mat_skin, parent=head_piv)

    # Olhos 3D brilhantes + pontos de brilho + sobrancelhas + boca (face voltada para -Y)
    eye_scale = 1.25 if expression in ("shocked", "scared") else 1.0
    for sx in (-0.13, 0.13):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.055 * eye_scale, location=(sx, -0.345, 0.38))
        eye = bpy.context.active_object
        eye.scale = (1.0, 0.45, 1.15)
        eye.data.materials.append(mat_eye)
        eye.parent = head_piv

        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.018, location=(sx - 0.018, -0.372, 0.405))
        glint = bpy.context.active_object
        glint.data.materials.append(mat_white)
        glint.parent = head_piv

        # Sobrancelha 3D inclinada conforme emoção
        brow = _add_beveled_box(f"{cid}_brow_{sx:.2f}", (0.13, 0.04, 0.032), (sx, -0.355, 0.47), mat_hair, parent=head_piv, bevel_width=0.008)
        if expression in ("angry", "determined"):
            brow.rotation_euler = Euler((0.0, math.radians(-18 if sx < 0 else 18), 0.0), "XYZ")
        elif expression in ("worried", "scared"):
            brow.rotation_euler = Euler((0.0, math.radians(18 if sx < 0 else -18), 0.0), "XYZ")
        elif expression in ("shocked", "curious"):
            brow.location.z += 0.035

    # Boca 3D expressiva
    if expression in ("shocked", "scared"):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.068, location=(0.0, -0.35, 0.22))
        mouth = bpy.context.active_object
        mouth.scale = (1.0, 0.4, 1.2)
        mouth.data.materials.append(mat_eye)
        mouth.parent = head_piv
    elif expression == "happy":
        mouth = _add_beveled_box(f"{cid}_mouth", (0.20, 0.04, 0.045), (0.0, -0.355, 0.22), mat_white, parent=head_piv, bevel_width=0.012)
    else:
        mouth = _add_beveled_box(f"{cid}_mouth", (0.16, 0.04, 0.028), (0.0, -0.355, 0.22), mat_eye, parent=head_piv, bevel_width=0.008)

    # Cabelo / Chapéu / Capuz / Coroa 3D modelados
    hair_style = str(char_data.get("hair_style") or "spiky").lower()
    if hair_style == "crown":
        _add_cylinder(f"{cid}_crown_base", radius=0.38, depth=0.14, location=(0.0, 0.0, 0.67), material=mat_gold, parent=head_piv)
        for ang in range(0, 360, 60):
            rad = math.radians(ang)
            bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.08, depth=0.22, location=(math.cos(rad) * 0.31, math.sin(rad) * 0.31, 0.78))
            spike = bpy.context.active_object
            spike.data.materials.append(mat_gold)
            spike.parent = head_piv
    elif hair_style == "cap":
        _add_cylinder(f"{cid}_cap_top", radius=0.39, depth=0.24, location=(0.0, 0.0, 0.60), material=mat_primary, parent=head_piv)
        _add_beveled_box(f"{cid}_cap_brim", (0.56, 0.36, 0.06), (0.0, -0.28, 0.52), mat_secondary, parent=head_piv, bevel_width=0.018)
    elif hair_style == "hood":
        _add_beveled_box(f"{cid}_hood_back", (0.86, 0.62, 0.78), (0.0, 0.14, 0.38), mat_primary, parent=head_piv, bevel_width=0.09)
        _add_beveled_box(f"{cid}_hood_top", (0.86, 0.84, 0.18), (0.0, 0.03, 0.68), mat_primary, parent=head_piv, bevel_width=0.06)
    else:
        # Cabelo 3D volumoso em camadas + mechas pontudas
        _add_beveled_box(f"{cid}_hair_cap", (0.80, 0.78, 0.26), (0.0, 0.04, 0.62), mat_hair, parent=head_piv, bevel_width=0.08)
        _add_beveled_box(f"{cid}_hair_back", (0.78, 0.24, 0.56), (0.0, 0.32, 0.42), mat_hair, parent=head_piv, bevel_width=0.06)
        for idx, sx in enumerate((-0.24, -0.08, 0.08, 0.24)):
            bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.13, depth=0.30, location=(sx, -0.10 + (idx % 2) * 0.12, 0.78))
            sp = bpy.context.active_object
            sp.rotation_euler = Euler((math.radians(-18), math.radians(sx * 45), 0.0), "XYZ")
            sp.data.materials.append(mat_hair)
            sp.parent = head_piv

    # Acessórios 3D (mochila, capa, fones de ouvido, cachecol)
    accessory = str(char_data.get("accessory") or "backpack").lower()
    if accessory == "backpack":
        _add_beveled_box(f"{cid}_backpack", (0.64, 0.30, 0.72), (0.0, 0.36, 0.52), mat_secondary, parent=torso_piv, bevel_width=0.06)
        _add_beveled_box(f"{cid}_backpack_pocket", (0.48, 0.12, 0.32), (0.0, 0.50, 0.38), mat_primary, parent=torso_piv, bevel_width=0.03)
    elif accessory == "cape":
        cape = _add_beveled_box(f"{cid}_cape", (0.98, 0.08, 1.38), (0.0, 0.34, 0.26), mat_primary, parent=torso_piv, bevel_width=0.025)
        cape.rotation_euler = Euler((math.radians(12), 0.0, 0.0), "XYZ")
    elif accessory == "headphones":
        for sx in (-0.40, 0.40):
            cup = _add_cylinder(f"{cid}_hp_{sx:.1f}", radius=0.13, depth=0.10, location=(sx, 0.0, 0.36), material=mat_accent, parent=head_piv)
            cup.rotation_euler = Euler((0.0, math.radians(90), 0.0), "XYZ")
        _add_beveled_box(f"{cid}_hp_band", (0.84, 0.12, 0.08), (0.0, 0.0, 0.76), mat_secondary, parent=head_piv, bevel_width=0.03)
    elif accessory == "scarf":
        _add_beveled_box(f"{cid}_scarf", (0.82, 0.62, 0.18), (0.0, 0.0, 0.98), mat_gold, parent=torso_piv, bevel_width=0.05)

    return {
        "root": root,
        "pelvis": pelvis,
        "torso": torso_piv,
        "head": head_piv,
        "arm_l": arm_l_piv,
        "arm_r": arm_r_piv,
        "leg_l": leg_l_piv,
        "leg_r": leg_r_piv,
    }


def animate_roblox_character(
    rig: Dict[str, bpy.types.Object],
    frame_start: int,
    frame_end: int,
    action_mode: str,
    expression: str,
    start_pos: Tuple[float, float, float],
    move_delta: Tuple[float, float, float],
) -> None:
    """Cria keyframes reais de caminhada, corrida, gestos e movimento expressivo de cabeça/braços."""
    total = max(1, frame_end - frame_start)
    step = max(1, total // 14)
    frames = list(range(frame_start, frame_end + 1, step))
    if frames[-1] != frame_end:
        frames.append(frame_end)

    for f in frames:
        t = (f - frame_start) / float(total)
        phase = t * math.pi * (4.5 if action_mode == "run" else 2.5 if action_mode == "walk" else 1.5)

        # Deslocamento real no espaço 3D
        rx = start_pos[0] + move_delta[0] * t
        ry = start_pos[1] + move_delta[1] * t
        rz = start_pos[2] + move_delta[2] * t
        rig["root"].location = (rx, ry, rz)
        rig["root"].keyframe_insert(data_path="location", frame=f)

        if action_mode in ("run", "walk"):
            amp_leg = 0.68 if action_mode == "run" else 0.36
            amp_arm = 0.62 if action_mode == "run" else 0.30
            bounce = abs(math.sin(phase)) * (0.11 if action_mode == "run" else 0.05)
            rig["pelvis"].location.z = 0.95 + bounce
            rig["pelvis"].keyframe_insert(data_path="location", frame=f)

            rig["torso"].rotation_euler = Euler((math.radians(12 if action_mode == "run" else 5), 0.0, math.sin(phase) * 0.08), "XYZ")
            rig["torso"].keyframe_insert(data_path="rotation_euler", frame=f)

            rig["leg_l"].rotation_euler = Euler((math.sin(phase) * amp_leg, 0.0, 0.0), "XYZ")
            rig["leg_r"].rotation_euler = Euler((-math.sin(phase) * amp_leg, 0.0, 0.0), "XYZ")
            rig["arm_l"].rotation_euler = Euler((-math.sin(phase) * amp_arm, 0.0, math.radians(-8)), "XYZ")
            rig["arm_r"].rotation_euler = Euler((math.sin(phase) * amp_arm, 0.0, math.radians(8)), "XYZ")
        else:
            # Respiração + gestos dramáticos naturais (nunca estátua congelada!)
            rig["pelvis"].location.z = 0.95 + math.sin(phase) * 0.03
            rig["pelvis"].keyframe_insert(data_path="location", frame=f)
            rig["torso"].rotation_euler = Euler((math.sin(phase) * 0.04, 0.0, math.sin(phase * 0.7) * 0.09), "XYZ")
            rig["torso"].keyframe_insert(data_path="rotation_euler", frame=f)

            if expression in ("shocked", "scared"):
                rig["arm_l"].rotation_euler = Euler((math.radians(-115 + 18 * math.sin(phase)), 0.0, math.radians(-22)), "XYZ")
                rig["arm_r"].rotation_euler = Euler((math.radians(-110 - 18 * math.sin(phase)), 0.0, math.radians(22)), "XYZ")
            elif expression in ("angry", "determined"):
                rig["arm_l"].rotation_euler = Euler((math.radians(-45 + 22 * math.sin(phase)), 0.0, math.radians(-10)), "XYZ")
                rig["arm_r"].rotation_euler = Euler((math.radians(-75 - 20 * math.sin(phase)), 0.0, math.radians(12)), "XYZ")
            else:
                rig["arm_l"].rotation_euler = Euler((math.radians(-15 + 14 * math.sin(phase)), 0.0, math.radians(-8)), "XYZ")
                rig["arm_r"].rotation_euler = Euler((math.radians(-25 - 16 * math.sin(phase)), 0.0, math.radians(10)), "XYZ")

            rig["leg_l"].rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
            rig["leg_r"].rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        # Movimento expressivo de cabeça (olhando em volta / reagindo)
        head_yaw = math.sin(phase * 0.85) * 0.24
        head_pitch = math.radians(-8 if expression in ("shocked", "curious") else 4) + math.cos(phase) * 0.06
        rig["head"].rotation_euler = Euler((head_pitch, 0.0, head_yaw), "XYZ")

        for k in ("leg_l", "leg_r", "arm_l", "arm_r", "head"):
            rig[k].keyframe_insert(data_path="rotation_euler", frame=f)


def build_environment_3d(
    theme: str,
    story_beat: str,
    seed: int,
    roughness_bias: float = 0.32,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Constrói cenário 3D real com arquitetura volumosa, piso PBR reflexivo, props tridimensionais
    e luzes práticas. Retorna (cor_accent_rgb, cor_sky_rgb).
    """
    rng = random.Random(seed)
    beat = (story_beat or "").lower()
    is_tense = any(k in beat for k in ("conflito", "clímax", "climax"))
    is_twist = "reviravolta" in beat or "twist" in beat

    if is_tense:
        accent_rgb = (0.95, 0.16, 0.22)
        sky_rgb = (0.03, 0.02, 0.06)
    elif is_twist:
        accent_rgb = (1.0, 0.72, 0.16)
        sky_rgb = (0.07, 0.05, 0.09)
    elif theme == "forest":
        accent_rgb = (0.18, 0.88, 0.48)
        sky_rgb = (0.02, 0.06, 0.07)
    elif theme == "neon":
        accent_rgb = (0.85, 0.20, 0.98)
        sky_rgb = (0.03, 0.02, 0.09)
    elif theme == "school":
        accent_rgb = (0.95, 0.56, 0.18)
        sky_rgb = (0.05, 0.07, 0.12)
    else:
        accent_rgb = (0.16, 0.68, 0.98)
        sky_rgb = (0.02, 0.04, 0.10)

    # Piso 3D amplo com material PBR (reflexos sutis de chão molhado/polido)
    mat_floor = _make_pbr_material(
        "env_floor",
        (0.06, 0.08, 0.12, 1.0) if theme != "forest" else (0.04, 0.10, 0.06, 1.0),
        roughness=max(0.14, roughness_bias - 0.10),
        metallic=0.12,
        noise_bump=0.14,
    )
    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0.0, 6.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "Env_Floor"
    floor.data.materials.append(mat_floor)

    mat_struct = _make_pbr_material("env_struct", (0.10, 0.13, 0.20, 1.0), roughness=roughness_bias + 0.18, noise_bump=0.12)
    mat_dark = _make_pbr_material("env_dark", (0.04, 0.05, 0.08, 1.0), roughness=0.45, metallic=0.2)
    mat_glow = _make_pbr_material(
        "env_glow",
        accent_rgb + (1.0,),
        roughness=0.15,
        emission_strength=6.5,
        emission_color=accent_rgb + (1.0,),
    )
    mat_warm = _make_pbr_material(
        "env_warm",
        (1.0, 0.78, 0.42, 1.0),
        roughness=0.2,
        emission_strength=5.0,
        emission_color=(1.0, 0.78, 0.42, 1.0),
    )

    if theme in ("school", "hallway"):
        # Corredor 3D real com paredes laterais, teto, armários 3D e porta iluminada ao fundo
        _add_beveled_box("Wall_Left", (0.5, 28.0, 6.0), (-4.2, 8.0, 3.0), mat_struct, bevel_width=0.04)
        _add_beveled_box("Wall_Right", (0.5, 28.0, 6.0), (4.2, 8.0, 3.0), mat_struct, bevel_width=0.04)
        _add_beveled_box("Ceiling", (9.0, 28.0, 0.4), (0.0, 8.0, 6.0), mat_dark, bevel_width=0.02)
        _add_beveled_box("Back_Wall", (9.0, 0.6, 6.2), (0.0, 19.0, 3.0), mat_dark, bevel_width=0.03)
        # Porta misteriosa 3D ao fundo com moldura emissiva
        _add_beveled_box("Mystery_Door_Frame", (2.6, 0.35, 4.0), (0.0, 18.5, 2.0), mat_glow, bevel_width=0.05)
        _add_beveled_box("Mystery_Door", (2.1, 0.42, 3.6), (0.0, 18.4, 1.8), mat_dark, bevel_width=0.04)
        # Armários 3D em fila nos dois lados + luminárias no teto
        mat_locker = _make_pbr_material("locker_blue", (0.08, 0.22, 0.44, 1.0), roughness=0.30, metallic=0.45)
        for idx in range(8):
            ly = -1.0 + idx * 2.4
            _add_beveled_box(f"Locker_L_{idx}", (0.7, 1.8, 3.2), (-3.55, ly, 1.6), mat_locker, bevel_width=0.04)
            _add_beveled_box(f"Locker_R_{idx}", (0.7, 1.8, 3.2), (3.55, ly, 1.6), mat_locker, bevel_width=0.04)
            if idx % 2 == 0:
                _add_beveled_box(f"Ceil_Light_{idx}", (2.2, 0.35, 0.12), (0.0, ly, 5.75), mat_glow if idx == 4 else mat_warm, bevel_width=0.02)

    elif theme == "forest":
        # Floresta 3D Roblox com pinheiros blocados em camadas e cabana iluminada ao fundo
        mat_trunk = _make_pbr_material("trunk", (0.18, 0.10, 0.05, 1.0), roughness=0.75, noise_bump=0.25)
        mat_leaf = _make_pbr_material("leaf", (0.04, 0.22, 0.10, 1.0), roughness=0.55, noise_bump=0.15)
        for idx in range(26):
            tx = rng.choice([-1, 1]) * rng.uniform(2.6, 12.0)
            ty = rng.uniform(-2.0, 22.0)
            h_scale = rng.uniform(0.85, 1.65)
            _add_beveled_box(f"Trunk_{idx}", (0.55, 0.55, 2.4 * h_scale), (tx, ty, 1.2 * h_scale), mat_trunk, bevel_width=0.04)
            for tier in range(3):
                w_tier = (2.2 - tier * 0.52) * h_scale
                z_tier = (2.3 + tier * 1.15) * h_scale
                _add_beveled_box(f"Leaf_{idx}_{tier}", (w_tier, w_tier, 1.15 * h_scale), (tx, ty, z_tier), mat_leaf, bevel_width=0.08)
        # Cabana 3D ao fundo com janela brilhante
        _add_beveled_box("Cabin_Body", (4.8, 4.2, 3.4), (0.0, 15.5, 1.7), mat_trunk, bevel_width=0.06)
        _add_beveled_box("Cabin_Window", (1.4, 0.2, 1.2), (0.0, 13.35, 1.9), mat_warm, bevel_width=0.02)
        # Vagalumes / partículas luminosas 3D
        for idx in range(18):
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.07, location=(rng.uniform(-4.5, 4.5), rng.uniform(-1.0, 12.0), rng.uniform(0.6, 4.2)))
            bpy.context.active_object.data.materials.append(mat_glow)

    elif theme == "castle":
        # Pátio de castelo 3D com torres, muralhas e portal brilhante
        mat_stone = _make_pbr_material("stone", (0.14, 0.13, 0.18, 1.0), roughness=0.72, noise_bump=0.30)
        for sx in (-5.5, 5.5):
            _add_beveled_box(f"Tower_{sx}", (3.0, 3.0, 10.5), (sx, 12.5, 5.25), mat_stone, bevel_width=0.08)
            _add_beveled_box(f"Pillar_{sx}", (1.2, 1.2, 5.5), (sx * 0.65, 5.5, 2.75), mat_stone, bevel_width=0.06)
            # Tocha 3D
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(sx * 0.65, 4.7, 3.4))
            bpy.context.active_object.data.materials.append(mat_warm)
        # Portal antigo 3D central
        bpy.ops.mesh.primitive_torus_add(major_radius=2.5, minor_radius=0.38, location=(0.0, 11.5, 3.0), rotation=(math.radians(90), 0.0, 0.0))
        bpy.context.active_object.data.materials.append(mat_stone)
        bpy.ops.mesh.primitive_cylinder_add(radius=2.2, depth=0.12, location=(0.0, 11.5, 3.0), rotation=(math.radians(90), 0.0, 0.0))
        bpy.context.active_object.data.materials.append(mat_glow)

    else:
        # Cidade / Servidor Roblox 3D completo com rua/praça, calçadas, prédios com janelas emissivas, postes e portal
        # Calçadas elevadas 3D
        _add_beveled_box("Sidewalk_L", (4.5, 36.0, 0.24), (-5.4, 10.0, 0.12), mat_struct, bevel_width=0.04)
        _add_beveled_box("Sidewalk_R", (4.5, 36.0, 0.24), (5.4, 10.0, 0.12), mat_struct, bevel_width=0.04)
        # Faixas da rua / plataforma de spawn luminosa
        _add_beveled_box("Spawn_Pad", (3.2, 3.2, 0.12), (0.0, 0.0, 0.06), mat_dark, bevel_width=0.04)
        _add_beveled_box("Spawn_Ring", (3.5, 3.5, 0.05), (0.0, 0.0, 0.03), mat_glow, bevel_width=0.02)

        # Prédios 3D dos dois lados criando rua em perspectiva profunda
        for idx in range(7):
            by = 1.5 + idx * 4.4
            for side in (-1, 1):
                bh = rng.uniform(7.5, 16.0)
                bx = side * rng.uniform(6.6, 8.2)
                _add_beveled_box(f"Bldg_{side}_{idx}", (3.8, 3.6, bh), (bx, by, bh / 2.0), mat_struct, bevel_width=0.08)
                # Janelas 3D emissivas na fachada voltada para a rua
                face_x = bx - side * 1.92
                for wy in range(2, int(bh) - 1, 2):
                    if rng.random() > 0.25:
                        wmat = mat_glow if rng.random() > 0.55 else mat_warm
                        _add_beveled_box(f"Win_{side}_{idx}_{wy}", (0.08, 2.2, 0.65), (face_x, by, float(wy)), wmat, bevel_width=0.01)

        # Postes de luz 3D ao longo da rua
        for idx in range(4):
            py = 2.0 + idx * 5.2
            for side in (-1, 1):
                px = side * 3.4
                _add_cylinder(f"LampPost_{side}_{idx}", radius=0.08, depth=4.6, location=(px, py, 2.3), material=mat_dark)
                _add_beveled_box(f"LampHead_{side}_{idx}", (0.65, 0.25, 0.14), (px - side * 0.28, py, 4.55), mat_warm, bevel_width=0.02)

        # Grande painel/portal holográfico 3D no fundo da avenida
        _add_beveled_box("Server_Pillar_L", (0.7, 0.7, 7.0), (-3.2, 16.0, 3.5), mat_dark, bevel_width=0.05)
        _add_beveled_box("Server_Pillar_R", (0.7, 0.7, 7.0), (3.2, 16.0, 3.5), mat_dark, bevel_width=0.05)
        _add_beveled_box("Server_Header", (7.4, 0.8, 0.9), (0.0, 16.0, 7.0), mat_glow, bevel_width=0.05)
        _add_beveled_box("Server_Holo", (5.6, 0.16, 4.4), (0.0, 16.0, 3.9), mat_glow, bevel_width=0.04)

    return accent_rgb, sky_rgb


def setup_cinematic_lighting(
    accent_rgb: Tuple[float, float, float],
    sky_rgb: Tuple[float, float, float],
    is_studio_ref: bool = False,
) -> None:
    """Configura iluminação global de mundo, luz chave, contra-luz (rim light) e preenchimento suave."""
    world = bpy.data.worlds.new("StudioWorld")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.06, 0.09, 0.16, 1.0) if is_studio_ref else (sky_rgb[0], sky_rgb[1], sky_rgb[2], 1.0)
        bg.inputs["Strength"].default_value = 0.85 if is_studio_ref else 0.45

    def _add_area(name: str, loc: Tuple[float, float, float], rot_deg: Tuple[float, float, float], energy: float, size: float, col: Tuple[float, float, float]) -> None:
        ldata = bpy.data.lights.new(name=name, type="AREA")
        ldata.energy = energy
        ldata.size = size
        ldata.color = col
        lobj = bpy.data.objects.new(name=name, object_data=ldata)
        bpy.context.collection.objects.link(lobj)
        lobj.location = loc
        lobj.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")

    # Key light cinematográfica (suave com sombras realistas)
    _add_area("KeyLight", (3.6, -4.2, 5.2), (52.0, 0.0, 38.0), 420.0 if is_studio_ref else 340.0, 2.8, (1.0, 0.95, 0.88))
    # Fill light fria para volume nas sombras
    _add_area("FillLight", (-4.2, -3.0, 3.2), (65.0, 0.0, -52.0), 160.0 if is_studio_ref else 115.0, 3.6, (0.58, 0.76, 1.0))
    # Rim light dramática (separa os avatares 3D do fundo!)
    _add_area("RimLight", (0.0, 5.5, 4.4), (118.0, 0.0, 180.0), 520.0, 3.2, accent_rgb)


def setup_animated_camera(
    camera_movement: str,
    focus_target: bpy.types.Object,
    frame_start: int,
    frame_end: int,
    has_two_chars: bool = False,
) -> bpy.types.Object:
    """Cria câmera 3D cinematográfica com Depth of Field e movimento real no espaço 3D."""
    cam_data = bpy.data.cameras.new("MainCamera")
    cam_data.lens = 42.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = focus_target
    cam_data.dof.aperture_fstop = 2.8

    cam = bpy.data.objects.new("MainCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    # Constraint Track-To para manter o protagonista enquadrado com naturalidade durante o movimento 3D
    track = cam.constraints.new(type="TRACK_TO")
    track.target = focus_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    base_dist = -7.2 if has_two_chars else -5.4
    if camera_movement == "slow_zoom_out":
        p0, p1 = (0.3, base_dist + 1.4, 2.1), (-0.4, base_dist - 1.2, 2.6)
    elif camera_movement == "pan_left":
        p0, p1 = (2.1, base_dist, 2.2), (-2.1, base_dist + 0.3, 2.3)
    elif camera_movement == "pan_right":
        p0, p1 = (-2.1, base_dist, 2.2), (2.1, base_dist + 0.3, 2.3)
    elif camera_movement == "tilt_up":
        p0, p1 = (0.6, base_dist + 0.5, 1.05), (-0.4, base_dist - 0.3, 3.1)
    elif camera_movement == "dramatic_push":
        p0, p1 = (-0.8, base_dist - 0.6, 2.3), (0.35, base_dist + 2.2, 2.05)
    elif camera_movement == "parallax_drift":
        p0, p1 = (-2.4, base_dist + 0.4, 2.0), (2.2, base_dist - 0.5, 2.65)
    else:  # slow_zoom_in
        p0, p1 = (-0.5, base_dist - 0.8, 2.35), (0.4, base_dist + 1.3, 2.05)

    cam.location = p0
    cam.keyframe_insert(data_path="location", frame=frame_start)
    cam.location = p1
    cam.keyframe_insert(data_path="location", frame=frame_end)
    return cam


def _enable_cycles_gpu(scene: bpy.types.Scene, gpu_device: str = "auto") -> bool:
    """Ativa aceleração CUDA/OptiX (ideal para NVIDIA T4/L4/A100 no Google Colab) com fallback seguro para CPU."""
    if str(gpu_device).lower() == "cpu":
        scene.cycles.device = "CPU"
        return False

    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        backends = ["OPTIX", "CUDA", "HIP", "ONEAPI"]
        if str(gpu_device).upper() in backends:
            backends = [str(gpu_device).upper()] + [b for b in backends if b != str(gpu_device).upper()]

        for backend in backends:
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                gpu_devs = [d for d in prefs.devices if d.type != "CPU"]
                if gpu_devs:
                    for d in prefs.devices:
                        d.use = d.type != "CPU"
                    scene.cycles.device = "GPU"
                    return True
            except Exception:
                continue
    except Exception:
        pass

    scene.cycles.device = "CPU"
    return False


def configure_render_settings(
    width: int,
    height: int,
    fps: int,
    engine: str,
    samples: int,
    color_look: str,
    gpu_device: str = "auto",
) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        scene.render.image_settings.compression = 15
    except Exception:
        pass
    try:
        scene.render.use_persistent_data = True
    except Exception:
        pass

    # Compatibilidade entre Blender 3.x/4.0-4.1/4.2-4.5 (BLENDER_EEVEE_NEXT) e 5.0+ (BLENDER_EEVEE)
    engine_candidates = [engine]
    if engine == "BLENDER_EEVEE":
        engine_candidates.append("BLENDER_EEVEE_NEXT")
    elif engine == "BLENDER_EEVEE_NEXT":
        engine_candidates.append("BLENDER_EEVEE")
    engine_candidates.append("CYCLES")

    for eng in engine_candidates:
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue

    if scene.render.engine == "CYCLES":
        using_gpu = _enable_cycles_gpu(scene, gpu_device=gpu_device)
        scene.cycles.samples = max(12 if using_gpu else 8, samples)
        scene.cycles.use_denoising = True
        try:
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.05
            scene.cycles.max_bounces = 4
            scene.cycles.diffuse_bounces = 2
            scene.cycles.glossy_bounces = 2
            scene.cycles.transmission_bounces = 2
            scene.cycles.transparent_max_bounces = 4
            scene.cycles.sample_clamp_indirect = 5.0
        except Exception:
            pass
    else:
        if hasattr(scene, "eevee"):
            scene.eevee.taa_render_samples = max(8, samples)
            if hasattr(scene.eevee, "use_raytracing"):
                scene.eevee.use_raytracing = False

    # Color management cinematográfico (AgX)
    for vt in ("AgX", "Filmic", "Standard"):
        try:
            scene.view_settings.view_transform = vt
            break
        except Exception:
            continue
    try:
        scene.view_settings.look = color_look
    except Exception:
        pass


def render_reference_mode(spec: Dict[str, Any]) -> None:
    _clear_scene()
    res = int(spec.get("resolution", 768))
    roughness_bias = float(spec.get("roughness_bias", 0.32))
    configure_render_settings(
        width=res,
        height=res,
        fps=24,
        engine=spec.get("engine", "BLENDER_EEVEE"),
        samples=int(spec.get("samples", 24)),
        color_look=spec.get("color_look", "AgX - Medium High Contrast"),
        gpu_device=str(spec.get("gpu_device", "auto")),
    )

    # Piso de estúdio reflexivo + fundo suave
    mat_stage = _make_pbr_material("studio_floor", (0.07, 0.09, 0.14, 1.0), roughness=0.18, metallic=0.15)
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0.0, 0.0, 0.0))
    bpy.context.active_object.data.materials.append(mat_stage)

    rig = build_roblox_character_3d(
        spec["character"],
        base_location=(0.0, 0.0, 0.0),
        yaw_deg=18.0,
        expression="curious",
        roughness_bias=roughness_bias,
    )
    setup_cinematic_lighting((0.25, 0.68, 1.0), (0.06, 0.09, 0.16), is_studio_ref=True)

    cam_data = bpy.data.cameras.new("RefCam")
    cam_data.lens = 50.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = rig["head"]
    cam_data.dof.aperture_fstop = 4.0
    cam = bpy.data.objects.new("RefCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0.95, -5.8, 2.05)
    aim_target = _add_empty("RefAim", (0.0, 0.0, 1.50))
    track = cam.constraints.new(type="TRACK_TO")
    track.target = aim_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    bpy.context.scene.render.filepath = str(spec["output_path"])
    bpy.ops.render.render(write_still=True)


def render_scene_mode(spec: Dict[str, Any]) -> None:
    _clear_scene()
    width = int(spec.get("width", 540))
    height = int(spec.get("height", 960))
    fps = int(spec.get("fps", 15))
    duration = float(spec.get("duration_seconds", 5.0))
    frame_start = 1
    frame_end = max(18, int(round(duration * fps)))
    roughness_bias = float(spec.get("roughness_bias", 0.32))

    configure_render_settings(
        width=width,
        height=height,
        fps=fps,
        engine=spec.get("engine", "BLENDER_EEVEE"),
        samples=int(spec.get("samples", 16)),
        color_look=spec.get("color_look", "AgX - Medium High Contrast"),
        gpu_device=str(spec.get("gpu_device", "auto")),
    )
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end

    accent_rgb, sky_rgb = build_environment_3d(
        theme=str(spec.get("setting_theme", "server")),
        story_beat=str(spec.get("story_beat", "Desenvolvimento")),
        seed=int(spec.get("seed", 42)),
        roughness_bias=roughness_bias,
    )
    setup_cinematic_lighting(accent_rgb, sky_rgb, is_studio_ref=False)

    chars: List[Dict[str, Any]] = spec.get("characters") or []
    expr = str(spec.get("expression", "curious"))
    movements_text = str(spec.get("movements_en", "")).lower()
    if any(k in movements_text for k in ("sprint", "run", "chase", "escape", "correndo")):
        action_mode = "run"
    elif any(k in movements_text for k in ("walk", "enter", "step", "andando")):
        action_mode = "walk"
    else:
        action_mode = "gesture"

    lead_rig: Dict[str, bpy.types.Object] | None = None
    if len(chars) >= 2:
        rig1 = build_roblox_character_3d(chars[0], (-0.95, 0.2, 0.0), yaw_deg=-24.0, expression=expr, roughness_bias=roughness_bias)
        delta1 = (0.35, -0.7, 0.0) if action_mode in ("run", "walk") else (0.12, -0.18, 0.0)
        animate_roblox_character(rig1, frame_start, frame_end, action_mode, expr, (-0.95, 0.2, 0.0), delta1)

        rig2 = build_roblox_character_3d(chars[1], (1.15, 2.1, 0.0), yaw_deg=26.0, expression="angry", roughness_bias=roughness_bias)
        delta2 = (-0.25, -0.8, 0.0) if action_mode == "run" else (-0.15, -0.25, 0.0)
        animate_roblox_character(rig2, frame_start, frame_end, "walk" if action_mode == "run" else "gesture", "angry", (1.15, 2.1, 0.0), delta2)
        lead_rig = rig1
    elif len(chars) == 1:
        rig1 = build_roblox_character_3d(chars[0], (0.0, 0.6, 0.0), yaw_deg=12.0, expression=expr, roughness_bias=roughness_bias)
        delta1 = (0.0, -1.6, 0.0) if action_mode == "run" else (0.0, -0.9, 0.0) if action_mode == "walk" else (0.0, -0.2, 0.0)
        animate_roblox_character(rig1, frame_start, frame_end, action_mode, expr, (0.0, 0.6, 0.0), delta1)
        lead_rig = rig1

    focus_obj = lead_rig["head"] if lead_rig else _add_empty("CenterFocus", (0.0, 0.5, 1.6))
    setup_animated_camera(
        camera_movement=str(spec.get("camera_movement", "slow_zoom_in")),
        focus_target=focus_obj,
        frame_start=frame_start,
        frame_end=frame_end,
        has_two_chars=(len(chars) >= 2),
    )

    frames_dir = Path(spec["frames_dir"])
    frames_dir.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(frames_dir / "frame_")
    bpy.ops.render.render(animation=True)


def main() -> None:
    if "--" not in sys.argv:
        raise RuntimeError("Passe '-- <spec.json>' ao executar blender_scene_script.py")
    spec_path = Path(sys.argv[sys.argv.index("--") + 1])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    mode = spec.get("mode", "scene")
    if mode == "reference":
        render_reference_mode(spec)
    else:
        render_scene_mode(spec)


if __name__ == "__main__":
    main()
