# 🎬 ROBLOX AI SHORTS STUDIO

Plataforma local e automatizada em Python para criar vídeos verticais **9:16 (1080×1920)** de histórias de **Roblox** prontos para **YouTube Shorts** e **TikTok**, priorizando **ferramentas open source, inteligência artificial gratuita e execução local**, com **troca automática entre Google Flow e modo 100% gratuito**.

---

## ✨ Principais Recursos

- **3 Modos de Geração com Troca Automática:**
  1. **Google Flow (Modo A):** gera roteiro, storyboard, fichas visuais de personagens e pacote completo de prompts em inglês para gerar clipes na interface oficial do [Google Flow](https://labs.google/fx/tools/flow), com importação fácil dos vídeos gerados.
  2. **100% Gratuito (Modo B):** usa exclusivamente ferramentas locais (`Ollama + Gemma 3`, `ComfyUI + Wan 2.2` ou plano alternativo em CPU, `Kokoro TTS`, `Whisper`, `FFmpeg`) com **R$ 0 em cobranças de API, créditos ou assinaturas adicionais**.
  3. **Automático — Flow + Gratuito (Modo C):** aproveita os créditos disponíveis do Flow na conta autorizada e inclui o botão **🚨 MEUS CRÉDITOS DO FLOW ACABARAM**, que alterna na hora para o modo local gratuito **preservando todas as cenas já importadas** sem interromper o projeto.
- **Detecção Real de Hardware + Modo Computador Fraco:**
  - Detecta GPU, VRAM, RAM, CPU, espaço em disco, FFmpeg, Ollama e ComfyUI.
  - **Bloqueia automaticamente o Wan 2.2** em placas sem VRAM/CUDA compatível (evitando travamentos).
  - Em PCs sem GPU forte, ativa automaticamente o **Plano Alternativo**: renderiza imagens consistentes estilizadas de Roblox (ou imagens locais via ComfyUI/usuário, ou gravações do Roblox Studio) e anima com **zoom cinematográfico (Ken Burns), panorâmicas, parallax e transições no FFmpeg**.
- **Criação Inteligente de Histórias e Storyboard Validado (JSON):**
  - Integra **Ollama + Gemma 3** (local offline), **Google Gemini API** (chave opcional em memória) e **Google Gemini Web (Google AI Pro)** via prompt copiável + importação direta de JSON (deixando claro que assinatura Google AI Pro e cota de API são serviços distintos).
  - Inclui **estruturador narrativo local offline** para funcionar mesmo antes de instalar o Ollama.
- **Consistência Visual de Personagens:**
  - Extrai todos os personagens, define paleta/roupas/cabelo/acessórios, gera fichas PNG em `references/` e injeta descrições padronizadas em todas as cenas.
- **Narração Natural Local em Português Brasileiro:**
  - **Kokoro TTS v1.0 ONNX** (`pm_alex`, `pf_dora`, `pm_santa`, nativo em `pt-br`) com ajuste de velocidade, ritmo por emoção da cena, prévia de voz e exportação WAV — além de suporte alternativo ao **Piper TTS** local.
- **Legendas Automáticas Sincronizadas (Whisper Local):**
  - Usa **Faster-Whisper** sobre o áudio real da narração (nunca timestamps fictícios), gerando **SRT** e **ASS** em formato vertical com letras grandes brancas, contorno escuro, animação de entrada e destaque palavra por palavra.
- **Trilhas Instrumentais e Efeitos Sonoros 100% Originais:**
  - Gera localmente músicas livres de direitos autorais (`suspense`, `divertida`, `emocionante`) e SFX (`transicao`, `surpresa`, `ambiente`), mixando a música abaixo da narração.
- **Editor Automático FFmpeg (1080×1920, H.264 + AAC):**
  - Padroniza todos os clipes para 9:16 **sem esticar ou deformar os personagens**, sincroniza cenas com os tempos reais da fala, aplica transições, áudio ducking, SFX e queima as legendas ASS.
- **Persistência, Cache, Logs e Recuperação:**
  - Salva automaticamente cada etapa em `projects/project_XXX/`, permite cancelar e retomar projetos interrompidos e nunca regenera cenas já prontas sem autorização.

---

## 📁 Estrutura de Pastas

```text
RobloxAIShortsStudio/
├── main.py                     # Ponto de entrada (UI web local/Colab + CLI --doctor / --generate / --colab)
├── requirements.txt            # Dependências Python
├── .gitignore                  # Mantém o repositório no GitHub leve (ignora .venv, modelos e vídeos pesados)
├── colab/
│   └── Roblox_AI_Shorts_Studio_Colab.ipynb  # Notebook pronto para Google Colab (GPU T4 + Google Drive)
├── scripts/
│   └── colab_setup.sh          # Instalador automático Linux/Colab (Blender 5.3.0, FFmpeg, dependências e cache)
├── engine/
│   ├── rbx/                    # Motor 3D Roblox da skill embutido (avatares articulados, câmeras, cenários)
│   └── assets/                 # Atlas de rostos expressivos e texturas 3D do motor rbx (~3,8 MB)
├── install.bat                 # Instalador automático Windows (com confirmação para modelos)
├── start.bat                   # Inicializador rápido (abre interface no navegador)
├── README.md                   # Esta documentação
├── app/                        # Módulos principais do estúdio
├── config/
│   └── settings.json           # Configurações padrão do estúdio
├── models/
│   ├── README.md               # Tamanhos, licenças e instruções de instalação dos modelos
│   ├── kokoro/                 # Pesos locais Kokoro TTS (~115 MB)
│   ├── piper/                  # Modelos opcionais Piper TTS
│   └── whisper/                # Cache offline Faster-Whisper
├── workflows/
│   └── comfyui/                # Workflows JSON reais para ComfyUI (Wan 2.2 TI2V-5B, I2V Ref, Imagens)
├── projects/
│   └── project_001/            # Projeto de exemplo testado ponta a ponta (com output/final.mp4)
├── assets/
│   ├── music/                  # Músicas instrumentais originais locais (WAV)
│   ├── sounds/                 # Efeitos sonoros originais locais (WAV)
│   └── fonts/                  # Fontes opcionais para legendas
├── logs/                       # Logs detalhados (studio.log)
├── temp/                       # Arquivos temporários e prévias de voz
└── tests/                      # Suíte de testes automatizados (pytest)
```

---

## ☁️ Rodar no Google Colab + Google Drive (GPU Gratuita!)

Se o seu PC for fraco ou você quiser renderizar muito mais rápido na **GPU NVIDIA T4 gratuita do Google Colab** salvando os vídeos direto no seu **Google Drive**:

### Passo 1 — Subir este projeto para o seu GitHub
Na pasta `RobloxAIShortsStudio` do seu PC, rode no terminal:
```bash
git init
git add .
git commit -m "Roblox AI Shorts Studio otimizado para Colab e Drive"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/RobloxAIShortsStudio.git
git push -u origin main
```
> O arquivo `.gitignore` já está configurado para **não** subir `.venv/`, modelos pesados ou vídeos antigos, mantendo o repositório no GitHub super leve e rápido de clonar!

### Passo 2 — Abrir no Google Colab e Conectar seu Google Drive
1. Abra o [Google Colab](https://colab.research.google.com/) → aba **GitHub** → cole o link do seu repositório e abra **`colab/Roblox_AI_Shorts_Studio_Colab.ipynb`**
   *(ou acesse direto `https://colab.research.google.com/github/SEU_USUARIO/RobloxAIShortsStudio/blob/main/colab/Roblox_AI_Shorts_Studio_Colab.ipynb`)*.
2. Ative a GPU gratuita: **Ambiente de execução → Alterar o tipo de ambiente de execução → GPU T4**.
3. Na **Célula 1**, coloque a URL do seu repositório GitHub e clique em **▶ Executar**: ela conecta sua conta do **Google Drive**, clona o projeto e cria a pasta `Meu Drive / RobloxAIShortsStudio/`.
4. Execute a **Célula 2**: verifica se o Blender existe e, se não tiver, **baixa e instala automaticamente o Blender 5.3.0 (Linux x64)** (com aceleração CUDA/OptiX na GPU T4 + cache no Drive), instala **FFmpeg**, **Faster-Whisper GPU**, usa o motor 3D **`engine/rbx`** já incluído no repositório e baixa os modelos leves com **cache permanente no Google Drive** (nas próximas vezes inicia muito mais rápido!).
5. Escolha como gerar:
   - **Célula 3 (Interface Web):** abre a interface completa do estúdio com link público `https://xxxx.gradio.live`.
   - **Célula 4 (1 Clique no Notebook):** preencha a história no formulário e gere o vídeo direto no Colab com player embutido.
6. Seus vídeos prontos (`.mp4` + `.srt` + `.txt` com título, descrição e hashtags) ficam salvos automaticamente no seu Google Drive em:
   **`Meu Drive / RobloxAIShortsStudio / Videos_Prontos/`**!

---

## 🚀 Instalação Rápida no Windows

1. Dê duplo clique em **`install.bat`** (ou execute no terminal dentro da pasta `RobloxAIShortsStudio`).
2. O instalador irá:
   - Verificar Python (usando `uv` com Python 3.12 quando disponível, ou `py -3.12` / `python`);
   - Criar o ambiente virtual `.venv` e instalar todas as bibliotecas;
   - Verificar FFmpeg (o pacote `imageio-ffmpeg` já fornece um binário funcional dentro do `.venv` caso o FFmpeg não esteja no PATH);
   - Verificar Ollama, ComfyUI, GPU, VRAM, RAM e espaço em disco;
   - **Perguntar confirmação `[S/N]`** antes de baixar os modelos leves locais (**Kokoro TTS ~115 MB** + **Whisper base ~145 MB**).
3. Dê duplo clique em **`start.bat`** para abrir a interface em **`http://127.0.0.1:7860`**.

---

## ⚙️ Configurações Opcionais para Potencializar o Modo Gratuito

### 1. Roteiros com IA Local (Ollama + Gemma 3)
1. Instale o [Ollama](https://ollama.com/).
2. Escolha o modelo conforme a sua memória RAM/VRAM:
   - PCs com 8 GB RAM: `ollama pull gemma3:1b` (~815 MB)
   - PCs com 16 GB RAM (recomendado): `ollama pull gemma3:4b` (~3.3 GB)
   - PCs com GPU 12 GB+ VRAM / 32 GB RAM: `ollama pull gemma3:12b` (~8.1 GB)
3. Deixe o Ollama rodando em segundo plano — o estúdio o detectará automaticamente em `http://127.0.0.1:11434`.

### 2. Google Gemini (Assinatura Google AI Pro vs API)
- **Assinatura Google AI Pro (site `gemini.google.com`):** não libera automaticamente cota ilimitada da API Gemini. Para usar sua assinatura oficial sem custo de API, abra a aba **✨ Gemini Web (Google AI Pro)**, copie o prompt gerado, cole no site oficial do Gemini e importe o JSON retornado.
- **Chave da API Gemini (opcional):** pode ser informada apenas na sessão atual da interface ou via variável de ambiente `GEMINI_API_KEY` (nunca gravada em `settings.json`).

### 3. Google Flow + Veo (Interface Oficial)
- No modo **Google Flow** ou **Automático — Flow + Gratuito**, o estúdio cria toda a pasta `prompts/` (`flow_instructions.md` + `scene_XX_flow.txt`) e as fichas de personagens em `references/`.
- Gere os clipes na interface oficial **https://labs.google/fx/tools/flow** na conta autorizada, salve em `projects/project_XXX/videos/scene_01.mp4` (ou envie na aba **Controle do Flow**) e clique em **Continuar / Retomar Projeto**.
- Se os créditos acabarem (mesmo no meio do projeto), clique em **🚨 MEUS CRÉDITOS DO FLOW ACABARAM**: o app muda para o modo local gratuito mantendo todas as cenas já importadas.

### 4. ComfyUI + Wan 2.2 TI2V-5B (Somente GPUs Compatíveis)
- Requisito mínimo de segurança: **GPU NVIDIA CUDA com 12 GB+ de VRAM** e 16–32 GB de RAM.
- Instale o [ComfyUI](https://github.com/comfyanonymous/ComfyUI) e inicie em `http://127.0.0.1:8188`.
- Os workflows prontos estão em `workflows/comfyui/`:
  - `wan22_ti2v_5b.json` (Text-to-Video 9:16)
  - `wan22_i2v_character_ref.json` (Image-to-Video usando referência de personagem)
  - `image_gen_roblox_scene.json` (Geração de imagens local para GPUs de 4–11 GB VRAM)

---

## 💰 Custos, Licenças e Segurança

- **Custo de APIs no Modo 100% Gratuito:** **R$ 0** (sem APIs pagas, sem compra de créditos e sem assinaturas obrigatórias). O processamento usa seu próprio hardware, energia elétrica e armazenamento local.
- **Licenças:**
  - Kokoro-82M (`hexgrad/Kokoro-82M`): **Apache-2.0**; `kokoro-onnx`: **MIT**.
  - Whisper / Faster-Whisper: **MIT**.
  - Wan 2.2 (`Wan-Video/Wan2.2`): **Apache-2.0**.
  - Gemma 3 (Google): **Gemma Terms of Use** (permite uso pessoal/comercial dentro dos termos da Google; verifique a Política de Uso Proibido).
  - FFmpeg: **LGPL / GPL** conforme build.
  - Trilhas e SFX em `assets/`: sintetizados localmente pelo próprio estúdio (100% originais).
- **Segurança:** o aplicativo **não** armazena senhas Google, **não** lê cookies, **não** automatiza login, **não** usa endpoints privados, **não** grava chaves de API em disco e **não** publica vídeos automaticamente.

---

## 🛠️ Solução de Erros Comuns

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| **"Modelos do Kokoro TTS não encontrados"** | Os arquivos locais do Kokoro (~115 MB) ainda não foram baixados | Clique em **Baixar Modelos Locais Leves** na aba *Controle do Computador* ou rode `.venv\Scripts\python.exe main.py --download-small-models` |
| **"Wan 2.2 bloqueado por segurança"** | A placa de vídeo tem menos de 12 GB VRAM CUDA (ex.: GT 710, GTX 1650, GPU integrada) | Comportamento esperado! O estúdio usa automaticamente o **Plano Alternativo** (imagens animadas no FFmpeg) ou clipes importados do Flow / Roblox Studio |
| **Ollama aparece como Inativo** | Serviço Ollama não instalado ou fechado | Abra o aplicativo Ollama ou use o estruturador local offline / aba Gemini Web |
| **Erro ao importar vídeo do Flow / Roblox Studio** | Arquivo corrompido ou formato não suportado | Exporte em `.mp4`, `.mov`, `.mkv` ou `.webm` e tente importar novamente |
| **Legendas sem acento ou fonte diferente** | Fonte `Arial Black` indisponível no sistema | Altere `subtitles.font_name` em `config/settings.json` para `Arial` ou `Segoe UI` |
| **Execução interrompida no meio** | Queda de energia ou clique em Cancelar | Selecione o projeto no topo da interface e clique em **Continuar / Retomar Projeto** (cenas já prontas são preservadas em cache) |

---

## 🧪 Executar Testes Automatizados

```bat
.venv\Scripts\python.exe -m pytest -v
```
