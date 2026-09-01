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
STILL_PX = 1.0           # abaixo disto o frame não contribui com baseline
MAX_STILL_RATIO = 0.05   # fração tolerada de frames parados na janela
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
    parados = int(sum(1 for p in parallax if p < STILL_PX))

    return {
        "fps": fps, "width": w, "height": h,
        "frames": n + 1,
        "features_median": med_alive,
        "tracks_total": len(tracks),
        "tracks_long": len(long_tracks),
        "parallax_px": med_parallax,
        "frames_parados": parados,
        "parallax_p10": float(np.percentile(parallax, 10)) if parallax else 0.0,
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
    # A MEDIANA passa e o solve morre assim mesmo quando há um trecho parado
    # dentro da janela: o COLMAP precisa de baseline em CADA par de frames, não
    # em média. Medido no clipe de demonstração: mediana 6.92px — folgada — e
    # ainda assim 4 de 60 frames registrados, porque os primeiros 1.5s tinham
    # paralaxe de 0.02px. Deslocar a janela em 1.5s deu 59/60 a 1.27px.
    #
    # É por isso que o teste é sobre a CAUDA, não sobre o centro.
    parados = m.get("frames_parados", 0)
    if parados > m["frames"] * MAX_STILL_RATIO:
        return False, (
            f"{parados} de {m['frames']} frames sem movimento "
            f"({parados / m['frames'] * 100:.0f}%, limite {MAX_STILL_RATIO * 100:.0f}%). "
            f"A janela contém um trecho parado — o solve precisa de baseline em "
            f"cada par de frames, não em média. Use --scan para achar a melhor janela"
        )
    return True, "cena adequada para camera solve"


def render_debug(video: Path, data: dict, out: Path, start: float) -> None:
    """Desenha as trilhas sobre o vídeo — o overlay verde da referência.

    Serve a dois propósitos, e o segundo é o que justifica o código: mostra ao
    usuário o que o tracking está vendo (o app da referência exibe exatamente
    isto), e permite julgar a QUALIDADE do rastreio olhando, em vez de confiar
    nos números do gate. Rastro ralo, pontos grudados no falante em vez do
    ambiente, ou pontos escorregando — nada disso aparece numa mediana.

    A cauda de cada trilha é desenhada em degradê: um ponto isolado não diz se
    está preso à cena ou vagando, o rastro diz.
    """
    cap = cv2.VideoCapture(str(video))
    if start > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    fps = data.get("fps") or cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = data["width"], data["height"]
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    # {frame: [(x, y, idade)]} — montado uma vez, em vez de varrer as trilhas
    # a cada frame.
    porf: dict[int, list] = {}
    for tr in data["tracks"]:
        for k, (f, x, y) in enumerate(tr):
            porf.setdefault(int(f), []).append((x, y, k, tr))

    n = 0
    while True:
        ok, frame = cap.read()
        if not ok or n > max(porf, default=0):
            break
        for x, y, k, tr in porf.get(n, []):
            # Rastro: até 8 posições anteriores, esmaecendo.
            for j in range(max(0, k - 8), k):
                _, px, py = tr[j]
                a = (j - max(0, k - 8)) / 8.0
                cv2.circle(frame, (int(px), int(py)), 1,
                           (0, int(120 + 135 * a), 0), -1)
            cv2.drawMarker(frame, (int(x), int(y)), (0, 255, 0),
                           cv2.MARKER_CROSS, 9, 1)
        cv2.putText(frame, f"{len(porf.get(n, []))} features", (24, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2)
        vw.write(frame)
        n += 1
    cap.release()
    vw.release()


def _fala_por_janela(transcript: Path | None, ini: float, fim: float) -> int:
    """Quantas palavras são ditas nesta janela.

    O solve e a narração competem: a câmera se move quando o apresentador
    caminha, e ele costuma falar parado. Medido no clipe de teste — a melhor
    janela de movimento (1.5–3.5s) tinha **zero palavras**, e montar a Fase 2
    ali daria um vídeo mudo. Cruzar os dois critérios achou 4.0–6.0s, com
    60/60 frames a 1.10px E fala.
    """
    if not transcript or not transcript.exists():
        return -1  # sem transcrição: não é critério, e o scan não deve fingir
    try:
        d = json.loads(transcript.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return -1
    return sum(1 for w in d.get("words", [])
               if w.get("text", "").strip()
               and ini <= float(w.get("start", -1)) < fim)


def scan(video: Path, win: float, passo: float = 0.5,
         transcript: Path | None = None) -> dict:
    """Varre o vídeo e devolve a melhor janela de `win` segundos para o solve.

    Existe porque escolher a janela a olho falha em silêncio: no clipe de
    demonstração a mediana de paralaxe era 6.92px — folgada — mas os primeiros
    1.5s estavam parados, e o solve registrou 4 de 60 frames. Deslocada em 1.5s,
    a MESMA filmagem deu 59/60 a 1.27px.

    Dois critérios, e o segundo só existe porque o primeiro sozinho enganou:
      - **movimento**: janela sem frames parados, ordenada pelo p10 da paralaxe;
      - **fala** (com `--transcript`): a janela mais móvel do clipe de teste não
        tinha palavra nenhuma. Uma janela boa para o solve e ruim para o vídeo
        não é uma janela boa.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"não consegui abrir {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ok, prev = cap.read()
    if not ok:
        raise SystemExit("vídeo sem frames legíveis")

    g0 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    p0 = _reseed(g0)
    serie: list[tuple[float, float]] = []
    n = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        n += 1
        g1 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if p0 is not None and len(p0) > 30:
            p1, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, p0, None, **LK)
            if p1 is not None and st.sum() > 20:
                good = st.ravel() == 1
                d = (p1[good] - p0[good]).reshape(-1, 2)
                serie.append((n / fps, float(np.hypot(d[:, 0], d[:, 1]).std())))
        p0 = _reseed(g1)
        g0 = g1
    cap.release()

    if not serie:
        return {"ok": False, "reason": "não foi possível medir movimento"}

    arr = np.asarray(serie)
    dur = float(arr[-1, 0])
    cands = []
    t = 0.0
    while t + win <= dur:
        w = arr[(arr[:, 0] >= t) & (arr[:, 0] < t + win)]
        if len(w) >= win * fps * 0.6:
            parados = int((w[:, 1] < STILL_PX).sum())
            cands.append({
                "start": round(t, 2),
                "end": round(t + win, 2),
                "p10": round(float(np.percentile(w[:, 1], 10)), 2),
                "min": round(float(w[:, 1].min()), 2),
                "parados": parados,
                "palavras": _fala_por_janela(transcript, t, t + win),
            })
        t += passo

    limpas = [c for c in cands if c["parados"] == 0]
    if not limpas:
        return {
            "ok": False,
            "reason": f"nenhuma janela de {win}s sem frames parados neste vídeo",
            "melhores": sorted(cands, key=lambda c: c["parados"])[:1],
        }

    com_fala = [c for c in limpas if c["palavras"] > 0]
    tem_transcript = any(c["palavras"] >= 0 for c in limpas)

    if tem_transcript and not com_fala:
        # Vale dizer em vez de devolver silenciosamente uma janela muda.
        limpas.sort(key=lambda c: -c["p10"])
        return {
            "ok": False,
            "reason": (f"as {len(limpas)} janelas com movimento não têm fala. "
                       f"A câmera se move quando o apresentador caminha, e ele "
                       f"fala parado — grave um trecho andando E falando"),
            "melhores": limpas[:3],
        }

    escolhidas = com_fala or limpas
    # Ordena por fala primeiro: um p10 alto numa janela muda não serve para nada.
    escolhidas.sort(key=lambda c: (-c["palavras"], -c["p10"]))
    return {
        "ok": True,
        "reason": (f"{len(escolhidas)} janela(s) de {win}s sem frames parados"
                   + (" e com fala" if com_fala else
                      " (sem --transcript: fala não foi considerada)")),
        "best": escolhidas[0],
        "alternativas": escolhidas[1:4],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", help="grava as trilhas em JSON")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--max-frames", type=int, default=300)
    ap.add_argument("--debug-video", metavar="MP4",
                    help="grava o overlay de tracking (pontos verdes) para "
                         "inspeção visual da qualidade do rastreio")
    ap.add_argument("--scan", type=float, metavar="SEGUNDOS", default=None,
                    help="acha a melhor janela deste tamanho para o solve, em "
                         "vez de rastrear. Faça isto ANTES de gastar minutos no "
                         "camera_solve_colmap.py")
    ap.add_argument("--transcript", type=Path, default=None,
                    help="transcripts/cut.json — com isto o --scan também exige "
                         "FALA na janela, não só movimento")
    args = ap.parse_args()

    if args.scan:
        r = scan(Path(args.video), args.scan, transcript=args.transcript)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        if not r.get("ok"):
            sys.exit(2)
        return

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

    # O debug roda mesmo com o gate reprovado — é justamente quando ver ajuda
    # mais: ele mostra POR QUE a cena foi recusada.
    if args.debug_video and "tracks" in m:
        render_debug(Path(args.video), m, Path(args.debug_video), args.start)
        resumo["debug_video"] = args.debug_video

    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
