/**
 * GlassCard (16:9) — port de shortform/src/GlassCard.tsx para o quadro horizontal.
 * Mesmas chaves de edit-data (`highlights`, variant "prism"|"pill", items[]), mas
 * as medidas vêm da ALTURA do quadro e não da largura: em 16:9 a largura de
 * 9:16 faria a placa ocupar mais da metade da tela. Aqui a placa prisma fica em
 * ~1/3 da largura, ao lado do falante (default x 0.26 = o rect verificado
 * x0.06 w0.40 do painel), e `maxWidth` a impede de passar de 40%.
 *
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

/**
 * `prism` (o padrão) — a moldura de VIDRO-PRISMA 3D: placa de vidro com
 * espessura, em perspectiva que gira devagar, aro iridescente que dispersa a
 * luz em RGB e um reflexo especular que varre a superfície na entrada. É o que
 * o usuário pediu para "Painel de vidro (3D)" no Estilo — a PALAVRA em destaque
 * numa moldura sofisticada — e substitui o painel vazio que só refratava o
 * vídeo (reprovado: um retângulo translúcido sem palavra não comunica nada).
 *
 * `pill` — a etiqueta 2D original, mantida para quem já a usa.
 */
export type CardVariant = 'prism' | 'pill';

export type HighlightBlock = {
  enabled: boolean;
  items: Highlight[];
  variant?: CardVariant;
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

/**
 * Teto de caracteres do card, medido e não estimado.
 *
 * O card é uma pílula de uma linha a ~52% da largura do quadro. Com o corpo em
 * `width*0.046*1.15` e o padding de `size*1.1` de cada lado, o texto começa a
 * transbordar por volta de 14 caracteres em 1080 de largura. "Estabilização"
 * (13) já lê esticado no still; 12 é o último confortável.
 *
 * A regra de ofício por trás do número: o card se lê num RELANCE. Um termo que
 * não cabe em doze caracteres não é etiqueta, é frase — e frase é trabalho da
 * legenda, não do destaque.
 */
const MAX_CHARS_CARD = 12;

const One: React.FC<{h: Highlight; total: number; fontFamily?: string}> = ({
  h,
  total,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
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

  // O card DESLIZA para o lugar enquanto cresce — observado no Reel de
  // referência (card "DSM-5", 28s): ele não brota no ponto final, chega até
  // ele. Só escalar lê como pop-up; deslizar lê como algo entrando em cena.
  // 22px é curto de propósito: deslocamento longo vira transição e rouba a
  // atenção do termo, que é o que deveria ser lido.
  const desliza = interpolate(enter, [0, 1], [22, 0], {extrapolateRight: 'clamp'});

  // Escala em função da largura do quadro: o card ocupa ~46% dela, o que o
  // mantém legível em 1080 vertical sem competir com o rosto.
  //
  // Termos acima do teto encolhem proporcionalmente em vez de estourar a
  // pílula. É a válvula de segurança, não a solução: o lugar de corrigir um
  // termo longo é no edit-data.json, e o gate avisa. Mas um card cortado pela
  // borda da tela é pior que um card 15% menor.
  const excesso = Math.max(1, h.text.length / MAX_CHARS_CARD);
  const size = (height * 0.05) / excesso;

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
          left: `${(h.x ?? 0.74) * 100}%`,
          top: `${(h.y ?? 0.24) * 100}%`,
          transform: `translate(-50%,calc(-50% + ${desliza}px)) scale(${vis}) rotate(${h.tilt ?? -2}deg)`,
          opacity: vis,
          // Blur em 18px: dentro da faixa 12–24 que a literatura chama de
          // "sweet spot". Acima de 30 o fundo vira borrão e some a sensação
          // de VER ATRAVÉS, que é o ponto do vidro.
          backdropFilter: 'blur(18px)',
          WebkitBackdropFilter: 'blur(18px)',
          background: dark ? 'rgba(12,17,28,0.62)' : 'rgba(255,255,255,0.58)',
          // A borda é o que "vende a ilusão de aresta física".
          border: `2px solid ${dark ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.75)'}`,
          // Raio quase-pílula. No Reel de referência o card é um comprimido
          // arredondado, não um retângulo com cantos suavizados — é o que lhe
          // dá o ar de etiqueta e não de caixa de texto. O `size*1.5` faz o
          // raio exceder a meia-altura num card de uma linha, e o browser
          // satura em pílula perfeita.
          borderRadius: size * 1.5,
          padding: `${size * 0.52}px ${size * 1.1}px`,
          boxShadow: '0 28px 70px rgba(0,0,0,0.35)',
          textAlign: 'center',
          // UMA LINHA, sempre. A pílula é definida pelo raio saturado na
          // meia-altura; assim que o texto quebra em duas linhas o card cresce
          // em altura, o raio deixa de saturar e a forma vira caixa — medido no
          // still com "Sem tripé" (9 caracteres). O limite de comprimento é
          // imposto na entrada (`MAX_CHARS_CARD`), não aqui: cortar a palavra
          // no CSS esconderia o erro em vez de apontá-lo.
          whiteSpace: 'nowrap',
          maxWidth: '40%',
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
            fontWeight: 700,
            lineHeight: 1.08,
            // Espaçamento POSITIVO. O -1 anterior comprimia as letras, que é o
            // gesto de manchete; num card pequeno de uma palavra o efeito é o
            // oposto — a referência abre levemente o termo, o que o faz ler
            // como etiqueta e sustenta o peso visual da pílula.
            letterSpacing: 0.5,
            color: dark ? '#fff' : '#0c111c',
          }}
        >
          {h.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Teto do prisma: a placa é mais larga que a pílula (até 80% do quadro). */
const MAX_CHARS_PRISM = 16;

const Prism: React.FC<{h: Highlight; total: number; fontFamily?: string}> = ({h, total, fontFamily}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const accent = h.accent ?? '#ff5200';

  // Entrada: a placa GIRA para dentro do plano (rotateY −38° → −14°) enquanto
  // cresce — lê como objeto físico chegando, não como pop-up. Mola só na
  // entrada; a saída é interpolate para pousar no último frame (D4).
  const enter = spring({frame, fps, config: {damping: 14, mass: 0.6}, durationInFrames: 16});
  const exit = interpolate(frame, [total - 9, total], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const vis = Math.min(enter, exit);
  // Deriva lenta durante a vida inteira: é o que faz o 3D ler como 3D. Uma
  // placa parada em perspectiva parece desenhada torta; girando 8° ela tem volume.
  const drift = interpolate(frame, [0, total], [0, 1], {extrapolateRight: 'clamp'});
  const rotY = -14 + drift * 8 - (1 - enter) * 24 + (1 - exit) * 18;
  const rotX = 7 - drift * 3 - (1 - enter) * 8;
  const scale = 0.86 + 0.14 * vis;

  const excesso = Math.max(1, h.text.length / MAX_CHARS_PRISM);
  const size = (height * 0.056) / excesso;
  const R = size * 0.62;

  // O aro iridescente gira devagar: a luz "corre" pela aresta do prisma.
  const ang = (frame * 3.2) % 360;
  // Reflexo especular: varre a placa uma vez na entrada e, mais suave, no meio.
  const sweep = (from: number, len: number) =>
    interpolate(frame, [from, from + len], [-140, 140], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const s1 = sweep(5, 16);
  const s2 = sweep(Math.round(total * 0.55), 22);

  return (
    <AbsoluteFill style={{pointerEvents: 'none', perspective: 1500}}>
      <div
        style={{
          position: 'absolute',
          left: `${(h.x ?? 0.26) * 100}%`,
          top: `${(h.y ?? 0.32) * 100}%`,
          transform: `translate(-50%,-50%) rotateX(${rotX}deg) rotateY(${rotY}deg) rotateZ(${h.tilt ?? 0}deg) scale(${scale})`,
          transformStyle: 'preserve-3d',
          opacity: vis,
          maxWidth: '40%',
        }}
      >
        {/* Espessura: a mesma placa, recuada no eixo Z — a aresta que se vê de lado. */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: R,
            transform: 'translateZ(-14px)',
            background: 'linear-gradient(160deg, rgba(255,255,255,0.18), rgba(255,255,255,0.03))',
            border: '1px solid rgba(255,255,255,0.18)',
            boxShadow: '0 50px 90px rgba(0,0,0,0.5)',
          }}
        />
        {/* Placa + aro. As franjas R/B deslocadas na sombra são a dispersão. */}
        <div
          style={{
            position: 'relative',
            borderRadius: R,
            boxShadow: '-3px 0 14px rgba(255,50,110,0.22), 3px 0 14px rgba(50,150,255,0.24)',
          }}
        >
          {/* Aro prisma: SÓ o anel. Sem a máscara o gradiente vaza para dentro
              da placa e o vidro inteiro vira degradê arco-íris — foi o primeiro
              still, e lê como adesivo, não como vidro. */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              padding: 2.5,
              borderRadius: R,
              background: `conic-gradient(from ${ang}deg, rgba(255,90,130,0.85), rgba(255,220,120,0.75), rgba(120,255,210,0.7), rgba(110,190,255,0.9), rgba(200,130,255,0.8), rgba(255,90,130,0.85))`,
              WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
              WebkitMaskComposite: 'xor',
              maskComposite: 'exclude',
              zIndex: 2,
            }}
          />
          <div
            style={{
              position: 'relative',
              overflow: 'hidden',
              borderRadius: R,
              padding: `${size * 0.5}px ${size * 0.95}px ${size * 0.58}px`,
              backdropFilter: 'blur(16px) saturate(1.5) brightness(1.06)',
              WebkitBackdropFilter: 'blur(16px) saturate(1.5) brightness(1.06)',
              background:
                'linear-gradient(135deg, rgba(255,255,255,0.26) 0%, rgba(255,255,255,0.07) 42%, rgba(14,18,28,0.42) 100%)',
              boxShadow:
                'inset 0 2px 0 rgba(255,255,255,0.65), inset 0 -2px 0 rgba(0,0,0,0.35), inset 0 0 30px rgba(255,255,255,0.10)',
              whiteSpace: 'nowrap',
              fontFamily,
              textAlign: 'left',
            }}
          >
            {/* Reflexo especular — a luz atravessando o vidro. */}
            {[s1, s2].map((x, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  top: '-40%',
                  bottom: '-40%',
                  left: `${x}%`,
                  width: '45%',
                  transform: 'rotate(18deg)',
                  background: `linear-gradient(90deg, transparent, rgba(255,255,255,${i ? 0.22 : 0.5}), transparent)`,
                  mixBlendMode: 'screen',
                }}
              />
            ))}
            {h.label ? (
              <div style={{display: 'flex', alignItems: 'center', gap: size * 0.28, marginBottom: size * 0.16}}>
                <div style={{width: size * 0.9, height: 3, borderRadius: 2, background: accent, boxShadow: `0 0 12px ${accent}`}} />
                <div
                  style={{
                    fontSize: size * 0.46,
                    fontWeight: 600,
                    letterSpacing: size * 0.09,
                    color: 'rgba(255,255,255,0.86)',
                    textTransform: 'uppercase',
                  }}
                >
                  {h.label}
                </div>
              </div>
            ) : null}
            <div
              style={{
                position: 'relative',
                fontSize: size * 1.22,
                fontWeight: 800,
                lineHeight: 1.04,
                letterSpacing: 0.5,
                color: '#fff',
                // Dispersão também no glifo: franja vermelha à esquerda, azul à
                // direita, sutil — é o "prisma" lido na própria palavra.
                textShadow:
                  '-1.5px 0 rgba(255,60,110,0.45), 1.5px 0 rgba(60,170,255,0.45), 0 4px 22px rgba(0,0,0,0.45)',
              }}
            >
              {h.text}
            </div>
          </div>
        </div>
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
            {(spec.variant ?? 'prism') === 'prism' ? (
              <Prism h={h} total={total} fontFamily={spec.fontFamily} />
            ) : (
              <One h={h} total={total} fontFamily={spec.fontFamily} />
            )}
          </Sequence>
        );
      })}
    </>
  );
};
