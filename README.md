# exam2md — Prova para Markdown com LaTeX

Converte PDFs de provas (EEAR, IF, ENEM, Fuvest, VUNESP, concursos militares, etc.) para **Markdown com fórmulas em LaTeX**, 100% local, sem IA, sem nuvem.

## ✨ Features

- **100% local** — roda na sua máquina (CPU), sem API key, sem upload para nuvem
- **Fórmulas em LaTeX** — frações `\frac{...}{...}`, raízes `\sqrt{...}`, subscritos/sobrescritos `_{...}` `^{...}`, matrizes
- **Auto-nome** — `prova.pdf` → `prova.md` automaticamente
- **Extração de imagens** — `--save-images` salva imagens em pasta + `manifest.json` com metadados
- **OCR Nougat** — `--ocr` para PDFs escaneados (requer ambiente separado)
- **Processamento em lote** — múltiplos PDFs em sequência (CLI + API)
- **Interface web** — drag & drop, barra de progresso, download direto
- **Páginas seletivas** — `--pages 1,3-5,10` ou pela web
- **Rápido** — ~5 s para prova de 18 páginas (i7-3770, 8 GB RAM)
- **Formatos suportados** — EEAR/CFS (a-d), VUNESP (A-E), ENEM, Fuvest, concursos militares

## 📦 Instalação

```bash
# 1. Clone
git clone https://github.com/rphl05/exam2md.git
cd exam2md

# 2. Crie venv e instale deps
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

## 🚀 Uso Rápido (3 formas)

### 1. 🎯 Mais Simples: Drag & Drop (Windows)
```bat
# Arraste seu prova.pdf sobre exam2md_rapido.bat
# → Gera prova.md + pasta prova_images/
```

### 2. 🖥️ Interface Web (Recomendado)
```bash
# Terminal 1: API
python api.py
# → http://localhost:8000

# Terminal 2 (opcional): Frontend
# ou abra web/index.html direto no navegador
```

### 3. 💻 CLI Direto
```bash
# Auto-nome: prova.pdf → prova.md
python reconstruir.py prova.pdf

# Com imagens
python reconstruir.py prova.pdf --save-images

# Pasta customizada para imagens
python reconstruir.py prova.pdf --save-images --images-dir ./minhas_imagens

# OCR para PDFs escaneados
python reconstruir.py prova_escaneada.pdf --ocr

# **NOVO: Modo híbrido (pdfplumber + pix2tex para fórmulas bitmap)**
python reconstruir.py prova.pdf --hybrid
python reconstruir.py prova.pdf --hybrid --save-images

# Apenas páginas específicas
python reconstruir.py prova.pdf --pages 1,3-5,10
```

### 4. 📦 Processamento em Lote (Batch)
```bash
# Múltiplos PDFs
python exam2md_batch.py *.pdf

# Com imagens
python exam2md_batch.py *.pdf --save-images

# Pasta de saída customizada
python exam2md_batch.py provas/*.pdf -o saida/

# Com OCR
python exam2md_batch.py *.pdf --ocr

# Relatório JSON
python exam2md_batch.py *.pdf --relatorio relatorio.json
```

### 5. 🌐 API - Upload em Lote
```bash
# Inicia API
python api.py
# → http://localhost:8000
```

**Upload em lote:**
```bash
POST /convert-batch
  files: [file1.pdf, file2.pdf, ...]
  pages: "1,3-5"
  save_images: true
  ocr: false
```

**Acompanha progresso:**
```
GET /batch-status/abc12345
```

**Download final (ZIP com todos):**
```
GET /batch-download/abc12345
```

## 🖥️ Launchers (Multiplataforma)

| Arquivo | Plataforma | Como Usa |
|---------|------------|----------|
| `exam2md_launcher.py` | **Linux, macOS, Windows** | `python exam2md_launcher.py` (compilável `.exe`/binário) |
| `exam2md_launcher.bat` | Windows | Duplo clique (menu interativo) |
| `exam2md.vbs` | Windows | Duplo clique (fixável na barra de tarefas) |
| `exam2md_web.bat` | Windows | **Duplo clique → abre navegador** (mais simples) |
| `exam2md_rapido.bat` | Windows | **Arraste PDF em cima** → gera `.md` |
| `exam2md.bat` | Windows | Menu interativo (1=simples, 2=imagens, 3=OCR, 4=Web) |
| `exam2md_batch.bat` | Windows | Menu para processamento em lote |
| `install_nougat.py` | **Linux, macOS, Windows** | `python install_nougat.py` (instalador OCR cross-platform) |
| `install_nougat.bat` | Windows | Duplo clique → instala Nougat OCR |

**Linux/macOS:** Use os arquivos `.py` diretamente (`python exam2md_launcher.py`).
**Windows:** Use `.bat`, `.vbs` ou `.py` — todos funcionam.

### 🐧🍎 Suporte Linux e macOS

A **lógica principal** (`reconstruir.py`, `api.py`, `exam2md_batch.py`, `exam2md_launcher.py`, `install_nougat.py`) é **100% Python puro** e roda em Linux, macOS e Windows.

| Componente | Linux | macOS | Windows |
|------------|-------|-------|---------|
| Core (`reconstruir.py`, `api.py`, `exam2md_batch.py`) | ✅ | ✅ | ✅ |
| API Web (`api.py` + `web/index.html`) | ✅ | ✅ | ✅ |
| OCR Nougat | ✅ | ✅ (ARM64 nativo M1/M2/M3) | ✅ |
| Launchers `.bat` | ❌ | ❌ | ✅ |
| Launchers `.vbs` | ❌ | ❌ | ✅ |
| Launchers `.py` | ✅ | ✅ | ✅ |

### No Linux / macOS

```bash
# Instalação
git clone https://github.com/rphl05/exam2md.git
cd exam2md
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# CLI direto
python reconstruir.py prova.pdf --save-images

# Batch
python exam2md_batch.py *.pdf --save-images

# OCR (requer install_nougat.py antes)
python reconstruir.py prova.pdf --ocr

# Web
python api.py  # → http://localhost:8000

# Instalador Nougat (cross-platform)
python install_nougat.py

# Launcher
python exam2md_launcher.py
```

### Build nativo (Linux/macOS)
```bash
# Linux
pyinstaller --onefile --name exam2md exam2md_launcher.py

# macOS (binário)
pyinstaller --onefile --name exam2md exam2md_launcher.py

# macOS App nativo
pyinstaller --onefile --windowed --name exam2md exam2md_launcher.py
```

### Compilar Executáveis (Multiplataforma)

```bash
pip install pyinstaller

# Linux (binário ELF)
pyinstaller --onefile --name exam2md exam2md_launcher.py
# → dist/exam2md (binário ELF)

# macOS (binário Mach-O)
pyinstaller --onefile --name exam2md exam2md_launcher.py
# → dist/exam2md (Mach-O 64-bit)

# macOS (App nativo .app com ícone no Dock)
pyinstaller --onefile --windowed --name exam2md exam2md_launcher.py
# → dist/exam2md.app

# Windows (executável .exe)
pyinstaller --onefile --noconsole exam2md_launcher.py
# → dist/exam2md.exe
```

**Build automático multi-plataforma:** Use GitHub Actions (`.github/workflows/build.yml`) para gerar Linux, macOS e Windows a cada push.

## 📂 Estrutura do Projeto

```
exam2md/
├── reconstruir.py          # CLI principal (pdfplumber + LaTeX)
├── exam2md_batch.py        # CLI batch processing
├── api.py                  # FastAPI wrapper (/convert, /convert-batch, /batch-status, /download)
├── web/index.html          # Interface drag & drop
├── exam2md_web.bat         # Launcher web (duplo clique)
├── exam2md_launcher.py     # Launcher Python (compilável .exe)
├── exam2md_launcher.bat    # Launcher batch
├── exam2md.vbs             # Launcher VBScript
├── exam2md_rapido.bat      # Drag & drop rápido
├── exam2md.bat             # Menu interativo
├── exam2md_batch.bat       # Batch wrapper
├── requirements.txt
├── run.bat / run.sh
├── .gitignore
├── GUIA_USUARIO.md
└── README.md
```

7. **Extrai imagens** — salva PNGs + `manifest.json` com metadados

## 🔀 Modo Híbrido (`--hybrid`)

O modo híbrido combina o melhor dos dois mundos:

| Modo | Texto/Vetores | Fórmulas Bitmap |
|------|---------------|-----------------|
| Padrão (`pdfplumber`) | ✅ Perfeito | ❌ Não detecta |
| OCR Nougat (`--ocr`) | ✅ | ✅ (lento) |
| **Híbrido (`--hybrid`)** | ✅ (pdfplumber) | ✅ (pix2tex) |

### Como funciona:
1. **pdfplumber** extrai texto, vetores, frações, radicais, subscritos/sobrescritos
2. **Detecta regiões de fórmula bitmap** (imagens/vetores que o pdfplumber não lê)
3. **Extrai regiões** como imagens PIL
4. **pix2tex OCR** converte bitmap → LaTeX
4. **Insere LaTeX** no markdown (`$$...$$` ou `$...$`)

### Uso:
```bash
# Modo híbrido (recomendado para PDFs com fórmulas bitmap)
python reconstruir.py prova.pdf --hybrid

# Com extração de imagens
python reconstruir.py prova.pdf --hybrid --save-images

# Páginas específicas
python reconstruir.py prova.pdf --hybrid --pages 1,3-5,10
```

### Quando usar `--hybrid`:
- ✅ PDFs com fórmulas renderizadas como **imagens bitmap** (não texto vetorial)
- ✅ PDFs gerados por alguns editores (Word, Google Docs exportados)
- ✅ PDFs escaneados de alta qualidade
- ❌ PDFs puramente vetoriais (use modo padrão)
- ❌ PDFs escaneados de baixa qualidade (use `--ocr`)

### Exemplo de saída:
```markdown
25 – Se sen 20° = x, então tg 40° = ___________.
a) \frac{2 \sqrt{1− x^{2}}}{1− 2x}
b) \frac{2x \sqrt{1− x^{2}}}{1− 2x}
c) \frac{2 \sqrt{1− x^{2}}}{1− 2x^{2}}
d) \frac{2x \sqrt{1− x^{2}}}{1− 2x^{2}}
```

**Detectado em testes:** 11 frações, 3 raízes, 9 sobrescritos, 23 subscritos.

Pipeline **determinístico** com `pdfplumber`:

1. **Detecta colunas** pela linha vertical central
2. **Agrupa linhas** por posição vertical (âncoras de todos os chars)
3. **Classifica sub/sobrescrito** pelo deslocamento relativo à linha de base
4. **Detecta frações** por barras vetoriais horizontais (espessura ~0,5)
5. **Detecta radicais** por curvas vetoriais em "V" com barra superior
6. **Traduz glifos Symbol** (área privada Unicode U+F0xx → LaTeX)
6. **Corrige quebras de linha** — junta parágrafos, conserta hifenização
7. **Extrai imagens** — salva PNGs + `manifest.json` com metadados

## 📋 Exemplo de Saída

```markdown
25 – Se sen 20° = x, então tg 40° = ___________.
a) \frac{2 \sqrt{1− x^{2}}}{1− 2x}
b) \frac{2x \sqrt{1− x^{2}}}{1− 2x}
c) \frac{2 \sqrt{1− x^{2}}}{1− 2x^{2}}
d) \frac{2x \sqrt{1− x^{2}}}{1− 2x^{2}}

27 – Seja ABC um triângulo isósceles, com Â = 120° e
BC = 2 \sqrt{3} cm.
```

### Extração de Imagens
```
prova_images/
├── manifest.json          # Metadados (página, x, y, largura, altura)
├── page1_1_img1.png
├── page2_3_img1.png
└── ...
```

## ⚠️ Limitações

| Cenário | Status |
|---------|--------|
| PDF digital (texto vetorial) | ✅ Perfeito |
| PDF escaneado (imagem) | ⚠️ Use `--ocr` (Nougat) |
| Fórmulas como bitmap | ❌ Não suportado |
| Múltiplas colunas (>2) | ❌ Não detecta |

**VUNESP**: Alternativas (B)-(E) podem faltar devido a limitação do pdfplumber — use `--ocr` para PDFs escaneados.

### 🔧 Melhorias Recentes (v2024.11)

- **Correção de loop infinito** no pós-processamento (`pos_processar_prova`) — adicionado contador global de operações (50.000 max) com verificações `check_ops()` em todos os laços
- **Detecção de colunas robusta** — retorno antecipado quando `x_div is None` (páginas sem layout de duas colunas)
- **Correção de bug em step 6/7** — uso correto de `linhas_processadas` em vez de `saida` para evitar loop infinito ao processar cada linha
- **Processamento de 24 páginas** do PDF VUNESP de teste concluído em ~5.5s sem timeouts

**Nota**: Palavras hifenizadas divididas entre colunas (ex: "estabe" + "lece" = "estabelece") são uma limitação conhecida de PDFs de duas colunas.

Para PDFs escaneados: use `--ocr` (requer `pip install nougat-ocr` em ambiente com `transformers 4.x`).

## 📄 Licença

MIT — use livremente, inclusive comercialmente.

---

**Desenvolvido para automatizar extração de provas EEAR/IF/ENEM/VUNESP/Fuvest** — PRs bem-vindos!