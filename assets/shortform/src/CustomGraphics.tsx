/**
 * CustomGraphics — the ONE file you edit in Phase 2, and ONLY when a spoken
 * word calls for a bespoke motion graphic instead of a stock image (e.g.
 * "animações" → animated shapes, "roteiro" → a typewriter script sheet,
 * "gráfico" → a growing chart). Everything else is data in edit-data.json.
 *
 * Default: renders nothing. To add graphics, build components here (worked
 * examples below — same upper-zone card motif as the image inserts) and mount
 * them in <CustomGraphics/> with their own <Sequence from/durationInFrames>.
 *
 * Timings: get the payoff word's timestamp from the cut transcript and land
 * the animation on it. Keep 0.5–2s per accent; whoosh on entry, pop on shapes.
 */
import {
  AbsoluteFill,
  Sequence,
  Img,
  OffthreadVideo,
  staticFile,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {Sfx} from './Main';
import editData from '../public/edit-data.json';

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// ============ MOUNT POINT (edit this) ==========================================
// STYLE "TELA DIVIDIDA" (split screen) — driven by edit-data.json `splitInserts`.
// Leave the array out and this renders nothing, as before.
type SplitInsert = {
  src: string;
  start: number;
  end: number;
  fit?: 'cover' | 'contain';
  bandH?: number;
  layout?: 'top' | 'bottom';
};

// Two variants of one idea — both PIN THE FACE to a fixed region and give the
// rest of the frame to the image:
//   'top'    "Tela dividida"   — art on top, head raised underneath
//   'bottom' "Tela dividida 2" — head held high, art underneath
// The zoom/focus pair is what pins the face and is NOT interchangeable between
// them. `focusY` is a SOURCE y that lands at the top of the video window, so a
// point y_src renders at (y_src - focusY) * zoom.
//   top:    the head must be lifted out of the source's headroom → zoom in hard.
//   bottom: that headroom is the point — it is what puts the face under the
//           frame edge instead of in the middle.
// MEASURE THE SOURCE before trusting these numbers: ffmpeg a frame out of
// cut.mp4, read the hair-top and chin y, and set focusY so the head lands where
// the user asked. The values below fit a head ~660px tall starting at y 455.
const LAYOUT = {
  top: {zoom: 1.25, focusY: 400},
  bottom: {zoom: 1.0, focusY: 225},
} as const;

// A cut transition: a light beam whips across the frame while a short flash
// blooms, with a click on the cut. Data, not JSX — `transitions` in
// edit-data.json — so the windows stay visible to the preview timeline and
// retimeable without touching code.
//
// `type` picks the transition; omitting it keeps the original flash (no
// existing edit-data.json breaks). 'whip-pan' and 'glitch' are new (E4,
// idea taken from HyperFrames' packages/shader-transitions — their transitions
// are WebGL shaders run inside a Puppeteer/Three.js context with no ffmpeg or
// plain-CSS equivalent to port, so these are built from scratch for Remotion's
// own render model, not translated code).
type CutFlash = {
  at: number;
  // 'displace' and 'refract' also live in transitions[] but are NOT overlays —
  // they need the footage as a texture and are rendered by ShaderTransition.tsx
  // from the same list. They are named here so the filter below can skip them:
  // without it they would fall through the switch's `default` and paint a flash
  // ON TOP of the shader pass, firing two effects on one cut.
  type?: 'flash' | 'whip-pan' | 'glitch' | 'displace' | 'refract';
  intensity?: number;
  sfx?: string;
  volume?: number;
};

const OVERLAY_TYPES = ['flash', 'whip-pan', 'glitch'];
const isOverlayCut = (t: CutFlash) => OVERLAY_TYPES.includes(t.type ?? 'flash');

// Escurecimento suave no topo, para o headline ler sobre fundo claro (céu,
// teto do carro). Janelas em edit-data.json `scrims`, nunca hardcoded.
type Scrim = {start: number; end: number; opacity?: number; height?: number};
// Selo fixo da série ("XC60 • 2/9"), em edit-data.json `seriesBadge`.
type SeriesBadge = {text: string; index: string; start?: number; end?: number; accent?: string};

export const CustomGraphics: React.FC = () => {
  const d = editData as {
    splitInserts?: SplitInsert[];
    transitions?: CutFlash[];
    scrims?: Scrim[];
    seriesBadge?: SeriesBadge;
  };
  const splits = d.splitInserts ?? [];
  const flashes = d.transitions ?? [];
  const scrims = d.scrims ?? [];
  return (
    <>
      {scrims.map((s, i) => (
        <TopScrim key={`scrim${i}`} {...s} />
      ))}
      {splits.length ? <SplitScreen items={splits} /> : null}
      {flashes.length ? <CutSfx items={flashes} /> : null}
      {flashes.length ? <CutFlashes items={flashes} /> : null}
      {d.seriesBadge ? <SeriesBadgeView {...d.seriesBadge} /> : null}
      {/* cenas sob medida: src/scenes/<Nome>.tsx + src/kit (references/scenes.md) */}
    </>
  );
};

const TopScrim: React.FC<Scrim> = ({start, end, opacity = 0.55, height = 0.42}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const a = interpolate(t, [start, start + 0.25, end - 0.35, end], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.37, 0, 0.63, 1),
  });
  if (a <= 0) return null;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          height: `${height * 100}%`,
          opacity: a * opacity,
          background:
            'linear-gradient(180deg, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.7) 45%, rgba(0,0,0,0) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};

const SeriesBadgeView: React.FC<SeriesBadge> = ({text, index, start = 0, end, accent = '#ff5200'}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const stop = end ?? durationInFrames / fps;
  // Some enquanto um insert em CARD ocupa o topo (mesma zona do selo). Lê os
  // inserts do edit-data — sem tempos duplicados aqui.
  const cards = ((editData as {inserts?: {start: number; end: number; fit?: string}[]}).inserts ?? []).filter(
    (it) => !it.fit || it.fit === 'card',
  );
  const hide = cards.reduce(
    (m, it) =>
      Math.max(
        m,
        interpolate(t, [it.start - 0.25, it.start, it.end, it.end + 0.25], [0, 1, 1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
      ),
    0,
  );
  const a =
    interpolate(t, [start, start + 0.4, stop - 0.3, stop], [0, 1, 1, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }) *
    (1 - hide);
  const slide = interpolate(t, [start, start + 0.5], [-24, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  if (a <= 0) return null;
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: 56,
          top: 168,
          transform: `translateX(${slide}px)`,
          opacity: a,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '12px 22px 12px 18px',
          borderRadius: 999,
          background: 'rgba(14,14,16,0.62)',
          border: '1px solid rgba(255,255,255,0.14)',
          backdropFilter: 'blur(10px)',
          fontFamily,
          color: '#fff',
          fontSize: 30,
          letterSpacing: '0.04em',
        }}
      >
        <div style={{width: 12, height: 12, borderRadius: 6, background: accent, boxShadow: `0 0 14px ${accent}`}} />
        <span style={{fontWeight: 600}}>{text}</span>
        <span style={{fontWeight: 400, opacity: 0.7}}>{index}</span>
      </div>
    </AbsoluteFill>
  );
};

// ============ CUT FLASH =======================================================
// Starts BEFORE the cut and peaks on it. A transition that begins on the cut
// frame reads as a flash after the fact; leading it by two frames makes the
// light look like the thing that caused the change.
// `at` is the cut time exactly as segments.json states it — VIDEO_LAG lines it
// up with the frame the picture actually changes on, same as the split windows.
const FLASH_LEAD = 2; // frames before the cut
const FLASH_LEN = 7; // total, ~230ms at 30fps
/**
 * Volume do clique de emenda. Era 0.9 — quase o teto, para um som que deve ser
 * SENTIDO e não ouvido. O próprio cabeçalho do Main pede camadas baixas
 * (whoosh ~0.09, pop ~0.12); um clique a 0.9 sobre voz normalizada não esconde
 * o corte, disputa com ele.
 *
 * 0.22 fica acima do whoosh (o clique precisa marcar o instante) e bem abaixo
 * da fala, que é a camada que manda.
 */
const CLICK_VOL = 0.22;

/**
 * O clique de TODA emenda, inclusive as que não têm overlay visual.
 *
 * `isOverlayCut` existe para impedir que um flash seja pintado por cima do
 * shader — problema de imagem. Mas ele filtrava a lista inteira, e junto foi o
 * ÁUDIO: os cortes `displace`/`refract` ficavam mudos. Medido neste vídeo, eram
 * as 3 emendas cobertas por B-roll — justamente as mais expostas, porque a
 * troca de imagem chama atenção para o ponto.
 *
 * A regra de montagem é que o clique curto na emenda a esconde melhor que
 * qualquer transição visual: o ouvido aceita o corte que o olho notaria. Por
 * isso o som é montado a partir da lista COMPLETA, e só o overlay é filtrado.
 */
const CutSfx: React.FC<{items: CutFlash[]}> = ({items}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {items.map((it, i) => {
        const c = Math.round(it.at * fps) + VIDEO_LAG;
        return (
          <Sequence key={i} from={c} durationInFrames={10} layout="none">
            <Sfx src={it.sfx ?? 'cut-click.mp3'} volume={it.volume ?? CLICK_VOL} />
          </Sequence>
        );
      })}
    </>
  );
};

const CutFlashes: React.FC<{items: CutFlash[]}> = ({items}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const active = items.filter(isOverlayCut).find((it) => {
    const c = Math.round(it.at * fps) + VIDEO_LAG;
    return frame >= c - FLASH_LEAD && frame < c - FLASH_LEAD + FLASH_LEN;
  });
  if (!active) return null;

  // O som é montado por <CutSfx> sobre a lista COMPLETA de emendas; este
  // componente cuida só do overlay visual. Manter o Sfx nos dois lugares
  // tocaria o clique duas vezes na mesma emenda.
  const c = Math.round(active.at * fps) + VIDEO_LAG;

  switch (active.type) {
    case 'whip-pan':
      return <WhipPan c={c} frame={frame} intensity={active.intensity ?? 1} />;
    case 'glitch':
      return <Glitch c={c} frame={frame} intensity={active.intensity ?? 1} />;
    default:
      return <Flash c={c} frame={frame} intensity={active.intensity ?? 1} />;
  }
};

// ---- flash (original) ------------------------------------------------------
const Flash: React.FC<{c: number; frame: number; intensity: number}> = ({
  c,
  frame,
  intensity: k,
}) => {
  const {width} = useVideoConfig();
  const p = (frame - (c - FLASH_LEAD)) / (FLASH_LEN - 1); // 0..1 pela janela

  // beam sweeps left→right, brightest as it crosses centre
  const x = interpolate(p, [0, 1], [-1.35 * width, 1.35 * width]);
  const beam = interpolate(p, [0, 0.35, 1], [0, 1 * k, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // the bloom is short and lands ON the cut, not spread across the window
  const bloom = interpolate(frame, [c - 1, c, c + 2], [0, 0.5 * k, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill style={{backgroundColor: '#fff', opacity: bloom, mixBlendMode: 'screen'}} />
      <AbsoluteFill style={{overflow: 'hidden'}}>
        <div
          style={{
            position: 'absolute',
            top: '-30%',
            left: 0,
            width: width * 0.46,
            height: '160%',
            transform: `translateX(${x.toFixed(1)}px) rotate(-18deg)`,
            background:
              'linear-gradient(90deg,rgba(255,255,255,0) 0%,rgba(255,255,255,0.95) 50%,rgba(255,255,255,0) 100%)',
            opacity: beam,
            mixBlendMode: 'screen',
            filter: 'blur(16px)',
          }}
        />
      </AbsoluteFill>
          </AbsoluteFill>
  );
};

// ---- whip-pan ---------------------------------------------------------------
// CustomGraphics is mounted as an overlay ABOVE the video layer (see Main.tsx
// — it has no access to the OffthreadVideo underneath to blur or shift it
// directly), same constraint the original flash already works within. So
// this reads as a whip-pan through streak lines that sweep across the WHOLE
// frame in one direction (denser and faster than the flash's single beam)
// plus a brief white-out at the peak, rather than actually motion-blurring
// pixels that aren't reachable from here.
const WhipPan: React.FC<{c: number; frame: number; intensity: number}> = ({
  c,
  frame,
  intensity: k,
}) => {
  const {width} = useVideoConfig();
  const p = interpolate(frame, [c - FLASH_LEAD, c, c - FLASH_LEAD + FLASH_LEN], [0, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const whiteout = interpolate(frame, [c - 1, c, c + 1], [0, 0.35 * k, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const streakOpacity = 0.85 * k * p;
  const baseX = interpolate(p, [0, 1], [-0.2 * width, 1.2 * width]);

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill style={{backgroundColor: '#fff', opacity: whiteout, mixBlendMode: 'screen'}} />
      <AbsoluteFill style={{overflow: 'hidden', opacity: streakOpacity, mixBlendMode: 'screen'}}>
        {[0.12, 0.3, 0.5, 0.7, 0.88].map((yFrac, i) => {
          const lag = (i - 2) * 0.06; // stagger each line's position slightly
          const x = baseX + lag * width;
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                top: `${yFrac * 100}%`,
                left: 0,
                width: width * 0.9,
                height: 4 + (i % 3),
                transform: `translateX(${x.toFixed(1)}px) skewX(-12deg)`,
                background:
                  'linear-gradient(90deg,rgba(255,255,255,0) 0%,rgba(255,255,255,0.95) 45%,rgba(255,255,255,0) 100%)',
                filter: 'blur(3px)',
              }}
            />
          );
        })}
      </AbsoluteFill>
          </AbsoluteFill>
  );
};

// ---- glitch -----------------------------------------------------------------
// The "digital hiccup" cut: colored slice-bands flicker across the frame with
// a small horizontal jitter. Like WhipPan, this is an overlay-only take on
// the idea (CustomGraphics has no handle on the video layer beneath it to
// RGB-split or displace directly — see the WhipPan comment above for why).
// Cyan/magenta bands standing in for a channel split read as "glitch" at a
// glance without needing pixels from the layer underneath.
// HyperFrames' original (packages/shader-transitions) is a WebGL shader pass;
// this is built from scratch for what a Chromium/CSS render context gives.
const Glitch: React.FC<{c: number; frame: number; intensity: number}> = ({
  c,
  frame,
  intensity: k,
}) => {
  const p = interpolate(frame, [c - FLASH_LEAD, c, c - FLASH_LEAD + FLASH_LEN], [0, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (p <= 0.01) return null;

  const shift = 14 * k * p;
  // a few deterministic "sliced" bands (frame-seeded, not random — renders
  // identically every time, which a still-frame diff test depends on)
  const seed = Math.round(c);
  const bands = [0, 1, 2, 3].map((i) => {
    const top = ((seed * 37 + i * 53) % 85) + 3; // 3-88%
    const h = 4 + ((seed * 13 + i * 29) % 8); // 4-12%
    const dx = (i % 2 === 0 ? 1 : -1) * shift * (1 + i * 0.35);
    const color = i % 2 === 0 ? 'rgba(0,255,255,0.55)' : 'rgba(255,0,180,0.55)'; // cyan / magenta
    return {top, h, dx, color};
  });

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {bands.map((b, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: `${b.top}%`,
            left: 0,
            width: '100%',
            height: `${b.h}%`,
            transform: `translateX(${b.dx.toFixed(1)}px)`,
            backgroundColor: b.color,
            mixBlendMode: 'screen',
            opacity: p,
          }}
        />
      ))}
          </AbsoluteFill>
  );
};

// ============ SPLIT SCREEN ("tela dividida") ==================================
// Art on top, the talking head re-drawn underneath, seam at the subject's hairline.
//
// ONE always-mounted layer, NOT a <Sequence> per window. The obvious version wraps
// each window in <Sequence from> + <OffthreadVideo startFrom>, and that samples
// cut.mp4 ONE FRAME BEHIND the base video: on the first frame of the split you
// still see the previous take, so the layout appears to change before the picture
// does. Mounted flat with no startFrom, this layer decodes the same frame the base
// layer does, and the window edges land exactly on the cut.
const SplitFrame: React.FC<{
  image: string;
  bandH: number;
  fit: 'cover' | 'contain';
  progress: number;
  layout: 'top' | 'bottom';
}> = ({image, bandH, fit, progress, layout}) => {
  // slow Ken-Burns so the band is not a dead still
  const artScale = 1 + 0.03 * progress;
  const {zoom, focusY} = LAYOUT[layout];
  const videoH = 1920 - bandH;
  const bandTop = layout === 'top' ? 0 : videoH;
  const videoTop = layout === 'top' ? bandH : 0;

  return (
    <AbsoluteFill style={{backgroundColor: '#0a0a0c'}}>
      <div style={{position: 'absolute', left: 0, top: videoTop, width: 1080, height: videoH, overflow: 'hidden'}}>
        <OffthreadVideo
          src={staticFile('cut.mp4')}
          muted
          style={{
            position: 'absolute',
            width: 1080 * zoom,
            height: 1920 * zoom,
            left: -(1080 * (zoom - 1)) / 2,
            top: -focusY * zoom,
          }}
        />
      </div>

      <div style={{position: 'absolute', left: 0, top: bandTop, width: 1080, height: bandH, overflow: 'hidden'}}>
        <Img
          src={staticFile(image)}
          style={{width: '100%', height: '100%', objectFit: fit, scale: String(artScale)}}
        />
        {/* Soft falloff into the seam — 'top' ONLY. There the caption sits ON the
            seam over the art and needs the darkening to stay legible. On
            'bottom' the caption sits above the seam over the video, so the same
            gradient only smears grey across the top of the photo. */}
        {layout === 'top' ? (
          <div
            style={{
              position: 'absolute',
              left: 0,
              bottom: 0,
              width: '100%',
              height: 110,
              background: 'linear-gradient(180deg,rgba(10,10,12,0),rgba(10,10,12,0.75))',
            }}
          />
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// OffthreadVideo draws the source frame at or before frame/fps; on an exact frame
// boundary that lands one frame LATE, so the decoded picture changes one
// composition frame after the index says it should. Measured, not guessed: with
// the split disabled, the camera zoom (index-driven) steps at frame 350 while the
// take itself changes at 351. Delay the layout by the same frame or the split
// visibly precedes the cut.
export const VIDEO_LAG = 1;

export const SplitScreen: React.FC<{items: SplitInsert[]}> = ({items}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  // frame-indexed, not seconds: the window edges ARE cut frames
  const active = items.find((it) => {
    const a = Math.round(it.start * fps) + VIDEO_LAG;
    const b = Math.round(it.end * fps) + VIDEO_LAG;
    return frame >= a && frame < b;
  });
  if (!active) return null;
  const a = Math.round(active.start * fps) + VIDEO_LAG;
  const b = Math.round(active.end * fps) + VIDEO_LAG;
  return (
    <SplitFrame
      image={active.src}
      bandH={active.bandH ?? 750}
      fit={active.fit ?? 'cover'}
      layout={active.layout ?? 'top'}
      progress={clamp((frame - a) / Math.max(1, b - a), 0, 1)}
    />
  );
};

// ============ WORKED EXAMPLE 1: editing timeline being cut + caption tracks =====
// For "os cortes, as legendas e as animações" — a mini editor UI: playhead
// sweeps and splits the video track, caption chips pop in, shapes pop last.
const TL_W = 800;
const TL_H = 378;
const PAD = 46;
const INNER = TL_W - PAD * 2;

const TimelineInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(appear, [0, 1], [26, 0]);

  // playhead sweeps, bar splits into 3
  const gap = interpolate(f, [6, 16], [0, 16], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pieceW = (INNER - gap * 2) / 3;
  const playX = interpolate(f, [0, 16], [0, INNER], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const playOp = interpolate(f, [0, 2, 15, 19], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: TL_W, height: TL_H, marginTop: 105, borderRadius: 28, background: '#15171c', border: '1px solid #262a31', boxShadow: '0 18px 50px rgba(0,0,0,0.5)', opacity: appear * exit, scale: String(interpolate(appear, [0, 1], [0.93, 1])), translate: `0px ${rise}px`, padding: PAD, boxSizing: 'border-box', position: 'relative', fontFamily}}>
        {/* window dots */}
        <div style={{display: 'flex', gap: 12}}>
          {['#ff5f57', '#febc2e', '#28c840'].map((c) => (<div key={c} style={{width: 16, height: 16, borderRadius: 999, background: c}} />))}
        </div>

        {/* VIDEO track — being cut */}
        <div style={{position: 'absolute', left: PAD, top: 92, width: INNER, height: 62}}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{position: 'absolute', left: i * (pieceW + gap), width: pieceW, height: 62, borderRadius: 10, background: 'linear-gradient(180deg,#5b8dff,#3f6fe0)', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)'}} />
          ))}
          <div style={{position: 'absolute', left: playX, top: -8, width: 3, height: 78, background: 'white', opacity: playOp, boxShadow: '0 0 8px rgba(255,255,255,0.8)'}} />
        </div>

        {/* LEGENDAS track — caption chips appear */}
        <div style={{position: 'absolute', left: PAD, top: 188, width: INNER, height: 46}}>
          {[0, 1, 2, 3].map((k) => {
            const ap = interpolate(f, [16 + k * 5, 24 + k * 5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.5))});
            return (
              <div key={k} style={{position: 'absolute', left: k * (INNER / 4), width: INNER / 4 - 14, height: 46, borderRadius: 9, background: '#33e0a3', opacity: Math.min(1, ap), scale: String(Math.max(0.01, ap)), display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6, padding: '0 12px', boxSizing: 'border-box'}}>
                <div style={{height: 6, width: '80%', borderRadius: 4, background: 'rgba(0,0,0,0.55)'}} />
                <div style={{height: 6, width: '55%', borderRadius: 4, background: 'rgba(0,0,0,0.4)'}} />
              </div>
            );
          })}
        </div>

        {/* ANIMAÇÕES track — shapes pop */}
        <div style={{position: 'absolute', left: PAD, top: 270, width: INNER, height: 60, display: 'flex', gap: 20, alignItems: 'center'}}>
          {[0, 1, 2, 3].map((k) => {
            const ap = interpolate(f, [34 + k * 4, 42 + k * 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.8))});
            const rot = Math.sin((f + k * 7) * 0.2) * 20;
            const colors = ['#ffffff', '#ffd23f', '#ff5f9e', '#5b8dff'];
            const rounds = [999, 12, 6, 999];
            return (<div key={k} style={{width: 52, height: 52, background: colors[k], borderRadius: rounds[k], opacity: Math.min(1, ap), scale: String(Math.max(0.01, ap)), rotate: `${rot}deg`}} />);
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const TimelineGraphic: React.FC<{startSec: number; endSec: number}> = ({startSec, endSec}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <TimelineInner totalFrames={duration} />
    </Sequence>
  );
};

// ============ WORKED EXAMPLE 2: script sheet with typewriter text ===============
// For "ela leu o roteiro" — a tilted paper card, lines typing in with a cursor.
const ScriptInner: React.FC<{totalFrames: number; lines: string[]}> = ({totalFrames, lines}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cps = 1.7; // chars per frame

  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: 640, height: 420, marginTop: 100, borderRadius: 16, background: '#f4f1e8', boxShadow: '0 22px 55px rgba(0,0,0,0.5)', opacity: appear * exit, scale: String(interpolate(appear, [0, 1], [0.94, 1])), rotate: '-2deg', translate: `0px ${interpolate(appear, [0, 1], [26, 0])}px`, padding: 46, boxSizing: 'border-box', fontFamily}}>
        <div style={{fontWeight: 900, fontSize: 26, letterSpacing: 3, color: '#c2492b'}}>ROTEIRO</div>
        <div style={{height: 4, width: 90, background: '#c2492b', borderRadius: 3, marginTop: 10, marginBottom: 30}} />
        {lines.map((line, i) => {
          const startLocal = 10 + i * 12;
          const shown = clamp(Math.floor((f - startLocal) * cps), 0, line.length);
          const isTyping = shown > 0 && shown < line.length;
          const cursor = isTyping && Math.floor(f / 6) % 2 === 0 ? '|' : '';
          return (
            <div key={i} style={{fontWeight: 400, fontSize: 32, color: '#2b2b2b', lineHeight: 1.5, minHeight: 40}}>
              {line.slice(0, shown)}
              <span style={{color: '#c2492b'}}>{cursor}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const ScriptGraphic: React.FC<{startSec: number; endSec: number; lines: string[]}> = ({startSec, endSec, lines}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <ScriptInner totalFrames={duration} lines={lines} />
    </Sequence>
  );
};

// ============ WORKED EXAMPLE 3: playful shapes pop (for "animações") ============
const Shape: React.FC<{i: number; color: string; round: number}> = ({i, color, round}) => {
  const frame = useCurrentFrame();
  const appear = interpolate(frame, [i * 3, i * 3 + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.6))});
  const pulse = 1 + 0.16 * Math.sin((frame + i * 6) * 0.28);
  const rot = Math.sin((frame + i * 8) * 0.12) * 22;
  return (
    <div
      style={{
        width: 92,
        height: 92,
        background: color,
        borderRadius: round,
        opacity: appear,
        scale: String(appear * pulse),
        rotate: `${rot}deg`,
        boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
      }}
    />
  );
};

const ShapesInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(frame, [0, 8], [24, 0], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="pop.mp3" volume={0.12} />
      <div style={{marginTop: 210, display: 'flex', gap: 34, opacity: exit, translate: `0px ${rise}px`}}>
        <Shape i={0} color="white" round={46} />
        <Shape i={1} color="#33e0a3" round={20} />
        <Shape i={2} color="white" round={8} />
      </div>
    </AbsoluteFill>
  );
};

export const ShapesGraphic: React.FC<{startSec: number; endSec: number}> = ({startSec, endSec}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <ShapesInner totalFrames={duration} />
    </Sequence>
  );
};
