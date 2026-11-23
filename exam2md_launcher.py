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
    
    # Encontra Python
    python_cmd = find_python()
    if not python_cmd:
        input("ERRO: Python não encontrado!\nInstale em: https://python.org/downloads\nMarque 'Add Python to PATH'\n\nPressione Enter para sair...")
        return 1
    
    print(f"Python encontrado: {python_cmd}")
    
    # Configura venv
    try:
        venv_python = setup_venv(Path(base_dir), python_cmd)
    except subprocess.CalledProcessError as e:
        print(f"ERRO ao configurar ambiente: {e}")
        input("Pressione Enter para sair...")
        return 1
    
    # Inicia servidor
    api_script = base_dir / "api.py"
    if not api_script.exists():
        print(f"ERRO: api.py não encontrado em {api_script}")
        input("Pressione Enter para sair...")
        return 1
    
    print("[OK] Servidor iniciando em http://localhost:8000")
    print()
    print("=" * 50)
    print("  PRONTO! O navegador vai abrir automaticamente.")
    print("  Arraste seu PDF na área indicada e clique 'Converter'.")
    print("=" * 50)
    print()
    print("Para parar: feche esta janela (Ctrl+C)")
    print("=" * 50)
    print()
    
    # Abre navegador após 2 segundos
    open_browser_delayed("http://localhost:8000", 2.0)
    
    # Inicia servidor (bloqueia)
    try:
        subprocess.run([str(venv_python), "api.py"], check=True)
    except KeyboardInterrupt:
        print("\nServidor parado.")
    except subprocess.CalledProcessError as e:
        print(f"\nERRO no servidor: {e}")
        input("Pressione Enter para sair...")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())