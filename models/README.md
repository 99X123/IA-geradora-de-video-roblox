# Modelos Locais — Tamanhos, Licenças e Instalação

Este diretório armazena os modelos locais utilizados no modo **100% Gratuito** (custo de API: R$ 0; o processamento utiliza apenas o seu computador, energia elétrica e armazenamento local).

> **Importante sobre licenças:** Verifique sempre os termos de uso de cada modelo antes de uso comercial em larga escala. Abaixo constam as licenças oficiais de cada ferramenta/modelo.

## 1. Narração Local (TTS — Português Brasileiro)

### Kokoro-82M v1.0 (Recomendado)
- **Licença dos pesos:** Apache-2.0 (`hexgrad/Kokoro-82M`)
- **Licença do runtime (`kokoro-onnx`):** MIT
- **Tamanho aproximado:**
  - `models/kokoro/kokoro-v1.0.int8.onnx` (~88 MB — leve e rápido em CPU)
  - `models/kokoro/voices-v1.0.bin` (~27 MB — inclui vozes PT-BR `pf_dora`, `pm_alex`, `pm_santa`)
- **Observação:** O instalador (`install.bat`) pergunta antes de baixar. Também pode ser baixado pela interface do aplicativo.

### Piper TTS (Alternativa Open Source)
- **Licença:** MIT (vozes variam entre MIT/CC-BY; `pt_BR-faber-medium` usa licença aberta permissiva)
- **Tamanho aproximado:** ~63 MB (`models/piper/pt_BR-faber-medium.onnx` + `.json`)

## 2. Legendas Automáticas (Whisper Local)

### Faster-Whisper (CTranslate2 / OpenAI Whisper)
- **Licença:** MIT (OpenAI Whisper + Faster-Whisper)
- **Pasta:** `models/whisper/`
- **Tamanhos aproximados:**
  - `tiny`: ~75 MB (ultra rápido em CPU fraca)
  - `base`: ~145 MB (bom equilíbrio em PT-BR para CPU)
  - `small`: ~480 MB (alta precisão em PT-BR)
  - `medium`: ~1.5 GB (recomendado para PCs com GPU ou CPU rápida)

## 3. Roteiro Local (Ollama + Gemma 3)

### Gemma 3 via Ollama
- **Licença:** Gemma Terms of Use (Google — permite uso pessoal e comercial dentro dos termos da licença Gemma, sujeito à Política de Uso Proibido da Google; **não** é domínio público irrestrito).
- **Instalação:** https://ollama.com/
- **Modelos e tamanhos aproximados:**
  - `ollama pull gemma3:1b` (~815 MB — PCs com 8 GB RAM)
  - `ollama pull gemma3:4b` (~3.3 GB — PCs com 16 GB RAM, recomendado)
  - `ollama pull gemma3:12b` (~8.1 GB — PCs com GPU >= 12 GB VRAM ou 32 GB RAM)

## 4. Geração de Vídeos e Imagens Locais (ComfyUI + Wan 2.2)

### Wan 2.2 TI2V-5B (Vídeo Local)
- **Licença:** Apache-2.0 (`Wan-Video/Wan2.2`)
- **Hardware mínimo recomendado:** GPU NVIDIA com **12 GB+ VRAM** (preferencialmente 16–24 GB VRAM) e 32 GB RAM.
- **Tamanhos aproximados (instalados na pasta `models/` do ComfyUI):**
  - `diffusion_models/wan2.2_ti2v_5B_fp16.safetensors` (~10 GB)
  - `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` (~6.7 GB)
  - `vae/wan2.2_vae.safetensors` (~1.4 GB)
- **Aviso:** O Roblox AI Shorts Studio **bloqueia automaticamente** a execução do Wan 2.2 em GPUs com menos de 12 GB de VRAM para evitar travamentos e alterna para o modo de imagens animadas.

### Geração de Imagens Local (Plano Alternativo com ComfyUI)
- **Hardware mínimo recomendado:** GPU com **4–8 GB VRAM** (ex.: SD 1.5 / SDXL Turbo / Flux Schnell).
- **Licenças:** SDXL Base 1.0 (CreativeML Open RAIL++-M), FLUX.1-schnell (Apache-2.0).
- **Tamanho aproximado:** ~2.5 GB a 6.9 GB (colocar em `ComfyUI/models/checkpoints/`).
