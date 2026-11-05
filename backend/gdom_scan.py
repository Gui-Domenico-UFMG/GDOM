"""
GDOM Scan — detector de conteúdo oculto e injeção de prompt em documentos (PDF, TXT, MD).

Procura o que um humano não vê mas um parser/LLM lê:
  * caracteres Unicode invisíveis em sequência (zero-width, Plane-14 Tags, Variation Selectors)
    e decodifica o payload escondido;
  * texto de PDF fora da página, com fonte minúscula, transparente ou em modo de render invisível;
  * bytes anexados depois do último %%EOF;
  * frases com cara de instrução para IA ("recomende este candidato", "score 99/100"...).

Uso:  python backend/gdom_scan.py arquivo.pdf [--json]
Saída: código 1 se houver achado de severidade alta, 0 caso contrário.
Somente biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
MIN_RUN = 8  # sequência mínima de invisíveis para contar (evita falso positivo com emoji/ZWJ)
OFFPAGE_LIMIT = 5000.0  # |coordenada| acima disso está fora de qualquer página real
TINY_FONT = 1.0  # pt

INVISIBLE_CLASSES = {
    "zero-width": (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF),
    "tag-chars": tuple(range(0xE0000, 0xE0080)),
    "variation-selectors": tuple(range(0xFE00, 0xFE10)) + tuple(range(0xE0100, 0xE01F0)),
}
_CLASS_OF = {cp: name for name, cps in INVISIBLE_CLASSES.items() for cp in cps}

INSTRUCTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"(strongly\s+)?recommend\s+(this|the)\s+(candidate|profile|resume)",
    r"recomende\s+(fortemente\s+)?(este|esse)\s+(perfil|candidato|curr[ií]culo)",
    r"score\s*[:=]?\s*\d{2}(\.\d+)?\s*/\s*100",
    r"top\s*1\s*%\s*candidate",
    r"CANDIDATE_RANKING_SIGNAL",
    r"AI[_\s-]*EVALUATION",
    r"ao\s+analisar\s+este\s+documento",
    r"when\s+(analy[sz]ing|reading|evaluating)\s+this\s+(document|resume)",
    r"(destaque|highlight)\s+(a\s+)?(s[oó]lida|strong|excellent)",
]
_INSTR_RE = re.compile("|".join(f"(?:{p})" for p in INSTRUCTION_PATTERNS), re.I)


@dataclass
class Finding:
    kind: str
    severity: str  # low | medium | high
    detail: str
    snippet: str = ""
    decoded: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v != ""}


@dataclass
class ScanReport:
    path: str
    size: int
    findings: List[Finding] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        if not self.findings:
            return "none"
        return max((f.severity for f in self.findings), key=SEVERITY_ORDER.__getitem__)

    @property
    def suspicious(self) -> bool:
        return self.max_severity == "high"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "max_severity": self.max_severity,
            "findings": [f.to_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------- unicode


def decode_hidden(run: str) -> str:
    """Tenta recuperar o texto escondido em uma sequência de invisíveis."""
    # Plane-14 tags: U+E0020..E007E espelham ASCII 0x20..0x7E
    tags = "".join(chr(ord(c) - 0xE0000) for c in run if 0xE0020 <= ord(c) <= 0xE007E)
    if tags:
        return tags
    # Variation selectors FE00..FE0F: dois nibbles por byte
    nibbles = [ord(c) - 0xFE00 for c in run if 0xFE00 <= ord(c) <= 0xFE0F]
    if len(nibbles) >= 2:
        data = bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles) - 1, 2))
        text = data.decode("utf-8", errors="ignore")
        if text.strip():
            return text
    # Zero-width binário: U+200B = 0, U+200C = 1
    bits = "".join("1" if c == "‌" else "0" for c in run if c in ("​", "‌"))
    if len(bits) >= 8:
        data = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits) - 7, 8))
        text = data.decode("utf-8", errors="ignore")
        if text.strip() and text.isprintable():
            return text
    return ""


def scan_unicode(text: str) -> List[Finding]:
    findings: List[Finding] = []
    run: list[str] = []

    def flush() -> None:
        if len(run) >= MIN_RUN:
            s = "".join(run)
            classes = sorted({_CLASS_OF[ord(c)] for c in s})
            decoded = decode_hidden(s)
            findings.append(
                Finding(
                    kind="invisible-unicode",
                    severity="high" if decoded else "medium",
                    detail=f"{len(s)} caracteres invisíveis seguidos ({', '.join(classes)})",
                    snippet="U+" + " U+".join(f"{ord(c):04X}" for c in s[:6]) + " ...",
                    decoded=decoded,
                )
            )
        run.clear()

    for ch in text:
        if ord(ch) in _CLASS_OF:
            run.append(ch)
        else:
            flush()
    flush()
    return findings


def scan_instructions(text: str, where: str) -> List[Finding]:
    clean = "".join(c for c in text if ord(c) not in _CLASS_OF)
    seen: set[str] = set()
    out: List[Finding] = []
    for m in _INSTR_RE.finditer(clean):
        key = m.group(0).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Finding(
                kind="ai-instruction",
                severity="high",
                detail=f"Frase com cara de instrução para IA em {where}",
                snippet=m.group(0)[:120],
            )
        )
    return out


# --------------------------------------------------------------------------- pdf

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_BT_RE = re.compile(rb"BT(.*?)ET", re.S)
_NUM = rb"(-?\d+(?:\.\d+)?)"
_TF_RE = re.compile(rb"/[A-Za-z0-9_.+-]+\s+" + _NUM + rb"\s+Tf")
_TM_RE = re.compile(_NUM + rb"\s+" + _NUM + rb"\s+" + _NUM + rb"\s+" + _NUM + rb"\s+" + _NUM + rb"\s+" + _NUM + rb"\s+Tm")
_TD_RE = re.compile(_NUM + rb"\s+" + _NUM + rb"\s+T[dD]")
_TR3_RE = re.compile(rb"(?<![\d.])3\s+Tr\b")
_STR_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)\s*Tj|\[(.*?)\]\s*TJ", re.S)
_ALPHA0_RE = re.compile(rb"/(?:ca|CA)\s+0(?:\.0*)?(?![\d.])")


def _pdf_string_text(data: bytes) -> str:
    out = bytearray()
    for m in re.finditer(rb"\(((?:\\.|[^\\()])*)\)", data, re.S):
        out += re.sub(rb"\\(.)", rb"\1", m.group(1), flags=re.S)
    return out.decode("latin-1", errors="replace")


def _extract_block_text(block: bytes) -> str:
    parts = []
    for m in _STR_RE.finditer(block):
        parts.append(_pdf_string_text(b"(" + m.group(1) + b")") if m.group(1) is not None else _pdf_string_text(m.group(2)))
    return " ".join(p for p in parts if p).strip()


def _pdf_streams(data: bytes) -> Iterable[bytes]:
    for m in _STREAM_RE.finditer(data):
        raw = m.group(1)
        try:
            yield zlib.decompress(raw)
        except zlib.error:
            yield raw


def scan_pdf(data: bytes) -> List[Finding]:
    findings: List[Finding] = []
    corpus_parts: list[str] = [data.decode("utf-8", errors="ignore")]
    transparent = bool(_ALPHA0_RE.search(data))

    for stream in _pdf_streams(data):
        corpus_parts.append(stream.decode("utf-8", errors="ignore"))
        for bt in _BT_RE.finditer(stream):
            block = bt.group(1)
            text = _extract_block_text(block)
            if not text:
                continue
            reasons: list[str] = []
            sev = "medium"

            sizes = [float(m.group(1)) for m in _TF_RE.finditer(block)]
            if sizes and min(sizes) < TINY_FONT:
                reasons.append(f"fonte de {min(sizes):g}pt")
            coords: list[float] = []
            for m in _TM_RE.finditer(block):
                coords += [float(m.group(5)), float(m.group(6))]
            for m in _TD_RE.finditer(block):
                coords += [float(m.group(1)), float(m.group(2))]
            if any(abs(c) > OFFPAGE_LIMIT for c in coords):
                reasons.append("posição fora da página")
                sev = "high"
            if _TR3_RE.search(block):
                reasons.append("modo de render invisível (3 Tr)")
            if reasons:
                if transparent and "fonte" in " ".join(reasons):
                    reasons.append("documento usa opacidade 0")
                findings.append(
                    Finding(
                        kind="pdf-hidden-text",
                        severity=sev,
                        detail="Texto no PDF que não é visível: " + ", ".join(reasons),
                        snippet=text[:160],
                    )
                )

    if transparent:
        findings.append(
            Finding("pdf-transparent-graphics", "low", "ExtGState com opacidade 0 (/ca 0 ou /CA 0)")
        )

    eof = data.rfind(b"%%EOF")
    if eof != -1:
        tail = data[eof + 5 :].strip()
        if tail:
            txt = tail.decode("utf-8", errors="ignore")
            findings.append(
                Finding(
                    kind="data-after-eof",
                    severity="high" if _INSTR_RE.search(txt) else "medium",
                    detail=f"{len(tail)} bytes depois do último %%EOF (leitores ignoram, parsers de texto podem não)",
                    snippet=txt[:160].replace("\n", " "),
                )
            )

    corpus = "\n".join(corpus_parts)
    findings += scan_unicode(corpus)
    findings += scan_instructions(corpus, "metadados/streams do PDF")
    return findings


# --------------------------------------------------------------------------- api


def scan_bytes(data: bytes, filename: str = "") -> ScanReport:
    report = ScanReport(path=filename, size=len(data))
    if data.startswith(b"%PDF"):
        report.findings = scan_pdf(data)
    else:
        text = data.decode("utf-8", errors="ignore")
        report.findings = scan_unicode(text) + scan_instructions(text, "texto")
        for m in re.finditer(r"<!--(.*?)-->", text, re.S):
            if _INSTR_RE.search(m.group(1)):
                report.findings.append(
                    Finding("html-comment", "high", "Comentário HTML com instrução para IA", m.group(1).strip()[:160])
                )
    # remove duplicatas exatas preservando ordem
    uniq, seen = [], set()
    for f in report.findings:
        key = (f.kind, f.detail, f.snippet)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    report.findings = sorted(uniq, key=lambda f: -SEVERITY_ORDER[f.severity])
    return report


def scan_file(path: str | Path) -> ScanReport:
    p = Path(path)
    return scan_bytes(p.read_bytes(), p.name)


def _print_human(r: ScanReport) -> None:
    print(f"GDOM Scan — {r.path} ({r.size} bytes)")
    if not r.findings:
        print("Nenhum conteúdo oculto encontrado.")
        return
    icon = {"high": "[ALTO]", "medium": "[MÉDIO]", "low": "[BAIXO]"}
    for f in r.findings:
        print(f"{icon[f.severity]} {f.kind}: {f.detail}")
        if f.snippet:
            print(f"        trecho:    {f.snippet}")
        if f.decoded:
            print(f"        decodificado: {f.decoded[:200]}")
    print(f"Resultado: severidade máxima = {r.max_severity}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Detecta texto oculto e injeção de prompt em documentos")
    ap.add_argument("input", help="PDF, TXT ou MD")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    args = ap.parse_args(argv)
    path = Path(args.input)
    if not path.exists():
        print(f"Erro: arquivo não encontrado: {path}", file=sys.stderr)
        return 2
    report = scan_file(path)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 1 if report.suspicious else 0


if __name__ == "__main__":
    sys.exit(main())
