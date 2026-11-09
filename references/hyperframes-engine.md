# HyperFrames como motor da Fase 2 — referência + mudanças propostas ao SKILL.md

Plano aprovado: `output/2026-11-06/prisma-hyperframes-plano.md` (§7, decisões de 2026-11-08).
Este arquivo tem duas partes: **(A)** o texto que foi integrado ao `SKILL.md` em 2026-11-09 (Hard Rules 10, 11, 14; EDITOR; motor da Fase 2), mantido como registro; **(B)** a referência técnica do motor (o que foi medido, como as peças se ligam).

---

## A. Texto proposto para o SKILL.md

### Hard Rule 10 (reescrita)
> **Fase 2 é renderizada por motor: HyperFrames por padrão, Remotion como fallback
> automático do vídeo INTEIRO.** `render_phase2.py --engine auto` (padrão) usa o
> HyperFrames quando toda camada ligada no edit-data está `ported`; senão renderiza o
> vídeo inteiro no Remotion e diz qual chave causou (nunca híbrido). Nada de texto ou
> overlay queimado com ffmpeg/PIL. **O áudio final vem sempre do `deliver_mix`** — o
> áudio do motor (HyperFrames ou Remotion) nunca é entregue.

### Hard Rule 11 (reescrita)
> **Fase 2 é data-driven.** Descreva tudo em `remotion/public/edit-data.json` e gere com
> `build_hyperframes.py` (HF) — o mesmo arquivo alimenta o Remotion. Não edite saída
> gerada (`<edit>/hyperframes/index.html`, `compositions/*.html`) nem template
> (TSX, `assets/hyperframes/vendor/prisma-hf.js`). Cena sob medida: `<edit>/hyperframes/custom/`
> (HF, F2) ou `src/CustomGraphics.tsx` (fallback). A edição da PESSOA no Studio é
> protegida pelo fingerprint (`.prisma-export.json`): o builder recusa remontar por cima
> dela; uma correção estrutural do agente é um patch no `index.html` + `hyperframes check`.

### Hard Rule 14 (nova)
> **Versão do HyperFrames fixa por projeto** (`hfkit/project.py HF_PIN`, gravada no
> `package.json` do projeto por `hf_version.stamp`; o CLI global só é usado se for a
> versão pinada, senão `npx --yes hyperframes@<pin>`). **Uma camada só vai para o HF se
> estiver `ported` em `helpers/hfkit/layers/__init__.py` com o fixture de paridade
> verde** (`regress.py --phase2`, SSIM ≥ 0,95 na caixa, entrada/saída ±1 quadro);
> senão o vídeo inteiro vai para o Remotion e isso é dito ao usuário.

### Sequência da Fase 2 (substitui o passo "render" atual)
1. Gate de Estilo → `edit-data.json` (como hoje; `safe_layout`, `sfx_events`, `inserts_plan` iguais).
2. `uv run python helpers/render_phase2.py --edit <edit>` — escolhe o motor (`[motor] …` na
   primeira linha), roda `check_direction` / `safe_layout` / `check_media` antes de qualquer motor.
   - **HyperFrames:** `build_hyperframes.py` → `hyperframes check --json` (0 erros) →
     `hyperframes render --quality delivery` (`hyperframes/out/render.mp4`, áudio descartado) →
     `deliver_mix.py --picture … --tone-ref … --tone-times …` → `qa_mix.py`.
   - **Remotion (fallback):** como hoje (`remotion render` + entrega).
3. Conferir como sempre (contact sheet, `qa_mix`). `state.json` ganha `engine` e
   `engineFallback: [chaves]`.

### Seção EDITOR (trocar)
- Sai: "o vídeo final é o Export do Editor".
- Entra: "Na Fase 2 o EDITOR abre o projeto do `build_hyperframes` (mesma pasta
  `<edit>/hyperframes`). O Export do Studio é **prévia**. Entregar = `render_phase2`
  (render HF sem o áudio dele) + `deliver_mix` + `qa_mix`. Overlay editado no Studio
  (legenda movida, card aparado): `render_phase2 --engine hyperframes --no-rebuild`
  renderiza a versão do Studio. **Take editado no Studio** (aparado, dividido,
  apagado) muda o tempo da voz: `helpers/hf_pull_takes.py <edit>` grava
  `preview_edits.json` → `apply_preview_edits.py` → `refine_edges.py` → `render.py` →
  `verify_cut.py` → `build_hyperframes.py --force`. O `render_phase2` RECUSA entregar
  com take alterado sem esse pull (decisão 1)."
- Na Fase 1 nada muda: `export_hyperframes.py` (proxies da fonte, corte seco).

### Phase-2 checks (somar)
- `hyperframes check --json` com 0 erros (o `render_phase2` já bloqueia).
- Mudou uma camada portada ou o pin do HF: `uv run python helpers/regress.py --phase2`.
- Dúvida num vídeo real: `uv run python helpers/hf_parity.py <edit>` (precisa dos dois
  renders: `render_phase2 --engine remotion --skip-delivery` e `build_hyperframes --render`).

### Bloco "3D / WebGL"
- `--gl=angle` (Remotion) ↔ `--browser-gpu` (HyperFrames). As camadas 3D/WebGL ainda não
  estão portadas (F3) — com elas ligadas o vídeo vai inteiro para o Remotion.

### Frontmatter `description` e a linha da "Remotion-only Phase-2 rule"
- "…build Phase 2/3 visuals (HyperFrames by default, Remotion as automatic fallback) and audio."

---

## B. Referência técnica

### Peças
| Arquivo | Papel |
|---|---|
| `helpers/build_hyperframes.py` | edit-data → `<edit>/hyperframes/` (index + uma composição por item) + `render.json` |
| `helpers/hfkit/timebase.py` | quadros ↔ segundos de clip, regras medidas (abaixo) |
| `helpers/hfkit/project.py` | esqueleto, pin do CLI, fontes/GSAP/runtime locais, `sub()`/`host()`, fingerprint |
| `helpers/hfkit/measure.py` + `measure.mjs` | largura de texto no Chrome do HF (= `measureText` do Remotion) |
| `helpers/hfkit/layers/*.py` | uma camada por módulo; `LAYERS` (ported/gl) + `unported(ed)` |
| `assets/hyperframes/vendor/prisma-hf.js` | `interpolate`/`spring`/`Easing` do Remotion 4.0.482 portados 1:1 + o desenho de cada camada |
| `assets/hyperframes/vendor/gsap.min.js` | GSAP 3.14.2 local (traps §2) |
| `assets/hyperframes/fonts/` + `fonts.json` | Poppins = os MESMOS woff2 que o `@remotion/google-fonts` baixa (família CSS `PrismaPoppins`, para o Poppins embutido do HF nunca substituir) |
| `helpers/hf_parity.py` | HF × Remotion por camada: SSIM na caixa, δ de entrada/saída, tom, folha de contato |
| `helpers/hf_pull_takes.py` | takes cortados no Studio → `preview_edits.json`; `changed_takes()` para o guarda |
| `tests/fixture_phase2/make_fixture.py` + `regress.py --phase2` | fixture 9:16 + 16:9, uma camada por janela |

### Por que o desenho é JS portado e não tweens GSAP "equivalentes"
A camada só é `ported` com SSIM ≥ 0,95 contra o Remotion. Recriar cada curva como ease
do GSAP deriva (mola do Remotion ≠ `back.out`). Cada item é uma composição com um
tween num proxy cujo `onUpdate` desenha o quadro `f` com a matemática do template —
o padrão que o HyperFrames documenta para gráficos (`runtimes.md`): tudo é função do
tempo da timeline, o seek funciona, o Studio move/apara o clip. Limitação: aparar um
card no Studio não refaz a curva de saída (o `total` é do edit-data).

### Medições (HyperFrames 0.8.93 · Remotion 4.0.482, 2026-11-08/09)
- **Amostragem do HF:** o quadro k é desenhado em exatamente k/fps; um clip `[start, start+dur)`
  mostra exatamente os quadros esperados (sonda com 3 marcadores, um deles em 2/3 s).
- **O HF escolhe o quadro da mídia por FLOOR do tempo de mídia** contado do 1º quadro do clip:
  `data-media-start` um fio abaixo de k/fps mostra o quadro k−1 (todos os takes saíram 1
  quadro atrasados até isso). Por isso `data-start` leva 0,1 ms de folga para TRÁS
  (`timebase.t_at`) e `data-media-start` 0,1 ms para a FRENTE (`timebase.media_t`).
- **O Remotion 4.0.482 NÃO atrasa a imagem:** em todas as emendas fora de B-roll do CLA200
  (quadros 179, 204, 349, 542) a troca de imagem cai no MESMO quadro no cut.mp4 e no
  render do Remotion. O `VIDEO_LAG = 1` dos templates hoje só atrasa o degrau de zoom, a
  tela dividida e as janelas da legenda 1 quadro DEPOIS do corte — e isso é o que o
  Remotion desenha, então o porte reproduz (`timebase.TEMPLATE_LAG`). A base do HF é o
  cut.mp4 SEM deslocamento (`PICTURE_LAG = 0`).
- **Consequência para o áudio (defeito antigo, dos dois motores):** o `deliver_mix` atrasava
  a voz 1 quadro para um lag de imagem que não existe mais — sonda de A/V (quadrado nos
  onsets das palavras, `build_hyperframes --sync-probe` + `hf_parity --sync-final`): imagem
  0 ms, voz +36,2 ms. Correção opt-in: `deliver_mix --video-lag N` (padrão 1 = comportamento
  antigo, Remotion inalterado); o ramo HF passa o lag medido (0) → voz +3,0 ms (latência da
  cadeia de voz). **Decisão pendente:** passar `--video-lag 0` também no Remotion.
- **Offset de container:** o Remotion posiciona os quadros pelo pts absoluto; o HF conta do
  início do container. Um clipe só-vídeo cortado com `-ss` (start_time 0,033) sai 1 quadro
  atrasado no Remotion; o cut.mp4 (vídeo 0,033, áudio 0 → container 0) fica alinhado nos dois.
  `media.pts_lag()` compensa pelo `format=start_time` do arquivo.
- **CSS:** o Remotion injeta `* { box-sizing: border-box }` (default-css.js); sem isso a
  legenda com `padding-bottom` descia 10% da altura. O HF recebe a mesma regra.
- **Tom:** render do HF ≈ 0,995·base − 1,2 (sonda, sem zoom); contra o Remotion no CLA200
  0,9997·x − 0,95. O `render_phase2` monta `hyperframes/out/tone_ref.mp4` com os quadros da
  base **com a câmera aplicada** nos `toneTimes` (o `--tone-ref` regride pixel a pixel; sem a
  câmera a regressão compararia pixels desalinhados pelo zoom 1,08–1,14). No CLA200:
  correção `y·1,0032 + 1,65`.
- **Nitidez de decodificação:** a base é o mesmo arquivo nos dois motores, alinhada
  (correlação de fase ≤ 0,02 px), mas o quadro do HF é mais nítido que o do OffthreadVideo
  (|Laplaciano| 3,3 × 2,9). Por isso o SSIM do `hf_parity` é medido com os dois lados
  suavizados (σ 1 px) e o limiar da base ficou em 0,97 (o 0,99 era chute; plano §3.5 manda
  calibrar). Texto/2D continua 0,95 (decisão 3).
- **CLI 0.8.93 não tem `--keyframe-interval`** (a doc da skill é mais nova): o GOP denso que
  importa é o da `base.mp4` (`-g fps`).
- Vídeo dentro de sub-composição funciona (tempo local). `data-start` ≠ 0 nele dá o aviso
  `nested_media_start_basis_ambiguous` (só acontece com `pts_lag` > 0).

### Resultados F1
| Caso | base | broll/inserts | split | cards | hook | legenda | fadeOut | δ |
|---|---|---|---|---|---|---|---|---|
| CLA200 16:9, 140,4 s (misto, karaokê, prism, 11 B-rolls) | 0,9949 | 0,9944 | — | 0,9941 | 0,9959 | 0,9849 | — | 0 |
| fixture 9:16 (card, inserts card+cover, split, prism) | ≥ 0,975 | 0,9619 | 0,9749 | 0,994 | 0,9891 | 0,9614 | 0,9858 | 0 |
| fixture 16:9 (outline, B-roll vídeo+imagem, split, pill) | ≥ 0,972 | 0,9528 | 0,9799 | 0,9869 | 0,9938 | 0,9769 | — | 0 |
(SSIM mínimo por camada, σ 1 px, na caixa; δ = deslocamento de entrada/saída em quadros.)

Tempo de render CLA200 (RTX 5070): Remotion 8 min 22 s · HyperFrames 8 min 02 s (montagem
110 s na 1ª vez, quase toda a `base.mp4`; depois ~25 s). Entrega `deliver_mix --picture` +
`qa_mix`: −14,0 LUFS, −1,4 dBTP, "mix OK".
