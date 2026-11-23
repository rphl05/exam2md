@echo off
chcp 65001 >nul
title exam2md - Instalador OCR (Nougat)

REM ============================================
REM exam2md - Instalador OCR Nougat (1 clique)
REM Cria venv isolado para Nougat sem conflitar com pdfplumber
REM ============================================

@echo off
chcp 65001 >nul
cls

echo.
echo  ============================================
echo    exam2md - Instalador OCR (Nougat)
echo  ============================================
echo.
echo  Este script cria um ambiente isolado (.venv-nougat)
echo  para o Nougat OCR sem conflitar com o pdfplumber.
echo.
echo  Requisitos:
echo   - Python 3.10+ instalado
echo   - Conexao com internet (baixa ~1.5 GB)
echo   - Espaco em disco: ~3 GB
echo.
echo  O Nougat usa: transformers==4.44.2, torch, timm==0.5.4
echo  (isolado do pdfplumber que usa transformers 4.46+)
echo.
echo ============================================
echo.

REM Verifica Python
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
python --version

echo.
echo Verificando se ja existe .venv-nougat...
if exist ".venv-nougat" (
    echo.
    echo ATENCAO: .venv-nougat ja existe!
    set /p resposta="Deseja recriar? (s/N): "
    if /i "%resposta%"=="s" (
        echo Removendo ambiente antigo...
        rmdir /s /q .venv-nougat 2>nul
    ) else (
        echo Instalacao cancelada.
        pause
        exit /b 0
    )
)

echo.
echo [1/4] Criando ambiente virtual isolado...
python -m venv .venv-nougat
if errorlevel 1 (
    echo ERRO ao criar ambiente virtual.
    pause
    exit /b 1
)

echo [2/4] Atualizando pip...
.venv-nougat\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

echo [3/4] Instalando PyTorch (CPU)...
echo Isso pode demorar alguns minutos...
.venv-nougat\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo ERRO ao instalar PyTorch.
    pause
    exit /b 1
)

echo [4/4] Instalando Nougat OCR (transformers==4.44.2)...
echo Isso pode demorar alguns minutos...
.venv-nougat\Scripts\pip install "transformers==4.44.2" nougat-ocr
if errorlevel 1 (
    echo ERRO ao instalar Nougat.
    echo.
    echo Tentando versao alternativa...
    .venv-nougat\Scripts\pip install "transformers==4.44.0" nougat-ocr
    if errorlevel 1 (
        echo ERRO: Falha ao instalar Nougat.
        pause
        exit /b 1
    )
)

echo.
echo ============================================
echo  INSTALACAO CONCLUIDA COM SUCESSO!
echo ============================================
echo.
echo Para usar OCR:
echo   python reconstruir.py arquivo.pdf --ocr
echo.
echo Ou pela web (API):
echo   1. Inicie: .venv-nougat\Scripts\python.exe api.py
echo   2. Use opcao "ocr: true" na API
echo.
echo O ambiente fica em: .venv-nougat\
echo (isolado do pdfplumber, sem conflitos)
echo.
pause