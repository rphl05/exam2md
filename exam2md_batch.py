#!/usr/bin/env python3
"""
exam2md_batch.py - Processamento em lote (fila de conversão)
Permite adicionar múltiplos PDFs e converte um por um em sequência.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List
from datetime import datetime

from reconstruir import converter_pdf


def format_time(seconds: float) -> str:
    """Formata tempo em formato legível"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}h"


def process_batch(pdf_files: List[Path], output_dir: Path = None, 
                  pages: str = None, save_images: bool = False,
                  images_dir: Path = None, ocr: bool = False) -> dict:
    """
    Processa uma lista de PDFs em sequência.
    
    Returns:
        dict com estatísticas: total, sucessos, falhas, tempo_total, detalhes
    """
    stats = {
        "total": len(pdf_files),
        "sucessos": 0,
        "falhas": 0,
        "tempo_total": 0,
        "detalhes": []
    }
    
    start_total = time.time()
    
    print(f"\n{'='*60}")
    print(f"  PROCESSAMENTO EM LOTE - {len(pdf_files)} arquivo(s)")
    print(f"{'='*60}\n")
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Processando: {pdf_path.name}")
        print("-" * 50)
        
        if not pdf_path.exists():
            print(f"  ❌ ERRO: Arquivo não encontrado")
            stats["falhas"] += 1
            stats["detalhes"].append({
                "arquivo": pdf_path.name,
                "status": "erro",
                "erro": "Arquivo não encontrado",
                "tempo": 0
            })
            continue
        
        # Define output path
        if output_dir:
            output_path = output_dir / f"{pdf_path.stem}.md"
        else:
            output_path = pdf_path.with_suffix(".md")
        
        # Define images dir
        img_dir = None
        if save_images:
            if images_dir:
                img_dir = images_dir / f"{pdf_path.stem}_images"
            else:
                img_dir = output_path.parent / f"{pdf_path.stem}_images"
        
        # Parse pages
        paginas = None
        if pages:
            paginas = []
            for parte in pages.split(","):
                parte = parte.strip()
                if "-" in parte:
                    ini, fim = map(int, parte.split("-", 1))
                    paginas.extend(range(ini - 1, fim))
                else:
                    paginas.append(int(parte) - 1)
        
        start_file = time.time()
        
        try:
            if ocr:
                from reconstruir import converter_com_nougat
                chars = converter_com_nougat(pdf_path, output_path, paginas)
            else:
                chars = converter_pdf(pdf_path, output_path, paginas, img_dir)
            
            tempo = time.time() - start_file
            stats["sucessos"] += 1
            stats["detalhes"].append({
                "arquivo": pdf_path.name,
                "status": "sucesso",
                "chars": chars,
                "tempo": tempo,
                "output": str(output_path)
            })
            print(f"  [OK] Sucesso! ({format_time(tempo)}) - {chars:,} chars")
            print(f"     Saida: {output_path}")
            
        except Exception as e:
            tempo = time.time() - start_file
            stats["falhas"] += 1
            stats["detalhes"].append({
                "arquivo": pdf_path.name,
                "status": "erro",
                "erro": str(e),
                "tempo": tempo
            })
            print(f"  [ERRO] {e}")
        
        # Pequena pausa entre arquivos para não sobrecarregar
        if i < len(pdf_files):
            time.sleep(0.5)
    
    stats["tempo_total"] = time.time() - start_total
    return stats


def print_summary(stats: dict):
    """Imprime resumo final"""
    print(f"\n{'='*60}")
    print(f"  RESUMO DO PROCESSAMENTO")
    print(f"{'='*60}")
    print(f"  Total de arquivos:  {stats['total']}")
    print(f"  [OK] Sucessos:      {stats['sucessos']}")
    print(f"  [ERRO] Falhas:      {stats['falhas']}")
    print(f"  Tempo total:        {format_time(stats['tempo_total'])}")
    
    if stats["sucessos"] > 0:
        tempo_medio = stats["tempo_total"] / stats["sucessos"]
        print(f"  Tempo medio:        {format_time(tempo_medio)}/arquivo")
    
    print(f"\n{'='*60}")
    print("  DETALHES:")
    print(f"{'='*60}")
    
    for d in stats["detalhes"]:
        status_icon = "[OK]" if d["status"] == "sucesso" else "[ERRO]"
        tempo_str = format_time(d["tempo"])
        if d["status"] == "sucesso":
            print(f"  {status_icon} {d['arquivo']} - {d['chars']:,} chars - {tempo_str}")
        else:
            print(f"  {status_icon} {d['arquivo']} - ERRO: {d['erro']} ({tempo_str})")


def main():
    parser = argparse.ArgumentParser(
        description="exam2md Batch - Processamento em lote de PDFs para Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python exam2md_batch.py *.pdf                    # Todos PDFs da pasta
  python exam2md_batch.py prova1.pdf prova2.pdf    # Arquivos específicos
  python exam2md_batch.py pasta/*.pdf --save-images  # Com imagens
  python exam2md_batch.py provas/ -o saida/         # Pasta de saída customizada
  python exam2md_batch.py *.pdf --ocr               # Com OCR (PDFs escaneados)
        """
    )
    
    parser.add_argument("arquivos", nargs="+", help="Arquivos PDF ou padrões (ex: *.pdf)")
    parser.add_argument("-o", "--output", type=Path, help="Pasta de saída para arquivos .md")
    parser.add_argument("--pages", help="Páginas (ex: 1,3-5,10)")
    parser.add_argument("--save-images", action="store_true", help=argparse.SUPPRESS)  # padrão agora
    parser.add_argument("--no-images", action="store_true", help="Não extrai imagens")
    parser.add_argument("--images-dir", type=Path, help="Pasta customizada para imagens")
    parser.add_argument("--ocr", action="store_true", help="Usa Nougat OCR (para PDFs escaneados)")
    parser.add_argument("--relatorio", type=Path, help="Salva relatório JSON")

    args = parser.parse_args()
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")  # emojis em console Windows (cp1252)
        except Exception:
            pass
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)

    # Expande padrões (glob) e pastas
    pdf_files = []
    for pattern in args.arquivos:
        path = Path(pattern)
        if path.is_file():
            pdf_files.append(path)
        elif path.is_dir():
            pdf_files.extend(sorted(path.glob("*.pdf")))
        else:
            # Expande glob
            parent = path.parent if path.parent != Path(".") else Path(".")
            matches = list(parent.glob(path.name))
            pdf_files.extend(matches)
    
    # Remove duplicatas mantendo ordem
    seen = set()
    pdf_files_unique = []
    for f in pdf_files:
        if f not in seen:
            seen.add(f)
            pdf_files_unique.append(f)
    
    if not pdf_files_unique:
        print("❌ Nenhum arquivo PDF encontrado!")
        return 1
    
    # Processa
    stats = process_batch(
        pdf_files=pdf_files_unique,
        output_dir=args.output,
        pages=args.pages,
        save_images=not args.no_images,
        images_dir=args.images_dir,
        ocr=args.ocr
    )
    
    # Imprime resumo
    print_summary(stats)
    
    # Salva relatório JSON se solicitado
    if args.relatorio:
        import json
        relatorio = {
            "timestamp": datetime.now().isoformat(),
            "estatisticas": {
                "total": stats["total"],
                "sucessos": stats["sucessos"],
                "falhas": stats["falhas"],
                "tempo_total_segundos": stats["tempo_total"]
            },
            "detalhes": stats["detalhes"]
        }
        args.relatorio.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False))
        print(f"\n📄 Relatório salvo em: {args.relatorio}")
    
    # Exit code
    return 0 if stats["falhas"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())