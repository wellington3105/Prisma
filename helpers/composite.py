"""Composite a keyed / matted subject over a new background so it BELONGS there.

A cutout pasted on a plate reads fake for a handful of measurable reasons —
the subject keeps its old light and colour, its edge is digitally hard and
untouched by the new environment, its grain differs from the plate, it casts
no shadow, and the two layers do not move as one camera. Each flag fixes one:

  --match 0..1     colour/light match: the subject's LAB mean/std pulled toward
                   the plate's (luma by --match, tint by --match×0.6)
  --wrap 0..1      light wrap: the blurred plate bleeds onto the subject's rim
                   (screen blend inside a --wrap-px band) — the #1 realism cue
  --edge px        soften the matte edge (kills the "sticker" line)
  --grain auto|N   add grain to the subject to match the plate's noise (auto =
                   measured high-pass std of the plate), then a light unifying
                   grain over the whole frame
  --shadow dx,dy,blur,opacity   contact/drop shadow from the matte
  --bg-blur px     depth of field on the plate (subject in focus)
  --shake px       handheld camera: low-frequency drift + micro-rotation applied
                   to the FINAL comp, so both layers move as one camera
  --vignette 0..1

Subject: alpha .webm/.mov (from chroma_key.py / person_matte.py) or a PNG.
Plate:   image or video (looped/held). Output: H.264 .mp4 at the subject's fps.

Usage:
  python helpers/composite.py --fg subject.webm --bg plate.jpg -o comp.mp4 \
      --scale 1.0 --x 0 --y 300 --match 0.6 --wrap 0.5 --edge 1.5 --grain auto \
      --shadow 0,30,40,0.35 --bg-blur 4 --shake 6 --start 0 --duration 5
  ... --qc 1.0 3.0     # side-by-side: plain paste vs this comp
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import itertools
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np


def probe(p: Path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate,codec_name:format=duration", "-of", "json", str(p)],
                                  capture_output=True, text=True, check=True).stdout)
    st = s["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return st["width"], st["height"], float(n) / float(d), st.get("codec_name", ""), float(s["format"].get("duration", 0))


def video_frames(p: Path, w: int, h: int, alpha: bool, vp9: bool, start: float = 0, dur: float | None = None,
                 size: tuple[int, int] | None = None):
    cmd = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if vp9 else []) + ["-ss", f"{start}"]
    if dur:
        cmd += ["-t", f"{dur}"]
    cmd += ["-i", str(p)]
    if size:
        cmd += ["-vf", f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]}"]
        w, h = size
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    c = 4 if alpha else 3
    while True:
        b = proc.stdout.read(w * h * c)
        if len(b) < w * h * c:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, c)


def lab_stats(rgb: np.ndarray, mask: np.ndarray | None = None):
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    px = lab[mask > 0.5] if mask is not None else lab.reshape(-1, 3)
    return px.mean(0), px.std(0) + 1e-3


def noise_std(rgb: np.ndarray) -> float:
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    hp = g - cv2.GaussianBlur(g, (0, 0), 1.5)
    return float(np.median(np.abs(hp)) * 1.4826)  # robust std of the fine noise


class Comp:
    def __init__(self, a, W, H, rng):
        self.a, self.W, self.H, self.rng = a, W, H, rng
        self.t = 0

    def layer(self, fg_rgba: np.ndarray, plate: np.ndarray, plate_stats, plate_noise) -> tuple[np.ndarray, np.ndarray]:
        a, W, H = self.a, self.W, self.H
        if a.scale != 1.0:
            fg_rgba = cv2.resize(fg_rgba, (int(fg_rgba.shape[1] * a.scale), int(fg_rgba.shape[0] * a.scale)),
                                 interpolation=cv2.INTER_AREA if a.scale < 1 else cv2.INTER_LANCZOS4)
        canvas = np.zeros((H, W, 4), np.uint8)
        x0, y0 = a.x, a.y
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        w = min(fg_rgba.shape[1] - sx0, W - dx0); h = min(fg_rgba.shape[0] - sy0, H - dy0)
        if w > 0 and h > 0:
            canvas[dy0:dy0 + h, dx0:dx0 + w] = fg_rgba[sy0:sy0 + h, sx0:sx0 + w]
        fg = canvas[..., :3].copy()
        al = canvas[..., 3].astype(np.float32) / 255
        if a.edge > 0:
            al = cv2.GaussianBlur(al, (0, 0), a.edge)
        bg = plate.astype(np.float32)
        if a.bg_blur > 0:
            bg = cv2.GaussianBlur(bg, (0, 0), a.bg_blur)
        if a.match > 0 and (al > 0.5).any():
            m_fg, s_fg = lab_stats(fg, al)
            m_bg, s_bg = plate_stats
            lab = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
            k = np.array([a.match, a.match * 0.6, a.match * 0.6])
            tgt_m = m_fg + (m_bg - m_fg) * k
            tgt_s = s_fg + (s_bg - s_fg) * k * np.array([0.5, 0.0, 0.0])  # contrast only on luma, gently
            lab = (lab - m_fg) / s_fg * tgt_s + tgt_m
            fg = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
        fgf = fg.astype(np.float32)
        if a.wrap > 0:
            wrap_src = cv2.GaussianBlur(plate.astype(np.float32), (0, 0), a.wrap_px)
            inner = cv2.GaussianBlur(al, (0, 0), a.wrap_px * 0.6)
            band = np.clip(al - inner, 0, 1) * 2.2           # rim inside the subject
            band = np.clip(band, 0, 1)[..., None] * a.wrap
            screen = 255 - (255 - fgf) * (255 - wrap_src) / 255
            fgf = fgf + (screen - fgf) * band
        if a.grain is not None:
            target = plate_noise if a.grain == "auto" else float(a.grain)
            have = noise_std(fg)
            add = max(target ** 2 - have ** 2, 0) ** 0.5
            if add > 0.2:
                fgf = fgf + self.rng.normal(0, add, fgf.shape[:2])[..., None]
        out = bg.copy()
        if a.shadow:
            dx, dy, blur, op = a.shadow
            sh = np.roll(np.roll(al, int(dy), 0), int(dx), 1)
            sh = cv2.GaussianBlur(sh, (0, 0), blur) * op
            out = out * (1 - sh[..., None])
        out = fgf * al[..., None] + out * (1 - al[..., None])
        return out, al

    def finish(self, img: np.ndarray) -> np.ndarray:
        a, W, H = self.a, self.W, self.H
        if a.grain is not None:
            img = img + self.rng.normal(0, 1.2, img.shape[:2])[..., None]  # unifying grain
        if a.vignette > 0:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
            img = img * (1 - a.vignette * np.clip(r - 0.55, 0, 1)[..., None] * 1.6)
        if a.shake > 0:
            t = self.t / a.fps
            dx = a.shake * (np.sin(t * 1.3) * 0.6 + np.sin(t * 2.9 + 1) * 0.3 + np.sin(t * 7.1 + 2) * 0.1)
            dy = a.shake * (np.sin(t * 1.1 + 3) * 0.6 + np.sin(t * 3.3) * 0.3 + np.sin(t * 6.3 + 4) * 0.1)
            rot = a.shake * 0.02 * np.sin(t * 0.9 + 5)
            z = 1 + a.shake * 2.2 / min(W, H)  # overscan so the edges never show
            M = cv2.getRotationMatrix2D((W / 2, H / 2), rot, z)
            M[:, 2] += (dx, dy)
            img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        self.t += 1
        return np.clip(img, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description="Realistic composite: subject (alpha) over a plate")
    ap.add_argument("--fg", type=Path, required=True)
    ap.add_argument("--bg", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--size", default="1080x1920")
    ap.add_argument("--start", type=float, default=0.0, help="subject start (s)")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--bg-start", type=float, default=0.0)
    ap.add_argument("--bg-zoom", type=float, default=1.0, help="still plate: zoom past cover-fit")
    ap.add_argument("--bg-focus", default="0.5,0.5", help="still plate: normalised point kept at frame centre")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--match", type=float, default=0.5)
    ap.add_argument("--wrap", type=float, default=0.5)
    ap.add_argument("--wrap-px", type=float, default=28)
    ap.add_argument("--edge", type=float, default=1.2)
    ap.add_argument("--grain", default="auto", help="auto | number | none")
    ap.add_argument("--shadow", default=None, help="dx,dy,blur,opacity")
    ap.add_argument("--bg-blur", type=float, default=0.0)
    ap.add_argument("--shake", type=float, default=0.0)
    ap.add_argument("--vignette", type=float, default=0.25)
    ap.add_argument("--qc", type=float, nargs="*", default=None, help="times (s): plain paste vs comp")
    a = ap.parse_args()
    a.grain = None if a.grain == "none" else ("auto" if a.grain == "auto" else float(a.grain))
    a.shadow = tuple(float(v) for v in a.shadow.split(",")) if a.shadow else None
    W, H = (int(v) for v in a.size.split("x"))

    fw, fh, fps, fcodec, fdur = probe(a.fg)
    a.fps = fps
    dur = a.duration or (fdur - a.start)
    is_img = a.bg.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    if is_img:
        im = cv2.cvtColor(cv2.imread(str(a.bg)), cv2.COLOR_BGR2RGB)
        s = max(W / im.shape[1], H / im.shape[0]) * a.bg_zoom
        im = cv2.resize(im, (int(im.shape[1] * s + 0.5), int(im.shape[0] * s + 0.5)), interpolation=cv2.INTER_LANCZOS4)
        fx, fy = (float(v) for v in a.bg_focus.split(","))  # point of the plate kept at frame centre
        ox = int(np.clip(fx * im.shape[1] - W / 2, 0, im.shape[1] - W))
        oy = int(np.clip(fy * im.shape[0] - H / 2, 0, im.shape[0] - H))
        still = im[oy:oy + H, ox:ox + W]
        plates = itertools.repeat(still)
    else:
        bw, bh, *_ = probe(a.bg)
        plates = video_frames(a.bg, bw, bh, False, False, a.bg_start, None, (W, H))
    fgs = video_frames(a.fg, fw, fh, True, fcodec == "vp9", a.start, dur) if a.fg.suffix.lower() != ".png" \
        else itertools.repeat(cv2.cvtColor(cv2.imread(str(a.fg), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA))

    rng = np.random.default_rng(7)
    comp = Comp(a, W, H, rng)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                            "-color_trc", "bt709", "-movflags", "+faststart", str(a.output)], stdin=subprocess.PIPE)
    nf = int(round(dur * fps))
    want = {int(round(t * fps)) for t in (a.qc or [])}
    qc, plate_stats, plate_noise, last_plate = [], None, None, None
    for i in range(nf):
        try:
            fg = next(fgs)
            plate = next(plates)
        except StopIteration:
            break
        last_plate = plate
        if plate_stats is None or not is_img:
            plate_stats, plate_noise = lab_stats(plate), noise_std(plate)
        img, al = comp.layer(fg, plate, plate_stats, plate_noise)
        out = comp.finish(img)
        enc.stdin.write(out.tobytes())
        if i in want:
            plain = plate.astype(np.float32)
            canvas = np.zeros((H, W, 4), np.uint8)
            src = fg if a.scale == 1 else cv2.resize(fg, (int(fg.shape[1] * a.scale), int(fg.shape[0] * a.scale)))
            hh, ww = min(src.shape[0], H - max(a.y, 0)), min(src.shape[1], W - max(a.x, 0))
            canvas[max(a.y, 0):max(a.y, 0) + hh, max(a.x, 0):max(a.x, 0) + ww] = src[:hh, :ww]
            pa = canvas[..., 3:4].astype(np.float32) / 255
            plain = canvas[..., :3] * pa + plain * (1 - pa)
            qc.append(np.hstack([plain.astype(np.uint8), out]))
    enc.stdin.close(); enc.wait()
    if qc:
        sheet = np.vstack([cv2.resize(q, (q.shape[1] * 700 // q.shape[0], 700)) for q in qc])
        cv2.imwrite(str(a.output.with_name(a.output.stem + "_qc.jpg")), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    print(f"wrote {a.output} ({nf} frames @ {fps:g}fps)" + (f" · plate grain σ={plate_noise:.2f}" if plate_noise else "")
          + (f" + {a.output.stem}_qc.jpg (left: plain paste · right: comp)" if qc else ""))


if __name__ == "__main__":
    main()
