/**
 * kit/three — moldura para cenas 3D sob medida (three.js via @remotion/three).
 *
 * Mesmo caminho dos cards `chrome`: precisa de WebGL, então o render usa
 * `--gl=angle` (render_phase2.py só detecta sozinho o que o edit-data declara —
 * para uma cena 3D própria, passe `--gl=angle` ou ponha `"scene3d": true` no edit-data).
 *
 * A câmera é perspectiva com 1 unidade de mundo = 1 px do quadro no plano z=0:
 * posicione objetos em pixels (`pxToWorld`) e eles caem onde o HTML cairia.
 * Fundo transparente — vai por cima do vídeo.
 */
import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';

const FOV = 30;

/** px do quadro (origem no canto superior esquerdo) -> coordenada de mundo [x, y] */
export const pxToWorld = (x: number, y: number, width: number, height: number): [number, number] => [x - width / 2, height / 2 - y];

const Tone: React.FC = () => {
  const {gl} = useThree();
  gl.toneMapping = THREE.ACESFilmicToneMapping;
  gl.toneMappingExposure = 1;
  return null;
};

export const Scene3D: React.FC<{children: React.ReactNode; style?: React.CSSProperties}> = ({children, style}) => {
  const {width, height} = useVideoConfig();
  const z = height / 2 / Math.tan(THREE.MathUtils.degToRad(FOV / 2));
  return (
    <AbsoluteFill style={{pointerEvents: 'none', ...style}}>
      <ThreeCanvas width={width} height={height} camera={{fov: FOV, near: 1, far: z * 6, position: [0, 0, z]}} gl={{alpha: true, antialias: true}}>
        <Tone />
        <ambientLight intensity={0.7} />
        <directionalLight position={[-300, 400, 600]} intensity={2.2} />
        {children}
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
