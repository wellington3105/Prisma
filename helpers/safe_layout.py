#!/usr/bin/env python3
"""Rosto livre — place overlays where they never cover the speaker's face.

    safe_layout.py <edit> [--platform instagram|tiktok|shorts|youtube|all]
                          [--report] [--apply] [--redetect] [--fps 5]

`<edit>` is the edit directory (it holds remotion/public/edit-data.json and
cut.mp4); a directory that itself holds edit-data.json + cut.mp4 also works.

What it does
  1. Faces over time from cut.mp4 -> remotion/public/faces.json (>= 5 fps, box
     grown to cover hair and chin). Detector chain: YuNet when its model file is
     present (helpers/models/face_detection_yunet_2023mar.onnx; fetch it yourself
     with --fetch-model, MIT), else OpenCV Haar frontal + profile (+ mirrored
     profile) on a 960px copy; gaps are bridged by holding/interpolating the box.
  2. For every overlay window in edit-data.json it computes the rendered box (same
     sizing maths as the components, ratios of the frame, conservative text
     metrics), maps the face through the template's dynamic camera (zoom + track)
     to SCREEN pixels, and tests the box against the face over the WHOLE window.
  3. A colliding overlay goes to the first candidate that fits inside the platform
     safe area, clear of the face and of the other overlays/caption band alive at
     the same time:  below the chin -> above the head -> beside the face -> the
     same again shrunk to 90% / 80%.  If no single position works through the whole
     window, a highlight card is split in two windows (face crossed the frame).
  --report prints one line per overlay; --apply writes edit-data.json (backup
  edit-data.before_safe_layout.<ts>.json) and tags moved items `"autoPlaced": true`.
  An item with `"lockPos": true` is never moved (still reported).

Overlays covered: highlights.items (prism/pill/keynote/studio/chrome/hud), hook,
callouts, captions block of stacked/scatter, splitInserts framing (landscape),
and — report only, they have no position keys — lowerThirds / chapters.

Ported from kurbaitaev/ghost-editor (scripts/lib/safezone.mjs, scripts/face_track.py):
  MIT License  Copyright (c) 2026 kurbaitaev
  Permission is hereby granted, free of charge, to any person obtaining a copy of
  this software and associated documentation files (the "Software"), to deal in the
  Software without restriction, including without limitation the rights to use,
  copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
  Software ... The above copyright notice and this permission notice shall be
  included in all copies or substantial portions of the Software.
  (the placement order below-chin / above-head / shrink, the platform UI bands and
  the head-box growth factors come from there; the overlay model, camera mapping,
  detector chain and card splitting are Prisma's.)
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
import os
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
YUNET = HERE / "models" / "face_detection_yunet_2023mar.onnx"
# The github.com/.../raw URL serves a 131-byte Git LFS POINTER, not the model
# (checked 2026-11-05) — the media.githubusercontent URL serves the real file.
# Pinned by size + sha256 from that pointer, so a pointer/corrupt file is refused.
YUNET_URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_SIZE = 232589
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

# Platform UI chrome at 1080x1920 (px covered by the app) — from ghost-editor.
PLATFORMS_916 = {
    "instagram": dict(top=220, bottom=420, right=130),
    "tiktok": dict(top=160, bottom=480, right=150),
    "shorts": dict(top=140, bottom=380, right=140),
    "youtube": dict(top=140, bottom=380, right=140),
    "all": dict(top=220, bottom=480, right=150),
}
SAFE_169 = 0.05  # 16:9 title-safe margin (also what Instagram's letterbox leaves usable)
GAP = 0.02       # clearance around the face, fraction of frame height
STEP = 0.1       # seconds between collision samples
SCALES = (1.0, 0.9, 0.8)


# ------------------------------------------------------------------ faces ---
def detect_faces(video: Path, target_fps: float = 5.0, log=print) -> dict:
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps / target_fps))
    DW = 960 if W >= H else 540
    sc = DW / W
    DH = int(H * sc)

    yn = None
    if YUNET.exists():
        try:
            yn = cv2.FaceDetectorYN.create(str(YUNET), "", (DW, DH), 0.6)
        except Exception as e:  # pragma: no cover
            log(f"  YuNet indisponível ({e}) — Haar")
    # Haar is optional: OpenCV 5 builds may ship without CascadeClassifier /
    # cv2.data (seen 2026-11-06 when three opencv wheels shared the venv). With
    # YuNet present the helper still works; with neither, stop with the fix.
    front, prof = [], None
    try:
        hd = cv2.data.haarcascades
        front = [cv2.CascadeClassifier(hd + "haarcascade_frontalface_default.xml"),
                 cv2.CascadeClassifier(hd + "haarcascade_frontalface_alt2.xml")]
        prof = cv2.CascadeClassifier(hd + "haarcascade_profileface.xml")
        if any(c.empty() for c in front) or prof.empty():
            front, prof = [], None
    except AttributeError:
        front, prof = [], None
    if not front and yn is None:
        raise SystemExit("nenhum detector de rosto disponível: este OpenCV não tem Haar e o YuNet "
                         "não está baixado — rode `safe_layout.py --fetch-model` (YuNet, MIT, ~227 KB)")
    if not front:
        log("  Haar indisponível neste OpenCV — só YuNet")

    def grow(x, y, w, h):
        # ghost-editor's growth: hair above, chin below, ears at the sides
        top, bottom = y - 0.40 * h, y + h * 1.15
        left, right = x - 0.12 * w, x + w * 1.12
        return [max(0.0, top), min(float(DH), bottom), max(0.0, left), min(float(DW), right)]

    samples, found, by = [], 0, {"yunet": 0, "front": 0, "profile": 0}
    f = 0
    while f < n:
        ok = cap.grab()
        if not ok:
            break
        if f % step == 0:
            ok, fr = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(fr, (DW, DH))
            t = round(f / fps, 3)
            box = None
            how = None
            if yn is not None:
                _, fs = yn.detect(small)
                if fs is not None and len(fs):
                    b = max(fs, key=lambda r: r[2] * r[3])
                    x, y, w, h = b[:4]
                    box, how = grow(x, y, w, h), "yunet"
            if box is None and front:
                g = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
                r = ()
                for c in front:
                    r = c.detectMultiScale(g, 1.1, 3, minSize=(40, 40), maxSize=(int(DW * 0.28),) * 2)
                    if len(r):
                        break
                if len(r):
                    x, y, w, h = max(r, key=lambda q: q[2] * q[3])
                    box, how = grow(x, y, w, h), "front"
                else:
                    r = prof.detectMultiScale(g, 1.1, 3, minSize=(40, 40), maxSize=(int(DW * 0.28),) * 2)
                    flipped = False
                    if not len(r):
                        r = prof.detectMultiScale(cv2.flip(g, 1), 1.1, 3, minSize=(40, 40), maxSize=(int(DW * 0.28),) * 2)
                        flipped = True
                    if len(r):
                        x, y, w, h = max(r, key=lambda q: q[2] * q[3])
                        if flipped:
                            x = DW - x - w
                        box, how = grow(x, y, w, h), "profile"
            if box is None:
                samples.append([t, None])
            else:
                top, bottom, left, right = [round(v / sc) for v in box]
                eyes = round(top + (bottom - top) * 0.40)
                mouth = round(top + (bottom - top) * 0.80)
                samples.append([t, top, bottom, left, right, eyes, mouth])
                found += 1
                by[{"yunet": "yunet", "front": "front", "profile": "profile"}[how]] += 1
        f += 1
    cap.release()
    return {"fps": target_fps, "w": W, "h": H, "detected": found, "total": len(samples), "by": by,
            "detector": "yunet+haar" if yn is not None else "haar", "samples": samples}


class Faces:
    """Face box at any time, held/interpolated across short misses."""

    def __init__(self, data: dict):
        self.w, self.h = data["w"], data["h"]
        raw = [s for s in data["samples"] if s[1] is not None]
        self.pts = self._clean(raw)
        self.ts = [s[0] for s in self.pts]
        self.rate = len(self.pts) / max(1, data["total"])  # after outlier removal

    @staticmethod
    def _clean(pts, win: float = 1.5):
        """Drop detector outliers (Haar fires on hair, lamps, wheels): a box must agree
        with the median of its neighbours within +-win s in position and size."""
        import statistics as st
        keep = []
        for p in pts:
            nb = [q for q in pts if abs(q[0] - p[0]) <= win]
            if len(nb) < 2:
                continue
            cx = [(q[3] + q[4]) / 2 for q in nb]; cy = [(q[1] + q[2]) / 2 for q in nb]; wd = [q[4] - q[3] for q in nb]
            mw = st.median(wd)
            ok = (abs((p[3] + p[4]) / 2 - st.median(cx)) <= 1.7 * mw and abs((p[1] + p[2]) / 2 - st.median(cy)) <= 1.7 * mw
                  and 0.5 * mw <= (p[4] - p[3]) <= 1.8 * mw)
            if ok:
                keep.append(p)
        return keep

    def at(self, t: float):
        if not self.pts:
            return None
        import bisect
        i = bisect.bisect_left(self.ts, t)
        prev = self.pts[i - 1] if i > 0 else None
        nxt = self.pts[i] if i < len(self.pts) else None
        if prev and nxt and nxt[0] - prev[0] <= 3.0:
            k = (t - prev[0]) / max(1e-6, nxt[0] - prev[0])
            return [prev[j] + (nxt[j] - prev[j]) * k for j in range(1, 5)]
        best = min((p for p in (prev, nxt) if p), key=lambda p: abs(p[0] - t))
        return list(best[1:5]) if abs(best[0] - t) <= 1.0 else None  # top,bottom,left,right (source px)


# ----------------------------------------------------------- frame / camera --
class Frame:
    def __init__(self, ed: dict, pub: Path, faces: Faces, platform: str):
        self.W, self.H = int(ed["width"]), int(ed["height"])
        self.fps = float(ed.get("fps") or 30)
        self.portrait = self.H > self.W
        self.faces = faces
        self.cam = ed.get("camera") or {}
        # windows where the speaker is NOT on screen: full-frame b-roll (no PiP) and
        # split screens (the split re-frames him on its own column)
        self.cover = [(float(b["start"]), float(b["start"]) + float(b.get("dur", 4))) for b in (ed.get("broll") or []) if not b.get("pip")]
        self.cover += [(float(b["start"]), float(b["end"])) for b in (ed.get("splitInserts") or [])]
        self.segs, self.track = [], []
        try:
            self.segs = json.loads((pub / "segments.json").read_text(encoding="utf-8")).get("segments", [])
        except Exception:
            pass
        try:
            self.track = json.loads((pub / "track.json").read_text(encoding="utf-8")).get("points", [])
        except Exception:
            pass
        if self.portrait:
            P = PLATFORMS_916.get(platform, PLATFORMS_916["all"])
            k = self.W / 1080
            self.safe = (0.0, P["top"] * k, self.W - P["right"] * k * 0.0, self.H - P["bottom"] * k)
            self.right_ui = P["right"] * k  # like/comment column: only the lower half
        else:
            m = SAFE_169
            self.safe = (self.W * m, self.H * m, self.W * (1 - m), self.H * (1 - m))
            self.right_ui = 0.0

    def screen_face(self, t: float):
        if any(a <= t < b for a, b in self.cover):
            return None
        b = self.faces.at(t)
        if not b:
            return None
        sx, sy = self.W / self.faces.w, self.H / self.faces.h
        top, bottom, left, right = b[0] * sy, b[1] * sy, b[2] * sx, b[3] * sx
        if self.cam.get("enabled"):
            fr = round(t * self.fps)
            S, tx, ty = self._cam(fr)
            top, bottom, left, right = ty + S * top, ty + S * bottom, tx + S * left, tx + S * right
        return (left, top, right, bottom)

    def _cam(self, f: int):  # mirrors Camera.tsx / DynamicVideo
        c, W, H = self.cam, self.W, self.H
        zooms = c.get("zooms") or [1.08]
        idx = 0
        for i, s in enumerate(self.segs):
            if f - 1 >= round(s["start"] * self.fps):
                idx = i
        seg = self.segs[idx] if self.segs else None
        seg_from = round(seg["start"] * self.fps) + 1 if seg else 0
        seg_len = max(1, round(seg["dur"] * self.fps)) if seg else 1
        push = (c.get("pushIn") or 0) * max(0.0, min(1.0, (f - seg_from) / seg_len))
        S = (zooms[idx % len(zooms)] or 1) + push
        pts = self.track or [[0.5, 0.4]]
        p = pts[min(f, len(pts) - 1)]
        cx = p[0] / W if p[0] > 1 else p[0]
        cy = p[1] / H if p[1] > 1 else p[1]
        tx = max(W - W * S, min(0.0, (c.get("targetX", 0.5)) * W - cx * W * S))
        ty = max(H - H * S, min(0.0, (c.get("targetY", 0.4)) * H - cy * H * S))
        return S, tx, ty

    def covered(self, t0: float, t1: float) -> bool:
        """True when the speaker is off screen for the WHOLE window (full-frame b-roll / split)."""
        t = t0
        while t <= t1 + 1e-6:
            if not any(a <= t < b for a, b in self.cover):
                return False
            t += STEP
        return True

    def span(self, t0: float, t1: float):
        """Union of the on-screen face over the window, or None when never seen."""
        u, seen, t = [1e9, 1e9, -1e9, -1e9], False, t0
        while t <= t1 + 1e-6:
            r = self.screen_face(t)
            if r:
                seen = True
                u = [min(u[0], r[0]), min(u[1], r[1]), max(u[2], r[2]), max(u[3], r[3])]
            t += STEP
        return tuple(u) if seen else None


# ------------------------------------------------------------ overlay model --
def est_w(text: str, em: float, factor: float = 0.58) -> float:
    return len(text) * em * factor


def hl_box(fr: Frame, ed: dict, it: dict, variant: str, scale: float):
    """Rendered size (w, h) of a highlights card, mirroring GlassCard.tsx /
    GlassCardVariants.tsx (size from frame height in 16:9, from width in 9:16)."""
    W, H = fr.W, fr.H
    land = not fr.portrait
    size = (H * 0.056 if land else W * 0.052) * scale
    avail = (0.40 if land else 0.82) * W
    text, label = str(it.get("text", "")), it.get("label")
    n = max(1, len(text))
    if variant == "pill":
        sz = (H * 0.05 if land else W * 0.046) * scale / max(1, n / 12)
        w = est_w(text, sz * 1.15, 0.6) + sz * 2.2
        h = sz * 1.15 * 1.08 + sz * 1.04 + (sz * 0.58 + sz * 0.18 if label else 0)
        return min(w, avail), h
    if variant == "keynote":
        px = size * 1.6
        px = min(px, px * (avail - size * 2.1) / max(1, est_w(text, px, 0.5)))
        w = est_w(text, px, 0.5) + size * 2.1
        h = px * 1.02 + size * 1.5 + (px * 0.32 * 1.45 if label else 0)
        return min(w, avail), h
    if variant == "studio":
        px = size * 1.45
        px = min(px, px * (avail - size * 1.6) / max(1, est_w(text, px, 0.6)))
        head = max(px * 0.29, 22 * H / 1080)
        w = max(est_w(text, px, 0.6), est_w((label or "READOUT") + " · 01", head, 0.72), size * 5) + size * 1.75
        h = head * 1.8 + px * 1.05 + size * 0.72 + size * 1.05
        return min(w, avail), h
    if variant == "hud":
        px = size * 1.25
        px = min(px, px * (avail - size * 2.2) / max(1, est_w(text, px, 0.6)))
        head = max(px * 0.29, 22 * H / 1080)
        w = max(est_w(text, px, 0.6), size * 5) + size * 1.9
        h = head * 1.8 + px * 1.05 + size * 1.4
        return min(w, avail), h
    if variant == "chrome":
        px = size * 1.7
        w = min(round(avail), est_w(text, px, 0.64) * min(1, 0.9 * avail / max(1, est_w(text, px, 0.64))))
        return w, round(px * 2.1) * 0.62  # the glyphs, not the transparent canvas
    # prism (default)
    sz = size / max(1, n / 16)
    w = est_w(text, sz * 1.22, 0.62) + sz * 1.9
    h = sz * 1.22 * 1.04 + sz * 1.08 + (sz * 0.46 * 1.0 + sz * 0.16 if label else 0)
    return min(w, 0.40 * W if land else 0.82 * W), h * 1.12  # tilt/perspective margin


HOOK_CAP = {"outline": (0.095, 1.02, 0.07), "card": (0.08, 1.06, 0.06), "realce": (0.085, 1.04, 0.07), "misto": (0.10, 0.98, 0.07)}
HOOK_CAP_916 = {"outline": (92, 1.02, 330), "card": (82, 1.06, 120), "realce": (86, 1.04, 300), "misto": (98, 0.98, 300)}


def hook_box(fr: Frame, hk: dict):
    W, H = fr.W, fr.H
    st = hk.get("style") or "outline"
    raw = str(hk.get("text") or " ".join(hk.get("lines") or [])).strip()
    words = raw.split()
    if len(words) < 2:
        words = words + [""]
    # balanced two lines by character count
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    widest = max(len(" ".join(words[:best])), len(" ".join(words[best:])), 1)
    if st == "card":
        widest = widest
    if fr.portrait:
        cap, lh, top = HOOK_CAP_916.get(st, HOOK_CAP_916["outline"])
        cap = (hk.get("fontSizePx") or hk.get("maxFontPx") or cap) * W / 1080
        safe = (hk.get("safeWidth") or 900) * W / 1080
        size = min(cap, safe / (widest * 0.6))
        w = min(safe, widest * 0.6 * size) + (60 * W / 1080 if st != "card" else 92 * W / 1080)
        h = 2 * size * lh + (56 * W / 1080 if st == "card" else 0)
        top = (hk.get("paddingTop") if hk.get("paddingTop") is not None else top) * W / 1080
        return w, h, top
    cap, lh, top = HOOK_CAP.get(st, HOOK_CAP["outline"])
    pad = 0.92 if st == "card" else 0.84 if st == "realce" else 1.0
    safe = (hk.get("safeWidth") * W / 1920 if hk.get("safeWidth") else W * 0.5) * pad
    cappx = (hk.get("fontSizePx") or hk.get("maxFontPx") or 0) * H / 1080 or cap * H
    size = min(cappx, safe / (widest * 0.6))
    w = min(safe, widest * 0.6 * size) + (size * 0.8 if st == "card" else size * 0.6 if st == "realce" else 0)
    h = 2 * size * lh + (H / 1080 * 48 if st == "card" else size * 0.4 if st == "realce" else 0)
    top = (hk.get("paddingTop") * H / 1080) if hk.get("paddingTop") is not None else top * H
    return w, h, top


def inter(a, b, m=0.0):
    return a[0] < b[2] + m and a[2] > b[0] - m and a[1] < b[3] + m and a[3] > b[1] - m


class Ov:
    """One overlay window. box = (cx, cy, w, h) in screen px."""

    def __init__(self, oid, kind, t0, t1, w, h, cx, cy, locked=False, movable=True, ref=None):
        self.id, self.kind, self.t0, self.t1 = oid, kind, t0, t1
        self.w, self.h, self.cx, self.cy = w, h, cx, cy
        self.locked, self.movable, self.ref = locked, movable, ref
        self.scale = 1.0
        self.scalable = kind.startswith("card") or kind == "hook"  # components that read `scale`
        self.top_policy = kind in ("hook", "callout")  # titles live in their band: sideways + shrink only
        self.axes = "xy"
        self.xs = None  # discrete x choices (hook side / caption side): [(name, cx)]

    def rect(self, cx=None, cy=None, s=None):
        s = self.scale if s is None else s
        cx = self.cx if cx is None else cx
        cy = self.cy if cy is None else cy
        w, h = self.w * s, self.h * s
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def build_overlays(ed: dict, fr: Frame):
    W, H = fr.W, fr.H
    land = not fr.portrait
    out, fixed = [], []
    hl = ed.get("highlights") or {}
    if hl.get("enabled"):
        off = float(hl.get("offsetS", 0.8))
        variant = hl.get("variant") or "prism"
        for i, it in enumerate(hl.get("items") or []):
            t0 = float(it["at"]) + off
            t1 = t0 + float(it.get("dur", 3.2))
            sc = float(it.get("scale", 1.0))
            w, h = hl_box(fr, ed, it, variant, 1.0)  # base box; the item's scale is applied by Ov.rect
            cx = float(it.get("x", 0.26 if land else 0.5)) * W
            cy = float(it.get("y", 0.32 if land else 0.3)) * H
            o = Ov(it.get("id") or f"hl[{i}]", f"card:{variant}", t0, t1, w, h, cx, cy, bool(it.get("lockPos")), ref=("hl", i))
            o.scale = sc
            out.append(o)
    hk = ed.get("hook") or {}
    if hk.get("enabled"):
        w, h, top = hook_box(fr, hk)
        endt = float(hk.get("endSec", 4))
        if land:
            side = hk.get("side", "left")
            m = W * 0.04
            xs = [("left", m + w / 2), ("center", W / 2), ("right", W - m - w / 2)]
            cx = dict(xs)[side if side in dict(xs) else "left"]
            o = Ov("hook", "hook", 0.0, endt, w, h, cx, top + h / 2, bool(hk.get("lockPos")), ref=("hook", 0))
            o.xs = xs
            o.axes = "y"
        else:
            o = Ov("hook", "hook", 0.0, endt, w, h, W / 2, top + h / 2, bool(hk.get("lockPos")), ref=("hook", 0))
            o.axes = "y"
        o.scale = float(hk.get("scale", 1.0))
        out.append(o)
    for i, c in enumerate(ed.get("callouts") or []):
        t = float(c["start"])
        txt = str(c.get("text", ""))
        w, h = est_w(txt, 44 * H / 1080, 0.6) + 44 * H / 1080, 44 * H / 1080 * 1.2 + 20
        out.append(Ov(c.get("id") or f"callout[{i}]", "callout", t, t + float(c.get("dur", 3)), w, h,
                      float(c.get("x", 0.5)) * W, float(c.get("y", 0.3)) * H, bool(c.get("lockPos")), ref=("callouts", i)))
    cap = ed.get("captions") or {}
    style = cap.get("style")
    dur = float(ed.get("durationSec") or 0)
    if cap.get("enabled") and style in ("stacked", "scatter") and dur:
        if land:
            wfrac, hfrac = (0.36, 0.45) if style == "stacked" else (0.34, 0.38)
            xs = [("left", W * 0.22), ("right", W * 0.78), ("center", W * 0.5)]
            side = cap.get("side", "left")
            cx = dict(xs).get(side, W * 0.22)
            cy = H * (0.5 + (cap.get("stackedOffsetY", 0.04) if style == "stacked" else cap.get("scatterOffsetY", 0.5) - 0.5))
            o = Ov("captions-block", f"captions:{style}", 0.0, dur, W * wfrac, H * hfrac, cx, cy, bool(cap.get("lockPos")), ref=("captions", 0))
            o.xs = xs
            o.axes = ""
            out.append(o)
        else:
            if style == "stacked":
                cy = H * (0.5 + cap.get("stackedOffsetY", 0.156))
                o = Ov("captions-block", "captions:stacked", 0.0, dur, (W - 180) * 0.9, H * 0.2, W / 2, cy, bool(cap.get("lockPos")), ref=("captions", 0))
            else:
                cy = H * cap.get("scatterOffsetY", 0.72)
                o = Ov("captions-block", "captions:scatter", 0.0, dur, cap.get("scatterSafeWidth", 820) * W / 1080, H * 0.2, W / 2, cy, bool(cap.get("lockPos")), ref=("captions", 0))
            o.axes = "y"
            out.append(o)
    # FIXED overlays (no position keys): obstacles for the others, warned if on the face
    mg = 96 * H / 1080
    for i, lt in enumerate(ed.get("lowerThirds") or []):
        t = float(lt["start"])
        name, title = str(lt.get("name", "")), str(lt.get("title") or "")
        w = 24 * H / 1080 + max(est_w(name, 40 * H / 1080, 0.62), est_w(title, 24 * H / 1080, 0.55)) + 44 * H / 1080
        h = (40 * 1.05 + (28 if title else 0) + 28) * H / 1080
        fixed.append(Ov(f"lowerThird[{i}]", "lowerThird", t, t + float(lt.get("dur", 4)), w, h, mg + w / 2, H - mg - h / 2, True, False))
    for i, ch in enumerate(ed.get("chapters") or []):
        t = float(ch["start"])
        w = est_w(str(ch.get("title", "")), 76 * H / 1080, 0.6)
        h = 110 * H / 1080
        fixed.append(Ov(f"chapter[{i}]", "chapter", t, t + float(ch.get("dur", 2.4)), w, h, mg + w / 2, H - mg - 40 * H / 1080 - h / 2, True, False))
    # burned-caption band (karaoke/simples/serifada/classica): an obstacle, never moved here
    if cap.get("enabled") and style not in ("stacked", "scatter", None) and dur:
        if land:
            band = Ov("caption-band", "band", 0.0, dur, W * 0.72, H * 0.14, W / 2, H * 0.84, True, False)
        else:
            pb = (cap.get("paddingBottom") or 430) * W / 1080
            fs = (cap.get("fontSize") or 76) * W / 1080
            band = Ov("caption-band", "band", 0.0, dur, W * 0.86, fs * 1.6, W / 2, H - pb - fs * 0.8, True, False)
        fixed.append(band)
    return out, fixed


# -------------------------------------------------------------- placement ---
def candidates(fr: Frame, o: Ov, F, s: float):
    """(name, cx, cy) in the module's preference order for scale s."""
    W, H = fr.W, fr.H
    gap = GAP * H
    w, h = o.w * s, o.h * s
    sl, st, sr, sb = fr.safe
    out = []
    if o.top_policy:
        # a title lives at the TOP band: same band, other side -> shrink -> farthest corner.
        # Never below the chin, never the middle band. The box keeps its TOP edge.
        top = o.cy - o.h * o.scale / 2
        cy = top + h / 2
        if o.xs:
            xs = list(o.xs)
        elif o.kind == "hook":  # 9:16 hook is centred and has no x key: shrink in place
            xs = [("centro", o.cx)]
        else:  # callouts: free x -> beside the face, or the frame thirds
            xs = [("left", W * 0.2), ("center", W * 0.5), ("right", W * 0.8)]
            if F:
                xs = [("esquerda do rosto", F[0] - gap - w / 2), ("direita do rosto", F[2] + gap + w / 2)] + xs
        if F:
            fcx = (F[0] + F[2]) / 2
            xs.sort(key=lambda nx: -abs(nx[1] - fcx))  # farthest from the face first
        for name, cx in xs:
            out.append((f"lado {name}", cx, cy))
        return out
    if o.xs:  # discrete horizontal choices (hook side / caption side)
        for name, cx in o.xs:
            out.append((f"lado {name}", cx, o.cy))
    fl, ft, frr, fb = F if F else (0, 0, 0, 0)
    if "y" in o.axes:
        if F:
            out.append(("abaixo do queixo", o.cx, max(o.cy, fb + gap + h / 2)))
            out.append(("acima da cabeça", o.cx, min(o.cy, ft - gap - h / 2)))
        else:
            out.append(("sem rosto", o.cx, o.cy))
    if "x" in o.axes and F:
        out.append(("ao lado (esquerda)", fl - gap - w / 2, o.cy))
        out.append(("ao lado (direita)", frr + gap + w / 2, o.cy))
        # same, lifted above / dropped below the face's band
        out.append(("esquerda, acima", fl - gap - w / 2, min(o.cy, ft - gap - h / 2)))
        out.append(("direita, acima", frr + gap + w / 2, min(o.cy, ft - gap - h / 2)))
    return out


def valid(fr: Frame, o: Ov, cx, cy, s, F, others):
    rect = o.rect(cx, cy, s)
    sl, st, sr, sb = fr.safe
    if rect[0] < sl - 0.5 or rect[1] < st - 0.5 or rect[2] > sr + 0.5 or rect[3] > sb + 0.5:
        return False
    if fr.portrait and fr.right_ui and rect[2] > fr.W - fr.right_ui and rect[3] > fr.H * 0.5:
        return False
    if F and inter(rect, F, GAP * 0.8 * fr.H):
        return False
    for q in others:
        if q is o or not (o.t0 < q.t1 and o.t1 > q.t0):
            continue
        if inter(rect, q.rect(), 4):
            return False
    return True


def solve(fr: Frame, o: Ov, others):
    """-> (status, placement|None, detail). status: ok | moved | split | locked | nofix"""
    F = fr.span(o.t0, o.t1)
    if o.kind == "hook" and fr.covered(o.t0, o.t1):
        return "ok", None, "coberto por B-roll/tela dividida (sem falante na tela) — não mexe"
    cur = o.rect()
    sl, st, sr, sb = fr.safe
    collides = bool(F and inter(cur, F, GAP * 0.8 * fr.H))
    outside = cur[0] < sl - 0.5 or cur[1] < st - 0.5 or cur[2] > sr + 0.5 or cur[3] > sb + 0.5
    clash = [q.id for q in others if q is not o and o.t0 < q.t1 and o.t1 > q.t0 and inter(cur, q.rect(), 4)]
    if not (collides or outside or clash):
        return "ok", None, "livre" if F else "sem rosto detectado na janela"
    why = ("rosto" if collides else "") + (" + " if collides and (outside or clash) else "") + \
          ("fora da área segura" if outside else "") + (" + " if outside and clash else "") + \
          (f"sobrepõe {','.join(clash)}" if clash else "")
    if o.locked or not o.movable:
        return "locked", None, f"{why} (lockPos/fixo — não movido)"
    for s in (SCALES if o.scalable else (1.0,)):
        for name, cx, cy in candidates(fr, o, F, s):
            if valid(fr, o, cx, cy, s, F, others):
                return "moved", dict(cx=cx, cy=cy, scale=s, how=name + (f" ×{s:g}" if s != 1 else "")), why
    if o.top_policy:
        why += " — sem espaço no topo — use B-roll/plano aberto sob o título ou encurte o texto"
    return "nofix", None, why


def try_split(fr: Frame, o: Ov, others):
    """Highlight cards only: two windows, each solved on its own."""
    if not o.kind.startswith("card") or o.t1 - o.t0 < 2.0:
        return None
    mid = (o.t0 + o.t1) / 2
    parts = []
    for a, b in ((o.t0, mid), (mid, o.t1)):
        c = Ov(o.id, o.kind, a, b, o.w, o.h, o.cx, o.cy)
        c.scale, c.axes, c.xs = o.scale, o.axes, o.xs
        st, pl, why = solve(fr, c, others)
        if st == "nofix":
            return None
        parts.append((a, b, pl))
    return parts


def run(ed: dict, fr: Frame, log):
    ovs, fixed = build_overlays(ed, fr)
    placed = list(fixed)
    results = []
    for o in sorted(ovs, key=lambda x: (not x.locked, x.t0)):  # locked first: they are obstacles
        st, pl, why = solve(fr, o, placed)
        split = None
        if st == "nofix":
            split = try_split(fr, o, placed)
            if split:
                st = "split"
        o.old = (o.cx, o.cy)
        results.append((o, st, pl, why, split))
        if st == "moved":
            o.cx, o.cy, o.scale = pl["cx"], pl["cy"], pl["scale"]
        placed.append(o)
    for fx in fixed:
        if fx.kind in ("lowerThird", "chapter"):
            F = fr.span(fx.t0, fx.t1)
            if F and inter(fx.rect(), F, GAP * 0.8 * fr.H):
                results.append((fx, "locked", None, "rosto (sem chaves de posição — mova o overlay à mão ou ajuste o enquadramento)", None))
    return results


def split_focus(ed: dict, fr: Frame, log):
    """Landscape splitInserts: centre the speaker column on the face (focusX/Y)."""
    out = []
    for i, sp in enumerate(ed.get("splitInserts") or []):
        if fr.portrait:
            continue
        F = fr.span(float(sp["start"]), float(sp["end"]))
        if not F:
            continue
        # face centre in SOURCE fractions (undo the camera: split re-frames the raw cut)
        fx = (F[0] + F[2]) / 2 / fr.W
        fy = (F[1] + F[3]) / 2 / fr.H
        if fr.cam.get("enabled"):
            continue
        cur = (sp.get("focusX", 0.55), sp.get("focusY", 0.5))
        if abs(cur[0] - fx) > 0.08 or abs(cur[1] - fy) > 0.12:
            out.append((i, sp, round(fx, 3), round(fy, 3), cur))
    return out


# ------------------------------------------------------------------- main ---
def resolve_dirs(edit: Path):
    for pub in (edit / "remotion" / "public", edit):
        if (pub / "edit-data.json").exists():
            return pub
    raise SystemExit(f"sem edit-data.json em {edit}/remotion/public nem em {edit}")


def apply_changes(ed: dict, results, focus):
    n = 0
    for o, st, pl, why, split in results:
        if st not in ("moved", "split") or not o.ref:
            continue
        key, i = o.ref
        W = None
        if st == "moved":
            n += 1
            _write(ed, key, i, pl, o)
        else:
            # split the card in two: first window keeps the id, the second is a copy
            hl = ed["highlights"]
            it = hl["items"][i]
            off = float(hl.get("offsetS", 0.8))
            (a, b, p1), (c, d, p2) = split
            base = dict(it)
            it["at"], it["dur"] = round(a - off, 3), round(b - a, 3)
            second = dict(base, at=round(c - off, 3), dur=round(d - c, 3))
            _write(ed, key, i, p1, o)
            hl["items"].append(second)
            _write(ed, key, len(hl["items"]) - 1, p2, o)
            n += 1
    for i, sp, fx, fy, cur in focus:
        ed["splitInserts"][i]["focusX"], ed["splitInserts"][i]["focusY"] = fx, fy
        ed["splitInserts"][i]["autoPlaced"] = True
        n += 1
    return n


def _write(ed, key, i, pl, o):
    W, H = ed["width"], ed["height"]
    if key == "hl":
        it = ed["highlights"]["items"][i]
        it["x"], it["y"] = round(pl["cx"] / W, 4), round(pl["cy"] / H, 4)
        if pl["scale"] != 1:
            it["scale"] = pl["scale"]
        it["autoPlaced"] = True
    elif key == "callouts":
        it = ed["callouts"][i]
        it["x"], it["y"] = round(pl["cx"] / W, 4), round(pl["cy"] / H, 4)
        it["autoPlaced"] = True
    elif key == "hook":
        hk = ed["hook"]
        if o.xs and pl["how"].startswith("lado"):
            hk["side"] = pl["how"].split()[1]
        k = (W / 1080) if H > W else (H / 1080)
        hk["paddingTop"] = round((pl["cy"] - o.h * pl["scale"] / 2) / k)
        if pl["scale"] != 1:
            hk["scale"] = pl["scale"]
        hk["autoPlaced"] = True
    elif key == "captions":
        cp = ed["captions"]
        if o.xs:
            cp["side"] = pl["how"].split()[1]
        elif False:
            pass
        else:
            frac = pl["cy"] / H
            if cp.get("style") == "stacked":
                cp["stackedOffsetY"] = round(frac - 0.5, 4)
            else:
                cp["scatterOffsetY"] = round(frac, 4)
        cp["autoPlaced"] = True


def report_lines(results, focus, fr: Frame):
    W, H = fr.W, fr.H
    lines = []
    for o, st, pl, why, split in sorted(results, key=lambda r: r[0].t0):
        win = f"{o.t0:6.2f}-{o.t1:6.2f}s"
        old = f"x{o.cx / W:.2f} y{o.cy / H:.2f}"
        if st == "ok":
            lines.append(f"  OK       {o.id:<16} {win}  {old}  {why}")
        elif st == "moved":
            sc = "" if pl["scale"] == 1 else " ×%g" % pl["scale"]
            lines.append("  MOVIDO   %-16s %s  x%.2f y%.2f → x%.2f y%.2f%s  [%s] motivo: %s" % (
                o.id, win, o.old[0] / W, o.old[1] / H, pl["cx"] / W, pl["cy"] / H, sc, pl["how"], why))
        elif st == "split":
            (a, b, p1), (c, d, p2) = split
            lines.append(f"  DIVIDIDO {o.id:<16} {win}  → {a:.1f}-{b:.1f}s x{p1['cx'] / W:.2f} y{p1['cy'] / H:.2f} | "
                         f"{c:.1f}-{d:.1f}s x{p2['cx'] / W:.2f} y{p2['cy'] / H:.2f}  motivo: {why}")
        elif st == "locked":
            lines.append(f"  COLISÃO  {o.id:<16} {win}  {old}  {why}")
        else:
            tail = "" if o.top_policy else " — nenhuma posição livre (close-up?): faça essa janela em tela cheia"
            lines.append(f"  SEM ESPAÇO {o.id:<14} {win}  {old}  {why}{tail}")
    for i, sp, fx, fy, cur in focus:
        lines.append(f"  FOCO     splitInserts[{i}]  focusX/Y {cur[0]:.2f}/{cur[1]:.2f} → {fx:.2f}/{fy:.2f} (rosto fora do centro da coluna)")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Posiciona overlays fora do rosto (safe layout)")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--platform", default="all", choices=sorted(PLATFORMS_916))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--redetect", action="store_true", help="refaz faces.json mesmo que exista")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--fetch-model", action="store_true",
                    help="baixa o YuNet (OpenCV Zoo, MIT, 232.589 bytes, sha256 conferido) — detector melhor que Haar")
    a = ap.parse_args(argv)
    if a.fetch_model:
        import hashlib
        import urllib.request
        YUNET.parent.mkdir(exist_ok=True)
        tmp = YUNET.with_suffix(".part")
        urllib.request.urlretrieve(YUNET_URL, tmp)
        data = tmp.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != YUNET_SIZE or digest != YUNET_SHA256:
            tmp.unlink(missing_ok=True)
            _sys.exit(f"modelo recusado: {len(data)} bytes, sha256 {digest[:12]}… "
                     f"(esperado {YUNET_SIZE} bytes, {YUNET_SHA256[:12]}…)")
        tmp.replace(YUNET)
        print(f"modelo salvo em {YUNET} ({len(data)} bytes, sha256 ok)")
    pub = resolve_dirs(a.edit.resolve())
    ed_p = pub / "edit-data.json"
    ed = json.loads(ed_p.read_text(encoding="utf-8"))
    faces_p = pub / "faces.json"
    video = pub / "cut.mp4"
    if a.redetect or not faces_p.exists() or (video.exists() and faces_p.stat().st_mtime < video.stat().st_mtime):
        if not video.exists():
            raise SystemExit(f"sem {video}")
        print(f"[faces] detectando em {video.name} ({a.fps:g} fps)…", flush=True)
        data = detect_faces(video, a.fps)
        faces_p.write_text(json.dumps(data), encoding="utf-8")
    data = json.loads(faces_p.read_text(encoding="utf-8"))
    faces = Faces(data)
    print(f"[faces] detecções brutas {data['detected']}/{data['total']} ({100 * data['detected'] // max(1, data['total'])}%); "
          f"consistentes após filtro {len(faces.pts)} ({100 * faces.rate:.0f}%) — {data.get('detector')} {data.get('by')}")
    fr = Frame(ed, pub, faces, a.platform)
    results = run(ed, fr, print)
    focus = split_focus(ed, fr, print)
    bad = [r for r in results if r[1] in ("moved", "split", "locked", "nofix")] + focus
    if a.report or not a.apply:
        print(f"[safe_layout] {fr.W}x{fr.H} · plataforma {a.platform} · {len(results)} overlay(s)")
        for ln in report_lines(results, focus, fr):
            print(ln)
    if a.apply:
        ts = time.strftime("%Y%m%d-%H%M%S")
        bak = pub / f"edit-data.before_safe_layout.{ts}.json"
        shutil.copy2(ed_p, bak)
        n = apply_changes(ed, results, focus)
        ed_p.write_text(json.dumps(ed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[apply] {n} overlay(s) reposicionado(s) → {ed_p.name} (backup {bak.name})")
    return 1 if (bad and not a.apply and any(r[1] in ("moved", "split", "locked", "nofix") for r in results)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
