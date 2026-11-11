"""HyperFrames × Remotion parity — the gate a layer passes before it is `ported`.

    uv run python helpers/hf_parity.py <edit> [--hf <mp4>] [--remotion <mp4>]
           [--layers base,captions,hook,…] [--per-layer 6] [--ssim-min 0.95]
           [--out <edit>/verify/parity] [--sheet 8]

Both renders come from the SAME edit-data.json: Remotion's `remotion/out/render.mp4`
(render_phase2 --engine remotion --skip-delivery) and HyperFrames'
`hyperframes/out/render.mp4` (build_hyperframes --render). Windows and boxes come
from `hyperframes/render.json` (written by the builder).

Per layer window (up to --per-layer, spread over the video):
  - SSIM of the luma IN THE LAYER'S BOX at entry (+0.15 s), settled (middle) and
    exit (−0.1 s); threshold 0.95 for 2D (decision 3), 0.97 for the bare base (decode floor);
  - timing: the frame offset δ ∈ {−2…2} that best aligns HF with Remotion around
    the entry and the exit (target |δ| ≤ 1);
  - tone: Remotion is range-normalised (pc → tv) and its luma fitted to HF's on
    base-only frames (the deliver_mix --tone-ref regression) before comparing.
Writes parity.json and a contact sheet (Remotion | HyperFrames | diff×4) for one Read.

    uv run python helpers/hf_parity.py <edit> --sync-final <final.mp4>

A/V of a delivery made from a `build_hyperframes --sync-probe` render (target: the
voice within 1 frame of the picture).
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

# base: calibrated in F1 (plan §3.5 "limiares iniciais, a calibrar"). The bare base is
# the SAME file in both engines, pixel-aligned (phase correlation ≤ 0.02 px, δ = 0), so
# what is left is decode sharpness: HyperFrames' frames are crisper than Remotion's
# OffthreadVideo extraction. Measured floor (σ 1 px SSIM): CLA200 ≥ 0.98, grainy
# up-scaled fixture 0.972–0.99. The base gate is "δ = 0 and SSIM ≥ 0.97"; 0.99 was a guess.
THR = {"base": 0.97}
DEFAULT_THR = 0.95


def probe(p: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,pix_fmt,color_range,nb_frames", "-of", "json", str(p)],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def range_vf(p: Path) -> str:
    s = probe(p)
    full = s.get("color_range") == "pc" or str(s.get("pix_fmt", "")).startswith("yuvj")
    return "scale=in_range=full:out_range=limited," if full else ""


def frames_at(p: Path, idx: list[int], w: int, h: int, color: bool = False) -> dict[int, np.ndarray]:
    """Decode exactly the frames `idx` (frame numbers), luma (or RGB) at w×h."""
    want = sorted(set(i for i in idx if i >= 0))
    if not want:
        return {}
    out: dict[int, np.ndarray] = {}
    ch = 3 if color else 1
    # chunks keep the select expression short
    for c in range(0, len(want), 60):
        part = want[c:c + 60]
        sel = "+".join(f"eq(n\\,{i})" for i in part)
        vf = f"{range_vf(p)}select='{sel}',scale={w}:{h}:flags=area,format={'rgb24' if color else 'gray'}"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vf", vf, "-vsync", "0", "-f", "rawvideo", "-"],
                             capture_output=True).stdout
        arr = np.frombuffer(raw, np.uint8)
        n = len(arr) // (w * h * ch)
        arr = arr[: n * w * h * ch].reshape((n, h, w, ch) if color else (n, h, w))
        for i, fr in zip(part, arr):
            out[i] = fr
    return out


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM at DRAWING scale: both sides low-passed (σ 1 px) first. Remotion decodes
    video frames softer than HyperFrames (OffthreadVideo frame extraction; measured on
    the fixture: |Laplacian| HF 3.3 vs Remotion 2.9 on the same, perfectly aligned base
    frame) — a decode property of the engines, not a layer that draws differently."""
    a = cv2.GaussianBlur(a.astype(np.float64), (0, 0), 1.0)
    b = cv2.GaussianBlur(b.astype(np.float64), (0, 0), 1.0)
    if min(a.shape) < 11:
        return float("nan")
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    g = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)
    mu1, mu2 = g(a), g(b)
    s1, s2, s12 = g(a * a) - mu1 ** 2, g(b * b) - mu2 ** 2, g(a * b) - mu1 * mu2
    m = ((2 * mu1 * mu2 + C1) * (2 * s12 + C2)) / ((mu1 ** 2 + mu2 ** 2 + C1) * (s1 + s2 + C2))
    return float(m[5:-5, 5:-5].mean()) if m.shape[0] > 10 and m.shape[1] > 10 else float(m.mean())


def crop(img: np.ndarray, box, W, H, scale=1.0):
    x, y, w, h = box or [0, 0, W, H]
    x0, y0 = int(max(0, x) * scale), int(max(0, y) * scale)
    x1, y1 = int(min(W, x + w) * scale), int(min(H, y + h) * scale)
    return img[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)]


def pick(wins: list[dict], n: int) -> list[dict]:
    if len(wins) <= n:
        return wins
    step = len(wins) / n
    return [wins[int(i * step + step / 2)] for i in range(n)]


def sync_check(edit: Path, final: Path) -> dict:
    """A/V of a delivery built from a `build_hyperframes --sync-probe` render.

    picture: frames where the 80×80 probe square lights up vs the word onsets the
    builder wrote (render.json syncOnsets); audio: cross-correlation of the
    delivered voice against cut.mp4. offset = audio delay − picture delay."""
    info = json.loads((edit / "hyperframes" / "render.json").read_text(encoding="utf-8"))
    fps, onsets = info["fps"], info.get("syncOnsets") or []
    if not onsets:
        raise SystemExit("render.json sem syncOnsets — monte com build_hyperframes --sync-probe")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-vf", "crop=60:60:10:10,scale=6:6,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    lum = np.frombuffer(raw, np.uint8).reshape(-1, 36).mean(1)
    lit = lum > 200
    rises = [i for i in range(1, len(lit)) if lit[i] and not lit[i - 1]] + ([0] if len(lit) and lit[0] else [])
    errs = []
    for o in onsets:
        near = [r - o for r in rises if abs(r - o) <= 3]
        if near:
            errs.append(min(near, key=abs))
    pic_ms = float(np.median(errs)) * 1000 / fps if errs else float("nan")

    def pcm(p, ss, t):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(ss), "-t", str(t), "-i", str(p), "-ac", "1", "-ar", "16000",
                            "-f", "f32le", "-"], capture_output=True).stdout
        return np.frombuffer(r, np.float32).astype(float)
    a, b = pcm(edit / "cut.mp4", 1, 20), pcm(final, 1, 20)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    c = np.fft.irfft(np.fft.rfft(b, 2 * n) * np.conj(np.fft.rfft(a, 2 * n)))
    i = int(np.argmax(c))
    aud_ms = (i if i < n else i - 2 * n) / 16.0
    return {"onsets": len(onsets), "matched": len(errs), "pictureDelayMs": round(pic_ms, 1),
            "audioDelayMs": round(aud_ms, 1), "avOffsetMs": round(aud_ms - pic_ms, 1),
            "ok": bool(errs) and abs(aud_ms - pic_ms) <= 1000 / fps + 1}


def main() -> None:
    if "--sync-final" in sys.argv:
        k = sys.argv.index("--sync-final")
        r = sync_check(Path(sys.argv[1]).resolve(), Path(sys.argv[k + 1]).resolve())
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r["ok"] else 1)
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--hf", type=Path, default=None)
    ap.add_argument("--remotion", type=Path, default=None)
    ap.add_argument("--layers", default="")
    ap.add_argument("--per-layer", type=int, default=6)
    ap.add_argument("--ssim-min", type=float, default=DEFAULT_THR)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sheet", type=int, default=8, help="moments in the contact sheet")
    a = ap.parse_args()

    edit = a.edit.resolve()
    hfroot = edit / "hyperframes"
    info = json.loads((hfroot / "render.json").read_text(encoding="utf-8"))
    hf = (a.hf or hfroot / "out" / "render.mp4").resolve()
    rm = (a.remotion or edit / "remotion" / "out" / "render.mp4").resolve()
    for p in (hf, rm):
        if not p.exists():
            raise SystemExit(f"render ausente: {p}")
    out = (a.out or edit / "verify" / "parity").resolve()
    out.mkdir(parents=True, exist_ok=True)
    W, H, fps, N = info["width"], info["height"], info["fps"], info["frames"]
    only = {x.strip() for x in a.layers.split(",") if x.strip()}
    windows = {k: v for k, v in info["windows"].items() if (not only or k in only) and k != "syncProbe"}
    fhf, frm = int(probe(hf).get("nb_frames") or 0), int(probe(rm).get("nb_frames") or 0)

    # ---- tone: fit Remotion luma → HF luma on base-only frames (full frame, both engines zoom alike)
    tone_f = [int(round(t * fps)) for t in info.get("toneTimes") or []][:6]
    th, tr = frames_at(hf, tone_f, W // 4, H // 4), frames_at(rm, tone_f, W // 4, H // 4)
    both = [f for f in tone_f if f in tr and f in th]
    if both:   # no base-only frame (overlays everywhere, e.g. the fixture): compare untouched
        X = np.concatenate([tr[f].ravel() for f in both]).astype(float)
        Y = np.concatenate([th[f].ravel() for f in both]).astype(float)
        g, o = np.polyfit(X, Y, 1)
    else:
        g, o = 1.0, 0.0
    tone = lambda img: np.clip(img.astype(float) * g + o, 0, 255)
    # fadeOut: Remotion's picture has no fade — render_phase2's delivery adds it
    # (ffmpeg fade, linear). Apply the same ramp to the Remotion frames compared.
    fades = [(w["f0"], w["f1"]) for w in info["windows"].get("fadeOut", [])]

    def fade_rm(d: dict) -> dict:
        for f0, f1 in fades:
            for f in d:
                if f0 <= f < f1:
                    d[f] = (d[f].astype(float) * (1 - (f - f0) / max(1, f1 - f0))).astype(np.uint8)
        return d

    # ---- instants per layer
    plan = []
    for key, wins in windows.items():
        for w in pick(wins, a.per_layer if key != "base" else min(a.per_layer, 4)):
            f0, f1 = w["f0"], w["f1"]
            if key == "base":
                inst = {"settled": (f0 + f1) // 2}
            else:
                inst = {"entry": min(f1 - 1, f0 + round(0.15 * fps)), "settled": (f0 + f1) // 2,
                        "exit": max(f0, f1 - 1 - round(0.1 * fps))}
            plan.append({"layer": key, "id": w["id"], "f0": f0, "f1": f1, "box": w.get("box"), "inst": inst})
    full_idx = sorted({f for p in plan for f in p["inst"].values()})
    print(f"parity: {len(plan)} janelas · {len(full_idx)} quadros em resolução cheia · tom R→HF = {g:.4f}·x {o:+.2f}")
    A = frames_at(hf, full_idx, W, H)
    B = fade_rm(frames_at(rm, full_idx, W, H))

    # timing frames (quarter res) around entry/exit
    sc = 0.25
    tim_idx = set()
    for p in plan:
        if p["layer"] == "base":
            continue
        for c in (p["f0"], p["f1"]):
            tim_idx.update(range(max(0, c - 6), min(N, c + 9)))
    tA = frames_at(hf, sorted(tim_idx), int(W * sc), int(H * sc))
    tB = fade_rm(frames_at(rm, sorted(tim_idx), int(W * sc), int(H * sc)))

    def offset(p, edge):
        c = p["f0"] if edge == "entry" else p["f1"]
        rng = range(c - 3, c + 5) if edge == "entry" else range(c - 5, c + 3)
        best, bd = None, None
        for d in (-2, -1, 0, 1, 2):
            errs = []
            for f in rng:
                if f in tA and (f + d) in tB:
                    errs.append(np.abs(crop(tA[f], p["box"], W, H, sc).astype(float)
                                       - tone(crop(tB[f + d], p["box"], W, H, sc))).mean())
            if errs:
                e = float(np.mean(errs))
                if bd is None or e < bd - 1e-9 or (abs(e - bd) < 1e-9 and abs(d) < abs(best)):
                    best, bd = d, e
        return best

    rows, per_layer = [], {}
    for p in plan:
        thr = THR.get(p["layer"], a.ssim_min)
        res = {"layer": p["layer"], "id": p["id"], "f0": p["f0"], "f1": p["f1"], "ssim": {}}
        for name, f in p["inst"].items():
            if f in A and f in B:
                res["ssim"][name] = round(ssim(crop(A[f], p["box"], W, H), tone(crop(B[f], p["box"], W, H))), 4)
        if p["layer"] != "base":
            res["dEntry"], res["dExit"] = offset(p, "entry"), offset(p, "exit")
        vals = [v for v in res["ssim"].values() if v == v]
        res["min"] = min(vals) if vals else None
        res["pass"] = bool(vals) and min(vals) >= thr and all(abs(res.get(k) or 0) <= 1 for k in ("dEntry", "dExit"))
        rows.append(res)
        L = per_layer.setdefault(p["layer"], {"windows": 0, "pass": 0, "ssimMin": 1.0, "ssimMean": [], "dMax": 0,
                                               "threshold": thr})
        L["windows"] += 1
        L["pass"] += res["pass"]
        if vals:
            L["ssimMin"] = min(L["ssimMin"], min(vals))
            L["ssimMean"] += vals
        L["dMax"] = max(L["dMax"], abs(res.get("dEntry") or 0), abs(res.get("dExit") or 0))
    for L in per_layer.values():
        L["ssimMean"] = round(float(np.mean(L["ssimMean"])), 4) if L["ssimMean"] else None
        L["ssimMin"] = round(L["ssimMin"], 4)
        L["ok"] = L["pass"] == L["windows"]

    # ---- whole-frame base lag (HF vs Remotion): δ that best aligns tone frames
    lag = {}
    for d in (-1, 0, 1):
        idx = [f + d for f in tone_f]
        rB = frames_at(rm, idx, W // 4, H // 4)
        e = [np.abs(th[f].astype(float) - tone(rB[f + d])).mean() for f in tone_f if f in th and (f + d) in rB]
        lag[d] = float(np.mean(e)) if e else None
    base_lag = min((d for d in lag if lag[d] is not None), key=lambda d: lag[d], default=None)

    # ---- contact sheet: Remotion | HF | diff×4
    moments = []
    for key in [k for k in windows if k != "base"] + ["base"]:
        for r in [r for r in rows if r["layer"] == key][:2]:
            f = (r["f0"] + r["f1"]) // 2 if key != "base" else (r["f0"] + r["f1"]) // 2
            moments.append((key, r["id"], f))
    moments = moments[: a.sheet]
    sheet_path = out / "parity_sheet.png"
    if moments:
        tw = 480
        th_ = int(tw * H / W)
        cA = frames_at(hf, [m[2] for m in moments], tw, th_, color=True)
        cB = fade_rm(frames_at(rm, [m[2] for m in moments], tw, th_, color=True))
        lab_h = 22
        sheet = np.zeros((len(moments) * (th_ + lab_h), tw * 3, 3), np.uint8)
        for i, (key, cid, f) in enumerate(moments):
            y = i * (th_ + lab_h)
            ra, rb = cA.get(f), cB.get(f)
            if ra is None or rb is None:
                continue
            rbt = np.clip(rb.astype(float) * g + o, 0, 255).astype(np.uint8)
            diff = np.clip(np.abs(ra.astype(int) - rbt.astype(int)) * 4, 0, 255).astype(np.uint8)
            sheet[y + lab_h:y + lab_h + th_, 0:tw] = rb
            sheet[y + lab_h:y + lab_h + th_, tw:2 * tw] = ra
            sheet[y + lab_h:y + lab_h + th_, 2 * tw:] = diff
            r = next((r for r in rows if r["id"] == cid), {})
            txt = f"{key} {cid} @{f / fps:.2f}s  REMOTION | HYPERFRAMES | DIFFx4   ssim {r.get('min')}"
            cv2.putText(sheet, txt, (6, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imwrite(str(sheet_path), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))

    rep = {"hf": str(hf), "remotion": str(rm), "frames": {"hf": fhf, "remotion": frm, "expected": N},
           "tone": {"gain": round(float(g), 4), "offset": round(float(o), 2)},
           "baseLag": {"best": base_lag, "err": lag}, "layers": per_layer, "windows": rows,
           "sheet": str(sheet_path) if moments else None}
    (out / "parity.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"quadros: HF {fhf} · Remotion {frm} · esperado {N}   lag da base HF×Remotion: {base_lag} quadro(s)")
    for k, L in per_layer.items():
        print(f"  {'PASS' if L['ok'] else 'FAIL'}  {k:<14} {L['pass']}/{L['windows']} janelas · SSIM mín {L['ssimMin']} "
              f"· média {L['ssimMean']} (limiar {L['threshold']}) · |δ| máx {L['dMax']} quadro(s)")
    print(f"parity.json + {sheet_path.name} em {out}")
    sys.exit(0 if all(L["ok"] for L in per_layer.values()) and frm == fhf else 1)


import sys  # noqa: E402

if __name__ == "__main__":
    main()
