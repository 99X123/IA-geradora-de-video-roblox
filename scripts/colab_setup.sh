#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/4] Instalando FFmpeg, fontes e bibliotecas graficas para Blender headless ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ffmpeg \
  fonts-dejavu-core \
  fonts-liberation \
  espeak-ng \
  libxi6 \
  libxrender1 \
  libxxf86vm1 \
  libxfixes3 \
  libxkbcommon0 \
  libsm6 \
  libegl1 \
  libgl1 \
  libgl1-mesa-dri \
  libvulkan1 \
  xvfb \
  xz-utils \
  curl >/dev/null

echo "=== [2/4] Verificando / instalando Blender 3D (5.3.0 Linux x64 — compativel com motor rbx + GPU CUDA/OptiX) ==="
BLENDER_DIR="/opt/blender"
DRIVE_CACHE_DIR="${DRIVE_ROOT:-}/cache"
BLENDER_TAR_NAME="blender-5.3.0-linux-x64.tar.xz"
BLENDER_CANDIDATE_URLS=(
  "https://download.blender.org/release/Blender5.3/blender-5.3.0-linux-x64.tar.xz"
  "https://download.blender.org/release/Blender5.2/blender-5.2.4-linux-x64.tar.xz"
  "https://download.blender.org/release/Blender5.0/blender-5.0.1-linux-x64.tar.xz"
  "https://download.blender.org/release/Blender4.2/blender-4.2.9-linux-x64.tar.xz"
)

if [ ! -x "${BLENDER_DIR}/blender" ] && ! command -v blender >/dev/null 2>&1; then
  TAR_PATH="/tmp/${BLENDER_TAR_NAME}"
  # Reutiliza cache no Google Drive se ja tiver baixado antes
  if [ -n "${DRIVE_ROOT:-}" ] && [ -f "${DRIVE_CACHE_DIR}/${BLENDER_TAR_NAME}" ]; then
    echo "Blender encontrado em cache no Google Drive! Extraindo..."
    TAR_PATH="${DRIVE_CACHE_DIR}/${BLENDER_TAR_NAME}"
  else
    DOWNLOADED=0
    for URL in "${BLENDER_CANDIDATE_URLS[@]}"; do
      echo "Baixando ${URL} ..."
      if curl -fL --retry 3 -o "${TAR_PATH}" "${URL}"; then
        DOWNLOADED=1
        # Salva copia no cache do Google Drive se montado (acelera futuras sessoes)
        if [ -n "${DRIVE_ROOT:-}" ] && [ -d "${DRIVE_ROOT}" ]; then
          mkdir -p "${DRIVE_CACHE_DIR}"
          cp -f "${TAR_PATH}" "${DRIVE_CACHE_DIR}/${BLENDER_TAR_NAME}" 2>/dev/null || true
        fi
        break
      fi
    done
    if [ "${DOWNLOADED}" -eq 0 ]; then
      echo "Fallback: instalando Blender via apt-get..."
      apt-get install -y -qq blender >/dev/null
      TAR_PATH=""
    fi
  fi

  if [ -n "${TAR_PATH}" ] && [ -f "${TAR_PATH}" ]; then
    mkdir -p "${BLENDER_DIR}"
    tar -xf "${TAR_PATH}" -C "${BLENDER_DIR}" --strip-components=1
    if [ "${TAR_PATH}" = "/tmp/${BLENDER_TAR_NAME}" ]; then
      rm -f "${TAR_PATH}"
    fi
    ln -sf "${BLENDER_DIR}/blender" /usr/local/bin/blender
  fi
fi

if command -v blender >/dev/null 2>&1; then
  blender --version | head -n 1
else
  echo "Aviso: Blender nao encontrado; o estudio usara o modo alternativo FFmpeg."
fi

if [ -f "engine/rbx/__init__.py" ]; then
  echo "Motor 3D rbx (skill Roblox embutido): OK -> $(pwd)/engine"
fi

echo "=== [3/4] Instalando dependencias Python ==="
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "=== [4/4] Baixando modelos leves (Kokoro TTS + Whisper) com cache no Google Drive ==="
python3 main.py --colab --download-small-models
python3 main.py --colab --doctor

echo "=== Setup concluido com sucesso! ==="
