# Devolução por arrependimento (política + dados do pedido)

> ⚠️ **Transcrição ilustrativa (rascunho).** As chamadas de ferramenta e os resultados (linhas `🔧`) são **reais**: foram produzidos pelo código deste repositório com o relógio fixado. As falas do atendente foram **escritas à mão** seguindo o comportamento esperado, pois esta versão foi montada sem acesso a um LLM. Para substituir por conversas geradas pelo modelo configurado, rode `python scripts/record_examples.py`.

- **Relógio fixado:** 2026-02-20T15:00 (fuso de Campo Grande)
- **Demonstra:** `check_return_window` + `consult_policies`, prazos contados do recebimento, não prometer aprovação, escalonamento

---

**Cliente:** Me arrependi da minha compra, posso devolver meu pedido?

**Atendente:** Poxa, sem problema — na compra online você tem direito de se arrepender. Pra eu ver como está o seu prazo, me passa o *número do pedido* e o *e-mail ou telefone* da compra?

---

**Cliente:** Pedido 7, meu e-mail é leticia.rocha@jmail.com

> 🔧 `check_return_window(contact='leticia.rocha@jmail.com', order_id=7)` → entregue (data usada: 2026-02-17, estimada); arrependimento até **2026-02-24** (4 dias), troca por defeito até 2026-03-05, garantia legal até 2026-05-18
> 🔧 `consult_policies(topic='trocas_devolucoes')` → seções do manual: ['4', '4.1', '4.2', '4.3', '4.4']

**Atendente:** Oi, Letícia! Olhei aqui: seu pedido 7 (*Ukulele Shelby SU-21S Soprano*) consta como entregue em 17/02 — essa é a data prevista, a de recebimento real eu não tenho no sistema. Se for essa mesma, você está *dentro do prazo*: o direito de arrependimento vai até *24/02* (7 dias corridos).

As condições:
• produto na embalagem original, sem sinais de uso, com acessórios e manuais
• o frete da devolução é por nossa conta
• reembolso na mesma forma de pagamento (seu cartão), em até 10 dias úteis

A aprovação final depende da conferência do produto pela equipe. Quer que eu já abra a solicitação?

---

**Cliente:** Quero sim, pode abrir

> 🔧 `escalate_to_human(category='devolucao_ou_cancelamento', summary='Pedido 7 (Shelby SU-21S, R$ 159,90, crédito 3x): cliente pede devolução por arrependimento, dentro dos 7 dias (até 24/02, recebimento estimado 17/02).', contact='leticia.rocha@jmail.com')` → ticket `EM-20260220-…`, retorno em até 24 horas úteis

**Atendente:** Pronto, solicitação registrada! Nossa equipe te chama em até *24 horas úteis* com as instruções de envio. Enquanto isso, é só deixar o ukulele bem guardado na embalagem original, com tudo que veio junto. 🎶

---
