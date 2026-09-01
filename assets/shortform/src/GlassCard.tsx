/**
 * GlassCard — a palavra-chave num card de vidro, na deixa em que é dita.
 *
 * É a técnica central do Reel de referência, e a que o usuário pediu desde o
 * começo: enquanto ele fala, o termo que importa aparece destacado. Não é
 * decoração — é a **segunda camada de informação**, somando com a legenda (que
 * acompanha toda a fala) e o B-roll (que mostra o significado).
 *
 * A regra que organiza as três, da literatura de explainer:
 *   **texto REFORÇA, não duplica.** O card não repete a legenda; isola o termo.
 *   Se os dois dizem a mesma coisa ao mesmo tempo, um deles é ruído.
 *
 * Números que vêm de ofício, não de gosto (PRP 2026-09-01):
 *   - permanência mínima de **3s** na tela;
 *   - entra **na palavra**, não antes nem depois — é o `highlighter effect` de
 *     Johnny Harris, que anima o destaque na deixa exata do narrador;
 *   - **animação simples supera estático**: o movimento atrai o olho;
 *   - sans limpa, uma ou duas fontes no vídeo inteiro;
 *   - ~1 a cada 8–15s. Mais que isso vira legenda redundante.
 *
 * E a receita de vidro, da literatura de glassmorphism:
 *   blur 12–24px (acima de 30 vira borrão), tinte 10–40%, borda de 1px —
 *   *"mesmo 1px de rgba(255,255,255,.15) faz uma diferença enorme"*. Os três
 *   juntos; tirar qualquer um quebra a ilusão.
 *
 * Por que 2D e não ancorado em 3D: a ancoragem exige camera solve, que falha
 * em vídeo de pessoa parada falando — o caso mais comum. O card precisa
 * funcionar sempre. Quando houver solve válido, `kind:'glassCard'` no
 * TrackedScene faz a versão ancorada.
 */
import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
  Easing,
} from 'remotion';

export type Highlight = {
  /** O termo destacado. Curto — é um destaque, não uma frase. */
  text: string;
  /** Segundo em que a palavra é DITA. O card entra aqui. */
  at: number;
  /** Segundos na tela. Mínimo 3 por ofício; default 3.2. */
  dur?: number;
  /** Rótulo pequeno acima, para contexto ("conversão", "por mês"). */
  label?: string;
  /** 0..1 na largura e altura do quadro.
   *
   *  O default NÃO é centrado: a referência põe os cards AO LADO do sujeito,
   *  nunca sobre ele. Um card centralizado cobre o rosto — que é onde o
   *  espectador está olhando — e as duas informações se anulam. 0.72/0.24 o
   *  encosta no canto superior direito, deixando o falante livre. */
  x?: number;
  y?: number;
  /** Inclinação leve, em graus. Tira o ar de banner de PowerPoint. */
  tilt?: number;
  accent?: string;
  /** Vidro escuro para cena clara (o padrão), claro para cena escura. */
  dark?: boolean;
};

export type HighlightBlock = {
  enabled: boolean;
  items: Highlight[];
  /** Fonte do card. Mesma família da headline mantém o vídeo coeso. */
  fontFamily?: string;
  /** Atraso após a palavra ser dita, em segundos. Default 0.8.
   *
   *  O número vem de medição, não de gosto: a legenda karaokê segura cada
   *  palavra por 0.20s (mediana) e até 0.48s nas longas. Com 0.5s o card caía
   *  exatamente na virada e os dois mostravam o mesmo termo — o defeito que o
   *  primeiro still expôs. 0.8s garante que a legenda já passou. */
  offsetS?: number;
};

const One: React.FC<{h: Highlight; total: number; fontFamily?: string}> = ({
  h,
  total,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const accent = h.accent ?? '#7fd4ff';
  const dark = h.dark ?? true;

  // Entrada com mola: overshoot leve. "Animação simples supera estático" —
  // o card precisa CHEGAR, não aparecer.
  const enter = spring({frame, fps, config: {damping: 15, mass: 0.5}, durationInFrames: 11});
  // Saída em interpolate, para pousar no último frame exato. Um card que
  // pisca ao desmontar chama mais atenção que o destaque em si.
  const exit = interpolate(frame, [total - 8, total], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const vis = Math.min(enter, exit);

  // Escala em função da largura do quadro: o card ocupa ~46% dela, o que o
  // mantém legível em 1080 vertical sem competir com o rosto.
  const size = width * 0.046;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-start',
        alignItems: 'center',
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: `${(h.x ?? 0.72) * 100}%`,
          top: `${(h.y ?? 0.24) * 100}%`,
          transform: `translate(-50%,-50%) scale(${vis}) rotate(${h.tilt ?? -2}deg)`,
          opacity: vis,
          // Blur em 18px: dentro da faixa 12–24 que a literatura chama de
          // "sweet spot". Acima de 30 o fundo vira borrão e some a sensação
          // de VER ATRAVÉS, que é o ponto do vidro.
          backdropFilter: 'blur(18px)',
          WebkitBackdropFilter: 'blur(18px)',
          background: dark ? 'rgba(12,17,28,0.62)' : 'rgba(255,255,255,0.58)',
          // A borda é o que "vende a ilusão de aresta física".
          border: `2px solid ${dark ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.75)'}`,
          borderRadius: size * 0.75,
          padding: `${size * 0.5}px ${size * 0.95}px`,
          boxShadow: '0 28px 70px rgba(0,0,0,0.35)',
          textAlign: 'center',
          // Largura máxima em vez de nowrap: com `nowrap` um card de três
          // palavras estica de borda a borda e cobre o rosto — foi o que o
          // still mostrou com "CÂMERA EM MOVIMENTO". 62% da largura deixa o
          // sujeito respirar e ainda cabe uma frase curta em duas linhas.
          maxWidth: '48%',
          fontFamily,
        }}
      >
        {h.label ? (
          <div
            style={{
              fontSize: size * 0.58,
              fontWeight: 600,
              letterSpacing: 3,
              color: accent,
              marginBottom: size * 0.18,
              textTransform: 'uppercase',
            }}
          >
            {h.label}
          </div>
        ) : null}
        <div
          style={{
            fontSize: size * 1.15,
            fontWeight: 800,
            lineHeight: 1.08,
            letterSpacing: -1,
            color: dark ? '#fff' : '#0c111c',
          }}
        >
          {h.text}
        </div>
        {/* Régua de acento sob o termo: fecha o card e dá a ele um eixo, em
            vez de deixar o texto flutuando na caixa. */}
        <div
          style={{
            height: 4,
            width: `${interpolate(enter, [0, 1], [0, 100], {extrapolateRight: 'clamp'})}%`,
            background: accent,
            borderRadius: 2,
            marginTop: size * 0.34,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

export const GlassCards: React.FC<{spec: HighlightBlock}> = ({spec}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {spec.items.map((h, i) => {
        // 3s é o mínimo de ofício para o espectador ler e absorver.
        const total = Math.round((h.dur ?? 3.2) * fps);
        // O card entra DEPOIS da palavra, não junto. A regra do ofício é que
        // texto reforça e não duplica: se o card e a legenda mostram o mesmo
        // termo no mesmo instante, uma das duas camadas é ruído — e foi
        // exatamente o que o primeiro still mostrou, "movimento" duas vezes na
        // tela. Meio segundo de atraso põe o card sobre a PRÓXIMA palavra da
        // legenda, e as duas camadas voltam a dizer coisas diferentes.
        const atraso = Math.round((spec.offsetS ?? 0.8) * fps);
        return (
          <Sequence
            key={i}
            from={Math.round(h.at * fps) + atraso}
            durationInFrames={total}
            layout="none"
          >
            <One h={h} total={total} fontFamily={spec.fontFamily} />
          </Sequence>
        );
      })}
    </>
  );
};
