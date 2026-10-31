"""Stabilise a take — robust to glossy cars, strength from take_analyzer.py.

Default engine `opencv` (Prisma): global camera motion per frame from sparse
optical flow + RANSAC partial-affine (reflections on paint/glass move unlike
the surface and are rejected as outliers), cumulative trajectory, Gaussian
smoothing over ±smoothing frames, per-frame correction warp, and ONE fixed zoom
just large enough to hide the borders of the whole clip (no breathing zoom).

Engine `vidstab` (ffmpeg vid.stab, 2-pass) is kept for matte subjects. Measured
on a glossy headlight macro (Taycan 4S, 2026-10-06): vid.stab produced a jump
every 4 frames (local-motion fields fooled by moving reflections); the opencv
engine on the same take: see the --check output.

Tip: a montage that also SLOWS the take (0.5–0.8) needs less smoothing — slowing
lowers the shake's frequency, so `light` (12) usually suffices.

Usage:
  python helpers/stabilize.py take.mp4 -o take_stab.mp4 --smoothing 12
  python helpers/stabilize.py take.mp4 -o take_stab.mp4 --analysis takes_analysis.json
  ... --engine vidstab   ... --check   (re-measure shake before/after)
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
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


def transforms(path: Path, work_w: int = 640):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev, T = None, []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        s = work_w / fr.shape[1]
        g = cv2.cvtColor(cv2.resize(fr, (work_w, int(fr.shape[0] * s))), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            dx = dy = da = 0.0
            p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 10)
            if p0 is not None and len(p0) >= 10:
                p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, g, p0, None)
                ok_ = st.ravel() == 1
                if ok_.sum() >= 10:
                    M, _ = cv2.estimateAffinePartial2D(p0[ok_], p1[ok_], method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    if M is not None:
                        dx, dy, da = M[0, 2] / s, M[1, 2] / s, np.arctan2(M[1, 0], M[0, 0])
            T.append((dx, dy, da))
        prev = g
    return np.array(T) if T else np.zeros((0, 3)), fps


def gauss_smooth(x: np.ndarray, sigma: float) -> np.ndarray:
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    return np.stack([np.convolve(np.pad(x[:, c], r, mode="reflect"), k, mode="valid") for c in range(x.shape[1])], 1)


def stab_opencv(src: Path, out: Path, smoothing: int, max_zoom: float = 1.12) -> dict:
    T, fps = transforms(src)
    # frames where tracking breaks (a flare, a reflection sweep) show as isolated
    # spikes; a 5-frame median removes them before they bend the whole path
    if len(T) >= 5:
        from scipy.signal import medfilt
        T = np.stack([medfilt(T[:, c], 5) for c in range(3)], 1)
    traj = np.vstack([[0, 0, 0], np.cumsum(T, axis=0)])
    smooth = gauss_smooth(traj, max(1.0, smoothing / 2))
    corr = smooth - traj                                     # per frame: dx, dy, dangle
    cap = cv2.VideoCapture(str(src))
    W, H = int(cap.get(3)), int(cap.get(4))
    # one fixed zoom that hides every frame's border (rotation adds to the need)
    need = 1 + 2 * max(np.abs(corr[:, 0]).max() / W, np.abs(corr[:, 1]).max() / H) + np.abs(corr[:, 2]).max() * 1.2
    zoom = float(min(need, max_zoom))
    if need > max_zoom:                                      # too shaky for the crop budget: scale corrections down
        corr *= (max_zoom - 1) / (need - 1)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", f"{fps}", "-i", "-", "-vf", "unsharp=5:5:0.4:3:3:0.2,format=yuv420p",
                            "-c:v", "libx264", "-crf", "15", "-preset", "fast", "-g", "15",
                            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(out)],
                           stdin=subprocess.PIPE)
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        dx, dy, da = corr[min(i, len(corr) - 1)]
        M = cv2.getRotationMatrix2D((W / 2, H / 2), np.degrees(da), zoom)
        M[:, 2] += (dx * zoom, dy * zoom)
        enc.stdin.write(cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).tobytes())
        i += 1
    enc.stdin.close(); enc.wait()
    return {"zoom": round(zoom, 3), "clamped": bool(need > max_zoom)}


def stab_vidstab(src: Path, out: Path, smoothing: int) -> dict:
    with tempfile.TemporaryDirectory() as td:
        trf = os.path.join(td, "t.trf").replace("\\", "/").replace(":", "\\:")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                        f"vidstabdetect=shakiness=6:accuracy=15:stepsize=6:result='{trf}'", "-f", "null", "-"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                        f"vidstabtransform=input='{trf}':smoothing={smoothing}:optzoom=1:interpol=bicubic,"
                        f"unsharp=5:5:0.5:3:3:0.3,format=yuv420p", "-c:v", "libx264", "-crf", "15", "-preset", "fast",
                        "-g", "15", "-an", str(out)], check=True)
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Take stabilisation (opencv RANSAC default, vid.stab optional)")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--smoothing", type=int, default=None, help="frames each side (12 light, 24 strong)")
    ap.add_argument("--analysis", type=Path, help="take_analyzer.py JSON (uses this take's vidstab_smoothing)")
    ap.add_argument("--engine", choices=["opencv", "vidstab"], default="opencv")
    ap.add_argument("--max-zoom", type=float, default=1.12)
    ap.add_argument("--check", action="store_true", help="re-measure shake before/after with take_analyzer")
    ap.add_argument("--keep-if-better", action="store_true",
                    help="keep the stabilised take only if shake drops >= 20% (else the original is written)")
    a = ap.parse_args()
    sm = a.smoothing
    if sm is None and a.analysis:
        sm = json.loads(a.analysis.read_text(encoding="utf-8")).get(a.video.stem, {}).get("vidstab_smoothing", 0)
    sm = 12 if sm is None else sm
    if sm <= 0:
        shutil.copy(a.video, a.output)
        print(f"{a.video.name}: no stabilisation needed — copied"); return
    info = stab_opencv(a.video, a.output, sm, a.max_zoom) if a.engine == "opencv" else stab_vidstab(a.video, a.output, sm)
    info.setdefault("zoom", 1.0)
    msg = f"{a.video.name} → {a.output.name} ({a.engine}, smoothing {sm}{', zoom ' + str(info['zoom']) if 'zoom' in info else ''})"
    if a.check or a.keep_if_better:
        from take_analyzer import analyse
        b, c = analyse(a.video)["shake_px"], analyse(a.output)["shake_px"] / info["zoom"]  # undo the crop's magnification
        gain = 1 - c / max(b, 1e-6)
        msg += f" · shake {b:.2f} → {c:.2f} px/frame ({gain:+.0%})"
        if a.keep_if_better and gain < 0.20:
            shutil.copy(a.video, a.output)
            msg += " → kept the ORIGINAL (gain < 20% is not worth the crop)"
    print(msg)


if __name__ == "__main__":
    main()
