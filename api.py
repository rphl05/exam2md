"""Servidor local do exam2md: interface web + API de conversão.

    python api.py            # sobe em http://localhost:8000
    python api.py --abrir    # e abre o navegador
    python api.py --porta 8080

Endpoints:
    POST /convert                 files=<pdf>[, <pdf>...], pages, extrair_imagens, formulas_imagem
                                  -> {"job_id": ...}
    GET  /jobs/{job_id}           progresso, resultados e prévia do Markdown
    GET  /jobs/{job_id}/download  .md (1 PDF sem imagens) ou .zip (md + pasta de imagens)
"""

import argparse
import importlib.util
import io
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from exam2md_launcher import comandos_instalar_formulas
from reconstruir import converter, nome_seguro, parse_paginas

app = FastAPI(title="exam2md", description="Provas em PDF -> Markdown com LaTeX + imagens", version="2.0.0")

RAIZ_JOBS = Path(tempfile.gettempdir()) / "exam2md_jobs"
RAIZ_JOBS.mkdir(parents=True, exist_ok=True)
TEMPO_VIDA = 6 * 3600  # jobs antigos são apagados depois de 6 h
MAX_PREVIA = 200_000

jobs = {}
trava = threading.Lock()
# Uma conversão por vez: o pdfplumber é pesado e o pix2tex não é thread-safe
fila = threading.Semaphore(1)

AVISO_PAGINA_ANTIGA = ("Nenhum PDF recebido. Se você acabou de atualizar o exam2md, "
                       "o navegador está usando a página antiga: recarregue com Ctrl+F5 (Cmd+Shift+R no Mac).")


@app.middleware("http")
async def sem_cache_na_interface(request: Request, call_next):
    """Evita que o navegador guarde a interface antiga depois de uma atualização."""
    resposta = await call_next(request)
    if request.url.path.startswith("/web"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(_request: Request, exc: RequestValidationError):
    """Devolve 'detail' como texto legível (o padrão do FastAPI é uma lista de objetos)."""
    campos = {str(e.get("loc", [""])[-1]) for e in exc.errors()}
    if "files" in campos:
        msg = AVISO_PAGINA_ANTIGA
    else:
        msg = "; ".join(f"{'.'.join(map(str, e.get('loc', [])))}: {e.get('msg')}" for e in exc.errors())
    return JSONResponse(status_code=422, content={"detail": msg})


def _limpar_antigos():
    agora = time.time()
    for pasta in RAIZ_JOBS.iterdir():
        try:
            if pasta.is_dir() and agora - pasta.stat().st_mtime > TEMPO_VIDA:
                shutil.rmtree(pasta, ignore_errors=True)
                jobs.pop(pasta.name, None)
        except OSError:
            pass


def _nome_pdf(nome: str, usados: set) -> str:
    base = nome_seguro(Path(nome).stem)
    candidato, n = base, 2
    while candidato in usados:
        candidato, n = f"{base}_{n}", n + 1
    usados.add(candidato)
    return candidato


def _executar(job_id: str, entradas: List[Path], paginas, extrair_imagens: bool, formulas_imagem: bool):
    job = jobs[job_id]
    pasta = RAIZ_JOBS / job_id / "saida"
    pasta.mkdir(parents=True, exist_ok=True)
    with fila:
        job["status"] = "processando"
        for i, pdf in enumerate(entradas):
            job["arquivo_atual"] = pdf.name

            def progresso(feitas, total, i=i):
                job["progresso"] = int(100 * (i + feitas / max(total, 1)) / len(entradas))

            md = pasta / f"{pdf.stem}.md"
            imgs = pasta / f"{pdf.stem}_images" if extrair_imagens else None
            try:
                resumo = converter(pdf, md, paginas, imgs, formulas_imagem, progresso)
                job["resultados"].append({
                    "arquivo": md.name,
                    "pdf": pdf.name,
                    "ok": True,
                    "caracteres": resumo["caracteres"],
                    "paginas": resumo["paginas"],
                    "imagens": resumo["imagens"],
                })
            except Exception as e:  # noqa: BLE001
                job["resultados"].append({"arquivo": md.name, "pdf": pdf.name, "ok": False, "erro": str(e)})
            finally:
                pdf.unlink(missing_ok=True)
        job["progresso"] = 100
        job["arquivo_atual"] = None
        job["status"] = "concluido"


@app.get("/")
def raiz():
    return RedirectResponse("/web/")


@app.get("/health")
def health():
    return {"status": "ok", "service": "exam2md"}


# Instalação do reconhecimento de fórmulas (pix2tex) pela interface
instalacao = {"status": "ocioso", "mensagem": ""}


def formulas_disponiveis() -> bool:
    importlib.invalidate_caches()
    return importlib.util.find_spec("pix2tex") is not None


def _instalar_formulas():
    try:
        for i, cmd in enumerate(comandos_instalar_formulas(sys.executable), 1):
            instalacao["mensagem"] = f"Baixando e instalando (etapa {i}). Pode levar alguns minutos…"
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip()[-600:])
        instalacao.update(status="ok", mensagem="Instalado.")
    except Exception as e:  # noqa: BLE001
        instalacao.update(status="erro", mensagem=f"Falha na instalação (verifique a internet): {e}")


@app.get("/recursos")
def recursos():
    return {"formulas": formulas_disponiveis(), "instalacao": instalacao}


@app.post("/recursos/formulas")
def instalar_formulas():
    if formulas_disponiveis():
        return recursos()
    with trava:
        if instalacao["status"] != "instalando":
            instalacao.update(status="instalando", mensagem="Iniciando…")
            threading.Thread(target=_instalar_formulas, daemon=True).start()
    return recursos()


@app.post("/convert")
async def convert(
    files: List[UploadFile] = File(...),
    pages: Optional[str] = Form(None),
    extrair_imagens: bool = Form(True),
    formulas_imagem: bool = Form(False),
):
    _limpar_antigos()
    if not files:
        raise HTTPException(400, AVISO_PAGINA_ANTIGA)
    try:
        paginas = parse_paginas(pages)
    except ValueError:
        raise HTTPException(400, "Páginas inválidas. Use, por exemplo: 1,3-5")

    job_id = uuid.uuid4().hex[:12]
    entrada = RAIZ_JOBS / job_id / "entrada"
    entrada.mkdir(parents=True)
    usados, caminhos = set(), []
    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            shutil.rmtree(RAIZ_JOBS / job_id, ignore_errors=True)
            raise HTTPException(400, f"{f.filename}: o arquivo deve ser PDF")
        destino = entrada / f"{_nome_pdf(f.filename, usados)}.pdf"
        with destino.open("wb") as saida:
            shutil.copyfileobj(f.file, saida)  # lido aqui, antes da resposta
        caminhos.append(destino)

    with trava:
        jobs[job_id] = {"status": "na_fila", "progresso": 0, "arquivo_atual": None, "resultados": []}
    threading.Thread(
        target=_executar, args=(job_id, caminhos, paginas, extrair_imagens, formulas_imagem), daemon=True
    ).start()
    return {"job_id": job_id}


def _job(job_id: str):
    if not re.fullmatch(r"[0-9a-f]{12}", job_id) or job_id not in jobs:
        raise HTTPException(404, "Conversão não encontrada ou expirada")
    return jobs[job_id]


@app.get("/jobs/{job_id}")
def status(job_id: str):
    job = _job(job_id)
    resposta = dict(job)
    ok = [r for r in job["resultados"] if r.get("ok")]
    if job["status"] == "concluido" and ok:
        md = RAIZ_JOBS / job_id / "saida" / ok[0]["arquivo"]
        texto = md.read_text(encoding="utf-8")
        resposta["previa"] = texto[:MAX_PREVIA]
        resposta["previa_truncada"] = len(texto) > MAX_PREVIA
        resposta["download"] = f"/jobs/{job_id}/download"
    return resposta


@app.get("/jobs/{job_id}/download")
def download(job_id: str):
    job = _job(job_id)
    if job["status"] != "concluido":
        raise HTTPException(409, "Conversão ainda em andamento")
    saida = RAIZ_JOBS / job_id / "saida"
    ok = [r for r in job["resultados"] if r.get("ok")]
    if not ok:
        raise HTTPException(404, "Nenhum arquivo convertido")

    if len(ok) == 1 and not ok[0]["imagens"]:
        return FileResponse(saida / ok[0]["arquivo"], media_type="text/markdown; charset=utf-8",
                            filename=ok[0]["arquivo"])

    # ZIP com a mesma estrutura gerada em disco: prova.md + prova_images/...
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for arquivo in sorted(saida.rglob("*")):
            if arquivo.is_file():
                zf.write(arquivo, arquivo.relative_to(saida).as_posix())
    buffer.seek(0)
    nome = f"{Path(ok[0]['arquivo']).stem}.zip" if len(ok) == 1 else f"provas_{job_id}.zip"
    return StreamingResponse(buffer, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})


web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")


def porta_livre(inicial: int) -> int:
    for porta in range(inicial, inicial + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    return inicial


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Servidor local do exam2md")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--abrir", action="store_true", help="Abre o navegador")
    args = parser.parse_args()

    porta = porta_livre(args.porta)
    url = f"http://localhost:{porta}/web/"
    print(f"exam2md rodando em {url}  (Ctrl+C para parar)")
    if args.abrir:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    # Só na máquina local: não expõe os arquivos para a rede
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")


if __name__ == "__main__":
    main()
