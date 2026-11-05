/**
 * Captions (16:9) — KARAOKE style, landscape layout.
 *
 * Ported from shortform's Karaoke, but nothing here is portrait pixels: every
 * size and position is a RATIO of useVideoConfig() width/height, so the same
 * edit-data renders identically at 1920x1080 and 3840x2160.
 *
 *   font size   5.8% of height (~62px @1080p)   x captions.fontScale
 *   baseline    10% of height from the bottom   (~108px @1080p)
 *   line width  70% of frame width max; wider lines are scaled down to fit
 *   grouping    up to captions.maxWords (default 6) words per line, ended early
 *               by punctuation, a speech gap, or the width budget
 *
 * Data: public/captions.json (word level, helpers/captions_for_remotion.py).
 * The static styles (simples / serifada / classica) live in SimpleCaptions.tsx.
 */
import {useMemo} from 'react';
import {AbsoluteFill, Easing, Sequence, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import editData from '../public/edit-data.json';

const {fontFamily} = loadFont('normal', {weights: ['900']});

type Caption = {text: string; startMs: number; endMs: number};

const C = ((editData as any).captions ?? {}) as {
  maxWords?: number;
  fontScale?: number;
  highlight?: string; // optional colour for the word being spoken
};
// Guard: a captions.json with the wrong shape must not take the whole render down.
const WORDS: Caption[] = Array.isArray(captions) ? (captions as Caption[]) : [];

const SIZE = 0.058; // of height
const BOTTOM = 0.1; // of height
const MAX_W = 0.7; // of width

const cleanW = (t: string) => t.replace(/[.,!?…]+$/, '');
const isBreak = (t: string) => /[.,!?…]$/.test(t);

const widthOf = (ws: Caption[], size: number) =>
  measureText({
    text: ws.map((w) => cleanW(w.text)).join(' '),
    fontFamily,
    fontSize: size,
    fontWeight: 900,
    letterSpacing: `${-size * 0.016}px`,
  }).width;

// Group by word count, punctuation, speech gap and measured width.
function buildLines(caps: Caption[], maxWords: number, size: number, budget: number): Caption[][] {
  const lines: Caption[][] = [];
  let cur: Caption[] = [];
  caps.forEach((w, i) => {
    if (cur.length && (cur.length >= maxWords || widthOf([...cur, w], size) > budget)) {
      lines.push(cur);
      cur = [];
    }
    cur.push(w);
    const next = caps[i + 1];
    if (isBreak(w.text) || (next && next.startMs - w.endMs > 450)) {
      lines.push(cur);
      cur = [];
    }
  });
  if (cur.length) lines.push(cur);
  return lines;
}

const SLIDE_FRAMES = 15; // ~0.5s at 30fps
const slideEase = Easing.bezier(0.25, 1, 0.5, 1); // power3.out

// The visible group (words 0..k) must always be centred. The container is laid
// out with the WHOLE line centred, so the group is shifted by (full - visible)/2.
// Each new word starts a slide from the CURRENT interpolated position (no snap).
function shiftAt(frame: number, starts: number[], targets: number[]): number {
  let from = targets[0];
  let to = targets[0];
  let t0 = 0;
  const pos = (t: number) => from + (to - from) * slideEase(Math.min(1, Math.max(0, (t - t0) / SLIDE_FRAMES)));
  for (let j = 1; j < starts.length; j++) {
    if (frame < starts[j]) break;
    const cur = pos(starts[j]);
    from = cur;
    to = targets[j];
    t0 = starts[j];
  }
  return pos(frame);
}

const WordEl: React.FC<{caption: Caption; lineFromFrame: number; size: number; last: boolean}> = ({caption, lineFromFrame, size, last}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const startLocal = (caption.startMs / 1000) * fps - lineFromFrame;
  const endLocal = (caption.endMs / 1000) * fps - lineFromFrame;
  const p = interpolate(frame, [startLocal, startLocal + 7], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  const active = Boolean(C.highlight) && frame >= startLocal && frame < endLocal;
  return (
    <span
      style={{
        display: 'inline-block',
        opacity: p,
        translate: `0px ${interpolate(p, [0, 1], [size * 0.5, 0])}px`,
        marginRight: last ? 0 : size * 0.28,
        color: active ? C.highlight : 'white',
      }}
    >
      {cleanW(caption.text)}
    </span>
  );
};

const LineEl: React.FC<{line: Caption[]; from: number; size: number; budget: number}> = ({line, from, size, budget}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const gap = size * 0.28;
  const widths = line.map((w) => widthOf([w], size));
  const full = widths.reduce((a, b) => a + b, 0) + gap * (line.length - 1);
  const fit = Math.min(1, budget / full);
  let acc = 0;
  const targets = widths.map((w, j) => {
    acc += w + (j ? gap : 0);
    return (full - acc) / 2;
  });
  const starts = line.map((w) => (w.startMs / 1000) * fps - from);
  const shift = shiftAt(frame, starts, targets) * fit;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: height * BOTTOM}}>
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          color: 'white',
          lineHeight: 1,
          letterSpacing: -size * 0.016,
          whiteSpace: 'nowrap',
          translate: `${shift}px 0px`,
          scale: String(fit),
          textShadow: `0 ${size * 0.06}px ${size * 0.32}px rgba(0,0,0,0.6), 0 0 ${size * 0.1}px rgba(0,0,0,0.5)`,
        }}
      >
        {line.map((w, j) => (
          <WordEl key={j} caption={w} lineFromFrame={from} size={size} last={j === line.length - 1} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const Captions: React.FC = () => {
  const {width, height, fps, durationInFrames} = useVideoConfig();
  const size = height * SIZE * (C.fontScale ?? 1);
  const budget = width * MAX_W;
  const lines = useMemo(() => buildLines(WORDS, C.maxWords ?? 6, size, budget), [size, budget]);
  return (
    <>
      {lines.map((line, i) => {
        const from = Math.round((line[0].startMs / 1000) * fps);
        const nextFrom =
          i + 1 < lines.length ? Math.round((lines[i + 1][0].startMs / 1000) * fps) : durationInFrames;
        const lastEnd = Math.round((line[line.length - 1].endMs / 1000) * fps) + fps;
        const duration = Math.max(1, Math.min(nextFrom, lastEnd) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            <LineEl line={line} from={from} size={size} budget={budget} />
          </Sequence>
        );
      })}
    </>
  );
};
