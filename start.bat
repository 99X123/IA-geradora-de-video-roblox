@echo off
chcp 65001 >nul
title ROBLOX AI SHORTS STUDIO
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual .venv nao encontrado. Execute install.bat primeiro!
    pause
    exit /b 1
)

echo Iniciando ROBLOX AI SHORTS STUDIO em http://127.0.0.1:7860 ...
echo Feche esta janela apenas quando terminar de usar o aplicativo.
echo.
.venv\Scripts\python.exe main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] O aplicativo encerrou com erro. Verifique logs\studio.log
    pause
)
