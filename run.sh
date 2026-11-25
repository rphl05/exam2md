#!/usr/bin/env bash
# exam2md - Linux/macOS: prepara o ambiente (1a vez), sobe o servidor e abre o navegador.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 não encontrado. Instale pelo gerenciador de pacotes ou em https://python.org/downloads"
    exit 1
fi
exec python3 exam2md_launcher.py "$@"
