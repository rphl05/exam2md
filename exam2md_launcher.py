#!/usr/bin/env python3
"""
exam2md_launcher.py - Launcher Python moderno
Pode ser compilado para .exe com: pyinstaller --onefile --noconsole exam2md_launcher.py
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

def find_python():
    """Encontra o executável do Python 3"""
    if not getattr(sys, "frozen", False):
        return sys.executable  # rodando como script: usa o próprio interpretador
    for cmd in ["python3", "python", "py"]:
        try:
            result = subprocess.run([cmd, "--version"], capture_output=True)
            if result.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    
    # Tenta locais comuns no Windows
    common_paths = [
        r"%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe",
        r"%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe",
        r"%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe",
        r"C:\Python312\python.exe",
        r"C:\Python311\python.exe",
    ]
    
    for path in common_paths:
        expanded = os.path.expandvars(path)
        if os.path.exists(expanded):
            return expanded
    
    return None

def setup_venv(project_dir: Path, python_cmd: str) -> Path:
    """Cria/atualiza ambiente virtual e retorna caminho do python do venv"""
    venv_dir = project_dir / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe" if sys.platform == "win32" else venv_dir / "bin" / "python"
    
    requisitos = project_dir / "requirements.txt"
    marcador = venv_dir / ".requirements_instalados"
    if not venv_python.exists():
        print("[1/2] Criando ambiente virtual (só na primeira vez)...")
        subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
    # Reinstala só se o requirements.txt mudou desde a última instalação
    if not marcador.exists() or marcador.read_text() != requisitos.read_text():
        print("[2/2] Instalando dependências...")
        subprocess.run([str(venv_python), "-m", "pip", "install", "-q", "-r", str(requisitos)], check=True)
        marcador.write_text(requisitos.read_text())

    return venv_python

def open_browser_delayed(url: str, delay: float = 2.0):
    """Abre navegador após delay"""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

def install_nougat_ocr(project_dir: Path, python_cmd: str) -> bool:
    """Instala Nougat OCR em venv isolado (.venv-nougat)"""
    venv_dir = project_dir / ".venv-nougat"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
        venv_pip = venv_dir / "Scripts" / "pip.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
        venv_pip = venv_dir / "bin" / "pip"

    if venv_python.exists():
        print(f"[OK] .venv-nougat ja existe em {venv_dir}")
        return True

    print("\n[1/4] Criando ambiente virtual isolado para Nougat...")
    try:
        subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
    except subprocess.CalledProcessError:
        print("  ERRO: Falha ao criar venv")
        return False

    print("[2/4] Atualizando pip...")
    try:
        subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], 
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("  Aviso: Falha ao atualizar pip")
        pass

    print("[3/4] Instalando PyTorch (CPU)...")
    try:
        subprocess.run([str(venv_pip), "install", "torch", "torchvision", 
                       "--index-url", "https://download.pytorch.org/whl/cpu"], 
                      check=True)
    except subprocess.CalledProcessError:
        print("  ERRO: Falha ao instalar PyTorch")
        return False

    print("[4/4] Instalando Nougat OCR (transformers==4.44.2)...")
    try:
        subprocess.run([str(venv_pip), "install", "transformers==4.44.2", "nougat-ocr"], 
                      check=True)
    except subprocess.CalledProcessError:
        print("  Tentando versao alternativa (transformers==4.44.0)...")
        try:
            subprocess.run([str(venv_pip), "install", "transformers==4.44.0", "nougat-ocr"], 
                          check=True)
        except subprocess.CalledProcessError:
            print("  ERRO: Falha ao instalar Nougat OCR")
            return False

    print(f"\n[OK] Nougat instalado em {venv_dir}")
    return True


def avisar(msg: str):
    """Mostra a mensagem mesmo quando compilado sem console (--noconsole)."""
    print(msg)
    if getattr(sys, "frozen", False):
        try:
            import tkinter
            from tkinter import messagebox
            raiz = tkinter.Tk()
            raiz.withdraw()
            messagebox.showinfo("exam2md", msg)
            raiz.destroy()
        except Exception:
            pass


def main():
    """Duplo clique: prepara o ambiente, sobe o servidor e abre o navegador.

    python exam2md_launcher.py               # interface web
    python exam2md_launcher.py --instalar-ocr  # instala o Nougat (PDF escaneado)
    """
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    os.chdir(base_dir)

    python_cmd = find_python()
    if not python_cmd:
        avisar("Python não encontrado.\nInstale em https://python.org/downloads "
               "(no Windows, marque 'Add Python to PATH').")
        return 1

    if "--instalar-ocr" in sys.argv:
        ok = install_nougat_ocr(base_dir, python_cmd)
        avisar("Nougat instalado." if ok else "Falha ao instalar o Nougat.")
        return 0 if ok else 1

    print("=" * 50)
    print("  exam2md - Conversor de Provas para Markdown")
    print("=" * 50)
    try:
        venv_python = setup_venv(base_dir, python_cmd)
    except subprocess.CalledProcessError as e:
        avisar(f"Erro ao preparar o ambiente: {e}")
        return 1

    print("\nAbrindo o navegador... Para parar, feche esta janela (ou Ctrl+C).\n")
    try:
        subprocess.run([str(venv_python), "api.py", "--abrir"], check=True)
    except KeyboardInterrupt:
        print("\nServidor parado.")
    except subprocess.CalledProcessError as e:
        avisar(f"Erro ao iniciar o servidor: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
