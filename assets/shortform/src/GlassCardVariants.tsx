/**
 * GlassCardVariants — the four 3D-looking card styles of `highlights`
 * (`variant`: "keynote" | "studio" | "hud" | "chrome"), next to the original
 * "prism" and "pill" in GlassCard.tsx. THIS FILE IS IDENTICAL IN BOTH TEMPLATES
 * (shortform + longform): the host GlassCard.tsx decides the numbers that depend
 * on the aspect and passes them in —
 *     size      the prism's base size (9:16: width*0.052 · 16:9: height*0.056)
 *     availPx   the widest the card may be (9:16: 82% of width · 16:9: 40%)
 *     cx, cy    centre, 0..1 of the frame (the item's x / y, host default)
 * — so every look scales with the frame and renders the same at 1080p and 4K.
 * Same keys as prism: text, label, at, dur, x, y (+ accent, `tone` on the block).
 *
 *   keynote  Apple-keynote language: frosted glass, very light, very large word,
 *            small label BELOW, generous padding, one slow specular sweep after
 *            it settles. `tone`: "dark" (default, graphite) | "light" (white).
 *            Inter (open) — no Apple typeface, logo or trademark is used.
 *   studio   colour-grading-suite language: matte black panel, thin orange bar on
 *            the left, monospace readout ("LABEL · 01"), tick ruler. Digits roll
 *            to the value when it is numeric, otherwise the word types on.
 *   hud      hologram: cyan corner brackets DRAW in, a scan line passes, the text
 *            decodes (scramble -> final) in monospace over a faint grid.
 *   chrome   the WORD as real extruded metal (three.js TextGeometry, PBR metal,
 *            PMREM environment — no HDR download), like a car badge. Needs WebGL:
 *            render_phase2.py adds --gl=angle by itself when it sees it.
 *
 * Motion (references/motion-craft.md): opacity/focus expo.out short, position
 * power3.out ~0.5s, exit ~0.25s power3.in. Never a bounce on the exit.
 */
import React, {useMemo} from 'react';
import * as THREE from 'three';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import {FontLoader} from 'three/examples/jsm/loaders/FontLoader.js';
import {TextGeometry} from 'three/examples/jsm/geometries/TextGeometry.js';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadPlexMono} from '@remotion/google-fonts/IBMPlexMono';
import {loadFont as loadJetBrains} from '@remotion/google-fonts/JetBrainsMono';
import {measureText} from '@remotion/layout-utils';
// Inter Bold outlines as a three.js typeface (OFL 1.1 — see fonts/OFL-Inter.txt).
import interBold from './fonts/inter-bold.typeface.json';

const INTER = loadInter('normal', {weights: ['300', '500']}).fontFamily;
const PLEX = loadPlexMono('normal', {weights: ['400', '500', '600']}).fontFamily;
const JETBRAINS = loadJetBrains('normal', {weights: ['400', '500']}).fontFamily;

export type VariantId = 'keynote' | 'studio' | 'hud' | 'chrome';
export const NEW_VARIANTS: readonly string[] = ['keynote', 'studio', 'hud', 'chrome'];

export type VariantItem = {text: string; label?: string; accent?: string};
type Props = {
  variant: VariantId;
  h: VariantItem;
  total: number;
  size: number;
  availPx: number;
  cx: number; // 0..1
  cy: number; // 0..1
  tone?: 'light' | 'dark';
  index: number; // 1-based, for "LABEL · 01"
};

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const expoOut = Easing.out(Easing.exp);
const cubicOut = Easing.out(Easing.cubic); // power3.out
const cubicIn = Easing.in(Easing.cubic); // power3.in
const hash = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// power3.out progress from `from` over `len` frames
const prog = (f: number, from: number, len: number, ease: (t: number) => number = cubicOut) =>
  interpolate(f, [from, from + len], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});
// exit ~0.25s power3.in: 0 (on screen) -> 1 (gone)
const exitOf = (f: number, total: number, fps: number) => {
  const len = Math.max(4, Math.round(fps * 0.25));
  return interpolate(f, [total - len, total], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: cubicIn});
};

const widthOf = (text: string, family: string, px: number, weight: number, spacing = 0) =>
  measureText({text, fontFamily: family, fontSize: px, fontWeight: weight, letterSpacing: `${spacing}px`}).width;

/** largest font size <= `base` that keeps `text` within `avail` px */
const fit = (text: string, family: string, base: number, weight: number, avail: number) => {
  const w = widthOf(text, family, base, weight);
  return w > avail ? Math.floor((base * avail) / w) : base;
};

const Anchor: React.FC<{cx: number; cy: number; children: React.ReactNode; style?: React.CSSProperties}> = ({cx, cy, children, style}) => (
  <AbsoluteFill style={{pointerEvents: 'none'}}>
    <div style={{position: 'absolute', left: `${cx * 100}%`, top: `${cy * 100}%`, transform: 'translate(-50%,-50%)', ...style}}>{children}</div>
  </AbsoluteFill>
);

// ============ KEYNOTE =========================================================
const Keynote: React.FC<Props> = ({h, total, size, availPx, cx, cy, tone = 'dark'}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const light = tone === 'light';
  const pad = size * 1.05;
  const px = fit(h.text, INTER, size * 1.6, 300, availPx - pad * 2);

  // soft spring rise (position) + opacity/focus on expo.out + blur-to-sharp
  const rise = spring({frame: f, fps, config: {damping: 22, mass: 0.7, stiffness: 120}, durationInFrames: 16});
  const fade = prog(f, 0, 7, expoOut);
  const blur = (1 - prog(f, 0, 11, expoOut)) * size * 0.28;
  const out = exitOf(f, total, fps);
  const opacity = fade * (1 - out);
  const y = (1 - rise) * size * 0.7 + out * size * 0.25;
  const scale = (0.96 + 0.04 * rise) * (1 - out * 0.02);

  // one specular sweep across the glass, after it settles
  const sweep = interpolate(f, [20, 52], [-70, 150], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});

  const bg = light ? 'rgba(245,245,247,0.88)' : 'rgba(29,29,31,0.74)';
  const ink = light ? '#1d1d1f' : '#f5f5f7';
  const sub = light ? '#6e6e73' : '#a1a1a6';
  const radius = size * 0.8;
  return (
    <Anchor cx={cx} cy={cy}>
      <div
        style={{
          position: 'relative',
          opacity,
          transform: `translateY(${y}px) scale(${scale})`,
          filter: blur > 0.3 ? `blur(${blur}px)` : undefined,
          padding: `${pad * 0.85}px ${pad}px ${pad * (h.label ? 0.78 : 0.85)}px`,
          borderRadius: radius,
          overflow: 'hidden',
          background: bg,
          backdropFilter: 'blur(34px) saturate(1.8)',
          WebkitBackdropFilter: 'blur(34px) saturate(1.8)',
          border: `1px solid ${light ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.14)'}`,
          boxShadow: light
            ? `0 ${size * 0.5}px ${size * 1.4}px rgba(0,0,0,0.28), 0 ${size * 0.08}px ${size * 0.25}px rgba(0,0,0,0.16)`
            : `0 ${size * 0.5}px ${size * 1.5}px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.12)`,
          fontFamily: INTER,
          textAlign: 'left',
          whiteSpace: 'nowrap',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: '-30%',
            bottom: '-30%',
            left: `${sweep}%`,
            width: '38%',
            transform: 'rotate(16deg)',
            background: `linear-gradient(90deg, transparent, rgba(255,255,255,${light ? 0.75 : 0.2}), transparent)`,
            mixBlendMode: light ? 'soft-light' : 'screen',
          }}
        />
        <div style={{position: 'relative', fontSize: px, fontWeight: 300, lineHeight: 1.02, letterSpacing: -px * 0.025, color: ink}}>{h.text}</div>
        {h.label ? (
          <div style={{position: 'relative', marginTop: px * 0.32 * 0.35, fontSize: px * 0.32, fontWeight: 400, letterSpacing: px * 0.32 * 0.01, color: sub, lineHeight: 1.1}}>{h.label}</div>
        ) : null}
      </div>
    </Anchor>
  );
};

// ============ STUDIO ==========================================================
const Studio: React.FC<Props> = ({h, total, size, availPx, cx, cy, index}) => {
  const f = useCurrentFrame();
  const {fps, height: frameH} = useVideoConfig();
  const accent = h.accent ?? '#ff7a1a';
  const px = fit(h.text, PLEX, size * 1.45, 500, availPx - size * 1.6);
  const headPx = Math.max(px * 0.29, 22 * (frameH / 1080));
  const slide = prog(f, 0, 10, expoOut); // panel in fast
  const out = exitOf(f, total, fps);
  const opacity = prog(f, 0, 5, expoOut) * (1 - out);
  const x = (1 - slide) * -size * 2.2 + out * size * 0.6;

  // numeric -> digits roll to the value; otherwise the word types on
  const m = h.text.match(/^([^\d-]*)(-?\d[\d.,]*)(.*)$/);
  const countP = prog(f, 5, 20, expoOut);
  let shown = h.text;
  if (m) {
    const raw = m[2];
    const dec = /[.,]\d{1,2}$/.test(raw) ? raw.split(/[.,]/).pop()!.length : 0;
    const val = parseFloat(raw.replace(/[.,](?=\d{3}(\D|$))/g, '').replace(',', '.'));
    if (Number.isFinite(val)) {
      const cur = val * countP;
      const body = countP >= 1 ? raw : cur.toLocaleString('pt-BR', {minimumFractionDigits: dec, maximumFractionDigits: dec});
      shown = m[1] + body + m[3];
    }
  } else {
    const n = Math.round(h.text.length * prog(f, 6, 16, Easing.linear));
    shown = h.text.slice(0, n);
  }
  const typing = !m && shown.length < h.text.length;
  const ticks = 36;
  const ruler = prog(f, 8, 16, cubicOut);
  const header = `${(h.label ?? 'READOUT').toUpperCase()} · ${String(index).padStart(2, '0')}`;
  return (
    <Anchor cx={cx} cy={cy}>
      <div
        style={{
          position: 'relative',
          opacity,
          transform: `translateX(${x}px)`,
          background: 'linear-gradient(180deg,#141516 0%,#0e0f10 100%)',
          border: '1px solid #2b2e31',
          borderLeft: 'none',
          borderRadius: size * 0.12,
          padding: `${size * 0.5}px ${size * 0.8}px ${size * 0.55}px ${size * 0.95}px`,
          boxShadow: `0 ${size * 0.4}px ${size * 1.1}px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.05)`,
          fontFamily: PLEX,
          whiteSpace: 'nowrap',
          minWidth: size * 5,
        }}
      >
        <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: Math.max(3, size * 0.075), background: accent, boxShadow: `0 0 ${size * 0.35}px ${accent}66`}} />
        <div style={{fontSize: headPx, fontWeight: 500, letterSpacing: headPx * 0.18, color: '#8e9297', marginBottom: headPx * 0.8}}>{header}</div>
        <div style={{fontSize: px, fontWeight: 500, lineHeight: 1.05, color: '#f3f3f1', minHeight: px * 1.05, letterSpacing: -px * 0.01}}>
          {shown}
          {typing ? <span style={{color: accent}}>▌</span> : null}
        </div>
        <div style={{marginTop: size * 0.42, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', height: size * 0.3, clipPath: `inset(0 ${(1 - ruler) * 100}% 0 0)`}}>
          {Array.from({length: ticks + 1}).map((_, i) => (
            <div key={i} style={{width: Math.max(1, size * 0.02), height: i % 5 === 0 ? '100%' : '48%', background: i === 0 ? accent : i % 5 === 0 ? '#9a9ea3' : '#4b4f53'}} />
          ))}
        </div>
      </div>
    </Anchor>
  );
};

// ============ HUD =============================================================
const SCRAMBLE = '01<>/\\|#%&@$*+=?';
const Hud: React.FC<Props> = ({h, total, size, availPx, cx, cy}) => {
  const f = useCurrentFrame();
  const {fps, height: frameH} = useVideoConfig();
  const cyan = h.accent ?? '#4fe3ff';
  const px = fit(h.text, JETBRAINS, size * 1.25, 500, availPx - size * 2.2);
  const headPx = Math.max(px * 0.29, 22 * (frameH / 1080));
  const out = exitOf(f, total, fps);
  const draw = prog(f, 0, 8, Easing.out(Easing.quad)); // brackets draw in ~8 frames
  const scan = interpolate(f, [8, 22], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const bodyIn = prog(f, 6, 6, expoOut);
  const L = size * 0.62; // bracket arm
  const sw = Math.max(1.5, size * 0.03);
  // decode: left to right, scramble until each char's turn
  const chars = [...h.text];
  const t0 = 14;
  const span = 18;
  const text = chars
    .map((c, i) => {
      if (c === ' ') return ' ';
      const at = t0 + (i / Math.max(1, chars.length)) * span;
      if (f >= at + 3) return c;
      return f < t0 - 2 ? ' ' : SCRAMBLE[Math.floor(hash(Math.floor(f / 2) * 31 + i) * SCRAMBLE.length)];
    })
    .join('');
  const header = `SCAN · ${(h.label ?? 'TARGET').toUpperCase()}`;
  const W = Math.max(widthOf(h.text, JETBRAINS, px, 500), size * 5);
  const padX = size * 0.95;
  const padY = size * 0.7;
  const corner = (rot: number, style: React.CSSProperties) => (
    <svg width={L} height={L} viewBox={`0 0 ${L} ${L}`} style={{position: 'absolute', overflow: 'visible', ...style, transform: `rotate(${rot}deg)`}}>
      <path d={`M0 ${L} V0 H${L}`} fill="none" stroke={cyan} strokeWidth={sw} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} style={{filter: `drop-shadow(0 0 ${size * 0.08}px ${cyan})`}} />
    </svg>
  );
  return (
    <Anchor cx={cx} cy={cy}>
      <div
        style={{
          position: 'relative',
          opacity: 1 - out,
          transform: `translateY(${out * size * 0.2}px)`,
          padding: `${padY}px ${padX}px`,
          background: `rgba(4,16,24,${0.5 * bodyIn})`,
          backdropFilter: 'blur(10px)',
          WebkitBackdropFilter: 'blur(10px)',
          backgroundImage: `linear-gradient(${cyan}14 1px, transparent 1px), linear-gradient(90deg, ${cyan}14 1px, transparent 1px)`,
          backgroundSize: `${size * 0.45}px ${size * 0.45}px`,
          fontFamily: JETBRAINS,
          whiteSpace: 'nowrap',
          width: W + padX * 2,
          boxSizing: 'content-box',
        }}
      >
        {corner(0, {left: 0, top: 0})}
        {corner(90, {right: 0, top: 0})}
        {corner(180, {right: 0, bottom: 0})}
        {corner(270, {left: 0, bottom: 0})}
        <div style={{position: 'absolute', left: 0, right: 0, top: `${scan * 100}%`, height: Math.max(2, size * 0.04), opacity: scan > 0 && scan < 1 ? 0.9 : 0, background: `linear-gradient(90deg, transparent, ${cyan}, transparent)`, boxShadow: `0 0 ${size * 0.35}px ${cyan}`}} />
        <div style={{fontSize: headPx, letterSpacing: headPx * 0.2, color: cyan, opacity: 0.95 * bodyIn, marginBottom: headPx * 0.8}}>{header}</div>
        <div style={{fontSize: px, fontWeight: 500, lineHeight: 1.05, color: '#e9fbff', letterSpacing: 0, textShadow: `0 0 ${size * 0.3}px ${cyan}aa, 0 ${size * 0.05}px ${size * 0.2}px rgba(0,0,0,0.6)`, minHeight: px * 1.05}}>{text}</div>
      </div>
    </Anchor>
  );
};

// ============ CHROME ==========================================================
const FONT = new FontLoader().parse(interBold as unknown as Parameters<FontLoader['parse']>[0]);

// A studio environment built locally (no HDR download), designed for MIRROR
// chrome: a bright sky above a dark horizon band, a near-black floor, and three
// soft-box strips. Polished metal shows what is around it, so the classic
// black/white banding of a car badge comes from this contrast — a soft grey room
// reads as satin aluminium. Values are linear and kept finite (the brightest
// strip is ~6, not 50) so the tone-mapped faces stay below clipping.
function buildEnv(gl: THREE.WebGLRenderer): THREE.Texture {
  const scene = new THREE.Scene();
  const geo = new THREE.SphereGeometry(20, 64, 32);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i) / 20; // -1..1
    let k: number;
    if (y > 0.1) k = 0.25 + 1.5 * Math.pow((y - 0.1) / 0.9, 0.8); // sky: bright overhead
    else if (y > -0.04) k = 0.012; // the dark horizon band
    else k = 0.03 + 0.12 * Math.min(1, (-y - 0.04) / 0.5); // dark floor, faint toward the nadir
    colors[i * 3] = k;
    colors[i * 3 + 1] = k * 1.01;
    colors[i * 3 + 2] = k * 1.04;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  scene.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({vertexColors: true, side: THREE.BackSide})));
  const box = (w: number, hh: number, x: number, y: number, z: number, k: number) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, hh), new THREE.MeshBasicMaterial({color: new THREE.Color(k, k, k * 1.03), side: THREE.DoubleSide}));
    m.position.set(x, y, z);
    m.lookAt(0, 0, 0);
    scene.add(m);
  };
  box(3, 14, -12, 4, 9, 3.4); // left soft-box (tall strip)
  box(3, 14, 12, 4, 9, 2.8); // right soft-box
  box(16, 2.2, 0, 14, -3, 2.6); // overhead strip
  const pm = new THREE.PMREMGenerator(gl);
  const tex = pm.fromScene(scene, 0.012).texture;
  pm.dispose();
  return tex;
}

const ChromeMesh: React.FC<{text: string; px: number; boxW: number; frame: number; fps: number; total: number}> = ({text, px, boxW, frame, fps, total}) => {
  const geo = useMemo(() => {
    const g = new TextGeometry(text, {font: FONT, size: px, depth: px * 0.24, curveSegments: 10, bevelEnabled: true, bevelThickness: px * 0.035, bevelSize: px * 0.022, bevelSegments: 5});
    g.computeBoundingBox();
    g.center();
    return g;
  }, [text, px]);
  const {gl} = useThree();
  const env = useMemo(() => buildEnv(gl), [gl]);
  const natural = useMemo(() => {
    geo.computeBoundingBox();
    return geo.boundingBox!.max.x - geo.boundingBox!.min.x;
  }, [geo]);
  const s = Math.min(1, (boxW * 0.9) / natural);

  const inP = prog(frame, 0, 20, cubicOut);
  const out = exitOf(frame, total, fps);
  const yaw = (1 - inP) * THREE.MathUtils.degToRad(25) + Math.sin(frame / 38) * THREE.MathUtils.degToRad(3.5) * inP;
  const pitch = Math.sin(frame / 53) * THREE.MathUtils.degToRad(1.5);
  const scale = (0.9 + 0.1 * inP) * (1 - out * 0.03) * s;
  // the streak: the environment slides across the metal once, after the entrance starts
  const sweep = interpolate(frame, [4, 34], [-1.1, 1.1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});

  return (
    <mesh geometry={geo} rotation={[pitch, yaw, 0]} scale={[scale, scale, scale]}>
      <meshStandardMaterial
        color="#f3f5f8"
        metalness={1}
        roughness={0.06}
        envMap={env}
        envMapIntensity={1}
        envMapRotation={new THREE.Euler(0.15, sweep * 1.6, 0)}
      />
    </mesh>
  );
};

const Chrome: React.FC<Props> = ({h, total, size, availPx, cx, cy}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const px = size * 1.7;
  const boxW = Math.round(availPx);
  const boxH = Math.round(px * 2.1);
  const out = exitOf(f, total, fps);
  const opacity = prog(f, 0, 6, expoOut) * (1 - out);
  const fov = 28;
  const camZ = boxH / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
  return (
    <Anchor cx={cx} cy={cy} style={{opacity}}>
      <div style={{position: 'relative', width: boxW, height: boxH}}>
        {/* soft backing so polished metal never vanishes against bright paint */}
        <div style={{position: 'absolute', inset: '-8% -4%', borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(8,10,14,0.62), rgba(8,10,14,0.38) 55%, rgba(8,10,14,0) 100%)'}} />
        <ThreeCanvas
          width={boxW}
          height={boxH}
          camera={{fov, near: 1, far: camZ * 4, position: [0, 0, camZ]}}
          gl={{alpha: true, antialias: true}}
        >
          <ToneSetup />
          <ChromeMesh text={h.text} px={px} boxW={boxW} frame={f} fps={fps} total={total} />
        </ThreeCanvas>
      </div>
    </Anchor>
  );
};
const ToneSetup: React.FC = () => {
  const {gl} = useThree();
  gl.toneMapping = THREE.ACESFilmicToneMapping;
  gl.toneMappingExposure = 0.95;
  return null;
};

export const CardVariant: React.FC<Props> = (p) => {
  switch (p.variant) {
    case 'keynote':
      return <Keynote {...p} />;
    case 'studio':
      return <Studio {...p} />;
    case 'hud':
      return <Hud {...p} />;
    default:
      return <Chrome {...p} />;
  }
};
