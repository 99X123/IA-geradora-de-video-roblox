# Tutorial Completo — AutoShorts AI (100% no Google Colab, Sem API Key!)

Este guia mostra como subir o projeto para o seu GitHub e rodar **tudo direto dentro da máquina do Google Colab** usando apenas **login por link nas suas contas** — sem precisar criar nem colar nenhuma API key.

---

## Parte 1 — Subir o projeto para o GitHub (uma única vez)

Abra o PowerShell na pasta `c:\Users\Carlos\Pictures\IA-geradora-de-video-roblox` e execute:

```powershell
git status
git add -A
git commit -m "feat: AutoShorts AI 100% Colab + OpenCode CLI com login por link"
git push -u origin main
```

> O `.gitignore` já exclui automaticamente `node_modules/`, backups, logs, credenciais e os arquivos `.mp4`/`.wav` pesados, deixando o clone no Colab super rápido.

---

## Parte 2 — Abrir no Google Colab com 1 clique

Clique no link abaixo (ou no botão **Open in Colab** no topo do `README.md` no seu GitHub):

```text
https://colab.research.google.com/github/99X123/IA-geradora-de-video-roblox/blob/main/AutoShorts_Colab.ipynb
```

Antes de rodar:
- Vá em **Ambiente de execução → Alterar tipo de ambiente de execução → GPU T4 → Salvar**.

---

## Parte 3 — Conectar suas contas por link (Zero API Key!)

Execute as células em ordem:

1. **Célula 1 — Verificar Ambiente:** verifica CPU, RAM e GPU do Colab.
2. **Célula 2 — Clonar e Instalar Tudo:** baixa seu repositório do GitHub e instala **FFmpeg, Python, Node.js, Three.js, Playwright Chromium e OpenCode CLI** direto dentro da máquina do Colab.
3. **Célula 3 — Teste Real de GPU/WebGL:** confirma se o Chromium está usando GPU real ou fallback SwiftShader.
4. **Célula 4 — Login no Google Drive (por link/popup):**
   - Clique em **Conectar ao Google Drive**, faça login na sua conta Google e autorize.
   - O notebook cria automaticamente a pasta `Meu Drive/AutoShorts AI/` com todas as subpastas (`Videos/`, `Projects/`, `Audio/`, `Scripts/`, `Storyboards/`, `Subtitles/`, `Logs/`, `Reports/`, `Backups/`).
5. **Célula 5 — Login no OpenCode por link (sem API key):**
   - Marque `FAZER_LOGIN_OPENCODE = True`, escolha o provedor (ex.: `google`, `opencode`, `github-copilot`, `openai`, `anthropic`) e rode a célula.
   - O OpenCode exibe um **link oficial de login** direto na saída da célula: clique no link, faça login na sua conta e pronto!
   - A própria célula lista todos os modelos disponíveis na sua conta (`opencode models`) para você copiar o nome de um modelo.
   - *(Opcional: se não quiser logar em conta nenhuma agora, o sistema já funciona com o gerador de histórias local PT-BR + vozes neurais PT-BR do `edge-tts`!)*

---

## Parte 4 — Colocar o SEU PRÓPRIO ROTEIRO (ou gerar pelo tema)

1. **Célula 6A — Escreva o SEU PRÓPRIO ROTEIRO certinho:**
   - Deixe `USAR_MEU_ROTEIRO = True`.
   - Escolha o `TITULO_DO_VIDEO` e o `PERSONAGEM_COSTAR` (`bot`, `pigeon`, `phantom`, `rock`, `human`, `mech` ou `auto`).
   - Cole suas falas dentro de `MEU_ROTEIRO`, uma por linha:
     ```text
     [sala] N: Eu só queria dormir cedo hoje, até meu robô aparecer com uma panela gigante.
     [cozinha] C: Calma Leo! Isso aqui vai virar o melhor brigadeiro da galáxia.
     [praca] S: Ei, por que tem fumaça brilhante saindo da sua janela?
     [sala_noite] N: Alguém sabe como mudar de planeta antes de segunda-feira?
     ```
   - `N:` = Narrador (voz 1), `C:` = Co-protagonista (voz 2), `S:` = 3º personagem opcional (voz 3).
   - Os cenários entre colchetes (`[sala]`, `[sala_noite]`, `[cozinha]`, `[corredor]`, `[praca]`, `[praca_dourada]`, `[praca_caos]`, `[estudio]`) são opcionais — se não colocar, o sistema escolhe automaticamente pelas palavras da frase!
   - *(Se quiser que a IA invente a história sozinha, basta desmarcar `USAR_MEU_ROTEIRO`.)*
2. **Célula 6B — Configuração de Vídeo, Voz e Qualidade:**
   - `PROVEDOR_TTS` já vem em **`edge_tts`** (vozes neurais brasileiras naturais sem API key e sem login).
   - Escolha `QUALIDADE`: `draft` (rápido para testar) ou `production` (`1080×1920 @ 30fps`).
3. **Célula 7 — Produzir Vídeo Completo:**
   - Gera vozes PT-BR para o seu roteiro exato, alinhamento palavra por palavra, legendas, storyboard 3D, SFX + música original, renderiza o MP4 em partes no disco rápido do Colab, passa no controle de qualidade e salva o vídeo pronto automaticamente em:
     `Meu Drive/AutoShorts AI/Videos/`

---

## Parte 5 — Recursos Extras no Notebook

- **Retomar renderização interrompida:** copie o `Project ID` mostrado na Célula 7, cole em `PROJECT_ID_RETOMAR` na Célula 6 e rode a Célula 7 de novo (partes já prontas são reaproveitadas).
- **Re-renderizar só uma parte específica:** use a **Célula 8** informando o número da parte (ex.: `2,5`).
- **Rodar testes e revisão de código pelo OpenCode direto no Colab:** use a **Célula 9** (`EXECUTAR_REVISAO_OPENCODE = True`).
