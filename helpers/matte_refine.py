"""Refine an AI person matte (RVM / person_matte.py) when there was NO green screen.

RVM keeps whatever touches the person as foreground — the chair back, a
headrest, a mic stand. Two passes, both measured on a real shoot (BMW Série 3,
2026-10-06, office chair behind a seated talker):

 1. person gate — MediaPipe selfie_multiclass (Google, local .tflite):
    alpha *= dilate(1 - P(background) > 0.6), smoothed over 3 frames. Removes
    most furniture. Its 256 px mask bleeds onto objects right beside the head
    when the head turns (the chair got labelled "face"/"clothes").
 2. --texture-kill (default on) — inside a 90 px band along the silhouette
    edge, remove big blobs of fine-band texture energy on a neutral grey
    (mesh fabric: energy 4.7-6.8 vs beard <= 3.0, shirt 1.1, skin 1.6). The
    band protects the grey chin beard and the glasses, which share the texture
    but sit deep inside the person. Blobs < 4000 px are ignored (specular specks).

RVM's own fine edge (hair, beard) is kept: the gate only multiplies it down.

Usage:
  python helpers/person_matte.py src.mp4 -o fg.webm --model resnet50
  python helpers/matte_refine.py --fg fg.webm --src src.mp4 -o fg_clean.webm [--no-texture-kill]
  python helpers/matte_refine.py --fg fg.webm --src src.mp4 -o x.webm --test 2.0 8.5 20.5   # PNG on red
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
from collections import deque
from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parent.parent / "assets/models/selfie_multiclass_256x256.tflite"


def probe(p: Path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate", "-of", "json", str(p)],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return s["width"], s["height"], float(n) / float(d)


def read(p: Path, w: int, h: int, alpha: bool):
    cmd = ["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if alpha and p.suffix == ".webm" else []) + [
        "-i", str(p), "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    c = 4 if alpha else 3
    while True:
        b = proc.stdout.read(w * h * c)
        if len(b) < w * h * c:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, c)


def refine(fg: Path, src: Path, texture_kill: bool, fps: float, w: int, h: int):
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    if not MODEL.exists():
        raise SystemExit(f"missing {MODEL} — MediaPipe selfie_multiclass_256x256.tflite (Google, ~16 MB)")
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)), running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True))
    hist = deque(maxlen=3)
    k = np.ones((11, 11), np.uint8)
    for i, (rgb, rgba) in enumerate(zip(read(src, w, h, False), read(fg, w, h, True))):
        r = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)),
                                  int(i * 1000 / fps))
        hist.append(1.0 - r.confidence_masks[0].numpy_view()[..., 0])
        gate = (np.mean(hist, axis=0) > 0.6).astype(np.uint8) * 255
        gate = cv2.GaussianBlur(cv2.dilate(gate, k), (0, 0), 4).astype(np.float32) / 255
        if texture_kill:
            L = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
            fine = cv2.GaussianBlur(np.abs(cv2.GaussianBlur(L, (0, 0), 0.8) - cv2.GaussianBlur(L, (0, 0), 1.8)), (0, 0), 8)
            f = rgb.astype(np.float32)
            sat = cv2.GaussianBlur((f.max(-1) - f.min(-1)) / np.maximum(f.max(-1), 1), (0, 0), 8)
            dist = cv2.distanceTransform((gate > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
            blob = ((fine > 4.0) & (sat < 0.22) & (dist < 90)).astype(np.uint8) * 255
            blob = cv2.morphologyEx(blob, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
            n, lab, st, _ = cv2.connectedComponentsWithStats(blob, 8)
            blob = np.isin(lab, [j for j in range(1, n) if st[j, cv2.CC_STAT_AREA] > 4000]).astype(np.uint8) * 255
            blob = cv2.dilate(blob, np.ones((7, 7), np.uint8))
            gate *= 1 - cv2.GaussianBlur(blob, (0, 0), 3).astype(np.float32) / 255
        out = rgba.copy()
        out[..., 3] = (rgba[..., 3].astype(np.float32) * gate).astype(np.uint8)
        yield i, out


def main() -> None:
    ap = argparse.ArgumentParser(description="Refine an AI person matte (no green screen)")
    ap.add_argument("--fg", type=Path, required=True, help="alpha video from person_matte.py")
    ap.add_argument("--src", type=Path, required=True, help="the original video the matte came from")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--no-texture-kill", action="store_true")
    ap.add_argument("--test", type=float, nargs="*", help="only write a PNG check at these times (s)")
    a = ap.parse_args()
    w, h, fps = probe(a.fg)
    gen = refine(a.fg, a.src, not a.no_texture_kill, fps, w, h)
    if a.test:
        want = {int(round(t * fps)) for t in a.test}
        tiles = []
        for i, c in gen:
            if i in want:
                al = c[..., 3:4].astype(np.float32) / 255
                tiles.append(cv2.resize((c[..., :3] * al + np.array([200, 20, 30]) * (1 - al)).astype(np.uint8), (360, 640)))
            if i >= max(want):
                break
        out = a.output.with_suffix(".test.png")
        cv2.imwrite(str(out), cv2.cvtColor(np.hstack(tiles), cv2.COLOR_RGB2BGR))
        print(f"test sheet: {out}"); return
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                            "-r", f"{fps}", "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                            "-b:v", "0", "-crf", "18", "-row-mt", "1", str(a.output)], stdin=subprocess.PIPE)
    n = 0
    for i, c in gen:
        enc.stdin.write(c.tobytes()); n = i + 1
    enc.stdin.close(); enc.wait()
    print(f"wrote {a.output} ({n} frames)")


if __name__ == "__main__":
    main()
