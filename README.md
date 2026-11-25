# AutoShorts AI — Fábrica Automatizada de Vídeos Curtos 3D

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/99X123/IA-geradora-de-video-roblox/blob/main/AutoShorts_Colab.ipynb)

> 📖 **Quer um passo a passo completo para subir no GitHub e rodar no Colab sem dor de cabeça?** Leia o [TUTORIAL.md](TUTORIAL.md).

**AutoShorts AI** é um sistema modular e completo capaz de receber apenas um **tema** e produzir automaticamente um vídeo curto vertical **9:16 (1080×1920, 30 fps, H.264 + AAC, `yuv420p`)**, animado 100% em código com **Three.js (estilo toon/cel-shading)**, narrado em **português brasileiro** por vozes sintetizadas por IA, com **alinhamento forçado palavra por palavra**, **legendas dinâmicas + SRT**, **efeitos sonoros procedurais**, **música original**, **controle de qualidade técnico/visual**, **armazenamento automático no Google Drive** e **revisão independente via OpenCode CLI**.

> **Nota de transparência técnica:** Nenhum pacote pré-existente `kit/` ou `toon-short-kit.zip` foi encontrado no repositório. Todos os módulos do motor 3D toon, enquadramento matemático de câmera, personagens originais, cenários, renderização via Playwright/FFmpeg e síntese de SFX foram implementados integralmente do zero seguindo rigorosamente a especificação técnica do `SKILL.md`, utilizando exclusivamente personagens 100% originais.

---

## Arquitetura do Projeto

```text
AutoShortsAI/
├── AutoShorts_Colab.ipynb       # Notebook principal de produção no Google Colab
├── package.json                 # Dependências Node.js fixadas (three 0.170.0, playwright 1.49.1)
├── requirements-colab.txt       # Dependências Python compatíveis com Colab e local
├── config/
│   ├── default_config.json      # Configuração central (vídeo, história, TTS, legendas, SFX, QA, Drive, OpenCode)
│   └── credentials.example.json # Modelo de variáveis de ambiente / Colab Secrets (nunca commitar chaves!)
├── engine/                      # Motor 3D Toon (Three.js + Playwright + FFmpeg image2pipe)
│   ├── index.html               # Import map local + canvas 1080x1920 + fonte Inter 900
│   ├── renderer.js              # WebGLRenderer, EffectComposer, UnrealBloomPass, gradiente toon 4 níveis, outline inverted hull
│   ├── characters.js            # Rigs originais: Human, Bot, Pigeon, Phantom, GiantMech, RockBuddy + face canvas 512px + lip-sync
│   ├── scenes.js                # 5 cenários (living_room, kitchen, entry_hall, town_square, studio) + 15 props
│   ├── camera.js                # Enquadramento matemático fit()/move()/audit() acima do chão e fora da faixa de legendas
│   ├── captions.js              # Legendas palavra por palavra com contorno escuro, destaque por personagem e pop suave
│   ├── effects.js               # Overlays determinísticos 2D (vinheta, speed lines, confete, faíscas, texto de impacto, shake)
│   ├── film_runtime.js          # Runtime determinístico orientado por storyboard.json + sync_data.json
│   ├── render_worker.mjs        # Worker Chromium com detecção real de GPU vs SwiftShader e pipe direto para FFmpeg
│   └── render_all.mjs           # Renderização paralela em partes resumível + concatenação -c copy + mux AAC
├── src/                         # Pipeline de automação em Python
│   ├── config.py                # Carregador central + leitura segura de Secrets + redação de segredos
│   ├── utils.py                 # Descoberta de FFmpeg/FFprobe/Node, silencedetect, mídia probe, logging
│   ├── story_generator.py       # Gerador de histórias/personagens (Gemini, OpenAI-compatível, fallback PT-BR local)
│   ├── tts_engine.py            # TTS plugável (Google Cloud TTS, Edge TTS PT-BR, OpenAI TTS, synth offline de teste)
│   ├── audio_processor.py       # Análise real de áudio, alinhamento forçado (faster-whisper / WordBoundary / fallback acústico) + lip-sync ENV
│   ├── subtitle_generator.py    # Agrupamento dinâmico até 3 palavras + geração de SRT e data.js
│   ├── storyboard_generator.py  # Planejamento de 18-30 tomadas/min sem repetir ângulos + storyboard visual HTML/folha de contato
│   ├── sfx_synthesizer.py       # 22 geradores procedurais NumPy (44.1kHz) + música original + mixagem FFmpeg loudnorm
│   ├── video_orchestrator.py    # Orquestrador ponta a ponta + retomada + re-render parcial de partes
│   ├── quality_checker.py       # Gate técnico (codec, FPS, resolução, blackdetect, áudio, SRT) + QA visual + Vision IA opcional
│   ├── drive_manager.py         # Montagem oficial Colab Drive + estrutura `Meu Drive/AutoShorts AI/` + bloqueio de credenciais
│   └── opencode_reviewer.py     # Agente independente OpenCode CLI (backup prévio, limite de 3 ciclos, reteste obrigatório)
├── scripts/
│   ├── run_production.py        # CLI de produção completa a partir de um tema
│   └── run_opencode_review.py   # CLI de auditoria independente via OpenCode
├── examples/                    # Exemplo completo de projeto gerado e verificado
└── tests/                       # Suíte automatizada pytest
```

---

## Execução no Google Colab (Ambiente Principal Recomendado)

1. Abra [`AutoShorts_Colab.ipynb`](AutoShorts_Colab.ipynb) no Google Colab.
2. Ative uma GPU em **Ambiente de execução → Alterar tipo de ambiente de execução → T4 GPU**.
3. Configure suas credenciais de forma segura em **Colab Secrets** (barra lateral esquerda, ícone de chave) — **nunca** coloque chaves no código ou no Google Drive:
   - `GEMINI_API_KEY`: geração de roteiros via Gemini e inspeção visual opcional (Vision IA).
   - `OPENAI_API_KEY`: alternativa para geração de roteiros, TTS ou Vision IA.
   - `GOOGLE_APPLICATION_CREDENTIALS` ou `GOOGLE_API_KEY`: opcional para Google Cloud Text-to-Speech (por padrão o sistema já oferece vozes neurais PT-BR expressivas via `edge-tts` sem necessidade de chave!).
   - `OPENCODE_MODEL`: modelo configurado no OpenCode CLI (ex.: qualquer identificador listado por `opencode models`).
4. Execute as células em sequência. Na Célula 6, basta definir o `TEMA` e rodar a Célula 7.

### Estrutura Criada Automaticamente no Google Drive

```text
Meu Drive/AutoShorts AI/
├── Videos/       # MP4 final pronto (1080x1920, H.264 + AAC)
├── Projects/     # Pasta dedicada por projeto com todos os artefatos
├── Audio/        # vo.wav e mix.wav
├── Scripts/      # story.json com roteiro completo
├── Storyboards/  # storyboard.json e folha de contato visual
├── Subtitles/    # subtitles.srt e sync_data.json
├── Logs/         # Logs de execução com segredos redigidos
├── Reports/      # Relatório técnico/visual de QA e folha de contato QA
└── Backups/      # Backups de segurança
```

---

## Execução Local (Windows / Linux / macOS)

```bash
# 1. Instalar dependências Python e Node.js
pip install -r requirements-colab.txt
npm install
npx playwright install chromium

# 2. Verificar GPU / WebGL real do Chromium (Hardware vs SwiftShader)
npm run probe

# 3. Produzir um vídeo completo a partir de apenas um tema
python scripts/run_production.py --theme "meu robô decidiu cozinhar feijoada" --duration 60

# 4. (Opcional) Pausar para aprovação visual do storyboard antes de renderizar
python scripts/run_production.py --theme "um pombo virou síndico do prédio" --pause-storyboard
# Depois de revisar o storyboard HTML/PNG:
python scripts/run_production.py --theme "um pombo virou síndico do prédio" --project-id <ID> --approved

# 5. Rodar testes automatizados
python -m pytest -v

# 6. Rodar revisão independente via OpenCode CLI (usando um modelo listado em `opencode models`)
python scripts/run_opencode_review.py --model <provider/model>
```

---

## Regras de Segurança & Confiabilidade Implementadas

- **Detecção honesta de WebGL:** `engine/render_worker.mjs probe` consulta `WEBGL_debug_renderer_info` (`UNMASKED_RENDERER_WEBGL`). Nunca afirma que houve aceleração por GPU caso o Chromium esteja usando `SwiftShader` ou `llvmpipe`.
- **Renderização sem milhares de PNGs:** cada worker envia buffers JPEG diretamente via `stdin` (`-f image2pipe`) para o FFmpeg codificar partes `.tmp.mp4`, renomeando atomicamente para `.mp4` somente com código de saída `0`.
- **Alinhamento forçado honesto:** nunca usa contagem de palavras disfarçada de alinhamento. Prioriza `faster-whisper` ou eventos reais `WordBoundary` validados contra `silencedetect` e energia do WAV; quando cai para o fallback acústico por envelope de energia, registra explicitamente `fallback_used: true` e avisos no relatório.
- **Proteção de credenciais:** `DriveManager` bloqueia arquivos `.env`, `*credential*`, `*secret*`, `*.key`, `*.pem` e redige segredos de logs/JSONs antes de salvar no Google Drive.
- **Controle de qualidade estrito:** vídeos que falham em qualquer verificação técnica (resolução, FPS, duração, codec H.264/AAC, `yuv420p`, integridade de decodificação, frames pretos inesperados, áudio cortado/silencioso, compatibilidade de SRT) recebem `approved: false` automaticamente.
- **OpenCode seguro:** trabalha apenas dentro do diretório do projeto, cria backup zip em `backups/` antes de qualquer revisão/edição, limita tentativas automáticas a **3 ciclos por erro**, executa `pytest` após cada ciclo e nunca simula verificação quando não configurado.
