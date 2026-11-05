/**
 * SimpleCaptions (16:9) — the three STATIC caption styles, landscape layout.
 *
 *   "simples"  Poppins semibold, off-white, ONE line
 *   "serifada" the same rules in a classic serif (Libre Baskerville)
 *   "classica" classic subtitle: small sans (Inter), TWO lines
 *
 * Same behaviour as shortform/src/SimpleCaptions.tsx (no animation; a cue
 * replaces the previous one on the frame its first word starts; lines grouped
 * by MEASURED WIDTH), but every dimension is a ratio of the frame, so it scales
 * from 1920x1080 to 3840x2160 untouched:
 *   size = fraction of height     bottom = fraction of height
 *   maxW = fraction of width (per line)
 *
 * Data: public/captions.json (word level). Optional captions.maxWords /
 * captions.fontScale from edit-data.json.
 */
import {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadBaskerville} from '@remotion/google-fonts/LibreBaskerville';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import editData from '../public/edit-data.json';

const POPPINS = loadPoppins('normal', {weights: ['600']}).fontFamily;
const BASKERVILLE = loadBaskerville('normal', {weights: ['700']}).fontFamily;
const INTER = loadInter('normal', {weights: ['500']}).fontFamily;

const OFFWHITE = '#f4f1e9';

type Word = {text: string; startMs: number; endMs: number};
type Variant = {
  family: string;
  weight: number;
  size: number; // fraction of frame height
  maxWords: number;
  lines: 1 | 2;
  tracking: number; // em
  bottom: number; // fraction of frame height
  maxW: number; // fraction of frame width, per line
};

const C = ((editData as any).captions ?? {}) as {maxWords?: number; fontScale?: number};
export const SIMPLE_VARIANTS: Record<string, Variant> = {
  simples: {family: POPPINS, weight: 600, size: 0.06, maxWords: 6, lines: 1, tracking: -0.02, bottom: 0.1, maxW: 0.7},
  serifada: {family: BASKERVILLE, weight: 700, size: 0.06, maxWords: 6, lines: 1, tracking: -0.01, bottom: 0.1, maxW: 0.7},
  classica: {family: INTER, weight: 500, size: 0.05, maxWords: 14, lines: 2, tracking: 0, bottom: 0.1, maxW: 0.5},
};

const clean = (t: string) => t.replace(/[.,!?…]+$/, '');
const isBreak = (t: string) => /[.,!?…]$/.test(t);

type Metrics = {V: Variant; px: number; maxPx: number; maxWords: number};

const widthOf = (words: Word[], M: Metrics) =>
  measureText({
    text: words.map((w) => clean(w.text)).join(' '),
    fontFamily: M.V.family,
    fontSize: M.px,
    fontWeight: M.V.weight,
    letterSpacing: `${M.V.tracking * M.px}px`,
  }).width;

function buildCues(words: Word[], M: Metrics): Word[][] {
  const budget = M.maxPx * M.V.lines;
  const cues: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    const trial = [...cur, w];
    if (cur.length && (trial.length > M.maxWords || widthOf(trial, M) > budget)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
    const next = words[i + 1];
    const gap = next ? next.startMs - w.endMs : 0;
    if (cur.length && (isBreak(w.text) || gap > 450)) {
      cues.push(cur);
      cur = [];
    }
  });
  if (cur.length) cues.push(cur);
  return cues;
}

// Two-line split: closest widths, but never ending a line on a short function word.
const ORPHAN = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

function splitTwo(words: Word[], M: Metrics): Word[][] {
  if (M.V.lines === 1 || words.length < 2) return [words];
  let best = 0;
  let bestScore = Infinity;
  for (let i = 1; i < words.length; i++) {
    const diff = Math.abs(widthOf(words.slice(0, i), M) - widthOf(words.slice(i), M));
    const score = diff + (ORPHAN.test(clean(words[i - 1].text)) ? M.px * 3 : 0);
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return [words.slice(0, best), words.slice(best)];
}

// Guard: a captions.json with the wrong shape must not take the whole render down.
const CAPS: Word[] = Array.isArray(captions) ? (captions as Word[]) : [];

export const SimpleCaptions: React.FC<{variant: string}> = ({variant}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const V = SIMPLE_VARIANTS[variant] ?? SIMPLE_VARIANTS.simples;
  const px = height * V.size * (C.fontScale ?? 1);
  const M: Metrics = {V, px, maxPx: width * V.maxW, maxWords: C.maxWords ?? V.maxWords};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const cues = useMemo(() => buildCues(CAPS, M), [variant, px, width, M.maxWords]);

  let idx = -1;
  for (let i = 0; i < cues.length; i++) {
    if (frame >= Math.round((cues[i][0].startMs / 1000) * fps)) idx = i;
  }
  if (idx < 0) return null;
  const next = cues[idx + 1];
  const end = next
    ? Math.round((next[0].startMs / 1000) * fps)
    : Math.min(durationInFrames, Math.round((cues[idx][cues[idx].length - 1].endMs / 1000) * fps) + fps);
  if (frame >= end) return null;

  const lines = splitTwo(cues[idx], M);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: height * V.bottom}}>
      <div
        style={{
          textAlign: 'center',
          fontFamily: V.family,
          fontWeight: V.weight,
          fontSize: px,
          letterSpacing: V.tracking * px,
          lineHeight: 1.18,
          color: OFFWHITE,
          whiteSpace: 'pre',
          textShadow: `0 ${px * 0.05}px ${px * 0.22}px rgba(0,0,0,0.6), 0 0 ${px * 0.08}px rgba(0,0,0,0.45)`,
        }}
      >
        {lines.map((ln, i) => (
          <div key={i}>{ln.map((w) => clean(w.text)).join(' ')}</div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
