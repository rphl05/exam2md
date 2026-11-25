#!/usr/bin/env python3
"""Launcher do exam2md: prepara o ambiente na 1ª vez e abre a interface.

    python exam2md_launcher.py                     # interface no navegador
    python exam2md_launcher.py --converter a.pdf   # converte PDFs direto (arrastar e soltar)
    python exam2md_launcher.py --preparar          # só prepara o ambiente (usado pelo instalador)
    python exam2md_launcher.py --instalar-formulas # fórmulas em imagem -> LaTeX (pix2tex)
    python exam2md_launcher.py --instalar-ocr      # PDFs escaneados (Nougat)

Usa só a biblioteca padrão: roda com qualquer Python 3.10+, antes do .venv existir.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
VENV = BASE / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")
REQUISITOS = BASE / "requirements.txt"
MARCADOR = VENV / ".requirements_instalados"


def titulo(msg):
    print(f"\n>> {msg}", flush=True)


def erro(msg):
    print(f"\n[ERRO] {msg}\n", flush=True)
    if getattr(sys, "frozen", False):
        try:
            import tkinter
            from tkinter import messagebox
            raiz = tkinter.Tk()
            raiz.withdraw()
            messagebox.showerror("exam2md", msg)
            raiz.destroy()
        except Exception:
            pass
    return 1


def python_base():
    """Python usado para criar o .venv (o próprio, quando roda como script)."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    for cmd in (["py", "-3"], ["python3"], ["python"]):
        try:
            if subprocess.run(cmd + ["-c", "import venv"], capture_output=True).returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    return None


def venv_funciona():
    if not VENV_PYTHON.exists():
        return False
    try:
        return subprocess.run([str(VENV_PYTHON), "-c", "import sys"], capture_output=True).returncode == 0
    except OSError:
        return False


def pip(*args, mostrar=False):
    cmd = [str(VENV_PYTHON), "-m", "pip", "install", "--disable-pip-version-check", *args]
    if not mostrar:
        cmd.insert(5, "-q")
    return subprocess.run(cmd).returncode == 0


def preparar_ambiente():
    """Cria o .venv e instala as dependências (só quando faltam ou mudaram)."""
    if sys.version_info < (3, 10) and not getattr(sys, "frozen", False):
        return erro(f"É preciso Python 3.10 ou mais novo (este é {sys.version.split()[0]}).\n"
                    "Baixe em https://www.python.org/downloads/")

    if VENV.exists() and not venv_funciona():
        # Python atualizado/movido: o .venv antigo não funciona mais
        titulo("Recriando o ambiente (o Python foi atualizado)...")
        shutil.rmtree(VENV, ignore_errors=True)

    if not VENV_PYTHON.exists():
        titulo("Primeira vez: preparando o exam2md (leva de 1 a 3 minutos)...")
        base = python_base()
        if base is None:
            return erro("Python não encontrado. Baixe em https://www.python.org/downloads/")
        base = base if isinstance(base, list) else [base]
        r = subprocess.run(base + ["-m", "venv", str(VENV)], capture_output=True, text=True)
        if r.returncode != 0:
            dica = ""
            if "ensurepip" in (r.stdout + r.stderr) and sys.platform.startswith("linux"):
                dica = "\nNo Ubuntu/Debian, instale antes:  sudo apt install python3-venv"
            return erro("Não foi possível criar o ambiente do exam2md." + dica + "\n" + r.stderr.strip()[-400:])

    requisitos = REQUISITOS.read_text(encoding="utf-8")
    if not MARCADOR.exists() or MARCADOR.read_text(encoding="utf-8") != requisitos:
        titulo("Instalando componentes (precisa de internet)...")
        if not pip("-r", str(REQUISITOS)):
            return erro("Falha ao instalar os componentes. Verifique a internet e tente de novo.")
        MARCADOR.write_text(requisitos, encoding="utf-8")
    return 0


def comandos_instalar_formulas(python):
    """Comandos pip para o pix2tex. No Windows/Linux, instala antes o PyTorch só
    para CPU (o padrão do PyPI no Linux traz CUDA e passa de 2 GB)."""
    base = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
    cmds = []
    if sys.platform != "darwin":
        cmds.append(base + ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])
    cmds.append(base + ["pix2tex"])
    return cmds


def instalar_formulas():
    titulo("Instalando o reconhecimento de fórmulas em imagem (~1 GB, alguns minutos)...")
    for cmd in comandos_instalar_formulas(VENV_PYTHON):
        if subprocess.run(cmd).returncode != 0:
            return erro("Falha ao instalar o reconhecimento de fórmulas. Verifique a internet.")
    print("\nPronto! Marque 'Fórmulas em imagem → LaTeX' na interface.")
    return 0


def instalar_ocr():
    """Nougat em um ambiente separado (.venv-nougat): conflita com as versões do pix2tex."""
    venv = BASE / ".venv-nougat"
    py = venv / ("Scripts/python.exe" if WINDOWS else "bin/python")
    if not py.exists():
        titulo("Criando ambiente separado para o OCR...")
        base = python_base()
        base = base if isinstance(base, list) else [base]
        if subprocess.run(base + ["-m", "venv", str(venv)]).returncode != 0:
            return erro("Falha ao criar o ambiente do OCR.")
    titulo("Instalando o Nougat (~2 GB, pode levar vários minutos)...")
    base = [str(py), "-m", "pip", "install", "--disable-pip-version-check"]
    passos = [base + ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"],
              base + ["transformers==4.44.2", "nougat-ocr"]]
    for cmd in passos[1 if sys.platform == "darwin" else 0:]:
        if subprocess.run(cmd).returncode != 0:
            return erro("Falha ao instalar o Nougat.")
    print("\nPronto! Use:  python reconstruir.py prova.pdf --ocr")
    return 0


def converter(pdfs):
    pdfs = [Path(p) for p in pdfs]
    if not pdfs:
        print("\nArraste um ou mais arquivos PDF sobre o atalho 'Arraste PDFs aqui'.")
        return 1
    falhas = 0
    for pdf in pdfs:
        if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
            print(f"\n[ignorado] {pdf.name}: não é um arquivo PDF")
            continue
        titulo(f"Convertendo {pdf.name}...")
        if subprocess.run([str(VENV_PYTHON), str(BASE / "reconstruir.py"), str(pdf)]).returncode != 0:
            falhas += 1
    print("\nPronto! O .md e a pasta de imagens ficam na mesma pasta de cada PDF.")
    return 1 if falhas else 0


def main():
    os.chdir(BASE)
    args = sys.argv[1:]

    if "--instalar-ocr" in args:
        return instalar_ocr()

    falhou = preparar_ambiente()
    if falhou:
        return falhou

    if "--preparar" in args:
        print("\nAmbiente pronto.")
        return 0
    if "--instalar-formulas" in args:
        return instalar_formulas()
    if "--converter" in args:
        return converter([a for a in args if a != "--converter"])

    print("\n" + "=" * 56)
    print("  exam2md está aberto no navegador.")
    print("  Deixe esta janela aberta enquanto usar; feche para sair.")
    print("=" * 56 + "\n", flush=True)
    try:
        return subprocess.run([str(VENV_PYTHON), str(BASE / "api.py"), "--abrir"]).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
