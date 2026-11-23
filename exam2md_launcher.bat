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

echo Escolha o modo:
echo   1) Servidor Web (conversao via navegador)
echo   2) Instalar/Atualizar Nougat OCR (para PDFs escaneados)
echo   3) Sair
echo.

:CHOICE
set /p choice="Escolha (1/2/3): "
if "%choice%"=="1" goto WEB
if "%choice%"=="2" goto INSTALL_NOU
if "%choice%"=="3" goto EXIT
echo Opcao invalida. Digite 1, 2 ou 3.
goto CHOICE

:INSTALL_NOU
echo.
echo [1/4] Criando ambiente virtual isolado para Nougat...
if not exist ".venv-nougat" (
    python -m venv .venv-nougat >nul 2>&1
    if errorlevel 1 (
        echo ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
) else (
    echo .venv-nougat ja existe. Recriando...
    rmdir /s /q .venv-nougat >nul 2>&1
    python -m venv .venv-nougat >nul 2>&1
    if errorlevel 1 (
        echo ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
)

echo [2/4] Atualizando pip...
.venv-nougat\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

echo [3/4] Instalando PyTorch (CPU)...
echo Isso pode demorar alguns minutos...
.venv-nougat\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu >nul 2>&1
if errorlevel 1 (
    echo ERRO ao instalar PyTorch.
    pause
    exit /b 1
)

echo [4/4] Instalando Nougat OCR (transformers==4.44.2)...
echo Isso pode demorar alguns minutos...
.venv-nougat\Scripts\pip install "transformers==4.44.2" nougat-ocr >nul 2>&1
if errorlevel 1 (
    echo Tentando versao alternativa (transformers==4.44.0)...
    .venv-nougat\Scripts\pip install "transformers==4.44.0" nougat-ocr >nul 2>&1
    if errorlevel 1 (
        echo ERRO ao instalar Nougat OCR.
        pause
        exit /b 1
    )
)

echo.
echo ============================================
echo  NOUGAT OCR INSTALADO COM SUCESSO!
echo ============================================
echo.
echo Para usar OCR:
echo   .venv-nougat\Scripts\python.exe reconstruir.py arquivo.pdf --ocr
echo.
echo Ou pela web (API):
echo   1. .venv-nougat\Scripts\python.exe api.py
echo   2. Use opcao "ocr: true" na API
echo.
echo O ambiente fica em: .venv-nougat\
echo (isolado do pdfplumber, sem conflitos)
echo.
pause
goto EXIT

:WEB
echo.
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

:EXIT
exit /b 0