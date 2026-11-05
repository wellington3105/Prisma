# LONGFORM track (YouTube 16:9) — cut philosophy + Phase 2 + captions reference

Read this file when the source is horizontal / the user says YouTube, longform,
tutorial or vlog. Reuses the whole Phase-1 engine and Phase-3 soundtrack —
what changes is the cut intent, output spec, captions, and the Phase-2 visuals.

## Deltas vs short-form

| | Short-form | **Longform** |
|---|---|---|
| Aspect / res | 1080×1920 @ 24 | **16:9 at source res/fps** (`render.py --keep-resolution`) |
| Cut goal | max compression | **retention arc**, keep pacing/breath |
| Silence trim | aggressive (30–80ms pads) | **gentle** — cut fillers/mistakes/dead-air > ~0.8s; keep 300–600ms beats |
| Captions | karaoke burned | **`.srt` for YouTube CC** by default — `captions_srt.py`; burned captions are **optional** (`captions.enabled`, Reels horizontal) |
| Hook | static 4s headline | **cold open** (5–15s tease) + intro |
| Camera | hard-zoom dynamic | mostly static; **B-roll cutaways** carry variety |
| Template | `assets/shortform/` | **`assets/longform/`** |

**Turning this source into short-form clips too?** `clip_finder.py` shortlists
candidate windows from the transcript (decupagem), and `reframe.py` reframes
each chosen window 9:16 with face/speaker tracking instead of a fixed center
crop — see `SKILL.md`'s Phase-1 helper list. Run these on the ORIGINAL
landscape source, before this file's retention-cut steps, since a Reel and
the longform cut are usually different selections from the same material.

## Phase 1 — cut for retention, not compression

Same helpers (`transcribe` → `pack` → editor sub-agent → `speech_regions` →
`render`), different intent:

1. **Retention arc**, assembled by argument, not clip order:
   - **COLD OPEN (0–15s):** the single most compelling line from *anywhere* —
     payoff tease, bold claim, the "after". Retention make-or-break.
   - **INTRO:** who/what/the promise. Short.
   - **BODY:** chapters, each opening a mini-hook and closing a loop.
   - **PAYOFF → OUTRO/CTA:** deliver, then CTA. **Last ~20s visually calm**
     (YouTube end cards).
2. **Gentle silence pass:** cut fillers, false starts, restarts, dead air
   > ~0.8–1.0s only. Longform cut as tight as a Reel feels breathless.
3. **Re-hooks / open loops** at section turns ("mas antes…", tease what's next)
   so retention survives the mid-video dip.
4. **Editor sub-agent brief:** longform archetypes — tutorial
   (INTRO→SETUP→STEPS→GOTCHAS→RECAP), talking-head essay
   (COLD-OPEN→THESIS→POINTS→COUNTER→CONCLUSION→CTA), vlog
   (COLD-OPEN→ARRIVAL→BEATS→REFLECTION). Tell it to place a cold open and to
   label chapter starts with `"chapter": "Title"` on the opening range.
5. **Render at source spec:** `render.py edl.json -o cut.mp4 --no-subtitles
   --keep-resolution` (+ `--voice-master` as usual; −14 LUFS is YouTube's
   target too). Verify with `verify_cut.py … --min-silence 1.2` (longform keeps
   breathing room — don't flag natural beats).
6. **Tutorial / screen-record:** the capture is the base video; add crop-zoom
   into the active UI region + callouts in Phase 2 rather than a face camera.

## Chapters + .srt (ship with the video)

- `chapters.py <edit>/edl.json -o <edit>/chapters.txt` — YouTube description
  block from the EDL `"chapter"` fields. YouTube rules (validated by the
  helper): first stamp `00:00`, ≥ 3 chapters, each ≥ 10s.
- `transcribe.py cut.mp4 --edit-dir <edit>` then
  `captions_srt.py --transcript <edit>/transcripts/cut.json -o <edit>/captions.srt`
  — broadcast-style cues (≤42 chars/line, ≤2 balanced lines, 1–6s, sentence
  case). Uploaded as CC, never burned into the YouTube file.

## Legenda queimada em 16:9 (Reels horizontal)

Burned captions now exist in the 16:9 template too (`assets/longform/src/Captions.tsx`
+ `SimpleCaptions.tsx`), off by default. Use them when the same horizontal video
also goes to Instagram Reels, where there is no CC toggle.

- `edit-data.json` → `"captions": {"enabled": true, "style": "karaoke"}`.
  `style`: `karaoke` (default), `stacked`, `scatter`, `simples`, `serifada`,
  `classica` — all six, as in 9:16. Optional: `maxWords` (default 6), `fontScale`
  (default 1), `highlight` (karaoke: colour of the word being spoken), `side`
  (`stacked`/`scatter`: `"left"` default | `"right"` | `"center"` — the free third
  beside the speaker; judge it per video, never over the face).
- `stacked` also needs `caption_style.py --transcript <edit>/transcripts/cut.json
  -o <edit>/remotion/public/caption-cues.json` (same helper as 9:16; the scaffold
  ships an empty placeholder). `scatter` reads `captions.json` alone.
- Needs `public/captions.json` — `captions_for_remotion.py --transcript
  <edit>/transcripts/cut.json -o <edit>/remotion/public/captions.json`
  (the scaffold ships an empty `[]`).
- Layout is landscape, not portrait pixels: everything is a ratio of the frame
  (size ≈ 5.8% of height, baseline 10% of height from the bottom, line ≤ 70% of
  width), so 1080p and 4K render the same picture. Captions are drawn ABOVE
  B-roll, glass and transitions so they stay readable over cutaways.
- **Two deliveries, ONE edit.** Render the same `edit-data.json` twice, changing
  only `captions.enabled`:
  - `true` → the Reels file (captions burned in);
  - `false` → the YouTube file, plus the `.srt` sidecar from `captions_srt.py`.
  Never two different edits — same cut, same B-roll, same timing; the only
  difference is the caption layer. `render_phase2.py` picks the `Longform`
  composition automatically for this template.

## Phase 2 — 16:9 visuals (data-driven template)

**Plano de inserts first** — same gate as short-form (`shortform.md`, "Plano de
inserts"): every B-roll cutaway, callout and chapter card is an `iNN` item
approved by number before it is written into `edit-data.json`
(`inserts_plan.py check → show → approve → apply`). On longform, approve by
section ("o gancho primeiro", "até 3:00") — the plan can be partially approved
and applied as it goes.

Scaffold + describe, same pattern as short-form:

```bash
cp -R <skill>/assets/longform/. <edit>/remotion/ && cd <edit>/remotion && npm install
cp ../cut.mp4 public/
```

Write `public/edit-data.json` (schema in `assets/longform/README.md`):
width/height/fps/durationSec **matching cut.mp4 exactly**, accent color, and
the four layers — graphics **punctuate, they don't saturate**:

- **broll[]** — full-frame image (Ken-Burns) or muted video cutaways over
  narration; the core of longform visual variety. Sync to what's said.
- **lowerThirds[]** — name/title card slides in bottom-left, ~3–4s.
- **chapters[]** — title card at each chapter start (mirrors chapters.txt).
- **callouts[]** — accent chip at a normalized x/y for emphasis
  ("2x mais rápido"). Occasional — NOT karaoke.

Reuse short-form extras sparingly if a moment calls for it (dynamic camera,
behind-the-subject, SFX) — longform ≠ Reel density. Verify with ONE
`contact_sheet.py` over the graphic moments, render
`npx remotion render Longform out/render.mp4`, loudnorm → `edit/final.mp4`.

Never edit `src/Main.tsx` — it's data-driven; the JSON is the edit.

---

## Anti-patterns (Fase 2/3)

**Espelhados de `shortform.md` — mudou um, muda o outro.** Valem para os dois
tracks; os que dependem da aba Estilo ficaram só no short-form, que é onde ela
existe.

- Hardcoding a bespoke graphic's timings inside `CustomGraphics.tsx`. Put the
  windows in an `edit-data.json` array (a key the template ignores, e.g.
  `splitInserts`) and map over it — otherwise the graphic is invisible to the
  preview timeline and the user cannot see or retime it.
- Re-rendering Phase 1 without regenerating `segments.json`. Every Phase-2
  overlay that must land on a cut is indexed off that file; stale, it is off by
  frames and nothing errors. Worse, a `VIDEO_LAG`-style constant can absorb the
  first frame of the drift and make a broken file look correct at the one
  boundary you happen to check.
- Delivering Phase 2 with Remotion's own audio track — it drifts progressively against the source (+0.66s by 78s on a 95s edit). Re-mux `cut.mp4`'s audio and mix the soundtrack in ffmpeg (recipe in the track reference).
- Judging A/V sync with short correlation windows — speech is quasi-periodic and a 2–3s window happily locks onto the wrong syllable, inventing a drift. Use 15s+ windows, and remember a PARTIAL render cannot show drift that accumulates over the full timeline.
- Indexing Phase 2 off `Σ(end−start)` when a `jcut_timeline` exists — the J-cut output is shorter, so everything after the first take lands late.

---

## Helpers de Fase 2/3

- **`epidemic_music.py`** — trilha licenciada do Epidemic Sound: `search` →
  `fit <id> --duration <cut>` (edição com final real, ≤300s) ou `download`
  inteira/stem. Fluxo em `references/soundtrack.md` "Catálogo licenciado".

---

## Chaves opcionais (nunca pedidas na instalação)

Nada aqui é necessário para instalar ou para a Fase 1. Peça UMA chave só no
momento em que o recurso for de fato usado, explique para quê, e escreva em
`.env` na raiz da skill — nunca em `<videos_dir>`. Se o usuário não quiser, siga
pelo caminho sem chave e diga o que muda.

| Chave | Recurso | Sem ela |
|---|---|---|
| `PEXELS_API_KEY` | imagens/vídeos ilustrativos | Wikimedia Commons cobre a maioria |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | marcas, pessoas e logos específicos | Wikimedia é o fallback |
| `TREBLO_API_KEY` | trilha sonora composta por IA (Fase 3) | trilha só a partir de arquivo local |
| `EPIDEMIC_SOUND_MCP_API_KEY` | trilha + SFX do catálogo Epidemic Sound (Fase 3) | Treblo ou arquivo local |

### Como o usuário cria a chave do Treblo (trilha com IA)

Quando ele escolher `musicAI` e não houver `TREBLO_API_KEY`, dite estes passos —
são a interface real do site, não um resumo:

1. Acessar **https://treblo.com/** e fazer login.
2. Clicar no **perfil**, no canto superior direito.
3. Abrir a seção **Developers**.
4. Clicar em **Get Started for Free**.
5. Clicar em **API Keys**.
6. Clicar em **Create Key**, escrever o nome **Prisma** e confirmar em **Create**.
7. Copiar a chave e colar na conversa.

Ao receber a chave: escreva `TREBLO_API_KEY=<chave>` no `.env` da raiz da skill,
confirme em uma linha que gravou, e **nunca repita a chave de volta** na conversa
nem em saída de ferramenta. Se ele preferir não criar conta, siga com trilha de
arquivo local — a Fase 3 funciona assim, só não compõe.

A instalação não menciona nenhuma delas de propósito: o Prisma não precisa de
chave para funcionar, e listar chaves no primeiro contato faz parecer que precisa.

## Camadas VFX (as mesmas do shortform)

O template horizontal tem `glass`, `transitions` (`displace`/`refract`),
`tracked` e `direction.energy` — os mesmos blocos do `edit-data.json` vertical,
com os mesmos componentes. Eles não sabem o aspecto do vídeo: o `rect` do vidro
é 0..1 e o camera solve trabalha no espaço do mundo.

**O que muda no horizontal é o ENQUADRAMENTO, não o código.** Um painel que
ocupa 76% da largura em 9:16 fica desproporcional em 16:9 — ali ele quer um
terço da tela, deixando espaço para o falante. Verificado com
`rect: {x: 0.06, y: 0.24, w: 0.40, h: 0.52}`, que é o painel encostado à
esquerda com o apresentador livre à direita.

### Headline, tela dividida e PiP (16:9)

Tudo da aba Estilo existe nas duas trilhas; as chaves do `edit-data.json` são as
do vertical, só a geometria muda.

- **Headline** — `hook: {enabled, endSec, text, style: outline|card|realce|misto,
  accent, logo, sign, side}`. `hook.enabled:false` = Nenhum. O texto é sempre
  quebrado em DUAS linhas balanceadas; no horizontal o bloco ocupa ≤50% da
  largura, canto superior esquerdo (`side: "left"|"center"|"right"`), porque o
  falante costuma estar centro-direita — ajuste pelo lado vazio, nunca sobre o
  rosto. Tamanhos são razões da altura do quadro (1080p == 4K).
- **Tela dividida** (`split` / `split2`) — `splitInserts[]`, as mesmas chaves do
  vertical, mas LADO A LADO: `layout: "top"` (id `split`, arte primeiro) = arte à
  ESQUERDA; `layout: "bottom"` (id `split2`) = arte à DIREITA. O falante é o
  `cut.mp4` reenquadrado: `zoom` (1.12), `focusX`/`focusY` (0..1 do source; 0.55 /
  0.5), `bandW` (parcela da arte, 0.5). `flash: "flash"|"whip-pan"|"glitch"` no
  item põe a transição de troca de layout na entrada e na saída.
- **B-roll com apresentador (PiP)** — `broll[].pip: true` (ou `{x,y,w,zoom,focusX,
  focusY}`): o cutaway cobre o quadro e o falante fica numa janela arredondada
  (canto superior direito, ~26% da largura).
- **Estilo (gate) → edit-data**: `split` → `splitInserts[]` com `layout:"top"`,
  `split2` → `layout:"bottom"`, `broll` → `broll[]`, `pip` → `broll[]` com
  `pip:true`. O PiP nunca existiu no template horizontal antes; não há projeto
  salvo que dependa do significado antigo de `split2`.

### Elementos do Estilo que o 16:9 constrói

Os seis elementos da aba Estilo têm o mesmo efeito no `edit-data.json`
horizontal — a tabela de mapeamento de `shortform.md` ("Workflow") vale para as
duas trilhas. Diferenças de número, não de chave:

| Elemento | Chave | 16:9 |
|---|---|---|
| `zoomCuts` | `camera.zooms[]` | **1.06–1.14** (9:16: 1.10–1.22 — num quadro largo o mesmo valor lê como um empurrão) |
| `zoomAuto` | `camera.pushIn` | **0.03** por segmento (9:16: 0.04). Exige `public/segments.json` |
| `tracking` | `camera.targetX/Y` + `track.json` | igual. OFF → `track.json` neutro `[[0.5,0.4]]` |
| `flashCut` | `transitions[]` ou `broll[].flash` | flash/whip-pan/glitch; no horizontal o lugar natural é a ENTRADA e a SAÍDA de um cutaway de B-roll (`broll[].flash` escreve as duas) |
| `glassPanel` | `highlights` `variant:"prism"` | placa de ~1/3 da largura (tamanho pela ALTURA do quadro), default `x 0.26 y 0.32` — ao lado do falante, nunca sobre o rosto. Ajuste `x`/`y` pelo lado vazio |
| `springIn` | `broll[].enter:"spring"` | no horizontal vale para `broll[]` (não há `inserts[]`). OFF → omita `enter` |

Dentro de uma janela `glass` ou `tracked` o quadro é desenhado pelo canvas e o
zoom/tracking da câmera não se aplica ali — mesmo trade do vertical.

Custo e regras idênticos ao vertical — ver `references/shortform.md` para as
seções "Painel de vidro", "Transição com distorção" e "Camera solve 3D".
`render_phase2.py` detecta o bloco 3D e passa `--gl=angle` sozinho.
