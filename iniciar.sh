#!/usr/bin/env bash
# exam2md (macOS e Linux): abre a interface no navegador.
#   ./iniciar.sh                      interface no navegador
#   ./iniciar.sh --converter a.pdf    converte PDFs direto
# No macOS, "Iniciar.command" faz o mesmo com duplo clique no Finder.
cd "$(dirname "$0")" || exit 1

achar_python() {
    for py in .venv/bin/python python3 python3.13 python3.12 python3.11 python3.10 python; do
        if command -v "$py" >/dev/null 2>&1 &&
           "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    return 1
}

if ! PY=$(achar_python); then
    echo
    echo "  O exam2md precisa do Python 3.10 ou mais novo, que não foi encontrado."
    if [ "$(uname)" = "Darwin" ]; then
        echo "  Instale em https://www.python.org/downloads/ (ou: brew install python)"
        open "https://www.python.org/downloads/" 2>/dev/null
    else
        echo "  Ubuntu/Debian:  sudo apt install python3 python3-venv"
        echo "  Fedora:         sudo dnf install python3"
    fi
    echo
    read -r -p "Pressione Enter para fechar..." _ </dev/tty 2>/dev/null
    exit 1
fi

"$PY" exam2md_launcher.py "$@"
status=$?
if [ $status -ne 0 ] || [ "$1" = "--converter" ]; then
    read -r -p "Pressione Enter para fechar..." _ </dev/tty 2>/dev/null
fi
exit $status
