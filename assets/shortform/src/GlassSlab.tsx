/**
 * GlassSlab — painel de vidro que EXISTE na cena, não sobre ela.
 *
 * A diferença para `GlassPanel.tsx`: aquele é um shader de tela cheia que
 * recorta um retângulo em coordenadas de viewport — o painel fica colado ao
 * quadro e a cena passa por trás. Este é uma MALHA no espaço 3D: tem posição,
 * rotação e tamanho no mundo reconstruído, e a câmera o vê de ângulos
 * diferentes conforme se move. É o que a referência faz — os painéis
 * acompanham a piscina e o deck em perspectiva, porque estão ali.
 *
 * Três coisas que a referência tem e um retângulo chapado não:
 *   - **curvatura**: o painel é levemente abaulado, então a borda que se afasta
 *     da câmera pega luz diferente da que se aproxima;
 *   - **borda luminosa fina**: é ela que separa o vidro do fundo quando a cena
 *     atrás é clara, e é o detalhe que mais denuncia um retângulo mal-acabado;
 *   - **refração dependente do ângulo**: o desvio cresce nas bordas, onde a
 *     superfície é mais oblíqua à visada (Fresnel).
 *
 * O que ele NÃO faz, e é uma limitação honesta: não amostra a footage atrás de
 * si. Um shader dentro de uma cena 3D não tem acesso ao que a câmera já
 * desenhou — para isso seria preciso um render target por painel. Ele distorce
 * um gradiente derivado do próprio ângulo, o que lê como vidro sobre fundo
 * variado, e não como lente sobre imagem nítida.
 */
import React, {useMemo, useRef} from 'react';
import * as THREE from 'three';
import {useFrame} from '@react-three/fiber';

export type SlabSpec = {
  /** Posição no mundo reconstruído. */
  at: [number, number, number];
  /** Rotação em graus. Com `onPlane`, herdada do plano. */
  rotation?: [number, number, number];
  w?: number;
  h?: number;
  /** Abaulamento. 0 = plano, 0.1 = bem curvo. Default 0.04. */
  curve?: number;
  /** Cor da borda luminosa. */
  edge?: string;
  /** Tinte do vidro. */
  tint?: string;
  /** 0..1, opacidade geral. Default 0.35 — vidro é quase transparente. */
  opacity?: number;
};

const VERT = /* glsl */ `
varying vec2 vUv;
varying vec3 vNormalW;
varying vec3 vViewW;

uniform float uCurve;

void main() {
  vUv = uv;
  vec3 p = position;
  // Abaulamento: desloca ao longo da normal em função da distância ao centro,
  // com queda quadrática — no meio empurra, nas bordas não.
  float r2 = uv.x * uv.x + uv.y * uv.y;
  p.z += uCurve * (0.25 - (uv.x - 0.5) * (uv.x - 0.5) - (uv.y - 0.5) * (uv.y - 0.5)) * 4.0;

  vec4 wp = modelMatrix * vec4(p, 1.0);
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vViewW = normalize(cameraPosition - wp.xyz);
  gl_Position = projectionMatrix * viewMatrix * wp;
}
`;

const FRAG = /* glsl */ `
precision highp float;
varying vec2 vUv;
varying vec3 vNormalW;
varying vec3 vViewW;

uniform vec3  uTint;
uniform vec3  uEdge;
uniform float uOpacity;
uniform float uProgress;

void main() {
  // Fresnel: a superfície reflete mais quando vista de raspão. É o que faz o
  // vidro parecer vidro em vez de plástico fosco.
  float fres = pow(1.0 - abs(dot(normalize(vNormalW), normalize(vViewW))), 2.5);

  // Borda. Espessura calibrada contra a referência: em 0.012 o painel sumia
  // sobre fundo claro — a borda existia mas não separava nada. 0.022 com um
  // halo interno é o que dá a moldura branca nítida que a referência tem.
  vec2 d = min(vUv, 1.0 - vUv);
  float dm = min(d.x, d.y);
  float borda = 1.0 - smoothstep(0.0, 0.022, dm);
  float halo  = (1.0 - smoothstep(0.0, 0.10, dm)) * 0.35;

  // Dispersão na borda: as três componentes decaem em larguras diferentes, e a
  // franja colorida é o que denuncia vidro em vez de acrílico.
  float dr = 1.0 - smoothstep(0.0, 0.030, dm);
  float db = 1.0 - smoothstep(0.0, 0.016, dm);

  vec3 col = uTint * (0.45 + fres * 0.9);
  col += uEdge * borda * 2.2;
  col += vec3(dr, borda, db) * 0.40;

  // O corpo do vidro precisa de opacidade própria, não só Fresnel: contra um
  // fundo claro o Fresnel sozinho zera no centro e o painel desaparece.
  float a = (uOpacity * (0.55 + fres * 0.75) + borda * 1.0 + halo) * uProgress;
  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));
}
`;

const hex = (s: string) => new THREE.Color(s);

export const GlassSlab: React.FC<{spec: SlabSpec; progress?: number}> = ({
  spec,
  progress = 1,
}) => {
  const mat = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uCurve: {value: spec.curve ?? 0.04},
      uTint: {value: hex(spec.tint ?? '#bfe8ff')},
      uEdge: {value: hex(spec.edge ?? '#ffffff')},
      uOpacity: {value: spec.opacity ?? 0.35},
      uProgress: {value: progress},
    }),
    [],
  );

  useFrame(() => {
    if (!mat.current) return;
    const u = mat.current.uniforms;
    u.uCurve.value = spec.curve ?? 0.04;
    u.uTint.value = hex(spec.tint ?? '#bfe8ff');
    u.uEdge.value = hex(spec.edge ?? '#ffffff');
    u.uOpacity.value = spec.opacity ?? 0.35;
    u.uProgress.value = progress;
  });

  const rot = useMemo(
    () =>
      (spec.rotation ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180) as [number, number, number],
    [spec.rotation],
  );

  return (
    <mesh position={spec.at} rotation={rot}>
      {/* Segmentado: o abaulamento acontece no vertex shader, e um plano de 1x1
          quad não teria vértices para curvar. */}
      <planeGeometry args={[spec.w ?? 1.4, spec.h ?? 0.9, 24, 24]} />
      <shaderMaterial
        ref={mat}
        vertexShader={VERT}
        fragmentShader={FRAG}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
};
