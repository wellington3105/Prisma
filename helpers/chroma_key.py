"""Chroma key (green / blue screen) → alpha video, done the compositor's way.

A colour-DIFFERENCE keyer (the principle behind Keylight / Primatte-style
keyers), not ffmpeg's `chromakey` similarity test: the matte comes from how
much the screen channel exceeds the other two, normalised by the screen's own
difference. That keeps hair and motion-blurred edges semi-transparent instead
of chewing them into a hard cutout.

Pipeline per frame:
  1. key colour   auto (median of the frame border) or --color
  2. matte        a = 1 - clamp((d / d_key - clip_black) / (clip_white - clip_black))
                  d = S - max(o1, o2)  (S = screen channel)   — matte levels = clip_black/white
  3. garbage      --garbage person: MediaPipe person mask, dilated, kills rigs,
                  stands and screen edges; or --garbage x0,y0,x1,y1 (keep box)
  4. choke/feather  erode N px, then blur N px (edge softness)
  5. despill      S' = min(S, mean(o1,o2) * --spill-limit) on the foreground,
                  blended by --despill (removes green bounce on skin/hair/shirt)
Writes VP9-alpha .webm (default) or ProRes 4444 .mov, plus a QC sheet: the
matte in black/white (holes and grey noise show instantly) + comp on a checker.

Usage:
  python helpers/chroma_key.py greenscreen.mp4 -o subject.webm
  python helpers/chroma_key.py gs.mp4 -o s.webm --clip-black 0.2 --clip-white 0.8 --choke 1 --feather 1.5
  python helpers/chroma_key.py gs.mp4 -o s.mov --garbage person --qc 1.0 3.5 6.0
  python helpers/chroma_key.py --selftest person_fg.webm      # synthetic screen → key → matte error
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

HERE = Path(__file__).resolve().parent
SEG_MODEL = HERE.parent / "assets/models/selfie_multiclass_256x256.tflite"


def probe(p: Path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate,codec_name:stream_side_data=rotation",
                                   "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    w, h = s["width"], s["height"]
    if any(abs(int(x.get("rotation", 0))) in (90, 270) for x in s.get("side_data_list", [])):
        w, h = h, w
    return w, h, float(n) / float(d), s.get("codec_name", "")


def read(p: Path, w: int, h: int, alpha=False, vp9=False):
    cmd = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if vp9 else []) + [
        "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    c = 4 if alpha else 3
    while True:
        b = proc.stdout.read(w * h * c)
        if len(b) < w * h * c:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, c)


def writer(out: Path, w: int, h: int, fps: float):
    if out.suffix.lower() == ".mov":
        codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
    else:
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "18", "-row-mt", "1"]
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                             "-r", f"{fps}", "-i", "-"] + codec + [str(out)], stdin=subprocess.PIPE)


def border_color(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    bw, bh = max(4, w // 16), max(4, h // 14)
    px = np.concatenate([rgb[:bh].reshape(-1, 3), rgb[:, :bw].reshape(-1, 3), rgb[:, -bw:].reshape(-1, 3)])
    return np.median(px, axis=0)


class Keyer:
    def __init__(self, color, clip_black, clip_white, choke, feather, despill, spill_limit, garbage, fill_holes=0.005):
        self.fill_holes = fill_holes
        self.color = None if color is None else np.array(color, np.float32)
        self.cb, self.cw = clip_black, clip_white
        self.choke, self.feather = choke, feather
        self.despill, self.limit = despill, spill_limit
        self.garbage = garbage
        self.seg = None
        if garbage == "person":
            import mediapipe as mp
            from mediapipe.tasks.python import vision, BaseOptions
            if not SEG_MODEL.exists():
                raise SystemExit(f"--garbage person needs {SEG_MODEL} (MediaPipe selfie_multiclass_256x256.tflite)")
            self._mp = mp
            self.seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(SEG_MODEL)), running_mode=vision.RunningMode.VIDEO,
                output_confidence_masks=True))
        self.i = 0

    def __call__(self, rgb: np.ndarray, fps: float) -> np.ndarray:
        f = rgb.astype(np.float32)
        key = self.color if self.color is not None else border_color(rgb).astype(np.float32)
        s = int(np.argmax(key))                      # screen channel: 1 = green, 2 = blue
        o = [c for c in range(3) if c != s]
        d = f[..., s] - np.maximum(f[..., o[0]], f[..., o[1]])
        dkey = max(float(key[s] - max(key[o[0]], key[o[1]])), 1.0)
        a = 1.0 - np.clip((d / dkey - self.cb) / max(self.cw - self.cb, 1e-3), 0, 1)
        if self.seg is not None:
            r = self.seg.segment_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                                          data=np.ascontiguousarray(rgb)), int(self.i * 1000 / fps))
            person = (1 - r.confidence_masks[0].numpy_view()[..., 0]) > 0.3
            gate = cv2.dilate(person.astype(np.uint8), np.ones((61, 61), np.uint8))
            a *= cv2.GaussianBlur(gate.astype(np.float32), (0, 0), 12)
        elif isinstance(self.garbage, tuple):
            x0, y0, x1, y1 = self.garbage
            m = np.zeros_like(a); m[y0:y1, x0:x1] = 1
            a *= cv2.GaussianBlur(m, (0, 0), 8)
        if self.fill_holes > 0:
            # core matte: small holes fully enclosed by the subject (green glare in
            # glasses, a green logo) are not background — fill them
            solid = (a > 0.9).astype(np.uint8)  # semi-transparent glare streaks count as holes too
            n, lab, st, _ = cv2.connectedComponentsWithStats(1 - solid, 4)
            hw = a.shape[0] * a.shape[1]
            for j in range(1, n):
                x, y, w, h, area = st[j]
                touches = x == 0 or y == 0 or x + w >= a.shape[1] or y + h >= a.shape[0]
                if not touches and area <= self.fill_holes * hw:
                    a[lab == j] = 1.0
        if self.choke > 0:
            k = int(self.choke) * 2 + 1
            a = cv2.erode(a, np.ones((k, k), np.uint8))
        if self.feather > 0:
            a = cv2.GaussianBlur(a, (0, 0), self.feather)
        if self.despill > 0:
            lim = (f[..., o[0]] + f[..., o[1]]) / 2 * self.limit
            fixed = np.minimum(f[..., s], lim)
            f[..., s] = f[..., s] + (fixed - f[..., s]) * self.despill
        self.i += 1
        out = np.dstack([np.clip(f, 0, 255), a * 255]).astype(np.uint8)
        return out


def qc_sheet(frames: list[np.ndarray], out: Path) -> None:
    tiles = []
    for rgba in frames:
        a = rgba[..., 3:4].astype(np.float32) / 255
        h, w = a.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        checker = (((xx // 32) + (yy // 32)) % 2 * 60 + 100).astype(np.float32)[..., None].repeat(3, -1)
        comp = rgba[..., :3] * a + checker * (1 - a)
        matte = (a * 255).repeat(3, -1)
        tile = np.hstack([matte, comp]).astype(np.uint8)
        s = 640 / tile.shape[0]
        tiles.append(cv2.resize(tile, (int(tile.shape[1] * s), 640)))
    cv2.imwrite(str(out), cv2.cvtColor(np.hstack(tiles), cv2.COLOR_RGB2BGR))


def selftest(fg_path: Path) -> None:
    """Composite an alpha video over a realistic green screen (uneven light,
    noise, green spill on the edges), key it back, and report the matte error."""
    w, h, fps, codec = probe(fg_path)
    out_dir = fg_path.parent
    gs = out_dir / "_selftest_greenscreen.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", f"{fps}", "-i", "-", "-frames:v", "60", "-c:v", "libx264", "-crf", "16",
                            "-pix_fmt", "yuv420p", str(gs)], stdin=subprocess.PIPE)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 0.80 + 0.25 * np.exp(-(((xx - w * 0.4) / (w * 0.7)) ** 2 + ((yy - h * 0.3) / (h * 0.8)) ** 2))
    screen = np.dstack([40 * light, 175 * light, 70 * light])
    truth = []
    rng = np.random.default_rng(1)
    for i, rgba in enumerate(read(fg_path, w, h, alpha=True, vp9=codec == "vp9")):
        if i >= 60:
            break
        a = rgba[..., 3:4].astype(np.float32) / 255
        fg = rgba[..., :3].astype(np.float32)
        edge = cv2.GaussianBlur(a[..., 0], (0, 0), 6)[..., None] * (1 - a) + a * (1 - cv2.erode(a[..., 0], np.ones((15, 15), np.uint8))[..., None])
        fg = fg + np.array([0, 38, 0]) * edge                       # green spill on the rim
        img = fg * a + screen * (1 - a) + rng.normal(0, 3.0, (h, w, 3))
        enc.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
        truth.append(rgba[..., 3].copy())
    enc.stdin.close(); enc.wait()
    k = Keyer(None, 0.15, 0.85, 0, 0.8, 1.0, 1.0, None)
    errs, edge_errs, spill_before, spill_after, sample = [], [], [], [], []
    for i, rgb in enumerate(read(gs, w, h)):
        out = k(rgb, fps)
        a_hat = out[..., 3].astype(np.float32) / 255
        a_true = truth[i].astype(np.float32) / 255
        band = (a_true > 0.02) & (a_true < 0.98)
        errs.append(np.abs(a_hat - a_true).mean())
        edge_errs.append(np.abs(a_hat - a_true)[band].mean() if band.any() else 0)
        fgm = (a_true > 0.9) & (cv2.erode((a_true > 0.9).astype(np.uint8), np.ones((15, 15), np.uint8)) == 0)  # rim
        spill_before.append(float((rgb[..., 1].astype(float) - rgb[..., [0, 2]].astype(float).mean(-1))[fgm].mean()))
        spill_after.append(float((out[..., 1].astype(float) - out[..., [0, 2]].astype(float).mean(-1))[fgm].mean()))
        if i in (5, 30, 55):
            sample.append(out)
    qc_sheet(sample, out_dir / "_selftest_qc.png")
    print(f"selftest: matte MAE {np.mean(errs) * 100:.2f}% · edge-band MAE {np.mean(edge_errs) * 100:.1f}% · "
          f"green excess on the subject's rim {np.mean(spill_before):.1f} → {np.mean(spill_after):.1f} (despill)")
    print(f"QC: {out_dir / '_selftest_qc.png'}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Colour-difference chroma keyer → alpha video")
    ap.add_argument("video", type=Path, nargs="?")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--color", help="key colour R,G,B (default: auto from the frame border)")
    ap.add_argument("--clip-black", type=float, default=0.15, help="matte level: below → fully opaque subject")
    ap.add_argument("--clip-white", type=float, default=0.85, help="matte level: above → fully transparent screen")
    ap.add_argument("--choke", type=float, default=0, help="erode the matte N px")
    ap.add_argument("--feather", type=float, default=0.8, help="blur the matte N px")
    ap.add_argument("--despill", type=float, default=1.0, help="0..1 strength")
    ap.add_argument("--spill-limit", type=float, default=1.0, help="screen channel capped at mean(others)×this")
    ap.add_argument("--garbage", default=None, help="'person' or x0,y0,x1,y1 keep-box")
    ap.add_argument("--fill-holes", type=float, default=0.005,
                    help="fill enclosed holes up to this fraction of the frame (0 = off)")
    ap.add_argument("--qc", type=float, nargs="*", default=None, help="times (s) for the QC sheet")
    ap.add_argument("--selftest", type=Path, help="alpha video to build a synthetic green screen from")
    a = ap.parse_args()
    if a.selftest:
        selftest(a.selftest); return
    if not a.video or not a.output:
        ap.error("video and -o are required")
    w, h, fps, _ = probe(a.video)
    garbage = a.garbage if a.garbage in (None, "person") else tuple(int(v) for v in a.garbage.split(","))
    color = [float(v) for v in a.color.split(",")] if a.color else None
    k = Keyer(color, a.clip_black, a.clip_white, a.choke, a.feather, a.despill, a.spill_limit, garbage, a.fill_holes)
    enc = writer(a.output, w, h, fps)
    want = {int(round(t * fps)) for t in (a.qc or [])}
    qc = []
    for i, rgb in enumerate(read(a.video, w, h)):
        out = k(rgb, fps)
        enc.stdin.write(out.tobytes())
        if i in want:
            qc.append(out)
    enc.stdin.close(); enc.wait()
    if qc:
        qc_sheet(qc, a.output.with_name(a.output.stem + "_qc.png"))
    print(f"wrote {a.output} ({w}x{h} @ {fps:g}fps)" + (f" + QC {a.output.stem}_qc.png" if qc else ""))


if __name__ == "__main__":
    main()
