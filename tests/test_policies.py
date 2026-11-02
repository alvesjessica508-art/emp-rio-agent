"""Parsing do manual e recuperação."""

from emporio_agent import policies


def ids(chunks):
    return [c.chunk_id for c in chunks]


def test_manual_is_split_into_sections():
    all_ids = ids(policies.parse_manual())
    for expected in ["1", "1.2", "2", "3", "3.1", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "6.2", "8.1", "8.3", "9"]:
        assert expected in all_ids


def test_internal_sections_are_not_customer_facing():
    sections = {c.section for c in policies.customer_chunks()}
    assert not sections & {7, 10}
    assert "Saudação" not in " ".join(c.text for c in policies.customer_chunks())


def test_topic_returns_whole_section_with_key_rules():
    r = policies.consult("trocas_devolucoes")
    text = " ".join(s["text"] for s in r["sections"]).lower()
    for must in ["7 (sete) dias", "30 (trinta) dias", "10 dias úteis", "boquilhas"]:
        assert must in text
    pay = " ".join(s["text"] for s in policies.consult("pagamento")["sections"])
    assert "5% de desconto" in pay and "R$ 80,00" in pay


def test_table_rows_survive_parsing():
    hours = policies.consult("horarios")["sections"][0]["text"]
    assert "Sábado | 09:00 às 13:00" in hours


def test_fallback_search_finds_relevant_sections():
    assert "4.1" in ids(policies.search("posso devolver meu pedido?"))
    assert "6.2" in ids(policies.search("o que é rain check"))
    assert "9" in ids(policies.search("como excluir meus dados pessoais"))


def test_unknown_question_says_nothing_found():
    r = policies.consult("outro", "qwertyuiop zxcvbnm")
    assert r["sections"] == [] and "note" in r
