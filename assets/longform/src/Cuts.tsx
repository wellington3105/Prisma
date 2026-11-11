/**
 * Cuts (16:9) — flash / whip-pan / glitch overlays + the click on every cut.
 *
 * Ported verbatim from shortform/src/CustomGraphics.tsx (same `transitions[]`
 * keys, same timing, same look: all measures are ratios of the frame width, so
 * they hold on a wide frame). `displace` / `refract` live in the same list but
 * are drawn by ShaderTransition.tsx — they are skipped here.
 *
 * In 16:9 the usual place for them is a B-ROLL CUTAWAY: either list the cuts in
 * `transitions[]` by hand, or set `broll[].flash` and Main.tsx adds one at the
 * cutaway's start and one at its end.
 */
import {AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type CutFlash = {
  at: number;
  type?: 'flash' | 'whip-pan' | 'glitch' | 'displace' | 'refract';
  intensity?: number;
  sfx?: string;
  volume?: number;
};

const OVERLAY_TYPES = ['flash', 'whip-pan', 'glitch'];
const isOverlayCut = (t: CutFlash) => OVERLAY_TYPES.includes(t.type ?? 'flash');
// OffthreadVideo draws one frame late; same compensation as shortform.
const VIDEO_LAG = 1;

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
export const CutSfx: React.FC<{items: CutFlash[]}> = ({items}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {items.map((it, i) => {
        const c = Math.round(it.at * fps) + VIDEO_LAG;
        return (
          <Sequence key={i} from={c} durationInFrames={10} layout="none">
            <Audio src={staticFile(`sfx/${it.sfx ?? 'cut-click.mp3'}`)} volume={it.volume ?? CLICK_VOL} />
          </Sequence>
        );
      })}
    </>
  );
};

export const CutFlashes: React.FC<{items: CutFlash[]}> = ({items}) => {
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

