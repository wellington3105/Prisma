/**
 * ScatterCaptions — caption style "disperso".
 *
 * Serif, lowercase, one word at a time, laid out in short ragged lines whose
 * horizontal offset looks random but is NOT: it is hashed off the cue index, so
 * every frame of a render agrees with every other. Never Math.random() here —
 * Remotion renders frames independently and a real random would jitter the
 * layout on every single frame.
 *
 * Two entrances, on purpose:
 *   - ordinary words just FADE IN — no movement at all;
 *   - a highlighted word per cue resolves OUT of a heavy blur at ~1.6× the size,
 *     and dissolves back INTO blur when the cue leaves.
 * The contrast is the style — if every word were special, none would be.
 *
 * Data: public/captions.json (word level, same file the karaoke style reads).
 * No extra generation step.
 */
import {
  AbsoluteFill,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Lora';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import editData from '../public/edit-data.json';

const {fontFamily} = loadFont('normal', {weights: ['400', '600']});
loadFont('italic', {weights: ['400', '600']});

type Word = {text: string; startMs: number; endMs: number};
type Placed = Word & {size: number; hi: boolean};
type Cue = {startMs: number; endMs: number; lines: Placed[][]; shift: number[]; drop: number};

const C = (editData as any).captions ?? {};
const SAFE_W = C.scatterSafeWidth ?? 820;
const BASE = C.scatterFontSize ?? 72;
const HI_SCALE = 1.62;
// Cor do destaque dentro da legenda. Vem do accent escolhido no gate de estilo,
// para headline, card e palavra destacada falarem a mesma língua cromática —
// duas cores de destaque no mesmo vídeo leem como dois vídeos colados.
const ACCENT = C.accentColor ?? (editData as any).accent ?? '#7fd4ff';
const SPREAD = 0.45; // how far a line may wander off centre, 0..1 of the free room
const WORD_GAP = 12;
// Block centre as a fraction of height. The reference puts this text over
// B-roll, where the middle of the frame is free; on a talking head the middle IS
// the face, so the default sits on the chest instead. Raise it only over B-roll.
const OFFSET_Y = C.scatterOffsetY ?? 0.72;

// deterministic hash — same input, same layout, on every frame
const hash = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// Off-white, not #fff, with a very slight darkening toward the baseline. The
// gradient rides on the WORD span, so it runs over the letterforms themselves
// rather than over the block — that is what makes it read as ink weight instead
// of a wash. Same background-clip:text technique as the stacked style, and the
// same caveat: it has to be on the element that OWNS the text, next to its
// filter, or the glyphs come out transparent.
const INK: React.CSSProperties = {
  backgroundImage: 'linear-gradient(180deg,#f8f5ef 0%,#f4f1e9 54%,#d5cec1 100%)',
  WebkitBackgroundClip: 'text',
  backgroundClip: 'text',
  WebkitTextFillColor: 'transparent',
  color: 'transparent',
};

const clean = (t: string) => t.replace(/[.,!?…]+$/, '').toLowerCase();
const isBreak = (t: string) => /[.,!?…]$/.test(t);

// Palavras que nunca são destaque: artigos, preposições, conectivos, verbos de
// ligação e muletas. Espelha a lista de `helpers/highlight_words.py` — as duas
// camadas precisam concordar sobre o que é importante, senão a legenda colore
// uma coisa e o card destaca outra na mesma frase.
const VAZIAS = new Set([
  'a','o','as','os','um','uma','uns','umas','de','da','do','das','dos','em',
  'na','no','nas','nos','por','para','pra','pro','com','sem','sobre','entre',
  'ate','que','quem','qual','quais','e','ou','mas','porem','porque','pois',
  'se','como','quando','onde','eu','voce','ele','ela','nos','eles','elas',
  'meu','minha','seu','sua','esse','essa','isso','este','esta','isto','ser',
  'estar','ter','haver','ir','vir','fazer','sao','estao','tem','tinha','foi',
  'era','vai','vou','muito','mais','menos','ja','ainda','so','tambem','nao',
  'sim','bem','bom','aqui','ali','la','entao','dai','ai','tipo','assim',
  'coisa','gente','vamos','acho','sei','tudo','nada','consigo','pode','vez',
  // Conjugações irregulares e adjetivos genéricos que o sufixo não pega, todos
  // observados escapando no teste isolado sobre este transcript.
  'precisa','precisam','entendi','entende','claro','clara','melhor','mesmo',
  'sabe','sabia','fica','ficou','quer','quero','deve','devia','parece',
  // Contrações de preposição e demonstrativos: têm 4+ letras e escapavam do
  // piso de comprimento, mas são exatamente o tipo de palavra que a regra
  // exclui — não nomeiam nada.
  'pelo','pela','pelos','pelas','desse','dessa','deste','desta','disso',
  'daquele','daquela','naquele','naquela','nesse','nessa','neste','nesta',
  'modo','forma','jeito','parte','lado','caso','ponto','meio','quase','todo',
]);

/** Sem acento e minúscula, para bater com VAZIAS. */
const semAcento = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '');

/**
 * Quanto esta palavra merece o destaque da cue. Mesma hierarquia do helper
 * Python: número > termo técnico > substantivo longo. Nome próprio é EXCLUÍDO
 * aqui, ao contrário do helper — o card nomeia um conceito e pode se dar ao
 * luxo de citar uma marca; a legenda acompanha a fala inteira, e colorir o nome
 * de uma pessoa no meio dela desvia o olho do assunto para quem foi citado.
 * Verbo no infinitivo/gerúndio devolve 0 — a referência destaca COISAS, não
 * ações.
 */
function pesoDaPalavra(limpo: string, nomeProprio = false): number {
  const n = semAcento(limpo);
  if (n.length < 4 || VAZIAS.has(n)) return 0;
  // Nome de pessoa não é destaque: colorir "Neto" ou "Davi" aponta para QUEM
  // foi citado em vez do assunto da frase. Medido em 2026-09-01 — a cue "o Neto
  // Davi e ficou meio" elegeu "neto" com 0.4, o piso genérico, por falta de
  // concorrência. A maiúscula no MEIO da frase é o sinal, e o WhisperX a marca
  // com fidelidade; no início não diz nada, porque toda frase começa assim.
  if (nomeProprio) return 0;
  if (/\d/.test(limpo)) return 3;
  // Advérbio em -mente e adjetivo em -ente: comprimento os fazia passar por
  // substantivo ("realmente", "diferente"), medido no teste isolado. Nenhum
  // dos dois nomeia uma coisa, que é o que o destaque deve fazer.
  if (/(mente|ente)$/.test(n)) return 0;
  // Verbo: infinitivo, gerúndio, particípio e as conjugações de 1ª/3ª pessoa
  // que apareceram na medição ("precisa", "entendi", "consigo").
  if (/(ar|er|ir|ando|endo|indo|ado|ido|amos|emos|imos)$/.test(n) && n.length > 4) return 0;
  if (/[kwy]/.test(n)) return 2;
  if (n.length >= 8) return 1.5;
  if (n.length >= 6) return 1;
  return 0.4;
}

// A cue is a breath: punctuation, or 6 words, or a gap of 400ms+ in the speech.
function buildCues(words: Word[]): Cue[] {
  const groups: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    cur.push(w);
    const next = words[i + 1];
    const gap = next ? next.startMs - w.endMs : Infinity;
    if (cur.length >= 6 || isBreak(w.text) || gap > 400) {
      groups.push(cur);
      cur = [];
    }
  });
  if (cur.length) groups.push(cur);

  return groups.map((g, gi) => {
    // One highlight per cue. Comprimento NÃO é importância: escolher a palavra
    // mais longa punha o destaque em "consigo" e "realmente", que são muleta e
    // advérbio. A referência (Reel psicristianefroes) colore substantivos —
    // "a gente", "a pessoa", "DSM-5" — o mesmo critério do highlight_words.py:
    // número > nome próprio > substantivo com carga; nunca verbo ou conectivo.
    let hiIdx = -1;
    let hiScore = 0;
    g.forEach((w, i) => {
      // Maiúscula só significa nome próprio no MEIO da frase. A primeira
      // palavra da cue e a que segue um ponto abrem frase e sempre vêm
      // capitalizadas — tratá-las como nome descartaria substantivos válidos.
      const abreFrase = i === 0 || isBreak(g[i - 1].text);
      const nomeProprio = !abreFrase && /^[A-ZÀ-Þ]/.test(w.text.trim());
      const s = pesoDaPalavra(clean(w.text), nomeProprio);
      if (s > hiScore) {
        hiScore = s;
        hiIdx = i;
      }
    });

    const placed: Placed[] = g.map((w, i) => ({
      ...w,
      size: i === hiIdx ? Math.round(BASE * HI_SCALE) : BASE,
      hi: i === hiIdx,
    }));

    // ragged lines of 2–3 words; a highlighted word takes a line of its own so
    // it can breathe at its bigger size
    const lines: Placed[][] = [];
    let line: Placed[] = [];
    placed.forEach((p, i) => {
      const want = hash(gi * 31 + i) > 0.5 ? 4 : 3;
      if (p.hi) {
        if (line.length) lines.push(line);
        lines.push([p]);
        line = [];
        return;
      }
      line.push(p);
      if (line.length >= want) {
        lines.push(line);
        line = [];
      }
    });
    if (line.length) lines.push(line);

    // horizontal offset per line, clamped so nothing leaves the safe width
    const shift = lines.map((ln, li) => {
      const w = ln.reduce(
        (acc, p, k) =>
          acc +
          measureText({text: clean(p.text), fontFamily, fontSize: p.size, fontWeight: 400}).width +
          (k ? WORD_GAP : 0),
        0,
      );
      // Only a fraction of the free room: at full range consecutive lines land
      // at opposite edges and the cue reads as scattered debris instead of a
      // phrase. SPREAD is what keeps it a paragraph that breathes.
      const room = Math.max(0, (SAFE_W - w) / 2) * SPREAD;
      return (hash(gi * 17 + li * 5 + 3) * 2 - 1) * room;
    });

    return {
      startMs: g[0].startMs,
      endMs: g[g.length - 1].endMs,
      lines,
      shift,
      drop: (hash(gi * 53 + 11) * 2 - 1) * 40, // vertical jitter of the block
    };
  });
}

// `as Word[]` e uma promessa ao compilador, nao uma verificacao: um
// captions.json com a forma errada passa pelo cast e explode em runtime com
// "words.forEach is not a function". Aconteceu numa instalacao limpa vinda do
// GitHub — o scaffold gravava {captions: []} e o componente esperava array.
//
// O scaffold foi corrigido; esta guarda existe porque o render e caro e um
// captions.json de outra ferramenta nao deveria derrubar o video inteiro.
const CAPS: Word[] = Array.isArray(captions) ? (captions as Word[]) : [];
const CUES = buildCues(CAPS);

const ENTER = 7; // frames — fade + drop
const HI_ENTER = 10; // frames — blur resolve
const EXIT = 8; // frames — the cue leaves

const CueView: React.FC<{cue: Cue; endFrame: number}> = ({cue, endFrame}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const exitStart = endFrame - EXIT;
  const out = interpolate(frame, [exitStart, endFrame], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div
        style={{
          width: SAFE_W,
          translate: `0px ${Math.round(height * (OFFSET_Y - 0.5)) + cue.drop}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          fontFamily,
        }}
      >
        {cue.lines.map((ln, li) => (
          <div
            key={li}
            style={{
              display: 'flex',
              gap: WORD_GAP,
              alignItems: 'baseline',
              whiteSpace: 'pre',
              translate: `${cue.shift[li].toFixed(1)}px 0px`,
              lineHeight: 1.03,
            }}
          >
            {ln.map((p, wi) => {
              const start = (p.startMs / 1000) * fps;
              const dur = p.hi ? HI_ENTER : ENTER;
              const t = interpolate(frame, [start, start + dur], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.out(Easing.cubic),
              });
              // Highlighted: blur resolves in, blurs back out on the way off.
              // Ordinary: fade ONLY. They also had a drop from above, and with a
              // word landing every ~200ms the whole screen read as frantic —
              // motion on every word is motion on nothing.
              const blur = p.hi ? (1 - t) * 26 + out * 30 : 0;
              return (
                <span
                  key={wi}
                  style={{
                    // A palavra destacada recebe COR SÓLIDA; o resto mantém o
                    // gradiente de tinta. É o gesto da referência: uma palavra
                    // colorida dentro da frase branca, e é a cor — não o
                    // tamanho — que diz onde olhar. Sobrescrever `...INK` exige
                    // limpar `WebkitTextFillColor`, senão o clip-to-text do
                    // gradiente vence e o glifo sai transparente.
                    ...INK,
                    ...(p.hi
                      ? {
                          backgroundImage: 'none',
                          WebkitTextFillColor: ACCENT,
                          color: ACCENT,
                        }
                      : null),
                    fontSize: p.size,
                    fontWeight: p.hi ? 600 : 400,
                    fontStyle: p.hi && hash(li * 7 + wi) > 0.65 ? 'italic' : 'normal',
                    opacity: t * (1 - out),
                    filter: `${blur > 0.4 ? `blur(${blur.toFixed(1)}px) ` : ''}drop-shadow(0 2px 3px rgba(0,0,0,0.85)) drop-shadow(0 6px 20px rgba(0,0,0,0.6))`,
                  }}
                >
                  {clean(p.text)}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const ScatterCaptions: React.FC = () => {
  const {fps, durationInFrames} = useVideoConfig();
  const frame = useCurrentFrame();
  // ONE mounted layer picking the live cue, not a <Sequence> per cue: the same
  // reason the split layer is mounted flat — a Sequence would restart the local
  // frame and the per-word absolute timings would have to be rebased.
  let idx = -1;
  for (let i = 0; i < CUES.length; i++) {
    if (frame >= Math.round((CUES[i].startMs / 1000) * fps)) idx = i;
  }
  if (idx < 0) return null;
  const next = CUES[idx + 1];
  const endFrame = next
    ? Math.round((next.startMs / 1000) * fps)
    : Math.min(durationInFrames, Math.round((CUES[idx].endMs / 1000) * fps) + fps);
  if (frame >= endFrame) return null;
  return <CueView cue={CUES[idx]} endFrame={endFrame} />;
};
