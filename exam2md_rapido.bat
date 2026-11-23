@echo off
chcp 65001 >nul
title exam2md - Conversao Rapida

REM ============================================
REM exam2md - Conversao Rapida (Drag & Drop)
REM Arraste um arquivo PDF sobre este arquivo .bat
REM ============================================

@echo off
chcp 65001 >nul

REM Verifica se foi passado um arquivo
if "%~1"=="" (
    echo.
    echo Arraste um arquivo PDF sobre este arquivo .bat
    echo.
    echo Exemplo: arraste "prova.pdf" sobre exam2md_rapido.bat
    echo.
    pause
    exit /b 1
endif

REM Verifica se é PDF
set "ext=%~x1"
if /i not "%ext%"==".pdf" (
    echo.
    echo ERRO: O arquivo deve ser PDF (.pdf)
    echo Arquivo recebido: %~nx1
    pause
    exit /b 1
endif

if not exist "%~f1" (
    echo.
    echo ERRO: Arquivo nao encontrado:
    echo %~f1
    pause
    exit /b 1
)

REM Verifica Python
where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: Python nao instalado. Instale em python.org
    pause
    exit /b 1
)

echo.
echo ============================================
echo  exam2md - Convertendo: %~nx1
echo ============================================
echo.

REM Cria venv se necessário
if not exist ".venv" (
    echo [1/3] Preparando ambiente (primeira vez)...
    python -m venv .venv >nul 2>&1
    .venv\Scripts\pip install -r requirements.txt >nul 2>&1
    echo.
) else (
    echo [1/2] Verificando dependencias...
    .venv\Scripts\pip install -r requirements.txt >nul 2>&1
    echo.
)

echo [2/2] Convertendo %~nx1 ...
.venv\Scripts\python.exe reconstruir.py "%~f1" --save-images

if errorlevel 1 (
    echo.
    echo ERRO na conversao. Verifique se o PDF e valido.
    pause
    exit /b 1
)

echo.
echo ============================================
echo SUCESSO!
echo ============================================
echo.
echo Arquivo gerado: %~dpn1.md
echo Imagens em:     %~dpn1_images\
echo.
echo O arquivo Markdown esta na mesma pasta do PDF original.
echo.
pause