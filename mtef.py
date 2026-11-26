"""Equações do MathType / Editor de Equações 3.0 (objetos OLE no Word) -> LaTeX.

O objeto OLE guarda, além da figura (WMF/EMF), a equação em si no fluxo
"Equation Native", no formato MTEF (MathType 6/7 = versão 5; Editor de
Equações 3.0 = versão 3). Este módulo lê esse formato e gera LaTeX, sem OCR.

    latex = ole_para_latex(bytes_do_oleObject_bin)   # None se não der para ler
"""

import io
import re
import struct

from docx2md import latex_char, simbolo

# Registros
END, LINE, CHAR, TMPL, PILE, MATRIX, EMBELL, RULER, FONT_STYLE_DEF, SIZE = range(10)
FULL, SUB, SUB2, SYM, SUBSYM, COLOR, COLOR_DEF, FONT_DEF, EQN_PREFS, ENCODING_DEF = range(10, 20)

# Fontes/estilos (typeface)
FN_TEXT, FN_FUNCTION, FN_VARIABLE, FN_LCGREEK, FN_UCGREEK, FN_SYMBOL, FN_VECTOR, FN_NUMBER = range(1, 9)
FN_MTEXTRA, FN_EXPAND, FN_MARKER, FN_SPACE = 11, 22, 23, 24

_FUNCOES = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "lg", "exp", "lim", "max", "min",
            "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "det", "mod", "gcd", "sup", "inf"}

_OPERADORES = {0x222B: "\\int", 0x222C: "\\iint", 0x222D: "\\iiint", 0x222E: "\\oint", 0x2211: "\\sum",
               0x220F: "\\prod", 0x2210: "\\coprod", 0x22C3: "\\bigcup", 0x22C2: "\\bigcap", 0x222F: "\\oiint"}

_EMBELL = {2: "\\dot", 3: "\\ddot", 4: "\\dddot", 8: "\\tilde", 9: "\\hat", 11: "\\vec", 12: "\\overleftarrow",
           13: "\\overleftrightarrow", 14: "\\vec", 15: "\\overleftarrow", 17: "\\bar", 19: "\\overset{\\frown}"}
_PRIMOS = {5: "'", 6: "''", 7: "\\backprime", 18: "'''"}

_MT_EXTRA = {}  # caracteres privados do MathType com equivalente Unicode conhecido

_CERCAS = {0: ("\\langle", "\\rangle"), 1: ("(", ")"), 2: ("\\{", "\\}"), 3: ("[", "]"), 4: ("|", "|"),
           5: ("\\|", "\\|"), 6: ("\\lfloor", "\\rfloor"), 7: ("\\lceil", "\\rceil"), 8: ("[", "]")}


class ErroMTEF(Exception):
    pass


class Leitor:
    def __init__(self, dados):
        self.d = dados
        self.i = 0

    def byte(self):
        if self.i >= len(self.d):
            raise ErroMTEF("fim inesperado")
        b = self.d[self.i]
        self.i += 1
        return b

    def u16(self):
        if self.i + 2 > len(self.d):
            raise ErroMTEF("fim inesperado")
        v = struct.unpack_from("<H", self.d, self.i)[0]
        self.i += 2
        return v

    def uint(self):
        """Inteiro sem sinal do MTEF 5: 1 byte, ou 255 seguido de 16 bits."""
        b = self.byte()
        return self.u16() if b == 255 else b

    def texto(self):
        fim = self.d.index(b"\x00", self.i)
        s = self.d[self.i:fim].decode("latin-1")
        self.i = fim + 1
        return s


# ---------------------------------------------------------------------------
# Leitura (árvore de nós)
# ---------------------------------------------------------------------------
class MTEF:
    def __init__(self, dados):
        self.r = Leitor(dados)
        self.versao = self.r.byte()
        if self.versao not in (2, 3, 4, 5):
            raise ErroMTEF(f"versão MTEF {self.versao} não suportada")
        self.r.byte()  # plataforma
        self.r.byte()  # produto
        self.r.byte()  # versão do produto
        self.r.byte()  # subversão
        if self.versao >= 5:
            self.r.texto()  # chave do aplicativo ("DSMT6")
            self.r.byte()   # opções da equação

    # cabeçalho de registro: (tipo, opções)
    def tag(self):
        b = self.r.byte()
        if self.versao >= 5:
            if b >= 100:  # registro futuro: pula
                n = self.r.u16()
                self.r.i += n
                return self.tag()
            return b, self.r.byte() if b in (LINE, CHAR, TMPL, PILE, MATRIX, EMBELL) else 0
        return b & 0x0F, b >> 4

    def nudge(self, opc):
        if opc & 0x08:
            dx, dy = self.r.byte(), self.r.byte()
            if dx == 128 and dy == 128:
                self.r.u16()
                self.r.u16()

    def ruler(self):
        n = self.r.byte()
        for _ in range(n):
            self.r.byte()
            self.r.u16()

    def lista(self):
        """Lê objetos até END."""
        itens = []
        while True:
            tipo, opc = self.tag()
            if tipo == END:
                return itens
            no = self.objeto(tipo, opc)
            if no is not None:
                itens.append(no)

    def objeto(self, tipo, opc):
        r, v5 = self.r, self.versao >= 5
        if tipo == LINE:
            self.nudge(opc)
            if v5 and opc & 0x04 or not v5 and opc & 0x04:
                r.u16()  # espaçamento de linha
            if opc & 0x02:
                if v5:
                    t, _ = self.tag()
                    if t != RULER:
                        raise ErroMTEF("RULER esperado")
                self.ruler()
            if opc & 0x01:  # linha nula
                return ("line", [])
            return ("line", self.lista())
        if tipo == CHAR:
            self.nudge(opc)
            face = r.byte() - 128
            if v5:
                codigo = r.u16() if not opc & 0x20 else None
                pos8 = r.byte() if opc & 0x04 else None
                pos16 = r.u16() if opc & 0x10 else None
                if codigo is None:
                    codigo = pos16 if pos16 is not None else pos8
                embell = self.lista() if opc & 0x01 else []
            else:
                codigo = r.u16()
                embell = self.lista() if opc & 0x02 else []
            return ("char", face, codigo, [e for e in embell if e[0] == "embell"], bool(v5 and opc & 0x02))
        if tipo == TMPL:
            self.nudge(opc)
            sel = r.byte()
            var = r.byte()
            if v5 and var & 0x80:
                var = (var & 0x7F) | (r.byte() << 8)
            r.byte()  # opções específicas do modelo
            return ("tmpl", sel, var, self.lista())
        if tipo == PILE:
            self.nudge(opc)
            halign, _valign = r.byte(), r.byte()
            if opc & 0x02:
                if v5:
                    self.tag()
                self.ruler()
            return ("pile", halign, self.lista())
        if tipo == MATRIX:
            self.nudge(opc)
            r.byte()  # valign
            r.byte()  # h_just
            r.byte()  # v_just
            linhas, cols = r.byte(), r.byte()
            r.i += ((linhas + 1) * 2 + 7) // 8  # partições das linhas
            r.i += ((cols + 1) * 2 + 7) // 8    # partições das colunas
            return ("matrix", linhas, cols, self.lista())
        if tipo == EMBELL:
            self.nudge(opc)
            return ("embell", r.byte())
        if tipo == RULER:
            self.ruler()
            return None
        if tipo == FONT_STYLE_DEF:
            r.uint() if v5 else r.byte()
            r.byte()
            return None
        if tipo == 8 and not v5:  # FONT (v3)
            r.byte()
            r.byte()
            r.texto()
            return None
        if tipo == SIZE:
            b = r.byte()
            if b == 101:
                r.u16()
            elif b == 100:
                r.byte()
                r.u16()
            else:
                r.byte()
            return None
        if tipo in (FULL, SUB, SUB2, SYM, SUBSYM):
            return None
        if v5 and tipo == COLOR:
            r.uint()
            return None
        if v5 and tipo == COLOR_DEF:
            o = r.byte()
            for _ in range(4 if o & 0x01 else 3):
                r.u16()
            if o & 0x04:
                r.texto()
            return None
        if v5 and tipo == FONT_DEF:
            r.uint()
            r.texto()
            return None
        if v5 and tipo == EQN_PREFS:
            self._prefs()
            return None
        if v5 and tipo == ENCODING_DEF:
            r.texto()
            return None
        raise ErroMTEF(f"registro desconhecido {tipo}")

    def _prefs(self):
        r = self.r
        r.byte()  # opções
        for _ in range(2):  # tamanhos e espaçamentos: dimensões em nibbles
            n = r.byte()
            nibbles, alto = 0, None

            def nib():
                nonlocal alto
                if alto is None:
                    b = r.byte()
                    alto = b & 0x0F
                    return b >> 4
                v, alto = alto, None
                return v

            for _ in range(n):
                nib()  # unidade
                while nib() != 0x0F:
                    pass
        n = r.byte()  # estilos
        for _ in range(n):
            if r.byte():
                r.byte()

    def ler(self):
        itens = []
        while self.r.i < len(self.r.d):
            try:
                tipo, opc = self.tag()
            except ErroMTEF:
                break
            if tipo == END:
                break
            no = self.objeto(tipo, opc)
            if no is not None:
                itens.append(no)
        return itens


# ---------------------------------------------------------------------------
# Árvore -> LaTeX
# ---------------------------------------------------------------------------
def _caractere(face, codigo, versao):
    if codigo is None:
        return ""
    if face == FN_SPACE or 0xEF00 <= codigo <= 0xEFFF:
        return " "  # espaços manuais do MathType: o LaTeX já espaça operadores
    if face in (FN_MARKER,):
        return ""
    ch = chr(codigo)
    if versao < 5 and face in (FN_LCGREEK, FN_UCGREEK, FN_SYMBOL) and codigo < 0x100:
        ch = simbolo(ch, "Symbol")
    if 0xE000 <= ord(ch) <= 0xF8FF:
        ch = simbolo(ch, "Symbol") if 0xF020 <= ord(ch) <= 0xF0FF else _MT_EXTRA.get(ord(ch), "")
        if not ch:
            return ""
    if ch == " ":
        return "\\ "
    return latex_char(ch)


class Gerador:
    def __init__(self, versao):
        self.versao = versao

    def linha(self, itens):
        partes = []
        k = 0
        while k < len(itens):
            no = itens[k]
            # sequência de texto/função: agrupa as letras
            if no[0] == "char" and no[1] in (FN_TEXT, FN_FUNCTION) and not no[3]:
                face = no[1]
                j, palavra = k, ""
                while j < len(itens) and itens[j][0] == "char" and itens[j][1] == face and not itens[j][3]:
                    if j > k and itens[j][4]:  # início de outra função
                        break
                    palavra += chr(itens[j][2]) if itens[j][2] else ""
                    j += 1
                partes.append(self._palavra(palavra, face))
                k = j
                continue
            partes.append(self.no(no))
            k += 1
        return "".join(partes)

    def _palavra(self, palavra, face):
        if face == FN_FUNCTION:
            p = palavra.strip()
            if p in _FUNCOES:
                return "\\" + p + " "
            return "\\operatorname{" + p + "}" if p.isalpha() else "".join(latex_char(c) for c in palavra)
        if not palavra.strip():
            return "\\ " * len(palavra)
        if all(c.isdigit() or c in ".,+-=()/" for c in palavra.strip()):
            return "".join(latex_char(c) for c in palavra)
        return "\\text{" + palavra + "}"

    def no(self, no):
        tipo = no[0]
        if tipo == "line":
            return self.linha(no[1])
        if tipo == "char":
            _, face, codigo, embell, _ = no
            s = _caractere(face, codigo, self.versao)
            if face == FN_VECTOR and s.strip():
                s = "\\mathbf{" + s.strip() + "}"
            for e in embell:
                t = e[1]
                if t in _PRIMOS:
                    s += _PRIMOS[t]
                elif t == 10:
                    s = "\\not " + s
                elif t in _EMBELL:
                    s = _EMBELL[t] + "{" + s.strip() + "}"
            return s
        if tipo == "pile":
            _, halign, linhas = no
            col = {1: "l", 2: "c", 3: "r"}.get(halign, "l")
            conteudo = [self.no(l) for l in linhas if l[0] == "line"]
            if len(conteudo) == 1:
                return conteudo[0]
            return "\\begin{array}{" + col + "}" + " \\\\ ".join(conteudo) + "\\end{array}"
        if tipo == "matrix":
            _, nl, nc, celulas = no
            cel = [self.no(c) for c in celulas if c[0] == "line"]
            linhas = [" & ".join(cel[i * nc:(i + 1) * nc]) for i in range(nl)]
            return "\\begin{matrix}" + " \\\\ ".join(linhas) + "\\end{matrix}"
        if tipo == "tmpl":
            return self.modelo(no[1], no[2], no[3])
        return ""

    def modelo(self, sel, var, subs):
        linhas = [s for s in subs if s[0] in ("line", "pile", "matrix")]
        chars = [s for s in subs if s[0] == "char"]
        L = lambda k: self.no(linhas[k]) if k < len(linhas) else ""  # noqa: E731

        if sel <= 8 or sel == 9:  # cercas: ( ), [ ], { }, | |, intervalos
            esq, dir_ = _CERCAS.get(sel, ("(", ")"))
            reais = [_caractere(FN_SYMBOL, c[2], self.versao).strip() for c in chars]
            # peças "esticáveis" privadas do MathType (ex.: EC07/EC08 = barras de |x|)
            # não têm equivalente: vale a cerca padrão do modelo
            if chars and all(reais):  # caracteres reais (intervalos ]a, b[, cerca de um lado só)
                mapa = {"{": "\\{", "}": "\\}", "\\{": "\\{", "\\}": "\\}"}
                reais = [mapa.get(x, x) for x in reais]
                if sel <= 8 and len(reais) == 1:
                    if var & 0x0001 and not var & 0x0002:
                        esq, dir_ = reais[0], "."
                    elif var & 0x0002 and not var & 0x0001:
                        esq, dir_ = ".", reais[0]
                elif len(reais) >= 2:
                    esq, dir_ = reais[0] or ".", reais[1] or "."
            elif sel <= 8:
                if var & 0x0003 == 0x0001:
                    dir_ = "."
                elif var & 0x0003 == 0x0002:
                    esq = "."
            return f"\\left{esq} {L(0)} \\right{dir_}"
        if sel == 10:  # raiz
            return "\\sqrt[" + L(1) + "]{" + L(0) + "}" if var & 1 and L(1).strip() else "\\sqrt{" + L(0) + "}"
        if sel == 11:  # fração
            if var & 0x0002:
                return L(0) + "/" + L(1)
            return "\\frac{" + L(0) + "}{" + L(1) + "}"
        if sel == 12:
            return "\\underline{" + L(0) + "}"
        if sel == 13:
            return "\\overline{" + L(0) + "}"
        if sel == 14:  # seta com texto
            return "\\xrightarrow[" + L(1) + "]{" + L(0) + "}"
        if 15 <= sel <= 22:  # integrais, somatórios, produtórios...
            if chars:
                op = _OPERADORES.get(chars[0][2], _caractere(FN_SYMBOL, chars[0][2], self.versao).strip())
            else:
                op = {15: "\\int", 16: "\\sum", 17: "\\prod", 18: "\\coprod", 19: "\\bigcup",
                      20: "\\bigcap", 21: "\\int", 22: "\\sum"}[sel]
            s = op
            if L(1).strip():
                s += "_{" + L(1) + "}"
            if L(2).strip():
                s += "^{" + L(2) + "}"
            return s + " " + L(0)
        if sel == 23:  # limite
            base = L(0).strip()
            s = base if base.startswith("\\") else "\\operatorname{" + base.replace("\\text{", "").rstrip("}") + "}"
            if L(1).strip():
                s += "_{" + L(1) + "}"
            if L(2).strip():
                s += "^{" + L(2) + "}"
            return s + " "
        if sel == 24:
            return "\\underbrace{" + L(0) + "}_{" + L(1) + "}" if L(1).strip() else "\\overbrace{" + L(0) + "}"
        if sel == 25:
            return "\\underbrace{" + L(0) + "}"
        if sel == 26:  # divisão longa
            return L(0) + " \\div " + L(1)
        if sel in (27, 28, 29):  # índices: aplicam-se ao item anterior
            sub, sup = L(0).strip(), L(1).strip()
            s = ""
            if sub:
                s += "_{" + sub + "}"
            if sup:
                s += "^{" + sup + "}"
            return s or "{}"
        if sel == 30:
            return "\\left\\langle " + L(0) + " \\middle| " + L(1) + " \\right\\rangle"
        if sel == 31:
            corpo = L(0)
            return ("\\vec{" if len(corpo.strip()) <= 2 else "\\overrightarrow{") + corpo + "}"
        if sel == 32:
            return "\\widetilde{" + L(0) + "}"
        if sel == 33:
            return "\\widehat{" + L(0) + "}"
        if sel == 34:
            return "\\overset{\\frown}{" + L(0) + "}"
        if sel == 36:
            return "\\cancel{" + L(0) + "}"
        if sel == 37:
            return "\\boxed{" + L(0) + "}"
        return "".join(self.no(s) for s in linhas)


def mtef_para_latex(dados):
    m = MTEF(dados)
    arvore = m.ler()
    latex = Gerador(m.versao).linha(arvore)
    latex = " ".join(latex.split())
    latex = latex.replace("{ ", "{").replace(" }", "}")
    # trigonometria em português digitada como letras: sen 30 -> \operatorname{sen} 30
    latex = re.sub(r"(?<![\\A-Za-z])(arcsen|arctg|cossec|cotg|sen|tg)(?![A-Za-z])",
                   r"\\operatorname{\1}", latex)
    latex = re.sub(r"(?<![\\A-Za-z])(cos|tan|log|ln)(?![A-Za-z])", r"\\\1", latex)
    latex = re.sub(r"\^\{o\}", r"^{\\circ}", latex)  # 60^{o} -> 60°
    return latex


def ole_para_latex(dados_ole):
    """LaTeX de um objeto OLE do MathType/Editor de Equações, ou None."""
    try:
        import olefile
    except ImportError:
        return None
    try:
        ole = olefile.OleFileIO(io.BytesIO(dados_ole))
        if not ole.exists("Equation Native"):
            return None
        bruto = ole.openstream("Equation Native").read()
        cab = struct.unpack_from("<H", bruto, 0)[0]  # tamanho do cabeçalho (28)
        latex = mtef_para_latex(bruto[cab:])
    except Exception:  # noqa: BLE001 — formato inesperado: fica a imagem
        return None
    from reconstruir import latex_valido
    return latex if latex and latex_valido(latex) else None
