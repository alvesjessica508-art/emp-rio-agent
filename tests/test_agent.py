"""Loop do agente com um LLM falso (determinístico, sem rede)."""

import json
from types import SimpleNamespace as NS

import pytest

from emporio_agent.agent import ConfigError, EmporioAgent
from emporio_agent.config import Settings
from emporio_agent.memory import SessionStore


def tool_call(name, args, id_="call_1"):
    return NS(id=id_, type="function", function=NS(name=name, arguments=json.dumps(args)))


def reply(content=None, calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=calls or None))])


class FakeClient:
    """Devolve respostas roteirizadas e guarda as mensagens recebidas."""

    def __init__(self, script):
        self.script, self.seen = list(script), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.seen.append(json.loads(json.dumps(kw["messages"], default=str)))
        return self.script.pop(0)


def make_agent(script, toolbox, **kw):
    return EmporioAgent(settings=Settings(api_key="x"), toolbox=toolbox, client=FakeClient(script), **kw)


def test_tool_roundtrip_feeds_real_data_back_to_model(toolbox):
    agent = make_agent(
        [reply(calls=[tool_call("search_products", {"query": "Takamine GD20"})]), reply("O GD20 sai por R$ 2.199,00.")],
        toolbox,
    )
    out = agent.respond("Quanto custa o Takamine GD20?")
    assert out.text.startswith("O GD20")
    assert [t.name for t in out.trace] == ["search_products"]
    tool_msg = agent.client.seen[1][-1]
    assert tool_msg["role"] == "tool" and "2199" in tool_msg["content"]  # o modelo recebe o dado real
    assert agent.history[-2:] == [
        {"role": "user", "content": "Quanto custa o Takamine GD20?"},
        {"role": "assistant", "content": "O GD20 sai por R$ 2.199,00."},
    ]


def test_system_prompt_carries_date_and_rules(toolbox):
    agent = make_agent([reply("Oi!")], toolbox)
    agent.respond("oi")
    system = agent.client.seen[0][0]
    assert system["role"] == "system"
    assert "quarta-feira, 25/03/2026" in system["content"]
    assert "NUNCA informe preço" in system["content"]


def test_multiple_tool_calls_in_sequence(toolbox):
    agent = make_agent(
        [
            reply(calls=[tool_call("check_return_window", {"contact": "leticia.rocha@jmail.com", "order_id": 7}, "a"),
                         tool_call("consult_policies", {"topic": "trocas_devolucoes"}, "b")]),
            reply("Você ainda está no prazo."),
        ],
        toolbox,
    )
    out = agent.respond("quero devolver o pedido 7, meu email é leticia.rocha@jmail.com")
    assert [t.name for t in out.trace] == ["check_return_window", "consult_policies"]
    assert out.trace[1].result["sections"]


def test_tool_loop_is_bounded(toolbox):
    looping = [reply(calls=[tool_call("get_store_info", {}, f"c{i}")]) for i in range(10)]
    agent = make_agent(looping, toolbox)
    out = agent.respond("oi")
    assert len(out.trace) == agent.settings.max_tool_steps
    assert "Me enrolei" in out.text


def test_empty_answer_after_tools_is_retried_once(toolbox):
    agent = make_agent([reply(calls=[tool_call("get_store_info", {})]), reply(""), reply("Abrimos às 9h!")], toolbox)
    assert agent.respond("que horas abre?").text == "Abrimos às 9h!"


def test_provider_error_gives_friendly_message_and_keeps_history_clean(toolbox):
    class Boom(FakeClient):
        def _create(self, **kw):
            raise RuntimeError("503")

    agent = EmporioAgent(settings=Settings(api_key="x"), toolbox=toolbox, client=Boom([]))
    out = agent.respond("oi")
    assert "instabilidade" in out.text and agent.history == []


def test_missing_api_key_is_a_config_error(toolbox):
    agent = EmporioAgent(settings=Settings(api_key=""), toolbox=toolbox)
    with pytest.raises(ConfigError):
        agent.respond("oi")


def test_history_window_and_persistence(toolbox, tmp_path):
    agent = make_agent([reply(f"r{i}") for i in range(30)], toolbox)
    agent.settings.history_window = 6
    for i in range(10):
        agent.respond(f"m{i}")
    assert len(agent.history) == 6 and agent.history[-1]["content"] == "r9"

    store = SessionStore("teste-1", base=tmp_path)
    store.save(agent.history)
    assert store.load() == agent.history
    store.clear()
    assert store.load() == []


def test_session_id_is_validated(tmp_path):
    with pytest.raises(ValueError):
        SessionStore("../../etc/passwd", base=tmp_path)


def test_long_input_is_truncated(toolbox):
    agent = make_agent([reply("ok")], toolbox)
    agent.respond("a" * 10_000)
    assert len(agent.client.seen[0][-1]["content"]) == agent.settings.max_user_chars
