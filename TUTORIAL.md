# Tutorial Completo — AutoShorts AI (GitHub + Google Colab + Google Drive)

Este guia mostra passo a passo como:
1. Subir o projeto limpo para o seu GitHub.
2. Abrir o notebook com **1 clique** no Google Colab.
3. Gerar vídeos curtos 3D verticais (1080×1920, 30 fps) informando **apenas um tema** e salvar tudo automaticamente no Google Drive.

---

## Parte 1 — Subir o projeto para o GitHub

O `.gitignore` já está configurado para **não** subir `node_modules/`, vídeos `.mp4`/`.wav` pesados, backups nem arquivos de senha/credenciais. Assim o repositório fica leve e o `git clone` no Colab leva poucos segundos.

Abra o terminal (PowerShell) dentro da pasta do projeto (`c:\Users\Carlos\Pictures\IA-geradora-de-video-roblox`) e execute:

```powershell
# 1. Conferir o que vai ser enviado (verifique que não há .env nem chaves)
git status

# 2. Adicionar todos os arquivos novos e removidos
git add -A

# 3. Criar o commit
git commit -m "feat: AutoShorts AI completo (Three.js 3D + Colab + Drive + QA + OpenCode)"

# 4. Enviar para o GitHub (branch main)
git push -u origin main
```

> Se o GitHub pedir login na primeira vez, autentique pelo navegador ou com um Personal Access Token (PAT).
> Se o repositório remoto tiver commits antigos que você queira substituir completamente, use `git push -u origin main --force-with-lease` (apenas se tiver certeza de que deseja sobrescrever a versão antiga).

---

## Parte 2 — Abrir no Google Colab com 1 clique

Assim que o `git push` terminar, basta acessar o link abaixo (ou clicar no botão **Open in Colab** no topo do `README.md` do seu GitHub):

```text
https://colab.research.google.com/github/99X123/IA-geradora-de-video-roblox/blob/main/AutoShorts_Colab.ipynb
```

---

## Parte 3 — Preparar o Google Colab (só na primeira vez da sessão)

1. **Ativar GPU (recomendado):**
   - No menu superior do Colab, clique em **Ambiente de execução → Alterar tipo de ambiente de execução → GPU T4 → Salvar**.
2. **(Opcional) Configurar chaves de IA em segurança (Colab Secrets):**
   - O sistema **já funciona sem nenhuma API key** (usa roteiro estruturado PT-BR + vozes neurais PT-BR gratuitas do `edge-tts`).
   - Se quiser roteiros via **Gemini** ou **OpenAI** e revisão visual por IA, clique no ícone de **chave (Secrets)** na barra lateral esquerda do Colab e adicione:
     - `GEMINI_API_KEY` (opcional — roteiros Gemini + inspeção visual no QA)
     - `OPENAI_API_KEY` (opcional — alternativa para roteiro/TTS/Vision)
     - `GOOGLE_API_KEY` (opcional — Google Cloud Text-to-Speech)
     - `OPENCODE_MODEL` (opcional — modelo listado em `opencode models`)
   - Ative a chavinha **"Acesso ao notebook"** para os segredos que cadastrar. **Nunca** escreva chaves dentro das células ou no Google Drive.

---

## Parte 4 — Produzir seu vídeo automaticamente

Execute as células do `AutoShorts_Colab.ipynb` em ordem:

1. **Célula 1 — Verificar Ambiente:** mostra CPU, RAM, FFmpeg, Node.js e se há GPU CUDA alocada.
2. **Célula 2 — Baixar Projeto e Instalar Dependências:** faz `git clone` automático do seu GitHub e instala Python + FFmpeg + Three.js + Playwright Chromium.
3. **Célula 3 — Teste Real de GPU/WebGL:** confirma se o Chromium está usando GPU real ou fallback SwiftShader (avisa com transparência).
4. **Célula 4 — Montar Google Drive:** autoriza o acesso oficial ao seu Google Drive e cria automaticamente toda a estrutura:
   ```text
   Meu Drive/AutoShorts AI/
   ├── Videos/       <- Seu MP4 final pronto fica aqui!
   ├── Projects/     <- Pasta completa de cada vídeo
   ├── Audio/
   ├── Scripts/
   ├── Storyboards/
   ├── Subtitles/    <- Legendas .srt e sync_data.json
   ├── Logs/
   ├── Reports/      <- Relatório de qualidade e folha de contato QA
   └── Backups/
   ```
5. **Célula 5 — Carregar Credenciais:** lê os Colab Secrets somente em memória.
6. **Célula 6 — Configuração Central:** preencha apenas o campo **`TEMA`** (por exemplo: `"um pombo virou síndico do meu prédio"`) e ajuste se quiser:
   - `DURACAO_SEGUNDOS`: `60` (ou `12`–`24` para testes rápidos)
   - `QUALIDADE`: `production` (1080×1920 @ 30fps) ou `draft` (540×960 @ 24fps, bem mais rápido para testar ideias)
   - `PAUSAR_APROVACAO_STORYBOARD`: deixe `False` para modo 100% automático, ou marque `True` se quiser ver a folha de contato das cenas antes de renderizar o vídeo completo.
7. **Célula 7 — Executar Fábrica Completa:** gera roteiro, vozes PT-BR, alinhamento palavra por palavra, legendas, storyboard 3D, SFX + música original, renderiza o MP4 em partes no disco rápido do Colab, roda o controle de qualidade e salva tudo no Google Drive.

---

## Parte 5 — Dicas Úteis do Dia a Dia

- **Retomar se o Colab desconectar no meio do render:** copie o `Project ID` exibido na Célula 7, cole em `PROJECT_ID_RETOMAR` na Célula 6 e rode a Célula 7 novamente. As partes já concluídas são puladas automaticamente.
- **Re-renderizar apenas 1 ou 2 cenas/partes:** na **Célula 8**, informe os números das partes (ex.: `2,5`) para re-renderizar somente elas sem refazer o vídeo inteiro.
- **Rodar testes e revisão OpenCode:** execute a **Célula 9** para rodar `pytest -v` e, se quiser, ativar a revisão independente via OpenCode CLI.

---

## Parte 6 — Uso Local no Windows (opcional)

Se quiser rodar direto no seu PC em vez do Colab:

```powershell
# Clonar do GitHub em qualquer pasta
git clone https://github.com/99X123/IA-geradora-de-video-roblox.git AutoShortsAI
cd AutoShortsAI

# Instalar dependências
pip install -r requirements-colab.txt
npm install
npx playwright install chromium

# Produzir um vídeo a partir de um tema
python scripts/run_production.py --theme "meu robô decidiu cozinhar feijoada" --duration 60
```

O vídeo final e todos os arquivos ficam salvos dentro de `output/<project_id>/`.
