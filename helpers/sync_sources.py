"""Sincroniza áudio externo / 2ª câmera / gravação de tela com o áudio da câmera (F4.5).

Podcast, entrevista com lapela, gravador separado, tela gravada à parte: até
aqui o Prisma só sabia cortar UMA fonte com o próprio áudio. Este helper mede,
por correlação cruzada (faixa da voz, 250–3500 Hz), quanto cada fonte está
deslocada em relação à câmera:

    tempo_na_câmera = tempo_na_fonte + offset

e diz o quanto confiar: a razão entre o pico da correlação e o segundo maior
pico, e a coerência medida em três janelas ao longo do trecho em comum. Se as
janelas discordam, o relógio do gravador DERIVA (comum em gravador barato): o
helper estima a deriva em ppm — um offset único escorregaria no fim do vídeo.
Confiança baixa → pergunte, não chute. Adaptado de `LeiteZ/fluxo-de-edicao`
(etapa preparar, MIT).

Saída: `<edit>/sync.json` — {reference, sources: [{name, offset_s, confidence,
drift_ppm, windows}]}.

Uso:
    uv run python helpers/sync_sources.py <camera.mp4> <lapela.wav> [<tela.mp4> …] --edit-dir <edit>
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

SR = 8000
GOOD = 6.0      # pico / 2º pico acima disto = confiança alta
FAIR = 3.0      # entre FAIR e GOOD = média; abaixo = baixa → perguntar
WIN = 30.0      # s de cada janela de conferência
EXCL = 0.05     # s em volta do pico excluídos ao procurar o 2º pico
SLIP_MS = 10.0  # escorregão previsto no trecho em comum a partir do qual a deriva importa


def load(path: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-af",
                        "highpass=f=250,lowpass=f=3500", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32).astype(np.float64)
    if not len(x):
        sys.exit(f"sem áudio em {path}")
    return (x - x.mean()) / (x.std() + 1e-12)


def xcorr_lag(ref: np.ndarray, oth: np.ndarray) -> tuple[float, float]:
    """(lag em s, razão pico/2º pico). lag > 0: o som aparece MAIS TARDE na câmera."""
    c = fftconvolve(ref, oth[::-1], mode="full")
    k = int(np.argmax(c))
    # refino sub-amostra (parábola nos 3 pontos do pico)
    if 0 < k < len(c) - 1:
        y0, y1, y2 = c[k - 1], c[k], c[k + 1]
        den = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / den if den else 0.0
    else:
        frac = 0.0
    lag = (k + frac - (len(oth) - 1)) / SR
    ex = int(EXCL * SR)
    c2 = c.copy()
    c2[max(0, k - ex):k + ex] = -np.inf
    second = float(np.max(c2)) if np.isfinite(np.max(c2)) else 1e-9
    ratio = float(c[k] / second) if second > 0 else 99.0
    return lag, ratio


def windows_check(ref: np.ndarray, oth: np.ndarray, off: float) -> list[dict]:
    """Re-mede o offset em 3 janelas do trecho em comum (para deriva de relógio)."""
    n_ref, n_oth = len(ref) / SR, len(oth) / SR
    a, b = max(0.0, off), min(n_ref, n_oth + off)       # trecho comum em tempo da câmera
    if b - a < 3 * min(WIN, (b - a) / 3) or b - a < 6:
        return []
    w = min(WIN, (b - a) / 3)
    out = []
    for c0 in (a, a + (b - a - w) / 2, b - w):
        r = ref[int(c0 * SR):int((c0 + w) * SR)]
        o_start = max(0.0, c0 - off - 1.0)             # 1 s de folga de cada lado
        o = oth[int(o_start * SR):int((c0 - off + w + 1.0) * SR)]
        lag, ratio = xcorr_lag(r, o)
        # t_cam − c0 = (t_fonte − o_start) + lag  →  offset = c0 − o_start + lag
        out.append({"at_camera_s": round(c0 + w / 2, 2),
                    "offset_s": round(c0 - o_start + lag, 6),
                    "ratio": round(ratio, 1)})
    return out


def sync(camera: Path, other: Path) -> dict:
    ref, oth = load(camera), load(other)
    lag, ratio = xcorr_lag(ref, oth)
    off = lag                                            # t_cam = t_oth + off
    wins = windows_check(ref, oth, off)
    drift = None
    if len(wins) == 3:
        t = np.array([x["at_camera_s"] for x in wins])
        o = np.array([x["offset_s"] for x in wins])
        slope = float(np.polyfit(t, o, 1)[0])
        drift = round(slope * 1e6, 1)
    conf = "alta" if ratio >= GOOD else ("média" if ratio >= FAIR else "baixa")
    # O que importa é quanto o som ESCORREGA no trecho em comum, não o ppm
    # sozinho: medido 2026-11-03, um corte de 23 s deu "−57 ppm" com menos de
    # 1 ms entre as janelas (ruído de medida) — alarme falso pelo ppm.
    common = min(len(ref) / SR, len(oth) / SR + off) - max(0.0, off)
    slip_ms = round(abs(drift) * 1e-6 * common * 1000, 1) if drift is not None else None
    if slip_ms is not None and slip_ms >= SLIP_MS and conf == "alta":
        conf = "média"  # offset certo no meio, escorrega nas pontas
    return {"name": other.name, "path": str(other), "offset_s": round(off, 6),
            "confidence": conf, "peak_ratio": round(ratio, 1), "drift_ppm": drift,
            "slip_ms": slip_ms, "windows": wins}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("camera", type=Path, help="a câmera — o relógio de referência do projeto")
    ap.add_argument("others", type=Path, nargs="+")
    ap.add_argument("--edit-dir", type=Path)
    a = ap.parse_args()
    res = {"reference": str(a.camera.resolve()), "sources": []}
    for o in a.others:
        s = sync(a.camera.resolve(), o.resolve())
        res["sources"].append(s)
        drift = (f" · deriva {s['drift_ppm']:+.0f} ppm (escorrega {s['slip_ms']} ms no trecho)"
                 if s["drift_ppm"] is not None else "")
        print(f"  {s['name']}: tempo_na_câmera = tempo_na_fonte {s['offset_s']:+.4f} s · "
              f"confiança {s['confidence']} (pico/2º {s['peak_ratio']}){drift}")
        for w in s["windows"]:
            print(f"      janela @ {w['at_camera_s']:7.1f}s → {w['offset_s']:+.4f} s (pico/2º {w['ratio']})")
        if s["confidence"] == "baixa":
            print("      ⚠ confiança baixa — confira uma palavra marcante nas duas fontes antes de usar")
        if s["slip_ms"] is not None and s["slip_ms"] >= SLIP_MS:
            print(f"      ⚠ relógio deriva: o som escorrega ~{s['slip_ms']:.0f} ms ao longo do trecho — "
                  f"um offset único não basta; reamostre a fonte ou sincronize por trecho")
    if a.edit_dir:
        p = a.edit_dir.resolve() / "sync.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  gravado {p}")


if __name__ == "__main__":
    main()
