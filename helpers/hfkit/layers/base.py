"""Base picture + dynamic camera (templates' DynamicVideo / Base, Camera.tsx).

assets/base.mp4 = cut.mp4 (grade already baked in Phase 1) re-encoded with
`-g fps` so the seek never freezes on a long GOP (shortform.md "Acabamento"),
bt709/tv tags. One <video> clip per take at the segments.json seams, each inside
its own `.cam` wrapper: the wrapper animates transform only ("time the <video>,
never its wrapper"). Each take carries a paired <audio> in group `voz` so the
Studio preview has sound — the delivery never uses HyperFrames' audio.
"""
from __future__ import annotations

import json
import subprocess

from .. import timebase as tb

Z = 0


def _src(ctx):
    for p in (ctx.pub / "cut.mp4", ctx.edit / "cut.mp4"):
        if p.exists():
            return p
    raise SystemExit("cut.mp4 não encontrado (nem em remotion/public nem no <edit>)")


def make_base(ctx) -> str:
    src = _src(ctx)
    out = ctx.proj.root / "assets" / "base.mp4"
    stamp = ctx.proj.root / ".prisma" / "base.json"
    key = {"src": str(src), "size": src.stat().st_size, "mtime": int(src.stat().st_mtime),
           "W": ctx.W, "H": ctx.H, "fps": ctx.fps, "N": ctx.N, "lag": tb.PICTURE_LAG, "v": 3}
    try:
        if out.exists() and json.loads(stamp.read_text(encoding="utf-8")) == key:
            return "assets/base.mp4"
    except (OSError, json.JSONDecodeError):
        pass
    # NOT the cut's first-pts offset: at the top level Remotion draws cut.mp4 from its
    # first frame (fixture cut with start_time 0.033: aligned only without a pad)
    lag = tb.PICTURE_LAG
    vf = (f"scale={ctx.W}:{ctx.H}:flags=lanczos,fps={ctx.fps},"
          + (f"tpad=start={lag}:start_mode=clone," if lag else "") + "format=yuv420p")
    # Studio preview only: the voice where the delivery puts it (deliver_mix --video-lag PICTURE_LAG)
    af = (f"adelay={round(48000 * tb.PICTURE_LAG / ctx.fps)}S:all=1," if tb.PICTURE_LAG else "") + "aresample=48000"
    print("base.mp4 (cut.mp4 → -g fps, bt709/tv)…", flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-af", af,
                    "-frames:v", str(ctx.N), "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                    "-g", str(ctx.fps), "-keyint_min", str(ctx.fps), "-sc_threshold", "0",
                    "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                    "-color_trc", "bt709", "-color_range", "tv", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out)], check=True)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps(key), encoding="utf-8")
    return "assets/base.mp4"


def _cam_at(ctx, k, f):
    """(tx, ty, S) of DynamicVideo at output frame f inside take k (same maths, same clamps)."""
    cam = ctx.ed.get("camera") or {}
    if not cam.get("enabled") or not ctx.segs:
        return 0.0, 0.0, 1.0
    zooms = cam.get("zooms") or [1.08 if ctx.fmt == "long" else 1.14]
    seg = ctx.segs[min(k, len(ctx.segs) - 1)]
    seg_from = ctx.f(float(seg["start"])) + tb.TEMPLATE_LAG
    seg_len = max(1, ctx.f(float(seg["dur"])))
    push = float(cam.get("pushIn") or 0) * min(1.0, max(0.0, (f - seg_from) / seg_len))
    S = (zooms[k % len(zooms)] or 1) + push
    cx, cy = ctx.track_point(f)
    W, H = ctx.W, ctx.H
    tx = min(max(float(cam.get("targetX", 0.5)) * W - cx * W * S, W - W * S), 0)
    ty = min(max(float(cam.get("targetY", 0.4)) * H - cy * H * S, H - H * S), 0)
    return round(tx, 2), round(ty, 2), round(S, 4)


def build(ctx):
    src = make_base(ctx)
    P, fps = ctx.proj, ctx.fps
    seams = ctx.seams + [ctx.N]
    takes = []
    for k in range(len(ctx.seams)):
        f0, f1 = seams[k], seams[k + 1]
        tid = f"take-{k + 1:02d}"
        s, d = tb.span(f0, f1, fps)
        m = tb.media_t(f0, fps)   # base time == output time
        P.media.append((Z, f'    <div class="cam" id="cam-{k + 1:02d}"><video id="{tid}" class="clip" src="{src}" '
                           f'data-start="{s}" data-duration="{d}" data-media-start="{m}" data-track-index="0" '
                           f'muted playsinline></video></div>'))
        # 2 µs shorter: start+duration sums to the next take's start in float, and lint
        # reads that as an overlap on the audio lane (duplicate_audio_track)
        P.audio.append(f'    <audio id="{tid}-a" src="{src}" data-start="{s}" data-duration="{tb.r6(d - 2e-6)}" '
                       f'data-media-start="{m}" data-track-index="9" data-volume="1" data-audio-group="voz"></audio>')
        takes.append({"id": tid, "f0": f0, "f1": f1, "cut0": max(0, f0 - tb.TEMPLATE_LAG)})
        # camera: a set at the take's first frame + one linear tween over the push
        # (S and the clamped translate are linear in f between the clamps)
        sel = f'"#cam-{k + 1:02d}"'
        x0, y0, s0 = _cam_at(ctx, k, f0)
        P.root_script.append(f'      tl.set({sel}, {{x:{x0}, y:{y0}, scale:{s0}, force3D:false}}, {tb.t_at(f0, fps)});')
        cam = ctx.ed.get("camera") or {}
        if cam.get("enabled") and cam.get("pushIn") and ctx.segs:
            seg = ctx.segs[min(k, len(ctx.segs) - 1)]
            seg_from = ctx.f(float(seg["start"])) + tb.TEMPLATE_LAG
            a = max(f0, seg_from)
            b = min(f1 - 1, seg_from + max(1, ctx.f(float(seg["dur"]))))
            if b > a:
                xa, ya, sa = _cam_at(ctx, k, a)
                xb, yb, sb = _cam_at(ctx, k, b)
                P.root_script.append(
                    f'      tl.fromTo({sel}, {{x:{xa}, y:{ya}, scale:{sa}}}, {{x:{xb}, y:{yb}, scale:{sb}, '
                    f'duration:{tb.r6((b - a) / fps)}, ease:"none", immediateRender:false, force3D:false}}, '
                    f'{tb.r6(a / fps)});')
    ctx.takes = takes
    P.windows["base"] = [{"id": t["id"], "f0": t["f0"], "f1": t["f1"], "box": None} for t in takes]


def cam_for_frame(ctx, f: int):
    """[tx, ty, S] of the base at output frame f (render_phase2 builds the tone reference from it)."""
    seams = ctx.seams + [ctx.N]
    k = max(i for i in range(len(ctx.seams)) if seams[i] <= f)
    return list(_cam_at(ctx, k, f))
