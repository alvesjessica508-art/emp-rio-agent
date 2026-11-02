"""Camada de dados: carrega, limpa e consulta os CSVs da loja.

Escolhas:
- `csv` da stdlib + dataclasses (a base é minúscula; pandas/SQL seriam peso morto).
- Regras de negócio determinísticas (preço efetivo, disponibilidade, verificação
  de cliente) ficam aqui, fora do LLM, para que o modelo nunca "calcule" nem "deduza".
"""

from __future__ import annotations

import csv
import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import config
from .text import digits, norm, stems

# --------------------------------------------------------------------------- #
# Qualidade do cadastro
# --------------------------------------------------------------------------- #
# Em parte do catálogo (baixos, baterias, teclados) a descrição fala de outra
# marca/modelo que o nome do produto (ex.: "Music Man Bass 1X" descrito como
# "Fender Jazz Bass"). Nome, preço e specs são tratados como fonte de verdade
# e a descrição, nesses casos, é suprimida para o agente não repassar dado errado.
KNOWN_BRANDS = [
    "yamaha", "tagima", "giannini", "rozini", "shelby", "crafter", "martin", "taylor",
    "takamine", "kala", "kalani", "ohana", "fender", "gibson", "ibanez", "prs",
    "music man", "korg", "nord", "roland", "pearl", "tama",
]  # fmt: skip
MODEL_HINTS = {  # modelo -> marca a que pertence
    "precision": "fender",
    "jazz bass": "fender",
    "stingray": "music man",
    "stage custom": "yamaha",
    "export": "pearl",
    "nord stage": "nord",
}


def _brands_in(text: str) -> set[str]:
    t = norm(text)
    return {b for b in KNOWN_BRANDS if re.search(rf"\b{re.escape(b)}\b", t)}


def description_is_reliable(name: str, description: str) -> bool:
    name_brands = _brands_in(name)
    desc_brands = _brands_in(description)
    if desc_brands - name_brands:
        return False
    d = norm(description)
    for hint, brand in MODEL_HINTS.items():
        if re.search(rf"\b{re.escape(hint)}\b", d) and brand not in name_brands:
            return False
    return True


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    percent: int
    label: str
    active: bool


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    category_id: int
    category: str
    price: float
    stock: int
    status: str  # active | discontinued | coming_soon
    description: str
    description_reliable: bool
    specs: dict = field(default_factory=dict)

    @property
    def availability(self) -> str:
        if self.status == "discontinued":
            return "descontinuado"
        if self.status == "coming_soon":
            return "em_breve"
        return "disponivel" if self.stock > 0 else "esgotado"

    @property
    def purchasable(self) -> bool:
        return self.availability == "disponivel"


@dataclass(frozen=True)
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    total: float
    payment_method: str
    tracking_code: str
    estimated_delivery: date | None
    notes: str
    items: tuple[OrderItem, ...]


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_specs(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------------------- #
# Loja de dados
# --------------------------------------------------------------------------- #
class DataStore:
    def __init__(self, data_dir: Path | None = None):
        d = Path(data_dir or config.DATA_DIR)
        self.categories = {int(r["category_id"]): r["name"] for r in _read_csv(d / "categories.csv")}

        self.products: dict[int, Product] = {}
        for r in _read_csv(d / "products.csv"):
            pid = int(r["product_id"])
            self.products[pid] = Product(
                product_id=pid,
                name=" ".join(r["name"].split()),
                category_id=int(r["category_id"]),
                category=self.categories.get(int(r["category_id"]), "?"),
                price=float(r["price_brl"]),
                stock=int(r["stock_quantity"] or 0),
                status=r["status"],
                description=r["description"],
                description_reliable=description_is_reliable(r["name"], r["description"]),
                specs=_parse_specs(r["specs"]),
            )

        self.promotions = [
            Promotion(
                int(r["promotion_id"]), int(r["product_id"]), int(r["discount_percent"]),
                r["description"], r["is_active"] == "1",
            )
            for r in _read_csv(d / "promotions.csv")
        ]  # fmt: skip

        self.customers = {
            int(r["customer_id"]): Customer(
                int(r["customer_id"]), r["name"], r["phone"], r["email"], r["city"]
            )
            for r in _read_csv(d / "customers.csv")
        }

        items: dict[int, list[OrderItem]] = {}
        for r in _read_csv(d / "order_items.csv"):
            items.setdefault(int(r["order_id"]), []).append(
                OrderItem(int(r["product_id"]), int(r["quantity"]))
            )
        self.orders: dict[int, Order] = {}
        for r in _read_csv(d / "orders.csv"):
            oid = int(r["order_id"])
            self.orders[oid] = Order(
                oid, int(r["customer_id"]), date.fromisoformat(r["order_date"]), r["status"],
                float(r["total_brl"]), r["payment_method"], r["tracking_code"],
                _date(r["estimated_delivery"]), r["notes"], tuple(items.get(oid, [])),
            )  # fmt: skip

    # ------------------------------------------------------------------ preços
    def active_promotion(self, product_id: int) -> Promotion | None:
        """Maior desconto ativo do produto. Promoções não são cumulativas (manual §6.2)."""
        active = [p for p in self.promotions if p.product_id == product_id and p.active]
        return max(active, key=lambda p: p.percent, default=None)

    def effective_price(self, product: Product) -> tuple[float, Promotion | None]:
        promo = self.active_promotion(product.product_id)
        if promo:
            return round(product.price * (1 - promo.percent / 100), 2), promo
        return product.price, None

    def last_promotion(self, product_id: int) -> Promotion | None:
        """Última promoção *encerrada* do produto (para responder "ainda está em promoção?")."""
        old = [p for p in self.promotions if p.product_id == product_id and not p.active]
        return max(old, key=lambda p: p.promotion_id, default=None)

    # ---------------------------------------------------------------- produtos
    def resolve_category(self, name: str) -> int | None:
        target = stems(name, drop_stopwords=True)
        if not target:
            return None
        for cid, cname in self.categories.items():
            if any(t in stems(cname) for t in target):
                return cid
        return None

    def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        string_type: str | None = None,
        electroacoustic: bool | None = None,
        include_unavailable: bool = False,
        limit: int = 8,
    ) -> dict:
        """Busca no catálogo.

        Com `query` (cliente perguntando por um item) itens indisponíveis entram
        sinalizados — nunca fingimos que o produto não existe. Navegando só por
        categoria/preço, escondemos os indisponíveis (e informamos quantos).
        """
        pool = list(self.products.values())

        if category:
            cid = self.resolve_category(category)
            if cid is None:
                return {"error": f"Categoria desconhecida: {category!r}", "categories": list(self.categories.values())}
            pool = [p for p in pool if p.category_id == cid]

        if string_type:
            want = {"nylon": "nylon", "aco": "steel", "aço": "steel", "steel": "steel"}.get(norm(string_type))
            if want:
                pool = [p for p in pool if p.specs.get("strings") == want]
        if electroacoustic is not None:
            flag = "yes" if electroacoustic else "no"
            pool = [p for p in pool if p.specs.get("electronics") == flag]

        match = "filtros"
        scored: list[tuple[float, Product]] = []
        if query and stems(query):
            q = stems(query)
            q_compact = re.sub(r"[^a-z0-9]", "", norm(query))
            for p in pool:
                name_t = set(stems(p.name))
                other_t = set(stems(f"{p.category} {p.description if p.description_reliable else ''}"))
                hits_name = sum(t in name_t for t in q)
                hits_other = sum((t in other_t) and (t not in name_t) for t in q)
                # "gd 20" -> "gd20": só para consultas com 2+ termos (evita "kala" casar "kalani")
                compact_hit = (
                    len(q) >= 2
                    and len(q_compact) >= 4
                    and q_compact in re.sub(r"[^a-z0-9]", "", norm(p.name))
                )
                if hits_name + hits_other == len(q) or compact_hit:
                    scored.append((hits_name * 2 + hits_other + (3 if compact_hit else 0), p))
            match = "exata"
            if not scored:  # fallback aproximado pelo nome
                names = {norm(p.name): p for p in pool}
                for close in difflib.get_close_matches(norm(query), list(names), n=3, cutoff=0.5):
                    scored.append((1.0, names[close]))
                match = "aproximada" if scored else "nenhuma"
            scored.sort(key=lambda sp: (-sp[0], self.effective_price(sp[1])[0]))
            results = [p for _, p in scored]
            if include_unavailable is False:
                include_unavailable = True  # pergunta específica: mostrar tudo, sinalizado
        else:
            results = sorted(pool, key=lambda p: self.effective_price(p)[0])

        def in_range(p: Product) -> bool:
            price = self.effective_price(p)[0]
            return (min_price is None or price >= min_price) and (max_price is None or price <= max_price)

        results = [p for p in results if in_range(p)]
        hidden = 0
        if not include_unavailable:
            visible = [p for p in results if p.purchasable]
            hidden = len(results) - len(visible)
            results = visible

        return {
            "match": match,
            "total_found": len(results),
            "hidden_unavailable": hidden,
            "products": [self.product_view(p) for p in results[: max(1, min(limit, 15))]],
        }

    def product_view(self, p: Product) -> dict:
        price, promo = self.effective_price(p)
        view: dict = {
            "product_id": p.product_id,
            "name": p.name,
            "category": p.category,
            "availability": p.availability,
            "list_price_brl": p.price,
            "current_price_brl": price,
        }
        if promo:
            view["promotion"] = {"label": promo.label, "discount_percent": promo.percent}
        else:
            view["pix_price_brl"] = round(price * 0.95, 2)  # manual §3: 5% no PIX, só sem promoção
            last = self.last_promotion(p.product_id)
            if last:
                view["expired_promotion"] = f"{last.label} ({last.percent}%) — ENCERRADA, não vale mais"
        if p.availability == "disponivel":
            view["stock_units"] = p.stock
            if p.stock <= 3:
                view["low_stock"] = True
        specs = {k: v for k, v in p.specs.items() if v not in ("", None)}
        view["specs"] = specs
        if p.description_reliable:
            view["description"] = p.description
        else:
            view["description_note"] = (
                "Descrição do cadastro inconsistente com o nome do produto; "
                "use apenas nome, preço e specs. Não cite marca/modelo da descrição."
            )
        return view

    def get_product(self, product_id: int) -> Product | None:
        return self.products.get(product_id)

    # ------------------------------------------------------ clientes e pedidos
    def customers_by_contact(self, contact: str) -> list[Customer]:
        c = (contact or "").strip()
        if "@" in c:
            return [x for x in self.customers.values() if x.email.lower() == c.lower()]
        d = digits(c)
        if d.startswith("55") and len(d) > 11:
            d = d[2:]
        if len(d) < 9:
            return []
        return [x for x in self.customers.values() if digits(x.phone).endswith(d)]

    def authorize(self, contact: str, order_id: int | None = None) -> tuple[list[Customer], str | None]:
        """Valida que `contact` (e-mail/telefone do cadastro) dá direito a ver os dados.

        Devolve (clientes autorizados, código de erro). Erros são deliberadamente
        genéricos para não permitir descobrir quais pedidos/contatos existem.
        Um e-mail compartilhado por dois clientes (existe nos dados) só é aceito
        junto com o número de um pedido que pertença a um deles.
        """
        matches = self.customers_by_contact(contact)
        if not matches:
            return [], "nao_verificado"
        if order_id is not None:
            order = self.orders.get(order_id)
            owners = [c for c in matches if order and c.customer_id == order.customer_id]
            return (owners, None) if owners else ([], "nao_verificado")
        if len(matches) > 1:
            return [], "contato_ambiguo"
        return matches, None

    def order_view(self, o: Order) -> dict:
        items = []
        for it in o.items:
            prod = self.products.get(it.product_id)
            items.append({"product": prod.name if prod else f"produto {it.product_id}", "quantity": it.quantity})
        return {
            "order_id": o.order_id,
            "order_date": o.order_date.isoformat(),
            "status": o.status,
            "status_pt": STATUS_PT.get(o.status, o.status),
            "total_brl": o.total,
            "payment": payment_pt(o.payment_method),
            "items": items,
            "tracking_code": o.tracking_code or None,
            "estimated_delivery": o.estimated_delivery.isoformat() if o.estimated_delivery else None,
            "notes": o.notes or None,
        }

    def orders_of(self, customer_ids: set[int]) -> list[Order]:
        return sorted(
            (o for o in self.orders.values() if o.customer_id in customer_ids),
            key=lambda o: o.order_date,
            reverse=True,
        )


# Significado dos status: o manual não os define; descrições neutras (suposição documentada no README).
STATUS_PT = {
    "pending": "recebido, aguardando confirmação",
    "confirmed": "confirmado, em preparação (ainda não despachado)",
    "shipped": "despachado, em transporte",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def payment_pt(code: str) -> str:
    if code.startswith("credit_"):
        return f"cartão de crédito em {code.split('_')[1]}"
    return {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto bancário"}.get(code, code)
