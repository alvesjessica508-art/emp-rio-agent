"""Ferramentas (function calling) expostas ao LLM e o despachante que as executa.

Princípio: o LLM *decide qual ferramenta chamar e redige a resposta*; tudo que é
dado, conta, data ou verificação de identidade é resolvido aqui, de forma
determinística, e devolvido como JSON.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime

from . import business, config, policies
from .data_store import DataStore

ESCALATION_CATEGORIES = ["reclamacao", "defeito_ou_garantia", "devolucao_ou_cancelamento", "frete_especial", "outro"]


def _schemas(store: DataStore) -> list[dict]:
    def fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required or []},
            },
        }

    return [
        fn(
            "search_products",
            "Busca no catálogo REAL da loja (preço, promoção ativa, estoque, specs). Use SEMPRE que o cliente "
            "perguntar sobre preço, disponibilidade, promoção, características ou recomendação de instrumento. "
            "Com `query` (nome/modelo/palavras-chave, ex.: 'Takamine GD20', 'ukulele tenor') itens esgotados/"
            "descontinuados também voltam, sinalizados em `availability`. Sem `query` (só categoria/preço) volta "
            "apenas o que dá para comprar. Filtros de preço usam o preço ATUAL (já com promoção ativa).",
            {
                "query": {"type": "string", "description": "Nome/modelo/marca ou palavras-chave. Não inclua preço aqui."},
                "category": {"type": "string", "enum": list(store.categories.values())},
                "min_price": {"type": "number", "description": "R$, preço atual mínimo"},
                "max_price": {"type": "number", "description": "R$, preço atual máximo"},
                "string_type": {"type": "string", "enum": ["nylon", "aço"], "description": "Tipo de corda (violões/ukuleles)"},
                "electroacoustic": {"type": "boolean", "description": "true = com captação/eletroacústico"},
                "limit": {"type": "integer", "description": "Máx. de itens (padrão 8)"},
            },
        ),
        fn(
            "calculate_payment_options",
            "Calcula PIX (5% de desconto só se NÃO houver promoção), cartão em até 12x sem juros respeitando a parcela "
            "mínima, débito e boleto. Use quando o cliente perguntar de parcelamento, PIX ou 'quanto fica'. "
            "Passe `product_id` (de search_products) — nunca calcule você mesmo.",
            {
                "product_id": {"type": "integer"},
                "quantity": {"type": "integer", "description": "Padrão 1"},
            },
            ["product_id"],
        ),
        fn(
            "get_order_status",
            "Consulta pedidos de um cliente (status, itens, rastreio, previsão). EXIGE verificação: `contact` deve ser "
            "o e-mail ou telefone cadastrados na compra. Se o cliente não informou, PEÇA antes de chamar. "
            "Nunca revele dados se `verified` for false.",
            {
                "contact": {"type": "string", "description": "E-mail ou telefone do cadastro do cliente"},
                "order_id": {"type": "integer", "description": "Número do pedido, se o cliente informou"},
            },
            ["contact"],
        ),
        fn(
            "check_return_window",
            "Para pedidos ENTREGUES: calcula se o cliente ainda está dentro dos prazos de arrependimento (7 dias), troca por "
            "defeito (30 dias) e garantia legal (90 dias). Use em pedidos de devolução/troca/defeito; combine com "
            "consult_policies('trocas_devolucoes') para as condições. Exige o mesmo contato verificado.",
            {"contact": {"type": "string"}, "order_id": {"type": "integer"}},
            ["contact", "order_id"],
        ),
        fn(
            "consult_policies",
            "Consulta o manual de políticas da loja. Use para REGRAS (trocas, devolução, garantia, frete/prazos, formas de "
            "pagamento, regras de promoção, privacidade/LGPD, quem somos). Escolha o `topic` mais próximo; use 'outro' "
            "(com `question`) só se nenhum servir. Para endereço/horário/contato prefira get_store_info.",
            {
                "topic": {"type": "string", "enum": [*policies.TOPICS, "outro"]},
                "question": {"type": "string", "description": "Pergunta do cliente (obrigatória se topic='outro')"},
            },
            ["topic"],
        ),
        fn(
            "get_store_info",
            "Endereço, telefone/WhatsApp, e-mail, horário de funcionamento e se a loja está aberta AGORA. "
            "Use para 'onde fica', 'que horas abre', 'estão abertos?', contato.",
            {},
        ),
        fn(
            "escalate_to_human",
            "Registra um chamado para a equipe humana (retorno em até 24 horas úteis). Use para reclamações, defeito/garantia, "
            "devoluções fora do prazo, frete especial (baterias etc.), ou quando você não tem como resolver. Resuma o caso "
            "para o cliente não precisar repetir.",
            {
                "category": {"type": "string", "enum": ESCALATION_CATEGORIES},
                "summary": {"type": "string", "description": "Resumo objetivo do caso (pedido, produto, o que o cliente quer)"},
                "contact": {"type": "string", "description": "E-mail/telefone do cliente, se informado"},
            },
            ["category", "summary"],
        ),
    ]


class ToolBox:
    """Registro + execução das ferramentas."""

    def __init__(self, store: DataStore | None = None, now: Callable[[], datetime] = config.now, var_dir=None):
        self.store = store or DataStore()
        self._now = now
        self.now = now
        self.var_dir = var_dir or config.VAR_DIR
        self.schemas = _schemas(self.store)
        self._impl: dict[str, Callable[..., dict]] = {
            "search_products": self.search_products,
            "calculate_payment_options": self.calculate_payment_options,
            "get_order_status": self.get_order_status,
            "check_return_window": self.check_return_window,
            "consult_policies": self.consult_policies,
            "get_store_info": self.get_store_info,
            "escalate_to_human": self.escalate_to_human,
        }

    # ---------------------------------------------------------------- dispatch
    def call(self, name: str, arguments: dict | str | None) -> dict:
        if name not in self._impl:
            return {"error": f"Ferramenta desconhecida: {name}"}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                return {"error": "Argumentos inválidos (JSON malformado)."}
        try:
            return self._impl[name](**(arguments or {}))
        except TypeError as e:  # argumento inesperado/faltando
            return {"error": f"Argumentos inválidos para {name}: {e}"}
        except Exception as e:  # nunca derrubar a conversa por erro de ferramenta
            return {"error": f"Falha ao executar {name}: {type(e).__name__}: {e}"}

    # ------------------------------------------------------------- implementações
    def search_products(self, query=None, category=None, min_price=None, max_price=None,
                        string_type=None, electroacoustic=None, limit=8, **_) -> dict:  # fmt: skip
        return self.store.search_products(
            query=query, category=category, min_price=min_price, max_price=max_price,
            string_type=string_type, electroacoustic=electroacoustic, limit=int(limit or 8),
        )  # fmt: skip

    def calculate_payment_options(self, product_id, quantity=1, **_) -> dict:
        product = self.store.get_product(int(product_id))
        if not product:
            return {"error": f"Produto {product_id} não encontrado."}
        if not product.purchasable:
            return {"error": f"'{product.name}' não está disponível para compra ({product.availability})."}
        total, promotional = business.pix_total_for(self.store, product.product_id, max(1, int(quantity or 1)))
        return {"product": product.name, "quantity": int(quantity or 1), **business.payment_options(total, promotional)}

    _NOT_VERIFIED = {
        "verified": False,
        "reason": "Não consegui verificar esses dados. Peça ao cliente para conferir o e-mail ou telefone usados na compra "
        "(e o número do pedido). NÃO revele se o pedido ou o contato existem.",
    }
    _AMBIGUOUS = {
        "verified": False,
        "reason": "Este contato está ligado a mais de um cadastro. Peça o número do pedido ou o telefone cadastrado. "
        "NÃO cite nomes ou detalhes de nenhum cadastro.",
    }

    def _authorize(self, contact, order_id):
        oid = int(order_id) if order_id not in (None, "") else None
        customers, err = self.store.authorize(str(contact or ""), oid)
        return customers, oid, err

    def get_order_status(self, contact, order_id=None, **_) -> dict:
        customers, oid, err = self._authorize(contact, order_id)
        if err == "contato_ambiguo":
            return self._AMBIGUOUS
        if err:
            return self._NOT_VERIFIED
        orders = self.store.orders_of({c.customer_id for c in customers})
        if oid is not None:
            orders = [o for o in orders if o.order_id == oid]
        today = self._now().date()
        views = []
        for o in orders[:5]:
            v = self.store.order_view(o)
            if o.status == "shipped" and o.estimated_delivery and o.estimated_delivery < today:
                v["estimated_delivery_passed"] = True
                v["hint"] = "Previsão de entrega já passou: peça desculpas, informe o rastreio e acione a equipe (escalate_to_human)."
            if o.status in ("pending", "confirmed"):
                v["hint"] = "Ainda sem código de rastreio: ele é enviado por e-mail e WhatsApp quando o pedido é despachado."
            views.append(v)
        return {
            "verified": True,
            "customer_first_name": customers[0].name.split()[0],
            "orders": views,
            "orders_shown": len(views),
            "carrier_note": "Rastreio consultável no site dos Correios ou da Jadlog; a transportadora do pedido não consta no sistema.",
        }

    def check_return_window(self, contact, order_id, **_) -> dict:
        customers, oid, err = self._authorize(contact, order_id)
        if err == "contato_ambiguo":
            return self._AMBIGUOUS
        if err or oid is None:
            return self._NOT_VERIFIED
        order = self.store.orders[oid]
        return {"verified": True, **business.return_windows(order, self._now().date())}

    def consult_policies(self, topic, question=None, **_) -> dict:
        return policies.consult(topic, question)

    def get_store_info(self, **_) -> dict:
        return {**business.STORE_INFO, "hours": business.HOURS_TEXT, **business.open_status(self._now())}

    def escalate_to_human(self, category, summary, contact=None, **_) -> dict:
        ticket = {
            "ticket_id": f"EM-{self._now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
            "created_at": self._now().isoformat(timespec="seconds"),
            "category": category if category in ESCALATION_CATEGORIES else "outro",
            "summary": summary,
            "contact": contact,
        }
        self.var_dir.mkdir(parents=True, exist_ok=True)
        with (self.var_dir / "escalations.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ticket, ensure_ascii=False) + "\n")
        return {
            "registered": True,
            "ticket_id": ticket["ticket_id"],
            "sla": "Nossa equipe retorna em até 24 horas úteis.",
            "note": "Chamado registrado em arquivo local (protótipo); em produção seria integrado ao CRM/helpdesk.",
        }
