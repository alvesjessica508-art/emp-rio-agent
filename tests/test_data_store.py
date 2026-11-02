"""Catálogo, preços, promoções e qualidade do cadastro."""

import pytest


def names(result):
    return [p["name"] for p in result["products"]]


def test_loads_all_tables(store):
    assert len(store.products) == 65
    assert len(store.customers) == 50
    assert len(store.orders) == 20


def test_price_of_specific_model(store):
    r = store.search_products(query="Takamine GD20")
    assert r["match"] == "exata"
    top = r["products"][0]
    assert top["name"].startswith("Takamine GD20")
    assert top["current_price_brl"] == 2199.0
    assert top["availability"] == "disponivel"


def test_spaced_model_name_still_matches(store):
    assert names(store.search_products(query="gd 20"))[0].startswith("Takamine GD20")


def test_single_token_brand_does_not_leak_into_similar_brand(store):
    # "kala" não deve casar "Kalani"
    assert all(n.startswith("Kala ") for n in names(store.search_products(query="kala", limit=15))[:7])
    assert not any(n.startswith("Kalani") for n in names(store.search_products(query="kala", limit=7)))


def test_guitars_under_1000_only_purchasable_and_sorted(store):
    r = store.search_products(category="Violões", max_price=1000, limit=15)
    prices = [p["current_price_brl"] for p in r["products"]]
    assert prices == sorted(prices)
    assert all(p <= 1000 for p in prices)
    assert all(p["availability"] == "disponivel" for p in r["products"])
    # Giannini GF-3D (R$ 799,90) está esgotado -> escondido na navegação, mas contado
    assert "Giannini GF-3D Dreadnought Sunburst" not in names(r)
    assert r["hidden_unavailable"] >= 2  # GF-3D (esgotado) e SN-7C (descontinuado)


def test_specific_query_shows_unavailable_items_flagged(store):
    p = store.search_products(query="Giannini GF-3D")["products"][0]
    assert p["availability"] == "esgotado"
    p = store.search_products(query="Shelby SN-7C")["products"][0]
    assert p["availability"] == "descontinuado"
    p = store.search_products(query="Kala KA-ABP-CTG")["products"][0]
    assert p["availability"] == "em_breve"


def test_active_promotion_applied_with_original_price(store):
    p = store.search_products(query="Crafter HT-100")["products"][0]
    assert p["list_price_brl"] == 2399.0
    assert p["promotion"]["discount_percent"] == 18
    assert p["current_price_brl"] == 1967.18
    assert "pix_price_brl" not in p  # PIX 5% não vale em preço promocional


def test_expired_promotion_is_never_applied(store):
    p = store.search_products(query="Giannini GF-3D")["products"][0]  # promo 40% encerrada
    assert p["current_price_brl"] == p["list_price_brl"] == 799.9
    assert "promotion" not in p
    assert "ENCERRADA" in p["expired_promotion"]


def test_pix_price_when_not_promotional(store):
    p = store.search_products(query="Takamine GD20")["products"][0]
    assert p["pix_price_brl"] == pytest.approx(2199 * 0.95, abs=0.01)


def test_price_filter_uses_promotional_price(store):
    # Ohana CK-20: R$ 549 com 20% => R$ 439,20 (entra em "até 450")
    r = store.search_products(category="Ukuleles", max_price=450, limit=15)
    assert "Ohana CK-20 Concert Natural" in names(r)


def test_inconsistent_descriptions_are_suppressed(store):
    p = store.search_products(query="Music Man Bass 1X")["products"][0]
    assert "description" not in p and "description_note" in p
    assert "Fender" not in str(p)  # a descrição fala de outra marca
    good = store.search_products(query="Yamaha C40")["products"][0]
    assert "description" in good


def test_filters_string_type_and_electroacoustic(store):
    r = store.search_products(category="Violões", string_type="aço", electroacoustic=True, limit=15)
    assert r["products"] and all(p["specs"]["strings"] == "steel" and p["specs"]["electronics"] == "yes" for p in r["products"])


def test_unknown_item_and_empty_categories(store):
    assert store.search_products(query="saxofone")["products"] == []
    assert store.search_products(query="xyzzy")["match"] == "nenhuma"
    assert store.search_products(category="Instrumentos de Sopro (Madeiras)")["products"] == []


def test_unknown_category_returns_error(store):
    assert "error" in store.search_products(category="Pedais")
