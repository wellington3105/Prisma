"""Film emulation + light VFX, baked per shot (the "optical finish" of a cinema edit).

Order per frame (light is added in linear light, BEFORE the print curve, the way
a lens and film stock would see it):
  1. highlights   luminance above --threshold, kept with their colour
  2. bloom        neutral multi-scale glow of the highlights (lens veiling)
  3. halation     red-orange fringe around bright edges (light bouncing off the
                  film base back into the red layer) — the strongest "film" cue
  4. streaks      anamorphic horizontal flares, steel-blue, only from the very
                  brightest points (headlights, LED bars) — nothing is invented
                  where there is no light source
  5. sweep        a soft diagonal band of light travelling over the PAINT (mask =
                  the car's own hue range, no model needed), modulated by luma
  6. light-hit    a 3-frame pulse that boosts 1–5 on the drop frame (replaces a
                  white flash: the light itself flares)
  7. print curve  toe + soft shoulder (highlights roll off instead of clipping)
  8. hue fixes    pull a hue range toward a target (e.g. a violet-drifting blue
                  paint back to 230°, a pink tail-light back to red)

All strengths are per shot (JSON), so a quiet "breathing" shot gets base levels
and the hook / drops get their peaks.

Usage:
  python helpers/film_look.py in.mp4 -o out.mp4 --params '{"halation":0.25,"bloom":0.15}'
  python helpers/film_look.py in.mp4 -o out.mp4 --params-file shot.json --qc 0.5
Params (defaults): threshold .82, bloom .15, halation .25, halation_radius .009,
  streaks 0, streak_threshold .93, streak_length .30, sweep null|{at,dur,angle,width,strength,hue:[lo,hi]},
  hit null|{frame:0,frames:4,gain:2.2}, curve .6, hue_fix [{from:[lo,hi],to:deg,strength}], crf 14
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
from pathlib import Path

import cv2
import numpy as np

DEFAULTS = {"threshold": 0.82, "bloom": 0.15, "halation": 0.25, "halation_radius": 0.009,
            "streaks": 0.0, "streak_threshold": 0.93, "streak_length": 0.30,
            "sweep": None, "hit": None, "curve": 0.6, "hue_fix": [], "crf": 14}


def probe(p: Path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate,nb_frames", "-of", "json", str(p)],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return s["width"], s["height"], float(n) / float(d)


def to_lin(x):  # sRGB-ish → linear
    return np.power(np.clip(x, 0, 1), 2.2)


def to_srgb(x):
    return np.power(np.clip(x, 0, None), 1 / 2.2)


def print_curve(x, amount):
    """filmic toe + soft shoulder on display values; amount 0..1."""
    if amount <= 0:
        return np.clip(x, 0, 1)
    shoulder = 1 - np.exp(-x * 2.2) / 1 if False else None
    # soft shoulder above 0.75, gentle toe below 0.08
    y = np.where(x < 0.75, x, 0.75 + (1 - np.exp(-(x - 0.75) * 4)) * 0.25 / (1 - np.exp(-1.0)))
    y = np.where(y < 0.08, 0.08 * (y / 0.08) ** 1.12, y)
    return np.clip(x + (y - x) * amount, 0, 1)


def hue_fix(rgb, fixes):
    if not fixes:
        return rgb
    hsv = cv2.cvtColor((np.clip(rgb, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h = hsv[..., 0] * 360 / 256
    s = hsv[..., 1] / 255
    for f in fixes:
        lo, hi = f["from"]
        tgt = f["to"]
        st = f.get("strength", 0.7)
        center = (lo + hi) / 2 if lo <= hi else ((lo + hi + 360) / 2) % 360
        half = ((hi - lo) % 360) / 2
        d = (h - center + 180) % 360 - 180
        w = np.clip(1 - np.abs(d) / max(half, 1e-3), 0, 1) ** 0.7 * np.clip((s - 0.12) / 0.2, 0, 1)
        delta = (tgt - h + 180) % 360 - 180
        h = (h + delta * w * st) % 360
    hsv[..., 0] = h * 256 / 360
    out = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB_FULL).astype(np.float32) / 255
    # keep the original luminance detail (8-bit HSV round trip is coarse)
    lum_o = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    lum_n = out @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return np.clip(out + (lum_o - lum_n)[..., None], 0, 1)


class FilmLook:
    def __init__(self, p: dict, W: int, H: int, fps: float, n_frames: int):
        self.p = {**DEFAULTS, **p}
        self.W, self.H, self.fps, self.n = W, H, fps, n_frames
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx / W, yy / H

    def __call__(self, rgb8: np.ndarray, i: int) -> np.ndarray:
        p = self.p
        x = rgb8.astype(np.float32) / 255
        lin = to_lin(x)
        lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        gain = 1.0
        if p["hit"]:
            k = i - int(p["hit"].get("frame", 0))
            frames = int(p["hit"].get("frames", 4))
            if 0 <= k < frames:
                gain = 1 + (p["hit"].get("gain", 2.2) - 1) * (1 - k / frames) ** 1.5
        thr = to_lin(np.float32(p["threshold"]))
        hi = np.clip((lum - thr) / (1 - thr), 0, 1)[..., None] * lin * gain
        small = cv2.resize(hi, (self.W // 4, self.H // 4), interpolation=cv2.INTER_AREA)
        add = np.zeros_like(lin)
        if p["bloom"] > 0:
            b = sum(cv2.GaussianBlur(small, (0, 0), s) * w for s, w in ((3, 0.5), (9, 0.3), (24, 0.2)))
            add += cv2.resize(b, (self.W, self.H), interpolation=cv2.INTER_LINEAR) * p["bloom"] * 2.0 * gain
        if p["halation"] > 0:
            r = max(1.0, p["halation_radius"] * self.W / 4)
            hb = cv2.GaussianBlur(small.mean(-1), (0, 0), r) - cv2.GaussianBlur(small.mean(-1), (0, 0), r * 0.35)
            hb = cv2.resize(np.clip(hb, 0, None), (self.W, self.H), interpolation=cv2.INTER_LINEAR)
            add += hb[..., None] * np.array([1.0, 0.34, 0.10], np.float32) * p["halation"] * 4.0 * gain
        if p["streaks"] > 0:
            st_thr = to_lin(np.float32(p["streak_threshold"]))
            core = np.clip((lum - st_thr) / (1 - st_thr), 0, 1)
            cs = cv2.resize(core, (self.W // 2, self.H // 2), interpolation=cv2.INTER_AREA)
            L = max(3, int(p["streak_length"] * self.W / 2))
            sk = sum(cv2.blur(cs, (max(3, int(L * f)) | 1, 1)) * w for f, w in ((1.0, 0.5), (0.45, 0.3), (0.15, 0.2)))
            sk = cv2.GaussianBlur(sk, (0, 0), 1.2)
            sk = cv2.resize(sk, (self.W, self.H), interpolation=cv2.INTER_LINEAR)
            add += sk[..., None] * np.array([0.55, 0.75, 1.0], np.float32) * p["streaks"] * 6.0 * gain
        out = lin + add
        if p["sweep"]:
            sw = p["sweep"]
            t = i / self.fps
            at, dur = sw.get("at", 0.0), sw.get("dur", 1.2)
            if at <= t <= at + dur:
                u = (t - at) / dur
                ang = np.radians(sw.get("angle", 25))
                proj = self.xx * np.cos(ang) + self.yy * np.sin(ang)
                pos = -0.3 + 1.9 * (u * u * (3 - 2 * u))           # eased travel across the frame
                band = np.exp(-((proj - pos) / sw.get("width", 0.08)) ** 2)
                hsv = cv2.cvtColor(rgb8, cv2.COLOR_RGB2HSV_FULL)
                hue = hsv[..., 0].astype(np.float32) * 360 / 256
                lo, hi_ = sw.get("hue", [205, 255])
                paint = ((hue >= lo) & (hue <= hi_) & (hsv[..., 1] > 50) & (hsv[..., 2] > 18)).astype(np.uint8)
                paint = cv2.morphologyEx(paint, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
                paint = cv2.GaussianBlur(paint.astype(np.float32), (0, 0), 3)
                env = np.sin(np.pi * u)
                # a sweep is a REFLECTION: it rides the paint's own sheen (measured: flat
                # white added in linear light washed the dark-blue car to grey)
                sheen = np.clip(x.max(-1) - 0.08, 0, 1) ** 1.3
                core = band ** 2.5                                  # bright core inside a soft band
                k = (0.35 * band + 0.65 * core) * paint * sheen * sw.get("strength", 0.6) * env
                out += k[..., None] * np.array([0.85, 0.93, 1.0], np.float32)
        disp = to_srgb(out)
        disp = print_curve(disp, p["curve"])
        disp = hue_fix(disp, p["hue_fix"])
        if p.get("grain"):
            # film grain baked per frame (same seed scheme and amount in every shot →
            # one constant texture across the film); strongest in the mid-tones like
            # emulsion, weaker in shadows/highlights
            gr = p["grain"]
            rs = np.random.default_rng((int(gr.get("seed", 7)) * 1_000_003 + int(gr.get("offset", 0)) + i) & 0xFFFFFFFF)
            n = rs.standard_normal((self.H, self.W)).astype(np.float32)
            if gr.get("size", 1.0) > 1.0:
                n = cv2.GaussianBlur(n, (0, 0), (gr["size"] - 1.0) * 0.6 + 0.3)
                n /= n.std() + 1e-6
            l = disp @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            resp = (4 * l * (1 - l)) ** 0.8
            disp = disp + (n * resp * gr.get("amount", 0.035))[..., None]
        return (np.clip(disp, 0, 1) * 255 + 0.5).astype(np.uint8)


def run(src: Path, dst: Path, params: dict, qc: list[float] | None = None) -> dict:
    W, H, fps = probe(src)
    n = int(cv2.VideoCapture(str(src)).get(cv2.CAP_PROP_FRAME_COUNT))
    fl = FilmLook(params, W, H, fps, n)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-crf", str(fl.p["crf"]), "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                            "-color_trc", "bt709", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    want = {int(round(t * fps)) for t in (qc or [])}
    shots, i = [], 0
    while True:
        b = dec.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        f = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        o = fl(f, i)
        enc.stdin.write(o.tobytes())
        if i in want:
            shots.append(np.hstack([f, o]))
        i += 1
    enc.stdin.close(); enc.wait()
    if shots:
        sheet = np.vstack([cv2.resize(s, (s.shape[1] * 640 // s.shape[0], 640)) for s in shots])
        cv2.imwrite(str(dst.with_name(dst.stem + "_qc.jpg")), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    return {"frames": i, "fps": fps}


def main() -> None:
    ap = argparse.ArgumentParser(description="Film emulation + light VFX per shot")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--params-file", type=Path)
    ap.add_argument("--qc", type=float, nargs="*", help="times (s): before|after side by side")
    a = ap.parse_args()
    params = json.loads(a.params_file.read_text(encoding="utf-8")) if a.params_file else json.loads(a.params)
    r = run(a.video, a.output, params, a.qc)
    print(f"{a.output.name}: {r['frames']} frames @ {r['fps']:g} fps" + (" + qc" if a.qc else ""))


if __name__ == "__main__":
    main()
