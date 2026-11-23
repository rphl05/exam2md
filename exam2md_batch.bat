@echo off
chcp 65001 >nul
title exam2md Batch - Processamento em Lote

REM ============================================
REM exam2md Batch - Processamento em lote de múltiplos PDFs
REM ============================================

@echo off
chcp 65001 >nul
cls

echo.
echo  ============================================
echo     exam2md Batch - Processamento em Lote
echo  ============================================
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

echo.
echo  ============================================
echo  MODO LOTE - Arraste VÁRIOS PDFs aqui ou digite caminhos
echo  ============================================
echo.
echo Exemplos:
echo   Arraste varios PDFs sobre este arquivo
echo   Ou digite: prova1.pdf prova2.pdf prova3.pdf
echo   Ou use coringas: *.pdf  provas\*.pdf
echo.
echo Opcoes disponiveis (adicione apos os arquivos):
echo   --save-images        Extrai imagens
echo   --ocr                Usa OCR (PDFs escaneados)
echo   -o pasta_saida       Pasta de saida para .md
echo   --images-dir pasta   Pasta customizada para imagens
echo   --pages 1,3-5        Apenas paginas especificas
echo   --relatorio rel.json Salva relatorio JSON
echo.
echo Digite os arquivos/opcoes (ou ENTER para usar arquivos arrastados):
set /p user_input="> "

REM Se não digitou nada, usa argumentos passados
if "%user_input%"=="" (
    set "args=%*"
) else (
    set "args=%user_input%"
)

if "%args%"=="" (
    echo.
    echo Nenhum arquivo especificado!
    echo Arraste os PDFs sobre este arquivo .bat
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Processando em lote...
echo.

.venv\Scripts\python.exe exam2md_batch.py %args%

echo.
echo ============================================
echo  PROCESSAMENTO CONCLUIDO
echo ============================================
pause