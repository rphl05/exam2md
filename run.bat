@echo off
REM exam2md - Start script for Windows
echo Iniciando exam2md...

REM Verifica se venv existe
if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

echo.
echo [1/2] Iniciando API (FastAPI) na porta 8000...
start "exam2md API" cmd /k ".venv\Scripts\activate && python api.py"

REM Aguarda API subir
timeout /t 3 >nul

echo.
echo [2/2] Abrindo interface no navegador...
start "" http://localhost:8000

echo.
echo ================================
echo exam2md rodando!
echo API:     http://localhost:8000
echo Web:     http://localhost:8000 (ou abra web/index.html)
echo Parar:   Feche as janelas do terminal
echo ================================
pause