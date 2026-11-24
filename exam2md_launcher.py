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
    """Encontra o executável do Python"""
    # Tenta python no PATH
    for cmd in ["python", "python3", "py"]:
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
    
    if not venv_python.exists():
        print("[1/3] Criando ambiente virtual...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        print("[2/3] Instalando dependências...")
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    else:
        print("[1/2] Verificando dependências...")
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], 
                      capture_output=True)
    
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


def main():
    # Diretório do script/executável
    if getattr(sys, 'frozen', False):
        # Executando como executável compilado
        base_dir = Path(sys.executable).parent
    else:
        # Executando como script
        base_dir = Path(__file__).parent
    
    os.chdir(base_dir)
    
    print("=" * 50)
    print("  exam2md - Conversor de Provas para Markdown")
    print("=" * 50)
    print()
    print("Escolha o modo:")
    print("  1) Servidor Web (conversao via navegador)")
    print("  2) Instalar/Atualizar Nougat OCR (para PDFs escaneados)")
    print("  3) Sair")
    print()
    
    while True:
        choice = input("Escolha (1/2/3): ").strip()
        if choice in ("1", "2", "3"):
            break
        print("Opcao invalida. Digite 1, 2 ou 3.")
    
    if choice == "3":
        return 0
    
    if choice == "2":
        # Instala Nougat OCR
        python_cmd = find_python()
        if not python_cmd:
            input("ERRO: Python nao encontrado!\nInstale em: https://python.org/downloads\nMarque 'Add Python to PATH'\n\nPressione Enter para sair...")
            return 1
        
        print(f"Python encontrado: {python_cmd}")
        if not install_nougat_ocr(Path(base_dir), python_cmd):
            input("\nFalha na instalacao. Pressione Enter para sair...")
            return 1
        input("\nInstalacao concluida! Pressione Enter para continuar...")
        # Volta ao menu principal
        return main()
    
    # Opção 1: Servidor Web
    # Encontra Python
    python_cmd = find_python()
    if not python_cmd:
        input("ERRO: Python não encontrado!\nInstale em: https://python.org/downloads\nMarque 'Add Python to PATH'\n\nPressione Enter para sair...")
        return 1

    # Configura venv e inicia servidor
    venv_python = setup_venv(Path(base_dir), python_cmd)
    
    print("\n[OK] Servidor iniciando em http://localhost:8000")
    print("Abrindo navegador...")
    print()
    print("=" * 50)
    print("  PRONTO! O navegador vai abrir automaticamente.")
    print("  Arraste seu PDF na area indicada e clique 'Converter'.")
    print("=" * 50)
    print()
    print("Para parar: pressione Ctrl+C nesta janela.")
    print("=" * 50)
    print()

    # Abre navegador após delay
    open_browser_delayed("http://localhost:8000/web/", delay=2.0)
    
    # Inicia servidor (bloqueia)
    try:
        subprocess.run([str(venv_python), "api.py"], check=True)
    except KeyboardInterrupt:
        print("\nServidor parado.")
    except subprocess.CalledProcessError as e:
        print(f"\nERRO ao iniciar servidor: {e}")
        input("Pressione Enter para sair...")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())