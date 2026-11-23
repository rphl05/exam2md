# exam2md - Guia Rápido para Usuários

## 🚀 Três Formas de Usar

### 1. 🎯 Mais Simples: Arraste e Solte (Recomendado)
1. Baixe o projeto (botão **Code** → **Download ZIP**)
2. Extraia a pasta
2. **Arraste seu arquivo PDF** sobre o arquivo **`exam2md_rapido.bat`**
3. Pronto! O arquivo `.md` e a pasta `_images/` aparecerão na mesma pasta do PDF

### 2. 🖥️ Interface Web (Visual)
1. Dê dois cliques em **`exam2md.bat`**
2. Escolha a opção **4** (Interface Web)
3. Abre o navegador em `http://localhost:8000`
3. Arraste o PDF na área indicada
4. Clique em **Converter** → Baixe o `.md`

### 3. 📋 Menu Interativo
1. Dê dois cliques em **`exam2md.bat`**
2. Escolha a opção desejada:
   - **1** = Conversão simples
   - **2** = Com extração de imagens
   - **3** = OCR (para PDFs escaneados)
   - **4** = Interface Web

---

## 📋 O que você precisa

- **Windows 10/11**
- **Python 3.10+** instalado ([baixar aqui](https://python.org/downloads))
  - ✅ **IMPORTANTE**: Marque **"Add Python to PATH"** na instalação

---

## 📁 O que é gerado

```
prova.pdf                    ← Seu arquivo original
prova.md                     ← Markdown com LaTeX (use no Obsidian, Notion, VS Code)
prova_images/                ← Pasta com todas as imagens extraídas
   ├── manifest.json         ← Metadados (página, posição, tamanho)
   ├── page1_1_img1.png
   ├── page2_1_img1.png
   └── ...
```

---

## 🎯 Formatos Suportados

| Tipo de Prova | Questões | Alternativas | Status |
|---------------|----------|--------------|--------|
| **EEAR/CFS**  | 1-96     | a) b) c) d)  | ✅ Perfeito |
| **VUNESP**    | 01-60    | (A) (B) (C) (D) (E) | ✅ Funciona |
| **ENEM**      | 1-90     | A B C D E    | ✅ Funciona |
| **PDF Escaneado** | - | - | Use `--ocr` |

---

## 🔧 Opções Avançadas (Linha de Comando)

```bash
# Simples
python reconstruir.py prova.pdf

# Com imagens
python reconstruir.py prova.pdf --save-images

# Pasta personalizada para imagens
python reconstruir.py prova.pdf --save-images --images-dir ./minhas_imagens

# OCR para PDFs escaneados (requer instalacao separada)
python reconstruir.py prova_escaneada.pdf --ocr

# Apenas algumas paginas
python reconstruir.py prova.pdf --pages 1,3,5-10
```

---

## ❓ Problemas Comuns

| Problema | Solução |
|----------|---------|
| `'python' não é reconhecido` | Reinstale Python marcando **"Add Python to PATH"** |
| `ModuleNotFoundError` | Execute `exam2md.bat` novamente (reinstala dependências) |
| `Permission denied` | Execute como Administrador ou verifique antivírus |
| PDF não converte | Tente `--ocr` para PDFs escaneados (imagens) |
| Alternativas faltando (VUNESP) | Limitação do PDF - use `--ocr` |

---

## 📞 Suporte

- **Issues**: [GitHub Issues](https://github.com/rphl05/exam2md/issues)
- **Código fonte**: [GitHub](https://github.com/rphl05/exam2md)

---

**Desenvolvido para automatizar extração de provas EEAR/IF/ENEM/VUNESP** 🎓