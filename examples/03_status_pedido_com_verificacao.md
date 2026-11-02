# Status de pedido com verificação de identidade e atraso

> ⚠️ **Transcrição ilustrativa (rascunho).** As chamadas de ferramenta e os resultados (linhas `🔧`) são **reais**: foram produzidos pelo código deste repositório com o relógio fixado. As falas do atendente foram **escritas à mão** seguindo o comportamento esperado, pois esta versão foi montada sem acesso a um LLM. Para substituir por conversas geradas pelo modelo configurado, rode `python scripts/record_examples.py`.

- **Relógio fixado:** 2026-03-25T14:00 (fuso de Campo Grande)
- **Demonstra:** verificação por e-mail/telefone (LGPD), resposta genérica em falha, previsão vencida, escalonamento

---

**Cliente:** Cadê meu pedido 8? Já faz tempo que comprei

**Atendente:** Oi! Vou olhar isso pra você. Só preciso confirmar que o pedido é seu: me passa o *e-mail ou o telefone* que você usou na compra?

---

**Cliente:** Meu email é ana.ferreira@coldmail.com

> 🔧 `get_order_status(contact='ana.ferreira@coldmail.com', order_id=8)` → **NÃO verificado** (dados não revelados)

**Atendente:** Hum, não consegui confirmar com esse dado. Pode conferir o e-mail (ou me mandar o telefone com DDD) que você usou na compra? Por segurança eu só consigo abrir o pedido quando bate com o cadastro.

---

**Cliente:** Ih, errei. É anacarol.ferreira@coldmail.com

> 🔧 `get_order_status(contact='anacarol.ferreira@coldmail.com', order_id=8)` → verificado; pedido 8 = `shipped`, rastreio BRJL5544332BR, previsão 2026-02-28 (**já passou**)
> 🔧 `escalate_to_human(category='reclamacao', summary='Pedido 8 (Kala KA-C Concert Mogno) despachado, previsão de 28/02 vencida; cliente quer posição.', contact='anacarol.ferreira@coldmail.com')` → ticket `EM-20260325-21C8`, retorno em até 24 horas úteis

**Atendente:** Pronto, Ana, achei! Seu pedido 8 (*Kala KA-C Concert Mogno*, R$ 349,90) foi despachado e o código de rastreio é *BRJL5544332BR* — dá pra acompanhar no site dos Correios ou da Jadlog.

Mas a previsão de entrega era 28/02 e já passou, então te devo desculpas por isso. Já abri um chamado (*EM-20260325-21C8*) pra nossa equipe verificar com a transportadora, e eles retornam em até 24 horas úteis.

Posso ajudar em mais alguma coisa?

---
