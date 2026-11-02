# Preço, promoção ativa, promoção encerrada e produto esgotado

> ⚠️ **Transcrição ilustrativa (rascunho).** As chamadas de ferramenta e os resultados (linhas `🔧`) são **reais**: foram produzidos pelo código deste repositório com o relógio fixado. As falas do atendente foram **escritas à mão** seguindo o comportamento esperado, pois esta versão foi montada sem acesso a um LLM. Para substituir por conversas geradas pelo modelo configurado, rode `python scripts/record_examples.py`.

- **Relógio fixado:** 2026-03-25T10:30 (fuso de Campo Grande)
- **Demonstra:** regras de promoção (sem PIX em preço promocional, preço original + %), promoção vencida, alternativas para esgotado

---

**Cliente:** Quanto custa o Takamine GD20?

> 🔧 `search_products(query='Takamine GD20')` → 1 resultado(s), 0 indisponível(is) oculto(s): Takamine GD20 Dreadnought Natural (R$ 2199.00)

**Atendente:** O *Takamine GD20 Dreadnought Natural* está R$ 2.199,00 e temos em estoque. É um violão de tampo sólido em cedro, ótimo pra fingerstyle, com timbre quente e definido. No PIX fica *R$ 2.089,05*.

---

**Cliente:** Dá pra parcelar em quanto?

> 🔧 `calculate_payment_options(product_id=95)` → total 2199.00 · cartão em até 12x de R$ 183,25 · pix 2089.05

**Atendente:** Dá sim: em até *12x de R$ 183,25 sem juros* no cartão. Se preferir pagar à vista, o PIX com 5% de desconto sai por R$ 2.089,05.

---

**Cliente:** E o Crafter HT-100? Ouvi que tá em promoção

> 🔧 `search_products(query='Crafter HT-100')` → 1 resultado(s): Crafter HT-100 Folk Aço Natural (R$ 1967.18, promoção "Desconto Exclusivo" 18%, restam 3 unidades)
> 🔧 `calculate_payment_options(product_id=90)` → total 1967.18 · pix 1967.18 (sem desconto: preço já promocional) · cartão em até 12x de R$ 163,93

**Atendente:** Ouviu certo! O *Crafter HT-100* (folk, tampo sólido de Spruce Engelmann) está com *18% de desconto*: de R$ 2.399,00 por *R$ 1.967,18*. Restam só 3 unidades.

Como o preço já é promocional, o desconto de 5% do PIX não se soma. Dá pra parcelar em até 12x de R$ 163,93 sem juros.

---

**Cliente:** O Giannini GF-3D tava com 40% na Semana do Músico, ainda tá valendo?

> 🔧 `search_products(query='Giannini GF-3D')` → Giannini GF-3D Dreadnought Sunburst (R$ 799.90) · availability=**esgotado** · expired_promotion="Semana do Músico (40%) — ENCERRADA"
> 🔧 `search_products(query='dreadnought', string_type='aço', max_price=1000)` → 3 resultado(s): Giannini GF-3D (esgotado), Tagima Woodstock Dreadnought Natural (R$ 899.00), Shelby SGD-195E Elétrico Aço Sunburst (R$ 799.00)

**Atendente:** Aquela promoção da Semana do Músico já acabou, e o *GF-3D* está esgotado no momento (preço de tabela: R$ 799,90). Não quero te prometer um desconto que não existe mais.

Dois dreadnoughts parecidos que tenho disponíveis:

• *Tagima Woodstock* (aço, som potente) — R$ 899,00
• *Shelby SGD-195E* (aço, eletroacústico com afinador) — R$ 799,00

Quer detalhes de algum deles?

---
