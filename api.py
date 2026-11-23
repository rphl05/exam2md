"""FastAPI wrapper for exam2md - Prova to Markdown converter."""

import tempfile
import shutil
import json
import zipfile
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pdfplumber

from reconstruir import converter_pdf, converter_com_nougat, processar_pagina

app = FastAPI(
    title="exam2md - Prova to Markdown",
    description="Converte PDFs de provas (EEAR, IF, ENEM, etc.) para Markdown com fórmulas LaTeX + Imagens + OCR",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConvertResponse(BaseModel):
    success: bool
    filename: str
    chars: int
    pages: int
    images_count: int = 0
    download_url: str
    images_url: Optional[str] = None
    message: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "exam2md"}


@app.post("/convert", response_model=ConvertResponse)
async def convert_pdf_endpoint(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),           # "1,2,3" or "1-5"
    save_images: bool = Form(False),             # extrai imagens
    ocr: bool = Form(False),                     # usa Nougat OCR
    images_dir: Optional[str] = Form(None),      # pasta customizada para imagens
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

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

    # Save upload to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        # Output filename = input stem + .md
        output_name = Path(file.filename).with_suffix(".md").name
        
        # Pasta de imagens (temp dir)
        pasta_imagens = None
        if save_images:
            pasta_imagens = tmp_path.parent / f"{tmp_path.stem}_images"
        
        if ocr:
            chars = converter_com_nougat(tmp_path, tmp_path.with_suffix(".md"), paginas)
            images_count = 0
        else:
            chars = converter_pdf(tmp_path, tmp_path.with_suffix(".md"), paginas, pasta_imagens)
            # Conta imagens se houver
            images_count = 0
            if pasta_imagens and pasta_imagens.exists():
                manifest = pasta_imagens / "manifest.json"
                if manifest.exists():
                    import json
                    with open(manifest) as f:
                        images_count = len(json.load(f))

        # Prepara resposta
        response = ConvertResponse(
            success=True,
            filename=output_name,
            chars=chars,
            pages=len(paginas) if paginas else "all",
            images_count=images_count,
            download_url=f"/download/{output_name}",
        )

        # Se tem imagens, cria ZIP para download
        if images_count > 0 and pasta_imagens and pasta_imagens.exists():
            # Cria ZIP com markdown + imagens
            zip_path = tmp_path.parent / f"{tmp_path.stem}_complete.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Adiciona markdown
                md_path = tmp_path.with_suffix(".md")
                zf.write(md_path, output_name)
                # Adiciona imagens
                for img_file in pasta_imagens.glob("*"):
                    if img_file.name != "manifest.json":
                        zf.write(img_file, f"images/{img_file.name}")
                # Adiciona manifest
                manifest = pasta_imagens / "manifest.json"
                if manifest.exists():
                    zf.write(manifest, "images/manifest.json")
            
            response.download_url = f"/download-zip/{zip_path.name}"
            response.message = f"Inclui {images_count} imagens no ZIP"

        return response

    except Exception as e:
        raise HTTPException(500, f"Erro na conversão: {e}")
    finally:
        # Cleanup input temp file
        try:
            tmp_path.unlink()
        except Exception:
            pass


@app.get("/download/{filename}")
async def download_file(filename: str):
    temp_dir = Path(tempfile.gettempdir())
    file_path = temp_dir / filename
    if not file_path.exists():
        raise HTTPException(404, "Arquivo não encontrado ou expirado")
    return FileResponse(
        file_path,
        media_type="text/markdown",
        filename=filename,
    )


@app.get("/download-zip/{filename}")
async def download_zip(filename: str):
    temp_dir = Path(tempfile.gettempdir())
    file_path = temp_dir / filename
    if not file_path.exists():
        raise HTTPException(404, "Arquivo não encontrado ou expirado")
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename,
    )


@app.post("/convert-stream")
async def convert_stream(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),
    save_images: bool = Form(False),
    ocr: bool = Form(False),
):
    """
    Versão streaming para arquivos grandes - retorna markdown conforme vai gerando.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    # Salva upload
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    async def generate():
        try:
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

            with pdfplumber.open(str(tmp_path)) as pdf:
                alvos = paginas if paginas is not None else range(len(pdf.pages))
                for indice in alvos:
                    texto, _ = processar_pagina(pdf.pages[indice])
                    yield f"<!-- pagina {indice + 1} -->\n{texto}\n\n"
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={Path(file.filename).with_suffix('.md').name}"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)