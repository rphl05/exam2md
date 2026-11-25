@echo off
chcp 65001 >nul
title exam2md - Conversao rapida
REM ============================================================
REM  Arraste um ou mais PDFs sobre este arquivo.
REM  Gera prova.md + pasta prova_images\ ao lado de cada PDF.
REM ============================================================
cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo Arraste um ou mais arquivos PDF sobre este arquivo .bat
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Preparando ambiente pela primeira vez...
    python -m venv .venv || (echo ERRO: instale o Python em https://python.org/downloads & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo ERRO ao instalar dependencias & pause & exit /b 1)
)

:proximo
if "%~1"=="" goto fim
if /i not "%~x1"==".pdf" (
    echo [ignorado] %~nx1 nao e PDF
) else (
    echo Convertendo %~nx1 ...
    ".venv\Scripts\python.exe" reconstruir.py "%~f1"
)
shift
goto proximo

:fim
echo.
echo Pronto.
pause
