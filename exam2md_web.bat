@echo off
chcp 65001 >nul
title exam2md - Conversor Web

REM ============================================
REM exam2md - Inicia servidor web e abre navegador
REM Dois cliques neste arquivo = abre navegador pronto para usar
REM ============================================

@echo off
chcp 65001 >nul
cls

echo.
echo  ============================================
echo     exam2md - Conversor de Provas para Markdown
echo  ============================================
echo.
echo  Iniciando servidor local...
echo.

REM Verifica Python
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERRO: Python nao encontrado!
    echo.
    echo Por favor, instale o Python em: https://python.org/downloads
    echo IMPORTANTE: Marque "Add Python to PATH" na instalacao.
    echo.
    pause
    exit /b 1
)

REM Cria/Atualiza ambiente virtual
if not exist ".venv" (
    echo [1/3] Preparando ambiente (primeira vez)...
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
echo Para parar: feche esta janela.
echo ============================================
echo.

REM Inicia servidor em background, aguarda ficar pronto, depois abre navegador
start "exam2md API" cmd /c ".venv\Scripts\python.exe api.py"
echo Aguardando servidor iniciar...
timeout /t 3 >nul
start "" "http://localhost:8000/web/"
echo.
echo Servidor rodando. Feche esta janela para parar.
echo.
pause