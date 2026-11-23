#!/usr/bin/env python3
"""
install_nougat.py - Instalador 1-clique para Nougat OCR
Cria venv isolado (.venv-nougat) sem conflitar com pdfplumber
"""

import subprocess
import sys
import os
from pathlib import Path

def run_cmd(cmd, desc, check=True):
    """Executa comando com feedback visual"""
    print(f"[{desc}]")
    try:
        result = subprocess.run(cmd, shell=True, check=check, 
                              capture_output=True, text=True)
        if result.stdout:
            # Mostra últimas linhas de output
            lines = result.stdout.strip().split('\n')
            for line in lines[-3:]:
                if line.strip():
                    print(f"  {line}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ERRO: {e}")
        if e.stdout:
            print(f"  stdout: {e.stdout[-500:]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[-500:]}")
        return False

def main():
    print("=" * 60)
    print("  exam2md - Instalador Nougat OCR (1 clique)")
    print("=" * 60)
    print()
    print("Cria ambiente isolado (.venv-nougat) para Nougat OCR")
    print("sem conflitar com pdfplumber (transformers 4.44.x vs 4.46+)")
    print()
    print("Requisitos:")
    print("  - Python 3.10+ instalado e no PATH")
    print("  - Conexao internet (baixa ~1.5 GB)")
    print("  - Espaco em disco: ~3 GB")
    print()
    print("Dependencias que serao instaladas no .venv-nougat:")
    print("  - torch, torchvision (CPU)")
    print("  - transformers==4.44.2 (exato, para compatibilidade)")
    print("  - timm==0.5.4")
    print("  - nougat-ocr")
    print()

    # Verifica Python
    python_cmd = sys.executable
    print(f"Python detectado: {sys.version.split()[0]}")
    print(f"Executavel: {python_cmd}")
    print()

    # Verifica se ja existe
    venv_path = Path(".venv-nougat")
    if venv_path.exists():
        resp = input("AVISO: .venv-nougat ja existe. Recriar? [s/N]: ").strip().lower()
        if resp != 's':
            print("Instalacao cancelada.")
            return 0
        import shutil
        print("Removendo ambiente antigo...")
        import shutil
        shutil.rmtree(venv_path, ignore_errors=True)

    print()
    print("=" * 50)
    print("INICIANDO INSTALACAO")
    print("=" * 50)

    # 1. Cria venv
    print("\n[1/4] Criando ambiente virtual isolado...")
    if not run_cmd(f'"{sys.executable}" -m venv .venv-nougat', "Criando venv"):
        return 1

    # Determina python do venv
    if os.name == 'nt':
        venv_python = ".venv-nougat\\Scripts\\python.exe"
        venv_pip = ".venv-nougat\\Scripts\\pip"
    else:
        venv_python = ".venv-nougat/bin/python"
        venv_pip = ".venv-nougat/bin/pip"

    # 2. Atualiza pip
    print("\n[2/4] Atualizando pip...")
    if not run_cmd(f'"{venv_python}" -m pip install --upgrade pip', "Atualizando pip"):
        return 1

    # 3. PyTorch CPU
    print("\n[3/4] Instalando PyTorch (CPU)...")
    print("  (pode demorar 2-5 minutos dependendo da conexao)")
    if not run_cmd(f'"{venv_pip}" install torch torchvision --index-url https://download.pytorch.org/whl/cpu', "Instalando PyTorch"):
        return 1

    # 4. Nougat OCR com transformers fixo
    print("\n[4/4] Instalando Nougat OCR...")
    print("  (transformers==4.44.2 + nougat-ocr)")
    print("  (pode demorar 3-8 minutos)")
    cmd = f'"{venv_pip}" install "transformers==4.44.2" nougat-ocr'
    if not run_cmd(cmd, "Instalando Nougat"):
        print("\nTentando versao alternativa (transformers==4.44.0)...")
        cmd = f'"{venv_pip}" install "transformers==4.44.0" nougat-ocr'
        if not run_cmd(cmd, "Instalando Nougat (alt)"):
            print("\nERRO: Falha ao instalar Nougat OCR")
            print("Tente rodar manualmente:")
            print(f"  {venv_pip} install 'transformers==4.44.2' nougat-ocr")
            return 1

    # Sucesso!
    print()
    print("=" * 50)
    print("  INSTALACAO CONCLUIDA COM SUCESSO!")
    print("=" * 50)
    print()
    print("Como usar OCR:")
    print(f"  {venv_python} reconstruir.py arquivo.pdf --ocr")
    print()
    print("Via API (web):")
    print(f"  1. {venv_python} api.py")
    print(f"  2. POST /convert com 'ocr': true")
    print()
    print(f"Ambiente isolado em: .venv-nougat/")
    print(f"(isolado do pdfplumber - sem conflitos de transformers)")
    print()
    return 0

if __name__ == "__main__":
    sys.exit(main())