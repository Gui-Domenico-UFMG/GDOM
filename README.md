# GDOM — Plataforma de Binarização, Stego-Bits e Otimização de Documentos para IA

**GDOM** é uma plataforma web e motor em Python desenvolvidos para processar **currículos e documentos (PDF, TXT, MD, Imagens)** diretamente no **nível de bytes e bits**, aplicando técnicas de **binarização adaptativa (Otsu)**, **codificação binária invisível (LSB & Zero-Width Bitstream)** e **injeção de camadas micro-semânticas e metadados XMP** para maximizar a leitura, indexação e avaliação positiva por sistemas de Inteligência Artificial (LLMs) e triagem automatizada (ATS).

---

## Principais Funcionalidades

1. **Binarização Adaptativa de Otsu & Assinatura LSB (`Least Significant Bit`)**
   - Calcula automaticamente o limiar ótimo de luminância maximizando a variância inter-classes ($\sigma_B^2$) para garantir contraste máximo em leitores OCR.
   - Embute a assinatura binária do payload diretamente nos bits menos significativos (LSB) do documento/imagem.

2. **Codificação em Bits Invisíveis (`Zero-Width Bitstream`)**
   - Converte diretrizes de avaliação, competências e resumo executivo em sequências binárias de 8 bits (`01000111...`) mapeadas para caracteres Unicode de largura zero (`U+200B` para bit `0`, `U+200C` para bit `1`, delimitados por `U+200D`).

3. **Camada Micro-Semântica PDF & Dicionário Binário XMP**
   - Utiliza manipulação direta de estrutura PDF (`pdf-lib` + trailer binário) para gravar metadados de alta afinidade (`/Title`, `/Subject`, `/Keywords`, `/Producer`) e uma camada de texto em micro-escala (`0.6pt`, opacidade `0.01`) invisível a olho nu, porém 100% legível por extratores de texto de IA e sistemas ATS.

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

## Autor

Desenvolvido por **Guilherme Domenico** ([Gui-Domenico-UFMG](https://github.com/Gui-Domenico-UFMG)).
