"""Manual de políticas: parsing do PDF em seções + recuperação.

Decisões:
- O manual tem 8 páginas (~3 mil palavras). Chunking por *seção/subseção do próprio
  documento* mantém regras e exceções juntas (um chunk de tamanho fixo cortaria
  "7 dias..." de "...exceto boquilhas").
- Recuperação em dois níveis: (1) `topic` enumerado -> devolve as seções inteiras,
  sem depender de similaridade lexical; (2) `topic="outro"` -> BM25 sobre os chunks.
  Embeddings/vector DB seriam custo e dependência sem ganho para ~25 chunks.
- Só entram as seções voltadas ao cliente. §7 (tom, fluxo, situações especiais) e
  §10 são instruções internas: viram prompt, não conteúdo citável.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

from . import config
from .text import stems

# tópico -> seções principais do manual
TOPICS: dict[str, list[int]] = {
    "sobre_a_loja": [1],
    "horarios": [2],
    "pagamento": [3],
    "trocas_devolucoes": [4],
    "frete_entrega": [5],
    "promocoes": [6],
    "garantia": [8],
    "privacidade": [9],
}
INTERNAL_SECTIONS = {7, 10}  # atendimento interno / disposições finais

_NOISE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")
_BULLET = re.compile(r"^[•\-–]\s")
_HEADING = re.compile(r"^\d{1,2}(\.\d{1,2})?\.?\s+\S")
_LABEL = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ú /]{2,40}:\s")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # "4.1"
    section: int
    title: str
    text: str


def _clean_lines(raw: str) -> list[str]:
    """Remove ruído, preserva colunas de tabela como ' | ' e junta linhas quebradas."""
    out: list[str] = []
    for line in raw.splitlines():
        line = line.rstrip()
        if not line.strip():
            out.append("")
            continue
        stripped = re.sub(r"\s{2,}", " | ", line.strip())
        if _NOISE.match(stripped.replace(" | ", " ")):
            continue
        stripped = re.sub(r"^([•\-–]) \| ", r"\1 ", stripped)  # bullet não é coluna de tabela
        is_row = " | " in stripped
        starts_new = bool(_BULLET.match(stripped) or _HEADING.match(stripped) or _LABEL.match(stripped) or is_row)
        prev_is_heading = bool(out and out[-1] and _HEADING.match(out[-1]) and len(out[-1]) < 70)
        if out and out[-1] and not starts_new and not prev_is_heading:
            out[-1] += " " + stripped
        else:
            out.append(stripped)
    return out


def parse_manual(path: Path | None = None) -> list[Chunk]:
    path = Path(path or config.DATA_DIR / "politicas_da_loja.pdf")
    reader = PdfReader(str(path))
    raw = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in reader.pages)
    lines = [ln for ln in _clean_lines(raw)]

    chunks: list[Chunk] = []
    expected, section, title = 1, 0, ""
    cur_id, cur_title, buf = "", "", []

    def flush():
        nonlocal buf
        text = "\n".join(l for l in buf if l.strip()).strip()
        if cur_id and text:
            chunks.append(Chunk(cur_id, section, cur_title, text))
        buf = []

    for line in lines:
        m_main = re.match(r"^(\d{1,2})\.\s+(\S.*)$", line)
        # título principal: numeração sequencial, curto e sem ':' (evita a lista "1. Saudação: ...")
        if m_main and int(m_main.group(1)) == expected and len(line) < 70 and ":" not in line:
            flush()
            section, title = expected, m_main.group(2).strip()
            cur_id, cur_title = str(section), title
            expected += 1
            continue
        m_sub = re.match(r"^(\d{1,2})\.(\d{1,2})\s+(\S.*)$", line)
        if section and m_sub and int(m_sub.group(1)) == section:
            flush()
            cur_id, cur_title = f"{section}.{m_sub.group(2)}", f"{title} — {m_sub.group(3).strip()}"
            continue
        if section:
            buf.append(line)
    flush()
    return chunks


@lru_cache(maxsize=1)
def customer_chunks() -> tuple[Chunk, ...]:
    return tuple(c for c in parse_manual() if c.section not in INTERNAL_SECTIONS)


# ----------------------------------------------------------------------- BM25
class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: list[str], i: int) -> float:
        dl, s = len(self.docs[i]), 0.0
        for t in query:
            f = self.tf[i].get(t, 0)
            if f:
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


# Expansão mínima de consulta (stems de 5 letras) para o vocabulário do manual.
_SYNONYMS = {
    "devol": ["arrep", "reemb"],
    "arrep": ["devol", "reemb"],
    "troca": ["defei", "prefe"],
    "defei": ["garan", "troca"],
    "quebr": ["defei", "garan"],
    "estra": ["defei", "garan"],
    "entre": ["frete", "prazo"],
    "envio": ["frete", "prazo"],
    "parce": ["credi", "paral"],
    "desco": ["promo", "pix"],
    "dados": ["lgpd", "priva"],
}


def _expand(q: list[str]) -> list[str]:
    return q + [s for t in q for s in _SYNONYMS.get(t, [])]


def search(question: str, k: int = 3) -> list[Chunk]:
    chunks = list(customer_chunks())
    bm = _BM25([stems(f"{c.title} {c.text}") for c in chunks])
    q = _expand(stems(question))
    ranked = sorted(((bm.score(q, i), i) for i in range(len(chunks))), reverse=True)
    return [chunks[i] for s, i in ranked[:k] if s > 0]


def by_topic(topic: str) -> list[Chunk]:
    sections = TOPICS.get(topic, [])
    return [c for c in customer_chunks() if c.section in sections]


def consult(topic: str, question: str | None = None) -> dict:
    """Ponto de entrada usado pela ferramenta do agente."""
    if topic in TOPICS:
        found = by_topic(topic)
    else:
        found = search(question or topic)
    return {
        "source": "Manual de Políticas e Procedimentos v2.1 (jun/2025)",
        "sections": [{"id": c.chunk_id, "title": c.title, "text": c.text} for c in found],
        **({} if found else {"note": "Nada encontrado no manual para essa pergunta; não invente — encaminhe à equipe."}),
    }
