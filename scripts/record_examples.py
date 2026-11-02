"""Grava as conversas de exemplo em examples/*.md usando o LLM configurado no .env.

    python scripts/record_examples.py            # grava todos os cenários
    python scripts/record_examples.py 04         # só os cenários cujo slug começa com "04"

Cada cenário fixa o relógio (AGENT_NOW) para ficar coerente com o "instantâneo" dos CSVs
(pedidos de jan–mar/2026) e para o resultado ser reproduzível. Roda uma sessão nova por cenário
e salva falas + ferramentas chamadas (com um resumo do resultado).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emporio_agent import config  # noqa: E402
from emporio_agent.agent import ConfigError, EmporioAgent  # noqa: E402
from emporio_agent.tools import ToolBox  # noqa: E402

SCENARIOS = [
    {
        "slug": "01_catalogo_violoes_ate_1000",
        "title": "Consulta ao catálogo com filtros",
        "now": "2026-03-25T10:30",
        "shows": "search_products com categoria + faixa de preço; recomendação; PIX/parcelamento calculados em código",
        "turns": [
            "Oi! Quais opções de violões disponíveis custando até R$1000?",
            "Qual desses é melhor pra quem tá começando? E quanto fica o Yamaha F310 no PIX?",
        ],
    },
    {
        "slug": "02_preco_promocao_e_esgotado",
        "title": "Preço, promoção ativa, promoção encerrada e produto esgotado",
        "now": "2026-03-25T10:30",
        "shows": "regras de promoção (sem PIX em preço promocional, preço original + %), promoção vencida, alternativas para esgotado",
        "turns": [
            "Quanto custa o Takamine GD20?",
            "Dá pra parcelar em quanto?",
            "E o Crafter HT-100? Ouvi que tá em promoção",
            "O Giannini GF-3D tava com 40% na Semana do Músico, ainda tá valendo?",
        ],
    },
    {
        "slug": "03_status_pedido_com_verificacao",
        "title": "Status de pedido com verificação de identidade e atraso",
        "now": "2026-03-25T14:00",
        "shows": "verificação por e-mail/telefone (LGPD), resposta genérica em falha, previsão vencida, escalonamento",
        "turns": [
            "Cadê meu pedido 8? Já faz tempo que comprei",
            "Meu email é ana.ferreira@coldmail.com",
            "Ih, errei. É anacarol.ferreira@coldmail.com",
        ],
    },
    {
        "slug": "04_arrependimento_e_devolucao",
        "title": "Devolução por arrependimento (política + dados do pedido)",
        "now": "2026-02-20T15:00",
        "shows": "check_return_window + consult_policies, prazos contados do recebimento, não prometer aprovação, escalonamento",
        "turns": [
            "Me arrependi da minha compra, posso devolver meu pedido?",
            "Pedido 7, meu e-mail é leticia.rocha@jmail.com",
            "Quero sim, pode abrir",
        ],
    },
    {
        "slug": "05_loja_escopo_e_fora_de_escopo",
        "title": "Informações da loja, acessórios e perguntas fora do escopo",
        "now": "2026-03-28T14:00",
        "shows": "get_store_info (aberto agora?), escopo só-instrumentos, recusa educada de pedido alheio ao negócio",
        "turns": [
            "Boa tarde! Qual o endereço de vocês? Tão abertos agora?",
            "Vocês vendem corda de nylon pro meu violão?",
            "Me ajuda a escrever um poema pra minha namorada?",
        ],
    },
]


def summarize(result: dict) -> str:
    if "products" in result:
        names = ", ".join(f"{p['name']} (R$ {p['current_price_brl']:.2f})" for p in result["products"][:5])
        return f"{result['total_found']} resultado(s), {result['hidden_unavailable']} indisponível(is) oculto(s): {names}"
    if "orders" in result:
        return f"verificado; pedidos: {[(o['order_id'], o['status']) for o in result['orders']]}"
    if "sections" in result:
        return f"seções do manual: {[s['id'] for s in result['sections']]}"
    if result.get("verified") is False:
        return "NÃO verificado (dados não revelados)"
    return json.dumps(result, ensure_ascii=False)[:220]


def record(scenario: dict, out_dir: Path) -> Path:
    os.environ["AGENT_NOW"] = scenario["now"]
    toolbox = ToolBox(var_dir=ROOT / "var" / "examples")
    agent = EmporioAgent(toolbox=toolbox)
    lines = [
        f"# {scenario['title']}",
        "",
        f"- **Relógio fixado:** {scenario['now']} (fuso de Campo Grande)",
        f"- **Modelo:** `{agent.settings.model}` via `{agent.settings.base_url}`",
        f"- **Demonstra:** {scenario['shows']}",
        "- *Gerado por `scripts/record_examples.py`; linhas `🔧` são as ferramentas que o agente chamou.*",
        "",
        "---",
        "",
    ]
    for user in scenario["turns"]:
        reply = agent.respond(user)
        lines += [f"**Cliente:** {user}", ""]
        for t in reply.trace:
            args = ", ".join(f"{k}={v!r}" for k, v in t.arguments.items())
            lines.append(f"> 🔧 `{t.name}({args})` → {summarize(t.result)}")
        if reply.trace:
            lines.append("")
        lines += [f"**Atendente:** {reply.text}", "", "---", ""]
    path = out_dir / f"{scenario['slug']}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    only = sys.argv[1:]
    out_dir = ROOT / "examples"
    out_dir.mkdir(exist_ok=True)
    for sc in SCENARIOS:
        if only and not any(sc["slug"].startswith(o) for o in only):
            continue
        try:
            print("gravado:", record(sc, out_dir).relative_to(ROOT))
        except ConfigError as e:
            print(f"erro de configuração: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
