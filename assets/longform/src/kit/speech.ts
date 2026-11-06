/**
 * kit/speech — tempo a partir da FALA, não de segundos escritos à mão.
 *
 * Uma cena sob medida ("a palavra MBUX aparece quando ele diz MBUX") deve ser
 * ancorada no que o falante diz: se a edição for re-cortada, a transcrição
 * muda e a cena acompanha. Segundo fixo no código quebra em silêncio.
 *
 * Fonte: public/captions.json (helpers/captions_for_remotion.py), nível de
 * palavra, tempos na linha do cut. Tudo aqui é puro (sem hooks) — use dentro de
 * qualquer componente com `useCurrentFrame()` / `useVideoConfig()`.
 */
import {Easing, interpolate} from 'remotion';
import captions from '../../public/captions.json';

export type Spoken = {raw: string; w: string; s: number; e: number};

/** minúsculas, sem acento e sem pontuação: "MBUX." -> "mbux" */
export const norm = (t: string): string =>
  t
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '');

// captions.json com a forma errada não pode derrubar o render
const RAW = (Array.isArray(captions) ? captions : []) as {text: string; startMs: number; endMs: number}[];
export const SPOKEN: Spoken[] = RAW.map((c) => ({raw: c.text, w: norm(c.text), s: c.startMs / 1000, e: c.endMs / 1000}));

/** índices onde a frase (1+ palavras) começa */
function occurrences(phrase: string): number[] {
  const want = phrase.split(/\s+/).map(norm).filter(Boolean);
  if (!want.length) return [];
  const hits: number[] = [];
  for (let i = 0; i + want.length <= SPOKEN.length; i++) {
    if (want.every((w, k) => SPOKEN[i + k].w === w)) hits.push(i);
  }
  return hits;
}

/**
 * Segundo em que `phrase` COMEÇA a ser dita — a ocorrência mais próxima de `near`
 * (segundos). Sem `near`, a primeira. Não achou: devolve `near` e avisa no log
 * (a cena aparece no tempo de referência em vez de quebrar o render).
 */
export function whenSaid(phrase: string, near = 0): number {
  const hits = occurrences(phrase);
  if (!hits.length) {
    // eslint-disable-next-line no-console
    console.warn(`[kit/speech] "${phrase}" não está em captions.json — usando ${near}s`);
    return near;
  }
  return SPOKEN[hits.reduce((b, i) => (Math.abs(SPOKEN[i].s - near) < Math.abs(SPOKEN[b].s - near) ? i : b))].s;
}

/** Segundo em que `phrase` TERMINA de ser dita (mesma regra de `whenSaid`). */
export function endOfSaid(phrase: string, near = 0): number {
  const n = phrase.split(/\s+/).filter(Boolean).length;
  const hits = occurrences(phrase);
  if (!hits.length) return near;
  const i = hits.reduce((b, k) => (Math.abs(SPOKEN[k].s - near) < Math.abs(SPOKEN[b].s - near) ? k : b));
  return SPOKEN[i + n - 1].e;
}

/** palavras ditas entre dois instantes */
export const wordsBetween = (a: number, b: number): Spoken[] => SPOKEN.filter((w) => w.s >= a && w.s < b);

// ---- curvas (motion-craft: opacidade/foco expo.out curto; posição power3.out ~0.5s) ----
export const power3Out = Easing.bezier(0.215, 0.61, 0.355, 1);
export const expoOut = Easing.out(Easing.exp);
export const power3In = Easing.in(Easing.cubic);
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);

/** progresso 0 -> 1 a partir de `t0` (s) durante `dur` (s) */
export function progress(frame: number, fps: number, t0: number, dur: number, ease: (x: number) => number = power3Out): number {
  return interpolate(frame / fps, [t0, t0 + Math.max(1e-3, dur)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: ease,
  });
}

/**
 * Envelope entra/segura/sai entre dois instantes: 0 antes de `a`, sobe até 1 em
 * `inDur`, segura, desce a 0 terminando em `b` (saída `outDur`, power3.in).
 */
export function windowOf(frame: number, fps: number, a: number, b: number, inDur = 0.35, outDur = 0.25): number {
  const up = progress(frame, fps, a, inDur, expoOut);
  const down = interpolate(frame / fps, [b - outDur, b], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: power3In});
  return Math.max(0, Math.min(up, 1 - down));
}

/** `windowOf` entre duas frases ditas: da primeira palavra de `from` ao fim de `to`. */
export function windowBetweenWords(frame: number, fps: number, from: string, to: string, near = 0, inDur = 0.35, outDur = 0.25): number {
  const a = whenSaid(from, near);
  return windowOf(frame, fps, a, Math.max(a + 0.4, endOfSaid(to, a)), inDur, outDur);
}
