"""Persistência do histórico de conversa (um JSON por sessão).

Guardamos só as falas (user/assistant). Resultados de ferramentas NÃO são
persistidos: estoque, promoções e status de pedido mudam, então o agente
re-consulta a cada turno em vez de confiar em dados velhos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import config


class SessionStore:
    def __init__(self, session_id: str, base: Path | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
            raise ValueError("session_id deve ter 1–64 caracteres: letras, números, '_' ou '-'.")
        self.session_id = session_id
        self.path = Path(base or config.VAR_DIR / "sessions") / f"{session_id}.json"

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]

    def save(self, history: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
