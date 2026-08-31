"""Encontra planos na nuvem do camera solve — mesa, parede, chão.

OPUS-VFX-3D, story C6. Sem isto, ancorar um objeto exige escolher três números
no espaço reconstruído às cegas: as unidades não são metros (visão monocular
não recupera escala), e a origem cai onde o par inicial calhou de estar. Na
prática significa renderizar, ver o objeto no lugar errado, ajustar, repetir.

Com isto, o objeto vai **sobre a mesa** — e a orientação do plano dá de graça a
rotação que o deita ali, que é justamente o que a referência do Instagram faz
com o "Aprenda a fazer".

Método: RANSAC. Sorteia 3 pontos, ajusta o plano que passa por eles, conta
quantos da nuvem ficam a menos de `--tol` dele, repete e guarda o melhor.
Depois refina com todos os inliers via SVD, porque o plano de 3 pontos é exato
para eles e aproximado para o resto.

Por que não `cv2.findHomography`: homografia acha um plano em coordenadas de
IMAGEM, entre dois frames. Aqui os pontos já estão em 3D — ajustar o plano
diretamente é mais simples e não depende de escolher um par de frames.

Uso:
    uv run python helpers/detect_plane.py camera.json [--max 3] [--tol 0.05]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np

ITERS = 600
MIN_INLIERS = 30
# Tolerância padrão como FRAÇÃO da extensão da nuvem, não valor absoluto: a
# escala do solve é arbitrária, e 0.05 unidades pode ser um milímetro ou um
# metro dependendo do clipe.
TOL_RATIO = 0.012


def fit_plane(pts: np.ndarray) -> tuple[np.ndarray, float]:
    """Plano de mínimos quadrados: normal (unitária) e distância à origem."""
    c = pts.mean(axis=0)
    # O menor vetor singular é a direção de menor variância — a normal.
    _, _, vt = np.linalg.svd(pts - c)
    n = vt[-1]
    return n / (np.linalg.norm(n) + 1e-12), float(np.dot(n, c))


def ransac_plane(pts: np.ndarray, tol: float, rng: np.random.Generator):
    melhor_inl = None
    melhor_n = 0
    for _ in range(ITERS):
        idx = rng.choice(len(pts), 3, replace=False)
        a, b, c = pts[idx]
        n = np.cross(b - a, c - a)
        norm = np.linalg.norm(n)
        if norm < 1e-9:      # três pontos colineares não definem plano
            continue
        n = n / norm
        d = float(np.dot(n, a))
        inl = np.abs(pts @ n - d) < tol
        k = int(inl.sum())
        if k > melhor_n:
            melhor_n, melhor_inl = k, inl
    if melhor_inl is None or melhor_n < MIN_INLIERS:
        return None
    # Refino: o plano de 3 pontos é exato para eles e aproximado para o resto.
    n, d = fit_plane(pts[melhor_inl])
    return n, d, melhor_inl


def orientation(n: np.ndarray) -> str:
    """Horizontal ou vertical? O eixo Y do COLMAP aponta para BAIXO."""
    vert = abs(float(n[1]))
    if vert > 0.85:
        return "horizontal"   # mesa, chão, teto
    if vert < 0.35:
        return "vertical"     # parede
    return "inclinado"


def euler_for_plane(n: np.ndarray) -> list[float]:
    """Rotação em graus que deita um objeto NO plano, para `text3d`/`tracked`.

    Um plano horizontal quer o objeto girado -90° em X (deitado); um vertical,
    de frente. O ângulo intermediário sai da própria normal, então uma mesa
    inclinada também funciona.
    """
    # Ângulo entre a normal e o eixo Y (vertical do mundo COLMAP).
    ang = float(np.degrees(np.arccos(np.clip(abs(n[1]), 0, 1))))
    return [round(-90.0 + ang, 1), 0.0, 0.0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("camera", help="camera.json de camera_solve_colmap.py")
    ap.add_argument("--max", type=int, default=3, help="quantos planos extrair")
    ap.add_argument("--tol", type=float, default=None,
                    help="tolerância em unidades do solve; sem isto, 1.2%% da "
                         "extensão da nuvem")
    ap.add_argument("--out", help="grava os planos em JSON")
    args = ap.parse_args()

    d = json.loads(Path(args.camera).read_text(encoding="utf-8"))
    cloud = d.get("cloud")
    if not cloud:
        raise SystemExit(
            "camera.json sem 'cloud' — regere com camera_solve_colmap.py atual")

    pts = np.asarray(cloud, dtype=float)
    # Extensão por estatística ROBUSTA, não por max-min. Medido na cena real:
    # a diagonal do bounding box dava 53.5 por causa de alguns pontos distantes,
    # enquanto a mediana das distâncias ao centro era 4.1. A tolerância derivada
    # do bounding box (0.64) engolia 74% da nuvem num plano só, e os três
    # "planos" saíam com a mesma normal.
    centro = np.median(pts, axis=0)
    extent = float(np.percentile(np.linalg.norm(pts - centro, axis=1), 90) * 2)
    tol = args.tol if args.tol is not None else extent * TOL_RATIO
    rng = np.random.default_rng(0)   # determinístico: mesmo input, mesmo plano

    planos = []
    restantes = pts
    for _ in range(args.max):
        if len(restantes) < MIN_INLIERS:
            break
        r = ransac_plane(restantes, tol, rng)
        if r is None:
            break
        n, dist, inl = r
        # Um plano quase paralelo a outro já aceito é o MESMO plano visto pelos
        # pontos que sobraram, não uma superfície nova. Sem este teste os três
        # "planos" da cena real saíam com normais 0.786/0.799/0.79 — o mesmo
        # muro, três vezes.
        if any(abs(float(np.dot(n, np.asarray(p["normal"])))) > 0.95 for p in planos):
            restantes = restantes[~inl]
            continue
        p = restantes[inl]
        centro = p.mean(axis=0)
        planos.append({
            "normal": [round(float(v), 4) for v in n],
            "d": round(dist, 4),
            "center": [round(float(v), 4) for v in centro],
            "points": int(inl.sum()),
            "share": round(float(inl.sum()) / len(pts), 3),
            "orientation": orientation(n),
            "rotation_deg": euler_for_plane(n),
            # Meia-extensão nas duas direções do plano — quanto cabe ali.
            "size": [
                round(float(np.percentile(np.abs((p - centro) @ v), 90)), 3)
                for v in np.linalg.svd(p - centro)[2][:2]
            ],
        })
        # Remover os inliers para o próximo plano ser OUTRO, não o mesmo.
        restantes = restantes[~inl]

    resumo = {
        "ok": bool(planos),
        "reason": (f"{len(planos)} plano(s) encontrado(s)" if planos
                   else "nenhum plano com pontos suficientes — cena sem "
                        "superfícies planas ou nuvem muito esparsa"),
        "cloud_points": len(pts),
        "extent": round(extent, 3),
        "tolerance": round(tol, 4),
        "planes": planos,
    }
    if args.out and planos:
        Path(args.out).write_text(json.dumps(resumo, ensure_ascii=False),
                                  encoding="utf-8")
        resumo["out"] = args.out
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if not planos:
        sys.exit(2)


if __name__ == "__main__":
    main()
