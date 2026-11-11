"""Analyse takes for a music montage: camera shake vs intended move → stabilise? how slow?

For every take, global camera motion is tracked frame to frame (sparse optical
flow → partial affine: dx, dy, rotation). The cumulative trajectory is split
into the INTENDED move (Gaussian-smoothed over ~0.5 s) and SHAKE (the residual).

Per take it reports:
  shake_px     robust size of the frame-to-frame jitter (velocity minus its 0.2 s
               smoothing, whip frames excluded), px/frame at 1080 width
  shake_deg    RMS of the residual rotation
  move_px_s    median speed of the intended move (px/s at 1080 width)
  peak_move_t  where the move is fastest (good place for the ramp's fast part)
and recommends:
  stabilize    none | light | strong   (+ vid.stab smoothing for stabilize.py)
  speed        playback speed for the shot (most car/product takes look better
               slowed: weight and elegance, and slowing lowers the shake's
               frequency so it reads as float instead of jitter)

Rules (measured on phone footage, 1080 w):
  shake < 1.2 px → none · 1.2–3 px → light (smoothing 12) · > 3 px → strong (smoothing 24)
  speed starts at 0.75; −0.10 for light shake, −0.20 for strong; −0.10 when the
  move is fast (> 350 px/s, a sweep worth revealing); +0.15 for a near-static
  take (< 60 px/s: slow-mo of nothing adds nothing); 120 fps sources → 0.35–0.5
  (real slow motion). Clamped 0.4–1.0.

Usage:
  python helpers/take_analyzer.py takes/*.mp4 -o edit/takes_analysis.json
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
from pathlib import Path

import cv2
import numpy as np


def motion(path: Path, work_w: int = 540):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    step = max(1, int(round(fps / 30)))       # analyse at ~30 fps even for 120 fps takes
    prev, rows, i = None, [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step:
            i += 1; continue
        g = cv2.cvtColor(cv2.resize(fr, (work_w, int(fr.shape[0] * work_w / fr.shape[1]))), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            p0 = cv2.goodFeaturesToTrack(prev, 300, 0.01, 12)
            dx = dy = da = 0.0
            if p0 is not None and len(p0) >= 8:
                p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, g, p0, None)
                good = st.ravel() == 1
                if good.sum() >= 8:
                    M, _ = cv2.estimateAffinePartial2D(p0[good], p1[good], method=cv2.RANSAC)
                    if M is not None:
                        dx, dy, da = M[0, 2], M[1, 2], np.degrees(np.arctan2(M[1, 0], M[0, 0]))
            rows.append((dx, dy, da))
        prev = g
        i += 1
    eff_fps = fps / step
    a = np.array(rows) if rows else np.zeros((1, 3))
    a[:, :2] *= 1080.0 / work_w                       # px at 1080 width
    return a, eff_fps, fps, i / fps


def analyse(path: Path) -> dict:
    d, f, src_fps, dur = motion(path)
    # Shake lives in the VELOCITY: the frame-to-frame motion minus its own ~0.2 s
    # smoothing. (Residuals of the cumulative trajectory also count every change
    # of speed of an intended orbit as "shake" — measured: every take flagged.)
    sig = max(1.0, 0.1 * f)
    k = np.exp(-0.5 * (np.arange(-int(3 * sig), int(3 * sig) + 1) / sig) ** 2); k /= k.sum()
    pad = len(k) // 2
    sm = np.stack([np.convolve(np.pad(d[:, c], pad, mode="edge"), k, mode="valid") for c in range(3)], 1)
    hf = d - sm
    speed_f = np.linalg.norm(sm[:, :2], axis=1)            # intended px/frame
    calm = speed_f < np.quantile(speed_f, 0.85) if len(speed_f) > 6 else np.ones(len(speed_f), bool)
    jit = np.linalg.norm(hf[:, :2], axis=1)[calm]          # whips excluded (top 15% speed)
    shake_px = float(np.median(jit) * 1.4826) if len(jit) else 0.0   # robust, px/frame at 1080 w
    shake_deg = float(np.median(np.abs(hf[calm, 2])) * 1.4826) if calm.any() else 0.0
    move = float(np.median(speed_f) * f)
    peak_t = float(np.argmax(speed_f) / f) if len(speed_f) else 0.0

    stab = "none" if shake_px < 1.2 else "light" if shake_px < 3.0 else "strong"
    speed = 0.75 - {"none": 0, "light": 0.10, "strong": 0.20}[stab]
    if move > 350:
        speed -= 0.10
    if move < 60:
        speed += 0.15
    if src_fps >= 100:
        speed = 0.35 if move > 200 else 0.5
    speed = float(np.clip(round(speed, 2), 0.4, 1.0))
    return {"file": str(path), "duration": round(dur, 3), "fps": round(src_fps, 2),
            "shake_px": round(shake_px, 2), "shake_deg": round(shake_deg, 3),
            "move_px_s": round(move, 1), "peak_move_t": round(peak_t, 2),
            "stabilize": stab, "vidstab_smoothing": {"none": 0, "light": 12, "strong": 24}[stab],
            "speed": speed,
            "usable_source_s_per_beat_at_speed": None}


def main() -> None:
    ap = argparse.ArgumentParser(description="Shake / move analysis → stabilise + speed recommendations")
    ap.add_argument("takes", type=Path, nargs="+")
    ap.add_argument("-o", "--output", type=Path, required=True)
    a = ap.parse_args()
    res = {}
    print(f"{'take':28s} {'dur':>5s} {'fps':>5s} {'shake':>6s} {'rot':>6s} {'move':>7s}  stab    speed")
    for p in a.takes:
        r = analyse(p)
        r.pop("usable_source_s_per_beat_at_speed")
        res[p.stem] = r
        print(f"{p.stem:28s} {r['duration']:5.2f} {r['fps']:5.0f} {r['shake_px']:6.2f} {r['shake_deg']:6.3f} "
              f"{r['move_px_s']:7.1f}  {r['stabilize']:7s} {r['speed']:.2f}")
    a.output.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()
