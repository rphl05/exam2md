# exam2md — Prova em PDF para Markdown com LaTeX

Converte provas em PDF (EEAR/CFS, VUNESP, FGV, ENEM, concursos) para **Markdown com fórmulas em LaTeX** e uma pasta de imagens nomeadas pela questão em que aparecem. Roda 100% no seu computador, em Windows, Linux e macOS.

```
prova.pdf  →  prova.md
              prova_images/
                ├── prova_q05_1.png        (figura da questão 05)
                ├── prova_q53_altB_1.png   (figura da alternativa B da questão 53)
                ├── prova_pag01_1.png      (antes da 1ª questão: capa, instruções)
                └── manifest.json          (questão, alternativa, página e posição de cada imagem)
```

## Como abrir (duplo clique)

| Sistema | Arquivo | O que faz |
|---|---|---|
| Windows | `exam2md_web.bat` | Prepara o ambiente na 1ª vez e abre a interface no navegador |
| Windows | `exam2md_rapido.bat` | **Arraste um ou mais PDFs** sobre ele → gera `.md` + imagens ao lado do PDF |
| macOS | `exam2md.command` | Abre a interface no navegador |
| Linux | `run.sh` | Abre a interface no navegador |
| Qualquer | `python exam2md_launcher.py` | O mesmo, pela linha de comando |

Requisito único: [Python 3.10+](https://python.org/downloads) (no Windows, marque *Add Python to PATH*). Na primeira execução o launcher cria o `.venv` e instala as dependências.

> macOS/Linux: se o duplo clique não executar, rode uma vez `chmod +x exam2md.command run.sh`.

Na interface: arraste os PDFs, escolha as opções e clique em **Converter**. Você vê o progresso por página, uma prévia do Markdown e baixa um `.zip` com `prova.md` + `prova_images/` (ou só o `.md`, quando não há imagens).

## Linha de comando

```bash
python reconstruir.py prova.pdf                  # prova.md + prova_images/
python reconstruir.py prova.pdf -o saida/p.md    # nome/pasta de saída
python reconstruir.py prova.pdf --pages 1,3-5    # só algumas páginas
python reconstruir.py prova.pdf --no-images      # sem extrair imagens
python reconstruir.py prova.pdf --hybrid         # fórmulas em IMAGEM → LaTeX (pix2tex)
python reconstruir.py prova.pdf --ocr            # PDF escaneado (Nougat)

python exam2md_batch.py provas/ -o saida/        # lote: pasta inteira ou *.pdf
python api.py --abrir                            # só o servidor web (porta 8000)
```

## O que o conversor preserva

| Elemento | Saída |
|---|---|
| Duas colunas | Lidas na ordem certa (esquerda, depois direita), com cabeçalho em largura total |
| Frações e radicais vetoriais | `$\frac{2x}{1 - 2x}$`, `$\sqrt{3}$` |
| Sub/sobrescritos | `$x^{2}$`, `$H_{2}O$`; ordinais viram `1º`, `2ª` |
| Negrito / itálico | `**texto**`, `*texto*`, `***texto***` (pela fonte do PDF) |
| Sublinhado | `<u>termo</u>` — essencial em "assinale o termo sublinhado" |
| Lacunas `____` | `\_\_\_\_\_` (ex.: questões de crase) |
| Quebras de linha | Junta só as linhas quebradas pela margem; versos, listas, alternativas e parágrafos ficam separados |
| Hifenização | `apli-` + `cado` → `aplicado`; `pé-` + `-rapado` → `pé-rapado` |
| `R$` | Escapado como `R\$` para não abrir modo matemático |
| Imagens | Recortadas como PNG reais na posição em que aparecem no texto |
| Figuras e fórmulas **vetoriais** | Figuras geométricas, gráficos e fórmulas desenhadas com curvas (sem texto selecionável) viram imagem — inline quando estão no meio da frase ou ao lado de "(A)" |
| Tabelas | Linhas da tabela não são coladas num parágrafo; traços de grade não viram fração |
| Cabeçalhos/rodapés repetidos | Removidos ("Confidencial até…", "Página 3", nome do concurso) |

As fórmulas usam `$...$` (inline) e `$$...$$` (bloco), compatíveis com KaTeX, MathJax, Obsidian, Typora, Jupyter e GitHub.

## Modos

| Modo | Quando usar | Como funciona |
|---|---|---|
| Padrão | PDF digital (texto selecionável) | `pdfplumber`: texto, fontes e vetores do PDF. Rápido (~0,5 s/página) |
| `--hybrid` | Fórmulas como **imagem** ou **desenho vetorial** | Padrão + `pix2tex` nas imagens pequenas com cara de fórmula; o LaTeX entra no lugar da imagem (inline ou `$$`). Sem `--hybrid`, essas fórmulas ficam como imagem. Instale com `pip install pix2tex` (o modelo leva ~40 s para carregar); confira o resultado, o OCR erra dígitos às vezes. Quando o resultado não é confiável — LaTeX malformado, vários blocos lado a lado (ex.: três sistemas `{` em sequência) ou caixas de formulário — a fórmula fica como imagem e o console avisa |
| `--ocr` | PDF **escaneado** | Chama o CLI do [Nougat](https://github.com/facebookresearch/nougat) instalado em `.venv-nougat` (`python install_nougat.py` ou `python exam2md_launcher.py --instalar-ocr`) |

## Instalação manual

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install pix2tex        # opcional, para --hybrid
```

## Estrutura

```
reconstruir.py        conversor (CLI e biblioteca: converter(pdf, md, paginas, pasta_imagens, ...))
api.py                servidor local (FastAPI) + interface em web/index.html
exam2md_launcher.py   launcher multiplataforma (cria .venv, sobe servidor, abre navegador)
exam2md_batch.py      conversão em lote
exam2md_web.bat / exam2md_rapido.bat / exam2md.command / run.sh   atalhos de duplo clique
```

### API

```
POST /convert                 files=<pdf>[, ...]  pages="1,3-5"  extrair_imagens=true  formulas_imagem=false
                              → {"job_id": "..."}
GET  /jobs/{job_id}           status, progresso (%), resultados e prévia do Markdown
GET  /jobs/{job_id}/download  .md, ou .zip com prova.md + prova_images/
```

O servidor escuta só em `127.0.0.1` e apaga conversões com mais de 6 h.

## Limitações conhecidas

- **Tabelas** saem como texto linha a linha, não como tabela Markdown.
- Caixas decorativas da capa (campos de formulário com conteúdo) podem sair como imagem.
- Mais de 2 colunas, ou colunas que voltam a largura total no meio da página, não são detectadas.
- A imagem é nomeada pela última questão vista antes dela; uma figura compartilhada ("Leia a tira para responder às questões 01 e 02") que venha antes do número recebe o nome da questão anterior.
- Palavras hifenizadas no fim de uma coluna e continuadas na outra não são reunidas.

## Licença

MIT.
