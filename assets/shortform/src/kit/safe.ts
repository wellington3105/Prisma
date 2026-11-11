/**
 * kit/safe — área segura da plataforma + onde está o rosto, para a cena não
 * cair em cima de quem fala.
 *
 * As faixas de UI vêm do mesmo lugar que helpers/safe_layout.py (portadas do
 * ghost-editor, MIT): 9:16 = topo/base/coluna de botões; 16:9 = margem de 5%.
 * O rosto vem de public/faces.json, gerado por `safe_layout.py <edit>` — se o
 * arquivo não existir, `faceAt` devolve null e a cena usa o ponto pedido.
 * O zoom/tracking da `camera` do edit-data é aplicado (o rosto na TELA).
 */
import editData from '../../public/edit-data.json';

export type Rect = {x0: number; y0: number; x1: number; y1: number};

const PLATFORMS_916: Record<string, {top: number; bottom: number; right: number}> = {
  instagram: {top: 220, bottom: 420, right: 130},
  tiktok: {top: 160, bottom: 480, right: 150},
  shorts: {top: 140, bottom: 380, right: 140},
  youtube: {top: 140, bottom: 380, right: 140},
  all: {top: 220, bottom: 480, right: 150},
};

const ED = editData as unknown as {
  platform?: string;
  camera?: {enabled?: boolean; zooms?: number[]; pushIn?: number; targetX?: number; targetY?: number};
  fps?: number;
};

/** área onde cabe texto/gráfico sem cair na UI da plataforma (px do quadro) */
export function safeArea(width: number, height: number, platform: string = ED.platform ?? 'all'): Rect & {w: number; h: number; rightUi: number} {
  if (height > width) {
    const P = PLATFORMS_916[platform] ?? PLATFORMS_916.all;
    const k = width / 1080;
    return {x0: 0, y0: P.top * k, x1: width, y1: height - P.bottom * k, w: width, h: height - (P.top + P.bottom) * k, rightUi: P.right * k};
  }
  const m = 0.05;
  return {x0: width * m, y0: height * m, x1: width * (1 - m), y1: height * (1 - m), w: width * (1 - 2 * m), h: height * (1 - 2 * m), rightUi: 0};
}

/** mantém uma caixa (centro x,y; w,h) dentro da área segura */
export function fitInside(x: number, y: number, w: number, h: number, a: Rect): {x: number; y: number} {
  return {
    x: Math.max(a.x0 + w / 2, Math.min(a.x1 - w / 2, x)),
    y: Math.max(a.y0 + h / 2, Math.min(a.y1 - h / 2, y)),
  };
}

// ---- rosto -------------------------------------------------------------------
type FacesFile = {w: number; h: number; samples: ([number, number, number, number, number, number?, number?] | [number, null])[]};
let FACES: FacesFile | null = null;
try {
  // opcional: gerado por helpers/safe_layout.py. require em try — um import estático
  // quebraria todo projeto que ainda não rodou a detecção.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  FACES = require('../../public/faces.json') as FacesFile;
} catch {
  FACES = null;
}
const SEGS: {start: number; dur: number}[] = (() => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return (require('../../public/segments.json') as {segments: {start: number; dur: number}[]}).segments ?? [];
  } catch {
    return [];
  }
})();
const TRACK: [number, number][] = (() => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return (require('../../public/track.json') as {points: [number, number][]}).points ?? [];
  } catch {
    return [];
  }
})();

/** câmera dinâmica do template no frame `f` (mesma conta de Camera.tsx / DynamicVideo) */
export function cameraAt(f: number, width: number, height: number, fps: number): {S: number; tx: number; ty: number} {
  const c = ED.camera;
  if (!c?.enabled) return {S: 1, tx: 0, ty: 0};
  const zooms = c.zooms?.length ? c.zooms : [1.08];
  let idx = 0;
  for (let i = 0; i < SEGS.length; i++) if (f - 1 >= Math.round(SEGS[i].start * fps)) idx = i;
  const seg = SEGS[idx];
  const segFrom = seg ? Math.round(seg.start * fps) + 1 : 0;
  const segLen = seg ? Math.max(1, Math.round(seg.dur * fps)) : 1;
  const S = (zooms[idx % zooms.length] ?? 1) + (c.pushIn ?? 0) * Math.max(0, Math.min(1, (f - segFrom) / segLen));
  const p = TRACK[Math.min(f, TRACK.length - 1)] ?? [0.5, 0.4];
  const cx = p[0] > 1 ? p[0] / width : p[0];
  const cy = p[1] > 1 ? p[1] / height : p[1];
  return {
    S,
    tx: Math.max(width - width * S, Math.min(0, (c.targetX ?? 0.5) * width - cx * width * S)),
    ty: Math.max(height - height * S, Math.min(0, (c.targetY ?? 0.4) * height - cy * height * S)),
  };
}

/** caixa do rosto NA TELA no frame `f` (px do quadro), ou null (sem dado/sem rosto) */
export function faceAt(f: number, width: number, height: number, fps: number): Rect | null {
  if (!FACES) return null;
  const t = f / fps;
  const pts = FACES.samples.filter((s): s is [number, number, number, number, number] => s[1] !== null);
  if (!pts.length) return null;
  const near = pts.reduce((b, s) => (Math.abs(s[0] - t) < Math.abs(b[0] - t) ? s : b));
  if (Math.abs(near[0] - t) > 1.0) return null; // longe demais de uma detecção
  const {S, tx, ty} = cameraAt(f, width, height, fps);
  const sx = width / FACES.w;
  const sy = height / FACES.h;
  return {x0: tx + S * near[3] * sx, y0: ty + S * near[1] * sy, x1: tx + S * near[4] * sx, y1: ty + S * near[2] * sy};
}

const hit = (a: Rect, b: Rect, m = 0) => a.x0 < b.x1 + m && a.x1 > b.x0 - m && a.y0 < b.y1 + m && a.y1 > b.y0 - m;

/**
 * Centro final de uma caixa w×h que PREFERE (x,y): se cobrir o rosto, vai para
 * abaixo do queixo -> acima da cabeça -> ao lado; sempre dentro da área segura.
 * Ordem do ghost-editor (MIT). Sem rosto detectado, só encaixa na área segura.
 */
export function freeSpot(f: number, width: number, height: number, fps: number, x: number, y: number, w: number, h: number): {x: number; y: number; moved: boolean} {
  const a = safeArea(width, height);
  const first = fitInside(x, y, w, h, a);
  const face = faceAt(f, width, height, fps);
  const box = (cx: number, cy: number): Rect => ({x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2});
  if (!face) return {...first, moved: first.x !== x || first.y !== y};
  const gap = height * 0.02;
  if (!hit(box(first.x, first.y), face, gap * 0.8)) return {...first, moved: first.x !== x || first.y !== y};
  const tries: [number, number][] = [
    [first.x, face.y1 + gap + h / 2],
    [first.x, face.y0 - gap - h / 2],
    [face.x0 - gap - w / 2, first.y],
    [face.x1 + gap + w / 2, first.y],
  ];
  for (const [cx, cy] of tries) {
    const p = fitInside(cx, cy, w, h, a);
    if (p.x === cx && p.y === cy && !hit(box(cx, cy), face, gap * 0.8)) return {x: cx, y: cy, moved: true};
  }
  return {...first, moved: false}; // sem espaço: mantém — o `safe_layout.py --report` já avisa
}
