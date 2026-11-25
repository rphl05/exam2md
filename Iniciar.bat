@echo off
chcp 65001 >nul
title exam2md
REM Duplo clique: abre o exam2md no navegador.
REM Com PDFs como argumento (ver "Arraste PDFs aqui.bat"): converte direto.
cd /d "%~dp0"

call :achar_python
if not defined PY (
    echo.
    echo  O exam2md precisa do Python 3.10 ou mais novo, que nao foi encontrado.
    echo.
    where winget >nul 2>nul && (
        choice /c SN /m " Instalar o Python agora automaticamente"
        if not errorlevel 2 (
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            call :achar_python
        )
    )
)
if not defined PY (
    echo.
    echo  Instale o Python em https://www.python.org/downloads/
    echo  IMPORTANTE: na instalacao, marque "Add python.exe to PATH".
    echo  Depois, abra este arquivo de novo.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)

%PY% exam2md_launcher.py %*
if errorlevel 1 (pause & exit /b 1)
if /i "%~1"=="--converter" pause
exit /b 0

:achar_python
REM Ordem: ambiente ja preparado > launcher "py" > python no PATH > instalacao padrao.
REM O teste de versao tambem descarta o atalho falso "python" da Microsoft Store.
set "PY="
set "TESTE=import sys; sys.exit(sys.version_info < (3, 10))"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "%TESTE%" >nul 2>nul && (set PY=".venv\Scripts\python.exe" & exit /b 0)
)
py -3 -c "%TESTE%" >nul 2>nul && (set "PY=py -3" & exit /b 0)
python -c "%TESTE%" >nul 2>nul && (set "PY=python" & exit /b 0)
for %%V in (313 312 311 310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        exit /b 0
    )
)
exit /b 0
