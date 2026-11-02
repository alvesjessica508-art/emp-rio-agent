"""Utilitários de texto: normalização, "stemming" leve e formatação em reais."""

from __future__ import annotations

import re
import unicodedata

_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "no", "na",
    "para", "pra", "com", "e", "em", "que", "qual", "quais", "tem", "voces", "quero",
    "preco", "quanto", "custa", "valor", "posso", "pode", "podem", "meu", "minha", "meus",
    "como", "onde", "quando", "se", "eu", "ter", "tenho", "fazer", "vcs", "voce", "ainda",
    "isso", "essa", "esse", "mais", "muito", "ja", "por", "ao", "aos", "ou", "sao", "foi",
}  # fmt: skip


def norm(text: str) -> str:
    """minúsculas, sem acentos."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def stem(token: str) -> str:
    """Stemmer propositalmente rudimentar: prefixo de 5 letras.

    Aproxima plurais/derivações do português ("violão"/"violões", "devolver"/
    "devolução", "troca"/"trocar") sem dependências. Mantém "kala" ≠ "kalani".
    """
    return token[:5]


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    out = re.findall(r"[a-z0-9]+", norm(text))
    if drop_stopwords:
        out = [t for t in out if t not in _STOPWORDS]
    return out


def stems(text: str, drop_stopwords: bool = True) -> list[str]:
    return [stem(t) for t in tokens(text, drop_stopwords)]


def brl(value: float) -> str:
    """1299.9 -> 'R$ 1.299,90'."""
    s = f"{value:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def digits(text: str) -> str:
    return re.sub(r"\D", "", str(text))
