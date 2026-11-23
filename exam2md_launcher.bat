@echo off
chcp 65001 >nul
title exam2md Launcher

REM ============================================
REM exam2md - Launcher Python (compilavel para .exe)
REM pyinstaller --onefile --noconsole exam2md_launcher.py
REM ============================================

@echo off
chcp 65001 >nul
cls

echo.
echo  ============================================
echo     exam2md - Conversor de Provas para Markdown
echo  ============================================
echo.

REM Diretório base
set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

echo [1/3] Verificando Python...
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERRO: Python nao encontrado!
    echo.
    echo Instale em: https://python.org/downloads
    echo IMPORTANTE: Marque "Add Python to PATH" na instalacao.
    echo.
    pause
    exit /b 1
)

echo Python encontrado.

REM Cria/Atualiza venv
if not exist ".venv" (
    echo [1/3] Criando ambiente virtual (primeira vez)...
    python -m venv .venv >nul 2>&1
    if errorlevel 1 (
        echo ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo [2/3] Instalando dependencias...
    .venv\Scripts\pip install -r requirements.txt >nul 2>&1
    if errorlevel 1 (
        echo ERRO ao instalar dependencias.
        pause
        exit /b 1
    )
    echo.
) else (
    echo [1/2] Verificando dependencias...
    .venv\Scripts\pip install -r requirements.txt >nul 2>&1
    echo.
)

echo [OK] Servidor iniciando em http://localhost:8000
echo.
echo Abrindo navegador...
echo.
echo ============================================
echo  PRONTO! O navegador vai abrir automaticamente.
echo  Arraste seu PDF na area indicada e clique "Converter".
echo ============================================
echo.
echo Para parar: feche esta janela (Ctrl+C).
echo ============================================
echo.

REM Abre navegador após 2 segundos
start /b cmd /c "timeout /t 2 >nul && start "" http://localhost:8000"

REM Inicia servidor (bloqueia)
.venv\Scripts\python.exe api.py

REM Pausa se houver erro
if errorlevel 1 pause