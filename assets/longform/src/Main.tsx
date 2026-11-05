/**
 * LONGFORM composition (YouTube 16:9) — DATA-DRIVEN. DO NOT EDIT.
 * All per-video values live in ../public/edit-data.json (schema in README.md).
 *
 * Produced-but-not-saturated: the frame is mostly the talker or a B-roll
 * cutaway; graphics PUNCTUATE. Layers (all optional, driven by the data):
 *   - base cut (full-frame)         - B-roll cutaways (image Ken-Burns / video)
 *   - lower-thirds (name/title)     - chapter cards (title at each chapter)
 *   - callouts (emphasis boxes)     - soundtrack bed
 *   - burned captions (OPTIONAL)    - ABOVE b-roll/glass, `captions.enabled`
 * Captions are OFF by default: the YouTube delivery ships a .srt sidecar
 * (captions_srt.py). Turn `captions.enabled` on to burn them in (Reels
 * horizontal) — render the SAME edit-data twice, once with and once without.
 * Camera (zoom/tracking), flash cuts, prism highlights and springIn: see README.md.
 * Styles: karaoke | stacked | scatter | simples | serifada | classica (all 6, as in 9:16).
 * Also: headline (hook), split screen (splitInserts[], side-by-side), PiP (broll[].pip).
 */
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  staticFile,
  interpolate,
  spring,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import editData from '../public/edit-data.json';
import {GlassPanel, type GlassSpec} from './GlassPanel';
import {ShaderTransitions, type ShaderCut, type Energy} from './ShaderTransition';
import {TrackedScene, type TrackedBlock, type TrackedData} from './TrackedScene';
import {DynamicVideo, type CameraSpec} from './Camera';
import {CutFlashes, CutSfx, type CutFlash} from './Cuts';
import {GlassCards, type HighlightBlock} from './GlassCard';
import {Captions} from './Captions';
import {StackedCaptions} from './StackedCaptions';
import {ScatterCaptions} from './ScatterCaptions';
import {HookIntro, type HookSpec} from './Hook';
import {SplitScreen, type SplitInsert} from './Split';
import {SimpleCaptions, SIMPLE_VARIANTS} from './SimpleCaptions';

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// ============ TYPES + DATA ====================================================
type Broll = {
  kind: 'image' | 'video';
  src: string;
  start: number;
  dur: number;
  /** 'spring' (elements.springIn): overshoot entrance. Omit = the historical ease. */
  enter?: 'cubic' | 'spring';
  /** flash | whip-pan | glitch on the cutaway's in AND out (elements.flashCut). */
  flash?: 'flash' | 'whip-pan' | 'glitch';
  /** PiP ("B-roll com apresentador"): the speaker stays in a rounded window over
   *  the cutaway. `true` = top-right, ~26% of the width. Ratios of the frame. */
  pip?: boolean | {x?: number; y?: number; w?: number; zoom?: number; focusX?: number; focusY?: number};
};
type Lower = {name: string; title?: string; start: number; dur: number};
type Chapter = {title: string; start: number; dur?: number};
type Callout = {text: string; start: number; dur: number; x?: number; y?: number};

export type EditData = {
  width: number;
  height: number;
  fps: number;
  durationSec: number;
  accent: string;
  broll: Broll[];
  lowerThirds: Lower[];
  chapters: Chapter[];
  callouts: Callout[];
  soundtrack: {enabled: boolean; file: string; volume: number};
  // As camadas VFX, iguais às do shortform. Os componentes não sabem o aspecto
  // do vídeo — `rect` é 0..1 e o camera solve trabalha no espaço do mundo —
  // então o que muda no horizontal é o ENQUADRAMENTO, não o código.
  direction?: {energy?: Energy};
  // flash/whip-pan/glitch (Cuts.tsx) + displace/refract (ShaderTransition.tsx)
  transitions?: (ShaderCut | CutFlash)[];
  // Dynamic camera (Camera.tsx): zoomCuts = zooms[], zoomAuto = pushIn, tracking = track.json
  camera?: CameraSpec;
  // Headline (Hook.tsx) and split screen (Split.tsx) — same keys as shortform
  hook?: HookSpec;
  splitInserts?: SplitInsert[];
  // Palavras em vidro-prisma (GlassCard.tsx) — elements.glassPanel
  highlights?: HighlightBlock;
  glass?: GlassBlock;
  tracked?: TrackedBlock;
  // Legenda queimada (opcional). Tamanho/posição são razões do frame, não px.
  captions?: {
    enabled: boolean;
    style?: 'karaoke' | 'stacked' | 'scatter' | 'simples' | 'serifada' | 'classica';
    side?: 'left' | 'right' | 'center'; // stacked/scatter: which free third of the frame
    maxWords?: number;   // palavras por linha (default 6; classica 14)
    fontScale?: number;  // multiplica o tamanho base (default 1)
    highlight?: string;  // karaoke: cor da palavra falada
  };
};

type GlassBlock = GlassSpec & {
  enabled: boolean;
  windows?: {start: number; end: number}[];
};

const D = editData as unknown as EditData;

// camera.json é opcional e gerado por helper — import estático quebraria todo
// projeto que não usa ancoragem 3D.
let trackedData: TrackedData | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  trackedData = require('../public/camera.json') as TrackedData;
} catch {
  trackedData = null;
}

const SHADER_CUT_TYPES = ['displace', 'refract'] as const;
const ACCENT = D.accent || '#33e0a3';
const MARGIN = 96; // 16:9 safe margin

export const Sfx: React.FC<{src: string; volume?: number}> = ({src, volume = 0.08}) => (
  <Audio src={staticFile(`sfx/${src}`)} volume={volume} />
);

// ============ BASE ============
const Base: React.FC = () => {
  const {width, height} = useVideoConfig();
  return <OffthreadVideo src={staticFile('cut.mp4')} style={{width, height}} />;
};

// ============ PiP: the speaker stays on screen over a cutaway ==================
// A second decode of cut.mp4 in a rounded window, re-framed on him. Top-right so
// it clears the bottom caption band and the top-left headline.
const Pip: React.FC<{spec: {x?: number; y?: number; w?: number; zoom?: number; focusX?: number; focusY?: number}; startFrame: number}> = ({spec, startFrame}) => {
  const {width, height} = useVideoConfig();
  const w = width * (spec.w ?? 0.26);
  const h = w * (height / width);
  const x = width * (spec.x ?? 0.71);
  const y = height * (spec.y ?? 0.06);
  const zoom = spec.zoom ?? 1.5;
  const vw = w * zoom;
  const vh = h * zoom;
  const left = clamp(w / 2 - (spec.focusX ?? 0.55) * vw, w - vw, 0);
  const top = clamp(h / 2 - (spec.focusY ?? 0.38) * vh, h - vh, 0);
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, borderRadius: height * 0.018, overflow: 'hidden', boxShadow: `0 ${height * 0.016}px ${height * 0.05}px rgba(0,0,0,0.5)`, border: `${Math.max(2, height / 540)}px solid rgba(255,255,255,0.35)`, boxSizing: 'border-box'}}>
      <OffthreadVideo src={staticFile('cut.mp4')} muted startFrom={startFrame} style={{position: 'absolute', width: vw, height: vh, left, top}} />
    </div>
  );
};

// ============ B-ROLL CUTAWAYS (cover the talker over narration) ================
const BrollEl: React.FC<{item: Broll; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const inn = interpolate(f, [0, 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const out = interpolate(f, [totalFrames - 10, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // elements.springIn: the entrance overshoots slightly and settles ("arrived",
  // not "appeared"). The EXIT stays interpolate so it lands on the last frame.
  const springed = item.enter === 'spring' ? spring({frame: f, fps, config: {damping: 14, mass: 0.55}, durationInFrames: 14}) : null;
  const op = springed === null ? Math.min(inn, out) : Math.min(clamp(springed, 0, 1), out);
  const kb = interpolate(f, [0, totalFrames], [1, 1.06], {extrapolateRight: 'clamp'}); // Ken-Burns
  const grow = springed === null ? kb : kb * interpolate(springed, [0, 1], [0.985, 1]);
  return (
    <AbsoluteFill style={{opacity: op}}>
      <Sfx src="whoosh.mp3" />
      {item.kind === 'image' ? (
        <Img src={staticFile(item.src)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${grow})`}} />
      ) : (
        <OffthreadVideo src={staticFile(item.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      )}
      {item.pip ? <Pip spec={item.pip === true ? {} : item.pip} startFrame={Math.round(item.start * fps)} /> : null}
    </AbsoluteFill>
  );
};

// ============ LOWER-THIRDS (name / title) =====================================
const LowerThird: React.FC<{item: Lower; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const inn = interpolate(f, [0, 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [totalFrames - 10, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(inn, out);
  const x = interpolate(inn, [0, 1], [-40, 0]);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: MARGIN}}>
      <div style={{opacity: op, transform: `translateX(${x}px)`, display: 'flex', alignItems: 'stretch', gap: 16, fontFamily}}>
        <div style={{width: 8, borderRadius: 4, background: ACCENT}} />
        <div style={{background: 'rgba(20,22,26,0.86)', borderRadius: 12, padding: '14px 22px', boxShadow: '0 12px 34px rgba(0,0,0,0.4)'}}>
          <div style={{color: '#fff', fontWeight: 900, fontSize: 40, lineHeight: 1.05}}>{item.name}</div>
          {item.title ? <div style={{color: ACCENT, fontWeight: 600, fontSize: 24, marginTop: 4}}>{item.title}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============ CHAPTER CARDS (title at each chapter start) ======================
const ChapterCard: React.FC<{title: string; totalFrames: number}> = ({title, totalFrames}) => {
  const f = useCurrentFrame();
  const inn = interpolate(f, [0, 14], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [totalFrames - 12, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(inn, out);
  const y = interpolate(inn, [0, 1], [30, 0]);
  const lineW = interpolate(inn, [0, 1], [0, 120]);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: MARGIN, paddingBottom: MARGIN + 40}}>
      <Sfx src="whoosh.mp3" />
      <div style={{opacity: op, transform: `translateY(${y}px)`, fontFamily}}>
        <div style={{height: 6, width: lineW, background: ACCENT, borderRadius: 3, marginBottom: 16}} />
        <div style={{color: '#fff', fontWeight: 900, fontSize: 76, letterSpacing: -1, lineHeight: 1, textShadow: '0 4px 24px rgba(0,0,0,0.6)'}}>{title}</div>
      </div>
    </AbsoluteFill>
  );
};

// ============ CALLOUTS (emphasis box / keyword) ================================
const CalloutEl: React.FC<{item: Callout; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const pop = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.6))});
  const out = interpolate(f, [totalFrames - 8, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(interpolate(f, [0, 5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), out);
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill>
      <Sfx src="pop.mp3" volume={0.1} />
      <div style={{position: 'absolute', left: (item.x ?? 0.5) * width, top: (item.y ?? 0.3) * height, transform: `translate(-50%,-50%) scale(${clamp(pop, 0.01, 1)})`, opacity: op, fontFamily, fontWeight: 900, fontSize: 44, color: '#0c0d10', background: ACCENT, padding: '10px 22px', borderRadius: 12, boxShadow: '0 10px 30px rgba(0,0,0,0.4)', whiteSpace: 'nowrap'}}>
        {item.text}
      </div>
    </AbsoluteFill>
  );
};

// ============ SOUNDTRACK (bed) ================================================
const Soundtrack: React.FC = () => {
  const {durationInFrames} = useVideoConfig();
  const S = D.soundtrack;
  return (
    <Audio
      src={staticFile(S.file)}
      volume={(f) => interpolate(f, [0, 20, durationInFrames - 40, durationInFrames], [0, S.volume, S.volume, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
    />
  );
};

// ============ helper: map a timed list to sequences ===========================
function Timed<T extends {start: number; dur?: number}>(
  items: T[], defaultDur: number, render: (item: T, totalFrames: number) => React.ReactNode,
) {
  const {fps} = useVideoConfig();
  return (
    <>
      {items.map((it, i) => {
        const from = Math.round(it.start * fps);
        const duration = Math.round((it.dur ?? defaultDur) * fps);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            {render(it, duration)}
          </Sequence>
        );
      })}
    </>
  );
}

// ============ MAIN ============
// Painel de vidro em janelas. Idêntico ao shortform: enquanto ativo a canvas
// desenha a footage, então a base 2D não se aplica ali.
const GlassLayer: React.FC<{spec: GlassBlock}> = ({spec}) => {
  const {fps} = useVideoConfig();
  const wins = spec.windows?.length ? spec.windows : [{start: 0, end: Infinity}];
  return (
    <>
      {wins.map((w, i) => {
        const from = Math.round(w.start * fps);
        const dur = Number.isFinite(w.end)
          ? Math.max(1, Math.round((w.end - w.start) * fps))
          : undefined;
        return (
          <Sequence key={i} from={from} durationInFrames={dur} layout="none">
            <AbsoluteFill>
              <GlassPanel spec={spec} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </>
  );
};

export const Main: React.FC = () => {
  const shaderCuts = ((editData as {transitions?: ShaderCut[]}).transitions ?? []).filter(
    (t): t is ShaderCut =>
      Boolean(t) && (SHADER_CUT_TYPES as readonly string[]).includes(t.type as string),
  );
  // flash/whip-pan/glitch: explicit transitions[] + the in/out of any broll with `flash`
  const brollCuts: CutFlash[] = D.broll.flatMap((b) =>
    b.flash ? [{at: b.start, type: b.flash}, {at: b.start + b.dur, type: b.flash}] : [],
  );
  const splitCuts: CutFlash[] = (D.splitInserts ?? []).flatMap((b) =>
    b.flash ? [{at: b.start, type: b.flash}, {at: b.end, type: b.flash}] : [],
  );
  const cuts = [...((D.transitions ?? []) as CutFlash[]), ...brollCuts, ...splitCuts];
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {D.soundtrack.enabled ? <Soundtrack /> : null}
      {D.camera?.enabled ? <DynamicVideo /> : <Base />}
      {Timed(D.broll, 4, (it, d) => <BrollEl item={it} totalFrames={d} />)}
      {D.splitInserts?.length ? <SplitScreen items={D.splitInserts} /> : null}
      {Timed(D.chapters, 2.4, (it, d) => <ChapterCard title={it.title} totalFrames={d} />)}
      {Timed(D.lowerThirds, 4, (it, d) => <LowerThird item={it} totalFrames={d} />)}
      {D.glass?.enabled ? <GlassLayer spec={D.glass} /> : null}
      {D.tracked?.enabled && trackedData ? (
        <TrackedScene spec={D.tracked} data={trackedData} />
      ) : null}
      <ShaderTransitions items={shaderCuts} energy={D.direction?.energy} />
      {cuts.length ? <CutSfx items={cuts} /> : null}
      {cuts.length ? <CutFlashes items={cuts} /> : null}
      {D.hook?.enabled ? <HookIntro /> : null}
      {/* Legenda queimada: acima de b-roll/vidro/transições para ficar legível nos cutaways */}
      {D.captions?.enabled
        ? D.captions.style === 'stacked'
          ? <StackedCaptions />
          : D.captions.style === 'scatter'
            ? <ScatterCaptions />
            : SIMPLE_VARIANTS[D.captions.style as string]
              ? <SimpleCaptions variant={D.captions.style as string} />
              : <Captions />
        : null}
      {Timed(D.callouts, 3, (it, d) => <CalloutEl item={it} totalFrames={d} />)}
      {D.highlights?.enabled ? <GlassCards spec={{...D.highlights, fontFamily: D.highlights.fontFamily ?? fontFamily}} /> : null}
    </AbsoluteFill>
  );
};
