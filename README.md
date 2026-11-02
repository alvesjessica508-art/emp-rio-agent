# 🎸 Empório da Música — Agente de Atendimento

Protótipo (Python) de um agente de atendimento por mensagens de texto para a **Empório da Música**, loja fictícia de instrumentos musicais de Campo Grande/MS. Desafio técnico AI Engineer — Artefact.

O agente assume a persona da loja (informal, acolhedor, "amigo que entende de música"), responde sobre **catálogo, preço, promoções e estoque**, **status de pedidos**, **políticas** (trocas, devolução, garantia, frete, pagamento…), **informações da loja**, e recusa com simpatia o que foge do escopo.

---

## Sumário
1. [Como rodar](#como-rodar)
2. [Arquitetura](#arquitetura)
3. [Decisões técnicas e justificativas](#decisões-técnicas-e-justificativas)
4. [Dados vs. políticas: como o agente decide](#dados-vs-políticas-como-o-agente-decide)
5. [Suposições adotadas](#suposições-adotadas)
6. [Problemas encontrados nos dados](#problemas-encontrados-nos-dados)
7. [Testes](#testes)
8. [Exemplos de interação](#exemplos-de-interação)
9. [Limitações conhecidas](#limitações-conhecidas)
10. [O que eu faria com mais tempo](#o-que-eu-faria-com-mais-tempo)
11. [Uso de assistentes de código](#uso-de-assistentes-de-código)

---

## Como rodar

Requisitos: **Python 3.10+** e uma chave de API de qualquer provedor com API compatível com OpenAI (Gemini, OpenAI, Groq…) — ou um modelo local via Ollama (sem chave).

```bash
git clone <URL-DO-REPOSITÓRIO> && cd emporio-agent
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # edite e preencha LLM_API_KEY
python main.py              # abre o chat no terminal
```

Comandos dentro do chat: `/debug` (mostra cada ferramenta chamada e o resultado), `/novo` (reinicia), `/sair`.
Opções: `python main.py --session minha-conversa` retoma/continua uma conversa salva; `--debug` já inicia mostrando as ferramentas.

### Provedor do modelo (`.env`)
| Variável | Padrão | Descrição |
|---|---|---|
| `LLM_API_KEY` | — | chave do provedor |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | endpoint compatível com OpenAI |
| `LLM_MODEL` | `gemini-2.5-flash` | nome do modelo (**confira o nome vigente no seu provedor**) |
| `AGENT_NOW` | relógio real | fixa "agora" (ex.: `2026-03-25T10:30`) para demos reproduzíveis |

O `.env.example` traz receitas prontas para OpenAI, Groq e Ollama (local).

### Outros comandos
```bash
python -m pytest -q                      # 49 testes, sem rede e sem chave
python scripts/record_examples.py        # regrava examples/*.md usando o seu LLM
python scripts/record_examples.py 04     # só o cenário 04
```

### Estrutura
```
data/                     CSVs + manual de políticas (PDF)
src/emporio_agent/
  config.py               configuração, provedor, relógio da loja
  text.py                 normalização de texto, stemming leve, formatação em R$
  data_store.py           carga + limpeza dos CSVs; busca de produtos; verificação de cliente
  business.py             regras do manual em código: parcelas, PIX, prazos, horário
  policies.py             parsing do PDF em seções + recuperação (tópico / BM25)
  tools.py                7 ferramentas (schemas + execução)
  prompts.py              persona, regras, escopo
  agent.py                loop de function calling
  memory.py               histórico de conversa persistido
  cli.py                  interface de terminal
tests/                    pytest (dados, ferramentas, políticas, loop do agente)
examples/                 5 conversas de exemplo
scripts/record_examples.py
```

---

## Arquitetura

```
 cliente ──► CLI ──► EmporioAgent ──► LLM (function calling)
                        ▲   │             │ decide qual ferramenta chamar
                        │   │             ▼
              histórico │   └──────►  ToolBox ─┬─ search_products ────────┐
              (JSON/    │                      ├─ calculate_payment_options├─► DataStore (CSVs limpos)
               sessão)  │                      ├─ get_order_status ────────┤   + business.py (regras)
                        │                      ├─ check_return_window ─────┘
                        │                      ├─ consult_policies ───────► policies.py (PDF → seções)
                        │                      ├─ get_store_info
                        │                      └─ escalate_to_human ──────► var/escalations.jsonl
                        └────────────── resposta final (texto, estilo WhatsApp)
```

Cada turno: mensagem → LLM → (ferramentas → resultado JSON → LLM)\* → resposta. O loop tem limite de 6 passos, trata erro de ferramenta e de provedor sem derrubar a conversa.

---

## Decisões técnicas e justificativas

### 1. Abordagem: function calling nativo, com ferramentas "de negócio" (híbrido)
**Escolha:** um loop de *function calling* escrito à mão (~60 linhas) com 7 ferramentas específicas; dados estruturados via código determinístico e políticas via recuperação de seções.

**Por quê:**
- O problema tem dois tipos de conhecimento muito diferentes: **dados que mudam** (preço, estoque, promoção, pedido) e **texto de regras** (manual). Tratar os dois igual (ex.: "joga tudo em RAG" ou "LLM escreve SQL") erra o que importa — preço e prazo precisam estar *certos*.
- **Ferramentas de negócio em vez de agente de SQL:** o LLM não escreve consultas; passa parâmetros tipados (`category`, `max_price`…). Elimina SQL inválido/perigoso, e embute regras que o modelo erraria ou esqueceria: promoção só se `is_active`, PIX 5% não vale em preço promocional, parcela mínima, produto esgotado/descontinuado/"em breve", verificação de identidade (LGPD).
- **Contas e datas em código, não no LLM:** parcelamento, desconto, e prazos de devolução (7/30/90 dias, cada um contado de um marco diferente) são calculados em `business.py` e testados.
- **Sem LangChain/LlamaIndex:** com 7 ferramentas e sem grafo de estados, um framework só adicionaria abstração e dependências. O loop explícito deixa limites, logs e erros visíveis e é fácil de explicar/depurar. (Se o fluxo crescesse — multi-agente, aprovações humanas, filas — eu reavaliaria LangGraph.)
- **Alternativas consideradas:** *ReAct em texto* (menos robusto que tool calling nativo e mais caro em tokens); *RAG vetorial sobre tudo* (ótimo para texto longo, ruim para preço/estoque); *prompt gigante com tudo* (os 65 produtos cabem, mas ficaria desatualizado, caro e sem controle de acesso aos pedidos).

### 2. Modelo e provedor
**Escolha:** cliente OpenAI-compatível com `base_url`/`model` por variável de ambiente. Padrão: **Gemini 2.5 Flash** pelo endpoint de compatibilidade.

**Por quê:** o requisito é suporte a *function calling* + português + baixa latência/custo — um modelo "flash/mini" basta, pois a inteligência "difícil" (regras e contas) está no código. O formato OpenAI é o denominador comum (OpenAI, Gemini, Groq, OpenRouter, Ollama, vLLM), então **trocar de provedor é editar o `.env`**, sem mexer em código. Gemini tem camada gratuita, o que reduz a barreira para quem for rodar o projeto; Ollama cobre o cenário 100% local.
*Nota honesta:* o código foi testado com um LLM falso (testes automatizados) — a qualidade fim a fim varia com o modelo escolhido; modelos locais pequenos tendem a errar mais a escolha de ferramentas.

### 3. Recuperação de políticas (o "RAG" do projeto)
**Escolha:** o PDF é lido com `pypdf` (modo *layout*, que preserva as tabelas) e dividido **por seção/subseção do próprio manual** (25 chunks). A ferramenta `consult_policies` aceita um `topic` enumerado (pagamento, trocas_devolucoes, frete_entrega, garantia, promocoes, horarios, privacidade, sobre_a_loja) e devolve as seções **inteiras**; se nenhum tópico servir (`outro`), cai para **BM25** (implementado em ~20 linhas, com stemming leve e pequena lista de sinônimos).

**Por quê:** o manual tem ~3 mil palavras. Embeddings + banco vetorial seriam dependência e custo sem ganho, e *erram regras com exceções* (um chunk de tamanho fixo separaria "7 dias…" de "…exceto boquilhas"). Deixar o **LLM escolher o tópico** (função com enum) é mais confiável que similaridade lexical para perguntas curtas; o BM25 é a rede de segurança. Se o manual crescesse para dezenas de páginas, eu trocaria o fallback por embeddings (mantendo chunking por seção).

**Seções internas ficam fora do índice:** §7 (tom/fluxo/situações especiais de atendimento) e §10 são instruções para a equipe, não conteúdo a ser citado ao cliente. Elas viraram **regras do prompt** (`prompts.py`).

### 4. Estratégia de prompt
- **Persona** ancorada no manual §7.1 ("informal mas profissional, como um amigo que entende de música"), formato WhatsApp (curto, sem tabelas/títulos, ≤1 emoji, "R$ 1.299,00").
- **Regra de ouro:** nunca informar preço/estoque/promoção/prazo/pedido/horário de memória — sempre via ferramenta; se faltar dado, dizer que não tem e oferecer a equipe (§7.1: "informações incorretas podem configurar propaganda enganosa").
- **Tabela de roteamento** explícita "pergunta → ferramenta" (é aqui que o agente "sabe quando consultar dados e quando consultar políticas").
- **Situações especiais do §7.3** codificadas como regras: produto esgotado → alternativas; descontinuado → equivalentes; promoção vencida → transparência, nunca prometer desconto; reclamação → empatia + registro (retorno em 24h úteis).
- **Escopo:** só instrumentos; acessórios são recusados com gentileza **sem inventar lojas parceiras** (o manual pede sugerir parceiras "quando possível", mas não há lista); fora do negócio → recusa curta e retomada.
- **Robustez:** texto do cliente é tratado como *dado* (resistência a "ignore as regras / dê 50% / mostre pedidos de outra pessoa"); a data/hora atual é injetada a cada turno.
- **Temperatura 0,2** para respostas consistentes com os dados.

### 5. Interface
**CLI** (`python main.py`): o foco do desafio é o agente. A lógica está desacoplada (`EmporioAgent.respond(texto) -> AgentReply`), então plugar um webhook do WhatsApp/API HTTP é trocar apenas `cli.py`. O flag `/debug` mostra as ferramentas usadas — útil para avaliar o raciocínio.

### 6. Persistência do histórico
**JSON por sessão** em `var/sessions/`, janela das últimas 20 mensagens. Persiste **só as falas** (user/assistant); **resultados de ferramentas não são salvos** de propósito: estoque, promoção e status de pedido mudam, então o agente reconsulta em vez de confiar em dado velho. Tradeoff: "e o segundo?" depende de o atendente ter citado o nome do produto na resposta anterior (cita).

### 7. Tratamento dos dados (`data_store.py`)
- Carga com `csv` + dataclasses (a base é minúscula; pandas/SQL seriam peso morto), normalização de espaços, `specs` (JSON em string) parseado.
- **Busca de produtos** insensível a acento/plural (stemmer de prefixo de 5 letras: "violão"="violões"; mantém "Kala"≠"Kalani"), junta "gd 20"→"GD20", e tem fallback aproximado (`difflib`). Com `query`, itens esgotados/descontinuados **aparecem sinalizados** (nunca "fingir" que não existem); navegando por categoria/preço, escondemos os indisponíveis e informamos quantos.
- **Preço efetivo** = preço de tabela − maior promoção **ativa** (`is_active=1`; não cumulativas, §6.2). Promoções encerradas só alimentam o aviso "essa promoção acabou".
- **Descrições inconsistentes são suprimidas** (ver [problemas nos dados](#problemas-encontrados-nos-dados)); nome, preço e specs são a fonte de verdade.
- **Privacidade (LGPD, §9):** pedidos só são abertos mediante **e-mail ou telefone do cadastro**; falha devolve mensagem genérica (não revela se o pedido/contato existe); o agente nunca vê PII além do primeiro nome. Um e-mail compartilhado por dois cadastros só é aceito junto do nº de um pedido que pertença a um deles.

---

## Dados vs. políticas: como o agente decide

| Pergunta do cliente | Ferramenta | Fonte |
|---|---|---|
| "Quanto custa o Takamine GD20?" · "violões até R$ 1000" · "tem promoção?" | `search_products` | CSV (produtos/promoções/estoque) |
| "Parcela em quanto?" · "quanto fica no PIX?" | `calculate_payment_options` | regras §3 em código |
| "Cadê meu pedido?" | `get_order_status` (exige e-mail/telefone) | CSV (pedidos/clientes) |
| "Me arrependi, posso devolver?" | `check_return_window` **+** `consult_policies("trocas_devolucoes")` | CSV (datas) **+** manual §4 |
| "Como funciona a garantia/frete/troca?" | `consult_policies` | manual |
| "Onde fica? Estão abertos?" | `get_store_info` | manual §1–2 + relógio |
| Reclamação, defeito, caso sem solução | `escalate_to_human` | — |
| Cordas, receita de bolo, poema… | nenhuma — recusa e redireciona | prompt |

---

## Suposições adotadas
O enunciado pede para assumir interpretações razoáveis e documentá-las:

1. **Contradições do manual.**
   - *Telefone/WhatsApp:* §1.2 diz (67) 3341-4444; §7 diz (67) 3321-4500. Usei o da tabela oficial de dados da empresa (§1.2).
   - *E-mail:* a tabela §1.2 traz `contato@empóriodamusica…` (com acento, inválido); usei `contato@emporiodamusica.com.br` (capa do manual).
   - *Parcela mínima:* a tabela §3 diz "R$ 100" para qualquer cartão; a §3.1 detalha faixas (até 3x: sem mínimo exceto parcela < R$ 50; 4–6x: R$ 80; 7–12x: R$ 100). Adotei a **§3.1** (regra detalhada) e li "exceto abaixo de R$ 50" como parcela mínima de R$ 50 nas faixas 2–3x.
2. **Significado dos status de pedido** não está definido no manual. Assumi: `pending` = recebido/aguardando confirmação; `confirmed` = confirmado/em preparação (sem rastreio); `shipped` = despachado; `delivered`; `cancelled`.
3. **Data de recebimento** não existe nos CSVs. Uso `estimated_delivery` como proxy para contar os 7 dias de arrependimento e os 90 de garantia legal (e o agente avisa que é estimada). A troca por defeito (30 dias) conta da **data da compra**, como diz o §4.2.
4. **Canal de compra:** o direito de arrependimento (§4.1) é para compras *online*; assumi que os pedidos do CSV são online (têm rastreio/transportadora).
5. **"Região metropolitana de Campo Grande"** não é definida (nem há CEP nos dados), então **não calculo frete**: o agente cita as regras do manual (grátis > R$ 500, taxa R$ 35, prazos PAC/SEDEX/Jadlog) e encaminha cotações especiais (ex.: baterias) à equipe.
6. **Promoções:** só `is_active = 1` vale; havendo mais de uma ativa no mesmo produto, vale a de maior desconto (não cumulativas). Nenhuma promoção ativa recai sobre produto indisponível nos dados atuais.
7. **Relógio:** os CSVs são um "instantâneo" de ~março/2026. Em uso real o agente usa a data atual (fuso `America/Campo_Grande`); para demos coerentes com os dados, `AGENT_NOW` fixa a data. Consequência: com a data real, pedidos "enviados" com previsão antiga aparecem como atrasados (comportamento desejado: pedir desculpas e escalar).
8. **Feriados** não são considerados no "aberto agora?" (o agente avisa).
9. **Catálogo parcial:** a loja diz ter 300+ itens e vender sopros e cordas orquestrais, mas os CSVs têm 65 produtos e as categorias de sopro/cordas estão vazias. Quando a busca volta vazia, o agente diz "não encontrei no sistema" e oferece a equipe — **não afirma que a loja não vende**.

---

## Problemas encontrados nos dados
Tratados ou sinalizados no código (e cobertos por testes quando possível):

| Problema | Tratamento |
|---|---|
| **Descrições trocadas** em baixos, baterias e teclados (ex.: "Music Man Bass 1X" descrito como Fender Jazz Bass; "Bateria Yamaha Kit 1" como Pearl Export; "Teclado Korg" como Roland 88 teclas, specs dizem 61; baixo "5 cordas" com spec "4") — 7 produtos | detectado por heurística de marca/modelo (`description_is_reliable`); a descrição é **omitida** e o agente descreve só com nome, preço e specs |
| E-mail **duplicado** em 2 clientes (`bruno.martins@jmail.com`, IDs 11 e 43) | exige nº do pedido para desambiguar; nunca expõe dados de um cadastro por engano |
| `total_brl` ≠ soma dos itens nos pedidos 3 (R$ 3.498 vs 3.450) e 20 (R$ 1.488 vs 1.400) | usa-se o `total_brl` do pedido (pode refletir desconto/frete); fica como pendência a confirmar com a loja |
| Produto `coming_soon` (id 130) aparece em pedido já **entregue** (pedido 3) e há estoque 2 | tratado como "em breve — não disponível para compra" no catálogo |
| Produto `discontinued` com estoque > 0 (id 136, estoque 13) | `status` prevalece: indisponível |
| IDs fora de ordem / nomes com typo ("Cedr") | mantidos como estão (nome é identificador para o cliente) |
| Categorias de sopro e cordas orquestrais sem produtos | ver suposição 9 |
| Promoções com `is_active = 0` em quase tudo (21 de 25) e produto com 2 promoções antigas (id 96, 18% e 40%) | só ativas valem; encerradas só servem para explicar "essa acabou" |

---

## Testes
`python -m pytest -q` → **49 testes**, sem rede nem chave. Cobrem: busca e filtros do catálogo, promoção ativa × encerrada, PIX × preço promocional, parcelamento, verificação de identidade (inclusive e-mail duplicado e mensagem genérica em falha), prazos de devolução em diferentes datas, horário de funcionamento, parsing do PDF e recuperação, e o loop do agente com um **LLM falso** (ida e volta de ferramenta, limite de passos, erro de provedor, janela de histórico, truncamento de entrada).

O que os testes **não** cobrem é a *qualidade das respostas do modelo real* (escolha de ferramenta, tom). Para isso, ver "O que eu faria com mais tempo".

---

## Exemplos de interação
Em [`examples/`](examples/) há 5 conversas cobrindo: (1) catálogo com filtros, (2) preço + promoção ativa/encerrada + esgotado, (3) status de pedido com verificação e atraso, (4) devolução por arrependimento aplicando política e prazos, (5) endereço/horário + acessório + pedido fora de escopo. Os cenários 2–4 são "não triviais" (dados em tempo real + regras do manual).

> **Nota:** as transcrições versionadas são **ilustrativas** (rotuladas no topo de cada arquivo): as chamadas de ferramenta/resultados são reais, mas as falas foram redigidas à mão. Rode `python scripts/record_examples.py` com o seu `.env` para gerá-las com o modelo configurado.

---

## Limitações conhecidas
- **Sem avaliação automatizada do LLM** (só testes determinísticos); o prompt foi desenhado, não otimizado empiricamente.
- **Autenticação fraca por design de protótipo:** e-mail/telefone como "segredo" não é forte; em produção usaria o número do WhatsApp remetente (já autenticado pelo canal) + OTP, e *rate limit* contra enumeração.
- **Chamados de escalonamento** vão para um arquivo local (`var/escalations.jsonl`), sem integração com CRM/helpdesk, e o retorno de "24h úteis" é só informado.
- **Sem cálculo de frete** (sem CEP) e **sem criação/alteração/cancelamento de pedido**: o agente é consultivo.
- **Catálogo e estoque lidos de CSV** no início do processo (não há "tempo real" de verdade; em produção seria banco/API).
- **Idioma:** otimizado para pt-BR. **Um cliente por processo** (CLI): sem concorrência.
- **Prefixo de 5 letras** como stemmer é grosseiro (pode casar termos distintos em catálogos maiores).
- **Dados do cliente:** o agente não sabe quem é o interlocutor até ele se identificar.

## O que eu faria com mais tempo
1. **Suíte de avaliação (evals)** com ~50 conversas anotadas (acerto de ferramenta, ausência de alucinação de preço/promoção, recusas corretas) rodando em CI contra 2–3 modelos, para escolher modelo/prompt com dados.
2. **Interface WhatsApp** (webhook Cloud API/Twilio) usando o telefone do remetente como identidade; histórico em SQLite/Redis; *handoff* humano de verdade (CRM/helpdesk) com contexto.
3. **Streaming + guardrails de saída:** validar que todo valor em R$ citado na resposta aparece nos resultados das ferramentas (detector de alucinação numérica).
4. **Recomendação melhor:** perguntas de qualificação (nível, estilo, orçamento) e comparação lado a lado de produtos.
5. **Dados:** corrigir o cadastro na origem (descrições trocadas, totais divergentes), carregar o catálogo completo, adicionar data real de entrega e transportadora ao pedido.
6. **Embeddings** para o fallback de políticas se o manual crescer; versionamento do manual.
7. **Observabilidade:** *tracing* (ex.: Langfuse/OpenTelemetry) de ferramentas, latência e custo por conversa.
8. **Frete por CEP** (API dos Correios/Jadlog) e **cálculo de múltiplos itens** no carrinho.

---

## Uso de assistentes de código
<!-- ATENÇÃO: rascunho. Ajuste para refletir fielmente o SEU fluxo antes de enviar. -->
Ferramenta utilizada: **Claude (Anthropic)**, em modo agêntico (leitura dos arquivos, execução de código e testes no ambiente).

- **Entendimento dos dados:** o assistente inspecionou os CSVs e o PDF; daí saíram os achados da seção de problemas nos dados (descrições trocadas, e-mail duplicado, totais divergentes), verificados rodando consultas sobre os arquivos.
- **Design:** foram comparadas alternativas (agente de SQL, function calling, RAG vetorial) e escolhido function calling com ferramentas de negócio.
- **Implementação e testes:** o assistente escreveu os módulos e os testes em pytest; falhas apontadas pelos próprios testes (parsing do PDF, busca "kala" × "kalani", sinônimos no BM25) foram corrigidas em seguida.
- **Documentação:** este README foi redigido com o assistente.
- **Limite importante:** o ambiente de desenvolvimento não tinha chave de LLM, então as falas do atendente em `examples/` foram escritas à mão (sinalizado no topo de cada arquivo) e o fluxo com um modelo real não foi exercitado. Rode `python scripts/record_examples.py` para gerar as conversas com o modelo configurado.
