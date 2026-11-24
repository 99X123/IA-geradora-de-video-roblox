@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Instalador - ROBLOX AI SHORTS STUDIO
cd /d "%~dp0"

echo ========================================================================
echo   ROBLOX AI SHORTS STUDIO - INSTALADOR AUTOMATICO (WINDOWS)
echo ========================================================================
echo.

echo [1/9] Criando estrutura de pastas do projeto...
for %%D in (config models models\kokoro models\piper models\whisper workflows workflows\comfyui projects assets assets\music assets\sounds assets\fonts logs temp) do (
    if not exist "%%D" mkdir "%%D"
)
echo   OK - Pastas verificadas.
echo.

echo [2/9] Verificando Python e criando ambiente virtual (.venv)...
where uv >nul 2>&1
if %errorlevel%==0 (
    echo   uv detectado! Criando .venv com Python 3.12 para maxima compatibilidade...
    if not exist ".venv\Scripts\python.exe" (
        uv venv .venv --python 3.12
    )
    set "USE_UV=1"
) else (
    set "USE_UV=0"
    set "PY_CMD="
    py -3.12 --version >nul 2>&1 && set "PY_CMD=py -3.12"
    if not defined PY_CMD (
        py -3.11 --version >nul 2>&1 && set "PY_CMD=py -3.11"
    )
    if not defined PY_CMD (
        python --version >nul 2>&1 && set "PY_CMD=python"
    )
    if not defined PY_CMD (
        echo   [ERRO] Python 3.11 ou 3.12 nao encontrado!
        echo   Instale em: https://www.python.org/downloads/ (marque "Add Python to PATH")
        pause
        exit /b 1
    )
    echo   Usando: !PY_CMD!
    if not exist ".venv\Scripts\python.exe" (
        !PY_CMD! -m venv .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo   [ERRO] Falha ao criar o ambiente virtual .venv.
    pause
    exit /b 1
)
echo   OK - Ambiente virtual pronto.
echo.

echo [3/9] Instalando dependencias Python (requirements.txt)...
if "!USE_UV!"=="1" (
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
) else (
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if %errorlevel% neq 0 (
    echo   [ERRO] Falha ao instalar dependencias Python. Verifique sua conexao com a internet.
    pause
    exit /b 1
)
echo   OK - Dependencias instaladas.
echo.

echo [4/9] Verificando FFmpeg...
where ffmpeg >nul 2>&1
if %errorlevel%==0 (
    echo   OK - FFmpeg encontrado no PATH do Windows.
) else (
    echo   FFmpeg nao esta no PATH global, mas o pacote imageio-ffmpeg ja incluiu um binario funcional no .venv!
)
echo.

echo [5/9] Verificando Ollama (IA local de roteiros)...
where ollama >nul 2>&1
if %errorlevel%==0 (
    echo   OK - Ollama encontrado. Modelos instalados:
    ollama list 2>nul
) else (
    echo   [OPCIONAL] Ollama nao encontrado.
    echo   Para gerar roteiros com Gemma 3 localmente (offline): https://ollama.com/
)
echo.

echo [6/9] Verificando ComfyUI (geracao local em GPU)...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8188/system_stats'; Write-Host '  OK - ComfyUI ativo em http://127.0.0.1:8188' } catch { Write-Host '  [OPCIONAL] ComfyUI nao esta em execucao em http://127.0.0.1:8188 (https://github.com/comfyanonymous/ComfyUI)' }"
echo.

echo [7/9] Detectando GPU, VRAM, RAM, Disco e configuracao inicial...
.venv\Scripts\python.exe main.py --doctor
echo.

echo [8/9] Download opcional de modelos leves locais (COM CONFIRMACAO):
echo   - Kokoro TTS v1.0 INT8 (voz natural PT-BR): ~115 MB (Licenca Apache-2.0)
echo   - Faster-Whisper base (legendas reais PT-BR): ~145 MB (Licenca MIT)
echo   Total aproximado: ~260 MB.
set /p DL_SMALL="Deseja baixar Kokoro TTS + Whisper agora? [S/N]: "
if /i "!DL_SMALL!"=="S" (
    .venv\Scripts\python.exe main.py --download-small-models
) else (
    echo   Download pulado. Voce pode baixar depois pela interface na aba "Controle do Computador".
)
echo.

echo [9/9] Orientacoes para modelos maiores (NAO baixados automaticamente):
echo   - Ollama Gemma 3 1B (~815 MB)  : ollama pull gemma3:1b   (PCs 8 GB RAM)
echo   - Ollama Gemma 3 4B (~3.3 GB)  : ollama pull gemma3:4b   (PCs 16 GB RAM - recomendado)
echo   - Ollama Gemma 3 12B (~8.1 GB) : ollama pull gemma3:12b  (GPU 12+ GB VRAM / 32 GB RAM)
echo   - ComfyUI + Wan 2.2 TI2V-5B (~18 GB total): somente para GPUs NVIDIA CUDA com 12 GB+ VRAM.
echo     Consulte models\README.md para links oficiais e licencas.
echo.
echo ========================================================================
echo   INSTALACAO CONCLUIDA! Execute start.bat para abrir o aplicativo.
echo ========================================================================
pause
