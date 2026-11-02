"""Regras de negócio determinísticas extraídas do manual.

Contas e datas ficam em código (testável), não no LLM. Cada constante cita a
seção do manual de onde veio; se o manual mudar, este é o único lugar a ajustar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .data_store import DataStore, Order
from .text import brl

# --- manual §1.2 / §2 -------------------------------------------------------
STORE_INFO = {
    "name": "Empório da Música Instrumentos Musicais Ltda. (nome fantasia: Empório da Música)",
    "address": "Rua 14 de Maio, 3200 — Centro, Campo Grande – MS, CEP 79202-333",
    "phone_whatsapp": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
    "founded": 2008,
    "sells_only": "instrumentos musicais (não vende cordas, palhetas, cabos, cases, pedais nem amplificadores)",
}
# weekday(): segunda=0 ... domingo=6 -> (abre, fecha) em horas
OPENING_HOURS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}
HOURS_TEXT = "Segunda a sexta, 09h às 18h; sábado, 09h às 13h; domingo e feriados fechado."
_WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# --- manual §3 --------------------------------------------------------------
PIX_DISCOUNT = 0.05
# (n_min, n_max, parcela mínima). §3.1; "até 3x ... (exceto abaixo de R$ 50,00)" foi lido
# como parcela mínima de R$ 50 — a tabela da §3 diz R$ 100 para qualquer parcelamento,
# o que contradiz a §3.1; adotamos a §3.1 por ser a regra detalhada (ver README).
INSTALLMENT_RULES = [(2, 3, 50.0), (4, 6, 80.0), (7, 12, 100.0)]
COMBINED_PAYMENT_MIN = 2000.0

# --- manual §4 / §8 ---------------------------------------------------------
REGRET_DAYS = 7  # §4.1, após o recebimento
DEFECT_EXCHANGE_DAYS = 30  # §4.2, após a compra
LEGAL_WARRANTY_DAYS = 90  # §8.1, após o recebimento


def open_status(now: datetime) -> dict:
    wd = now.weekday()
    hours = OPENING_HOURS.get(wd)
    is_open = bool(hours and hours[0] <= now.hour + now.minute / 60 < hours[1])
    # próxima abertura
    probe = now
    for _ in range(8):
        h = OPENING_HOURS.get(probe.weekday())
        if h:
            opens = probe.replace(hour=h[0], minute=0, second=0, microsecond=0)
            if opens > now:
                nxt = opens
                break
        probe = (probe + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # pragma: no cover
        nxt = None
    out = {
        "now": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": _WEEKDAYS[wd],
        "open_now_by_schedule": is_open,
        "note": "Calculado pela grade semanal; não considero feriados — se for feriado, a loja está fechada.",
    }
    if not is_open and nxt:
        out["next_opening"] = f"{_WEEKDAYS[nxt.weekday()]}, {nxt.strftime('%d/%m')} às {nxt.hour:02d}h"
    return out


def installment_plans(total: float) -> list[dict]:
    plans = [{"installments": 1, "each_brl": round(total, 2), "label": f"1x de {brl(total)} (à vista)"}]
    for lo, hi, min_parcel in INSTALLMENT_RULES:
        for n in range(lo, hi + 1):
            each = round(total / n, 2)
            if each >= min_parcel:
                plans.append({"installments": n, "each_brl": each, "label": f"{n}x de {brl(each)} sem juros"})
    return plans


def payment_options(total: float, promotional: bool) -> dict:
    out: dict = {
        "total_brl": round(total, 2),
        "credit_card": installment_plans(total),
        "credit_card_max_installments": installment_plans(total)[-1]["installments"],
        "debit_card_brl": round(total, 2),
        "boleto_brl": round(total, 2),
        "boleto_note": "compensação em até 3 dias úteis",
        "combined_payment_allowed": total > COMBINED_PAYMENT_MIN,
    }
    if promotional:
        out["pix_brl"] = round(total, 2)
        out["pix_note"] = "Preço já é promocional: o desconto de 5% do PIX não se aplica (promoções não são cumulativas)."
    else:
        out["pix_brl"] = round(total * (1 - PIX_DISCOUNT), 2)
        out["pix_note"] = "5% de desconto no PIX sobre o preço de tabela."
    return out


def return_windows(order: Order, today: date) -> dict:
    """Prazos de arrependimento / defeito / garantia legal de um pedido.

    O CSV não traz a data real de recebimento; usamos `estimated_delivery` como
    proxy (e dizemos isso na resposta). Direito de arrependimento: 7 dias após
    o recebimento. Troca por defeito: 30 dias após a COMPRA. Garantia legal: 90
    dias após o recebimento.
    """
    base = {"order_id": order.order_id, "status": order.status, "today": today.isoformat()}
    if order.status == "cancelled":
        return {**base, "applicable": False, "reason": "Pedido cancelado: não há produto para devolver.", "cancel_note": order.notes or None}
    if order.status != "delivered":
        return {
            **base,
            "applicable": False,
            "reason": "Pedido ainda não foi entregue; os prazos de devolução/garantia só começam a contar no recebimento. "
            "Se o cliente quer desistir antes disso, encaminhe para a equipe.",
        }
    received = order.estimated_delivery or order.order_date

    def window(start: date, days: int) -> dict:
        end = start + timedelta(days=days)
        left = (end - today).days
        return {"deadline": end.isoformat(), "open": left >= 0, "days_left": max(left, 0), "days_overdue": max(-left, 0)}

    return {
        **base,
        "applicable": True,
        "order_date": order.order_date.isoformat(),
        "received_date_used": received.isoformat(),
        "received_date_note": "Data real de recebimento não consta no sistema; usada a data estimada de entrega como referência.",
        "regret_7d_after_receipt": window(received, REGRET_DAYS),
        "defect_exchange_30d_after_purchase": window(order.order_date, DEFECT_EXCHANGE_DAYS),
        "legal_warranty_90d_after_receipt": window(received, LEGAL_WARRANTY_DAYS),
        "reminders": [
            "Arrependimento vale para compras ONLINE; produto na embalagem original, sem uso, com acessórios.",
            "Reembolso na mesma forma de pagamento em até 10 dias úteis; frete de devolução por conta da loja.",
            "Após 30 dias de defeito, a garantia é acionada com o fabricante (a loja pode intermediar se solicitado).",
            "Não prometa aprovação: a equipe valida o estado do produto.",
        ],
    }


def pix_total_for(store: DataStore, product_id: int, quantity: int = 1) -> tuple[float, bool]:
    p = store.get_product(product_id)
    price, promo = store.effective_price(p)
    return round(price * quantity, 2), promo is not None
