@echo off
chcp 65001 >nul
title exam2md - Conversor de Provas para Markdown

echo.
echo ============================================
echo   exam2md - Conversor de Provas para Markdown
echo ============================================
echo.

REM Verifica se o Python está instalado
where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    echo.
    echo Por favor, instale o Python em: https://python.org/downloads
    echo Marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

REM Cria ambiente virtual se nao existir
if not exist ".venv" (
    echo [1/3] Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo [2/3] Instalando dependencias...
    .venv\Scripts\pip install -r requirements.txt >nul 2>nul
    if errorlevel 1 (
        echo ERRO ao instalar dependencias.
        pause
        exit /b 1
    )
    echo.
) else (
    echo [1/2] Ambiente virtual ja existe.
    echo [2/2] Verificando dependencias...
    .venv\Scripts\pip install -r requirements.txt >nul 2>nul
    echo.
)

echo ============================================
echo ESCOLHA UMA OPCAO:
echo ============================================
echo.
echo  1) Converter um arquivo PDF (modo simples)
echo 2) Converter PDF com imagens
echo 3) Converter PDF escaneado (OCR - lento)
echo 4) Abrir interface web (arrastar e soltar)
echo 5) Sair
echo.

set /p choice="Digite o numero da opcao (1-5): "

if "%choice%"=="1" goto :convert_simple
if "%choice%"=="2" goto :convert_images
if "%choice%"=="3" goto :convert_ocr
if "%choice%"=="4" goto :web
if "%choice%"=="5" goto :exit

echo Opcao invalida!
pause
goto :exit

:convert_simple
echo.
echo Arraste o arquivo PDF para esta janela e pressione Enter:
set /p pdf_file="Caminho do PDF: "
REM Remove aspas se houver
set pdf_file=%pdf_file:"=%
if not exist "%pdf_file%" (
    echo Arquivo nao encontrado: %pdf_file%
    pause
    goto :exit
)
echo.
echo Convertendo...
.venv\Scripts\python.exe reconstruir.py "%pdf_file%"
echo.
echo Pronto! O arquivo .md foi criado na mesma pasta do PDF.
pause
goto :exit

:convert_images
echo.
echo Arraste o arquivo PDF para esta janela e pressione Enter:
set /p pdf_file="Caminho do PDF: "
set pdf_file=%pdf_file:"=%
if not exist "%pdf_file%" (
    echo Arquivo nao encontrado: %pdf_file%
    pause
    goto :exit
)
echo.
echo Convertendo com extracao de imagens...
.venv\Scripts\python.exe reconstruir.py "%pdf_file%" --save-images
echo.
echo Pronto! Arquivo .md e pasta _images/ criados.
pause
goto :exit

:convert_ocr
echo.
echo ATENCAO: OCR (Nougat) requer instalacao separada e e lento.
echo Recomendado apenas para PDFs escaneados (imagens).
echo.
echo Arraste o arquivo PDF escaneado para esta janela:
set /p pdf_file="Caminho do PDF: "
set pdf_file=%pdf_file:"=%
if not exist "%pdf_file%" (
    echo Arquivo nao encontrado: %pdf_file%
    pause
    goto :exit
)
echo.
echo Iniciando OCR (pode demorar varios minutos)...
.venv\Scripts\python.exe reconstruir.py "%pdf_file%" --ocr
echo.
echo Pronto!
pause
goto :exit

:web
echo.
echo Iniciando servidor web...
echo.
echo Aguardando servidor ficar pronto...
start "exam2md API" /b .venv\Scripts\python.exe api.py
timeout /t 3 >nul
echo Abrindo navegador em http://localhost:8000/web/
start "" http://localhost:8000/web/
echo.
echo Servidor rodando. Feche esta janela para parar.
echo.
pause
goto :exit

:exit
echo.
echo Obrigado por usar o exam2md!
timeout /t 3 >nul