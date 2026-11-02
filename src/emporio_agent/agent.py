"""Loop do agente: LLM com function calling (API compatível com OpenAI).

Fluxo de cada turno:
  mensagem -> LLM -> [chama ferramentas -> resultado JSON -> LLM]* -> resposta final
O loop é escrito à mão (~60 linhas) em vez de usar um framework: o problema tem
7 ferramentas e nenhum grafo/estado complexo, e o loop explícito deixa limites,
logs e tratamento de erro visíveis.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import config
from .prompts import build_system_prompt
from .tools import ToolBox

log = logging.getLogger(__name__)

FALLBACK_BUSY = "Opa, tive uma instabilidade aqui do meu lado. Pode repetir a mensagem em instantes? Se preferir, a equipe também atende pelo WhatsApp (67) 3341-4444."
FALLBACK_LOOP = "Me enrolei um pouco com essa consulta. Pode me contar de novo o que você precisa, de um jeito mais direto? Se preferir, posso acionar a equipe."


class ConfigError(RuntimeError):
    """Erro de configuração do provedor (chave/URL/modelo)."""


@dataclass
class ToolTrace:
    name: str
    arguments: dict
    result: dict


@dataclass
class AgentReply:
    text: str
    trace: list[ToolTrace] = field(default_factory=list)


class EmporioAgent:
    def __init__(
        self,
        settings: config.Settings | None = None,
        toolbox: ToolBox | None = None,
        client: Any | None = None,
        history: list[dict] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings = settings or config.Settings()
        self.toolbox = toolbox or ToolBox(now=now or config.now)
        self._now = now or self.toolbox.now  # um único relógio para prompt e ferramentas
        self._client = client
        self.history: list[dict] = list(history or [])

    # ------------------------------------------------------------------ cliente
    @property
    def client(self):
        if self._client is None:
            if not self.settings.api_key:
                raise ConfigError("LLM_API_KEY não definida. Copie .env.example para .env e preencha a chave.")
            from openai import OpenAI

            self._client = OpenAI(api_key=self.settings.api_key, base_url=self.settings.base_url, timeout=60, max_retries=2)
        return self._client

    def _chat(self, messages: list[dict]):
        return self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            tools=self.toolbox.schemas,
            tool_choice="auto",
            temperature=self.settings.temperature,
        )

    # ------------------------------------------------------------------- turno
    def respond(self, user_message: str) -> AgentReply:
        text_in = (user_message or "").strip()[: self.settings.max_user_chars]
        if not text_in:
            return AgentReply("Oi! Em que posso ajudar? 🎸")

        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(self._now())},
            *self.history[-self.settings.history_window :],
            {"role": "user", "content": text_in},
        ]
        trace: list[ToolTrace] = []
        final: str | None = None

        try:
            for _ in range(self.settings.max_tool_steps):
                msg = self._chat(messages).choices[0].message
                calls = getattr(msg, "tool_calls", None) or []
                if not calls:
                    final = (msg.content or "").strip()
                    if not final and trace:  # alguns modelos devolvem vazio após tool results
                        messages.append({"role": "user", "content": "(sistema) Responda ao cliente agora, com base nas informações acima."})
                        final = (self._chat(messages).choices[0].message.content or "").strip()
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                            for c in calls
                        ],
                    }
                )
                for c in calls:
                    result = self.toolbox.call(c.function.name, c.function.arguments)
                    args = _safe_json(c.function.arguments)
                    trace.append(ToolTrace(c.function.name, args, result))
                    log.info("tool %s(%s) -> %s", c.function.name, args, str(result)[:200])
                    messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, ensure_ascii=False)})
        except ConfigError:
            raise
        except Exception as e:  # erro de rede/provedor
            if _is_config_problem(e):
                raise ConfigError(f"Problema de configuração do provedor ({type(e).__name__}): {e}") from e
            log.exception("falha ao chamar o LLM")
            return AgentReply(FALLBACK_BUSY, trace)

        text = final or FALLBACK_LOOP
        self.history += [{"role": "user", "content": text_in}, {"role": "assistant", "content": text}]
        self.history = self.history[-self.settings.history_window :]
        return AgentReply(text, trace)

    def reset(self) -> None:
        self.history = []


def _safe_json(raw: str | None) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {"_raw": raw}
    except json.JSONDecodeError:
        return {"_raw": raw}


def _is_config_problem(e: Exception) -> bool:
    try:
        import openai

        return isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError))
    except ImportError:  # pragma: no cover
        return False
