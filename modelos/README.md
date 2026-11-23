# Biblioteca de modelos de edição

Um **tipo** é uma técnica de edição com nome (whip pan, speed ramp, zoom punch…). Um **estilo** é
uma combinação de tipos com regras (uma transição primária, no máximo 3 acentos) e "sinais" sem
os quais deixa de ser aquele estilo. Cada modelo tem uma ficha (`MODELO.md`), uma receita
(`modelo.json`) que `helpers/modelos.py apply` escreve no projeto, e uma demo renderizada na
galeria (fora do git). Desenho: `docs/superpowers/specs/2026-11-22-biblioteca-modelos-design.md`.

## Usar

```
uv run python helpers/modelos.py list                     # ✅ = tem demo na galeria · 🧪 = sem demo
uv run python helpers/modelos.py show whip-pan
uv run python helpers/modelos.py apply whip-pan plan.json --plano 2 --param dir=right
uv run python helpers/modelos.py apply reel-fala-broll <videos>/edit
uv run python helpers/modelos.py galeria --abrir
```

## Acrescentar um modelo

1. Crie `modelos/tipos/<slug>/` (ou `estilos/<slug>/`) com `modelo.json` e `MODELO.md`. A ficha precisa
   das seções `## O que é`, `## Quando usar`, `## Quando não usar`, `## Contenção`.
2. `modelo.json`: `slug` igual ao nome da pasta, `nivel` (`tipo`/`estilo`), `familia`, `host`
   (`montagem` = plano do `beat_edit`; `reel-fala` = `state.json` style + `edit-data.json`; `cena` = cena
   HyperFrames inteira montada por dados em `helpers/cenas.py`, ex.: `card-ficha`), `acento` (conta para
   o limite de 3) e a receita (`aplica` para montagem; `style` + `edit_data` para Reel de fala; `tipos` +
   `regras` + `sinais` para estilo).
3. `modelos.py check` (também roda no `tests/test_catalog.py`) recusa nome de transição, rampa, efeito ou
   elemento que não existe.
4. `modelos.py demo <slug>` renderiza a demo; ela só entra na galeria se passar G0/G2 do `motion_gates`.

## Fila (spec §6)

Feitos em 2026-11-22: L-cut alternado com J (`l-cut`, host `corte`), freeze frame (`freeze-frame`). Faltam: smash cut (precisa de corte da música antes do impacto no `beat_edit`), mask transition / passar pelo objeto, morph, recorte
congelado com contorno, cross-cut, legenda que segue a boca, peças de interface (HUD de filmadora, chat
digitando, cursor no CTA, barra de progresso, leque, carimbo), ampliar a entrada por frase do título misto a outras cenas HyperFrames e o
estilo VSL com interface animada (recriado do zero; o skill-reel não tem licença).
