/**
 * Hook / headline (16:9) — static two-line headline in the first seconds.
 * Landscape port of the HookInner layer in shortform/src/Main.tsx: same styles
 * (outline | card | realce | misto), same copy rules (`hook.text` is re-broken
 * into exactly TWO balanced lines by measured width; size fitted to them), same
 * edit-data keys. `hook.enabled:false` (or no `hook`) = no headline.
 *
 * What changes is the LAYOUT. Nothing here is portrait pixels:
 *   size    capped at ~8–10% of the frame HEIGHT, fitted so the widest line is
 *           <= 50% of the frame WIDTH (a wide frame must not be spanned edge to
 *           edge — it would sit on the speaker)
 *   anchor  top-left by default (`hook.side`: "left" | "center" | "right"), 7%
 *           from the top, 4% from the side: the speaker usually stands centre-right
 *   so 1080p and 4K render the same picture.
 * Optional overrides keep the shortform key names but are read at a 1080-high
 * basis (px × height/1080; safeWidth px × width/1920): fontSizePx / maxFontPx,
 * safeWidth, strokePx, paddingTop, lineHeight. Plus `accent` (default edit-data
 * `accent`) for realce/misto, `logo` / `sign` for card.
 */
import {AbsoluteFill, Audio, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {measureText} from '@remotion/layout-utils';
import editData from '../public/edit-data.json';

const {fontFamily} = loadFont('normal', {weights: ['400', '800', '900']});

export type HookSpec = {
  enabled: boolean;
  endSec?: number;
  text?: string;
  lines?: string[];
  style?: 'outline' | 'card' | 'realce' | 'misto';
  side?: 'left' | 'center' | 'right';
  accent?: string;
  logo?: string | null;
  sign?: string | null;
  fontSizePx?: number;
  maxFontPx?: number;
  safeWidth?: number;
  strokePx?: number;
  paddingTop?: number;
  lineHeight?: number;
};

const D = editData as unknown as {hook?: HookSpec; accent?: string};
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// cap = fraction of height; lh = line height; top = fraction of height
type HlStyle = {weights: [number, number]; cap: number; lh: number; top: number};
const HL_STYLES: Record<string, HlStyle> = {
  outline: {weights: [800, 800], cap: 0.095, lh: 1.02, top: 0.07},
  card: {weights: [900, 900], cap: 0.08, lh: 1.06, top: 0.06},
  realce: {weights: [900, 900], cap: 0.085, lh: 1.04, top: 0.07},
  misto: {weights: [400, 900], cap: 0.1, lh: 0.98, top: 0.07},
};
const SAFE_W = 0.5; // of frame width — widest line
const MARGIN_X = 0.04; // of frame width

const hlWidth = (text: string, size: number, weight: number) =>
  text ? measureText({text, fontFamily, fontSize: size, fontWeight: weight, letterSpacing: `${-size * 0.01}px`}).width : 0;

// Balance by MEASURED width, not word count.
function twoLines(text: string, weights: [number, number]): [string, string] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] ?? '', ''];
  let best: [string, string] = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) {
      bestDiff = d;
      best = [a, b];
    }
  }
  return best;
}

function fitHeadline(lines: [string, string], w: [number, number], safeW: number, cap: number, min: number): number {
  const widest = (size: number) => Math.max(hlWidth(lines[0], size, w[0]), hlWidth(lines[1], size, w[1]));
  let size = Math.floor((safeW / Math.max(1, widest(100))) * 100);
  size = clamp(Math.floor((safeW / Math.max(1, widest(size))) * size), min, cap);
  return size;
}

const HookInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const H = D.hook as HookSpec;
  const k = height / 1080;
  const enter = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 9, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [24 * k, 0]);

  const styleId = H.style ?? 'outline';
  const S = HL_STYLES[styleId] ?? HL_STYLES.outline;
  const accent = H.accent ?? D.accent ?? '#ff5200';
  const raw = (H.text ?? (H.lines || []).join(' ')).trim();
  const lines = twoLines(styleId === 'card' ? raw.toUpperCase() : raw, S.weights);
  const cap = (H.fontSizePx ?? H.maxFontPx ?? 0) * k || S.cap * height;
  // `card` and `realce` add horizontal padding around the text — budget for it
  const pad = styleId === 'card' ? 0.92 : styleId === 'realce' ? 0.84 : 1;
  const safeW = (H.safeWidth ? H.safeWidth * (width / 1920) : width * SAFE_W) * pad;
  const size = fitHeadline(lines, S.weights, safeW, cap, 40 * k);
  const lh = H.lineHeight ?? S.lh;
  const top = H.paddingTop != null ? H.paddingTop * k : S.top * height;
  const side = H.side ?? 'left';
  const align = side === 'left' ? 'flex-start' : side === 'right' ? 'flex-end' : 'center';
  const textAlign = side === 'center' ? 'center' : side;
  const frame: React.CSSProperties = {
    justifyContent: 'flex-start',
    alignItems: align,
    paddingTop: top,
    paddingLeft: width * MARGIN_X,
    paddingRight: width * MARGIN_X,
  };
  const shell: React.CSSProperties = {
    opacity: op,
    translate: `0px ${y}px`,
    textAlign,
    fontFamily,
    lineHeight: lh,
    letterSpacing: -size * 0.01,
    // the two-line promise is structural: a bad fit overflows visibly instead of wrapping
    whiteSpace: 'nowrap',
  };
  const whoosh = <Audio src={staticFile('sfx/whoosh.mp3')} volume={0.1} />;

  if (styleId === 'realce') {
    return (
      <AbsoluteFill style={frame}>
        {whoosh}
        <div style={{...shell, display: 'flex', flexDirection: 'column', alignItems: align, gap: 10 * k}}>
          {lines.filter(Boolean).map((l, i) => (
            <div key={i} style={{background: accent, color: '#fff', fontWeight: 900, fontSize: size, padding: '0.08em 0.3em 0.16em', borderRadius: 12 * k, boxShadow: `0 ${10 * k}px ${28 * k}px rgba(0,0,0,0.45)`}}>
              {l}
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  if (styleId === 'misto') {
    return (
      <AbsoluteFill style={frame}>
        {whoosh}
        <div style={{...shell, filter: `drop-shadow(0 ${6 * k}px ${16 * k}px rgba(0,0,0,0.55))`}}>
          <div style={{fontWeight: 400, fontSize: size, color: '#fff'}}>{lines[0]}</div>
          <div style={{fontWeight: 900, fontSize: size, color: accent}}>{lines[1]}</div>
        </div>
      </AbsoluteFill>
    );
  }

  if (styleId === 'card') {
    return (
      <AbsoluteFill style={frame}>
        {whoosh}
        <div style={{opacity: op, translate: `0px ${y}px`, display: 'flex', flexDirection: 'column', alignItems: align, gap: 22 * k}}>
          {H.logo || H.sign ? (
            <div style={{display: 'flex', alignItems: 'center', gap: 26 * k}}>
              {H.logo ? <Img src={staticFile(H.logo)} style={{width: 240 * k, borderRadius: 14 * k, boxShadow: `0 ${12 * k}px ${34 * k}px rgba(0,0,0,0.4)`}} /> : null}
              {H.sign ? <Img src={staticFile(H.sign)} style={{width: 100 * k, filter: `drop-shadow(0 ${8 * k}px ${20 * k}px rgba(0,0,0,0.45))`}} /> : null}
            </div>
          ) : null}
          <div style={{background: '#232326', borderRadius: 22 * k, padding: `${24 * k}px ${40 * k}px`, textAlign, fontFamily, fontWeight: 900, fontSize: size, color: '#fff', lineHeight: lh, letterSpacing: -size * 0.01, textShadow: `0 ${4 * k}px ${20 * k}px rgba(0,0,0,0.55)`, boxShadow: `0 ${18 * k}px ${50 * k}px rgba(0,0,0,0.45)`}}>
            {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  const stroke = (H.strokePx ?? 12) * k * 0.75;
  return (
    <AbsoluteFill style={frame}>
      {whoosh}
      <div
        style={{
          ...shell,
          fontWeight: 800,
          fontSize: size,
          color: '#fff',
          WebkitTextStroke: `${stroke}px #000`,
          paintOrder: 'stroke fill',
          filter: `drop-shadow(0 ${6 * k}px ${14 * k}px rgba(0,0,0,0.45))`,
        }}
      >
        {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
      </div>
    </AbsoluteFill>
  );
};

export const HookIntro: React.FC = () => {
  const {fps} = useVideoConfig();
  const dur = Math.round((D.hook?.endSec ?? 4) * fps);
  return (
    <Sequence from={0} durationInFrames={dur} layout="none">
      <HookInner totalFrames={dur} />
    </Sequence>
  );
};
