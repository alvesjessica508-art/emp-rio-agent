"""Configuração central: caminhos, provedor do LLM e relógio da loja."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # .env é opcional
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
VAR_DIR = Path(os.getenv("VAR_DIR", ROOT / "var"))  # sessões e tickets (git-ignored)

STORE_TZ = ZoneInfo("America/Campo_Grande")


def now() -> datetime:
    """Data/hora atual no fuso da loja.

    `AGENT_NOW` (ISO 8601, ex.: 2026-03-25T10:30) permite fixar o relógio, o que
    deixa as demos reproduzíveis e coerentes com o "instantâneo" dos CSVs.
    """
    override = os.getenv("AGENT_NOW")
    if override:
        dt = datetime.fromisoformat(override)
        return dt if dt.tzinfo else dt.replace(tzinfo=STORE_TZ)
    return datetime.now(STORE_TZ)


@dataclass
class Settings:
    """Parâmetros do LLM (qualquer API compatível com OpenAI Chat Completions)."""

    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    )
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.5-flash"))
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.2")))
    max_tool_steps: int = field(default_factory=lambda: int(os.getenv("MAX_TOOL_STEPS", "6")))
    history_window: int = field(default_factory=lambda: int(os.getenv("HISTORY_WINDOW", "20")))
    max_user_chars: int = 2000
