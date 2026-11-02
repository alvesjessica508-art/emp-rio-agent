"""Ferramentas: verificação de identidade, pedidos, prazos, pagamentos, horário, escalonamento."""

import json
from datetime import datetime

from emporio_agent import business, config


# ----------------------------------------------------------------- pedidos / LGPD
def test_order_requires_matching_contact(toolbox):
    ok = toolbox.call("get_order_status", {"contact": "anacarol.ferreira@coldmail.com", "order_id": 8})
    assert ok["verified"] and ok["orders"][0]["order_id"] == 8
    assert ok["orders"][0]["tracking_code"] == "BRJL5544332BR"
    assert ok["customer_first_name"] == "Ana"


def test_wrong_contact_reveals_nothing(toolbox):
    r = toolbox.call("get_order_status", {"contact": "fulano@jmail.com", "order_id": 8})
    assert r["verified"] is False and "orders" not in r
    # contato de OUTRO cliente + pedido que não é dele: mesma resposta genérica
    r2 = toolbox.call("get_order_status", {"contact": "lucas.mendes@jmail.com", "order_id": 8})
    assert r2 == r


def test_nonexistent_order_looks_same_as_wrong_contact(toolbox):
    a = toolbox.call("get_order_status", {"contact": "anacarol.ferreira@coldmail.com", "order_id": 999})
    b = toolbox.call("get_order_status", {"contact": "x@y.com", "order_id": 8})
    assert a == b and a["verified"] is False


def test_phone_formats_are_normalized(toolbox):
    for phone in ("(67) 99654-7821", "67996547821", "+55 67 99654 7821"):
        assert toolbox.call("get_order_status", {"contact": phone})["verified"] is True


def test_shared_email_needs_order_number(toolbox):
    # bruno.martins@jmail.com está em 2 cadastros (clientes 11 e 43)
    amb = toolbox.call("get_order_status", {"contact": "bruno.martins@jmail.com"})
    assert amb["verified"] is False and "mais de um cadastro" in amb["reason"]
    ok = toolbox.call("get_order_status", {"contact": "bruno.martins@jmail.com", "order_id": 10})
    assert ok["verified"] and ok["orders"][0]["order_id"] == 10


def test_order_id_can_arrive_as_string(toolbox):
    assert toolbox.call("get_order_status", {"contact": "anacarol.ferreira@coldmail.com", "order_id": "8"})["verified"]


def test_overdue_shipped_order_is_flagged(toolbox, clock):
    clock.value = datetime(2026, 3, 25, 10, 0, tzinfo=config.STORE_TZ)  # previsão era 28/02
    o = toolbox.call("get_order_status", {"contact": "anacarol.ferreira@coldmail.com", "order_id": 8})["orders"][0]
    assert o["estimated_delivery_passed"] is True
    clock.value = datetime(2026, 2, 20, 10, 0, tzinfo=config.STORE_TZ)
    o = toolbox.call("get_order_status", {"contact": "anacarol.ferreira@coldmail.com", "order_id": 8})["orders"][0]
    assert "estimated_delivery_passed" not in o


def test_pending_order_has_no_tracking(toolbox):
    o = toolbox.call("get_order_status", {"contact": "fernanda.ribeiro@coldmail.com", "order_id": 13})["orders"][0]
    assert o["tracking_code"] is None and "rastreio" in o["hint"]


# ------------------------------------------------------------------- devolução
def _window(toolbox, contact, order_id):
    return toolbox.call("check_return_window", {"contact": contact, "order_id": order_id})


def test_regret_window_open_shortly_after_delivery(toolbox, clock):
    clock.value = datetime(2026, 2, 20, 10, 0, tzinfo=config.STORE_TZ)  # entrega prevista 17/02
    w = _window(toolbox, "leticia.rocha@jmail.com", 7)
    assert w["applicable"] and w["regret_7d_after_receipt"]["open"]
    assert w["regret_7d_after_receipt"]["deadline"] == "2026-02-24"
    assert w["regret_7d_after_receipt"]["days_left"] == 4
    assert w["defect_exchange_30d_after_purchase"]["deadline"] == "2026-03-05"  # 30d após a COMPRA (03/02)


def test_windows_closed_months_later(toolbox):
    w = _window(toolbox, "lucas.mendes@jmail.com", 4)  # entregue ~22/12/2025; hoje 25/03/2026
    assert not w["regret_7d_after_receipt"]["open"]
    assert not w["defect_exchange_30d_after_purchase"]["open"]
    assert not w["legal_warranty_90d_after_receipt"]["open"]  # 22/12 + 90d = 22/03


def test_legal_warranty_can_outlive_other_windows(toolbox):
    w = _window(toolbox, "rafael.pereira@jmail.com", 5)  # entrega prevista 18/01/2026
    assert not w["regret_7d_after_receipt"]["open"]
    assert w["legal_warranty_90d_after_receipt"]["open"]  # até 18/04


def test_return_not_applicable_for_undelivered_or_cancelled(toolbox):
    assert _window(toolbox, "anacarol.ferreira@coldmail.com", 8)["applicable"] is False  # shipped
    assert _window(toolbox, "matheus.correia@hayoo.com.br", 17)["applicable"] is False  # cancelado


def test_return_window_requires_ownership(toolbox):
    assert _window(toolbox, "lucas.mendes@jmail.com", 7)["verified"] is False


# ------------------------------------------------------------------- pagamentos
def test_installments_respect_minimum_parcel():
    plans = {p["installments"]: p["each_brl"] for p in business.installment_plans(599.9)}
    assert plans[6] == 99.98 and 7 not in plans  # 7x = 85,70 < R$100
    assert max(plans) == 6
    assert max(p["installments"] for p in business.installment_plans(2199)) == 12
    assert [p["installments"] for p in business.installment_plans(40)] == [1]  # parcela <50


def test_pix_discount_not_on_promotional_price(toolbox):
    regular = toolbox.call("calculate_payment_options", {"product_id": 95})  # GD20, sem promoção
    assert regular["pix_brl"] == 2089.05
    promo = toolbox.call("calculate_payment_options", {"product_id": 90})  # HT-100, 18% off
    assert promo["total_brl"] == 1967.18 and promo["pix_brl"] == 1967.18
    assert "não se aplica" in promo["pix_note"]


def test_payment_options_rejects_unavailable_product(toolbox):
    assert "error" in toolbox.call("calculate_payment_options", {"product_id": 96})  # esgotado
    assert "error" in toolbox.call("calculate_payment_options", {"product_id": 99999})


# ------------------------------------------------------------- loja / horário
def test_store_open_status(toolbox, clock):
    clock.value = datetime(2026, 3, 25, 10, 30, tzinfo=config.STORE_TZ)  # quarta 10:30
    assert toolbox.call("get_store_info", {})["open_now_by_schedule"] is True
    clock.value = datetime(2026, 3, 28, 13, 0, tzinfo=config.STORE_TZ)  # sábado 13:00 (fechou)
    info = toolbox.call("get_store_info", {})
    assert info["open_now_by_schedule"] is False and "segunda" in info["next_opening"]
    clock.value = datetime(2026, 3, 29, 11, 0, tzinfo=config.STORE_TZ)  # domingo
    assert toolbox.call("get_store_info", {})["open_now_by_schedule"] is False
    assert toolbox.call("get_store_info", {})["address"].startswith("Rua 14 de Maio, 3200")


# ----------------------------------------------------------------- escalonamento
def test_escalation_is_persisted(toolbox, tmp_path):
    r = toolbox.call("escalate_to_human", {"category": "reclamacao", "summary": "Atraso no pedido 8", "contact": "a@b.com"})
    assert r["registered"] and "24 horas úteis" in r["sla"]
    line = json.loads((tmp_path / "escalations.jsonl").read_text().splitlines()[-1])
    assert line["ticket_id"] == r["ticket_id"] and line["category"] == "reclamacao"


# --------------------------------------------------------------- robustez
def test_dispatcher_handles_bad_calls(toolbox):
    assert "error" in toolbox.call("nao_existe", {})
    assert "error" in toolbox.call("search_products", "{json quebrado")
    assert "error" in toolbox.call("calculate_payment_options", {})  # falta product_id
    assert toolbox.call("search_products", '{"query": "Yamaha C40", "campo_extra": 1}')["products"]  # extras são ignorados
