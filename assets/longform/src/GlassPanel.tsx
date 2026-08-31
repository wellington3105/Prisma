/**
 * GlassPanel — refracting glass panel (OPUS-VFX-3D § ÉPICO G).
 *
 * A real refraction pass, not a blur pretending to be one. The cut is uploaded
 * to the GPU as a texture and the fragment shader samples it at an OFFSET
 * derived from the panel's surface normal — which is what bending light does.
 * `backdrop-filter: blur()` cannot do this: it blurs what is behind, but every
 * pixel stays where it was, so a straight line crossing the panel edge stays
 * straight. Through real glass it breaks. That break is the reason this file
 * exists instead of a CSS rule.
 *
 * Chromatic dispersion (the "prism") comes from sampling R, G and B at three
 * slightly different offsets: glass has a different index of refraction per
 * wavelength, and per-channel sampling is the cheap, honest model of it.
 *
 * ARCHITECTURE — the part that took two failed attempts to get right:
 * `useOffthreadVideoTexture` must be called in the component that OWNS the
 * <ThreeCanvas>, never inside it. Called from a child, it returned null on
 * every rendered frame and the panel came out opaque grey (shader sampling a
 * null texture reads black; only the sheen and rim terms survived). The canvas
 * ALSO draws the video itself here — a full-frame quad behind the panel —
 * because a sibling DOM <OffthreadVideo> is invisible to the shader. This is
 * the same limitation CustomGraphics.tsx documents for whip-pan/glitch, and
 * WebGL does not remove it: it has to be solved by putting the footage inside
 * the canvas.
 *
 * Gated by `elements.glassPanel`. Without the tick no `glass` block is written
 * and none of this mounts, so an edit that does not use it pays nothing.
 */
import React, {useMemo, useRef} from 'react';
import * as THREE from 'three';
import {useFrame} from '@react-three/fiber';
import {ThreeCanvas, useOffthreadVideoTexture} from '@remotion/three';
import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  staticFile,
  useRemotionEnvironment,
} from 'remotion';

export type GlassSpec = {
  /** Footage the panel refracts. Defaults to the cut. */
  src?: string;
  /** 0..1 of frame width/height. Defaults to a centred 76% x 34% panel. */
  rect?: {x: number; y: number; w: number; h: number};
  /** How hard light bends. 0 = flat pane, 1 = heavy. Default 0.5. */
  intensity?: number;
  /** RGB split at the edges. 0 = none, 1 = pronounced. Default 0.35. */
  dispersion?: number;
  /** Corner radius, in frame-width units. Default 0.03. */
  radius?: number;
  /** Frames the panel takes to settle in. Default 12. */
  enterFrames?: number;
};

const VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * The panel is a rounded rectangle drawn in UV space rather than modelled
 * geometry. A signed-distance field gives an analytically exact edge at any
 * resolution and — the reason it is worth it — its GRADIENT is the surface
 * normal the refraction needs, for free. A bevelled slab would cost geometry
 * and still need a normal map to read as glass.
 */
const FRAG = /* glsl */ `
precision highp float;
varying vec2 vUv;

uniform sampler2D uScene;   // the cut
uniform vec2  uRes;         // frame size in px, for aspect correction
uniform vec4  uRect;        // x, y, w, h in 0..1 frame space
uniform float uRadius;
uniform float uIntensity;
uniform float uDispersion;
uniform float uProgress;    // 0..1 entrance

// Signed distance to a rounded box. Negative inside.
float sdRoundBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

void main() {
  float aspect = uRes.x / uRes.y;
  vec2 centre = uRect.xy + uRect.zw * 0.5;
  vec2 half_  = uRect.zw * 0.5;

  // Aspect-corrected space, so the corner radius is round and not oval.
  vec2 p = (vUv - centre) * vec2(aspect, 1.0);
  vec2 b = half_ * vec2(aspect, 1.0);
  float rad = uRadius * aspect;

  float d = sdRoundBox(p, b, rad);

  // Outside the panel the scene passes through untouched.
  if (d > 0.0) {
    gl_FragColor = texture2D(uScene, vUv);
    return;
  }

  // --- refraction ----------------------------------------------------------
  // The SDF gradient points away from the nearest edge. Light bends hardest at
  // the rim and not at all in the middle of the pane, hence the falloff.
  vec2 e = vec2(1.5 / uRes.x, 1.5 / uRes.y);
  vec2 grad = normalize(vec2(
    sdRoundBox(p + vec2(e.x, 0.0), b, rad) - sdRoundBox(p - vec2(e.x, 0.0), b, rad),
    sdRoundBox(p + vec2(0.0, e.y), b, rad) - sdRoundBox(p - vec2(0.0, e.y), b, rad)
  ) + 1e-6);

  float rim  = 1.0 - smoothstep(0.0, 0.16, -d);   // 1 at the edge → 0 inside
  float bend = uIntensity * 0.09 * rim * uProgress;

  // Per-channel offsets: glass refracts short wavelengths more than long ones.
  float spread = uDispersion * 0.35;
  vec3 col = vec3(
    texture2D(uScene, vUv - grad * bend * (1.0 - spread)).r,
    texture2D(uScene, vUv - grad * bend).g,
    texture2D(uScene, vUv - grad * bend * (1.0 + spread)).b
  );

  // --- surface -------------------------------------------------------------
  // A specular sheen running top-left to bottom-right. Without it the panel
  // reads as a distortion filter rather than a physical object.
  float sheen = pow(clamp(1.0 - (vUv.x - vUv.y) * 0.5 - 0.25, 0.0, 1.0), 3.0);
  col += sheen * 0.10 * uProgress;

  // The edge catches light — this is what separates the panel from its
  // background when the footage behind it happens to be flat.
  col += rim * 0.22 * uProgress;

  gl_FragColor = vec4(col, 1.0);
}
`;

const Panel: React.FC<{spec: GlassSpec; tex: THREE.Texture}> = ({spec, tex}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const {rect = {x: 0.12, y: 0.33, w: 0.76, h: 0.34}} = spec;
  const intensity = spec.intensity ?? 0.5;
  const dispersion = spec.dispersion ?? 0.35;
  const radius = spec.radius ?? 0.03;
  const enterFrames = spec.enterFrames ?? 12;

  const mat = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      uScene: {value: tex},
      uRes: {value: new THREE.Vector2(width, height)},
      uRect: {value: new THREE.Vector4(rect.x, rect.y, rect.w, rect.h)},
      uRadius: {value: radius},
      uIntensity: {value: intensity},
      uDispersion: {value: dispersion},
      uProgress: {value: 0},
    }),
    // Identity must be stable or the material recompiles every frame; the
    // values are refreshed below.
    [width, height],
  );

  const progress = interpolate(frame, [0, enterFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  // Written during render, not in useFrame: on the first pass useFrame runs
  // after the draw, so frame 0 would sample a stale texture.
  uniforms.uScene.value = tex;
  uniforms.uRect.value.set(rect.x, rect.y, rect.w, rect.h);
  uniforms.uRadius.value = radius;
  uniforms.uIntensity.value = intensity;
  uniforms.uDispersion.value = dispersion;
  uniforms.uProgress.value = progress;

  useFrame(() => {
    if (mat.current) mat.current.uniforms.uScene.value = tex;
  });

  return (
    <mesh>
      {/* Full-frame quad. The shader decides what is glass and what is
          pass-through, so the geometry never changes with the panel rect. */}
      <planeGeometry args={[2, 2]} />
      <shaderMaterial ref={mat} vertexShader={VERT} fragmentShader={FRAG} uniforms={uniforms} />
    </mesh>
  );
};

export const GlassPanel: React.FC<{spec: GlassSpec}> = ({spec}) => {
  const {width, height} = useVideoConfig();
  const env = useRemotionEnvironment();

  // Must be called HERE — in the component that owns the canvas. Called from a
  // child of <ThreeCanvas> it resolves to null on every frame.
  const tex = useOffthreadVideoTexture({src: staticFile(spec.src ?? 'cut.mp4')});

  // In the Studio (not rendering) the hook throws by design, and there is no
  // offthread frame server to ask. Rendering nothing there is correct: the
  // preview shows the plain cut, and the glass appears in the render.
  if (!env.isRendering || !tex) return null;

  return (
    <ThreeCanvas
      width={width}
      height={height}
      orthographic
      camera={{left: -1, right: 1, top: 1, bottom: -1, near: 0.1, far: 10, position: [0, 0, 1]}}
    >
      {/* Orthographic on purpose: the panel is a full-frame quad whose shader
          decides what is glass, so it must map 1:1 to the frame. Under the
          default perspective camera a 2x2 quad covered only part of the
          viewport and the panel came out 380x170px instead of the 821x653px
          its rect asked for — measured, not guessed. */}
      <Panel spec={spec} tex={tex} />
    </ThreeCanvas>
  );
};
