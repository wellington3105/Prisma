"""Per-take colour pipeline for multi-take edits shot in mixed / LOW light.

One look on top of unmatched takes amplifies their differences (one take noisy
and dark, the next warm and bright). This measures every take, CORRECTS it
toward a reference, then applies one shared look — the order a colourist works:

  1. denoise    hqdn3d, strength from the measured noise (luma + stronger chroma;
                temporal, which is where low-light grain is removed best)
  2. balance    neutral pixels (low saturation, mid-high luma: floors, walls,
                ceilings) pulled to grey by per-channel gains (--wb-strength)
  3. exposure   one monotone curve (pchip): black point → 0.02, the take's
                median → toward the reference median (--match), white point →
                0.94 with a soft shoulder above (headlights/reflections roll off
                instead of clipping)
  4. look       the shared creative grade (--look, a spaceless ffmpeg chain)
  5. clarity    mid-radius unsharp after the denoise (detail without grain)

Writes graded takes (same names) into --out, a before/after sheet (one frame
per take: top = in, bottom = out) and a JSON report with the spread of take
medians and the noise before/after — the numbers that say "the takes match".

Usage:
  python helpers/color_pipeline.py takes/*.mp4 --out graded/ --ref takes/hero.mp4 \
      --look "eq=contrast=1.14:brightness=-0.035:saturation=1.08,colorbalance=bs=0.06:bm=0.025:rh=0.025"
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np


def samples(p: Path, n: int = 8) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(p))
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) / n * N))
        ok, f = cap.read()
        if ok:
            out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return out


def stats(frames: list[np.ndarray]) -> dict:
    Y, neutral, noise = [], [], []
    for f in frames:
        small = cv2.resize(f, (270, 480)).astype(np.float32)
        y = small @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        Y.append(y.ravel())
        mx, mn = small.max(-1), small.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1)
        m = (sat < 0.12) & (y > 70) & (y < 235)
        if m.sum() > 200:
            neutral.append(small[m].mean(0))
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
        hp = g - cv2.GaussianBlur(g, (0, 0), 1.2)
        grad = cv2.GaussianBlur(np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1)), (0, 0), 3)
        flat = grad <= np.quantile(grad, 0.3)
        noise.append(float(np.median(np.abs(hp[flat])) * 1.4826))
    Y = np.concatenate(Y)
    return {"p_black": float(np.quantile(Y, 0.005)), "p_shadow": float(np.quantile(Y, 0.20)),
            "median": float(np.median(Y)), "p_white": float(np.quantile(Y, 0.995)),
            "neutral_rgb": (np.mean(neutral, 0).tolist() if neutral else None), "noise": float(np.median(noise))}


def chain(st: dict, ref: dict, a) -> tuple[str, dict]:
    nz = st["noise"]
    ls = float(np.clip(nz * 1.1, 1.0, 6.0)); cs = ls * 1.4
    parts = [f"hqdn3d={ls:.2f}:{cs:.2f}:{ls * 1.6:.2f}:{cs * 1.6:.2f}"]
    gains = [1.0, 1.0, 1.0]
    if st["neutral_rgb"]:
        r, g, b = st["neutral_rgb"]
        m = (r + g + b) / 3
        gains = [1 + (m / max(c, 1) - 1) * a.wb_strength for c in (r, g, b)]
        gains = [float(np.clip(x, 0.8, 1.25)) for x in gains]
        parts.append(f"colorchannelmixer=rr={gains[0]:.4f}:gg={gains[1]:.4f}:bb={gains[2]:.4f}")
    b0, med, w0 = st["p_black"] / 255, st["median"] / 255, st["p_white"] / 255
    # asymmetric exposure match: brighten dark takes toward the reference, but
    # darken bright ones only by --darken-limit of the gap (low light: never
    # throw away exposure the camera managed to get)
    gap = ref["median"] / 255 - med
    tgt = med + gap * (a.match if gap > 0 else a.match * a.darken_limit)
    tgt = float(np.clip(tgt, 0.18, 0.62))
    b0 = min(b0, med - 0.05); w0 = max(w0, med + 0.1)
    # shadow protection: in low light the SUBJECT often lives in the shadows (a
    # dark-blue car on a white floor — measured: a median-led curve crushed the
    # car to near-black). The 20th percentile never goes below where it was;
    # if that collides with the median target, the target yields (not the shadows).
    sh = st["p_shadow"] / 255
    pts = [(0, 0), (b0, 0.02), (w0, 0.94), (1, 1)]
    if b0 + 0.02 < sh < med - 0.03:
        sh_out = max(sh, min(sh * a.shadow_lift + 0.01, 0.45))
        pts.append((sh, sh_out))
        tgt = max(tgt, sh_out + (med - sh) * 0.6)
    pts.append((med, min(tgt, 0.9)))
    pts = sorted({round(x, 4): y for x, y in pts}.items())
    parts.append("curves=interp=pchip:master='" + " ".join(f"{x:.4f}/{y:.4f}" for x, y in pts) + "'")
    if a.look:
        parts.append(a.look)
    parts.append("unsharp=7:7:0.35:5:5:0.0")
    return ",".join(["format=gbrp"] + parts + ["format=yuv420p"]), {"denoise": ls, "wb_gains": gains, "curve": pts}


def frame_at(p: Path, frac: float = 0.5) -> np.ndarray:
    cap = cv2.VideoCapture(str(p)); N = int(cap.get(7)); cap.set(1, int(N * frac)); ok, f = cap.read()
    return f


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-take colour pipeline: denoise → balance → exposure → look → clarity")
    ap.add_argument("takes", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ref", type=Path, help="reference take (default: the median of all takes)")
    ap.add_argument("--look", default="", help="shared creative grade, spaceless ffmpeg filters")
    ap.add_argument("--match", type=float, default=0.6, help="0..1 how far medians move toward the reference")
    ap.add_argument("--wb-strength", type=float, default=0.7)
    ap.add_argument("--shadow-lift", type=float, default=1.10, help="20th-percentile output = input × this (+0.01)")
    ap.add_argument("--darken-limit", type=float, default=0.3, help="fraction of --match used when a take must get darker")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    S = {p.stem: stats(samples(p)) for p in a.takes}
    ref = stats(samples(a.ref)) if a.ref else {"median": float(np.median([s["median"] for s in S.values()]))}
    plans = {p.stem: chain(S[p.stem], ref, a) for p in a.takes}

    def run(p: Path):
        vf, _ = plans[p.stem]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf", vf, "-c:v", "libx264", "-crf", "15",
                        "-preset", "fast", "-g", "15", "-an", "-colorspace", "bt709", "-color_primaries", "bt709",
                        "-color_trc", "bt709", "-color_range", "tv", str(a.out / p.name)], check=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, a.takes))

    after = {p.stem: stats(samples(a.out / p.name)) for p in a.takes}
    rep = {k: {"before": S[k], "after": after[k], "applied": plans[k][1]} for k in S}
    spread_b = float(np.std([S[k]["median"] for k in S])); spread_a = float(np.std([after[k]["median"] for k in S]))
    noise_b = float(np.mean([S[k]["noise"] for k in S])); noise_a = float(np.mean([after[k]["noise"] for k in S]))
    sh_b = float(np.mean([S[k]["p_shadow"] for k in S])); sh_a = float(np.mean([after[k]["p_shadow"] for k in S]))
    rep["_summary"] = {"median_spread_before": round(spread_b, 2), "median_spread_after": round(spread_a, 2),
                       "shadow_p20_before": round(sh_b, 1), "shadow_p20_after": round(sh_a, 1),
                       "noise_before": round(noise_b, 2), "noise_after": round(noise_a, 2)}
    (a.out / "color_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    tiles_b, tiles_a = [], []
    for p in a.takes:
        tiles_b.append(cv2.resize(frame_at(p), (144, 256)))
        tiles_a.append(cv2.resize(frame_at(a.out / p.name), (144, 256)))
    per = 10
    rows = []
    for i in range(0, len(tiles_b), per):
        b = tiles_b[i:i + per]; c = tiles_a[i:i + per]
        pad = [np.zeros_like(b[0])] * (per - len(b))
        rows += [np.hstack(b + pad), np.hstack(c + pad), np.zeros((12, 144 * per, 3), np.uint8)]
    cv2.imwrite(str(a.out / "before_after.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"{len(a.takes)} takes · take-median spread {spread_b:.1f} → {spread_a:.1f} (luma) · "
          f"shadows p20 {sh_b:.1f} → {sh_a:.1f} · noise {noise_b:.2f} → {noise_a:.2f} · sheet {a.out / 'before_after.jpg'}")


if __name__ == "__main__":
    main()
