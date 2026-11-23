#!/usr/bin/env python
"""exam2md - Prova para Markdown com LaTeX + Imagens + OCR Nougat.

Uso:
    python reconstruir.py prova.pdf                           # gera prova.md + pasta prova_images/
    python reconstruir.py prova.pdf -o saida.md               # nome customizado
    python reconstruir.py prova.pdf --pages 1,3-5             # páginas específicas
    python reconstruir.py prova.pdf --ocr                     # usa Nougat OCR (para PDFs escaneados)
    python reconstruir.py prova.pdf --save-images             # extrai imagens para pasta
    python reconstruir.py prova.pdf --ocr --save-images       # ambas

Pipeline:
  1. PDF digital (texto vetorial) -> pdfplumber (rápido, 100% local)
  2. PDF escaneado (imagem) -> Nougat OCR (preciso, requer GPU/CPU)
  3. Imagens -> salvas em pasta ao lado do PDF/Markdown

Requisitos Nougat: pip install nougat-ocr (requer transformers 4.x, torch)
"""

import argparse
import sys
import shutil
from pathlib import Path
from typing import Optional, List

from pdfplumber import open as pdf_open

# ---- constants & helpers ----
SIMBOLOS = {
    0xF028: "(", 0xF029: ")", 0xF02B: "+", 0xF02D: "−",
    0xF03D: "=", 0xF0B7: "·",
    0xF0E6: "⎛", 0xF0E7: "⎜", 0xF0E8: "⎝",
    0xF0F6: "⎞", 0xF0F7: "⎟", 0xF0F8: "⎠",
}
ABRE_COLCHETE = "⎛⎜⎝"
FECHA_COLCHETE = "⎞⎟⎠"
ESPACO_RELATIVO = 0.17

import collections
import statistics


def normalizar(texto: str) -> str:
    return "".join(SIMBOLOS.get(ord(c), c) for c in texto)


def tamanho_corpo(chars):
    contagem = collections.Counter(round(ch["size"], 1) for ch in chars)
    return contagem.most_common(1)[0][0]


def achar_divisoria(pagina, chars):
    candidatas = [
        linha for linha in pagina.lines
        if (linha["x1"] - linha["x0"]) < 2 and (linha["bottom"] - linha["top"]) > 200
    ]
    if candidatas:
        melhor = min(candidatas, key=lambda l: abs(l["x0"] - pagina.width / 2))
        return melhor["x0"], melhor["top"], melhor["bottom"]

    faixas = 60
    passo = pagina.width / faixas
    ocupacao = [0] * faixas
    for ch in chars:
        centro = (ch["x0"] + ch["x1"]) / 2
        indice = min(faixas - 1, max(0, int(centro / passo)))
        ocupacao[indice] += 1

    melhor_inicio, melhor_tamanho, atual = None, 0, 0
    for i in range(int(faixas * 0.3), int(faixas * 0.7)):
        if ocupacao[i] == 0:
            atual += 1
            if atual > melhor_tamanho:
                melhor_tamanho, melhor_inicio = atual, i - atual + 1
        else:
            atual = 0
    if melhor_tamanho < 4:
        return None
    x = (melhor_inicio + melhor_tamanho / 2) * passo
    return x, 0.0, pagina.height


def agrupar_linhas(chars, corpo):
    ancoras = []
    for top in sorted(ch["top"] for ch in chars):
        if not ancoras or top - ancoras[-1] > 0.45 * corpo:
            ancoras.append(top)
        else:
            ancoras[-1] = 0.85 * ancoras[-1] + 0.15 * top

    linhas = [[] for _ in ancoras]
    for ch in chars:
        melhor_i, melhor_d = 0, None
        for i, ancora in enumerate(ancoras):
            d = abs(ch["top"] - ancora)
            if melhor_d is None or d < melhor_d:
                melhor_i, melhor_d = i, d
        linhas[melhor_i].append(ch)

    saida = [(ancora, itens) for ancora, itens in zip(ancoras, linhas) if itens]
    saida.sort(key=lambda par: par[0])
    return saida


def linha_de_base(itens, corpo):
    normais = [ch for ch in itens if ch["size"] >= 0.9 * corpo]
    if not normais:
        normais = itens
    base = statistics.median(ch["bottom"] for ch in normais)
    return base, corpo


def classificar(ch, base, tamanho):
    if ch["size"] >= 0.82 * tamanho:
        return None
    deslocamento = ch["bottom"] - base
    if 0.5 < deslocamento <= 0.5 * tamanho:
        return "sub"
    if -0.6 * tamanho <= deslocamento < -1.0:
        return "sup"
    return None


def montar_texto(itens, corpo):
    if not itens:
        return ""
    base, tamanho = linha_de_base(itens, corpo)

    partes = []
    script = None
    buffer_script = []
    anterior = None

    def fechar():
        nonlocal script, buffer_script
        if script and buffer_script:
            marcador = "_" if script == "sub" else "^"
            partes.append(f"{marcador}{{{''.join(buffer_script)}}}")
        script = None
        buffer_script = []

    for ch in itens:
        texto = ch["text"]
        if not texto:
            continue
        if texto in ABRE_COLCHETE or texto in FECHA_COLCHETE:
            continue

        classe = classificar(ch, base, tamanho)
        if classe != script:
            fechar()
            script = classe

        if classe:
            buffer_script.append(texto)
            anterior = ch
            continue

        if anterior is not None:
            vao = ch["x0"] - anterior["x1"]
            if vao > ESPACO_RELATIVO * corpo and partes and not partes[-1].endswith(" "):
                partes.append(" ")
        partes.append(texto)
        anterior = ch

    fechar()
    return "".join(partes).strip()


def achar_radicais(pagina):
    radicais = []
    for curva in pagina.curves:
        caminho = curva.get("path") or []
        if len(caminho) != 3:
            continue
        if caminho[0][0] != "m" or caminho[1][0] != "l" or caminho[2][0] != "l":
            continue
        inicio, meio, fim = caminho[0][1], caminho[1][1], caminho[2][1]
        altura = curva["bottom"] - curva["top"]
        if not (5.0 <= altura <= 18.0):
            continue
        if not (inicio[1] > meio[1] and abs(fim[1] - meio[1]) < 0.6):
            continue
        if not (fim[0] > meio[0] > inicio[0]):
            continue
        radicais.append({
            "x0": inicio[0], "x1": meio[0],
            "barra_ini": meio[0], "barra_fim": fim[0],
            "y": curva["bottom"] - 1.5,
            "radical": True,
        })
    return radicais


def achar_fracoes(pagina, chars):
    barras = [
        linha for linha in pagina.lines
        if linha["height"] < 1.2
        and 3.0 <= (linha["x1"] - linha["x0"]) <= 45.0
        and (linha.get("linewidth") or 0) >= 0.45
    ]

    fracoes = []
    for barra in barras:
        x0, x1 = barra["x0"] - 1.5, barra["x1"] + 1.5
        y = barra["top"]

        numerador = [
            ch for ch in chars
            if x0 <= (ch["x0"] + ch["x1"]) / 2 <= x1 and y - 14 <= ch["bottom"] <= y + 0.8
        ]
        denominador = [
            ch for ch in chars
            if x0 <= (ch["x0"] + ch["x1"]) / 2 <= x1 and y - 0.8 <= ch["top"] <= y + 14
        ]
        if not numerador or not denominador:
            continue
        if max(ch["bottom"] for ch in numerador) > y + 1:
            continue
        if min(ch["top"] for ch in denominador) < y - 1:
            continue

        fracoes.append({
            "x0": barra["x0"], "x1": barra["x1"], "y": y,
            "numerador": sorted(numerador, key=lambda c: c["x0"]),
            "denominador": sorted(denominador, key=lambda c: c["x0"]),
        })
    return fracoes


def juntar_numeros_de_questao(linhas):
    saida = []
    i = 0
    while i < len(linhas):
        if (
            i + 1 < len(linhas)
            and linhas[i].isdigit()
            and len(linhas[i]) <= 2
            and linhas[i + 1].startswith("–")
        ):
            saida.append(f"{linhas[i]} {linhas[i + 1]}")
            i += 2
            continue
        saida.append(linhas[i])
        i += 1
    return saida


def renderizar_tokens(tokens, corpo, base=None, tamanho=None):
    if not tokens:
        return ""

    tokens = sorted(tokens, key=lambda t: t["x0"])
    chars = [t for t in tokens if t.get("text") and "size" in t]
    if base is None or tamanho is None:
        if chars:
            base, tamanho = linha_de_base(chars, corpo)
        else:
            base, tamanho = 0.0, corpo

    partes = []
    script = None
    buffer_script = []
    anterior = None

    def fechar():
        nonlocal script, buffer_script
        if script and buffer_script:
            marcador = "_" if script == "sub" else "^"
            partes.append(f"{marcador}{{{''.join(buffer_script)}}}")
        script = None
        buffer_script = []

    def espaco_antes(x0, texto_atual=""):
        nonlocal anterior
        if anterior is None:
            return
        vao = x0 - anterior["x1"]
        limite = ESPACO_RELATIVO
        anterior_texto = anterior.get("text", "") or ""
        if (
            anterior_texto
            and texto_atual
            and anterior_texto[-1].isalnum()
            and texto_atual[0].isalnum()
        ):
            limite = 0.30
        if vao > limite * corpo and partes and not partes[-1].endswith(" "):
            partes.append(" ")

    for token in tokens:
        if "numerador" in token:
            fechar()
            espaco_antes(token["x0"])
            num = renderizar_tokens(
                token["numerador"] + token.get("radicais_num", []), corpo
            )
            den = renderizar_tokens(
                token["denominador"] + token.get("radicais_den", []), corpo
            )
            partes.append(f"\\frac{{{num}}}{{{den}}}")
            anterior = token
            continue

        if token.get("radical"):
            fechar()
            espaco_antes(token["x0"])
            partes.append(f"\\sqrt{{{token['radicando']}}}")
            anterior = token
            continue

        texto = token["text"]
        if not texto:
            continue
        if texto in ABRE_COLCHETE or texto in FECHA_COLCHETE:
            continue

        classe = classificar(token, base, tamanho)
        if classe != script:
            fechar()
            script = classe

        if classe:
            buffer_script.append(texto)
            anterior = token
            continue

        espaco_antes(token["x0"], texto)
        partes.append(texto)
        anterior = token

    fechar()
    return "".join(partes).strip()


def renderizar_coluna(chars, corpo, fracoes, radicais):
    linhas = agrupar_linhas(chars, corpo)
    linhas.sort(key=lambda par: par[0])

    consumidos = set()
    extras = {}

    for radical in radicais:
        candidatos = [
            ch for ch in chars
            if radical["barra_ini"] - 0.6
            <= (ch["x0"] + ch["x1"]) / 2
            <= radical["barra_fim"] + 0.6
            and abs(ch["bottom"] - radical["y"]) <= 9
        ]
        radical["chars_radicando"] = sorted(candidatos, key=lambda c: c["x0"])

    for fracao in fracoes:
        consumidos_fracao = {id(ch) for ch in fracao["numerador"] + fracao["denominador"]}
        candidatas = []
        for indice, (_ancora, itens) in enumerate(linhas):
            topo = min(ch["top"] for ch in itens)
            base = max(ch["bottom"] for ch in itens)
            if topo - 0.5 <= fracao["y"] <= base + 0.5:
                normais = sum(1 for ch in itens if id(ch) not in consumidos_fracao)
                candidatas.append((normais, indice))
        if candidatas:
            hospedeira = max(candidatas)[1]
        else:
            melhor = None
            for indice, (_ancora, itens) in enumerate(linhas):
                centro = (
                    min(ch["top"] for ch in itens) + max(ch["bottom"] for ch in itens)
                ) / 2
                d = abs(centro - fracao["y"])
                if melhor is None or d < melhor[1]:
                    melhor = (indice, d)
            if melhor is None:
                continue
            hospedeira = melhor[0]
        extras.setdefault(hospedeira, []).append(fracao)
        for ch in fracao["numerador"] + fracao["denominador"]:
            consumidos.add(id(ch))

    pendentes = []
    for radical in radicais:
        ids_rad = {id(ch) for ch in radical["chars_radicando"]}
        destino = None
        for fracao in fracoes:
            ids_num = {id(ch) for ch in fracao["numerador"]}
            ids_den = {id(ch) for ch in fracao["denominador"]}
            if ids_rad and ids_rad <= ids_num:
                fracao.setdefault("radicais_num", []).append(radical)
                destino = "num"
                break
            if ids_rad and ids_rad <= ids_den:
                fracao.setdefault("radicais_den", []).append(radical)
                destino = "den"
                break
        if destino is None:
            pendentes.append(radical)
        else:
            radical["radicando"] = renderizar_tokens(radical["chars_radicando"], corpo)
            for ch in radical["chars_radicando"]:
                consumidos.add(id(ch))

    for radical in pendentes:
        contagem = collections.Counter()
        for indice, (_ancora, itens) in enumerate(linhas):
            ids = {id(ch) for ch in itens}
            contagem[indice] = sum(1 for ch in radical["chars_radicando"] if id(ch) in ids)
        if not contagem:
            continue
        indice_linha, qtd = max(contagem.items(), key=lambda par: par[1])
        if qtd == 0:
            continue
        radical["radicando"] = renderizar_tokens(radical["chars_radicando"], corpo)
        for ch in radical["chars_radicando"]:
            consumidos.add(id(ch))
        extras.setdefault(indice_linha, []).append(radical)

    resultado = []
    for indice, (_ancora, itens) in enumerate(linhas):
        tokens = [ch for ch in itens if id(ch) not in consumidos]
        tokens.extend(extras.get(indice, []))
        if not tokens:
            continue
        texto = renderizar_tokens(tokens, corpo, *linha_de_base(itens, corpo))
        if texto:
            resultado.append(texto)

    return juntar_numeros_de_questao(resultado)


def extrair_imagens(pagina, pasta_saida: Path, prefixo: str = "page") -> List[dict]:
    """Extrai imagens da página e salva na pasta. Retorna lista de metadados."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    resultados = []
    
    for idx, img in enumerate(pagina.images):
        try:
            # pdfplumber retorna dict com 'stream', 'width', 'height', etc.
            stream = img.get("stream")
            if not stream:
                continue
            
            # Gera nome único
            ext = ".png"  # pdfplumber extrai como PNG
            nome = f"{prefixo}_{pagina.page_number}_img{idx+1}{ext}"
            caminho = pasta_saida / nome
            
            # Salva a imagem
            with open(caminho, "wb") as f:
                f.write(stream.get_data())
            
            resultados.append({
                "arquivo": nome,
                "caminho": str(caminho),
                "pagina": pagina.page_number,
                "x": img.get("x0", 0),
                "y": img.get("top", 0),
                "largura": img.get("width", 0),
                "altura": img.get("height", 0),
            })
        except Exception as e:
            print(f"[aviso] Falha ao extrair imagem {idx}: {e}", file=sys.stderr)
    
    return resultados


def processar_pagina(pagina, pasta_imagens: Optional[Path] = None) -> tuple:
    """Processa uma página. Retorna (texto_markdown, lista_imagens)."""
    chars = []
    for ch in pagina.chars:
        novo = dict(ch)
        novo["text"] = normalizar(ch["text"])
        chars.append(novo)

    if not chars:
        return "", []

    corpo = tamanho_corpo(chars)
    divisoria = achar_divisoria(pagina, chars)

    if divisoria is None:
        x_div, topo_div, base_div = None, 0.0, pagina.height
    else:
        x_div, topo_div, base_div = divisoria

    rodape = [ch for ch in chars if ch["top"] >= base_div - 1]
    corpo_pagina = [ch for ch in chars if ch["top"] < base_div - 1]

    if x_div is None:
        blocos = [corpo_pagina]
    else:
        blocos = [
            [ch for ch in corpo_pagina if (ch["x0"] + ch["x1"]) / 2 < x_div],
            [ch for ch in corpo_pagina if (ch["x0"] + ch["x1"]) / 2 >= x_div],
        ]

    todos_radicais = achar_radicais(pagina)
    resultado = []
    for bloco in blocos:
        if not bloco:
            continue
        fracoes = achar_fracoes(pagina, bloco)
        if x_div is None:
            radicais = todos_radicais
        else:
            esquerda = bloco is blocos[0]
            radicais = [r for r in todos_radicais if (r["x0"] < x_div) == esquerda]
        resultado.extend(renderizar_coluna(bloco, corpo, fracoes, radicais))
        resultado.append("")

    if rodape:
        resultado.extend(renderizar_coluna(rodape, corpo, [], []))

    texto = "\n".join(resultado).strip()
    
    # Extrai imagens se pasta informada
    imagens = []
    if pasta_imagens:
        imagens = extrair_imagens(pagina, pasta_imagens, f"page{pagina.page_number}")
        # Adiciona referências de imagem no markdown se houver imagens
        if imagens:
            refs = "\n\n".join(f"![Imagem página {img['pagina']}]({img['arquivo']})" for img in imagens)
            texto = f"{texto}\n\n{refs}" if texto else refs
    
    return texto, imagens


def converter_pdf(
    pdf_path: Path,
    output_path: Path,
    paginas: Optional[List[int]] = None,
    pasta_imagens: Optional[Path] = None,
) -> int:
    """Converte PDF para Markdown. Retorna número de caracteres."""
    pedacos = []
    todas_imagens = []
    
    with pdf_open(str(pdf_path)) as pdf:
        alvos = paginas if paginas is not None else range(len(pdf.pages))
        for indice in alvos:
            texto, imagens = processar_pagina(pdf.pages[indice], pasta_imagens)
            pedacos.append(f"<!-- pagina {indice + 1} -->\n{texto}")
            todas_imagens.extend(imagens)
    
    output_path.write_text("\n\n".join(pedacos), encoding="utf-8")
    
    # Salva manifesto de imagens se houver
    if pasta_imagens and todas_imagens:
        import json
        manifesto = pasta_imagens / "manifest.json"
        manifesto.write_text(json.dumps(todas_imagens, indent=2, ensure_ascii=False), encoding="utf-8")
    
    return len(output_path.read_text(encoding="utf-8"))


# ---- Nougat OCR ----
def converter_com_nougat(pdf_path: Path, output_path: Path, paginas: Optional[List[int]] = None) -> int:
    """Converte PDF usando Nougat OCR (para PDFs escaneados)."""
    try:
        from nougat import NougatModel
        from nougat.utils.checkpoint import get_checkpoint
    except ImportError:
        print("Erro: Nougat não instalado. Execute: pip install nougat-ocr", file=sys.stderr)
        print("Nota: Requer transformers 4.x e torch. Use ambiente separado se necessário.", file=sys.stderr)
        return 0
    
    print("Carregando modelo Nougat (pode demorar na primeira vez)...")
    checkpoint = get_checkpoint(None, model_tag="0.1.0-base")
    model = NougatModel.from_pretrained(checkpoint)
    model.eval()
    
    # TODO: Implementar conversão página a página com Nougat
    # Por enquanto, avisa que não está implementado
    print("Nougat OCR: conversão página a página não implementada ainda.")
    print("Use o CLI do Nougat diretamente: nougat arquivo.pdf -o saida --markdown")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="exam2md - Prova para Markdown com LaTeX + Imagens + OCR")
    parser.add_argument("pdf", type=Path, help="Arquivo PDF de entrada")
    parser.add_argument("-o", "--output", type=Path, help="Arquivo Markdown de saída (padrão: mesmo nome do PDF com .md)")
    parser.add_argument("--pages", help="Páginas 1-based, ex.: 1,2,3 ou 5-10")
    parser.add_argument("--ocr", action="store_true", help="Usa Nougat OCR (para PDFs escaneados)")
    parser.add_argument("--save-images", action="store_true", help="Extrai imagens do PDF para pasta ao lado")
    parser.add_argument("--images-dir", type=Path, help="Pasta personalizada para imagens (padrão: <pdf>_images/)")
    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.is_file():
        print(f"Erro: arquivo não encontrado: {pdf_path}", file=sys.stderr)
        return 2

    if args.output:
        output_path = args.output
    else:
        output_path = pdf_path.with_suffix(".md")

    # Pasta de imagens
    pasta_imagens = None
    if args.save_images:
        if args.images_dir:
            pasta_imagens = args.images_dir
        else:
            pasta_imagens = pdf_path.parent / f"{pdf_path.stem}_images"

    paginas = None
    if args.pages:
        paginas = []
        for parte in args.pages.split(","):
            parte = parte.strip()
            if "-" in parte:
                ini, fim = map(int, parte.split("-", 1))
                paginas.extend(range(ini - 1, fim))
            else:
                paginas.append(int(parte) - 1)

    if args.ocr:
        chars = converter_com_nougat(pdf_path, output_path, paginas)
    else:
        chars = converter_pdf(pdf_path, output_path, paginas, pasta_imagens)
    
    msg = f"OK: {output_path} ({chars} caracteres)"
    if pasta_imagens:
        msg += f" | Imagens em: {pasta_imagens}/"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())