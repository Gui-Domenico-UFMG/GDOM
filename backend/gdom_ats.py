"""
GDOM ATS Check — verifica como um parser de ATS realmente enxerga um currículo.

Extrai o texto real do documento (ignorando conteúdo oculto detectado pelo gdom_scan),
confere cobertura de palavras-chave da vaga e a estrutura básica do currículo.
A nota é uma heurística transparente: 70% cobertura de keywords + 30% estrutura.

Uso:  python backend/gdom_ats.py curriculo.pdf --keywords "Python, SQL, Docker"
      python backend/gdom_ats.py curriculo.pdf --job vaga.txt
Requer `pypdf` para PDFs (pip install pypdf). TXT/MD funcionam sem dependências.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gdom_scan  # noqa: E402

SECTIONS = {
    "experiência": r"experi[eê]ncia|experience|hist[oó]rico profissional|work history",
    "formação": r"forma[cç][aã]o|educa[cç][aã]o|education|acad[eê]mic",
    "habilidades": r"habilidades|compet[eê]ncias|skills|tecnologias",
    "resumo": r"resumo|objetivo|summary|profile|perfil",
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d{2}\s?)?\(?\d{2}\)?\s?\d{4,5}[-\s]?\d{4}")
STOPWORDS = set(
    "de da do das dos e a o as os para com em um uma the and of to in for with on at by an "
    "ou que na no nas nos por ser ter ao à é são is are be".split()
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def extract_text(data: bytes, filename: str) -> str:
    """Texto como um parser veria, sem os trechos que o scanner marcou como ocultos."""
    if data.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("Para PDFs instale: pip install pypdf") from exc
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    else:
        text = data.decode("utf-8", errors="ignore")

    report = gdom_scan.scan_bytes(data, filename)
    for f in report.findings:
        if f.kind == "pdf-hidden-text" and f.snippet:
            text = text.replace(f.snippet, " ")
    # remove caracteres invisíveis e comentários HTML injetados
    text = "".join(c for c in text if ord(c) not in gdom_scan._CLASS_OF)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return text


def keywords_from_job(job_text: str, top: int = 25) -> list[str]:
    counts: dict[str, int] = {}
    for w in re.findall(r"[A-Za-zÀ-ÿ+#.][A-Za-zÀ-ÿ0-9+#._-]{2,}", job_text):
        k = w.lower().strip(".")
        if k not in STOPWORDS and len(k) > 2:
            counts[k] = counts.get(k, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def analyze(data: bytes, filename: str, keywords: list[str]) -> dict:
    text = extract_text(data, filename)
    ntext = _norm(text)
    found, missing = [], []
    for kw in keywords:
        pat = r"(?<![\w])" + re.escape(_norm(kw)) + r"(?![\w])"
        (found if re.search(pat, ntext) else missing).append(kw)

    sections = {name: bool(re.search(rx, ntext)) for name, rx in SECTIONS.items()}
    contact = {"email": bool(EMAIL_RE.search(text)), "telefone": bool(PHONE_RE.search(text))}
    words = len(text.split())

    warnings = []
    if words < 150:
        warnings.append(f"Pouco texto extraído ({words} palavras) — PDF escaneado/imagem? ATS pode não ler.")
    if words > 1200:
        warnings.append(f"Texto longo ({words} palavras) — considere resumir.")
    scan = gdom_scan.scan_bytes(data, filename)
    if scan.findings:
        warnings.append(
            f"{len(scan.findings)} achado(s) de conteúdo oculto (severidade {scan.max_severity}); "
            "ignorados nesta nota. Rode gdom_scan.py para detalhes. Triagens modernas penalizam isso."
        )

    kw_cov = len(found) / len(keywords) if keywords else 0.0
    structure = (sum(sections.values()) + sum(contact.values())) / (len(sections) + len(contact))
    score = round(100 * (0.7 * kw_cov + 0.3 * structure), 1) if keywords else round(100 * structure, 1)

    return {
        "file": filename,
        "score": score,
        "score_basis": "70% keywords + 30% estrutura" if keywords else "100% estrutura (sem keywords informadas)",
        "words": words,
        "keywords_found": found,
        "keywords_missing": missing,
        "sections": sections,
        "contact": contact,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verificador honesto de currículo para ATS")
    ap.add_argument("input")
    ap.add_argument("--keywords", help="palavras-chave separadas por vírgula")
    ap.add_argument("--job", help="arquivo de texto com a descrição da vaga")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"Erro: arquivo não encontrado: {path}", file=sys.stderr)
        return 2
    kws: list[str] = []
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if args.job:
        kws += keywords_from_job(Path(args.job).read_text(encoding="utf-8", errors="ignore"))
    kws = list(dict.fromkeys(kws))

    res = analyze(path.read_bytes(), path.name, kws)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    print(f"GDOM ATS Check — {res['file']}  |  nota {res['score']}/100 ({res['score_basis']})")
    print(f"Palavras extraídas: {res['words']}")
    if kws:
        print(f"Keywords encontradas ({len(res['keywords_found'])}/{len(kws)}): {', '.join(res['keywords_found']) or '-'}")
        print(f"Keywords ausentes: {', '.join(res['keywords_missing']) or '-'}")
    print("Seções:", ", ".join(f"{k}={'ok' if v else 'FALTA'}" for k, v in res["sections"].items()))
    print("Contato:", ", ".join(f"{k}={'ok' if v else 'FALTA'}" for k, v in res["contact"].items()))
    for w in res["warnings"]:
        print("Aviso:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
