#!/usr/bin/env bash
# Instalador do exam2md para macOS e Linux.
# Uso (Terminal):  curl -fsSL https://raw.githubusercontent.com/rphl05/exam2md/main/instalar.sh | bash
# Rodar de novo atualiza para a versão mais recente (mantém o que já foi instalado).
#
# O que faz: baixa o exam2md para ~/exam2md, prepara as dependências e cria um
# atalho (macOS: na Mesa; Linux: no menu de aplicativos e na área de trabalho).
set -euo pipefail

REPO="rphl05/exam2md"
# EXAM2MD_DESTINO: instalar em outra pasta
DESTINO="${EXAM2MD_DESTINO:-$HOME/exam2md}"
# EXAM2MD_TAR permite instalar de outro endereço ou de um .tar.gz local (testes)
TAR="${EXAM2MD_TAR:-https://github.com/$REPO/archive/refs/heads/main.tar.gz}"

passo() { printf '\n\033[36m>> %s\033[0m\n' "$1"; }
falha() { printf '\n\033[31m[ERRO] %s\033[0m\n\n' "$1"; exit 1; }

echo "=============================================="
echo "  exam2md - instalação"
echo "=============================================="

# 1. Python 3.10+
passo "Procurando o Python 3.10+..."
PY=""
for c in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        PY="$c"; break
    fi
done
if [ -z "$PY" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        falha "Instale o Python em https://www.python.org/downloads/ (ou: brew install python) e rode este comando de novo."
    else
        falha "Instale o Python 3.10+ (Ubuntu/Debian: sudo apt install python3 python3-venv | Fedora: sudo dnf install python3) e rode este comando de novo."
    fi
fi
if ! "$PY" -c 'import venv, ensurepip' 2>/dev/null; then
    falha "Falta o módulo venv do Python. Ubuntu/Debian: sudo apt install python3-venv"
fi
echo "   OK: $PY ($("$PY" --version 2>&1))"

# 2. Arquivos (preserva o .venv de uma instalação anterior)
passo "Baixando o exam2md para $DESTINO ..."
mkdir -p "$DESTINO"
if [ -f "$TAR" ]; then
    tar -xzf "$TAR" -C "$DESTINO" --strip-components=1
else
    curl -fsSL "$TAR" | tar -xz -C "$DESTINO" --strip-components=1
fi
chmod +x "$DESTINO/iniciar.sh" "$DESTINO/Iniciar.command" 2>/dev/null || true

# 3. Dependências
"$PY" "$DESTINO/exam2md_launcher.py" --preparar || falha "Não foi possível preparar o exam2md (veja a mensagem acima)."

# 4. Atalhos
passo "Criando atalho..."
if [ "$(uname)" = "Darwin" ]; then
    ATALHO="$HOME/Desktop/exam2md.command"
    printf '#!/usr/bin/env bash\nexec bash "%s/iniciar.sh" "$@"\n' "$DESTINO" > "$ATALHO"
    chmod +x "$ATALHO"
    ONDE="na Mesa: exam2md.command (duplo clique)"
else
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APPS"
    cat > "$APPS/exam2md.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=exam2md
Comment=Converter provas em PDF para Markdown
Exec=bash "$DESTINO/iniciar.sh"
Icon=accessories-text-editor
Terminal=true
Categories=Office;Education;
EOF
    chmod +x "$APPS/exam2md.desktop"
    ONDE="no menu de aplicativos: exam2md"
    MESA="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
    if [ -d "$MESA" ]; then
        cp "$APPS/exam2md.desktop" "$MESA/"
        chmod +x "$MESA/exam2md.desktop"
        gio set "$MESA/exam2md.desktop" metadata::trusted true 2>/dev/null || true
        ONDE="$ONDE (e na área de trabalho)"
    fi
fi

printf '\n\033[32m==============================================\n'
printf '  Pronto! O exam2md foi instalado.\n'
printf '==============================================\033[0m\n'
echo "  Atalho $ONDE"
echo "  Ou no Terminal:  ~/exam2md/iniciar.sh"
echo "  Arquivos em: $DESTINO"
echo

if [ -z "${EXAM2MD_NAO_ABRIR:-}" ]; then
    exec bash "$DESTINO/iniciar.sh" </dev/tty
fi
