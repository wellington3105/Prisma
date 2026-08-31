/**
 * ShaderTransition — cut transitions that displace real pixels
 * (OPUS-VFX-3D § ÉPICO T).
 *
 * Why this exists next to CustomGraphics' flash/whip-pan/glitch: those three
 * are overlay-only, and that file says so plainly — they have "no handle on the
 * video layer beneath". The glitch paints cyan/magenta bands that STAND IN for
 * a channel split; it never splits anything. Same for the whip-pan's streaks.
 *
 * These two do the real thing, because the footage is inside the canvas as a
 * texture and the shader can move the pixels themselves:
 *
 *   'displace' — the frame tears along a noise field, strongest at the cut and
 *                resolving either side of it. A dissolve through turbulence.
 *   'refract'  — the frame passes through a lens that swells and collapses, so
 *                the cut happens THROUGH glass. Same optics as GlassPanel,
 *                driven by time instead of a fixed rect.
 *
 * Gated by `elements.shaderCut`. Without the tick the writer never emits these
 * types and no canvas is created — flash/whip-pan/glitch keep working exactly
 * as before, and this file is dead weight that costs nothing.
 */
import React, {useMemo, useRef} from 'react';
import * as THREE from 'three';
import {ThreeCanvas, useOffthreadVideoTexture} from '@remotion/three';
import {
  AbsoluteFill,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  useRemotionEnvironment,
} from 'remotion';
// Same import direction CustomGraphics.tsx already uses for Sfx.
import {Sfx} from './Main';

/**
 * Presets nomeados de references/direction.md § Presets. São o vocabulário
 * fechado de duração: escolher "0.37s" a olho é o que produz um vídeo em que
 * cada transição dura um tempo diferente sem motivo.
 *
 * A tabela ali está em segundos; aqui em frames a 30fps, que é o que o
 * template conta. Intensidade acompanha a duração — uma transição de 0.15s
 * precisa ser forte para ser percebida; uma de 0.7s, contida.
 */
export const CUT_PRESETS = {
  instant: {frames: 5, intensity: 1.0},   // 0.15s · expo.inOut
  snappy: {frames: 6, intensity: 1.0},    // 0.20s · power4.inOut
  smooth: {frames: 12, intensity: 0.8},   // 0.40s · power2.inOut
  dramatic: {frames: 15, intensity: 0.9}, // 0.50s · power3
  gentle: {frames: 18, intensity: 0.6},   // 0.60s · sine.inOut
  luxe: {frames: 21, intensity: 0.5},     // 0.70s · power1.inOut
} as const;

/** Energia → preset. Tabela Energia→duração de direction.md. */
export const ENERGY_PRESET = {
  calm: 'gentle',
  medium: 'smooth',
  high: 'snappy',
} as const;

export type CutPreset = keyof typeof CUT_PRESETS;
export type Energy = keyof typeof ENERGY_PRESET;

export type ShaderCut = {
  at: number;
  type: 'displace' | 'refract';
  /** 0..1. Sem isto, vem do preset. */
  intensity?: number;
  /** Total de frames. Sem isto, vem do preset. */
  frames?: number;
  /** Preset nomeado. Sem isto, vem de `direction.energy`; sem ela, 'smooth'. */
  preset?: CutPreset;
  src?: string;
  /** Cut SFX, same contract as the overlay transitions. */
  sfx?: string;
  volume?: number;
};

/**
 * Resolve duração e intensidade na ordem: valor explícito > preset do corte >
 * energia do vídeo > default.
 *
 * A ordem importa: o preset é a regra, o valor explícito é a exceção. Escrever
 * `frames` direto continua possível — mas quem não escreve recebe um número
 * que veio da doutrina, não de um default arbitrário.
 */
export const resolveCut = (cut: ShaderCut, energy?: Energy) => {
  const nome = cut.preset ?? (energy ? ENERGY_PRESET[energy] : 'smooth');
  const p = CUT_PRESETS[nome] ?? CUT_PRESETS.smooth;
  return {
    frames: cut.frames ?? p.frames,
    intensity: cut.intensity ?? p.intensity,
  };
};

const VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * One shader for both transitions, branching on uMode. Two materials would
 * mean two compiles and two code paths to keep in sync for what is the same
 * idea — sample the frame somewhere other than where the pixel is.
 *
 * uT runs 0 → 1 → 0 across the window, peaking on the cut: the distortion
 * grows into the cut and unwinds out of it, so the transition reads as one
 * gesture rather than an effect that starts and stops.
 */
const FRAG = /* glsl */ `
precision highp float;
varying vec2 vUv;

uniform sampler2D uScene;
uniform vec2  uRes;
uniform float uT;         // 0..1..0, peaks at the cut
uniform float uAmount;    // intensity
uniform int   uMode;      // 0 = displace, 1 = refract

// Value noise. Cheap, and its gradient is smooth enough to tear an image
// without the result reading as television static.
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1,0)), u.x),
             mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
}

void main() {
  float aspect = uRes.x / uRes.y;
  vec2 uv = vUv;
  float k = uT * uAmount;

  if (uMode == 0) {
    // ---- displace: tear along a turbulent field ---------------------------
    // Two octaves at different scales: the coarse one moves whole regions, the
    // fine one breaks their edges. One octave alone looks like a wobble.
    // Scales are deliberately low. At 6.0/22.0 the field cycles many times
    // across the frame and every straight line becomes a separate squiggle:
    // rendered, that read as abstract noise, not as a cut — the picture was
    // gone rather than disturbed. 2.2/5.0 keeps regions recognisable while
    // they slide, which is what a transition needs.
    float n1 = noise(vUv * 2.2 + vec2(0.0, uT * 1.2));
    float n2 = noise(vUv * 5.0 - vec2(uT * 1.6, 0.0));
    vec2 dir = normalize(vec2(n1 - 0.5, n2 - 0.5) + 1e-6);
    // 0.10 of the frame is ~190px at 1080 wide — far past legibility.
    uv += dir * k * 0.028;

    // Channels tear by slightly different amounts — the same wavelength idea
    // as the glass panel, here as a by-product of the tear rather than a lens.
    float sp = k * 0.006;
    gl_FragColor = vec4(
      texture2D(uScene, uv + dir * sp).r,
      texture2D(uScene, uv).g,
      texture2D(uScene, uv - dir * sp).b,
      1.0
    );
    return;
  }

  // ---- refract: the cut happens through a lens ----------------------------
  // Barrel distortion around the centre, swelling into the cut. Aspect
  // correction keeps the lens circular on a 9:16 frame instead of an ellipse.
  vec2 c = (vUv - 0.5) * vec2(aspect, 1.0);
  float r = length(c);
  float lens = 1.0 - k * 0.55 * exp(-r * r * 3.2);
  vec2 warped = c * lens;
  uv = warped / vec2(aspect, 1.0) + 0.5;

  float sp = k * 0.018 * smoothstep(0.0, 0.6, r);   // dispersion grows outward
  vec2 rad = normalize(c + 1e-6) / vec2(aspect, 1.0);
  vec3 col = vec3(
    texture2D(uScene, uv + rad * sp).r,
    texture2D(uScene, uv).g,
    texture2D(uScene, uv - rad * sp).b
  );

  // A brief bloom at the peak, so the cut has a beat and not just a wobble.
  col += k * 0.12 * (1.0 - smoothstep(0.0, 0.5, r));
  gl_FragColor = vec4(col, 1.0);
}
`;

const Pass: React.FC<{cut: ShaderCut; tex: THREE.Texture; localFrame: number; total: number}> = ({
  cut,
  tex,
  localFrame,
  total,
}) => {
  const {width, height} = useVideoConfig();
  const mat = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uScene: {value: tex},
      uRes: {value: new THREE.Vector2(width, height)},
      uT: {value: 0},
      uAmount: {value: cut.intensity ?? 1},
      uMode: {value: cut.type === 'refract' ? 1 : 0},
    }),
    [width, height],
  );

  // Triangle 0 → 1 → 0. sin() would ease the peak too softly for a cut, which
  // wants to arrive.
  const half = total / 2;
  const t = 1 - Math.abs(localFrame - half) / half;

  uniforms.uScene.value = tex;
  uniforms.uT.value = Math.max(0, Math.min(1, t));
  uniforms.uAmount.value = cut.intensity ?? 1;
  uniforms.uMode.value = cut.type === 'refract' ? 1 : 0;

  return (
    <mesh>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial ref={mat} vertexShader={VERT} fragmentShader={FRAG} uniforms={uniforms} />
    </mesh>
  );
};

const OneTransition: React.FC<{cut: ShaderCut; total: number}> = ({cut, total}) => {
  const {width, height} = useVideoConfig();
  const localFrame = useCurrentFrame();
  const env = useRemotionEnvironment();

  // Must be called by the owner of the canvas, never inside it — from a child
  // it resolves to null on every rendered frame.
  const tex = useOffthreadVideoTexture({src: staticFile(cut.src ?? 'cut.mp4')});

  // In the Studio the hook throws by design (no offthread frame server), so
  // the preview shows the plain cut and the effect appears in the render.
  if (!env.isRendering || !tex) return null;

  return (
    <ThreeCanvas
      width={width}
      height={height}
      orthographic
      camera={{left: -1, right: 1, top: 1, bottom: -1, near: 0.1, far: 10, position: [0, 0, 1]}}
    >
      <Pass cut={cut} tex={tex} localFrame={localFrame} total={total} />
    </ThreeCanvas>
  );
};

export const ShaderTransitions: React.FC<{items: ShaderCut[]; energy?: Energy}> = ({
  items,
  energy,
}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {items.map((cut, i) => {
        const {frames: total, intensity} = resolveCut(cut, energy);
        // Centre the window on the cut. VIDEO_LAG (+1) matches the one
        // CustomGraphics applies: OffthreadVideo draws the source frame at or
        // before frame/fps, so an uncompensated effect fires one frame early.
        const centre = Math.round(cut.at * fps) + 1;
        const from = Math.max(0, centre - Math.floor(total / 2));
        return (
          <Sequence key={i} from={from} durationInFrames={total} layout="none">
            <AbsoluteFill>
              <OneTransition cut={{...cut, intensity}} total={total} />
            </AbsoluteFill>
            {/* The click lands ON the cut, not at the window's start — the
                window opens before it. Same file and level the overlay
                transitions use, since it is the same editorial beat. */}
            <Sequence from={centre - from} durationInFrames={10} layout="none">
              <Sfx src={cut.sfx ?? 'cut-click.mp3'} volume={cut.volume ?? 0.9} />
            </Sequence>
          </Sequence>
        );
      })}
    </>
  );
};
