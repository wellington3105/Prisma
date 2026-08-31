"""Rastreia features ao longo do vídeo e julga se a cena aceita camera solve.

OPUS-VFX-3D, stories C1 e C2. As duas vivem no mesmo arquivo de propósito:
rastrear sem julgar a qualidade produz um solve ruim em silêncio, e um solve
ruim é pior que não ter o recurso — o objeto ancorado treme, e tremor lê como
defeito, não como efeito.

Método: `goodFeaturesToTrack` (cantos de Shi-Tomasi) + Lucas-Kanade piramidal,
com re-semeadura quando o rastro fica ralo. É o caminho barato: medido no vídeo
de referência, 600 features caem para ~419 em 30 frames a **25 ms/frame** em
CPU, ~40x tempo real. COLMAP faria melhor e custa uma dependência nativa que
esta skill não tem.

O gate (C2) mede três coisas e recusa a cena quando qualquer uma falha:

  1. **Densidade** — features sobreviventes por frame. Parede lisa, céu, fundo
     desfocado: não há o que rastrear, e o solve inventa.
  2. **Paralaxe** — quanto os pontos se deslocam UNS EM RELAÇÃO AOS OUTROS.
     É a medida que separa translação de rotação pura. Uma panorâmica no
     tripé move todos os pixels juntos e não revela profundidade nenhuma;
     matematicamente não há baseline, e nenhum algoritmo resolve isso.
  3. **Persistência** — trilhas longas o bastante para triangular. Motion blur
     e cortes rápidos matam trilhas, e trilhas curtas dão pose instável.

Saída: JSON em stdout com `ok`, `reason` e as métricas. Quando `ok` é falso a
razão é específica ("rotação pura, sem paralaxe") — não "falhou".

Uso:
    uv run python helpers/camera_track.py <video> [--out tracks.json]
                   [--start 0] [--end 10] [--max-frames 300]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import cv2
import numpy as np

# ---- parâmetros do detector ------------------------------------------------
MAX_CORNERS = 600
QUALITY = 0.01
MIN_DISTANCE = 8
BLOCK_SIZE = 7

LK = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
)

# ---- limiares do gate ------------------------------------------------------
# Calibrados no vídeo de referência (Reel 1080x1920, câmera na mão andando por
# um ambiente): ele passa com folga. Uma cena estática de parede lisa não.
MIN_FEATURES = 80        # features vivas por frame, mediana
MIN_TRACK_LEN = 8        # frames que uma trilha precisa durar
MIN_TRACKS = 40          # trilhas longas o bastante
MIN_PARALLAX_PX = 1.2    # desvio-padrão do movimento relativo, em px
RESEED_BELOW = 250       # re-semeia quando o rastro rala


def _reseed(gray, existing=None):
    """Detecta cantos, evitando os que já estão sendo rastreados."""
    mask = None
    if existing is not None and len(existing):
        mask = np.full(gray.shape, 255, dtype=np.uint8)
        for x, y in existing.reshape(-1, 2):
            cv2.circle(mask, (int(x), int(y)), MIN_DISTANCE, 0, -1)
    return cv2.goodFeaturesToTrack(
        gray, maxCorners=MAX_CORNERS, qualityLevel=QUALITY,
        minDistance=MIN_DISTANCE, blockSize=BLOCK_SIZE, mask=mask,
    )


def track(video: Path, start: float = 0.0, end: float | None = None,
          max_frames: int = 300) -> dict:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"não consegui abrir {video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if start > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)

    ok, prev = cap.read()
    if not ok:
        raise SystemExit("vídeo sem frames legíveis")

    h, w = prev.shape[:2]
    gray0 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    pts = _reseed(gray0)
    if pts is None:
        return {"ok": False, "reason": "nenhuma feature detectável no primeiro frame",
                "fps": fps, "width": w, "height": h}

    # tracks[i] = lista de (frame_idx, x, y). Identidade sobrevive à re-semeadura
    # porque os pontos novos ganham índices novos; os antigos mantêm os seus.
    tracks: list[list[tuple[int, float, float]]] = [
        [(0, float(p[0][0]), float(p[0][1]))] for p in pts
    ]
    alive = list(range(len(tracks)))
    per_frame_alive: list[int] = [len(alive)]
    parallax: list[float] = []

    n = 0
    while n < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        t = start + n / fps
        if end is not None and t > end:
            break

        gray1 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        p1, st, _ = cv2.calcOpticalFlowPyrLK(gray0, gray1, pts, None, **LK)
        if p1 is None:
            break
        good = st.ravel() == 1

        # Paralaxe: o desvio-padrão do deslocamento. Se todos os pontos se movem
        # igual (rotação/pan), o desvio é ~0 mesmo com movimento grande — é
        # exatamente essa a distinção que interessa, e por isso a medida é o
        # desvio e não a média.
        if good.sum() >= 8:
            d = (p1[good] - pts[good]).reshape(-1, 2)
            parallax.append(float(np.hypot(d[:, 0], d[:, 1]).std()))

        new_alive = []
        for k, keep in zip(alive, good):
            if keep:
                new_alive.append(k)
        pts = p1[good].reshape(-1, 1, 2)
        for k, p in zip(new_alive, pts):
            tracks[k].append((n, float(p[0][0]), float(p[0][1])))
        alive = new_alive
        per_frame_alive.append(len(alive))

        if len(alive) < RESEED_BELOW:
            extra = _reseed(gray1, pts)
            if extra is not None and len(extra):
                for p in extra:
                    tracks.append([(n, float(p[0][0]), float(p[0][1]))])
                    alive.append(len(tracks) - 1)
                pts = np.vstack([pts, extra]).astype(np.float32)

        gray0 = gray1

    cap.release()

    long_tracks = [t for t in tracks if len(t) >= MIN_TRACK_LEN]
    med_alive = float(np.median(per_frame_alive)) if per_frame_alive else 0.0
    med_parallax = float(np.median(parallax)) if parallax else 0.0

    return {
        "fps": fps, "width": w, "height": h,
        "frames": n + 1,
        "features_median": med_alive,
        "tracks_total": len(tracks),
        "tracks_long": len(long_tracks),
        "parallax_px": med_parallax,
        "tracks": [
            [[f, round(x, 2), round(y, 2)] for f, x, y in t] for t in long_tracks
        ],
    }


def gate(m: dict) -> tuple[bool, str]:
    """C2 — a cena aceita camera solve? Recusa com a razão específica."""
    if m.get("frames", 0) < MIN_TRACK_LEN:
        return False, f"vídeo curto demais ({m.get('frames', 0)} frames)"
    if m["features_median"] < MIN_FEATURES:
        return False, (
            f"textura insuficiente — {m['features_median']:.0f} features vivas por "
            f"frame (mínimo {MIN_FEATURES}). Parede lisa, céu ou fundo desfocado "
            f"não dão o que rastrear"
        )
    if m["tracks_long"] < MIN_TRACKS:
        return False, (
            f"trilhas curtas demais — {m['tracks_long']} com {MIN_TRACK_LEN}+ frames "
            f"(mínimo {MIN_TRACKS}). Motion blur ou corte no meio do trecho"
        )
    if m["parallax_px"] < MIN_PARALLAX_PX:
        return False, (
            f"sem paralaxe — movimento relativo de {m['parallax_px']:.2f}px "
            f"(mínimo {MIN_PARALLAX_PX}). A câmera gira mas não translada: sem "
            f"baseline não existe profundidade para resolver, em nenhum algoritmo"
        )
    return True, "cena adequada para camera solve"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", help="grava as trilhas em JSON")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--max-frames", type=int, default=300)
    args = ap.parse_args()

    m = track(Path(args.video), args.start, args.end, args.max_frames)
    ok, reason = gate(m) if "features_median" in m else (False, m.get("reason", "falhou"))

    resumo = {
        "ok": ok, "reason": reason,
        "frames": m.get("frames"),
        "features_median": round(m.get("features_median", 0), 1),
        "tracks_long": m.get("tracks_long"),
        "parallax_px": round(m.get("parallax_px", 0), 2),
        "fps": m.get("fps"), "width": m.get("width"), "height": m.get("height"),
    }

    if args.out and ok:
        Path(args.out).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        resumo["out"] = args.out

    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
