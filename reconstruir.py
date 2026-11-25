#!/usr/bin/env python
"""exam2md - Prova em PDF para Markdown com LaTeX + imagens.

Uso:
    python reconstruir.py prova.pdf                     # gera prova.md + pasta prova_images/
    python reconstruir.py prova.pdf -o saida.md         # nome customizado
    python reconstruir.py prova.pdf --pages 1,3-5       # páginas específicas
    python reconstruir.py prova.pdf --hybrid            # fórmulas em imagem -> LaTeX (pix2tex)
    python reconstruir.py prova.pdf --no-images         # não extrai imagens
    python reconstruir.py prova.pdf --ocr               # PDF escaneado (Nougat)

Pipeline (PDF vetorial, 100% local):
  1. Detecta colunas (linha divisória vertical ou faixa vazia no meio da página)
  2. Agrupa caracteres em linhas, classifica sub/sobrescritos pela linha de base
  3. Frações (barras vetoriais) e radicais (curvas em "V") viram \\frac / \\sqrt
  4. Trechos matemáticos são delimitados com $...$; negrito/itálico vêm da fonte
  5. Quebras de linha: junta só linhas que foram quebradas pela margem
     (linha "cheia"); versos, listas e alternativas ficam em linhas próprias
  6. Imagens são recortadas como PNG e nomeadas pela questão em que aparecem:
     prova_images/prova_q05_1.png, prova_q05_altB_1.png, prova_pag01_1.png
"""

import argparse
import collections
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pdfplumber import open as pdf_open

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
SIMBOLOS = {
    # Fonte Symbol (área privada Unicode)
    0xF028: "(", 0xF029: ")", 0xF02B: "+", 0xF02D: "−",
    0xF03D: "=", 0xF0B7: "·",
    0xF0E6: "⎛", 0xF0E7: "⎜", 0xF0E8: "⎝",
    0xF0F6: "⎞", 0xF0F7: "⎟", 0xF0F8: "⎠",
    0x2018: "'", 0x2019: "'",
    0x201C: '"', 0x201D: '"',
    0x2026: "...",
}
ABRE_COLCHETE = "⎛⎜⎝"
FECHA_COLCHETE = "⎞⎟⎠"
ESPACO_RELATIVO = 0.17

# Caracteres que podem fazer parte de uma expressão matemática em volta de
# \frac, \sqrt, ^{} e _{} (para delimitar o trecho com $...$).
OPERADORES_MATH = set("0123456789+−-=·×÷<>≤≥≠±≈∞,./()[]|'′°πθαβγΔ∆")

MARCADOR_IMG = "⟦IMG:{}⟧"
RE_MARCADOR = re.compile(r"^⟦IMG:([^⟧]+)⟧$")

# Início de bloco que nunca deve ser colado à linha anterior
RE_INICIO_BLOCO = re.compile(
    r"^(?:\*{1,3})?(?:"
    r"\(?[A-Ea-e]\)"                     # (A)  a)
    r"|\d{1,3}(?:\s*[)–]|\.(?:\s|$)|\s+[–-]\s)"   # 01.  1)  1 –
    r"|[•●○■□▪➢►✓]"                       # marcadores de lista
    r"|[-–—]\s"
    r"|⟦IMG:"
    r")"
)
RE_QUESTAO = re.compile(r"^(?:\*{1,3})?(?:quest[ãa]o\s+)?(\d{1,3})\s*(?:\.(?!\d)|\)|–|-)", re.I)
RE_ALTERNATIVA = re.compile(r"^(?:\*{1,3})?\(?([A-Ea-e])\)")


# ---------------------------------------------------------------------------
# Utilidades básicas
# ---------------------------------------------------------------------------
def normalizar(texto: str) -> str:
    return "".join(SIMBOLOS.get(ord(c), c) for c in texto)


def estilo_fonte(fontname: str):
    """(negrito, itálico) a partir do nome da fonte (ex.: 'ABCDEF+Calibri-BoldItalic')."""
    nome = (fontname or "").split("+")[-1].lower()
    negrito = any(k in nome for k in ("bold", "black", "heavy", "semibold", "demi"))
    italico = "italic" in nome or "oblique" in nome
    return (negrito, italico)


def tamanho_corpo(chars):
    contagem = collections.Counter(round(ch["size"], 1) for ch in chars)
    return contagem.most_common(1)[0][0]


def eh_marca_dagua(img, pagina_height) -> bool:
    """Marca d'água típica da VUNESP: quadrado ~262pt no rodapé."""
    return (
        img.get("top", 0) > pagina_height * 0.65
        and 240 <= img.get("width", 0) <= 290
        and 240 <= img.get("height", 0) <= 290
    )


def parse_paginas(spec: Optional[str]) -> Optional[List[int]]:
    """'1,3-5' -> [0, 2, 3, 4] (0-based)."""
    if not spec or not spec.strip():
        return None
    paginas = []
    for parte in spec.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            ini, fim = map(int, parte.split("-", 1))
            paginas.extend(range(ini - 1, fim))
        else:
            paginas.append(int(parte) - 1)
    return paginas


# ---------------------------------------------------------------------------
# Colunas
# ---------------------------------------------------------------------------
def achar_divisoria(pagina, chars, corpo):
    """Encontra a divisória vertical entre colunas.

    Retorna (x, topo, base, explicita) ou None.
    """
    # 1. Linha vertical explícita perto do centro
    candidatas = [
        linha for linha in pagina.lines
        if (linha["x1"] - linha["x0"]) < 2
        and (linha["bottom"] - linha["top"]) > 200
        and abs(linha["x0"] - pagina.width / 2) < 0.15 * pagina.width
    ]
    if candidatas:
        melhor = min(candidatas, key=lambda l: abs(l["x0"] - pagina.width / 2))
        topo = min(l["top"] for l in candidatas if abs(l["x0"] - melhor["x0"]) < 2)
        base = max(l["bottom"] for l in candidatas if abs(l["x0"] - melhor["x0"]) < 2)
        return melhor["x0"], topo, base, True

    # 2. Faixa vazia no meio da página (densidade de caracteres do corpo do texto)
    chars_filtrados = [ch for ch in chars if 0.7 * corpo <= ch["size"] <= 1.3 * corpo]
    if not chars_filtrados:
        return None

    faixas = 60
    passo = pagina.width / faixas
    ocupacao = [0] * faixas
    for ch in chars_filtrados:
        centro = (ch["x0"] + ch["x1"]) / 2
        ocupacao[min(faixas - 1, max(0, int(centro / passo)))] += 1

    ini, fim = int(faixas * 0.3), int(faixas * 0.7)
    max_ocup = max(ocupacao[ini:fim]) or 1
    threshold = max(1, max_ocup * 0.05)

    melhor_inicio, melhor_tamanho, atual = None, 0, 0
    for i in range(ini, fim):
        if ocupacao[i] <= threshold:
            atual += 1
            if atual > melhor_tamanho:
                melhor_tamanho, melhor_inicio = atual, i - atual + 1
        else:
            atual = 0
    if melhor_tamanho < 2:
        return None
    # Precisa haver texto dos dois lados
    esquerda = sum(ocupacao[:melhor_inicio])
    direita = sum(ocupacao[melhor_inicio + melhor_tamanho:])
    if esquerda < 20 or direita < 20:
        return None
    x = (melhor_inicio + melhor_tamanho / 2) * passo
    return x, 0.0, pagina.height, False


def encontrar_inicio_colunas(chars, x_div, corpo):
    """Y onde começa o trecho em duas colunas (acima dele o texto ocupa a largura toda).

    Trabalha em faixas horizontais de ~3 linhas, porque as linhas de colunas
    diferentes raramente ficam exatamente na mesma altura.
    """
    if x_div is None or not chars:
        return None
    altura = 3 * corpo
    lados = collections.defaultdict(lambda: [0, 0])
    cruzando = collections.Counter()
    for ch in chars:
        k = int(ch["top"] // altura)
        centro = (ch["x0"] + ch["x1"]) / 2
        lados[k][0 if centro < x_div else 1] += 1
        if abs(centro - x_div) < 0.4 * corpo:
            cruzando[k] += 1

    def boa(k):
        esq, dir_ = lados.get(k, (0, 0))
        return esq >= 3 and dir_ >= 3 and cruzando.get(k, 0) == 0

    ks = sorted(lados)
    for idx, k in enumerate(ks):
        if boa(k):
            proximas = ks[idx:idx + 4]
            if sum(boa(x) for x in proximas) >= min(3, len(proximas)):
                return k * altura
    return None


# ---------------------------------------------------------------------------
# Linhas, sub/sobrescritos, frações e radicais
# ---------------------------------------------------------------------------
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
    normais = [ch for ch in itens if ch.get("size", 0) >= 0.9 * corpo] or itens
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
        # Só a linha mais próxima da barra (evita pegar letras da linha de cima/baixo)
        numerador = [ch for ch in numerador if ch["text"].strip()]
        denominador = [ch for ch in denominador if ch["text"].strip()]
        if not numerador or not denominador:
            continue
        base_num = max(ch["bottom"] for ch in numerador)
        topo_den = min(ch["top"] for ch in denominador)
        numerador = [ch for ch in numerador if ch["bottom"] >= base_num - 2.5]
        denominador = [ch for ch in denominador if ch["top"] <= topo_den + 2.5]
        if base_num > y + 1 or topo_den < y - 1:
            continue
        # Numerador e denominador com tamanhos parecidos (sublinhado de "2º"
        # sob um 'o' pequeno não é fração)
        t_num = statistics.median(ch["size"] for ch in numerador)
        t_den = statistics.median(ch["size"] for ch in denominador)
        if abs(t_num - t_den) > 0.2 * max(t_num, t_den):
            continue
        # Numerador e denominador colados à barra; lacunas "____" desenhadas como
        # linha têm as letras das linhas vizinhas a uma entrelinha de distância
        if y - base_num > 0.7 * t_num or topo_den - y > 0.7 * t_den:
            continue
        fracoes.append({
            "x0": barra["x0"], "x1": barra["x1"], "y": y,
            "numerador": sorted(numerador, key=lambda c: c["x0"]),
            "denominador": sorted(denominador, key=lambda c: c["x0"]),
        })
    return fracoes


def achar_tracos(pagina):
    """Traços horizontais finos (lines e rects): sublinhados, lacunas, barras.
    Ignora os que encostam em traços verticais (bordas de tabela/caixa)."""
    objetos = list(pagina.lines) + list(pagina.rects)
    verticais = [
        (o["x0"], o["top"], o["bottom"]) for o in objetos
        if o["x1"] - o["x0"] < 1.5 and o["bottom"] - o["top"] >= 3
    ]
    # Retângulos com área (caixas, células) também têm bordas verticais
    verticais += [
        (x, o["top"], o["bottom"]) for o in pagina.rects
        if o["x1"] - o["x0"] >= 1.5 and o["bottom"] - o["top"] >= 3
        for x in (o["x0"], o["x1"])
    ]
    tracos = []
    for obj in objetos:
        if obj["bottom"] - obj["top"] < 1.5 and obj["x1"] - obj["x0"] >= 3:
            x0, x1, y = obj["x0"], obj["x1"], obj["top"]
            em_grade = any(
                (abs(vx - x0) < 2 or abs(vx - x1) < 2) and vt - 2 <= y <= vb + 2
                for vx, vt, vb in verticais
            )
            if not em_grade:
                tracos.append((x0, x1, y))
    return tracos


def marcar_sublinhados_e_lacunas(tracos, chars, corpo, fracoes, largura_pagina):
    """Marca ch['sublinhado'] nos caracteres com traço logo abaixo e devolve as
    lacunas ("____" desenhadas como linha ao lado de texto) como tokens."""
    barras = [(f["x0"], f["y"]) for f in fracoes]
    lacunas = []
    for x0, x1, y in tracos:
        if any(abs(x0 - bx) < 0.6 and abs(y - by) < 0.6 for bx, by in barras):
            continue
        largura = x1 - x0
        if largura > 0.6 * largura_pagina:
            continue
        mesma_linha = [c for c in chars if c["text"].strip() and c["top"] <= y <= c["bottom"] + 2.5]
        if not mesma_linha:
            continue
        sobre = [c for c in mesma_linha if x0 - 0.5 <= (c["x0"] + c["x1"]) / 2 <= x1 + 0.5]
        if sobre:
            for c in sobre:
                c["sublinhado"] = True
        elif largura >= 1.0 * corpo and any(
            min(abs(c["x1"] - x0), abs(c["x0"] - x1)) < 4 * corpo for c in mesma_linha
        ):
            lacunas.append({"x0": x0, "x1": x1, "y": y, "lacuna": True, "text": ""})
    return lacunas


# ---------------------------------------------------------------------------
# Renderização de uma linha (texto + LaTeX + negrito/itálico)
# ---------------------------------------------------------------------------
def renderizar_tokens(tokens, corpo, base=None, tamanho=None, topo=False):
    """Renderiza tokens (chars, frações, radicais) de uma linha.

    topo=True: linha final do documento (delimita math com $...$ e aplica
    negrito/itálico). topo=False: conteúdo interno de \\frac/\\sqrt (LaTeX puro).
    """
    if not tokens:
        return ""

    tokens = sorted(tokens, key=lambda t: t["x0"])
    chars = [t for t in tokens if t.get("text") and "size" in t]
    if base is None or tamanho is None:
        base, tamanho = linha_de_base(chars, corpo) if chars else (0.0, corpo)
    # Linha quase toda em fonte pequena (rodapé, legenda): não há sub/sobrescrito
    visiveis = [c for c in chars if c["text"].strip()]
    pequenos = sum(1 for c in visiveis if c["size"] < 0.82 * tamanho)
    sem_scripts = bool(visiveis) and pequenos > 0.5 * len(visiveis)

    pecas = []  # (texto, tipo: txt|esp|math, estilo)
    script = None
    buffer_script = []
    anterior = None

    def espaco():
        if pecas and pecas[-1][1] != "esp":
            pecas.append((" ", "esp", None))

    def fechar():
        nonlocal script, buffer_script
        conteudo = "".join(buffer_script).strip()
        anterior_txt = pecas[-1][0] if pecas and pecas[-1][1] == "txt" else ""
        if script == "sup" and conteudo in ("o", "a", "os", "as") and anterior_txt[-1:].isdigit():
            # Ordinal: 1^{o} -> 1º, 2^{a} -> 2ª
            pecas.append(({"o": "º", "a": "ª", "os": "ºs", "as": "ªs"}[conteudo], "txt", None))
        elif script and conteudo:
            marcador = "_" if script == "sub" else "^"
            pecas.append((f"{marcador}{{{conteudo}}}", "math", None))
        script = None
        buffer_script = []

    def espaco_antes(x0, texto_atual=""):
        if anterior is None:
            return
        vao = x0 - anterior["x1"]
        limite = ESPACO_RELATIVO
        anterior_texto = anterior.get("text", "") or ""
        if anterior_texto and texto_atual and anterior_texto[-1].isalnum() and texto_atual[0].isalnum():
            limite = 0.30
        if vao > limite * corpo:
            espaco()

    for token in tokens:
        if "numerador" in token:
            fechar()
            espaco_antes(token["x0"])
            num = renderizar_tokens(token["numerador"] + token.get("radicais_num", []), corpo)
            den = renderizar_tokens(token["denominador"] + token.get("radicais_den", []), corpo)
            pecas.append((f"\\frac{{{num}}}{{{den}}}", "math", None))
            anterior = token
            continue

        if token.get("radical"):
            fechar()
            espaco_antes(token["x0"])
            pecas.append((f"\\sqrt{{{token['radicando']}}}", "math", None))
            anterior = token
            continue

        if token.get("lacuna"):
            fechar()
            espaco()
            n = max(3, min(15, round((token["x1"] - token["x0"]) / (0.5 * corpo))))
            pecas.append(("_" * n, "lac", None))
            pecas.append((" ", "esp", None))
            anterior = token
            continue

        texto = token["text"]
        if not texto or texto in ABRE_COLCHETE or texto in FECHA_COLCHETE:
            continue
        if not texto.strip():
            fechar()
            espaco()
            anterior = token
            continue

        classe = None if sem_scripts else classificar(token, base, tamanho)
        if classe != script:
            fechar()
            script = classe
        if classe:
            buffer_script.append(texto)
            anterior = token
            continue

        espaco_antes(token["x0"], texto)
        negrito, italico = token.get("estilo") or (False, False)
        pecas.append((texto, "txt", (negrito, italico, bool(token.get("sublinhado")))))
        anterior = token

    fechar()
    if not topo:
        return re.sub(r" {2,}", " ", "".join(p[0] for p in pecas)).strip()
    return montar_linha(pecas)


def _marcar_trechos_math(pecas):
    """Expande cada peça LaTeX para os vizinhos 'matemáticos' (números, operadores,
    letras isoladas) e retorna a lista de flags 'está dentro de $...$'."""
    n = len(pecas)

    def eh_letra(i):
        return 0 <= i < n and pecas[i][1] == "txt" and pecas[i][0].isalpha()

    def mathish(i):
        texto, tipo, _ = pecas[i]
        if tipo in ("math", "esp"):
            return True
        if all(c in OPERADORES_MATH for c in texto):
            return True
        if len(texto) == 1 and texto.isalpha():
            if eh_letra(i - 1) or eh_letra(i + 1):
                return False  # faz parte de uma palavra
            vizinhos = [pecas[j][0] for j in (i - 1, i + 1) if 0 <= j < n]
            if any(v in "()" for v in vizinhos):  # evita "a)" / "(A)"
                return False
            if texto in "aeoéàó":
                # Palavras de uma letra ("e", "a", "o"): só são variável se houver
                # operador do lado ("a = 2", "2 + e")
                def vizinho_real(passo):
                    j = i + passo
                    while 0 <= j < n and pecas[j][1] == "esp":
                        j += passo
                    return pecas[j][0] if 0 <= j < n else ""
                return any(v and v in "=+−-<>≤≥·×÷" for v in (vizinho_real(-1), vizinho_real(1)))
            return True
        return False

    em_math = [False] * n
    for i, (_texto, tipo, _e) in enumerate(pecas):
        if tipo != "math" or em_math[i]:
            continue
        a = i
        while a - 1 >= 0 and mathish(a - 1):
            a -= 1
        b = i
        while b + 1 < n and mathish(b + 1):
            b += 1
        # Corta bordas: espaços, pontuação de frase, parênteses desbalanceados
        while a < i and (pecas[a][1] == "esp" or pecas[a][0] in ",.;:)]"):
            a += 1
        while b > i and (pecas[b][1] == "esp" or pecas[b][0] in ",.;:(["):
            b -= 1
        trecho = "".join(p[0] for p in pecas[a:b + 1])
        while a < i and pecas[a][0] == "(" and trecho.count("(") > trecho.count(")"):
            a += 1
            trecho = trecho[1:]
        while b > i and pecas[b][0] == ")" and trecho.count(")") > trecho.count("("):
            b -= 1
            trecho = trecho[:-1]
        for j in range(a, b + 1):
            em_math[j] = True
    return em_math


def _escapar_markdown(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("*", "\\*").replace("$", "\\$")


MARCAS_ESTILO = {(True, False): "**", (False, True): "*", (True, True): "***"}


def montar_linha(pecas) -> str:
    em_math = _marcar_trechos_math(pecas)

    # 1. Itens finais: ("$...$", "M") | (" ", "esp") | (texto, estilo)
    itens = []
    i, n = 0, len(pecas)
    while i < n:
        if em_math[i]:
            j = i
            while j < n and em_math[j]:
                j += 1
            expr = "".join(p[0] for p in pecas[i:j]).strip()
            expr = re.sub(r" {2,}", " ", expr).replace("°", "^{\\circ}")
            itens.append((f"${expr}$", "M"))
            i = j
            continue
        texto, tipo, estilo = pecas[i]
        if tipo == "esp":
            itens.append((" ", "esp"))
        elif tipo == "lac":
            itens.append((texto.replace("_", "\\_"), None))
        else:
            estilo = estilo if estilo and any(estilo) else None
            itens.append((_escapar_markdown(texto), estilo))
        i += 1

    # 2. Agrupa em corridas do mesmo estilo (espaços entre corridas iguais ficam dentro)
    corridas = []  # [estilo, [textos]]
    for idx, (texto, estilo) in enumerate(itens):
        if estilo == "esp":
            prox = next((e for _t, e in itens[idx + 1:] if e != "esp"), None)
            if corridas and corridas[-1][0] not in (None, "M") and corridas[-1][0] == prox:
                corridas[-1][1].append(texto)
            else:
                corridas.append([None, [texto]])
            continue
        chave = estilo
        if corridas and corridas[-1][0] == chave and chave != "M":
            corridas[-1][1].append(texto)
        else:
            corridas.append([chave, [texto]])

    # 3. Aplica marcas de negrito/itálico
    saida = []
    for estilo, textos in corridas:
        texto = "".join(textos)
        if estilo in (None, "M"):
            saida.append(texto)
            continue
        miolo = texto.strip()
        if not miolo or not any(c.isalnum() for c in miolo):
            saida.append(texto)
            continue
        negrito, italico, sublinhado = estilo
        marca = MARCAS_ESTILO.get((negrito, italico), "")
        abre = ("<u>" if sublinhado else "") + marca
        fecha = marca + ("</u>" if sublinhado else "")
        esq = texto[: len(texto) - len(texto.lstrip())]
        dir_ = texto[len(texto.rstrip()):]
        saida.append(f"{esq}{abre}{miolo}{fecha}{dir_}")

    linha = re.sub(r" {2,}", " ", "".join(saida)).strip()
    return _desembrulhar_rotulo(linha)


def _desembrulhar_rotulo(linha: str) -> str:
    """Tira o número da questão/letra da alternativa de dentro do negrito:
    '**01.**' -> '01.' ; '**01. Texto**' -> '01. **Texto**'."""
    rotulo = r"(\(?[A-Ea-e]\)|\d{1,3}\s?(?:\.|\)|–|-)?)"
    m = re.match(r"^(\*{1,3})" + rotulo + r"\1(\s|$)", linha)
    if m:
        return m.group(2) + m.group(3) + linha[m.end():]
    m = re.match(r"^(\*{1,3})" + rotulo + r"\s+(?=\S)", linha)
    if m:
        return f"{m.group(2)} {m.group(1)}" + linha[m.end():]
    return linha


# ---------------------------------------------------------------------------
# Coluna -> linhas
# ---------------------------------------------------------------------------
def renderizar_coluna(chars, corpo, fracoes, radicais, lacunas=()):
    """Retorna lista de dicts {texto, top, x0, x1, w_primeira} (uma por linha visual)."""
    linhas = agrupar_linhas(chars, corpo)

    consumidos = set()
    extras = {}

    for lacuna in lacunas:
        candidatas = [
            (len(itens), indice) for indice, (_a, itens) in enumerate(linhas)
            if min(c["top"] for c in itens) - 0.5 <= lacuna["y"] <= max(c["bottom"] for c in itens) + 2.5
        ]
        if candidatas:
            extras.setdefault(max(candidatas)[1], []).append(lacuna)

    for radical in radicais:
        candidatos = [
            ch for ch in chars
            if radical["barra_ini"] - 0.6 <= (ch["x0"] + ch["x1"]) / 2 <= radical["barra_fim"] + 0.6
            and abs(ch["bottom"] - radical["y"]) <= 9
        ]
        radical["chars_radicando"] = sorted(candidatos, key=lambda c: c["x0"])

    for fracao in fracoes:
        ids_fracao = {id(ch) for ch in fracao["numerador"] + fracao["denominador"]}
        candidatas = []
        for indice, (_ancora, itens) in enumerate(linhas):
            topo = min(ch["top"] for ch in itens)
            base = max(ch["bottom"] for ch in itens)
            if topo - 0.5 <= fracao["y"] <= base + 0.5:
                normais = sum(1 for ch in itens if id(ch) not in ids_fracao)
                candidatas.append((normais, indice))
        if candidatas:
            hospedeira = max(candidatas)[1]
        else:
            melhor = None
            for indice, (_ancora, itens) in enumerate(linhas):
                centro = (min(ch["top"] for ch in itens) + max(ch["bottom"] for ch in itens)) / 2
                d = abs(centro - fracao["y"])
                if melhor is None or d < melhor[1]:
                    melhor = (indice, d)
            if melhor is None:
                continue
            hospedeira = melhor[0]
        extras.setdefault(hospedeira, []).append(fracao)
        consumidos.update(ids_fracao)

    pendentes = []
    for radical in radicais:
        ids_rad = {id(ch) for ch in radical["chars_radicando"]}
        destino = None
        for fracao in fracoes:
            if ids_rad and ids_rad <= {id(ch) for ch in fracao["numerador"]}:
                fracao.setdefault("radicais_num", []).append(radical)
                destino = "num"
                break
            if ids_rad and ids_rad <= {id(ch) for ch in fracao["denominador"]}:
                fracao.setdefault("radicais_den", []).append(radical)
                destino = "den"
                break
        if destino is None:
            pendentes.append(radical)
        else:
            radical["radicando"] = renderizar_tokens(radical["chars_radicando"], corpo)
            consumidos.update(ids_rad)

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
        consumidos.update(id(ch) for ch in radical["chars_radicando"])
        extras.setdefault(indice_linha, []).append(radical)

    resultado = []
    for indice, (ancora, itens) in enumerate(linhas):
        tokens = [ch for ch in itens if id(ch) not in consumidos]
        tokens.extend(extras.get(indice, []))
        if not tokens:
            continue
        texto = renderizar_tokens(tokens, corpo, *linha_de_base(itens, corpo), topo=True)
        if texto:
            resultado.append({
                "texto": texto,
                "top": ancora,
                "x0": min(t["x0"] for t in tokens),
                "x1": max(t["x1"] for t in tokens),
                "w_primeira": largura_primeira_palavra(itens, corpo),
            })
    return resultado


def largura_primeira_palavra(chars, corpo) -> float:
    cs = sorted((c for c in chars if c.get("text")), key=lambda c: c["x0"])
    while cs and not cs[0]["text"].strip():
        cs.pop(0)
    if not cs:
        return 0.0
    inicio, fim = cs[0]["x0"], cs[0]["x1"]
    for a, b in zip(cs, cs[1:]):
        if not b["text"].strip() or b["x0"] - a["x1"] > ESPACO_RELATIVO * corpo:
            break
        fim = b["x1"]
    return fim - inicio


def juntar_paragrafos(linhas, corpo, borda_direita, largura):
    """Junta uma linha à anterior só quando a quebra foi automática: a primeira
    palavra da linha seguinte não caberia no fim da anterior. Linhas curtas
    (versos, títulos, listas, fim de parágrafo) são preservadas."""
    texto_linhas = [l for l in linhas if not l.get("img")]
    margem_esq = min((l["x0"] for l in texto_linhas), default=0)
    passos = [b["top"] - a["top"] for a, b in zip(texto_linhas, texto_linhas[1:]) if b["top"] > a["top"]]
    entrelinha = statistics.median(passos) if passos else 1.2 * corpo

    saida = []
    anterior = None
    for linha in linhas:
        texto = linha["texto"]
        if linha.get("img"):
            saida.append(texto)
            anterior = None
            continue
        continua = (
            saida and anterior is not None
            and largura > 12 * corpo
            # a 1ª palavra desta linha não caberia no fim da anterior
            and anterior["x1"] + 0.25 * corpo + linha.get("w_primeira", 0) > borda_direita - 1.0 * corpo
            and not RE_INICIO_BLOCO.match(texto)
            and linha["top"] - anterior["top"] <= 1.45 * entrelinha     # sem espaço extra
            and not (                                                   # recuo de 1ª linha
                linha["x0"] - anterior["x0"] > 1.0 * corpo
                and anterior["x0"] - margem_esq < 0.5 * corpo
                and not RE_INICIO_BLOCO.match(anterior["texto"])        # (A) com recuo pendurado
            )
        )
        if continua:
            atual = saida[-1]
            if re.search(r"\w-$", atual):
                if texto.startswith("-"):           # "pé-" + "-rapado" -> "pé-rapado"
                    atual = atual + texto[1:]
                elif texto[:1].islower():           # "apli-" + "cado" -> "aplicado"
                    atual = atual[:-1] + texto
                else:
                    atual = atual + texto
            else:
                atual = atual + " " + texto
            saida[-1] = atual
        else:
            saida.append(texto)
        anterior = linha
    return saida


def eh_alternativa(texto: str) -> bool:
    """Detecta se uma linha é uma alternativa (A), (B), a), etc."""
    texto = texto.lstrip("*")
    m = re.match(r"^\(?([A-E])\)?[\s\.]", texto)
    if not m:
        return False
    resto = texto[m.end():].lstrip()
    if not resto:
        return True
    # "A subjetividade..." (minúscula depois) é palavra, não alternativa
    return resto[0].isupper() or resto[0] in "(\"'*$" or resto[0].isdigit()


def juntar_numeros_de_questao(linhas):
    """Junta número da questão que ficou sozinho na linha com o início do enunciado.

    - CFS/EEAR: "1" + "– Enunciado"
    - VUNESP:   "01." + "Enunciado"
    - Outros:   "12" + "Enunciado"
    """
    saida = []
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
        prox_ok = prox and not RE_MARCADOR.match(prox)

        if prox_ok and linha.isdigit() and len(linha) <= 3 and prox.startswith("–"):
            saida.append(f"{linha} {prox}")
            i += 2
            continue
        if prox_ok and re.match(r"^\d{2,3}\.$", linha) and not re.match(r"^\d", prox):
            saida.append(f"{linha} {prox}")
            i += 2
            continue
        if prox_ok and re.match(r"^\d{1,2}$", linha) and not eh_alternativa(prox) \
                and not re.match(r"^\d{1,2}$", prox):
            saida.append(f"{linha}. {prox}")
            i += 2
            continue
        saida.append(linhas[i])
        i += 1
    return saida


def pos_processar_prova(texto: str) -> str:
    """Limpezas finais por página (alternativas, LaTeX quebrado, linhas vazias)."""
    linhas = [l.strip() for l in texto.split("\n")]

    # Alternativas unidas na mesma linha: "... (B) xxx" -> nova linha
    processadas = []
    for linha in linhas:
        if not RE_MARCADOR.match(linha) and "$" not in linha:
            linha = re.sub(r"\s*/\s*(?=\([A-E]\)\s)", "\n", linha)
            linha = re.sub(r"(\S)\s+(\([A-E]\)\s)", r"\1\n\2", linha)
        processadas.extend(linha.split("\n"))

    # Junta linhas com LaTeX aberto ({ sem fechar)
    saida = []
    for linha in processadas:
        if saida and saida[-1] and not RE_MARCADOR.match(linha) and \
                saida[-1].count("{") > saida[-1].count("}"):
            saida[-1] = saida[-1] + " " + linha
        else:
            saida.append(linha)

    # No máximo uma linha vazia seguida
    resultado = []
    for linha in saida:
        if linha == "" and resultado and resultado[-1] == "":
            continue
        resultado.append(linha)
    return "\n".join(resultado).strip()


# ---------------------------------------------------------------------------
# Imagens
# ---------------------------------------------------------------------------
def coletar_regioes_imagem(pagina) -> List[dict]:
    """Caixas das imagens da página (sem marcas d'água/fundos), mescladas quando
    se sobrepõem (figuras fatiadas em vários pedaços)."""
    W, H = pagina.width, pagina.height
    caixas = []
    for img in pagina.images:
        x0, top = max(0.0, img["x0"]), max(0.0, img["top"])
        x1, bottom = min(W, img["x1"]), min(H, img["bottom"])
        w, h = x1 - x0, bottom - top
        if w < 8 or h < 8:
            continue
        if w * h > 0.85 * W * H:     # fundo de página
            continue
        if eh_marca_dagua(img, H):
            continue
        caixas.append([x0, top, x1, bottom])

    mesclou = True
    while mesclou:
        mesclou = False
        for i in range(len(caixas)):
            for j in range(i + 1, len(caixas)):
                a, b = caixas[i], caixas[j]
                if a[0] - 3 <= b[2] and b[0] - 3 <= a[2] and a[1] - 3 <= b[3] and b[1] - 3 <= a[3]:
                    caixas[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del caixas[j]
                    mesclou = True
                    break
            if mesclou:
                break

    return [{"bbox": tuple(c), "top": c[1]} for c in sorted(caixas, key=lambda c: (c[1], c[0]))]


def _chave_imagem(regiao):
    x0, top, x1, bottom = regiao["bbox"]
    return (round(x0 / 3), round(top / 3), round((x1 - x0) / 3), round((bottom - top) / 3))


def imagens_repetidas(regioes, total_paginas) -> set:
    """Imagens na mesma posição em muitas páginas = logo/cabeçalho/marca d'água."""
    if total_paginas < 3:
        return set()
    paginas_por_chave = collections.defaultdict(set)
    for r in regioes:
        paginas_por_chave[_chave_imagem(r)].add(r["indice_pagina"])
    limite = max(3, 0.5 * total_paginas)
    return {r["id"] for r in regioes if len(paginas_por_chave[_chave_imagem(r)]) >= limite}


def nome_seguro(texto: str) -> str:
    return re.sub(r"[^\w\-]+", "_", texto, flags=re.UNICODE).strip("_") or "prova"


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
def processar_pagina(pagina, pasta_imagens: Optional[Path] = None):
    """Processa uma página.

    Retorna (texto, regioes): o texto contém marcadores ⟦IMG:id⟧ (linha própria)
    na posição de cada imagem; 'regioes' traz a caixa de cada uma.
    O parâmetro pasta_imagens é mantido por compatibilidade e ignorado — as
    imagens são salvas por converter(), que conhece o número das questões.
    """
    W, H = pagina.width, pagina.height
    chars = []
    for ch in pagina.chars:
        if ch["top"] < 50 and ch["size"] < 9:  # marca d'água/carimbo no topo
            continue
        novo = dict(ch)
        novo["text"] = normalizar(ch["text"])
        novo["estilo"] = estilo_fonte(ch.get("fontname"))
        chars.append(novo)

    regioes = coletar_regioes_imagem(pagina)
    for k, r in enumerate(regioes, 1):
        r["id"] = f"{pagina.page_number}-{k}"
        r["pagina"] = pagina.page_number

    if not chars:
        texto = "\n".join(MARCADOR_IMG.format(r["id"]) for r in regioes)
        return texto, regioes

    corpo = tamanho_corpo(chars)
    for r in regioes:
        r["corpo"] = corpo
    divisoria = achar_divisoria(pagina, chars, corpo)
    # Margem direita: a observada ou, se nenhuma linha chega lá (página só com
    # versos/listas), a simétrica da margem esquerda
    margem_esq = min(ch["x0"] for ch in chars)
    direita_pagina = max(max(ch["x1"] for ch in chars), W - margem_esq - corpo)

    # Blocos: (chars, (x_min, x_max, y_min, y_max), borda_direita)
    blocos = []
    if divisoria is None:
        x_div = None
        blocos.append((chars, (0, W, 0, H), direita_pagina))
    else:
        x_div, topo_div, base_div, explicita = divisoria
        if explicita:
            y_ini, y_fim = topo_div - 1, base_div + 1
            # A linha pode começar abaixo do início real das colunas
            y_dens = encontrar_inicio_colunas([c for c in chars if c["top"] < topo_div], x_div, corpo)
            if y_dens is not None and y_dens < y_ini:
                y_ini = y_dens
        else:
            y_ini, y_fim = encontrar_inicio_colunas(chars, x_div, corpo), H + 1
        if y_ini is None:
            x_div = None
            blocos.append((chars, (0, W, 0, H), direita_pagina))
        else:
            cabecalho = [c for c in chars if c["top"] < y_ini]
            meio = [c for c in chars if y_ini <= c["top"] < y_fim]
            rodape = [c for c in chars if c["top"] >= y_fim]
            esquerda = [c for c in meio if (c["x0"] + c["x1"]) / 2 < x_div]
            direita = [c for c in meio if (c["x0"] + c["x1"]) / 2 >= x_div]
            inicio_dir = min((c["x0"] for c in direita), default=x_div)
            borda_esq = max(max((c["x1"] for c in esquerda), default=0),
                            x_div - (inicio_dir - x_div) - corpo)
            blocos.append((cabecalho, (0, W, 0, y_ini), direita_pagina))
            blocos.append((esquerda, (0, x_div, y_ini, y_fim), borda_esq))
            blocos.append((direita, (x_div, W, y_ini, y_fim), direita_pagina))
            blocos.append((rodape, (0, W, y_fim, H + 1), direita_pagina))

    def bloco_de(x, y):
        for idx, (_c, (bx0, bx1, by0, by1), _b) in enumerate(blocos):
            if bx0 <= x < bx1 and by0 <= y < by1:
                return idx
        return len(blocos) - 1

    imgs_por_bloco = collections.defaultdict(list)
    for r in regioes:
        x0, top, x1, _b = r["bbox"]
        imgs_por_bloco[bloco_de((x0 + x1) / 2 if x1 - x0 < 0.6 * W else x0 + 1, top)].append(r)

    todos_radicais = achar_radicais(pagina)
    todos_tracos = achar_tracos(pagina)
    saida = []
    for idx, (bloco, (bx0, bx1, by0, by1), borda) in enumerate(blocos):
        imgs = imgs_por_bloco.get(idx, [])
        if not bloco and not imgs:
            continue
        linhas = []
        if bloco:
            fracoes = achar_fracoes(pagina, bloco)
            radicais = [r for r in todos_radicais if bloco_de(r["x0"], r["y"]) == idx]
            tracos = [t for t in todos_tracos if bloco_de((t[0] + t[1]) / 2, t[2]) == idx]
            lacunas = marcar_sublinhados_e_lacunas(tracos, bloco, corpo, fracoes, W)
            linhas = renderizar_coluna(bloco, corpo, fracoes, radicais, lacunas)
        for r in imgs:
            linhas.append({"texto": MARCADOR_IMG.format(r["id"]), "top": r["top"], "img": True})
        linhas.sort(key=lambda l: l["top"])

        esquerda_bloco = min((l["x0"] for l in linhas if not l.get("img")), default=bx0)
        textos = juntar_paragrafos(linhas, corpo, borda, borda - esquerda_bloco)
        textos = juntar_numeros_de_questao(textos)
        if saida and saida[-1] != "":
            saida.append("")
        saida.extend(textos)

    texto = "\n".join(saida)
    texto = texto.replace("�", "")
    texto = re.sub(r" {2,}", " ", texto)
    return pos_processar_prova(texto), regioes


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------
def _normalizar_cabecalho(linha: str) -> str:
    linha = re.sub(r"[*$\\]", "", linha.lower())
    linha = re.sub(r"\d+", "#", linha)
    # Ordem das palavras ignorada: rodapés de páginas pares/ímpares invertem a ordem
    return " ".join(sorted(linha.split()))


def remover_cabecalhos_repetidos(textos: List[str]) -> List[str]:
    """Remove cabeçalhos/rodapés repetidos, como 'Confidencial até o momento da
    aplicação.' ou 'SOLDADO PM DE 2ª CLASSE – TARDE'.

    Primeiras/últimas 3 linhas: repetidas em >= 40% das páginas.
    Demais linhas: repetidas em >= 60% das páginas.
    """
    if len(textos) < 3:
        return textos

    def visiveis(texto):
        return [l for l in texto.split("\n") if l.strip() and not RE_MARCADOR.match(l.strip())]

    borda, qualquer = collections.Counter(), collections.Counter()
    for texto in textos:
        linhas = visiveis(texto)
        borda.update({_normalizar_cabecalho(l) for l in linhas[:3] + linhas[-3:]})
        # Fora das bordas, só linhas idênticas (sem trocar dígitos): evita apagar
        # alternativas parecidas como "(A) $\frac{1}{2}$" de questões diferentes
        qualquer.update({l.strip() for l in linhas})

    def pode_remover(linha):
        linha = linha.strip()
        return len(linha) >= 4 and "$" not in linha and not RE_INICIO_BLOCO.match(linha)

    n = len(textos)
    rep_borda = {k for k, c in borda.items() if c >= max(3, 0.4 * n)}
    rep_geral = {k for k, c in qualquer.items() if c >= max(3, 0.6 * n) and len(k) >= 8}
    if not rep_borda and not rep_geral:
        return textos

    resultado = []
    for texto in textos:
        linhas = texto.split("\n")
        vis = visiveis(texto)
        nas_bordas = set(vis[:3] + vis[-3:])
        novas = []
        for l in linhas:
            if pode_remover(l) and (
                l.strip() in rep_geral
                or (l in nas_bordas and _normalizar_cabecalho(l) in rep_borda)
            ):
                continue
            novas.append(l)
        resultado.append("\n".join(novas).strip())
    return resultado


_MODELO_PIX2TEX = None


def carregar_pix2tex():
    """Carrega (uma vez por processo) o modelo pix2tex. None se não instalado."""
    global _MODELO_PIX2TEX
    if _MODELO_PIX2TEX is not None:
        return _MODELO_PIX2TEX
    try:
        from pix2tex.cli import LatexOCR
    except ImportError:
        print("[aviso] pix2tex não instalado (pip install pix2tex) — fórmulas em imagem "
              "serão salvas como imagem.", file=sys.stderr)
        return None
    print("Carregando modelo pix2tex (fórmulas em imagem)...", file=sys.stderr)
    _MODELO_PIX2TEX = LatexOCR()
    return _MODELO_PIX2TEX


def parece_formula(regiao, largura_pagina) -> bool:
    x0, top, x1, bottom = regiao["bbox"]
    corpo = regiao.get("corpo", 10)
    return (bottom - top) <= 5 * corpo and (x1 - x0) <= 0.55 * largura_pagina


def resolver_imagens(documento, regioes, ignorar, pdf, output_path, pasta_imagens,
                     modelo_formulas=None, resolucao=200):
    """Troca os marcadores pelas referências Markdown definitivas, salva os PNGs
    nomeados pela questão/alternativa e devolve (documento, manifesto)."""
    stem = nome_seguro(output_path.stem)
    manifesto = []
    usados = collections.Counter()
    questao = None
    alternativa = None
    pagina_atual = None
    saida = []

    for linha in documento.split("\n"):
        m_pag = re.match(r"^<!-- pagina (\d+) -->$", linha)
        if m_pag:
            pagina_atual = int(m_pag.group(1))
            saida.append(linha)
            continue

        m = RE_MARCADOR.match(linha.strip())
        if not m:
            texto = linha.strip()
            mq = RE_QUESTAO.match(texto)
            if mq and not RE_ALTERNATIVA.match(texto):
                q = int(mq.group(1))
                if questao is None or q > questao or q == 1:
                    questao, alternativa = q, None
            ma = RE_ALTERNATIVA.match(texto)
            if texto:
                alternativa = ma.group(1).upper() if ma and questao is not None else None
            saida.append(linha)
            continue

        regiao = regioes.get(m.group(1))
        if regiao is None or regiao["id"] in ignorar:
            continue
        pagina = pdf.pages[regiao["indice_pagina"]]

        if modelo_formulas is not None and parece_formula(regiao, pagina.width):
            try:
                img = pagina.crop(regiao["bbox"], strict=False).to_image(resolution=300).original
                latex = (modelo_formulas(img) or "").strip()
                if latex:
                    saida.append(f"$${latex}$$")
                    continue
            except Exception as e:  # noqa: BLE001
                print(f"[aviso] pix2tex falhou na imagem {regiao['id']}: {e}", file=sys.stderr)

        if pasta_imagens is None:
            continue

        if questao is not None:
            base = f"{stem}_q{questao:02d}" + (f"_alt{alternativa}" if alternativa else "")
            legenda = f"Questão {questao:02d}" + (f" – alternativa {alternativa}" if alternativa else "")
        else:
            base = f"{stem}_pag{regiao['pagina']:02d}"
            legenda = f"Página {regiao['pagina']}"
        usados[base] += 1
        nome = f"{base}_{usados[base]}.png"

        pasta_imagens.mkdir(parents=True, exist_ok=True)
        caminho = pasta_imagens / nome
        try:
            pagina.crop(regiao["bbox"], strict=False).to_image(resolution=resolucao).save(caminho, format="PNG")
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] falha ao salvar {nome}: {e}", file=sys.stderr)
            continue

        rel = Path(os.path.relpath(caminho, output_path.parent)).as_posix()
        saida.append(f"![{legenda} – figura {usados[base]}]({rel})")
        x0, top, x1, bottom = regiao["bbox"]
        manifesto.append({
            "arquivo": nome,
            "markdown": rel,
            "pagina": regiao["pagina"],
            "questao": questao,
            "alternativa": alternativa,
            "x": round(x0, 1), "y": round(top, 1),
            "largura": round(x1 - x0, 1), "altura": round(bottom - top, 1),
        })

    return "\n".join(saida), manifesto


def limpar_documento(texto: str) -> str:
    # "**a** **b**" -> "**a b**"  (sem tocar em *** ou em itálico+negrito)
    texto = re.sub(r"(?<!\*)\*\*([ \t]+)\*\*(?!\*)", r"\1", texto)
    texto = re.sub(r"(?<![*\\])\*([ \t]+)\*(?!\*)", r"\1", texto)
    texto = re.sub(r"</u>([ \t]+)<u>", r"\1", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() + "\n"


def converter(
    pdf_path: Path,
    output_path: Path,
    paginas: Optional[List[int]] = None,
    pasta_imagens: Optional[Path] = None,
    formulas_imagem: bool = False,
    progresso: Optional[Callable[[int, int], None]] = None,
) -> Dict:
    """Converte um PDF vetorial em Markdown. Retorna um resumo (dict)."""
    pdf_path, output_path = Path(pdf_path), Path(output_path)
    with pdf_open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        alvos = [i for i in (paginas if paginas is not None else range(total)) if 0 <= i < total]
        textos, regioes = [], {}
        for n, indice in enumerate(alvos, 1):
            texto, regs = processar_pagina(pdf.pages[indice])
            for r in regs:
                r["indice_pagina"] = indice
                regioes[r["id"]] = r
            textos.append(texto)
            if progresso:
                progresso(n, len(alvos))

        textos = remover_cabecalhos_repetidos(textos)
        ignorar = imagens_repetidas(list(regioes.values()), len(alvos))
        documento = "\n\n".join(f"<!-- pagina {i + 1} -->\n{t}" for i, t in zip(alvos, textos))

        modelo = carregar_pix2tex() if formulas_imagem else None
        if pasta_imagens is not None and pasta_imagens.exists():
            for antigo in pasta_imagens.glob(f"{nome_seguro(output_path.stem)}_*.png"):
                antigo.unlink()
        documento, manifesto = resolver_imagens(
            documento, regioes, ignorar, pdf, output_path, pasta_imagens, modelo
        )

    documento = limpar_documento(documento)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(documento, encoding="utf-8")
    if pasta_imagens is not None and manifesto:
        (pasta_imagens / "manifest.json").write_text(
            json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return {
        "markdown": str(output_path),
        "caracteres": len(documento),
        "paginas": len(alvos),
        "imagens": len(manifesto),
        "pasta_imagens": str(pasta_imagens) if manifesto else None,
    }


def converter_pdf(pdf_path, output_path, paginas=None, pasta_imagens=None, formulas_imagem=False) -> int:
    """Compatibilidade: retorna o número de caracteres."""
    return converter(pdf_path, output_path, paginas, pasta_imagens, formulas_imagem)["caracteres"]


def converter_hibrido(pdf_path, output_path, paginas=None, pasta_imagens=None) -> int:
    """Compatibilidade: pdfplumber + pix2tex para fórmulas em imagem."""
    return converter_pdf(pdf_path, output_path, paginas, pasta_imagens, formulas_imagem=True)


# ---------------------------------------------------------------------------
# Nougat OCR (PDF escaneado) — usa o CLI do Nougat instalado em .venv-nougat
# ---------------------------------------------------------------------------
def achar_nougat() -> Optional[str]:
    raiz = Path(__file__).resolve().parent / ".venv-nougat"
    for candidato in (raiz / "Scripts" / "nougat.exe", raiz / "bin" / "nougat"):
        if candidato.exists():
            return str(candidato)
    return shutil.which("nougat")


def converter_com_nougat(pdf_path: Path, output_path: Path, paginas: Optional[List[int]] = None) -> int:
    """Converte PDF escaneado com Nougat. Retorna número de caracteres (0 se indisponível)."""
    exe = achar_nougat()
    if not exe:
        print("Erro: Nougat não encontrado. Rode: python install_nougat.py", file=sys.stderr)
        return 0
    pdf_path, output_path = Path(pdf_path), Path(output_path)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [exe, str(pdf_path), "-o", tmp, "--markdown"]
        if paginas:
            cmd += ["-p", ",".join(str(p + 1) for p in paginas)]
        print("Rodando Nougat (pode demorar)...", file=sys.stderr)
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print("Erro: Nougat falhou.", file=sys.stderr)
            return 0
        saidas = list(Path(tmp).glob("*.mmd"))
        if not saidas:
            return 0
        texto = saidas[0].read_text(encoding="utf-8")
    # Nougat usa \( \) e \[ \]; padroniza para $ e $$
    texto = re.sub(r"\\\((.+?)\\\)", r"$\1$", texto)
    texto = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", texto, flags=re.S)
    output_path.write_text(texto, encoding="utf-8")
    return len(texto)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="exam2md - Prova em PDF para Markdown com LaTeX + imagens")
    parser.add_argument("pdf", type=Path, help="Arquivo PDF de entrada")
    parser.add_argument("-o", "--output", type=Path, help="Markdown de saída (padrão: <pdf>.md)")
    parser.add_argument("--pages", help="Páginas 1-based, ex.: 1,2,3 ou 5-10")
    parser.add_argument("--ocr", action="store_true", help="Nougat OCR (PDF escaneado)")
    parser.add_argument("--hybrid", "--formulas-imagem", dest="hybrid", action="store_true",
                        help="Converte fórmulas em imagem para LaTeX com pix2tex")
    parser.add_argument("--no-images", action="store_true", help="Não extrai imagens")
    parser.add_argument("--save-images", action="store_true", help=argparse.SUPPRESS)  # padrão agora
    parser.add_argument("--images-dir", type=Path, help="Pasta das imagens (padrão: <md>_images/)")
    args = parser.parse_args()
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001
            pass

    if not args.pdf.is_file():
        print(f"Erro: arquivo não encontrado: {args.pdf}", file=sys.stderr)
        return 2

    output_path = args.output or args.pdf.with_suffix(".md")
    pasta_imagens = None
    if not args.no_images:
        pasta_imagens = args.images_dir or output_path.parent / f"{output_path.stem}_images"
    paginas = parse_paginas(args.pages)

    if args.ocr:
        chars = converter_com_nougat(args.pdf, output_path, paginas)
        if not chars:
            return 1
        print(f"OK: {output_path} ({chars} caracteres)")
        return 0

    resumo = converter(args.pdf, output_path, paginas, pasta_imagens, formulas_imagem=args.hybrid)
    msg = f"OK: {output_path} ({resumo['caracteres']} caracteres, {resumo['paginas']} páginas)"
    if resumo["imagens"]:
        msg += f" | {resumo['imagens']} imagens em {resumo['pasta_imagens']}"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
