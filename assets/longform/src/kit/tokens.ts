/**
 * kit/tokens — o "estilo" do vídeo para cenas sob medida: cor de destaque e
 * fonte vêm do edit-data (a mesma `accent` que headline, cards e legenda usam),
 * para a cena falar a mesma língua cromática do resto. Duas cores de destaque
 * no mesmo vídeo leem como dois vídeos colados.
 */
import {loadFont} from '@remotion/google-fonts/Poppins';
import editData from '../../public/edit-data.json';

const FONT = loadFont('normal', {weights: ['400', '600', '800', '900']}).fontFamily;
const ED = editData as unknown as {accent?: string};

export const TOKENS = {
  accent: ED.accent || '#ff5200',
  ink: '#ffffff',
  dim: 'rgba(255,255,255,0.72)',
  font: FONT,
} as const;

/** #rrggbb + alpha -> rgba() */
export function rgba(hex: string, a: number): string {
  const h = hex.replace('#', '');
  const v = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(v, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** vidro fosco (blur 12–24, tinta 10–40%, borda de 1px — receita do GlassCard) */
export const glassStyle = (tint = 0.45): React.CSSProperties => ({
  background: `linear-gradient(135deg, rgba(255,255,255,0.20), rgba(14,18,28,${tint}))`,
  backdropFilter: 'blur(16px) saturate(1.4)',
  WebkitBackdropFilter: 'blur(16px) saturate(1.4)',
  border: '1px solid rgba(255,255,255,0.18)',
  boxShadow: '0 24px 60px rgba(0,0,0,0.4)',
});

/** texto legível sobre pintura clara: sombra em duas camadas */
export const inkShadow = '0 2px 3px rgba(0,0,0,0.75), 0 6px 22px rgba(0,0,0,0.55)';

/** brilho de cor para destaque de palavra */
export const glow = (hex: string = TOKENS.accent, k = 1): string => `0 0 ${18 * k}px ${rgba(hex, 0.75)}, 0 0 ${48 * k}px ${rgba(hex, 0.4)}`;
