/**
 * SplitScreen (16:9) — "tela dividida" as a SIDE-BY-SIDE layout, data-driven by
 * edit-data `splitInserts[]` (the same key shortform reads).
 *
 *   layout "top"    (id `split`)  art FIRST  -> art on the LEFT,  speaker right
 *   layout "bottom" (id `split2`) art SECOND -> art on the RIGHT, speaker left
 *   ("left" / "right" are accepted as aliases)
 *
 * In 9:16 the frame is split top/bottom; a wide frame splits left/right. The
 * speaker column is the cut re-framed on him: `zoom` (default 1.12) and
 * `focusX` / `focusY` (0..1 of the source, default 0.55 / 0.5) pick the crop, and
 * it is clamped so it never reveals an edge. `bandW` is the art's share of the
 * width (default 0.5). All values are ratios of the frame, so 1080p == 4K.
 *
 * The window edges ARE cut frames: same `VIDEO_LAG` compensation as shortform
 * (OffthreadVideo draws one frame late) and ONE always-mounted layer, no
 * <Sequence> per window, so the layout never precedes the picture.
 *
 * Transitions on the layout change: set `flash` on an item ("flash" | "whip-pan"
 * | "glitch") and Main.tsx adds a cut at its start and at its end, or list them
 * in `transitions[]` by hand (same as shortform's flashCut).
 */
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type SplitInsert = {
  src: string;
  start: number;
  end: number;
  fit?: 'cover' | 'contain';
  layout?: 'top' | 'bottom' | 'left' | 'right';
  bandW?: number;
  zoom?: number;
  focusX?: number;
  focusY?: number;
  flash?: 'flash' | 'whip-pan' | 'glitch';
};

const VIDEO_LAG = 1;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

const SplitFrame: React.FC<{item: SplitInsert; progress: number}> = ({item, progress}) => {
  const {width, height} = useVideoConfig();
  const artLeft = (item.layout ?? 'top') === 'top' || item.layout === 'left';
  const artW = Math.round(width * clamp(item.bandW ?? 0.5, 0.3, 0.7));
  const colW = width - artW;
  const zoom = item.zoom ?? 1.12;
  const fx = item.focusX ?? 0.55;
  const fy = item.focusY ?? 0.5;
  const vw = width * zoom;
  const vh = height * zoom;
  const left = clamp(colW / 2 - fx * vw, colW - vw, 0);
  const top = clamp(height / 2 - fy * vh, height - vh, 0);
  const fit = item.fit ?? 'cover';
  const isVideo = /\.(mp4|mov|webm|m4v)$/i.test(item.src);
  const artStyle = {width: '100%', height: '100%', objectFit: fit, scale: String(1 + 0.03 * progress)} as const;
  const seam = Math.max(2, Math.round(height / 540));

  return (
    <AbsoluteFill style={{backgroundColor: '#0a0a0c'}}>
      <div style={{position: 'absolute', top: 0, height, width: colW, left: artLeft ? artW : 0, overflow: 'hidden'}}>
        <OffthreadVideo src={staticFile('cut.mp4')} muted style={{position: 'absolute', width: vw, height: vh, left, top}} />
      </div>
      <div style={{position: 'absolute', top: 0, height, width: artW, left: artLeft ? 0 : colW, overflow: 'hidden'}}>
        {isVideo ? (
          <OffthreadVideo src={staticFile(item.src)} muted style={artStyle} />
        ) : (
          <Img src={staticFile(item.src)} style={artStyle} />
        )}
      </div>
      {/* seam */}
      <div style={{position: 'absolute', top: 0, height, width: seam, left: (artLeft ? artW : colW) - seam / 2, background: 'rgba(255,255,255,0.5)'}} />
    </AbsoluteFill>
  );
};

export const SplitScreen: React.FC<{items: SplitInsert[]}> = ({items}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const active = items.find((it) => {
    const a = Math.round(it.start * fps) + VIDEO_LAG;
    const b = Math.round(it.end * fps) + VIDEO_LAG;
    return frame >= a && frame < b;
  });
  if (!active) return null;
  const a = Math.round(active.start * fps) + VIDEO_LAG;
  const b = Math.round(active.end * fps) + VIDEO_LAG;
  return <SplitFrame item={active} progress={clamp((frame - a) / Math.max(1, b - a), 0, 1)} />;
};
