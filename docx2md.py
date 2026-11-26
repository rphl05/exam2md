"""Provas em Word (.docx) -> Markdown com LaTeX + imagens nomeadas por questão.

Lê o XML do .docx direto (só biblioteca padrão + Pillow), sem depender do Word:

- numeração automática do Word (questões "01", alternativas "a)", itens "I-"),
  calculada como o Word calcula — o número não existe no texto do documento;
- negrito, itálico, sublinhado, sobrescrito/subscrito (x² -> $x^{2}$, 1º);
- equações do Word (OMML) convertidas para LaTeX exato, sem OCR;
- caracteres da fonte Symbol (→, ≤, π...) que ficam invisíveis se lidos crus;
- caixas de texto (sem duplicar a versão "compatível" que o Word guarda junto);
- imagens (PNG/JPG/GIF; WMF/EMF do Editor de Equações antigo viram PNG quando
  o sistema consegue desenhá-las), nomeadas pela questão/alternativa;
- tabelas de dados viram tabelas Markdown; tabelas usadas só para diagramar
  (com questões dentro) são "achatadas";
- notas de rodapé no fim do documento.
"""

import collections
import io
import json
import os
import posixpath
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
V = "{urn:schemas-microsoft-com:vml}"
O = "{urn:schemas-microsoft-com:office:office}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
WPG = "{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}"

EMU_POR_CM = 360000

# ---------------------------------------------------------------------------
# Fonte Symbol: o Word guarda os caracteres na área privada (U+F020–U+F0FF)
# ---------------------------------------------------------------------------
_SYMBOL = dict(zip(range(0x20, 0x7F),
    " !∀#∃%&∋()∗+,−./0123456789:;<=>?≅ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ[∴]⊥_‾αβχδεφγηιϕκλμνοπθρστυϖωξψζ{|}∼"))
_SYMBOL.update(zip(range(0xA0, 0xFF),
    "€ϒ′≤⁄∞ƒ♣♦♥♠↔←↑→↓°±″≥×∝∂•÷≠≡≈…⏐⎯↵ℵℑℜ℘⊗⊕∅∩∪⊃⊇⊄⊂⊆∈∉∠∇®©™∏√⋅¬∧∨⇔⇐⇑⇒⇓◊〈®©™∑⎛⎜⎝⎡⎢⎣⎧⎨⎩⎪ 〉∫⌠⎮⌡⎞⎟⎠⎤⎥⎦⎫⎬⎭"))


def simbolo(ch, fonte=None):
    """Converte um caractere da fonte Symbol para Unicode."""
    cp = ord(ch)
    if 0xF020 <= cp <= 0xF0FF:
        cp -= 0xF000
    elif not (fonte and fonte.lower() == "symbol"):
        return ch
    return _SYMBOL.get(cp, ch)


# ---------------------------------------------------------------------------
# Unicode -> LaTeX (equações)
# ---------------------------------------------------------------------------
_GREGO = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
          "omicron pi rho varsigma sigma tau upsilon varphi chi psi omega").split()
_LATEX = {chr(0x3B1 + i): "\\" + n for i, n in enumerate(_GREGO) if n != "omicron"}
_LATEX.update({"ο": "o", "ε": "\\varepsilon", "ϵ": "\\epsilon", "ϕ": "\\phi", "ϑ": "\\vartheta", "ϖ": "\\varpi"})
_LATEX.update({"Γ": "\\Gamma", "Δ": "\\Delta", "Θ": "\\Theta", "Λ": "\\Lambda", "Ξ": "\\Xi", "Π": "\\Pi",
               "Σ": "\\Sigma", "Υ": "\\Upsilon", "Φ": "\\Phi", "Ψ": "\\Psi", "Ω": "\\Omega"})
_LATEX.update({
    "×": "\\times", "÷": "\\div", "·": "\\cdot", "⋅": "\\cdot", "∙": "\\cdot", "±": "\\pm", "∓": "\\mp",
    "≤": "\\leq", "≥": "\\geq", "≠": "\\neq", "≈": "\\approx", "≡": "\\equiv", "∼": "\\sim", "≅": "\\cong",
    "∝": "\\propto", "∞": "\\infty", "∂": "\\partial", "∇": "\\nabla", "∈": "\\in", "∉": "\\notin",
    "∋": "\\ni", "⊂": "\\subset", "⊃": "\\supset", "⊆": "\\subseteq", "⊇": "\\supseteq", "⊄": "\\not\\subset",
    "∪": "\\cup", "∩": "\\cap", "∅": "\\emptyset", "∀": "\\forall", "∃": "\\exists", "¬": "\\neg",
    "∧": "\\wedge", "∨": "\\vee", "→": "\\rightarrow", "←": "\\leftarrow", "↔": "\\leftrightarrow",
    "⇒": "\\Rightarrow", "⇐": "\\Leftarrow", "⇔": "\\Leftrightarrow", "↑": "\\uparrow", "↓": "\\downarrow",
    "⟶": "\\longrightarrow", "↦": "\\mapsto", "°": "^{\\circ}", "′": "'", "″": "''", "…": "\\ldots",
    "⋯": "\\cdots", "⋮": "\\vdots", "∑": "\\sum", "∏": "\\prod", "∫": "\\int", "∬": "\\iint", "∮": "\\oint",
    "−": "-", "∗": "*", "∘": "\\circ", "⊥": "\\perp", "∥": "\\parallel", "∠": "\\angle", "△": "\\triangle",
    "ℝ": "\\mathbb{R}", "ℕ": "\\mathbb{N}", "ℤ": "\\mathbb{Z}", "ℚ": "\\mathbb{Q}", "ℂ": "\\mathbb{C}",
    "〈": "\\langle", "〉": "\\rangle", "⟨": "\\langle", "⟩": "\\rangle", "‖": "\\|", "⌊": "\\lfloor",
    "⌋": "\\rfloor", "⌈": "\\lceil", "⌉": "\\rceil", "%": "\\%", "#": "\\#", "&": "\\&", "{": "\\{",
    "}": "\\}", "_": "\\_", "$": "\\$", " ": "~", " ": "\\,", "⁡": "", "⁢": "",
    "⁣": "", "​": "", "√": "\\surd", "∴": "\\therefore", "ℓ": "\\ell", "ℏ": "\\hbar", "Å": "\\AA",
})
_FUNCOES = set("sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln lg exp lim max min "
               "sup inf det dim ker gcd deg arg".split())
_SEN = {"sen": "\\operatorname{sen}", "tg": "\\operatorname{tg}", "cotg": "\\operatorname{cotg}",
        "cossec": "\\operatorname{cossec}", "arcsen": "\\operatorname{arcsen}", "arctg": "\\operatorname{arctg}"}


def latex_char(ch):
    if ch in _LATEX:
        cmd = _LATEX[ch]
        return cmd + " " if re.fullmatch(r"\\[A-Za-z]+", cmd) else cmd
    if 0x1D400 <= ord(ch) <= 0x1D7FF:  # letras matemáticas itálicas/negrito (𝑥 -> x)
        return unicodedata.normalize("NFKC", ch)
    return ch


def latex_texto(t):
    return "".join(latex_char(c) for c in t)


# ---------------------------------------------------------------------------
# OMML (equações do Word) -> LaTeX
# ---------------------------------------------------------------------------
_DELIM = {"(": "(", ")": ")", "[": "[", "]": "]", "{": "\\{", "}": "\\}", "|": "|", "‖": "\\|",
          "〈": "\\langle", "〉": "\\rangle", "⟨": "\\langle", "⟩": "\\rangle", "⌊": "\\lfloor",
          "⌋": "\\rfloor", "⌈": "\\lceil", "⌉": "\\rceil", "": "."}
_ACENTOS = {"̂": "\\hat", "̃": "\\tilde", "̄": "\\bar", "̅": "\\overline",
            "̇": "\\dot", "̈": "\\ddot", "⃗": "\\vec", "⃑": "\\vec", "́": "\\acute",
            "̀": "\\grave", "̆": "\\breve", "̌": "\\check", "⃖": "\\overleftarrow",
            "⃡": "\\overleftrightarrow", "→": "\\vec", "¯": "\\overline"}


def _val(el, caminho, padrao=None):
    alvo = el.find(caminho) if el is not None else None
    if alvo is None:
        return padrao
    return alvo.get(M + "val", alvo.get(W + "val", padrao))


def _grupo(s):
    """Envolve em {} quando o trecho tem mais de um "átomo" (para ^ e _)."""
    s = s.strip()
    if len(s) == 1 or re.fullmatch(r"\\[A-Za-z]+ ?|\d+|\\left.*\\right.|\{.*\}", s, re.S):
        return s
    return "{" + s + "}"


def omml(el, matriz_eq=False):
    """Converte um nó OMML (m:oMath ou filho) para LaTeX."""
    tag = el.tag
    filhos = lambda nome: el.find(M + nome)  # noqa: E731
    conv = lambda x: omml(x, matriz_eq) if x is not None else ""  # noqa: E731

    if tag == M + "r":
        t = "".join(x.text or "" for x in el.iter(M + "t"))
        rpr = el.find(M + "rPr")
        if rpr is not None and rpr.find(M + "nor") is not None:
            return "\\text{" + t + "}"
        palavra = t.strip()
        if palavra in _FUNCOES:
            return "\\" + palavra + " "
        if palavra in _SEN:
            return _SEN[palavra] + " "
        if matriz_eq:  # "&" alinha colunas em sistemas/matrizes
            return "".join("&" if c == "&" else latex_char(c) for c in t)
        if _val(rpr, M + "sty") == "p" and re.fullmatch(r"[A-Za-z]{2,}", palavra):
            return "\\mathrm{" + palavra + "}"
        return latex_texto(t)
    if tag == W + "r":  # texto comum dentro da equação
        t = "".join(x.text or "" for x in el.iter(W + "t"))
        return "\\text{" + t + "}" if t.strip() else t
    if tag == M + "f":
        tipo = _val(el.find(M + "fPr"), M + "type", "bar")
        num, den = conv(filhos("num")), conv(filhos("den"))
        if tipo == "lin":
            return f"{_grupo(num)}/{_grupo(den)}"
        if tipo == "noBar":
            return "{" + num + " \\atop " + den + "}"
        return "\\frac{" + num + "}{" + den + "}"
    if tag == M + "sSup":
        return _grupo(conv(filhos("e"))) + "^{" + conv(filhos("sup")) + "}"
    if tag == M + "sSub":
        return _grupo(conv(filhos("e"))) + "_{" + conv(filhos("sub")) + "}"
    if tag == M + "sSubSup":
        return _grupo(conv(filhos("e"))) + "_{" + conv(filhos("sub")) + "}^{" + conv(filhos("sup")) + "}"
    if tag == M + "sPre":
        return "{}_{" + conv(filhos("sub")) + "}^{" + conv(filhos("sup")) + "}" + conv(filhos("e"))
    if tag == M + "rad":
        oculto = _val(el.find(M + "radPr"), M + "degHide") in ("1", "on", "true")
        grau = conv(filhos("deg")).strip()
        corpo = conv(filhos("e"))
        return ("\\sqrt[" + grau + "]{" if grau and not oculto else "\\sqrt{") + corpo + "}"
    if tag == M + "d":
        pr = el.find(M + "dPr")
        ini, fim = _val(pr, M + "begChr", "("), _val(pr, M + "endChr", ")")
        sep = _val(pr, M + "sepChr", "|")
        partes = [conv(e) for e in el.findall(M + "e")]
        meio = (" " + (_DELIM.get(sep, sep) if sep != "|" else "\\mid") + " ").join(partes)
        return f"\\left{_DELIM.get(ini, latex_texto(ini))} {meio} \\right{_DELIM.get(fim, latex_texto(fim))}"
    if tag == M + "nary":
        pr = el.find(M + "naryPr")
        op = _val(pr, M + "chr", "∫")
        s = latex_char(op).strip()
        if _val(pr, M + "subHide") not in ("1", "on", "true"):
            s += "_{" + conv(filhos("sub")) + "}"
        if _val(pr, M + "supHide") not in ("1", "on", "true"):
            s += "^{" + conv(filhos("sup")) + "}"
        return s + " " + conv(filhos("e"))
    if tag == M + "func":
        return conv(filhos("fName")).strip() + " " + conv(filhos("e"))
    if tag in (M + "limLow", M + "limUpp"):
        base, lim = conv(filhos("e")).strip(), conv(filhos("lim"))
        if base in ("\\lim", "\\max", "\\min", "\\sup", "\\inf") or tag == M + "limLow" and base.startswith("\\lim"):
            return base + ("_{" if tag == M + "limLow" else "^{") + lim + "}"
        return ("\\underset{" if tag == M + "limLow" else "\\overset{") + lim + "}{" + base + "}"
    if tag == M + "acc":
        ch = _val(el.find(M + "accPr"), M + "chr", "̂")
        corpo = conv(filhos("e"))
        cmd = _ACENTOS.get(ch, "\\hat")
        if cmd == "\\bar" and len(corpo.strip()) > 1:
            cmd = "\\overline"
        return cmd + "{" + corpo + "}"
    if tag == M + "bar":
        pos = _val(el.find(M + "barPr"), M + "pos", "top")
        return ("\\underline{" if pos == "bot" else "\\overline{") + conv(filhos("e")) + "}"
    if tag == M + "groupChr":
        pr = el.find(M + "groupChrPr")
        ch, pos = _val(pr, M + "chr", "⏟"), _val(pr, M + "pos", "bot")
        corpo = conv(filhos("e"))
        if ch == "⏟":
            return "\\underbrace{" + corpo + "}"
        if ch == "⏞":
            return "\\overbrace{" + corpo + "}"
        return ("\\underset{" if pos == "bot" else "\\overset{") + latex_char(ch).strip() + "}{" + corpo + "}"
    if tag == M + "borderBox":
        return "\\boxed{" + conv(filhos("e")) + "}"
    if tag == M + "eqArr":
        linhas = [omml(e, True) for e in el.findall(M + "e")]
        return "\\begin{aligned}" + " \\\\ ".join(linhas) + "\\end{aligned}"
    if tag == M + "m":
        linhas = [" & ".join(omml(e, True) for e in mr.findall(M + "e")) for mr in el.findall(M + "mr")]
        return "\\begin{matrix}" + " \\\\ ".join(linhas) + "\\end{matrix}"
    if tag.endswith("Pr") or tag in (M + "ctrlPr",):
        return ""
    # m:oMath, m:e, m:num, m:sup, m:box, m:phant e qualquer outro contêiner
    return "".join(omml(c, matriz_eq) for c in el)


def omml_latex(el):
    latex = omml(el)
    latex = re.sub(r"[ \t]{2,}", " ", latex).strip()
    return latex


# ---------------------------------------------------------------------------
# Numeração automática (listas do Word)
# ---------------------------------------------------------------------------
def _romano(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    s = ""
    for v, r in vals:
        while n >= v:
            s, n = s + r, n - v
    return s


def _letra(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s


def formatar_numero(n, fmt):
    if fmt in ("decimal", "decimalEnclosedParen", "decimalEnclosedCircle", None):
        return str(n)
    if fmt == "decimalZero":
        return f"{n:02d}"
    if fmt == "lowerLetter":
        return _letra(n)
    if fmt == "upperLetter":
        return _letra(n).upper()
    if fmt == "lowerRoman":
        return _romano(n).lower()
    if fmt == "upperRoman":
        return _romano(n)
    if fmt == "ordinal":
        return f"{n}º"
    return str(n)


class Numeracao:
    """Reproduz a contagem do Word: contadores por lista abstrata, níveis
    inferiores reiniciam quando um superior avança, startOverride reinicia."""

    def __init__(self, xml, estilos):
        self.niveis = {}    # abstractNumId -> {ilvl: dict}
        self.num_abs = {}   # numId -> abstractNumId
        self.overrides = {}  # numId -> {ilvl: start}
        self.contadores = collections.defaultdict(dict)  # abstractNumId -> {ilvl: n}
        self.vistos = set()
        if xml is None:
            return
        link_estilo = {}
        for a in xml.findall(W + "abstractNum"):
            aid = a.get(W + "abstractNumId")
            lv = {}
            for l in a.findall(W + "lvl"):
                ilvl = int(l.get(W + "ilvl", "0"))
                lv[ilvl] = {
                    "start": int(_val(l, W + "start", "1") or 1),
                    "fmt": _val(l, W + "numFmt", "decimal"),
                    "texto": _val(l, W + "lvlText", ""),
                    "restart": _val(l, W + "lvlRestart"),
                    "legal": l.find(W + "isLgl") is not None,
                }
            self.niveis[aid] = lv
            link = _val(a, W + "numStyleLink")
            if link:
                link_estilo[aid] = link
        for n in xml.findall(W + "num"):
            nid = n.get(W + "numId")
            self.num_abs[nid] = _val(n, W + "abstractNumId")
            ov = {}
            for o in n.findall(W + "lvlOverride"):
                st = _val(o, W + "startOverride")
                if st is not None:
                    ov[int(o.get(W + "ilvl", "0"))] = int(st)
            self.overrides[nid] = ov
        # Listas definidas por estilo (numStyleLink -> estilo -> numId -> abstrato real)
        for aid, est in link_estilo.items():
            num = estilos.num_do_estilo(est)
            if num and self.num_abs.get(num[0]) and self.num_abs[num[0]] != aid:
                for nid, a in list(self.num_abs.items()):
                    if a == aid:
                        self.num_abs[nid] = self.num_abs[num[0]]

    def rotulo(self, num_id, ilvl):
        """Avança o contador e devolve (rótulo, formato do nível)."""
        aid = self.num_abs.get(num_id)
        if aid is None or aid not in self.niveis or num_id == "0":
            return None, None
        niveis = self.niveis[aid]
        nivel = niveis.get(ilvl)
        if nivel is None:
            return None, None
        cont = self.contadores[aid]
        if num_id not in self.vistos:
            self.vistos.add(num_id)
            for lv, st in self.overrides.get(num_id, {}).items():
                cont[lv] = st - 1
                for inferior in [k for k in cont if k > lv]:
                    del cont[inferior]
        cont[ilvl] = cont.get(ilvl, nivel["start"] - 1) + 1
        for inferior in [k for k in cont if k > ilvl]:
            restart = niveis.get(inferior, {}).get("restart")
            if restart is None or restart != "0" and int(restart) - 1 <= ilvl:
                del cont[inferior]
        if nivel["fmt"] == "bullet":
            return "-", "bullet"
        if nivel["fmt"] == "none":
            return "", "none"

        def troca(m):
            k = int(m.group(1)) - 1
            n = cont.get(k, niveis.get(k, {}).get("start", 1))
            fmt = "decimal" if nivel["legal"] else niveis.get(k, {}).get("fmt", "decimal")
            return formatar_numero(n, fmt)

        return re.sub(r"%(\d)", troca, nivel["texto"]).strip(), nivel["fmt"]


# ---------------------------------------------------------------------------
# Estilos (negrito/itálico herdados, títulos, numeração por estilo)
# ---------------------------------------------------------------------------
class Estilos:
    def __init__(self, xml):
        self.estilos = {}
        self.padrao_par = None
        if xml is None:
            return
        for s in xml.findall(W + "style"):
            sid = s.get(W + "styleId")
            ppr, rpr = s.find(W + "pPr"), s.find(W + "rPr")
            num = ppr.find(W + "numPr") if ppr is not None else None
            self.estilos[sid] = {
                "base": _val(s, W + "basedOn"),
                "rpr": _props_run(rpr) if rpr is not None else {},
                "nivel_titulo": _val(ppr, W + "outlineLvl") if ppr is not None else None,
                "num": (_val(num, W + "numId"), int(_val(num, W + "ilvl", "0") or 0)) if num is not None else None,
            }
            if s.get(W + "type") == "paragraph" and s.get(W + "default") in ("1", "true"):
                self.padrao_par = sid

    def _cadeia(self, sid):
        vistos = []
        while sid and sid in self.estilos and sid not in vistos:
            vistos.append(sid)
            sid = self.estilos[sid]["base"]
        return vistos

    def props(self, sid):
        p = {}
        for s in reversed(self._cadeia(sid)):
            p.update(self.estilos[s]["rpr"])
        return p

    def nivel_titulo(self, sid):
        for s in self._cadeia(sid):
            n = self.estilos[s]["nivel_titulo"]
            if n is not None:
                return int(n)
        m = re.fullmatch(r"(?:Heading|Ttulo|Titulo|Título)(\d)", sid or "", re.I)
        return int(m.group(1)) - 1 if m else None

    def num_do_estilo(self, sid):
        for s in self._cadeia(sid):
            if self.estilos[s]["num"]:
                return self.estilos[s]["num"]
        return None


def _liga(el):
    if el is None:
        return None
    return el.get(W + "val", "1") not in ("0", "false", "off", "none")


def _props_run(rpr):
    p = {}
    for chave, tag in (("b", "b"), ("i", "i"), ("caps", "caps"), ("oculto", "vanish"), ("riscado", "strike")):
        el = rpr.find(W + tag)
        if el is not None:
            p[chave] = _liga(el)
    u = rpr.find(W + "u")
    if u is not None:
        p["u"] = u.get(W + "val", "single") not in ("none", "0")
    va = rpr.find(W + "vertAlign")
    if va is not None:
        p["va"] = va.get(W + "val")
    f = rpr.find(W + "rFonts")
    if f is not None and (f.get(W + "ascii") or f.get(W + "hAnsi")):
        p["fonte"] = f.get(W + "ascii") or f.get(W + "hAnsi")
    return p


# ---------------------------------------------------------------------------
# Markdown inline
# ---------------------------------------------------------------------------
def escapar(t):
    return re.sub(r"([\\*_$`])", r"\\\1", t)


def _envolver(texto, b, i, u):
    """Aplica marcadores deixando os espaços de fora (**a ** é inválido)."""
    m = re.match(r"^(\s*)(.*?)(\s*)$", texto, re.S)
    ini, meio, fim = m.groups()
    if not meio:
        return texto
    if u:
        meio = f"<u>{meio}</u>"
    marca = "***" if b and i else "**" if b else "*" if i else ""
    return f"{ini}{marca}{meio}{marca}{fim}"


_ORDINAIS = {"o": "º", "a": "ª", "º": "º", "ª": "ª", "os": "ºs", "as": "ªs", "°": "º"}


def _base_expoente(texto):
    """Separa o fim do texto que serve de base para ^ ou _ (ex.: 'f(x) = x' -> 'x')."""
    if texto.endswith(")"):
        nivel = 0
        for k in range(len(texto) - 1, -1, -1):
            nivel += {")": 1, "(": -1}.get(texto[k], 0)
            if nivel == 0:
                m = re.search(r"[\w.]*$", texto[:k])
                k = m.start() if m else k
                return texto[:k], texto[k:]
    m = re.search(r"[\w.,']*\w$|[\w]$", texto)
    if not m:
        return texto, ""
    return texto[:m.start()], m.group(0)


def renderizar_inline(itens):
    """itens: lista de (tipo, valor, props). Junta trechos de mesmo estilo e
    trata sobrescrito/subscrito. Devolve a linha em Markdown."""
    # 1) junta texto consecutivo com o mesmo estilo
    juntos = []
    for tipo, valor, p in itens:
        if tipo == "t" and juntos and juntos[-1][0] == "t" and juntos[-1][2] == p:
            juntos[-1] = ("t", juntos[-1][1] + valor, p)
        else:
            juntos.append((tipo, valor, p))

    saida = []  # (texto já em Markdown, cru_para_base_ou_None)
    for tipo, valor, p in juntos:
        if tipo != "t":
            saida.append((valor, None))
            continue
        va = p.get("va") if p else None
        if va in ("superscript", "subscript") and valor.strip():
            exp = valor.strip()
            cru = saida[-1][1] if saida and saida[-1][1] is not None else None
            if cru is not None:
                antes, base = _base_expoente(cru)
            else:
                antes, base = "", ""
            if va == "superscript" and exp.lower() in _ORDINAIS and re.search(r"\d$", base or ""):
                saida.append((escapar(_ORDINAIS[exp.lower()]), None))
                continue
            if va == "superscript" and exp.lower() in ("st", "nd", "rd", "th") and re.search(r"\d$", base or ""):
                saida.append((exp, None))
                continue
            palavra = re.fullmatch(r"[A-Za-zÀ-ÿ]{3,}", base or "")
            if palavra or not base and not saida:
                # nota/chamada ("palavra¹") ou expoente solto: HTML simples
                tagh = "sup" if va == "superscript" else "sub"
                saida.append((f"<{tagh}>{escapar(exp)}</{tagh}>", None))
                continue
            # tira a base do trecho anterior e monta $base^{exp}$
            if base:
                md_ant, cru_ant = saida.pop()
                prefixo_md = md_ant[: len(md_ant) - len(escapar(base))] if md_ant.endswith(escapar(base)) else None
                if prefixo_md is None:  # base dentro de marcação (**x**): mantém o texto e só anexa
                    saida.append((md_ant, cru_ant))
                    base_tex = ""
                else:
                    saida.append((prefixo_md, antes))
                    base_tex = latex_texto(base)
            else:
                base_tex = ""
            op = "^" if va == "superscript" else "_"
            saida.append((f"${base_tex}{op}{{{latex_texto(exp)}}}$", None))
            continue
        b, i, u = (p or {}).get("b"), (p or {}).get("i"), (p or {}).get("u")
        saida.append((_envolver(escapar(valor), b, i, u), valor if not (b or i or u) else None))
    linha = "".join(s for s, _ in saida)
    # $x^{2}$$y$ -> separa fórmulas coladas para não virar $$ (bloco)
    linha = re.sub(r"(?<=[^\s$])\$\$(?=[^\s$])", "$ $", linha)
    return linha


# ---------------------------------------------------------------------------
# Leitura do documento
# ---------------------------------------------------------------------------
class Pacote:
    def __init__(self, caminho):
        self.zip = zipfile.ZipFile(caminho)
        self.nomes = set(self.zip.namelist())
        self.doc = self._xml("word/document.xml")
        if self.doc is None:
            raise ValueError("arquivo .docx inválido (sem word/document.xml)")
        self.rels = self._rels("word/_rels/document.xml.rels")
        self.estilos = Estilos(self._xml("word/styles.xml"))
        self.numeracao = Numeracao(self._xml("word/numbering.xml"), self.estilos)
        self.notas = {}
        notas = self._xml("word/footnotes.xml")
        if notas is not None:
            for fn in notas.findall(W + "footnote"):
                if fn.get(W + "type") in (None, "normal"):
                    self.notas[fn.get(W + "id")] = fn

    def _xml(self, nome):
        if nome not in self.nomes:
            return None
        return ET.fromstring(self.zip.read(nome))

    def _rels(self, nome):
        rels = {}
        x = self._xml(nome)
        if x is not None:
            for r in x.findall(PR + "Relationship"):
                alvo = r.get("Target", "")
                if r.get("TargetMode") != "External":
                    alvo = posixpath.normpath(posixpath.join("word", alvo)) if not alvo.startswith("/") else alvo[1:]
                rels[r.get("Id")] = alvo
        return rels

    def midia(self, rid):
        alvo = self.rels.get(rid)
        if not alvo or alvo not in self.nomes:
            return None, None
        return self.zip.read(alvo), alvo


class Leitor:
    """Percorre o corpo e produz blocos: dict(texto, num_fmt, titulo, anexos...)."""

    def __init__(self, pacote):
        self.pk = pacote
        self.imagens = {}   # id -> dict(dados, origem, largura_cm, altura_cm, equacao)
        self.notas_usadas = []

    # -- imagens --------------------------------------------------------------
    def _nova_imagem(self, rid, cx=None, cy=None, equacao=False):
        dados, origem = self.pk.midia(rid)
        if dados is None:
            return None
        larg = cx / EMU_POR_CM if cx else None
        alt = cy / EMU_POR_CM if cy else None
        if larg is not None and alt is not None and larg < 0.25 and alt < 0.25:
            return None  # marcador/bolinha decorativa
        iid = f"d{len(self.imagens) + 1}"
        self.imagens[iid] = {"dados": dados, "origem": origem, "largura_cm": larg,
                             "altura_cm": alt, "equacao": equacao}
        return iid

    @staticmethod
    def _tam_vml(estilo):
        def med(nome):
            m = re.search(nome + r"\s*:\s*([\d.]+)\s*(pt|in|cm|mm|px)?", estilo or "")
            if not m:
                return None
            v = float(m.group(1))
            return v * {"pt": 12700, "in": 914400, "cm": 360000, "mm": 36000, "px": 9525}.get(m.group(2) or "pt")
        return med("width"), med("height")

    # -- percorrer conteúdo inline -------------------------------------------
    def _inline(self, el, itens, anexos, herdado):
        """Acumula itens inline de um parágrafo (recursivo)."""
        for c in el:
            tag = c.tag
            if tag == W + "r":
                self._run(c, itens, anexos, herdado)
            elif tag in (W + "hyperlink", W + "ins", W + "smartTag", W + "customXml", W + "fldSimple",
                         W + "moveTo", W + "sdt", W + "sdtContent", W + "dir", W + "bdo"):
                self._inline(c, itens, anexos, herdado)
            elif tag == M + "oMathPara":
                for om in c.iter(M + "oMath"):
                    itens.append(("eq_bloco", omml_latex(om), None))
            elif tag == M + "oMath":
                itens.append(("eq", omml_latex(c), None))
            elif tag == MC + "AlternateContent":
                alvo = c.find(MC + "Choice")
                if alvo is None:
                    alvo = c.find(MC + "Fallback")
                if alvo is not None:
                    self._inline(alvo, itens, anexos, herdado)

    def _run(self, r, itens, anexos, herdado):
        rpr = r.find(W + "rPr")
        p = dict(herdado)
        if rpr is not None:
            estilo = _val(rpr, W + "rStyle")
            if estilo:
                p.update(self.pk.estilos.props(estilo))
            p.update(_props_run(rpr))
        if p.get("oculto"):
            return
        fonte = p.pop("fonte", None)
        fmt = {k: v for k, v in p.items() if k in ("b", "i", "u", "va") and v and v != "baseline"}
        for c in r:
            tag = c.tag
            if tag == W + "t":
                t = "".join(simbolo(ch, fonte) for ch in (c.text or ""))
                if p.get("caps"):
                    t = t.upper()
                itens.append(("t", t, fmt))
            elif tag == W + "sym":
                ch = chr(int(c.get(W + "char", "20"), 16))
                itens.append(("t", simbolo(ch, c.get(W + "font")), fmt))
            elif tag in (W + "tab", W + "ptab"):
                itens.append(("t", "\t", fmt))
            elif tag in (W + "br", W + "cr"):
                if c.get(W + "type") not in ("page", "column"):
                    itens.append(("br", "", None))
            elif tag == W + "noBreakHyphen":
                itens.append(("t", "-", fmt))
            elif tag == W + "footnoteReference":
                nid = c.get(W + "id")
                if nid in self.pk.notas:
                    self.notas_usadas.append(nid)
                    itens.append(("raw", f"[^{len(self.notas_usadas)}]", None))
            elif tag == W + "drawing":
                self._desenho(c, itens, anexos)
            elif tag in (W + "pict", W + "object"):
                self._vml(c, itens, anexos, equacao=tag == W + "object")
            elif tag == MC + "AlternateContent":
                escolha = c.find(MC + "Choice")
                alvo = escolha if escolha is not None else c.find(MC + "Fallback")
                if alvo is not None:
                    falso = ET.Element(W + "r")
                    if rpr is not None:
                        falso.append(rpr)
                    falso.extend(list(alvo))
                    self._run(falso, itens, anexos, herdado)

    def _desenho(self, d, itens, anexos):
        ext = d.find(f".//{WP}extent")
        cx = int(ext.get("cx", "0")) if ext is not None else None
        cy = int(ext.get("cy", "0")) if ext is not None else None
        # Imagem flutuante (posicionada na página) não faz parte da frase:
        # vai numa linha própria logo depois do parágrafo
        flutuante = d.find(WP + "anchor") is not None
        destino = []
        pics = [p for p in d.iter(PIC + "pic")]
        if len(pics) > 1 or (pics and d.find(f".//{WPG}wgp") is not None):
            # Grupo: cada imagem tem o próprio tamanho, na escala do grupo
            escala = 1.0
            grupo = d.find(f".//{WPG}grpSpPr/{A}xfrm")
            if grupo is not None and grupo.find(A + "ext") is not None and grupo.find(A + "chExt") is not None:
                e, ch = grupo.find(A + "ext"), grupo.find(A + "chExt")
                escala = int(e.get("cx", "1")) / max(1, int(ch.get("cx", "1")))
            for pic in pics:
                b = pic.find(f".//{A}blip")
                x = pic.find(f".//{A}xfrm/{A}ext")
                if b is None or not b.get(R + "embed"):
                    continue
                pcx = int(x.get("cx")) * escala if x is not None else None
                pcy = int(x.get("cy")) * escala if x is not None else None
                iid = self._nova_imagem(b.get(R + "embed"), pcx, pcy)
                if iid:
                    destino.append(iid)
        else:
            for b in d.iter(A + "blip"):
                if b.get(R + "embed"):
                    iid = self._nova_imagem(b.get(R + "embed"), cx, cy)
                    if iid:
                        destino.append(iid)
        for iid in destino:
            if flutuante:
                anexos.append({"tipo": "p", "texto": f"⟦IMG:{iid}⟧", "titulo": None})
            else:
                itens.append(("img", iid, None))
        for tx in d.iter(W + "txbxContent"):
            anexos.extend(self._sem_titulo(self.blocos(tx)))

    @staticmethod
    def _sem_titulo(blocos):
        for b in blocos:
            b["titulo"] = None
        return blocos

    def _equacao_ole(self, el):
        """LaTeX de um objeto do MathType/Editor de Equações (w:object), ou None."""
        ole = el.find(O + "OLEObject")
        if ole is None or not (ole.get("ProgID") or "").startswith("Equation."):
            return None
        dados, _ = self.pk.midia(ole.get(R + "id"))
        if dados is None:
            return None
        from mtef import ole_para_latex
        return ole_para_latex(dados)

    def _vml(self, el, itens, anexos, equacao=False):
        if equacao:
            latex = self._equacao_ole(el)
            if latex:
                itens.append(("eq", latex, None))
                return
        for shape in el.iter():
            if shape.tag == V + "imagedata":
                rid = shape.get(R + "id") or shape.get(O + "relid")
                if rid:
                    estilo = ""
                    for s in el.iter():
                        if s.tag in (V + "shape", V + "rect", V + "image") and s.get("style"):
                            estilo = s.get("style")
                            break
                    cx, cy = self._tam_vml(estilo)
                    iid = self._nova_imagem(rid, cx, cy, equacao=equacao)
                    if iid and "position:absolute" in estilo.replace(" ", ""):
                        anexos.append({"tipo": "p", "texto": f"⟦IMG:{iid}⟧", "titulo": None})
                    elif iid:
                        itens.append(("img", iid, None))
        for tx in el.iter(W + "txbxContent"):
            anexos.extend(self._sem_titulo(self.blocos(tx)))

    # -- blocos ----------------------------------------------------------------
    def paragrafo(self, p):
        ppr = p.find(W + "pPr")
        estilo = _val(ppr, W + "pStyle") if ppr is not None else None
        estilo = estilo or self.pk.estilos.padrao_par
        herdado = {k: v for k, v in self.pk.estilos.props(estilo).items() if k in ("b", "i", "u", "caps", "oculto")}
        itens, anexos = [], []
        self._inline(p, itens, anexos, herdado)

        # numeração: direta no parágrafo, senão a do estilo
        num = None
        npr = ppr.find(W + "numPr") if ppr is not None else None
        if npr is not None and npr.find(W + "numId") is not None:
            num = (_val(npr, W + "numId"), int(_val(npr, W + "ilvl", "0") or 0))
        elif estilo:
            num = self.pk.estilos.num_do_estilo(estilo)
        rotulo, fmt = self.pk.numeracao.rotulo(*num) if num else (None, None)

        # parágrafo que é só uma equação (sem rótulo) -> fórmula em destaque ($$)
        visiveis = [x for x in itens if not (x[0] == "t" and not x[1].strip())]
        if not rotulo and len(visiveis) == 1 and visiveis[0][0] == "eq":
            itens = [("eq_bloco", visiveis[0][1], None)]

        partes, linhas = [], []
        for tipo, valor, props in itens:
            if tipo == "br":
                linhas.append(partes)
                partes = []
            elif tipo == "eq_bloco":
                linhas.append(partes)
                linhas.append([("raw", f"$${valor}$$", None)])
                partes = []
            elif tipo == "eq":
                # objeto de equação encostado no texto ("$x$é"): separa com espaço
                if partes and partes[-1][0] == "t" and re.search(r"\w$", partes[-1][1]):
                    partes.append(("t", " ", None))
                partes.append(("raw", f"${valor}$", None))
                partes.append(("espaco_se_palavra", "", None))
            elif tipo == "img":
                partes.append(("raw", f"⟦IMG:{valor}⟧", None))
            elif tipo == "raw":
                partes.append(("raw", valor, None))
            else:
                texto_t = valor.replace("\t", " ")
                if partes and partes[-1][0] == "espaco_se_palavra":
                    partes.pop()
                    if re.match(r"\w", texto_t):
                        texto_t = " " + texto_t
                partes.append(("t", texto_t, props))
        partes = [x for x in partes if x[0] != "espaco_se_palavra"]
        linhas.append(partes)
        textos = [re.sub(r"[  ]{2,}", " ", renderizar_inline(l)).strip() for l in linhas]
        textos = [t for t in textos if t] or [""]
        texto = "\n".join(textos)
        if rotulo:
            texto = f"{rotulo} {texto}".strip() if texto else rotulo
        nivel = self.pk.estilos.nivel_titulo(estilo)
        bloco = {"tipo": "p", "texto": texto, "num_fmt": fmt, "rotulo": rotulo,
                 "titulo": nivel if nivel is not None and nivel < 6 and texto and not rotulo else None}
        return [bloco] + anexos

    def tabela(self, tbl):
        linhas = []
        for tr in tbl.findall(W + "tr"):
            celulas = []
            for tc in tr.findall(W + "tc"):
                tcpr = tc.find(W + "tcPr")
                span = int(_val(tcpr, W + "gridSpan", "1") or 1) if tcpr is not None else 1
                vmerge = tcpr.find(W + "vMerge") if tcpr is not None else None
                continua = vmerge is not None and vmerge.get(W + "val", "continue") == "continue"
                blocos = [] if continua else self._sem_titulo(self.blocos(tc))
                celulas.append(blocos)
                celulas.extend([[]] * (span - 1))
            linhas.append(celulas)
        if not linhas:
            return []
        todos = [b for l in linhas for c in l for b in c]
        n_col = max(len(l) for l in linhas)
        # tabela de diagramação: uma coluna/linha, questões numeradas, imagens ou
        # células com muito texto -> conteúdo em sequência
        diagramacao = (
            n_col < 2 or len(linhas) < 2
            or any(b.get("rotulo") and b.get("num_fmt") not in ("bullet", "none") for b in todos)
            or any(b.get("tipo") == "tabela_md" for b in todos)
            or any(sum(1 for b in c if b.get("texto")) > 4 for l in linhas for c in l)
            or any(len(b.get("texto", "")) > 300 for b in todos)
        )
        if diagramacao:
            return todos
        def cel(c):
            t = " ".join(b["texto"].replace("\n", " ") for b in c if b.get("texto"))
            return t.replace("|", "\\|") or " "
        md = []
        for k, l in enumerate(linhas):
            l = l + [[]] * (n_col - len(l))
            md.append("| " + " | ".join(cel(c) for c in l) + " |")
            if k == 0:
                md.append("|" + "---|" * n_col)
        return [{"tipo": "tabela_md", "texto": "\n".join(md)}]

    def blocos(self, conteiner):
        saida = []
        for el in conteiner:
            tag = el.tag
            if tag == W + "p":
                saida.extend(self.paragrafo(el))
            elif tag == W + "tbl":
                saida.extend(self.tabela(el))
            elif tag in (W + "sdt", W + "sdtContent", W + "customXml"):
                saida.extend(self.blocos(el))
            elif tag == MC + "AlternateContent":
                escolha = el.find(MC + "Choice")
                saida.extend(self.blocos(escolha if escolha is not None else el))
        return saida

    def notas(self):
        saida = []
        for k, nid in enumerate(self.notas_usadas, 1):
            blocos = self.blocos(self.pk.notas[nid])
            texto = " ".join(b["texto"] for b in blocos if b.get("texto")).strip()
            saida.append(f"[^{k}]: {texto}")
        return saida


# ---------------------------------------------------------------------------
# Imagens: formato de saída e OCR opcional
# ---------------------------------------------------------------------------
_EXT_WEB = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".gif": "gif", ".svg": "svg"}


def preparar_imagem(info):
    """Devolve (bytes, extensão) num formato que o navegador mostra."""
    ext = Path(info["origem"]).suffix.lower()
    if ext in _EXT_WEB:
        return info["dados"], _EXT_WEB[ext]
    try:  # BMP, TIFF; WMF/EMF só no Windows (o Pillow usa a API do sistema)
        from PIL import Image
        img = Image.open(io.BytesIO(info["dados"]))
        if ext in (".wmf", ".emf"):
            img.load(dpi=200)
        buf = io.BytesIO()
        img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG")
        return buf.getvalue(), "png"
    except Exception:  # noqa: BLE001
        print(f"[aviso] não foi possível converter {info['origem']} para PNG; salvo no formato original",
              file=sys.stderr)
        return info["dados"], ext.lstrip(".") or "bin"


def _parece_formula(info):
    if info["equacao"]:
        return True
    larg, alt = info["largura_cm"], info["altura_cm"]
    return alt is not None and larg is not None and alt <= 1.6 and larg <= 10


def _ocr(modelo, info):
    from PIL import Image
    from reconstruir import ocr_formula
    dados, _ext = preparar_imagem(info)
    img = Image.open(io.BytesIO(dados)).convert("RGB")
    if info["altura_cm"]:
        # mesma escala do modo PDF: ~2 px por ponto tipográfico
        alvo = max(16, int(info["altura_cm"] / 2.54 * 72 * 2))
        if abs(img.height - alvo) > 4:
            img = img.resize((max(1, int(img.width * alvo / img.height)), alvo), Image.LANCZOS)
    return ocr_formula(modelo, img)


# ---------------------------------------------------------------------------
# Montagem do documento
# ---------------------------------------------------------------------------
RE_IMG = re.compile(r"⟦IMG:([^⟧]+)⟧")


def converter_docx(docx_path, output_path, pasta_imagens=None, formulas_imagem=False, progresso=None):
    from reconstruir import (RE_ALTERNATIVA, RE_QUESTAO, carregar_pix2tex, limpar_documento,
                             nome_seguro)

    docx_path, output_path = Path(docx_path), Path(output_path)
    try:
        pk = Pacote(docx_path)
    except zipfile.BadZipFile:
        raise ValueError(f"{docx_path.name}: não é um .docx válido (se for .doc antigo, "
                         "abra no Word e use Salvar como > Documento do Word .docx)")
    leitor = Leitor(pk)
    corpo = pk.doc.find(W + "body")
    elementos = list(corpo)
    blocos = []
    for k, el in enumerate(elementos, 1):
        blocos.extend(leitor.blocos([el]))
        if progresso and (k % 25 == 0 or k == len(elementos)):
            progresso(k, len(elementos))

    modelo = carregar_pix2tex() if formulas_imagem else None
    stem = nome_seguro(output_path.stem)
    if pasta_imagens is not None and pasta_imagens.exists():
        for antigo in pasta_imagens.glob(f"{stem}_*.*"):
            if antigo.suffix.lower() in (".png", ".jpg", ".gif", ".svg", ".wmf", ".emf", ".bmp", ".tif"):
                antigo.unlink()

    manifesto, usados = [], collections.Counter()
    questao = alternativa = None
    linhas = []

    def gerar(iid, sozinho):
        info = leitor.imagens[iid]
        if modelo is not None and _parece_formula(info):
            try:
                latex = _ocr(modelo, info)
                if latex:
                    return f"$${latex}$$" if sozinho else f"${latex}$"
            except Exception as e:  # noqa: BLE001
                print(f"[aviso] pix2tex falhou em {info['origem']}: {e}", file=sys.stderr)
        if pasta_imagens is None:
            return ""
        if questao is not None:
            base = f"{stem}_q{questao:02d}" + (f"_alt{alternativa}" if alternativa else "")
            legenda = f"Questão {questao:02d}" + (f" – alternativa {alternativa}" if alternativa else "")
        else:
            base, legenda = f"{stem}_inicio", "Início"
        usados[base] += 1
        dados, ext = preparar_imagem(info)
        nome = f"{base}_{usados[base]}.{ext}"
        pasta_imagens.mkdir(parents=True, exist_ok=True)
        (pasta_imagens / nome).write_bytes(dados)
        rel = Path(os.path.relpath(pasta_imagens / nome, output_path.parent)).as_posix()
        manifesto.append({
            "arquivo": nome, "markdown": rel, "questao": questao, "alternativa": alternativa,
            "inline": not sozinho, "origem": info["origem"],
            "largura_cm": round(info["largura_cm"], 2) if info["largura_cm"] else None,
            "altura_cm": round(info["altura_cm"], 2) if info["altura_cm"] else None,
        })
        return f"![{legenda} – figura {usados[base]}]({rel})"

    for b in blocos:
        texto = b.get("texto", "")
        if b["tipo"] == "tabela_md":
            linhas += ["", texto, ""]
            continue
        limpo = RE_IMG.sub("", texto).strip()
        # questão / alternativa: pela numeração do Word ou pelo texto digitado
        if limpo:
            fmt = b.get("num_fmt")
            # "**22** – ..." / "<u>a)</u>": tira a formatação antes de reconhecer o rótulo
            cru = re.sub(r"\*{1,3}|</?u>|\\(?=[*_$])", "", limpo).lstrip()
            mq = RE_QUESTAO.match(cru)
            ma = RE_ALTERNATIVA.match(cru)
            eh_alt = bool(ma) or fmt in ("lowerLetter", "upperLetter")
            if mq and not eh_alt:
                q = int(mq.group(1))
                # aceita a sequência (com folga para anuladas); ignora sublistas "1 –"
                if questao is None or questao < q <= questao + 5:
                    questao, alternativa = q, None
            if eh_alt and questao is not None:
                letra = ma.group(1) if ma else (b.get("rotulo") or "")[:1]
                alternativa = letra.upper() or None
            else:
                alternativa = None
        sozinho = not limpo
        texto = RE_IMG.sub(lambda m: gerar(m.group(1), sozinho), texto)
        texto = re.sub(r"[ \t]{2,}", " ", texto).strip()
        # título: só parágrafos do corpo com estilo de título que comecem com
        # maiúscula e tenham palavras (rótulos de figura como "20 cm" ou "x" não)
        eh_titulo = (b.get("titulo") is not None and "⟦IMG:" not in b["texto"]
                     and len(re.findall(r"[^\W\d_]", limpo)) >= 3
                     and re.match(r"^[^\w]*[^\W\d_]", limpo) and re.search(r"[^\W\d_]", limpo).group().isupper())
        if eh_titulo:
            titulo = re.sub(r"^\*{1,3}(.*?)\*{1,3}$", lambda m: m.group(1), texto)  # título já é destacado
            linhas += ["", "#" * min(6, b["titulo"] + 1) + " " + titulo, ""]
            continue
        # escapa marcadores de Markdown no começo da linha (não são listas/títulos)
        texto = re.sub(r"^([#>+])", r"\\\1", texto, flags=re.M)
        texto = re.sub(r"^- (?=\S)", "\\- ", texto, flags=re.M) if b.get("num_fmt") != "bullet" else texto
        linhas.append(texto)

    notas = leitor.notas()
    if notas:
        linhas += ["", "---", ""] + notas
    documento = limpar_documento("\n".join(linhas))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(documento, encoding="utf-8")
    if pasta_imagens is not None and manifesto:
        (pasta_imagens / "manifest.json").write_text(
            json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "markdown": str(output_path),
        "caracteres": len(documento),
        "paginas": None,
        "imagens": len(manifesto),
        "pasta_imagens": str(pasta_imagens) if manifesto else None,
    }
