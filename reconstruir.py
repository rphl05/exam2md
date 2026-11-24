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
import re
from pathlib import Path
from typing import Optional, List

from pdfplumber import open as pdf_open

# ---- constants & helpers ----
SIMBOLOS = {
    0xF028: "(", 0xF029: ")", 0xF02B: "+", 0xF02D: "−",
    0xF03D: "=", 0xF0B7: "·",
    0xF0E6: "⎛", 0xF0E7: "⎜", 0xF0E8: "⎝",
    0xF0F6: "⎞", 0xF0F7: "⎟", 0xF0F8: "⎠",
    # Bullet points and common special chars
    0x2022: "•",  # bullet
    0x2023: "‣",  # triangular bullet
    0x25CF: "●",  # black circle
    0x25CB: "○",  # white circle
    0x25A0: "■",  # black square
    0x25A1: "□",  # white square
    0x2013: "–",  # en dash
    0x2014: "—",  # em dash
    0x2018: "'",  # left single quote
    0x2019: "'",  # right single quote
    0x201C: "\"", # left double quote
    0x201D: "\"", # right double quote
    0x2026: "...", # ellipsis
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


def achar_divisoria(pagina, chars, corpo):
    """Encontra a divisória vertical entre colunas."""
    # 1. Tenta encontrar linha vertical explícita
    candidatas = [
        linha for linha in pagina.lines
        if (linha["x1"] - linha["x0"]) < 2 and (linha["bottom"] - linha["top"]) > 200
    ]
    if candidatas:
        melhor = min(candidatas, key=lambda l: abs(l["x0"] - pagina.width / 2))
        return melhor["x0"], melhor["top"], melhor["bottom"]

    # 2. Usa densidade de caracteres (filtrando watermark e headers grandes)
    # Filtra: remove watermark (topo pequeno, fonte tiny) e headers grandes
    chars_filtrados = [
        ch for ch in chars
        if not (ch["top"] < 50 and ch["size"] < 9)  # watermark
        and 0.7 * corpo <= ch["size"] <= 1.3 * corpo  # tamanho do corpo
    ]

    faixas = 60
    passo = pagina.width / faixas
    ocupacao = [0] * faixas
    for ch in chars_filtrados:
        centro = (ch["x0"] + ch["x1"]) / 2
        indice = min(faixas - 1, max(0, int(centro / passo)))
        ocupacao[indice] += 1

    # Usa threshold em vez de zero exato (permite alguns chars no gutter)
    max_ocup = max(ocupacao[int(faixas * 0.3):int(faixas * 0.7)]) if any(ocupacao[int(faixas * 0.3):int(faixas * 0.7)]) else 1
    threshold = max(1, max_ocup * 0.05)  # 5% do máximo

    melhor_inicio, melhor_tamanho, atual = None, 0, 0
    for i in range(int(faixas * 0.3), int(faixas * 0.7)):
        if ocupacao[i] <= threshold:
            atual += 1
            if atual > melhor_tamanho:
                melhor_tamanho, melhor_inicio = atual, i - atual + 1
        else:
            atual = 0
    if melhor_tamanho < 2:  # gap mínimo de 2 faixas
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


def eh_alternativa(texto: str) -> bool:
    """Detecta se uma linha é uma alternativa (A), (B), etc."""
    # Alternativas típicas: (A), (A), A), A., (A., (A., A., etc.
    # Após a letra, deve vir: espaço + maiúscula, ou pontuação, ou fim de linha
    # NÃO é alternativa se for palavra normal começando com A-E seguida de minúscula
    m = re.match(r'^\(?([A-E])\)?[\s\.]', texto)
    if not m:
        return False
    # Verifica o que vem após a letra + espaço/pontuação
    resto = texto[m.end():].lstrip()
    if not resto:
        return True  # linha é só "(A)" ou "A."
    # Se o próximo caractere é maiúsculo ou pontuação, é alternativa
    # Se é minúscula, é palavra normal (ex: "A subjetividade...")
    return resto[0].isupper() or resto[0] in '("\''
 

def juntar_numeros_de_questao(linhas):
    """Junta número da questão com enunciado e formata alternativas.
    Suporta formatos:
    - CFS/EEAR: "1 – Enunciado"
    - Vunesp: "01. Enunciado" (com zeros à esquerda)
    - FGV/outros: número sozinho na linha seguido de enunciado
    - Alternativas: (A), (B), etc. cada uma em linha separada
    """
    saida = []
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        
        # Formato CFS/EEAR: "N – Enunciado"
        if (
            i + 1 < len(linhas)
            and linha.isdigit()
            and len(linha) <= 2
            and linhas[i + 1].strip().startswith("–")
        ):
            saida.append(f"{linha} {linhas[i + 1].strip()}")
            i += 2
            continue
        
        # Formato Vunesp: "NN. Enunciado" (ex: 01. 02. 03.)
        if (
            re.match(r'^\d{2}\.$', linha)
            and i + 1 < len(linhas)
            and not re.match(r'^\d{2}\.\d', linhas[i + 1].strip())
            and not re.match(r'^\d{3}', linhas[i + 1].strip())
        ):
            saida.append(f"{linha} {linhas[i + 1].strip()}")
            i += 2
            continue
        
        # Formato FGV/geral: número da questão sozinho na linha (1-2 dígitos)
        # seguido de texto que não parece alternativa
        prox_linha = linhas[i + 1].strip() if i + 1 < len(linhas) else ''
        eh_alt = eh_alternativa(prox_linha)
        
        if (
            re.match(r'^\d{1,2}$', linha)
            and i + 1 < len(linhas)
            and not eh_alt
        ):
            # Junta com as próximas linhas até encontrar uma alternativa ou próxima questão
            enunciado = [linha]
            i += 1
            while i < len(linhas):
                prox = linhas[i].strip()
                # Para se encontrar próxima questão (número) ou alternativa
                if re.match(r'^\d{1,2}$', prox) or eh_alternativa(prox):
                    break
                enunciado.append(prox)
                i += 1
            saida.append(" ".join(enunciado))
            continue
        
        # Alternativas: (A), (B), (C), (D), (E) - cada uma em linha separada
        if eh_alternativa(linha):
            saida.append(linha)
            i += 1
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
    
    # Filtra watermarks: imagens no rodapé (65% da altura) com dimensões típicas
    # Watermark VUNESP: y=579 (68% de 841.92), 262.5x262.5
    pagina_height = pagina.height
    limite_rodape = pagina_height * 0.65  # 65% da altura
    
    for idx, img in enumerate(pagina.images):
        try:
            stream = img.get("stream")
            if not stream:
                continue
            
            # Filtra watermarks: no rodapé + dimensões típicas de marca d'água repetitiva
            img_y = img.get("top", 0)
            img_w = img.get("width", 0)
            img_h = img.get("height", 0)
            
            eh_watermark = (
                img_y > limite_rodape and
                240 <= img_w <= 290 and
                240 <= img_h <= 290
            )
            
            if eh_watermark:
                continue  # Pula watermark
            
            # Gera nome único
            ext = ".png"
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
                "largura": img_w,
                "altura": img_h,
            })
        except Exception as e:
            print(f"[aviso] Falha ao extrair imagem {idx}: {e}", file=sys.stderr)
    
    return resultados


def encontrar_inicio_colunas(chars, x_div, corpo, pagina_height, pagina=None):
    """
    Detecta onde começa o layout de duas colunas.
    Procura onde AMBOS os lados têm conteúdo consistente (duas colunas reais).
    Considera tanto texto quanto imagens.
    Retorna a coordenada Y onde as colunas começam, ou None se não detectado.
    """
    # If no column divider, there's no two-column layout to detect
    if x_div is None:
        return None
    
    from collections import defaultdict
    linhas = defaultdict(list)
    for ch in chars:
        top_key = round(ch["top"] / 2) * 2
        linhas[top_key].append(ch)
    
    # Também considera imagens para detectar colunas
    imagens_por_top = defaultdict(list)
    if pagina is not None:
        for img in pagina.images:
            top_key = round(img.get("top", 0) / 2) * 2
            # Só considera imagens que não são watermarks
            img_y = img.get("top", 0)
            img_w = img.get("width", 0)
            img_h = img.get("height", 0)
            eh_watermark = (
                img_y > pagina_height * 0.65 and
                240 <= img_w <= 290 and
                240 <= img_h <= 290
            )
            if not eh_watermark:
                imagens_por_top[top_key].append(img)
    
    balanco_por_top = []
    for top in sorted(set(list(linhas.keys()) + list(imagens_por_top.keys()))):
        chars_linha = linhas.get(top, [])
        imgs_linha = imagens_por_top.get(top, [])
        
        left = sum(1 for ch in chars_linha if (ch["x0"] + ch["x1"]) / 2 < x_div)
        right = sum(1 for ch in chars_linha if (ch["x0"] + ch["x1"]) / 2 >= x_div)
        
        # Also count images
        left_img = sum(1 for img in imgs_linha if (img.get("x0", 0) + img.get("x1", 0)) / 2 < x_div)
        right_img = sum(1 for img in imgs_linha if (img.get("x0", 0) + img.get("x1", 0)) / 2 >= x_div)
        
        left_total = left + left_img
        right_total = right + right_img
        total = left_total + right_total
        
        if total > 5:
            if left_total > 0 and right_total > 0:
                ratio = min(left_total, right_total) / max(left_total, right_total)
            else:
                ratio = 0
            balanco_por_top.append((top, ratio, left_total, right_total, total))
    
    if not balanco_por_top:
        return None
    
    # Procura a primeira linha onde o ratio é bom (>0.3) 
    # E as próximas linhas também têm ratio razoável na maioria
    # Permite alguns gaps (linhas de cabeçalho de seção num lado só)
    
    for i, (top, ratio, left, right, total) in enumerate(balanco_por_top):
        if ratio > 0.3 and total > 10:
            # Verifica as próximas 5 linhas: pelo menos 3 devem ter ratio > 0.3
            bons = 0
            for j in range(i, min(i + 6, len(balanco_por_top))):
                t, r, l, rt, tot = balanco_por_top[j]
                if r > 0.3 and tot > 10:
                    bons += 1
            if bons >= 3:
                return top
    
    return None


def processar_pagina(pagina, pasta_imagens: Optional[Path] = None) -> tuple:
    """Processa uma página. Retorna (texto_markdown, lista_imagens)."""
    chars = []
    for ch in pagina.chars:
        novo = dict(ch)
        novo["text"] = normalizar(ch["text"])
        # Filtra watermark (texto minúsculo no topo da página)
        if ch["top"] < 50 and ch["size"] < 9:
            continue
        chars.append(novo)

    if not chars:
        return "", []

    corpo = tamanho_corpo(chars)
    divisoria = achar_divisoria(pagina, chars, corpo)

    if divisoria is None:
        x_div, topo_div, base_div = None, 0.0, pagina.height
    else:
        x_div, topo_div, base_div = divisoria

    rodape = [ch for ch in chars if ch["top"] >= base_div - 1]
    corpo_pagina = [ch for ch in chars if ch["top"] < base_div - 1]

    if x_div is None:
        blocos = [corpo_pagina]
    else:
        # Detecta onde começa o layout de duas colunas
        y_inicio_colunas = encontrar_inicio_colunas(corpo_pagina, x_div, corpo, pagina.height, pagina)
        
        if y_inicio_colunas is not None:
            # Divide: acima de y_inicio_colunas = full width, abaixo = duas colunas
            cabecalho = [ch for ch in corpo_pagina if ch["top"] < y_inicio_colunas]
            corpo_colunas = [ch for ch in corpo_pagina if ch["top"] >= y_inicio_colunas]
            
            blocos = [cabecalho]
            if corpo_colunas:
                blocos.append([ch for ch in corpo_colunas if (ch["x0"] + ch["x1"]) / 2 < x_div])
                blocos.append([ch for ch in corpo_colunas if (ch["x0"] + ch["x1"]) / 2 >= x_div])
        else:
            # Fallback: uma coluna na página toda (layout não tem duas colunas claras)
            blocos = [corpo_pagina]

    todos_radicais = achar_radicais(pagina)
    resultado = []
    
    for idx_bloco, bloco in enumerate(blocos):
        if not bloco:
            continue
        fracoes = achar_fracoes(pagina, bloco)
        if x_div is None:
            radicais = todos_radicais
        else:
            esquerda = bloco is blocos[0]
            radicais = [r for r in todos_radicais if (r["x0"] < x_div) == esquerda]
        
        # Renderiza coluna
        linhas_coluna = renderizar_coluna(bloco, corpo, fracoes, radicais)
        
        # Adiciona marcador de coluna para pós-processamento (exceto primeira coluna)
        if idx_bloco > 0 and x_div is not None:
            resultado.append("__COLUMN_BREAK__")
        
        resultado.extend(linhas_coluna)
        resultado.append("")

    if rodape:
        resultado.extend(renderizar_coluna(rodape, corpo, [], []))

    texto = "\n".join(resultado).strip()
    
    # Pós-processamento conservador: apenas corrige hifenização óbvia
    import re
    
    # 1. Corrige hifenização quebrada (palavras quebradas com hífen no final da linha)
    # "apli-\ncado" -> "aplicado"
    texto = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', texto)
    
    # 2. Corrige palavras quebradas por espaço/quebra sem hífen (ex: "d ificuldades")
    # Padrão: letra no final da linha + quebra + letra minúscula no início da próxima
    # Apenas se a linha anterior NÃO termina com pontuação e a próxima começa com minúscula
    linhas = texto.split('\n')
    for i in range(len(linhas) - 1):
        atual = linhas[i].rstrip()
        prox = linhas[i + 1].lstrip()
        if (atual and prox and 
            not re.search(r'[.!?;:]\s*$', atual) and
            prox and prox[0].islower() and
            # Não juntar se linha atual parece número de questão
            not re.match(r'^\d{1,2}[.–]\s', atual) and
            # Não juntar se próxima linha parece alternativa
            not re.match(r'^\(?[A-E]\)?', prox.lstrip())):
            linhas[i] = atual + ' ' + prox.lstrip()
            linhas[i + 1] = ''
    texto = '\n'.join(l for l in linhas if l)
    
    # 2. Corrige hifenização quebrada (palavras quebradas com hífen no final da linha)
    texto = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', texto)
    
    # 3. Corrige palavras quebradas por espaço/quebra sem hífen
    texto = re.sub(r'(\w)\s*\n\s+([a-z])', r'\1\2', texto)
    
    # 4. Corrige espaços duplos
    texto = re.sub(r' {2,}', ' ', texto)
    
    # 5. Remove caracteres de substituição (U+FFFD) se houver
    texto = texto.replace('\ufffd', '')
    
    # Pós-processamento avançado: limpeza específica para provas FGV/Vunesp
    texto = pos_processar_prova(texto, pagina.page_number)
    
    # Extrai imagens se pasta informada
    imagens = []
    if pasta_imagens:
        imagens = extrair_imagens(pagina, pasta_imagens, f"page{pagina.page_number}")
        if imagens:
            # Insere imagens na posição aproximada baseada na coordenada Y
            texto = inserir_imagens_no_texto(texto, imagens, pagina.height)
    
    return texto, imagens


def inserir_imagens_no_texto(texto: str, imagens: list, pagina_height: float) -> str:
    """Insere referências de imagens no texto na posição aproximada baseada na coordenada Y."""
    if not imagens:
        return texto
    
    # Ordena imagens por posição Y (topo da página = 0)
    imagens_ordenadas = sorted(imagens, key=lambda img: img.get('y', 0))
    
    linhas = texto.split('\n')
    if not linhas:
        return "\n\n".join(f"![Imagem página {img['pagina']}]({img['arquivo']})" for img in imagens)
    
    # Estima a posição Y de cada linha baseada na distribuição
    # Assume que as linhas estão distribuídas uniformemente na página
    total_linhas = len(linhas)
    linhas_com_pos = []
    for i, linha in enumerate(linhas):
        # Posição Y estimada (0 = topo, pagina_height = base)
        y_estimado = (i / max(1, total_linhas - 1)) * pagina_height
        linhas_com_pos.append((y_estimado, linha))
    
    # Insere imagens nas posições corretas
    resultado = []
    img_idx = 0
    
    for y_linha, linha in linhas_com_pos:
        # Insere imagens que estão ANTES desta linha
        while img_idx < len(imagens_ordenadas):
            img = imagens_ordenadas[img_idx]
            img_y = img.get('y', 0)
            # Se a imagem está acima da linha atual (menor Y = mais no topo)
            if img_y < y_linha:
                ref = f"![Imagem página {img['pagina']}]({img['arquivo']})"
                resultado.append(ref)
                resultado.append("")  # linha em branco
                img_idx += 1
            else:
                break
        resultado.append(linha)
    
    # Insere imagens restantes no final
    while img_idx < len(imagens_ordenadas):
        img = imagens_ordenadas[img_idx]
        ref = f"![Imagem página {img['pagina']}]({img['arquivo']})"
        resultado.append(ref)
        resultado.append("")
        img_idx += 1
    
    return "\n".join(resultado)


def pos_processar_prova(texto: str, pagina_num: int) -> str:
    """Pós-processamento específico para provas (FGV, Vunesp, etc.)."""
    import re
    
    # Global operation counter to prevent infinite loops
    MAX_OPERATIONS = 50000
    operation_count = 0
    
    def check_ops():
        nonlocal operation_count
        operation_count += 1
        if operation_count > 50000:
            raise RuntimeError("pos_processar_prova: Maximum operations exceeded")
    
    # 1. Primeiro, processa marcadores de quebra de coluna
    linhas = texto.split('\n')
    linhas_sem_marcadores = []
    for linha in linhas:
        check_ops()
        if linha.strip() == '__COLUMN_BREAK__':
            # Substitui por marcador interno que será processado depois
            linhas_sem_marcadores.append('__COL_BREAK__')
        else:
            linhas_sem_marcadores.append(linha)
    
    # 2. Junta linhas que são continuação de LaTeX (frações, comandos)
    # Evita quebrar \frac{...}{...} no meio
    i = 0
    max_iter = len(linhas_sem_marcadores) * 2
    iter_count = 0
    while i < len(linhas_sem_marcadores) - 1:
        check_ops()
        iter_count += 1
        if iter_count > max_iter:
            break
        atual = linhas_sem_marcadores[i]
        prox = linhas_sem_marcadores[i + 1]
        # Se linha atual tem \frac{ ou { aberto e próxima continua
        if (re.search(r'\\frac\{[^}]*\{[^}]*$', atual) or 
            atual.count('{') > atual.count('}') or
            atual.rstrip().endswith('\\')):
            linhas_sem_marcadores[i] = atual + ' ' + prox.lstrip()
            linhas_sem_marcadores[i + 1] = '__REMOVE__'
            i += 1
        i += 1
    
    linhas_sem_marcadores = [l for l in linhas_sem_marcadores if l != '__REMOVE__']
    
    # 3. Reconstrói texto com quebras de coluna como linhas vazias
    resultado_com_quebras = []
    for l in linhas_sem_marcadores:
        if l == '__COL_BREAK__':
            if resultado_com_quebras and resultado_com_quebras[-1].strip() != '':
                resultado_com_quebras.append('')
        else:
            resultado_com_quebras.append(l)
    
    # 5. Remove linhas de rodapé/cabeçalho repetitivas
    padroes_remover = [
        r'SOLDADO\s+PM\s+DE\s+2[ª\º]\s+CLASSE\s*[–-]\s*TARDE',
        r'TIPO\s+BRANCA\s*[–-]\s*P[ÁA]GINA\s+\d+',
        r'www\.pciconcursos\.com\.br',
        r'^SOLDADO\s+PM\s+DE\s+2[ª\º]\s+CLASSE\s*$',
        r'CONHECIMENTOS\s+GERAIS',
        r'MATEM[ÁA]TICA\s+\d+',
        r'L[ÍI]NGUA\s+PORTUGUESA\s+E',
        r'INTERPRETA[CÇ][AÃ]O\s+DE\s+TEXTO',
        r'ESTADO\s+DE\s+S[ÃA]O\s+PAULO',
        r'NO\s+MENOR\s+TEMPO\s+POSS[ÍI]VEL',
    ]
    
    linhas_filtradas = []
    for linha in resultado_com_quebras:
        linha_strip = linha.strip()
        remover = False
        for padrao in padroes_remover:
            if re.search(padrao, linha_strip, re.IGNORECASE):
                remover = True
                break
        if not remover:
            linhas_filtradas.append(linha_strip)
    
    # 4. Processa números de questões consecutivos (ex: "9 15" -> "9\n15")
    i = 0
    saida = []
    while i < len(linhas_filtradas):
        check_ops()
        atual = linhas_filtradas[i]
        if (re.match(r'^\d{1,2}$', atual) and 
            i + 1 < len(linhas_filtradas) and 
            re.match(r'^\d{1,2}$', linhas_filtradas[i + 1])):
            saida.append(atual)
            saida.append('')  # separa
            i += 1
            continue
        saida.append(atual)
        i += 1
    
    # 5. Corrige "9 15" na mesma linha -> "9\n15"
    linhas_temp = []
    for linha in saida:
        # Corrige "9 15" na mesma linha -> "9\n15"
        linha = re.sub(r'^(\d{1,2})\s+(\d{1,2})$', r'\1\n\2', linha)
        linhas_temp.append(linha)
    saida = linhas_temp
    
    # 6. Processa cada linha
    linhas_processadas = []
    for linha in saida:
        check_ops()
        # Corrige formatação do número da questão: "1 " -> "1. "
        linha = re.sub(r'^(\d{1,2})\s+(?=[A-ZÀ-Ú])', r'\1. ', linha)
        
        # Separa alternativas unidas por " / " (vindas de colunas diferentes)
        linha = re.sub(r'\s*/\s*(?=\([A-E]\)?[\s\.])', '\n', linha)
        
        # Garante que alternativas comecem em linha nova
        linha = re.sub(r'(\S)\s+(\([A-E]\)?[\s\.])', r'\1\n\2', linha)
        
        linhas_processadas.append(linha)
    
    # 7. Junta linhas que são continuação de LaTeX
    i = 0
    max_iter = len(linhas_processadas) * 2
    iter_count = 0
    while i < len(linhas_processadas) - 1:
        check_ops()
        iter_count += 1
        if iter_count > max_iter:
            break
        atual = linhas_processadas[i]
        prox = linhas_processadas[i + 1]
        if (re.search(r'\\frac\{[^}]*\{[^}]*$', atual) or 
            atual.count('{') > atual.count('}') or
            atual.rstrip().endswith('\\')):
            linhas_processadas[i] = atual + ' ' + prox.lstrip()
            linhas_processadas[i + 1] = ''
            i += 1
        i += 1
    saida = [l for l in linhas_processadas if l != '']
    
    # 8. Junta linhas vazias consecutivas (máximo 1)
    resultado_final = []
    vazia_anterior = False
    for linha in saida:
        if linha.strip() == '':
            if not vazia_anterior:
                resultado_final.append('')
            vazia_anterior = True
        else:
            resultado_final.append(linha)
            vazia_anterior = False
    
    return '\n'.join(resultado_final)



def converter_hibrido(
    pdf_path: Path,
    output_path: Path,
    paginas: Optional[List[int]] = None,
    pasta_imagens: Optional[Path] = None,
) -> int:
    """
    Conversão híbrida: pdfplumber para texto/vetores + pix2tex para fórmulas bitmap.
    Detecta regiões de fórmula bitmap (imagens) e usa pix2tex para OCR seletivo.
    Nota: Fórmulas vetoriais (curvas) são processadas pelo pipeline principal do pdfplumber.
    """
    try:
        from pix2tex.cli import LatexOCR
    except ImportError:
        print("Erro: pix2tex não instalado. Execute: pip install pix2tex", file=sys.stderr)
        return 0

    print("Carregando modelo pix2tex...")
    modelo = LatexOCR()

    pedacos = []
    todas_imagens = []

    with pdf_open(str(pdf_path)) as pdf:
        alvos = paginas if paginas is not None else range(len(pdf.pages))
        for indice in alvos:
            pagina = pdf.pages[indice]
            
            # 1. Processa com pdfplumber (texto/vetores + frações/radicais vetoriais)
            texto, imagens = processar_pagina(pagina, None)  # sem pasta_imagens para não duplicar
            
            # 2. Detecta regiões de fórmula bitmap (imagens matemáticas bitmap)
            formula_regioes = detectar_formulas_bitmap(pagina)
            
            # 3. Para cada região, extrai imagem e roda pix2tex
            for regiao in formula_regioes:
                try:
                    # Extrai a região como imagem
                    regiao_img = extrair_regiao_como_imagem(pagina, regiao)
                    if regiao_img:
                        # Roda pix2tex
                        latex = modelo(regiao_img).strip()
                        if latex:
                            # Substitui a região no texto por LaTeX
                            # (simplificado: adiciona no final do texto da página)
                            texto += f"\n\n$${latex}$$"
                except Exception as e:
                    print(f"  Aviso: falha ao processar fórmula bitmap: {e}")

            pedacos.append(f"<!-- pagina {indice + 1} -->\n{texto}")
            todas_imagens.extend(imagens)

    output_path.write_text("\n\n".join(pedacos), encoding="utf-8")
    return len(output_path.read_text(encoding="utf-8"))


def extrair_regiao_como_imagem(pagina, regiao):
    """Extrai uma região da página como imagem PIL para OCR."""
    try:
        bbox = regiao['bbox']
        crop = pagina.crop(bbox)
        img = crop.to_image(resolution=300)
        return img.original
    except Exception:
        return None


def detectar_formulas_bitmap(pagina):
    """
    Detecta regiões que parecem fórmulas bitmap (imagens matemáticas).
    Retorna lista de dicts com 'bbox' (x0, y0, x1, y1) e metadados.
    """
    regioes = []
    pagina_height = pagina.height
    limite_rodape = pagina_height * 0.65  # 65% da altura
    
    # Procura por imagens na página que parecem fórmulas
    for img in pagina.images:
        # Filtra: imagens pequenas a grandes, não decorativas
        largura = img.get('width', 0)
        altura = img.get('height', 0)
        
        # Heurística: fórmulas podem ser imagens de vários tamanhos
        # Aumentado limites para capturar fórmulas maiores (ex: sistemas de equações)
        if 20 <= largura <= 600 and 20 <= altura <= 500:
            # Verifica se não é decorativa (muito pequena ou muito grande)
            area = largura * altura
            if 400 <= area <= 200000:  # Aumentado de 50000 para 200000
                # Filtra imagens que parecem ser fotos/gráficos decorativos (muito grandes)
                # Fórmulas matemáticas costumam ter proporção mais quadrada ou retangular moderada
                ratio = max(largura, altura) / min(largura, altura)
                if ratio <= 4:  # Não muito alongado
                    # Filtra watermarks: imagens no rodapé com dimensões típicas
                    img_y = img.get('top', 0)
                    img_w = img.get('width', 0)
                    img_h = img.get('height', 0)
                    eh_watermark = (
                        img_y > pagina_height * 0.65 and
                        240 <= img_w <= 290 and
                        240 <= img_h <= 290
                    )
                    if not eh_watermark:
                        regioes.append({
                            'bbox': (img['x0'], img['top'], img['x1'], img['bottom']),
                            'x0': img['x0'],
                            'y0': img['top'],
                            'x1': img['x1'],
                            'y1': img['bottom'],
                        })
    
    return regioes


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
    parser.add_argument("--hybrid", action="store_true", help="Modo híbrido: pdfplumber + pix2tex para fórmulas bitmap")
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
    elif args.hybrid:
        chars = converter_hibrido(pdf_path, output_path, paginas, pasta_imagens)
    else:
        chars = converter_pdf(pdf_path, output_path, paginas, pasta_imagens)
    
    msg = f"OK: {output_path} ({chars} caracteres)"
    if pasta_imagens:
        msg += f" | Imagens em: {pasta_imagens}/"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())