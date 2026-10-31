# Plano — Timeline Prisma com controles e visual do HyperFrames Studio

Status: **Substituído pelo EDITOR (2026-09-30)** — a timeline completa do HyperFrames Studio roda DENTRO do Prisma
(aba EDITOR, helpers/export_hyperframes.py + preview_server.Studio). As Etapas 1–2 abaixo continuam valendo para
as abas Fase 1/Fase 2 (revisão rápida); a edição manual completa é no EDITOR.

Histórico: Etapa 1 entregue · Etapa 2 entregue (núcleo) · 2026-09-29
Etapa 2: ferramentas Seleção (V) / Lâmina (B, ⇧ corta vídeo+legenda), dividir na agulha (S),
corte manual (S·S·Delete), aparar/apagar clipes nas DUAS fases, legenda editável (mover, aparar,
texto por duplo clique/Enter, dividir, apagar → servidor grava captions.json), cards de
palavra-chave (highlights) arrastáveis/apagáveis, desfazer/refazer (Ctrl+Z / Ctrl+Shift+Z), snap
(N, 8px, agulha > bordas, guia visual), J/K/L, Home/End, ⇧← → 10 frames. Divisão sozinha não
é ajuste (pedaços contíguos do mesmo take são fundidos no save — evita eco do J-cut).
Pendente da Etapa 2: marquee/multi-seleção, copiar/colar/duplicar, reordenar takes, ripple
explícito, "fechar gap". Verificado em fixture (split, undo/redo, corte manual, legenda
mover/aparar/texto → captions.json no disco, card snap + delete → edit-data.json).
Etapa 1: `assets/preview/timeline-skin.css` (novo) + ajustes em `app.js`/`index.html`;
verificada em fixture vertical e horizontal, Fase 1 e Fase 2. Corrigido de passagem:
aviso fantasma de "ajuste não salvo" quando a trilha tinha volume ≠ 0.1.
Decisões: accent = verde do Studio `#3ce6ac`; entrega etapa por etapa; HyperFrames global não atualizado.
Decisão do Wellington: portar para a timeline própria do Prisma (não trocar para HyperFrames),
trazendo **todos os controles e o visual** do Studio. Referência técnica:
`references/_hf-studio-inventory.md` (Studio 0.8.91, Apache-2.0).

## Princípios
1. **Uma UI só.** Continua em `assets/preview/` (vanilla JS, sem build), servida por
   `preview_server.py`. Vale para todo projeto, curto e longo, vertical e horizontal.
2. **A timeline edita um rascunho; o agente aplica.** O save continua indo para
   `preview_edits.json` (nunca edita `edl.json` direto), agora como **lista de operações**
   em vez de só bordas + notas. Assim o `speech_regions`/`verify_cut` continuam protegendo.
3. **Nada aparece na timeline sem o render saber fazer.** Cada controle entra junto com
   a capacidade correspondente no `render.py` / Remotion, ou fica fora.
4. **Atribuição.** Lógica adaptada do Studio leva cabeçalho Apache-2.0 + linha em
   `NOTICE` e `CREDITS.md`.
5. **Marca.** Geometria, densidade e comportamento do Studio. Cor de destaque: ver
   pergunta em aberto 1.

## Arquitetura
`app.js` (2.505 linhas) é dividido em módulos ES carregados por `<script type="module">`:

| Módulo | Conteúdo |
|---|---|
| `timeline/model.js` | modelo único de clips/trilhas derivado de EDL + edit-data + captions |
| `timeline/history.js` | undo/redo no cliente (pilha de snapshots do rascunho, coalesce 300ms) |
| `timeline/snap.js`, `zoom.js`, `layout.js`, `gaps.js`, `marquee.js`, `collision.js` | porte da lógica pura do Studio |
| `timeline/tools.js` | Select / Razor, seleção múltipla, clipboard, atalhos |
| `timeline/render-dom.js` | desenho das trilhas, clips, régua, playhead, overlays |
| `timeline/ops.js` | converte o rascunho em `preview_edits.json` v2 |

O Estilo, o gate de formatos, o player e o polling ficam onde estão.

## Etapas

### Etapa 1: visual (sem mudar comportamento)
- Tokens do Studio: shell/linha/gutter, clips 8px vs áudio em pílula 21px violeta, rótulo-chip,
  degraus de largura, seleção 1,5px, handles com opacidade por estado.
- Cabeçalho de trilha de 232px (ícone, nome, contagem, olho), linhas de 48px, régua de 24px mono,
  playhead com cabeça em losango e glow.
- Toolbar de 28px com ícones SVG próprios (sem dependência externa), leitura de zoom, slider log.
- Portrait continua com player à direita; a timeline ganha a mesma densidade.
- **Prova:** screenshots antes/depois num projeto real, vertical e horizontal.

### Etapa 2: núcleo de edição
- Ferramentas Select (V) e Razor (B), Split no playhead (S), ⇧+Razor corta todas as trilhas.
- Mover e **reordenar takes** na trilha principal com **Ripple** (padrão ligado), "fechar gap".
- **Snap** (N): playhead > bordas > marcadores, com guia visual.
- Multi-seleção: ⇧-click, marquee, `[` `]`. Copiar/colar/duplicar/recortar (⌘C/V/D/X). Delete.
- **Undo/redo** (⌘Z / ⌘⇧Z / Ctrl+Y) cobrindo tudo, inclusive as notas.
- Transporte: J/K/L, ←/→ por frame, ⇧ ×10, I/O in/out, Space.
- Zoom: Fit ×1,2, ×2/÷2, Ctrl+roda ancorado no cursor, follow a 75%.
- Tudo isso já cabe no formato atual (EDL = lista ordenada de `source/start/end`; inserts/hooks
  têm `start/end`). **Prova:** teste de ops → EDL aplicado e renderizado, `verify_cut` limpo.

### Etapa 3: trilhas
- Modelo por tipo: V1 (A-roll), overlays (inserts, hook, CustomGraphics), legendas (faixa
  única colorida, tempo por palavra editável — o Studio removeu, o Prisma já tem), A1/A2 (J-cut),
  música, SFX.
- Olho e mudo por trilha; **lock e solo** (o Studio não tem, pedido de "mais controle").
- Lanes com caret (J-cut, keyframes, automação) e altura que cresce com as lanes.

### Etapa 4: áudio fino
- Fades arrastáveis nos cantos dos clips de áudio (cunha escura).
- **Envelope de volume** desenhado na trilha (pontos, formas Ramp/Swell/Dip, simplificação),
  substituindo o fader único; os faders atuais viram o nível-base.
- Render: envelopes e fades no `edit-data.json` → `volume={f => …}` no Remotion para
  música/SFX e voz. **Prova:** medir loudness nos trechos com `voice_levels.py`.

### Etapa 5: além do Studio (capacidade nova de render)
O Studio **não** edita velocidade, freeze nem crossfade. O Prisma passa a fazer:
- **Velocidade** por take (0,25–4×, com pitch preservado) e **freeze** de frame → `render.py`.
- **Crossfade/transição** na emenda (badge na costura, como no Studio) → `render.py` / J-cut.
- **Keyframes (K)** de zoom/punch e posição por clip → `camera` passa de lista de números para
  keyframes com easing; mesmo esquema para inserts (Ken Burns editável).
- **Prova:** render de fixture com cada operação + `verify_cut` + frames extraídos.

### Etapa 6: contrato e documentação
- `preview_edits.json` v2 (`ops[]`: split, move, reorder, duplicate, delete, trim, speed,
  freeze, fade, envelope, keyframe, transition, note), com compatibilidade para o formato
  atual; `watch_edits.py` resume as ops.
- `SKILL.md`: seção "Preview interface" reescrita (atalhos, ops, como aplicar cada uma).
- Tela **?** de atalhos atualizada.

## Verificação por etapa
Projeto de fixture curto (vertical + horizontal) em `assets/preview/_fixtures/`;
`preview_start` → interação real no browser → screenshot → save → aplicar ops →
render → `verify_cut`. Uma etapa só fecha com essa evidência.

## Perguntas em aberto
1. **Cor de destaque:** verde do Studio (`#3ce6ac`) ou laranja Prisma (`#ff5200`)?
   Recomendação: laranja Prisma no playhead/seleção, o resto igual ao Studio.
2. **Ordem:** 1 → 2 → 3 → 4 → 5, entregando e testando cada etapa? Recomendado.
3. **Atualizar o HyperFrames global** de 0.4.3 → 0.8.91 (só se você quiser usar o Studio à parte).
