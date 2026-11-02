"""Interface de linha de comando: conversa com o agente no terminal."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid

from .agent import ConfigError, EmporioAgent
from .memory import SessionStore

HELP = "Comandos: /novo (limpa a conversa) · /debug (mostra as ferramentas usadas) · /sair"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="emporio-agent", description="Atendimento Empório da Música (CLI)")
    ap.add_argument("--session", help="ID da sessão para retomar uma conversa (padrão: nova sessão)")
    ap.add_argument("--debug", action="store_true", help="mostra chamadas de ferramenta e resultados")
    ap.add_argument("--verbose", action="store_true", help="logs detalhados")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    session_id = args.session or f"cli-{uuid.uuid4().hex[:8]}"
    sessions = SessionStore(session_id)
    agent = EmporioAgent(history=sessions.load())
    debug = args.debug

    print(f"🎸 Empório da Música — atendimento (sessão: {session_id})")
    print(HELP + "\n")
    if agent.history:
        print(f"[retomando conversa com {len(agent.history)} mensagens]\n")

    while True:
        try:
            user = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user in ("/sair", "/exit", "/quit"):
            break
        if user == "/novo":
            agent.reset()
            sessions.clear()
            print("[conversa reiniciada]\n")
            continue
        if user == "/debug":
            debug = not debug
            print(f"[debug {'ligado' if debug else 'desligado'}]\n")
            continue

        try:
            reply = agent.respond(user)
        except ConfigError as e:
            print(f"\n[erro de configuração] {e}\n", file=sys.stderr)
            return 2

        if debug:
            for t in reply.trace:
                print(f"  ↳ {t.name}({json.dumps(t.arguments, ensure_ascii=False)})")
                print(f"    {json.dumps(t.result, ensure_ascii=False)[:400]}")
        print(f"\nAtendente: {reply.text}\n")
        sessions.save(agent.history)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
