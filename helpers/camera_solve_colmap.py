"""Camera solve via COLMAP — recupera a pose da câmera com precisão de ancoragem.

OPUS-VFX-3D, stories C3/C4. Substitui o solve incremental caseiro
(`camera_solve.py`), que ficou preso em 27 de 149 frames a 6.6px de reprojeção.

**Por que trocar, com os números lado a lado** (mesmo material, 4K→1080p):

| | caseiro | COLMAP |
|---|---:|---:|
| frames resolvidos | 27/149 | **45/45** |
| reprojeção | 6.65px | **0.78px** |
| pontos 3D | 428 | **12.690** |
| reconstruções | 1 | 1 |

O gate exige ≤ 2px para ancorar. O caseiro nunca chegou lá; o COLMAP passa com
folga. A diferença não é de ajuste fino — é que `IncrementalMapper` faz
re-triangulação, seleção de próxima imagem por cobertura e BA local a cada
registro, e é isso que mantém a nuvem crescendo junto com a câmera. Reimplementar
isso custou seis bugs e não chegou perto.

O que este arquivo NÃO descarta: `camera_track.py` continua sendo o pré-filtro.
Rodar o COLMAP (~2 min/clipe) numa cena sem paralaxe é desperdício, e o gate
detecta isso em segundos.

Custo medido (45 frames a 1080p, RTX 5070 — CPU na prática):
features+matching 41s · mapping 87s · **~2min por clipe de 1.5s**. É caro, e a
razão de existirem janelas: o painel de vidro do ÉPICO G é um acento de 2-3s,
não o vídeo inteiro.

Uso:
    uv run python helpers/camera_solve_colmap.py <video> --out camera.json
                   [--start 0] [--end 3] [--work <dir>] [--keep]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

MAX_REPROJ_PX = 2.0      # acima disto a pose não serve para ancorar
MIN_REG_RATIO = 0.80     # fração mínima de frames registrados
MAX_CLOUD_POINTS = 2000  # nuvem exportada para detecção de plano


def extract_frames(video: Path, out_dir: Path, start: float, end: float | None) -> int:
    """Frames CONSECUTIVOS em JPEG de alta qualidade.

    Amostrar (1 em 5) fragmenta a reconstrução — medido: 3 reconstruções
    separadas com amostragem, 1 única com frames consecutivos. O matching
    sequencial do COLMAP conta com sobreposição alta entre vizinhos.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if end is not None:
        cmd += ["-t", str(max(0.1, end - start))]
    # -q:v 2 e não PNG: o SIFT não ganha nada com lossless e o disco agradece.
    cmd += ["-vsync", "0", "-q:v", "2", str(out_dir / "f%04d.jpg"), "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    return len(list(out_dir.glob("*.jpg")))


def solve(video: Path, start: float, end: float | None,
          work: Path, quiet: bool = True) -> dict:
    try:
        import pycolmap as pc
    except ImportError:
        return {"ok": False, "reason": "pycolmap ausente — uv pip install pycolmap"}

    images = work / "images"
    t0 = time.time()
    n = extract_frames(video, images, start, end)
    if n < 8:
        return {"ok": False, "reason": f"apenas {n} frames extraídos"}

    db = work / "db.db"
    db.unlink(missing_ok=True)
    pc.extract_features(database_path=db, image_path=images)
    # Sequencial e não exaustivo: frames de vídeo já vêm ordenados, e o
    # exaustivo custa O(n²) comparações para reencontrar o que a ordem temporal
    # já entrega.
    pc.match_sequential(database_path=db)
    t_match = time.time() - t0

    sparse = work / "sparse"
    sparse.mkdir(exist_ok=True)
    t1 = time.time()
    recs = pc.incremental_mapping(database_path=db, image_path=images,
                                  output_path=sparse)
    t_map = time.time() - t1

    if not recs:
        return {"ok": False, "reason": "COLMAP não produziu reconstrução — "
                                       "cena sem paralaxe ou sem textura"}

    # Mais de uma reconstrução = o clipe se partiu (corte de cena, oclusão, ou
    # um trecho parado no meio). Ficar com a maior e DIZER que houve fragmento é
    # melhor que costurar duas soluções com escalas diferentes.
    best = max(recs.values(), key=lambda r: r.num_reg_images())
    best.update_point_3d_errors()
    reproj = float(best.compute_mean_reprojection_error())
    reg = best.num_reg_images()
    ratio = reg / n

    poses = {}
    for iid, im in best.images.items():
        cfw = im.cam_from_world
        p = cfw() if callable(cfw) else cfw
        # O nome é fNNNN.jpg e o índice do frame vem dele: os ids do COLMAP não
        # seguem a ordem temporal, e a `<TrackedScene>` precisa do frame real.
        idx = int(Path(im.name).stem.lstrip("f"))
        poses[idx - 1] = {
            "R": [list(map(float, r)) for r in p.rotation.matrix()],
            "t": [float(x) for x in p.translation],
        }

    # Nuvem esparsa, para detecção de plano (C6). Os pontos mais bem
    # reconstruídos primeiro — um ponto com erro alto polui o ajuste de plano
    # mais do que ajuda, e 2000 bastam de sobra para um RANSAC.
    pts = sorted(best.points3D.items(), key=lambda kv: kv[1].error)[:MAX_CLOUD_POINTS]
    cloud = [[round(float(v), 4) for v in p.xyz] for _, p in pts]

    cam = next(iter(best.cameras.values()))
    params = list(map(float, cam.params))
    ok = reproj <= MAX_REPROJ_PX and ratio >= MIN_REG_RATIO

    return {
        "ok": ok,
        "reason": (
            f"solve ok — {reg}/{n} frames, reprojeção {reproj:.2f}px"
            if ok else
            f"apenas {reg}/{n} frames registrados ({ratio*100:.0f}%, mínimo "
            f"{MIN_REG_RATIO*100:.0f}%) — o clipe provavelmente tem um trecho "
            f"sem movimento ou um corte"
            if ratio < MIN_REG_RATIO else
            f"reprojeção {reproj:.2f}px acima do limite {MAX_REPROJ_PX}px"
        ),
        "reprojection_px": round(reproj, 3),
        "frames_registered": reg,
        "frames_total": n,
        "points_3d": len(best.points3D),
        "fragments": len(recs),
        "seconds": {"match": round(t_match, 1), "mapping": round(t_map, 1)},
        "intrinsics": {"model": str(cam.model), "params": params,
                       "width": cam.width, "height": cam.height},
        "poses": poses,
        "cloud": cloud,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", help="grava camera.json")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--work", help="dir de trabalho (padrão: temporário)")
    ap.add_argument("--keep", action="store_true", help="não apagar o dir de trabalho")
    args = ap.parse_args()

    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="prisma-colmap-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        r = solve(Path(args.video), args.start, args.end, work)
        if args.out and r.get("ok"):
            Path(args.out).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            r["out"] = args.out
        print(json.dumps({k: v for k, v in r.items() if k != "poses"},
                         ensure_ascii=False, indent=1))
        if not r.get("ok"):
            sys.exit(2)
    finally:
        if not args.keep and not args.work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
