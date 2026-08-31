/**
 * Verifica a conversão de pose COLMAP → Three.js sem renderizar nada.
 *
 * O caminho anterior era: escrever a conversão, renderizar 45 frames, medir o
 * objeto no still e descobrir 304px de erro. Este arquivo responde a mesma
 * pergunta em milissegundos, e diz QUAL das operações está trocada em vez de
 * apenas que o resultado está errado.
 *
 * O teste: projetar um ponto 3D conhecido pelos dois caminhos —
 *   (a) a projeção pinhole direta, com os intrínsecos do COLMAP;
 *   (b) a matriz de projeção do Three, com a câmera posicionada pela conversão.
 * Se a conversão está certa, os dois pixels coincidem.
 *
 *   node src/poseMath.test.mjs
 */
import * as THREE from 'three';

// Pose real do camera.json (frame 24 do material de referência) e os
// intrínsecos medidos pelo COLMAP — números de produção, não sintéticos.
const POSE = {
  R: [
    [0.9241, 0.0521, 0.3784],
    [-0.1163, 0.9823, 0.1485],
    [-0.3644, -0.1801, 0.9138],
  ],
  t: [-4.4389, -0.5534, -0.1553],
};
const F = 1253.2103439328375;
const CX = 540.0;
const CY = 960.0;
const W = 1080;
const H = 1920;

/** Verdade de referência: x_cam = R·X + t, depois divisão em perspectiva. */
const projectColmap = (X) => {
  const {R, t} = POSE;
  const xc = [
    R[0][0] * X[0] + R[0][1] * X[1] + R[0][2] * X[2] + t[0],
    R[1][0] * X[0] + R[1][1] * X[1] + R[1][2] * X[2] + t[1],
    R[2][0] * X[0] + R[2][1] * X[1] + R[2][2] * X[2] + t[2],
  ];
  return {u: (F * xc[0]) / xc[2] + CX, v: (F * xc[1]) / xc[2] + CY, z: xc[2]};
};

/** Candidata: converte a pose e projeta com a câmera do Three. */
const projectThree = (X, convert) => {
  const cam = new THREE.PerspectiveCamera(
    (2 * Math.atan(H / (2 * F)) * 180) / Math.PI,
    W / H,
    0.01,
    1000,
  );
  const {pos, quat} = convert(POSE);
  cam.position.copy(pos);
  cam.quaternion.copy(quat);
  cam.updateMatrixWorld(true);
  cam.updateProjectionMatrix();

  const ndc = new THREE.Vector3(X[0], X[1], X[2]).project(cam);
  return {u: ((ndc.x + 1) / 2) * W, v: ((1 - ndc.y) / 2) * H, z: ndc.z};
};

// ---- candidatas -------------------------------------------------------------
const mat4 = (R, t) =>
  new THREE.Matrix4().set(
    R[0][0], R[0][1], R[0][2], t[0],
    R[1][0], R[1][1], R[1][2], t[1],
    R[2][0], R[2][1], R[2][2], t[2],
    0, 0, 0, 1,
  );

const decompose = (m) => {
  const pos = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const scl = new THREE.Vector3();
  m.decompose(pos, quat, scl);
  return {pos, quat};
};

const FLIP = new THREE.Matrix4().makeRotationX(Math.PI);

const candidates = {
  // A que está no TrackedScene hoje.
  'invert().premultiply(FLIP)': (p) =>
    decompose(mat4(p.R, p.t).invert().premultiply(FLIP)),

  // world_from_cam e depois flip do lado do EIXO da câmera, não do mundo.
  'invert().multiply(FLIP)': (p) => decompose(mat4(p.R, p.t).invert().multiply(FLIP)),

  // Flip aplicado a cam_from_world antes de inverter.
  'premultiply(FLIP).invert()': (p) =>
    decompose(mat4(p.R, p.t).clone().premultiply(FLIP).invert()),

  // Sem flip nenhum — para provar que o flip é mesmo necessário.
  'invert() puro': (p) => decompose(mat4(p.R, p.t).invert()),
};

// ---- execução ---------------------------------------------------------------
// Pontos à frente da câmera, com profundidade positiva (cheirality).
const PTS = [
  [-2.0, -2.0, 4.0],
  [0.0, 0.0, 3.0],
  [1.5, -1.0, 2.0],
  [-1.0, 0.5, 5.0],
];

console.log('COLMAP (verdade) vs cada conversão candidata:\n');
let melhor = null;

for (const [nome, fn] of Object.entries(candidates)) {
  const erros = [];
  for (const X of PTS) {
    const a = projectColmap(X);
    if (a.z <= 0) continue; // atrás da câmera: não é caso de teste válido
    const b = projectThree(X, fn);
    erros.push(Math.hypot(a.u - b.u, a.v - b.v));
  }
  const media = erros.reduce((s, e) => s + e, 0) / erros.length;
  console.log(`  ${nome.padEnd(30)} erro médio ${media.toFixed(1).padStart(9)}px`);
  if (melhor === null || media < melhor.media) melhor = {nome, media};
}

console.log(`\nMelhor: ${melhor.nome} (${melhor.media.toFixed(2)}px)`);
console.log(melhor.media < 1 ? 'PASSOU — conversão correta' : 'FALHOU — nenhuma candidata alinha');
process.exit(melhor.media < 1 ? 0 : 1);
