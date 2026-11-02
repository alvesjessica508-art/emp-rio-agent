# Consulta ao catálogo com filtros

> ⚠️ **Transcrição ilustrativa (rascunho).** As chamadas de ferramenta e os resultados (linhas `🔧`) são **reais**: foram produzidos pelo código deste repositório com o relógio fixado. As falas do atendente foram **escritas à mão** seguindo o comportamento esperado, pois esta versão foi montada sem acesso a um LLM. Para substituir por conversas geradas pelo modelo configurado, rode `python scripts/record_examples.py`.

- **Relógio fixado:** 2026-03-25T10:30 (fuso de Campo Grande)
- **Demonstra:** `search_products` com categoria + faixa de preço; recomendação; PIX/parcelamento calculados em código

---

**Cliente:** Oi! Quais opções de violões disponíveis custando até R$1000?

> 🔧 `search_products(category='Violões', max_price=1000, limit=6)` → 12 resultado(s), 2 indisponível(is) oculto(s): Tagima Memphis AC-39 Nylon Natural (R$ 429,90), Rozini RC-104 Nylon Estudante (R$ 459,90), Shelby SN-100 Folk Aço Preto (R$ 549,00), Giannini GF-1R Aço Folk Sunburst (R$ 579,90), Yamaha C40 Nylon Natural (R$ 599,90)

**Atendente:** Oi! Tenho 12 violões disponíveis até R$ 1.000. Os mais em conta:

• *Tagima Memphis AC-39* (nylon) — R$ 429,90
• *Rozini RC-104* (nylon, estudante) — R$ 459,90
• *Shelby SN-100* (folk, aço, preto) — R$ 549,00
• *Giannini GF-1R* (folk, aço, sunburst) — R$ 579,90
• *Yamaha C40* (nylon) — R$ 599,90

Quer que eu mostre os outros ou filtre por corda de nylon ou aço?

---

**Cliente:** Qual desses é melhor pra quem tá começando? E quanto fica o Yamaha F310 no PIX?

> 🔧 `search_products(query='Yamaha F310')` → 1 resultado(s), 0 indisponível(is) oculto(s): Yamaha F310 Aço Natural (R$ 699.90)
> 🔧 `calculate_payment_options(product_id=87)` → pix_brl 664.90 · cartão em até 6x de R$ 116,65 sem juros

**Atendente:** Pra começar, o *Tagima Memphis AC-39* é uma ótima pedida: nylon (mais macio pros dedos), corpo leve e é o mais em conta da lista. Se você quer o som brilhante de aço pra cantar e acompanhar, o *Yamaha F310* é um clássico de iniciante.

O F310 custa R$ 699,90 e no PIX sai por *R$ 664,90* (5% de desconto). No cartão dá pra parcelar em até 6x de R$ 116,65 sem juros.

Quer que eu veja outros no mesmo estilo?

---
