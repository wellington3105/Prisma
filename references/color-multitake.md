# Colour for multi-take edits in mixed / low light (`color_pipeline.py`)

Read this when an edit is built from many takes (montages, b-roll packs, phone
shoots in showrooms, interiors, night) — especially in LOW light. One look on
top of unmatched takes amplifies their differences; correct first, then look.

## Order (what the helper does per take)

1. **Denoise** — `hqdn3d`, strength from the measured noise; chroma 1.4× luma
   (low-light noise is mostly colour), temporal 1.6× spatial (moving grain is
   what reads as "cheap"). Denoise BEFORE any contrast or sharpening.
2. **White balance** — neutral pixels (saturation < 0.12, luma 70–235: floors,
   walls, ceilings, paper) pulled to grey with per-channel gains, strength 0.7
   (keeps some ambience). Gains clamped 0.8–1.25.
3. **Exposure** — one monotone pchip curve per take:
   black point → 0.02 · 20th percentile → max(original, ×1.10) (**shadow
   protection**) · median → toward the reference · white point → 0.94 with a
   soft shoulder (headlights, reflections roll off instead of clipping).
   **Asymmetric match**: dark takes move `--match` (0.6) of the way to the
   reference; bright takes only `--match × --darken-limit` (0.3). Never throw
   away exposure a low-light camera managed to capture.
4. **Look** — one shared creative chain for all takes. Keep CONTRAST OUT of the
   look (`eq=contrast` pivots on mid-grey and crushes the shadows the curve just
   protected); put colour (saturation, colorbalance split-tone) there.
5. **Clarity** — mid-radius `unsharp=7:7:0.35` after the denoise.

## Read the report, not just the picture

`graded/color_report.json` → `_summary`:
- `median_spread_before/after` — std of take medians (luma). It should drop;
  it will not reach 0 (interiors are darker than exteriors, as they should be).
- `shadow_p20_before/after` — must NOT fall. If it falls, something crushes
  the subject (a contrast in the look, a too-dark reference).
- `noise_before/after` — must fall.
`graded/before_after.jpg` — one frame per take, in over out. Check the subject
first (the car, the face), then the neutrals.

## Measured — Taycan 4S showroom, 20 phone takes (2026-10-06)

| pass | median spread | shadows p20 | what was wrong |
|---|---|---|---|
| look only (v1 "cine": contrast 1.14) | 19.9 (no change) | — | takes still unmatched |
| median-led curve + contrast look | 9.2 | 36.5 → 28.8 | dark-blue car crushed to near-black on a white floor |
| + shadow protection, asymmetric match, contrast out of look | 13.3 | 36.5 → 39.1 | ✓ car detail kept, neutrals neutral, headlights intact |

Reference choice: the hero take (the one the edit is built around). If the
hero is darker than most takes, the asymmetric match keeps the others from being
dragged down.

## Quando NÃO neutralizar o branco (medido — Volvo XC60, 2026-10-30)

O passo 2 (`balance`) puxa para cinza os pixels pouco saturados e claros. Num
showroom com **piso creme e paredes bege** esses pixels NÃO são neutros: o
pipeline esfriou a cena inteira (RGB 90/85/84 → 93/90/90, piso creme virou cinza
ciano), e o usuário reprovou ("a correção de cor dos takes não está legal"). No
mesmo passe o ponto de preto foi a 0,02 (p2 15 → 3–6, piso preto sem detalhe) e
a saturação subiu 30–45%.

- Cena com superfícies quentes de propósito (madeira, creme, bege, couro caramelo):
  `--wb-strength 0` — ou não use o pipeline: denoise leve +
  `eq=contrast=1.05:saturation=1.04:gamma=0.98` preservou a cor e foi aprovado.
- Para AQUECER, desloque os canais de cor em YUV: `lutyuv=u=val-1.5:v=val+1.5`
  (sutil) / `u=val-2:v=val+2` (o "um pouco mais quente" pedido no vídeo principal).
  `colorbalance` nesse caminho (via grade.py/render) saiu MAIS ESCURO E ESVERDEADO,
  ao contrário do pedido — converte para RGB com matriz/faixa trocada. Use lutyuv.
- Compare sempre original × corrigido no MESMO quadro antes de aplicar no lote.

