"""Speed ramp a source span onto an exact output length (e.g. N beats).

The ramp is a speed curve over normalised output time. It is scaled so the
chosen source span [--in, --out] lands EXACTLY on --duration (or on N beats of
a beat_map.py grid), frame-accurate, so the cut after it hits the beat.

Picture quality is the point:
  * slow parts get real in-between frames (ffmpeg minterpolate, motion-
    compensated) instead of duplicated frames that stutter;
  * fast parts get REAL motion blur: every output frame averages the source
    frames its shutter would have seen (--shutter 180 = film look). Speed 4x →
    the shutter sweeps 2 source frames → natural smear; 0.3x → one sharp frame.

Presets (normalised output time : speed):
  whip-slow   0:1  0.30:4  0.50:0.35  0.80:0.35  1:1   punch in fast, hang on the hero moment
  ramp-in     0:4  0.45:4  0.70:0.4   1:0.4            arrive fast, land slow (end on the beat)
  ramp-out    0:0.4  0.35:0.4  0.6:4  1:4              hold slow, launch out fast into the cut
  bullet      0:1  0.20:0.2 0.80:0.2  1:1              bullet-time hold in the middle
  smooth      0:1  1:1                                 constant (still fitted to the length)
  speed-out / speed-in   the speed-ramp TRANSITION pair (A accelerates to 5x into
                         the cut, B enters at 5x and decelerates; -slow variants land/leave in slow-mo)
Custom: --curve "0:1,0.4:3,0.6:0.3,1:1"  (log-space quintic smootherstep between keys)

Usage:
  python helpers/speed_ramp.py take.mp4 --in 2.0 --out 6.5 --duration 1.94 --preset whip-slow -o r1.mp4
  python helpers/speed_ramp.py take.mp4 --in 2 --out 6.5 --beats beats.json --from-beat 12 --n-beats 4 -o r1.mp4
  ... --interp blend   (fast preview)   --interp none   (no new frames)   --shutter 0 (no blur)

Writes r1.mp4 (H.264, no audio) and r1.json (the time map + a HyperFrames
`data-automation` rate lane for an editable, lower-quality equivalent).
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
import math
import subprocess
from collections import deque
from pathlib import Path

import numpy as np

PRESETS = {
    # long, overlapping eases: no speed change shorter than ~20% of the shot
    "whip-slow": "0:1,0.15:1,0.40:3.5,0.62:0.4,0.88:0.4,1:0.6",
    "ramp-in": "0:4,0.12:4,0.62:0.4,1:0.4",
    "ramp-out": "0:0.4,0.38:0.4,0.88:4,1:4",
    "bullet": "0:1,0.30:0.25,0.70:0.25,1:1",
    "smooth": "0:1,1:1",
    # speed-ramp TRANSITION pair: A accelerates into the cut, B enters at the same
    # peak and decelerates — the cut hides inside the motion blur at max speed
    "speed-out": "0:1,0.35:1,1:5",
    "speed-in": "0:5,0.65:1,1:1",
    "speed-in-slow": "0:5,0.55:0.45,1:0.45",
    "speed-out-slow": "0:0.45,0.45:0.45,1:5",
}


def probe(path: Path) -> tuple[int, int, float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    w, h = s["width"], s["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", []) if "rotation" in d), 0)
    if rot in (90, 270):
        w, h = h, w
    return w, h, float(num) / float(den)


def parse_curve(spec: str) -> tuple[np.ndarray, np.ndarray]:
    pts = sorted((float(a), float(b)) for a, b in (p.split(":") for p in spec.split(",")))
    u, v = np.array([p[0] for p in pts]), np.array([max(p[1], 0.05) for p in pts])
    if u[0] > 0:
        u, v = np.r_[0, u], np.r_[v[0], v]
    if u[-1] < 1:
        u, v = np.r_[u, 1], np.r_[v, v[-1]]
    return u, v


def speed_at(x: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Speed between keys: interpolated in LOG space (the eye reads speed as a
    ratio — 4x→0.4x linearly stays fast and brakes at the very end; in log the
    deceleration feels even) with a quintic smootherstep (zero velocity AND
    zero acceleration of the speed at every key → no jolt entering or leaving
    a ramp)."""
    i = np.clip(np.searchsorted(u, x, side="right") - 1, 0, len(u) - 2)
    f = np.clip((x - u[i]) / np.maximum(u[i + 1] - u[i], 1e-9), 0, 1)
    f = f * f * f * (f * (f * 6 - 15) + 10)
    lv = np.log(v)
    return np.exp(lv[i] + (lv[i + 1] - lv[i]) * f)


def time_map(span: float, T: float, u: np.ndarray, v: np.ndarray, n: int = 4000):
    """t_out (0..T) -> source offset (0..span); returns (fn, speeds actually used)."""
    xs = np.linspace(0, 1, n + 1)
    s = speed_at(xs, u, v)
    cum = np.r_[0, np.cumsum((s[1:] + s[:-1]) / 2 * np.diff(xs))]  # ∫ s du, u in 0..1
    k = span / (T * cum[-1])  # scale so the whole span fits T exactly
    def fn(t):
        return np.interp(np.asarray(t) / T, xs, cum) * T * k
    return fn, s * k, xs


def frames(cmd: list[str], w: int, h: int):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)


def main() -> None:
    ap = argparse.ArgumentParser(description="Beat-fitted speed ramp with interpolation + real motion blur")
    ap.add_argument("video", type=Path)
    ap.add_argument("--in", dest="t_in", type=float, required=True, help="source in (s)")
    ap.add_argument("--out", dest="t_out", type=float, required=True, help="source out (s)")
    ap.add_argument("--duration", type=float, help="output length (s)")
    ap.add_argument("--beats", type=Path, help="beat_map.py JSON (length = n beats from --from-beat)")
    ap.add_argument("--from-beat", type=int, default=0)
    ap.add_argument("--n-beats", type=int, default=4)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="whip-slow")
    ap.add_argument("--curve", help='custom "u:speed,..." (overrides --preset)')
    ap.add_argument("--fps", type=float, default=30.0, help="output fps")
    ap.add_argument("--shutter", type=float, default=180.0, help="shutter angle; 0 = no blur")
    ap.add_argument("--interp", choices=["mci", "blend", "none"], default="mci")
    ap.add_argument("--max-up", type=int, default=8, help="cap on the interpolation factor")
    ap.add_argument("--width", type=int, default=None, help="scale output width (keeps aspect)")
    ap.add_argument("-o", "--output", type=Path, required=True)
    a = ap.parse_args()

    if a.beats:
        b = json.loads(a.beats.read_text(encoding="utf-8"))["beats"]
        if a.from_beat + a.n_beats >= len(b):
            raise SystemExit(f"beat grid has {len(b)} beats; {a.from_beat}+{a.n_beats} is past the end")
        T = b[a.from_beat + a.n_beats] - b[a.from_beat]
    elif a.duration:
        T = a.duration
    else:
        raise SystemExit("give --duration or --beats")
    nf = max(1, round(T * a.fps))
    T = nf / a.fps  # frame-exact
    span = a.t_out - a.t_in
    u, v = parse_curve(a.curve or PRESETS[a.preset])
    fn, speeds, xs = time_map(span, T, u, v)
    vmin, vmax = float(speeds.min()), float(speeds.max())

    W, H, sfps = probe(a.video)
    if a.width:
        H = int(round(H * a.width / W / 2) * 2); W = a.width
    # < 1 source frame per output frame → that many in-betweens are needed (120 fps at 0.25x needs none)
    need = vmin * sfps / a.fps  # source frames consumed per output frame at the slowest point
    up = 1 if a.interp == "none" else int(min(a.max_up, max(1, math.ceil(1 / max(need, 1e-3)))))
    ufps = sfps * up
    margin = 2 / sfps
    ss = max(0.0, a.t_in - margin)
    vf = [f"scale={W}:{H}:flags=lanczos"] if a.width else []
    if up > 1:
        vf.append(f"minterpolate=fps={ufps}:mi_mode={a.interp}" + (":mc_mode=aobmc:me_mode=bidir:vsbmc=1" if a.interp == "mci" else ""))
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.4f}", "-t", f"{span + 2 * margin:.4f}", "-i", str(a.video)]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    shutter = a.shutter / 360.0 / a.fps
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", f"{a.fps}", "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                            "-color_trc", "bt709", "-movflags", "+faststart", str(a.output)], stdin=subprocess.PIPE)
    src = frames(cmd, W, H)
    buf: deque = deque()  # (time_in_source, frame)
    idx = 0
    def fill_until(t):
        nonlocal idx
        while not buf or buf[-1][0] < t:
            try:
                f = next(src)
            except StopIteration:
                return
            buf.append((ss + idx / ufps, f)); idx += 1
    blurred = subblend = 0
    for i in range(nf):
        t0 = a.t_in + float(fn(i / a.fps))
        t1 = a.t_in + float(fn(min(T, i / a.fps + shutter))) if shutter > 0 else t0
        fill_until(t1 + 1 / ufps)
        while len(buf) > 2 and buf[1][0] <= t0:
            buf.popleft()
        # frames the open shutter saw; slow speeds see < 1 frame → the nearest one, sharp
        sel = [f for (t, f) in buf if t0 <= t <= t1]
        if len(sel) >= 2:
            blurred += 1
            out = np.mean(np.stack(sel).astype(np.float32), axis=0).astype(np.uint8)
        else:
            # sub-frame position: nearest-frame picking makes the cadence alternate
            # (1,1,2,1,1,2 frames…) = judder. Blend the two frames around the exact
            # source time by their distance → an even, smooth cadence.
            mid = (t0 + t1) / 2
            before = [p for p in buf if p[0] <= mid]
            after = [p for p in buf if p[0] > mid]
            if before and after:
                (ta, fa), (tb, fb) = before[-1], after[0]
                w = (mid - ta) / max(tb - ta, 1e-9)
                if 0.12 < w < 0.88:
                    out = (fa.astype(np.float32) * (1 - w) + fb.astype(np.float32) * w).astype(np.uint8)
                    subblend += 1
                else:
                    out = fa if w <= 0.12 else fb
            else:
                out = min(buf, key=lambda p: abs(p[0] - mid))[1]
        enc.stdin.write(out.tobytes())
    enc.stdin.close(); enc.wait()

    # editable equivalent for the HyperFrames editor (no interpolation / blur there)
    lane = [{"t": round(float(x) * T, 3), "v": round(float(np.clip(s, 0.1, 10)), 3)}
            for x, s in zip(xs[::200], speeds[::200])]
    meta = {"source": str(a.video), "in": a.t_in, "out": a.t_out, "duration": round(T, 4), "frames": nf,
            "fps": a.fps, "speed_min": round(vmin, 3), "speed_max": round(vmax, 3), "interp_factor": up,
            "shutter": a.shutter, "blurred_frames": blurred, "subframe_blends": subblend,
            "hyperframes_rate_lane": {"version": 1, "lanes": [{"target": "rate", "points": lane}]}}
    a.output.with_suffix(".json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{a.output.name}: {span:.2f}s of source → {T:.3f}s ({nf} frames) · speed {vmin:.2f}x–{vmax:.2f}x · "
          f"interp x{up} ({a.interp}) · {blurred} motion-blurred · {subblend} sub-frame blends")
    # speed graph for QC (log scale, 0.25x..8x)
    import cv2
    Wg, Hg = 900, 260
    g = np.full((Hg, Wg, 3), 20, np.uint8)
    yv = lambda v: int(Hg - 20 - (np.log2(np.clip(v, 0.25, 8)) + 2) / 5 * (Hg - 40))
    for ref in (0.25, 0.5, 1, 2, 4, 8):
        cv2.line(g, (0, yv(ref)), (Wg, yv(ref)), (60, 60, 60) if ref != 1 else (110, 110, 110), 1)
        cv2.putText(g, f"{ref}x", (4, yv(ref) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
    pts = np.array([[int(x * (Wg - 1)), yv(sp)] for x, sp in zip(xs, speeds)], np.int32)
    cv2.polylines(g, [pts], False, (80, 200, 255), 2)
    cv2.imwrite(str(a.output.with_suffix(".speed.png")), g)


if __name__ == "__main__":
    main()
