# exam2md — Provas em PDF viram Markdown com fórmulas em LaTeX

O **exam2md** transforma uma prova em PDF (EEAR/CFS, VUNESP, FGV, ENEM, concursos em geral) em um arquivo de texto **Markdown** que você pode editar, com:

- as questões e alternativas na ordem certa, mesmo em provas de duas colunas;
- **negrito**, *itálico*, <u>sublinhado</u> e quebras de linha preservados;
- fórmulas convertidas para **LaTeX** (`$\frac{2x}{1 - 2x}$`, `$\sqrt{3}$`, `$x^{2}$`);
- as **imagens** salvas em uma pasta, com o nome da questão em que aparecem.

Tudo roda **no seu computador**: nenhum arquivo é enviado para a internet. Funciona no Windows, macOS e Linux.

```
prova.pdf   →   prova.md               ← o texto da prova, com as fórmulas
                prova_images/
                  ├── prova_q05_1.png        ← figura da questão 05
                  ├── prova_q53_altB_1.png   ← figura da alternativa B da questão 53
                  └── prova_pag01_1.png      ← imagem antes da 1ª questão (capa)
```

---

## Instalação

Escolha **uma** das opções. A instalação leva de 2 a 5 minutos e precisa de internet só nessa hora.

### Opção 1 — Um comando (recomendado)

O instalador baixa o exam2md, instala o Python se precisar e cria um atalho na área de trabalho.

**Windows**

1. Aperte a tecla **Windows**, digite **PowerShell** e aperte **Enter**.
2. Cole o comando abaixo (botão direito do mouse cola) e aperte **Enter**:

```powershell
irm https://raw.githubusercontent.com/rphl05/exam2md/main/instalar.ps1 | iex
```

**macOS** — abra o app **Terminal** (Cmd+Espaço, digite "Terminal") e cole:

```bash
curl -fsSL https://raw.githubusercontent.com/rphl05/exam2md/main/instalar.sh | bash
```

**Linux** — abra um terminal e cole o mesmo comando:

```bash
curl -fsSL https://raw.githubusercontent.com/rphl05/exam2md/main/instalar.sh | bash
```

No fim, o exam2md abre sozinho no navegador. Os arquivos ficam na pasta **`exam2md`**, dentro da sua pasta de usuário.

> No macOS e no Linux, o Python 3.10+ precisa estar instalado. Se não estiver, o instalador avisa como instalar
> (macOS: [python.org/downloads](https://www.python.org/downloads/); Ubuntu/Debian: `sudo apt install python3 python3-venv`).

### Opção 2 — Baixar o ZIP (sem digitar comandos)

1. Instale o [Python](https://www.python.org/downloads/) (3.10 ou mais novo). **No Windows, marque a caixa "Add python.exe to PATH"** na primeira tela do instalador.
2. Nesta página do GitHub, clique no botão verde **Code** → **Download ZIP** e descompacte o arquivo.
3. Abra a pasta e dê dois cliques em:
   - **Windows:** `Iniciar.bat`
   - **macOS:** `Iniciar.command` (na primeira vez: botão direito → **Abrir** → **Abrir**)
   - **Linux:** `iniciar.sh`

Na primeira vez ele prepara tudo sozinho (de 1 a 3 minutos). Nas próximas, abre na hora.

---

## Como usar

### Pelo navegador

1. Abra o atalho **exam2md** (ou o `Iniciar` da pasta). Uma janela preta abre e o navegador mostra o exam2md.
   **Deixe a janela preta aberta** enquanto usar; feche quando terminar.
2. Arraste um ou mais PDFs para a área tracejada (ou clique nela para escolher).
3. Clique em **Converter** e acompanhe o progresso.
4. Clique em **Baixar**. Você recebe um `.zip` com o `prova.md` e a pasta de imagens. Também dá para copiar o texto direto da prévia.

| Opção | Para que serve |
|---|---|
| Extrair imagens | Salva as figuras da prova na pasta `prova_images/` (ligado por padrão) |
| Fórmulas em imagem → LaTeX | Para provas em que as fórmulas são figuras, sem texto selecionável. Na primeira vez, clique em **Instalar este recurso** (~1 GB) |
| Páginas | Converte só algumas páginas, ex.: `1-5, 8` |

### Arrastando sobre o atalho (Windows)

Arraste um ou mais PDFs sobre o atalho **exam2md - arraste PDFs aqui** (ou sobre o arquivo `Arraste PDFs aqui.bat`). O `.md` e a pasta de imagens são criados **ao lado de cada PDF**.

### Como abrir o arquivo `.md`

O `.md` é texto puro: abre até no Bloco de Notas. Para ver as fórmulas e as imagens formatadas, use um editor de Markdown:

- [Obsidian](https://obsidian.md) ou [Typora](https://typora.io): abrem com fórmulas e imagens prontas;
- [VS Code](https://code.visualstudio.com): abra o arquivo e aperte **Ctrl+Shift+V**.

Mantenha o `.md` **na mesma pasta** que `prova_images/`, senão as imagens não aparecem.

---

## Atualizar e desinstalar

- **Atualizar:** rode o comando de instalação de novo. Ele baixa a versão mais nova e mantém o que já foi instalado.
- **Desinstalar:** apague a pasta `exam2md` da sua pasta de usuário e os atalhos.

## Problemas comuns

| O que aparece | O que fazer |
|---|---|
| "Python não encontrado" | Instale pelo [python.org](https://www.python.org/downloads/) marcando **"Add python.exe to PATH"** e abra de novo. No Windows, o `Iniciar.bat` oferece instalar sozinho |
| Windows: aviso de segurança ao abrir o `Iniciar.bat` | Aparece em arquivos baixados da internet. Clique em **Executar** (ou **Mais informações** → **Executar assim mesmo**) |
| macOS: "não pode ser aberto porque é de um desenvolvedor não identificado" | Botão direito no arquivo → **Abrir** → **Abrir** |
| O navegador não abriu | Abra à mão o endereço mostrado na janela preta (ex.: `http://localhost:8000`) |
| Erro estranho depois de atualizar | Recarregue a página com **Ctrl+F5** (macOS: **Cmd+Shift+R**) |
| PDF escaneado (foto/scan, sem texto selecionável) | Sai quase vazio. Veja o modo `--ocr` em [Uso avançado](#uso-avançado) |
| Uma fórmula ficou como imagem mesmo com "Fórmulas em imagem" | É de propósito: quando o reconhecimento não é confiável (vários sistemas lado a lado, por exemplo), a imagem original é mantida para não gerar uma fórmula errada |

---

## O que o conversor preserva

| Elemento | Saída |
|---|---|
| Duas colunas | Lidas na ordem certa (esquerda, depois direita), com cabeçalho em largura total |
| Frações e radicais | `$\frac{2x}{1 - 2x}$`, `$\sqrt{3}$` |
| Sub/sobrescritos | `$x^{2}$`, `$H_{2}O$`; ordinais viram `1º`, `2ª` |
| Negrito / itálico | `**texto**`, `*texto*`, `***texto***` (pela fonte do PDF) |
| Sublinhado | `<u>termo</u>`, essencial em "assinale o termo sublinhado" |
| Lacunas `____` | `\_\_\_\_\_` (ex.: questões de crase) |
| Quebras de linha | Junta só as linhas quebradas pela margem; versos, listas, alternativas e parágrafos ficam separados |
| Hifenização | `apli-` + `cado` → `aplicado`; `pé-` + `-rapado` → `pé-rapado` |
| `R$` | Escapado como `R\$` para não virar fórmula |
| Imagens e figuras desenhadas | Recortadas como PNG na posição em que aparecem no texto, inclusive gráficos e figuras geométricas feitos com vetores |
| Tabelas | Linhas da tabela não são coladas num parágrafo |
| Cabeçalhos/rodapés repetidos | Removidos ("Confidencial até…", "Página 3", nome do concurso) |

As fórmulas usam `$...$` (no meio do texto) e `$$...$$` (em destaque), compatíveis com Obsidian, Typora, VS Code, KaTeX, MathJax, Jupyter e GitHub.

## Limitações conhecidas

- **Tabelas** saem como texto linha a linha, não como tabela Markdown.
- Caixas decorativas da capa podem sair como imagem.
- Mais de 2 colunas não são detectadas.
- O reconhecimento de fórmulas em imagem às vezes erra dígitos: confira o resultado.
- Uma figura compartilhada por várias questões ("Leia a tira para responder às questões 01 e 02") recebe o nome da questão anterior a ela.

---

## Uso avançado

### Linha de comando

Com o ambiente instalado (pasta `.venv`), use o Python dele: `.venv\Scripts\python` no Windows ou `.venv/bin/python` no macOS/Linux.

```bash
python reconstruir.py prova.pdf                  # prova.md + prova_images/
python reconstruir.py prova.pdf -o saida/p.md    # nome/pasta de saída
python reconstruir.py prova.pdf --pages 1,3-5    # só algumas páginas
python reconstruir.py prova.pdf --no-images      # sem extrair imagens
python reconstruir.py prova.pdf --hybrid         # fórmulas em imagem → LaTeX (pix2tex)
python reconstruir.py prova.pdf --ocr            # PDF escaneado (Nougat)

python exam2md_batch.py provas/ -o saida/        # lote: pasta inteira
python api.py --abrir                            # só o servidor web (porta 8000)
```

| Modo | Quando usar | Como funciona |
|---|---|---|
| Padrão | PDF digital (texto selecionável) | `pdfplumber` lê texto, fontes e vetores do PDF. ~0,5 s por página |
| `--hybrid` | Fórmulas como imagem ou desenho | Padrão + `pix2tex` nas imagens pequenas com cara de fórmula. Quando o resultado não é confiável (LaTeX malformado, vários blocos lado a lado, caixas), mantém a imagem e avisa no console. Instale com `python exam2md_launcher.py --instalar-formulas` |
| `--ocr` | PDF escaneado | Usa o [Nougat](https://github.com/facebookresearch/nougat) em um ambiente separado. Instale com `python exam2md_launcher.py --instalar-ocr` (~2 GB) |

### Opções do instalador

| Variável | Efeito |
|---|---|
| `EXAM2MD_DESTINO` | Instala em outra pasta (padrão: `~/exam2md`) |
| `EXAM2MD_NAO_ABRIR=1` | Não abre o exam2md no fim da instalação |

### API local

O servidor escuta só em `127.0.0.1` e apaga as conversões depois de 6 h.

```
POST /convert                 files=<pdf>[, ...]  pages="1,3-5"  extrair_imagens=true  formulas_imagem=false
                              → {"job_id": "..."}
GET  /jobs/{job_id}           status, progresso (%), resultados e prévia do Markdown
GET  /jobs/{job_id}/download  .md, ou .zip com prova.md + prova_images/
GET  /recursos                recursos opcionais instalados (fórmulas em imagem)
POST /recursos/formulas       instala o reconhecimento de fórmulas (pix2tex)
```

### Estrutura

```
Iniciar.bat / Iniciar.command / iniciar.sh   abrir com duplo clique
Arraste PDFs aqui.bat                         conversão direta, arrastando PDFs
instalar.ps1 / instalar.sh                    instaladores de um comando
exam2md_launcher.py   prepara o .venv, instala recursos opcionais e sobe o servidor
reconstruir.py        conversor (CLI e biblioteca: converter(pdf, md, paginas, pasta_imagens, ...))
api.py                servidor local (FastAPI) + interface em web/index.html
exam2md_batch.py      conversão em lote
```

## Licença

MIT.
