# GDOM — Plataforma de Binarização, Stego-Bits e Otimização de Documentos para IA

**GDOM** é uma plataforma web e motor em Python desenvolvidos para processar **currículos e documentos (PDF, TXT, MD, Imagens)** diretamente no **nível de bytes e bits**, aplicando técnicas de **binarização adaptativa (Otsu)**, **codificação binária invisível (LSB & Zero-Width Bitstream)** e **injeção de camadas micro-semânticas e metadados XMP** para maximizar a leitura, indexação e avaliação positiva por sistemas de Inteligência Artificial (LLMs) e triagem automatizada (ATS).

---

## Principais Funcionalidades

1. **Binarização Adaptativa de Otsu & Assinatura LSB (`Least Significant Bit`)**
   - Calcula automaticamente o limiar ótimo de luminância maximizando a variância inter-classes ($\sigma_B^2$) para garantir contraste máximo em leitores OCR.
   - Embute a assinatura binária do payload diretamente nos bits menos significativos (LSB) do documento/imagem.

2. **Codificação em Bits Invisíveis Zero-Hitbox (`Plane-14 Tags & Variation Selectors`)**
   - Converte diretrizes de avaliação, competências e resumo executivo em sequências binárias mapeadas para **Unicode Plane-14 Tag Characters (`U+E0001`..`U+E007F`)** e **Variation Selectors (`U+FE00`..`U+FE0F`)** (2 nibbles de 4 bits por byte), que possuem largura de avanço `0x0px` e não criam área de seleção de cursor.

3. **Camada Stealth Anti-Hover PDF (`Off-CropBox`) & Catálogo Binário XMP**
   - Trava o `/CropBox`, `/TrimBox` e `/BleedBox` na área visível da página `[0, 0, W, H]` e grava os operadores de texto em coordenadas **fora do viewport (`x: -16384, y: -16384`)** com escala `0.0001pt` e `opacity: 0`, além de injetar um objeto `FlateStream` `/Metadata` (`/Subtype /XML`) diretamente no catálogo do PDF (`pdfDoc.catalog`).
   - Impede qualquer detecção por passagem de mouse (*hover* / cursor *I-beam*) em leitores de PDF, mantendo 100% de leitura por extratores de texto de IA e sistemas ATS.

4. **Inspetor Hexadecimal e Simulador de Leitura IA em Tempo Real**
   - Visualize o dump hexadecimal (`Hex + ASCII`) antes e depois da injeção de bits e simule como um parser de IA/ATS interpreta o documento otimizado.

---

## Estrutura do Projeto

```text
GDOM/
├── index.html              # Interface Web Completa (Estúdio GDOM, Inspetor Hex e Simulador IA)
├── styles.css              # Design System Dark Cyberpunk / Glassmorphism
├── app.js                  # Motor Client-Side (Otsu, LSB, Zero-Width Bits, PDF Binary Injection)
├── backend/
│   └── gdom_engine.py      # Motor e CLI em Python para processamento em lote de arquivos
└── README.md               # Documentação do projeto
```

---

## Como Executar

### 1. Interface Web Interativa
Basta abrir o arquivo `index.html` no navegador ou iniciar um servidor HTTP local:

```bash
python -m http.server 8080
```
Depois, acesse `http://localhost:8080` no navegador.
- Clique em **"⚡ Gerar Currículo PDF de Teste"** ou arraste qualquer currículo `.pdf`, `.txt`, `.md` ou imagem.
- Clique em **"🚀 Processar Arquivo, Aplicar Binarização & Injetar Bits IA"** e baixe o arquivo otimizado.

### 2. Via Linha de Comando (Motor Python)
```bash
python backend/gdom_engine.py meu_curriculo.pdf --role "Engenheiro de Software & IA" -o meu_curriculo_GDOM.pdf
```

---

## Ferramentas de Verificação (Defensivas)

Para auditar um documento — inclusive os gerados pelo próprio GDOM — sem depender de nenhuma simulação:

```bash
# Detecta texto oculto, Unicode invisível (decodifica o payload), dados após %%EOF e frases de injeção de prompt
python backend/gdom_scan.py curriculo.pdf          # exit code 1 se severidade alta; --json disponível

# Verificador de ATS honesto: texto realmente extraído, cobertura de keywords e estrutura (ignora conteúdo oculto)
python backend/gdom_ats.py curriculo.pdf --keywords "Python, SQL, Docker"   # ou --job vaga.txt

# Testes
python -m unittest discover -s tests -v
```

O `gdom_ats.py` usa `pypdf` para PDFs (`pip install pypdf`). A nota é uma heurística transparente (70% keywords + 30% estrutura), não uma previsão do que um ATS específico fará. Conteúdo oculto é ignorado na nota e reportado como aviso: triagens modernas tendem a penalizá-lo.

---

## Autor

Desenvolvido por **Guilherme Domenico** ([Gui-Domenico-UFMG](https://github.com/Gui-Domenico-UFMG)).
