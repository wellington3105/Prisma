/**
 * DynamicVideo (16:9) — the dynamic camera of the base cut.
 *
 * Same data and same maths as shortform's DynamicVideo (edit-data `camera`,
 * public/segments.json, public/track.json) — three independent parts:
 *   zoomCuts  hard zoom change ON each cut segment — `camera.zooms[]`, cycles
 *   zoomAuto  slow push-in inside each segment      — `camera.pushIn`
 *   tracking  face follow (track.json), clamped so it never reveals an edge
 *
 * What differs from 9:16 is only the NUMBERS you put in edit-data: a wide frame
 * reads a punch-in as much stronger, so use ~1.06–1.14 (not 1.10–1.22) and
 * pushIn ~0.03. The code is aspect-agnostic (everything is a ratio of the frame).
 *
 * `camera` absent / enabled:false → the frame is the raw cut (as before).
 * tracking OFF → keep the neutral track.json ([[0.5,0.4]]): the follow has
 * nothing to correct, and the bundle still builds (the import is static).
 */
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import track from '../public/track.json';
import segData from '../public/segments.json';
import editData from '../public/edit-data.json';

export type CameraSpec = {
  enabled: boolean;
  zooms?: number[];
  pushIn?: number;
  targetX?: number;
  targetY?: number;
};

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const cam = (editData as {camera?: CameraSpec}).camera;

// `frameOffset` e `transparent` (paridade com o shortform): uma camada com janela
// própria (o recorte da pessoa dentro de um <Sequence>) usa o frame GLOBAL para a
// conta da câmera e fica alinhada com a base; `transparent` liga o alpha do
// ProRes 4444 / WebM do recorte.
export const DynamicVideo: React.FC<{src?: string; frameOffset?: number; transparent?: boolean}> = ({src = 'cut.mp4', frameOffset = 0, transparent = false}) => {
  const frame = useCurrentFrame() + frameOffset;
  const {width, height, fps} = useVideoConfig();

  let S = 1;
  let tx = 0;
  let ty = 0;
  if (cam?.enabled) {
    const segs = (segData as unknown as {segments: {start: number; dur: number}[]}).segments ?? [];
    const zooms = cam.zooms?.length ? cam.zooms : [1.08];
    let idx = 0;
    // -1: OffthreadVideo draws the source frame at or before frame/fps, which on
    // an exact boundary lands a frame late — without it the zoom steps one frame
    // BEFORE the picture cuts.
    for (let i = 0; i < segs.length; i++) {
      if (frame - 1 >= Math.round(segs[i].start * fps)) idx = i;
    }
    const seg = segs[idx];
    const segFrom = seg ? Math.round(seg.start * fps) + 1 : 0;
    const segLen = seg ? Math.max(1, Math.round(seg.dur * fps)) : 1;
    const push = (cam.pushIn ?? 0) * clamp((frame - segFrom) / segLen, 0, 1);
    S = (zooms[idx % zooms.length] ?? 1) + push;

    const pts = (track as unknown as {points: [number, number][]}).points;
    const p = pts[Math.min(frame, pts.length - 1)] ?? [0.5, 0.4];
    // points are normalised 0..1 (face_track.py); tolerate pixel coords from an
    // old neutral track instead of flinging the frame to an edge
    const cx = p[0] > 1 ? p[0] / width : p[0];
    const cy = p[1] > 1 ? p[1] / height : p[1];
    tx = clamp((cam.targetX ?? 0.5) * width - cx * width * S, width - width * S, 0);
    ty = clamp((cam.targetY ?? 0.4) * height - cy * height * S, height - height * S, 0);
  }

  return (
    <AbsoluteFill>
      <div
        style={{
          width,
          height,
          transformOrigin: '0 0',
          transform: `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${S.toFixed(4)})`,
        }}
      >
        <OffthreadVideo src={staticFile(src)} transparent={transparent} style={{width, height}} />
      </div>
    </AbsoluteFill>
  );
};
