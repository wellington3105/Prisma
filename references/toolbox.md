# Quadro de ferramentas — SFX · Motion · VFX

O que o Prisma consegue fazer HOJE, o que custa uma instalação, e o que não vale
a pena. Escrito depois de auditar o código e MEDIR os arquivos (2026-08-18) —
não é catálogo de intenções.

**Regra que atravessa tudo:** cada elemento entra por uma razão do conteúdo. Um
efeito que existe porque ficou bonito é ruído. Em vídeo de saúde mental, é pior:
soa como deboche do assunto.

---

## 1. SFX — o que existe e o que realmente toca

`assets/shortform/public/sfx/` — 9 arquivos. **Níveis medidos com
`volumedetect`**, porque a diferença entre eles decide o que se ouve sob fala:

| Arquivo | Pico | Duração | Uso | Veredito |
|---|---:|---:|---|---|
| `caption-click.mp3` | −0.8 dB | 0.41s | palavra solo (stacked) | ✅ o mais audível |
| `caption-scratch.mp3` | −0.5 dB | 0.96s | palavra circulada | ✅ |
| `cut-click.mp3` | −2.0 dB | 0.06s | corte / flash | ✅ **use este no flash** |
| `whoosh.mp3` | −2.3 dB | 0.45s | entrada de card | ✅ |
| `pop.mp3` | −4.1 dB | 0.14s | forma aparecendo | ✅ |
| `click.mp3` | −4.9 dB | 0.03s | tique seco | ✅ |
| `tictac.mp3` | −13.7 dB | 3.35s | relógio/contagem | ⚠️ precisa +6 dB |
| `click1.mp3` | −11.3 dB | 0.29s | pop de elemento | ⚠️ fraco |
| `click2.mp3` | **−25.0 dB** | 0.37s | — | ❌ **INAUDÍVEL** |

**`click2.mp3` é uma armadilha.** A −25 dB ele não existe sob narração em
nenhum volume sensato: a mixagem parece correta, o meter mostra o canal, e nada
se ouve. Se precisar de um clique, use `cut-click.mp3`.

**Dois cuidados que só aparecem em produção:**

1. **Onde está o transiente dentro do arquivo.** Um clique com 180ms de silêncio
   na cabeça, atrasado para o instante do corte, bate 180ms tarde — depois de um
   efeito de 230ms já ter terminado. Corte o silêncio inicial antes de usar.
2. **O SFX da entrega é mixado no ffmpeg, não pelo Remotion.** O re-mux da
   entrega descarta o áudio do Remotion (ele deriva). Um `<Sfx>` no componente
   só soa num `remotion render` puro. Para a entrega, entre como input com
   `adelay=<frame/fps*1000>`.

### Como disparar em um instante qualquer

```tsx
<Sequence from={frame} layout="none">
  <Sfx src="cut-click.mp3" volume={0.7} />
</Sequence>
```

---

## 1b. Áudio — cadeia de voz e envelopes de volume

Complementam `music_carve.py` (voiceover carve, seção anterior a esta no
histórico do arquivo — busque por "Carve a música" em `shortform.md`/
`SKILL.md`). Nenhum dos dois é chamado automaticamente por `render.py`; são
passos opcionais quando o áudio bruto precisa de mais do que o
`--voice-master` do `render.py` oferece, ou quando a trilha precisa de uma
curva de nível em vez de um número fixo.

**`audio_chain.py`** — gate → EQ → compressor → limiter (+ reverb opcional),
nativo ffmpeg. Use quando `--voice-master` (a cadeia embutida do `render.py`)
não for suficiente — por exemplo, ruído de sala que precisa de gate antes do
compressor, ou EQ com bandas customizadas. Sempre `--measure` primeiro (mede
nível geral + energia por banda, mesma disciplina do `--measure` do
`music_carve.py`) antes de confiar nos defaults num áudio novo.

**`volume_envelope.py`** — curva de volume por keyframes
`(tempo_s, nível 0-1)`, para quando a trilha (ou qualquer faixa) precisa
variar ao longo do tempo — baixa na intro, sobe no corpo, desce no fim —
em vez do único `soundtrack.volume` fixo que o fader do preview salva hoje.
Um envelope com 1 keyframe reproduz o comportamento atual (nível fixo); use
mais keyframes quando o pedido for algo como "a trilha deveria entrar mais
baixo e crescer depois do gancho".

---

## 2. Motion — o que já está construído

`assets/shortform/src/CustomGraphics.tsx` é **o único arquivo de código
editável** do template. Já traz:

| Componente | O que faz |
|---|---|
| `CutFlashes` (`type: 'flash'`, default) | feixe de luz atravessa o quadro com bloom, 7 frames |
| `WhipPan` (`type: 'whip-pan'`) | linhas de movimento horizontais + white-out breve, lê como giro rápido de câmera |
| `Glitch` (`type: 'glitch'`) | bandas ciano/magenta com jitter, "falha digital" — ⚠️ evitar em conteúdo de saúde mental/vulnerabilidade, mesmo motivo do `chromaticAberration` abaixo |
| `SplitScreen` | tela dividida com costura, corte seco |
| `TimelineInner` | timeline de edição sendo cortada (exemplo) |
| `ScriptInner` | folha de roteiro com texto datilografando (exemplo) |
| `ShapesInner` | formas geométricas pipocando (exemplo) |

Todas as três transições de corte são a mesma peça de dado (`transitions[]` em
`edit-data.json`, campo `type` opcional) — ver `references/shortform.md`
"Transições na troca de layout" para o schema completo e o raciocínio de
quando usar cada uma.

Mais, no `Main.tsx` (imutável): Ken Burns nos inserts, push-in de câmera,
tracking de rosto, legendas animadas em 6 estilos.

**Duas lições do flash, que valem para qualquer motion novo:**

- **O efeito LIDERA o evento em 2 frames.** Começar na hora faz o olho ver a
  mudança e só então a luz — parece defeito. Antecipando, a luz parece a causa.
- **Blur separa feixe de lavagem.** A 26px lê como clarão geral; a 16px lê como
  feixe. Suba opacidade e baixe blur juntos.

### Motion graphics explicativo — o padrão

Para gráfico que ENSINA (não só ritma), o esqueleto é sempre o mesmo:

```tsx
// Cada elemento entra quando a FALA o menciona — o tempo vem do transcript,
// nunca de um ritmo arbitrário.
const t = (frame - startFrame) / fps;
const aparece = interpolate(t, [0, 0.4], [0, 1], {
  extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  easing: Easing.bezier(0.16, 1, 0.3, 1),
});
```

**Regra de ouro:** as janelas vão em `edit-data.json` (um array que o template
ignora, ex. `splitInserts`), nunca fixas no TSX. Fixo no código, o gráfico fica
invisível para a timeline do preview e o usuário não consegue ver nem retimar.

---

## 3. VFX — `@remotion/effects` (uma instalação)

**Não vem instalado.** Custa um comando:

```bash
npx remotion add @remotion/effects
```

E, para renderizar, WebGL ligado no `remotion.config.ts`:

```ts
import {Config} from '@remotion/cli/config';
Config.setChromiumOpenGlRenderer('angle');
```

São ~50 efeitos aplicáveis via prop `effects` em `<Video>`, `<CanvasImage>`,
`<Solid>` e `<HtmlInCanvas>`. Os que interessam para conteúdo falado:

| Efeito | Onde serve |
|---|---|
| `glow()` | destacar um elemento sem cobrir o rosto |
| `lightLeak()` | passagem de tempo, transição de bloco |
| `vignette()` | fechar a atenção no centro |
| `zoomBlur()` | ênfase súbita (usar com muita parcimônia) |
| `wave()` | **movimento de água — o "mar interno" literal** |
| `chromaticAberration()` | glitch/tensão — quase sempre errado em saúde |
| `duotone()` · `grayscale()` | separar passado/presente, antes/depois |
| `noiseDisplacement()` | dissolução orgânica |
| `dropShadow()` | separar camada do fundo |

**Custo:** WebGL no render. Meça antes de aplicar ao vídeo inteiro.

**O que NÃO usar em vídeo de saúde mental:** `tvSignalOff`, `pixelate`,
`chromaticAberration`, `barrelDistortion`, `fisheye`. O vocabulário de glitch
sugere defeito e erro — sobre TDAH, isso lê como o transtorno sendo o defeito.

### Efeito próprio

Quando nada da lista serve, `createEffect()` do próprio `remotion` cria um
efeito reutilizável com backend `2d` (filtros de pixel) ou `webgl2` (shader).
Não é gambiarra: entra no mesmo array `effects` e aparece no Studio.

---

## 4. O que precisaria de ferramenta externa

Auditado. **Quase nada:**

| Vontade | Precisa de algo novo? |
|---|---|
| Motion graphics explicativo | ❌ React + interpolate |
| Partículas, luz, distorção | ❌ `@remotion/effects` |
| 3D (cérebro girando, cena 3D) | ⚠️ `@remotion/three` + React Three Fiber |
| Lottie (animação do After Effects) | ⚠️ `@remotion/lottie` |
| Mapas animados | ⚠️ `@remotion/maps` |
| Visualização de áudio (barras) | ❌ já dá com `@remotion/media-utils` |
| Rotoscopia / máscara de pessoa | ❌ `person_matte.py` já existe |
| Reframe 16:9 → 9:16 seguindo o rosto | ❌ `reframe.py` já existe (`uv sync --extra reframe`) |
| Decupagem (1 vídeo longo → N clipes) | ❌ `clip_finder.py` já existe |
| Reusar um asset baixado num projeto anterior | ❌ `media_ledger.py` já existe |
| Publicar o vídeo entregue numa rede social | ❌ `publish.py` já existe (API do Postiz) |

Os três "⚠️" são pacotes oficiais do Remotion, instaláveis com
`npx remotion add`. **Nenhum caso exige sair do ecossistema.**

---

## 4b. Exemplos construídos e verificados (projeto 1001, 2026-08-18)

Ambos vivem em `CustomGraphics.tsx`, lidos de `explain[]` em edit-data.json:

```json
"explain": [
  {"kind": "exec", "start": 24.26, "dur": 6.6,
   "items": ["organização", "planejamento", "tomada de decisões", "memória de trabalho"]},
  {"kind": "wave", "start": 92.24, "dur": 4.2, "label": "pessoas-mar"}
]
```

**`exec` — lista que se monta.** Chips brancos entram um por vez, cada um no
segundo em que a fala nomeia o item, com `pop.mp3` a 0.34. O `start` sai do
transcript (`organização` em 24.26s) e o intervalo `per` é o ritmo real da fala,
não um valor redondo. Uma lista falada é difícil de segurar; vista, gruda.

**`wave` — o mar interno.** Ondas em SVG, desenhadas por `Math.sin` sobre
`useCurrentFrame()`, com amplitude subindo de 0.35 a 1.0 ao longo da janela:
calmo → agitado, que é literalmente o que ela descreve. **Substituiu a FOTO de
mar** que estava no split — a metáfora é interna, então o mar pertence ao fundo
dela, não a uma paisagem de oceano. Isso é a diferença entre ilustrar a palavra
e ilustrar a ideia.

Nenhum dos dois precisou de `@remotion/effects`: são React + `interpolate()` +
SVG. O pacote de efeitos (instalado, 4.0.482) fica para quando a necessidade for
de pixel — brilho, vazamento de luz, distorção.

---

## 4c. Voiceover carve — `music_carve.py`

Ideia vinda do **HyperFrames** (HeyGen, Apache 2.0), implementada no nosso
ffmpeg em vez de migrar de motor.

**O problema:** a saída padrão para "a música briga com a fala" é baixar a
música. Funciona, e custa a música — no volume em que ela para de brigar, ela
também quase não existe (0.10 neste projeto, audível só nas pausas).

**O carve:** divide a trilha em três bandas e comprime **só a banda média**
contra a voz. Grave e agudo mantêm o nível cheio, então a música conserva corpo
e brilho, enquanto a faixa onde a voz vive sai da frente — e só enquanto ela
fala.

```bash
uv run python helpers/music_carve.py --voice cut.mp4 --music trilha.mp3 \
    -o trilha_carved.mp3 --volume 0.22 --reduction 9
```

`--measure` mede a energia da voz por banda antes de escolher a faixa. Medido
nesta locutora (pt-BR, feminina): pico em **500-1000 Hz**, forte de 250 a 2000 —
daí o padrão 250-2200 Hz. Voz masculina senta mais baixo; meça em vez de chutar.

**Resultado medido** (música sozinha, banda 250-2200 Hz, plano vs carve):

| janela | delta |
|---|---:|
| fala 30s | −4.1 dB |
| fala 100s | **−8.7 dB** |
| fala 145s | −7.0 dB |
| pausa 133.45s | −4.1 dB |

Com isso a trilha pode ficar em **0.22** em vez de 0.10 — mais que o dobro — sem
disputar com a voz.

### Três coisas que só apareceram medindo

1. **`amix` DIVIDE pelo número de entradas.** Remontar três bandas com ele custa
   ~9.5 dB em cada e o carve some. Some as bandas com `normalize=0` e aplique o
   volume DEPOIS da remontagem.
2. **Não meça o mix — meça a música sozinha.** A primeira verificação comparou
   mixes completos e leu −0.10 dB, ou seja, "não funciona". A voz está a −17 dB
   na mesma banda e mascara a música inteira. Renderize o caminho da música SEM
   somar a voz e o sidechain fica visível.
3. **A pausa não abre.** Ajustar o release (150/220/300ms) dá exatamente o mesmo
   −4.2 dB: respiração e ruído de sala mantêm a chave acima do threshold. É o
   compressor funcionando. A música ainda toca 4 dB mais alta na pausa do que
   sob a fala.

---

## 5. Como escolher — a única pergunta que importa

Antes de qualquer elemento: **que trecho da fala pede isso?**

- Fala nomeia coisa concreta ("cérebro", "testes") → imagem / split
- Fala nomeia processo ("organização, planejamento") → motion explicativo
- Fala usa metáfora ("pessoas-mar") → VFX literal da metáfora
- Fala muda de argumento → transição com flash
- Fala enfatiza ("repito") → zoom + SFX
- Fala não pede nada → **nada.** Quadro limpo também é decisão

O erro caro não é escolher o efeito errado — é aplicar efeito onde a fala não
pediu. Mapeei 36 termos candidatos neste projeto e só 5 mereciam imagem; o
resto era abstração que o banco de imagens devolveria como clichê corporativo.
