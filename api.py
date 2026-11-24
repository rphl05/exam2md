"""FastAPI wrapper for exam2md - Prova to Markdown converter."""

import tempfile
import shutil
import json
import zipfile
import uuid
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import asyncio

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
    pages: int | str
    images_count: int = 0
    download_url: str
    images_url: Optional[str] = None
    message: Optional[str] = None


class BatchConvertResponse(BaseModel):
    success: bool
    total: int
    completed: int
    failed: int
    results: List[ConvertResponse]
    zip_download_url: Optional[str] = None
    message: Optional[str] = None


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str  # "pending", "processing", "completed", "failed"
    progress: int  # 0-100
    current_file: Optional[str] = None
    results: List[ConvertResponse] = []
    error: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


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
            temp_md_path = tmp_path.with_suffix(".md")
            chars = converter_com_nougat(tmp_path, temp_md_path, paginas)
            # Copy/rename to expected output name in same temp dir for download
            output_md_path = tmp_path.parent / output_name
            if temp_md_path != output_md_path:
                shutil.copy2(temp_md_path, output_md_path)
            images_count = 0
        else:
            temp_md_path = tmp_path.with_suffix(".md")
            chars = converter_pdf(tmp_path, temp_md_path, paginas, pasta_imagens)
            # Copy/rename to expected output name in same temp dir for download
            output_md_path = tmp_path.parent / output_name
            if temp_md_path != output_md_path:
                shutil.copy2(temp_md_path, output_md_path)
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
                md_path = tmp_path.parent / output_name
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


# In-memory storage for batch jobs (em produção usar Redis/DB)
batch_jobs = {}


@app.post("/convert-batch", response_model=BatchConvertResponse)
async def convert_batch_endpoint(
    files: List[UploadFile] = File(...),
    pages: Optional[str] = Form(None),
    save_images: bool = Form(False),
    ocr: bool = Form(False),
    images_dir: Optional[str] = Form(None),
):
    """
    Converte múltiplos PDFs em lote.
    Retorna quando todos terminarem, com ZIP contendo todos os resultados.
    """
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")
    
    # Valida todos os arquivos
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Arquivo {file.filename} não é PDF")
    
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
    
    # Cria batch ID
    import uuid
    batch_id = str(uuid.uuid4())[:8]
    
    # Inicializa job
    batch_jobs[batch_id] = {
        "status": "processing",
        "progress": 0,
        "total": len(files),
        "completed": 0,
        "failed": 0,
        "current_file": None,
        "results": [],
        "error": None,
        "zip_path": None
    }
    
    # Processa em background
    asyncio.create_task(_process_batch(
        batch_id, files, paginas, save_images, ocr, images_dir
    ))
    
    return BatchConvertResponse(
        success=True,
        total=len(files),
        completed=0,
        failed=0,
        results=[],
        message=f"Batch {batch_id} iniciado. Use GET /batch-status/{batch_id} para acompanhar."
    )


async def _process_batch(
    batch_id: str,
    files: List[UploadFile],
    paginas: Optional[List[int]],
    save_images: bool,
    ocr: bool,
    images_dir: Optional[str]
):
    """Processa lote de PDFs em background"""
    job = batch_jobs[batch_id]
    results = []
    zip_files = []
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        
        for i, file in enumerate(files):
            job["current_file"] = file.filename
            job["progress"] = int((i / len(files)) * 100)
            
            # Salva upload
            tmp_path = tmp_dir_path / file.filename
            with open(tmp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            output_name = Path(file.filename).with_suffix(".md").name
            output_path = tmp_dir_path / output_name
            
            pasta_imagens = None
            if save_images:
                pasta_imagens = tmp_dir_path / f"{tmp_path.stem}_images"
            
            try:
                if ocr:
                    chars = converter_com_nougat(tmp_path, output_path, paginas)
                    images_count = 0
                else:
                    chars = converter_pdf(tmp_path, output_path, paginas, pasta_imagens)
                    images_count = 0
                    if pasta_imagens and pasta_imagens.exists():
                        manifest = pasta_imagens / "manifest.json"
                        if manifest.exists():
                            import json
                            with open(manifest) as f:
                                images_count = len(json.load(f))
                
                # Se tem imagens, cria ZIP individual
                download_url = f"/download/{output_name}"
                if images_count > 0 and pasta_imagens and pasta_imagens.exists():
                    zip_path = tmp_dir_path / f"{tmp_path.stem}_complete.zip"
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        md_path = tmp_dir_path / output_name
                        zf.write(md_path, output_name)
                        for img_file in pasta_imagens.glob("*"):
                            if img_file.name != "manifest.json":
                                zf.write(img_file, f"images/{img_file.name}")
                        manifest = pasta_imagens / "manifest.json"
                        if manifest.exists():
                            zf.write(manifest, "images/manifest.json")
                    download_url = f"/download-zip/{zip_path.name}" if images_count > 0 else f"/download/{output_name}"
                    zip_files.append(zip_path) if images_count > 0 else None
                
                result = ConvertResponse(
                    success=True,
                    filename=output_name,
                    chars=chars,
                    pages=len(paginas) if paginas else "all",
                    images_count=images_count,
                    download_url=download_url,
                )
                results.append(result)
                job["completed"] += 1
                
            except Exception as e:
                job["failed"] += 1
                result = ConvertResponse(
                    success=False,
                    filename=file.filename,
                    chars=0,
                    pages=0,
                    images_count=0,
                    download_url="",
                    message=f"Erro: {str(e)}"
                )
                results.append(result)
            finally:
                try:
                    tmp_path.unlink()
                except:
                    pass
        
        # Cria ZIP final com todos os resultados
        final_zip = tmp_dir_path / f"batch_{batch_id}_complete.zip"
        with zipfile.ZipFile(final_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for result in results:
                if result.success:
                    md_name = result.filename
                    md_path = tmp_dir_path / md_name
                    if md_path.exists():
                        zf.write(md_path, md_name)
                    # Adiciona imagens se houver
                    img_dir = tmp_dir_path / f"{Path(md_name).stem}_images"
                    if img_dir.exists():
                        for img_file in img_dir.glob("*"):
                            if img_file.name != "manifest.json":
                                zf.write(img_file, f"images/{img_file.name}")
        
        job["status"] = "completed"
        job["progress"] = 100
        job["current_file"] = None
        job["results"] = results
        job["zip_path"] = str(final_zip)
        batch_jobs[batch_id] = job


@app.get("/batch-status/{batch_id}", response_model=BatchStatusResponse)
async def batch_status(batch_id: str):
    """Consulta status de um batch"""
    if batch_id not in batch_jobs:
        raise HTTPException(404, "Batch não encontrado")
    
    job = batch_jobs[batch_id]
    return BatchStatusResponse(
        batch_id=batch_id,
        status=job["status"],
        progress=job["progress"],
        current_file=job["current_file"],
        results=job["results"],
        error=job["error"]
    )


@app.get("/batch-download/{batch_id}")
async def batch_download(batch_id: str):
    """Download do ZIP final do batch"""
    if batch_id not in batch_jobs:
        raise HTTPException(404, "Batch não encontrado")
    
    job = batch_jobs[batch_id]
    if job["status"] != "completed" or not job["zip_path"]:
        raise HTTPException(400, "Batch ainda não concluído")
    
    zip_path = Path(job["zip_path"])
    if not zip_path.exists():
        raise HTTPException(404, "ZIP não encontrado")
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"batch_{batch_id}_complete.zip"
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


# Serve static files from web folder at /web path
from fastapi.staticfiles import StaticFiles
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)