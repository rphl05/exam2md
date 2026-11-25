@echo off
chcp 65001 >nul
title exam2md
REM Duplo clique: prepara o ambiente (1a vez), sobe o servidor e abre o navegador.
cd /d "%~dp0"
where python >nul 2>nul || (
    echo Python nao encontrado. Instale em https://python.org/downloads
    echo IMPORTANTE: marque "Add Python to PATH" na instalacao.
    pause
    exit /b 1
)
python exam2md_launcher.py
pause
