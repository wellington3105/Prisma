/**
 * GLProbe — sonda de verificação do render WebGL headless (OPUS-VFX-3D, story V2).
 *
 * Esta composição NÃO faz parte de nenhum vídeo entregue. Existe para responder
 * uma única pergunta, com pixels em vez de fé: **o Chromium headless da Remotion
 * consegue renderizar WebGL nesta máquina, e com qual backend de GL?**
 *
 * Por que ela existe: `remotion render` não usa WebGL real por padrão — o
 * backend é escolhido pela flag `--gl` (`angle`, `swiftshader`, `angle-egl`…).
 * Sem o backend certo a ThreeCanvas rende frames PRETOS, e o sintoma parece
 * "o shader não funciona" quando o defeito está no invocador. Descobrir isso
 * depois de construir os épicos G/B/T custaria a sessão inteira.
 *
 * Como ler o resultado:
 *   - Quadrado LARANJA girando sobre fundo azul-escuro  → WebGL vivo. Prossiga.
 *   - Frame totalmente PRETO                            → backend de GL errado.
 *   - Frame AZUL sem o quadrado                          → canvas ok, geometria não.
 *
 * O fundo é azul-escuro (não preto) de propósito: distingue "não renderizou
 * nada" de "renderizou o fundo mas não a geometria" — dois defeitos diferentes
 * que um fundo preto tornaria indistinguíveis.
 */
import React from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig, AbsoluteFill} from 'remotion';

const Spinner: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;

  return (
    <mesh rotation={[t * 0.9, t * 1.3, 0]}>
      <boxGeometry args={[2.2, 2.2, 2.2]} />
      {/* meshBasicMaterial não depende de luz: se o cubo não aparecer, o
          problema é o pipeline de GL, não a iluminação da cena. */}
      <meshBasicMaterial color="#ff7a1a" />
    </mesh>
  );
};

export const GLProbe: React.FC = () => {
  const {width, height} = useVideoConfig();

  return (
    <AbsoluteFill style={{backgroundColor: '#0b1a2e'}}>
      <ThreeCanvas width={width} height={height} orthographic={false}>
        <Spinner />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
