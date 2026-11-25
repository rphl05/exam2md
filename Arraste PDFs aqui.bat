@echo off
REM Arraste um ou mais PDFs sobre este arquivo (ou sobre o atalho da area de trabalho).
REM Gera prova.md + pasta prova_images\ ao lado de cada PDF.
call "%~dp0Iniciar.bat" --converter %*
