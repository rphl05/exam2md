"""FastAPI wrapper for exam2md - Prova to Markdown converter."""

import tempfile
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reconstruir import converter_pdf

app = FastAPI(
    title="exam2md - Prova to Markdown",
    description="Converte PDFs de provas (EEAR, IF, ENEM, etc.) para Markdown com fórmulas LaTeX",
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
    download_url: str
    message: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "exam2md"}


@app.post("/convert", response_model=ConvertResponse)
async def convert_pdf_endpoint(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),  # "1,2,3" or "1-5"
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
        output_path = tmp_path.with_suffix(".md")

        chars = converter_pdf(tmp_path, output_path, paginas)

        return ConvertResponse(
            success=True,
            filename=output_name,
            chars=chars,
            pages=len(paginas) if paginas else "all",
            download_url=f"/download/{output_name}",
        )
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
    # Files are stored in temp dir with same name
    temp_dir = Path(tempfile.gettempdir())
    file_path = temp_dir / filename
    if not file_path.exists():
        raise HTTPException(404, "Arquivo não encontrado ou expirado")
    return FileResponse(
        file_path,
        media_type="text/markdown",
        filename=filename,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)