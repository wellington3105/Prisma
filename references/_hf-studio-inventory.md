# HyperFrames Studio 0.8.91 — inventário da timeline NLE

Fonte: `@hyperframes/studio@0.8.91` (Apache-2.0, heygen-com/hyperframes), estudado em
`$TEMP/hfstudio/package/src/`. O motor real da timeline está em `src/player/components/*`
(`nle/TimelinePane.tsx` só embrulha `<Timeline>`). Uso: referência para o porte em
`assets/preview/`. Qualquer lógica adaptada leva atribuição em `NOTICE` / `CREDITS.md`.

## 1. Ferramentas e operações
- Ferramentas: **Select (V)**, **Razor/Split (B)**, Select-leftward `[`, Select-rightward `]` (`components/TimelineToolPicker.tsx:29-58`). Razor+⇧Click corta todas as trilhas (`TimelineRazorInteraction.tsx:39`); guia do razor = 1px `--timeline-danger`.
- Toolbar esquerda: Undo/Redo · picker · divisor · Snap (N) · Ripple · Medidores de áudio · Keyframe (K, losango cheio/vazio) · Auto-record (vermelho) · Split no playhead (habilitado só com clip selecionado e playhead dentro) · Beat. Direita: thumbs · Fit · Zoom− · slider log 96px · Zoom+ · leitura "Fit"/"N%" mono 11px (`TimelineToolbar.tsx:213-554`).
- Mover: livre no tempo e entre lanes; classificado em timing / lane-reorder / track-insert, commit atômico (`hooks/timelineMoveAdapter.ts:28`).
- Trim: zonas de 14px nas bordas, barra de 2px (`TimelineClip.tsx:144-202`); trim de início desloca `playbackStart` por delta×rate (`timelineEditingHelpers.ts:230`); mínimo 0,1s (piso 0,05s) (`timelineGroupEditing.ts:7-8`).
- **Não existem no Studio:** roll, slip, edição de velocidade do clip, freeze (o SpeedMenu só muda a velocidade do preview).
- Delete/Backspace apaga a seleção inteira; keyframes selecionados primeiro; range de automação tem prioridade (`hooks/appHotkeysDispatch.ts:241-283`).
- **Ripple** (padrão ligado, `playerStore.ts:444`): delete na trilha principal puxa os clips seguintes; clique-direito em gap → "Close gap" / "Close all gaps".
- ⌘C/⌘V/⌘X/⌘D copiar/colar/recortar/duplicar; menu de contexto do clip: Split (S), Copy/"Copy N clips", Paste, Duplicate, Delete; ⌘G/⌘⇧G agrupar/desagrupar.
- Multi-seleção: ⇧-click; ⇧-arrastar no vazio = range de tempo; arrastar no vazio = marquee (⌘/⇧ adiciona; começa após 4px, `timelineMarquee.ts:8`); apertar a régua = scrub.
- **Snap** (`timelineSnapping.ts`): raio 8px (`TIMELINE_SNAP_PX`) ÷ px/s; prioridade playhead(0) > borda de clip(1) > beat(2); dedup a 1ms; exclui o próprio clip; trim não gruda no playhead; clamp [0, dur−len]; N alterna, ligado e persistido (`playerStore.ts:439`). Pontos de automação em passos de 0,04s.
- **Undo** (`hooks/usePersistentEditHistory.ts`): entradas `{label, coalesceKey, coalesceMs, files:{path:{before,after}}}` no servidor; coalesce 300ms; falha com `content-mismatch` se o arquivo mudou. ⌘Z, ⌘⇧Z/Ctrl+Y.
- **Fades** (`TimelineClipFades.tsx`): pontos de 10px nos cantos (hit 16px, limiar 2px) em clips de áudio / vídeo com áudio → `data-fade-in/out`; cunha `--timeline-fade-shade rgba(0,0,0,.38)`. Sem handle de crossfade; transições aparecem como badge na emenda.
- FX popover 260px (presets de `@hyperframes/core/audio-fx-presets`, "+ effect", "Open rack"); só em grupos ou trilha com 1 clip de áudio.
- Keyframes: K liga/desliga no playhead; lanes de losangos de 28px; "Edit Ease…" no clique-direito; áudio não recebe keyframe.
- Formas de automação: Ramp up, Ramp down, Swell, Dip (`automationShapes.ts:18`).

## 2. Trilhas
- Linhas = trilhas autorais (`data-track-index`), número exibido 1-based; sobreposição no mesmo tempo vira sub-lane; nunca sobreposição na mesma trilha.
- Duas zonas: visual em cima, áudio embaixo (`timelineZones.ts` `classifyZone`); trilha principal = track 0 com clip visual.
- Drop (`timelineCollision.ts:43`): perto da fronteira → nova trilha (na zona certa); senão lane livre na zona (prefere acima); senão nova trilha ao lado.
- Cabeçalho 232px sticky, `--timeline-gutter-bg`, borda 1px: glifo de música (áudio) · nome 11px · contagem de clips · olho (24px) · FX · caret de lanes. **Sem mute/solo/lock/altura** — linha fixa 48px, +28px por lane de keyframe, +72px por lane de automação.
- Grupos de áudio: cabeçalho acima, membros recuados 14px com trilho 2px `--timeline-accent-rail` e tint; envelopes de volume/FX do grupo (pontos 4,9px, `TimelineAutomationLane.tsx:50`), simplificação (`automationSimplify.ts`).
- Legendas (`captions/components/CaptionTimeline.tsx`): faixa de 40px, segmentos coloridos por ciclo `#3CE6AC #FF6B6B #4ECDC4 #FFE66D #A78BFA #F472B6 #34D399 #FB923C #60A5FA #C084FC`, rótulo 9px preto; edição de tempo foi removida de propósito (l.21-25).
- Espelho de z-order canvas ↔ ordem de lanes (`timelineZMirror.ts`).

## 3. Atalhos
Space play/pause · J/K/L ré/stop/frente · M mute · ⇧L loop · ←/→ 1 frame · ⇧←/→ 10 frames · F fullscreen ·
S split · B razor · V select · A volta ao select com razor (senão vai ao in-point) · Esc (razor: desseleciona, depois select) ·
`[`/`]` · N snap · K keyframe · R gesto · Del/Backspace · ⌘Z / ⌘⇧Z / Ctrl+Y · ⌘C/V/X/D · ⌘G/⌘⇧G ·
I/O in/out · ⇧I/⇧O limpa · A/E vai ao in/out · setas/Home/End/PgUp/PgDn navegam na timeline focada, Enter entra, ⇧F10 menu.
Fontes: `studioShortcuts.ts:22-106`, `appHotkeysDispatch.ts`, `useTimelineKeyboardActor.ts:107-142`.

## 4. Linguagem visual
(`styles/theme.css:37-160`, `styles/components.css:140-360`)
- Shell `#0a0a0b` · linhas `#101014` · gutter `#0e0f12` · bordas: linha 6%, gutter 10%, régua 16%, shell 5% (branco).
- Texto 92% / 62% / ticks 34%; tick maior 10%, menor 6%.
- Clip visual: fundo branco 12% (hover 16%), borda 22%; ativo `rgba(60,230,172,.2)` borda .55 (hover .75); arrastando `rgba(38,42,52,.96)` + sombra `0 8px 24px rgba(0,0,0,.4)` + `translateY(-1px)`; raio 8px; sombra = highlight interno 8% + `0 2px 6px rgb(0 0 0/.3)`.
- Clip de áudio: violeta `rgba(167,139,250,.16)`, borda .4, hover .24, arrastando `rgba(60,52,84,.96)`, mudo `rgb(72,74,78)`, raio **21px** (pílula); barras da forma de onda `rgb(245,237,255)`; linha de vínculo vídeo↔áudio 1px `#a0aaa4`.
- Tipo de clip não muda a cor (só áudio vs resto); o tipo aparece por thumbnail e ícones 15×15 em `dist/icons/timeline/*.svg`.
- Seleção: `outline 1.5px rgba(255,255,255,.85)` offset −1.5px + anel interno 1px .55. Empilhamento 1/5/10/20 (normal/hover/selecionado/arrastando). Handles: opacidade .95/.82/.76/0, só com clip ≥32px ou selecionado. Cursor padrão.
- Rótulo: chip no topo 5px / esquerda 6px, padding 1×5, raio 4, `rgba(15,22,18,.73)` (áudio `rgba(25,16,38,.7)`), 10px/500; timecode embaixo 9px mono. Degraus de largura: ≥60px rótulo; 24–60 só imagem; <24 um frame; mínimo 4px.
- Accent `#3ce6ac` (soft .18, fill .1, glow .5, border .7, rail .35); beats `rgb(34,197,94)`.
- Playhead: linha 1px accent com glow 6px + faixa de glow 13px; cabeça losango 9×9 (quadrado girado 45°, raio 2, borda 1,5px), vazada em repouso e cheia no scrub; a linha começa 10px abaixo; z 100.
- Régua 24px sticky (z 70), sem borda; rótulos 10px mono em +5px/top 5px; tick menor 1×8px, maior altura total a 10%; linhas de beat com opacidade .08–.7 (gamma 2,2), só se espaçadas ≥5px.
- Overlays: guia de snap 1px (accent + glow 6px no playhead, senão branco .6); linha de nova trilha 1px accent glow 3px; linha de inserção 2px + ponto 8px; marquee accent .1 com borda tracejada 1px .7, raio 2; range `rgba(59,130,246,.12)` bordas .4; emenda de transição = zona borrada 42px + badge redondo 28px.
- Toolbar: botões 28px quadrados, raio 6, neutral-400, hover branco 6%, ativo branco 8% + neutral-100, press scale .98; ícones Phosphor 16px; `px-2 py-0.5 gap-0.5`, borda inferior neutral-800/60.
- Fontes: sans `-apple-system, "Segoe UI", Roboto`; mono `"JetBrains Mono", "IBM Plex Mono"`. Transições de 120ms ease-out (respeita reduced-motion).
- Layout: 50px de folga acima das trilhas, 72px abaixo, 48px antes do zero.

## 5. Interação
- Zoom (`timelineZoom.ts`, `timelineLayout.ts:295-404`): Fit = duração×1,2 (60s se desconhecida); manual de 10% a `(30fps×48px)/fitPps`; botões ×2/÷2; Ctrl+roda/pinça `exp(−deltaY×0,014)` ancorado no cursor; Fit zera o scroll; a primeira edição fixa o zoom atual.
- Scroll: segue o playhead ao passar de 75% da largura; auto-scroll na borda (zona 40px, até 12px/frame); conteúdo estende 160px além do fantasma; régua e cabeçalhos sticky.
- Scrub: apertar a régua, clamp [0, dur]; a cabeça enche durante o scrub.
- Arraste: camada de gesto separada desenha o clip-fantasma; outros selecionados vão como "passageiros"; fantasma mostra snap, linha de inserção e limites de zona; preview do trim adianta 1 frame.
- Tooltips com atalho ("Snapping on (N)", "Split at playhead (S)", "Ripple on — keeps the main track gapless"); `title` do clip "label • 1.0s – 3.0s".

## 6. Lógica portável (sem React)
| Arquivo (`src/player/components/` salvo indicação) | Funções | Para quê |
|---|---|---|
| `timelineSnapping.ts` | `collectTimelineSnapTargets`, `snapTimelineTime`, `snapMoveToTargets`, `resolveSnapGuide` | alvos, snap por prioridade, guia |
| `timelineZoom.ts` | `getTimelinePixelsPerSecond`, `clampTimelineZoomPercent`, `getNextTimelineZoomPercent`, `getPinchTimelineZoomPercent`, slider log | zoom |
| `timelineLayout.ts` | `createTimelineRowGeometry`, `getTimelineFitPps`, `getTimelineScrollLeftForZoomAnchor`, `getTimelinePlayheadLeft`, `getTimelineScrubTime`, `getTimelinePlaybackFollowScrollLeft` | geometria, zoom ancorado, follow |
| `timelineGaps.ts` | `resolveTrackGapAt`, `resolveAllTrackGaps`, `resolveCloseGapShifts` | gaps |
| `timelineCollision.ts` | `resolvePlacement`, `isLaneFree`, `timeRangesOverlap`, `resolveInsertRow` | regras de drop |
| `timelineZones.ts` | `classifyZone`, `isMainTrackElement` | zonas |
| `timelineMarquee.ts` | `isMarqueeDrag`, `getMarqueeRect`, `computeMarqueeSelection` | marquee |
| `timelineEditing.ts` | `resolveTimelineMove`, `resolveTimelineResize`, `resolveTimelineAutoScroll` | mover/aparar, auto-scroll |
| `timelineGroupEditing.ts` | `resolveTimelineGroupMove`, `clampTimelineGroupResizeDelta`, `applyClipStartTrimDelta` | edição em grupo |
| `timelineMultiDragPreview.ts` | `multiDragDeltaSeconds`, `clampGroupMoveDelta` | passageiros |
| `automationLaneDragMath.ts`, `automationSimplify.ts`, `automationShapes.ts` | `computeGroupMove`, `simplifyPoints`, `generateShape` | envelopes |
| `src/hooks/usePersistentEditHistory.ts` | modelo de histórico | undo com coalesce (backend próprio) |
| `timelineTheme.ts` | `clipWidthLadder`, `getClipHandleOpacity` | degraus de largura, handles |
