/**
 * TrackedScene — objetos ancorados no espaço 3D da cena (OPUS-VFX-3D § C5).
 *
 * A diferença em relação a tudo o mais neste template: um insert, um painel de
 * vidro ou uma legenda vivem NA TELA — movem-se com a composição, não com o
 * mundo filmado. Um objeto aqui fica onde foi posto na SALA. A câmera anda, e
 * ele permanece na mesa; a câmera gira, e ele sai de quadro pela borda certa.
 *
 * Isso exige saber como a câmera se moveu de verdade, o que vem de
 * `helpers/camera_solve_colmap.py` → `public/camera.json`
 * (45/45 frames, 0.82px de reprojeção no material de referência).
 *
 * DUAS CONVENÇÕES QUE NÃO COINCIDEM, e é onde este tipo de integração falha:
 *   COLMAP  → câmera olha para +Z, Y aponta para BAIXO
 *   Three.js → câmera olha para −Z, Y aponta para CIMA
 * A conversão é uma rotação de 180° em X. Sem ela a cena aparece de cabeça
 * para baixo e espelhada em profundidade — e o erro é sutil o bastante para
 * parecer "quase certo" num still isolado.
 *
 * Gated por `elements.tracked3d`. Sem a marcação, nada disto monta.
 */
import React, {useMemo} from 'react';
import * as THREE from 'three';
import {useThree, useFrame} from '@react-three/fiber';
import {ThreeCanvas, useOffthreadVideoTexture} from '@remotion/three';
import {
  AbsoluteFill,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  useRemotionEnvironment,
} from 'remotion';

type Pose = {R: number[][]; t: number[]};

export type TrackedData = {
  ok: boolean;
  intrinsics: {params: number[]; width: number; height: number};
  poses: Record<string, Pose>;
};

/** Posição: coordenada crua OU referência a um plano detectado. */
type Placement = {
  /** Coordenada no mundo reconstruído. Ignorada quando `onPlane` existe. */
  at?: [number, number, number];
  /** Índice em `tracked.planes` — o objeto assenta nesta superfície. */
  onPlane?: number;
  /** Deslocamento a partir do centro do plano, nos eixos do mundo. */
  offset?: [number, number, number];
  /** Afastamento ao longo da normal, para não brigar com a superfície. */
  lift?: number;
  /** Rotação em graus. Sem isto e com `onPlane`, vem da orientação do plano. */
  rotation?: [number, number, number];
};

export type TrackedObject =
  | (Placement & {kind: 'box'; size?: number; color?: string})
  | (Placement & {kind: 'panel'; w?: number; h?: number; color?: string; opacity?: number})
  | (Placement & {kind: 'text'; text: string; size?: number; color?: string});

export type Plane = {
  normal: [number, number, number];
  center: [number, number, number];
  orientation: string;
  rotation_deg: [number, number, number];
  size: [number, number];
};

export type TrackedBlock = {
  enabled: boolean;
  /** Arquivo em public/, saída de camera_solve_colmap.py. */
  data: string;
  /** Planos de detect_plane.py. Com isto, um objeto pode dizer
   *  `onPlane: 0` em vez de três coordenadas escolhidas às cegas. */
  planes?: Plane[];
  /** Frame do vídeo em que o frame 0 do solve começa. */
  offset?: number;
  objects: TrackedObject[];
  /** Vídeo de fundo. Default: o cut. */
  src?: string;
};

/** COLMAP (Y baixo, +Z frente) → Three (Y cima, −Z frente). */
const FLIP = new THREE.Matrix4().makeRotationX(Math.PI);

const poseToThree = (p: Pose) => {
  const R = new THREE.Matrix4().set(
    p.R[0][0], p.R[0][1], p.R[0][2], p.t[0],
    p.R[1][0], p.R[1][1], p.R[1][2], p.t[1],
    p.R[2][0], p.R[2][1], p.R[2][2], p.t[2],
    0, 0, 0, 1,
  );
  // cam_from_world → world_from_cam, e o flip aplicado DO LADO DA CÂMERA
  // (multiply, à direita), não do lado do mundo (premultiply, à esquerda).
  // A distinção não é estilística: `premultiply` gira o mundo inteiro em torno
  // do eixo X global e dá **1283px** de erro de projeção; `multiply` gira só os
  // eixos locais da câmera e dá **0.9px**. Verificado em src/poseMath.test.mjs,
  // que projeta pontos conhecidos pelos dois caminhos e compara — rode-o antes
  // de tocar nesta linha.
  const m = R.clone().invert().multiply(FLIP);
  const pos = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const scl = new THREE.Vector3();
  m.decompose(pos, quat, scl);
  return {pos, quat};
};

/**
 * Resolve a posição de um objeto: coordenada explícita ou "sobre o plano N".
 *
 * Escolher três números no espaço reconstruído é adivinhação — as unidades não
 * são metros e a origem cai onde o par inicial calhou de estar. `onPlane` troca
 * isso por uma referência à geometria que o solve já encontrou, e traz a
 * rotação junto: um objeto sobre a mesa deve estar DEITADO nela.
 */
const resolvePlacement = (o: TrackedObject, planes?: Plane[]) => {
  if (o.onPlane === undefined || !planes?.length) {
    return {at: o.at ?? ([0, 0, 0] as [number, number, number]), rot: o.rotation};
  }
  const p = planes[Math.min(o.onPlane, planes.length - 1)];
  const [ox, oy, oz] = o.offset ?? [0, 0, 0];
  // Deslocamento ao longo da normal separa o objeto da superfície: um plano
  // com espessura zero e um objeto exatamente sobre ele brigam por z-fighting.
  const lift = o.lift ?? 0.02;
  return {
    at: [
      p.center[0] + p.normal[0] * lift + ox,
      p.center[1] + p.normal[1] * lift + oy,
      p.center[2] + p.normal[2] * lift + oz,
    ] as [number, number, number],
    rot: o.rotation ?? p.rotation_deg,
  };
};

const Obj: React.FC<{o: TrackedObject; planes?: Plane[]}> = ({o, planes}) => {
  const {at, rot} = resolvePlacement(o, planes);
  const rotation = (rot ?? [0, 0, 0]).map((d) => (d * Math.PI) / 180) as [number, number, number];
  if (o.kind === 'panel') {
    return (
      <mesh position={at} rotation={rotation}>
        <planeGeometry args={[o.w ?? 1, o.h ?? 0.6]} />
        <meshBasicMaterial
          color={o.color ?? '#7fd4ff'}
          transparent
          opacity={o.opacity ?? 0.55}
          side={THREE.DoubleSide}
        />
      </mesh>
    );
  }
  if (o.kind === 'text') {
    // Sem carregar fonte 3D: um plano com a cor do texto marca a posição.
    // Tipografia de verdade é a story G5; aqui o que importa é a ÂNCORA.
    return (
      <mesh position={at} rotation={rotation}>
        <planeGeometry args={[(o.size ?? 0.5) * o.text.length * 0.5, o.size ?? 0.5]} />
        <meshBasicMaterial color={o.color ?? '#ffd400'} transparent opacity={0.9} />
      </mesh>
    );
  }
  return (
    <mesh position={at} rotation={rotation}>
      <boxGeometry args={[o.size ?? 0.4, o.size ?? 0.4, o.size ?? 0.4]} />
      <meshBasicMaterial color={o.color ?? '#ff7a1a'} />
    </mesh>
  );
};

/**
 * A footage, desenhada em coordenadas de tela atrás de tudo.
 *
 * Uma câmera ortográfica própria e `depthTest: false` mantêm o plano fixo ao
 * viewport enquanto a câmera principal se move — se ele participasse da cena 3D,
 * a footage se moveria junto e o efeito se anularia.
 */
const Backdrop: React.FC<{tex: THREE.Texture}> = ({tex}) => {
  const {size} = useThree();
  const cam = useMemo(() => new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), []);
  const scene = useMemo(() => {
    const s = new THREE.Scene();
    s.add(new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      new THREE.MeshBasicMaterial({map: tex, depthTest: false, depthWrite: false}),
    ));
    return s;
  }, [tex]);

  useFrame(({gl, scene: main, camera}) => {
    const mat = (scene.children[0] as THREE.Mesh).material as THREE.MeshBasicMaterial;
    mat.map = tex;
    mat.needsUpdate = true;
    gl.autoClear = false;
    gl.clear();
    gl.render(scene, cam);        // fundo primeiro
    gl.render(main, camera);      // objetos ancorados por cima
  }, 1);

  return null;
};

const Rig: React.FC<{data: TrackedData; objects: TrackedObject[]; offset: number; planes?: Plane[]}> = ({
  data,
  objects,
  offset,
  planes,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();

  const idx = frame - offset;
  const pose = data.poses[String(idx)];

  // Frames que o solve não registrou: a última pose conhecida é melhor que
  // nenhuma — o objeto congela um instante em vez de piscar.
  const usable = useMemo(() => {
    if (pose) return pose;
    const keys = Object.keys(data.poses).map(Number).sort((a, b) => a - b);
    const prev = keys.filter((k) => k <= idx).pop();
    return prev === undefined ? data.poses[String(keys[0])] : data.poses[String(prev)];
  }, [pose, idx, data.poses]);

  const {pos, quat} = useMemo(() => poseToThree(usable), [usable]);

  // FOV vertical a partir da focal medida pelo COLMAP. Usar um FOV arbitrário
  // aqui desalinha tudo: a projeção tem de ser a MESMA que produziu as poses.
  const fov = useMemo(() => {
    const f = data.intrinsics.params[0];
    return (2 * Math.atan(data.intrinsics.height / (2 * f)) * 180) / Math.PI;
  }, [data]);

  // Dirigir a câmera DEFAULT do canvas, em vez de declarar uma <perspectiveCamera>
  // como filha: um elemento filho cria uma câmera que o R3F não usa para
  // renderizar, e o resultado é uma cena estática que ignora o solve inteiro.
  const cam = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  useFrame(() => {
    cam.position.copy(pos);
    cam.quaternion.copy(quat);
    if (cam.fov !== fov || cam.aspect !== width / height) {
      cam.fov = fov;
      cam.aspect = width / height;
      cam.updateProjectionMatrix();
    }
  });
  // Também fora do useFrame: no primeiro passe o useFrame roda DEPOIS do draw,
  // e o frame inicial sairia com a câmera na origem.
  cam.position.copy(pos);
  cam.quaternion.copy(quat);
  cam.fov = fov;
  cam.aspect = width / height;
  cam.updateProjectionMatrix();

  return (
    <>
      {objects.map((o, i) => (
        <Obj key={i} o={o} planes={planes} />
      ))}
    </>
  );
};

export const TrackedScene: React.FC<{spec: TrackedBlock; data: TrackedData}> = ({spec, data}) => {
  const {width, height} = useVideoConfig();
  const env = useRemotionEnvironment();
  const tex = useOffthreadVideoTexture({src: staticFile(spec.src ?? 'cut.mp4')});

  if (!env.isRendering || !tex || !data.ok) return null;

  const fov =
    (2 * Math.atan(data.intrinsics.height / (2 * data.intrinsics.params[0])) * 180) / Math.PI;

  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} camera={{fov, near: 0.01, far: 1000}}>
        {/* A footage vai para dentro do canvas: um WebGL não alcança um
            <OffthreadVideo> irmão no DOM (mesma restrição do GlassPanel), e
            aqui ela precisa estar sob os objetos ancorados. */}
        <Backdrop tex={tex} />
        <Rig data={data} objects={spec.objects} offset={spec.offset ?? 0} planes={spec.planes} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
