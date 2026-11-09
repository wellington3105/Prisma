"""Cutaways over the speaker: 16:9 `broll[]`, 9:16 `inserts[]`, both formats' `splitInserts[]`, `fadeOut`.

Remotion 4.0.482's OffthreadVideo shows source frame k at local frame k (measured,
timebase.py), so a cutaway's <video> starts with its clip at media 0. The split's
footage is the base itself, flat-mounted in Remotion: it shows the base at the
GLOBAL time, and its window edges carry the template's VIDEO_LAG (+1).
Inner element ids never equal the composition id: the root host div carries it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .. import timebase as tb
from ..project import js

VIDEO = re.compile(r"\.(mp4|mov|webm|m4v)$", re.I)
FILL = ("        .fill { position:absolute; top:0; left:0; right:0; bottom:0; width:100%; height:100%; "
        "display:flex; flex-direction:column; }")


def _n(x: float) -> str:
    return repr(float(x)) if x != int(x) else str(int(x))


def _src(ctx, rel: str, what: str):
    p = ctx.pub / rel
    if not p.exists():
        ctx.notes.append(f"{what}: asset não encontrado ({rel}) — fora do HyperFrames")
        return None, False
    return ctx.proj.asset(p, "media"), bool(VIDEO.search(rel))


def pts_lag(ctx, rel: str) -> int:
    """Frames of the file's CONTAINER start offset. Remotion places frames at their
    absolute pts; HyperFrames counts from the container start. They differ by the
    container start_time: a video-only clip cut with `-ss` that starts at pts 0.033
    draws one frame late in Remotion (fixture B-roll), while cut.mp4 (video 0.033,
    audio 0 → container 0) is aligned in both. Measured 2026-11-09."""
    if not VIDEO.search(rel):
        return 0
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=start_time", "-of", "default=nw=1:nk=1", str(ctx.pub / rel)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return max(0, tb.fround(float(out), ctx.fps))
    except ValueError:
        return 0


def _media(eid, src, is_video, dur_s, style, lag=0, fps=30):
    if is_video:
        start = tb.t_at(lag, fps)   # nonzero only for a pts-offset file (lint: nested_media_start_basis_ambiguous)
        return (f'<video id="{eid}-m" class="clip" src="{src}" data-start="{start}" '
                f'data-duration="{tb.r6(max(1e-3, dur_s - start))}" '
                f'data-media-start="0" muted playsinline style="{style}"></video>')
    return f'<img id="{eid}-m" src="{src}" alt="" style="{style}" />'


def build_broll(ctx):
    """longform/src/Main.tsx BrollEl (pip is unported → whole video falls back)."""
    for i, it in enumerate(ctx.ed.get("broll") or []):
        src, is_video = _src(ctx, it["src"], f"broll {it.get('id') or i + 1}")
        if not src:
            continue
        f0 = ctx.f(float(it["start"]))
        total = ctx.f(float(it.get("dur") or 4))
        cid = ctx.proj.uid(f"broll-{it.get('id') or f'{i + 1:02d}'}")
        s, d = tb.span(f0, f0 + total, ctx.fps)
        eid = f"{cid}-e"
        img = it.get("kind") == "image" or not is_video
        style = "width:100%; height:100%; object-fit:cover;"
        body = (f'        <div id="{eid}" class="fill" style="opacity:0">'
                f'{_media(eid, src, not img, d, style, pts_lag(ctx, it["src"]), ctx.fps)}</div>')
        o = {"id": eid, "fps": ctx.fps, "total": total, "image": img, "spring": it.get("enter") == "spring"}
        ctx.proj.sub(cid, FILL, body, f"          PrismaHF.layers.brollLong(tl, {js(o)});", fonts=False)
        ctx.proj.host(cid, f0, f0 + total, 6 + i % 2, "graphics", 10, "broll", [0, 0, ctx.W, ctx.H])


def build_inserts(ctx):
    """shortform/src/Main.tsx Inserts + InsertCard (frame:'glass' is unported)."""
    for i, it in enumerate(ctx.ed.get("inserts") or []):
        src, is_video = _src(ctx, it["src"], f"insert {it.get('id') or i + 1}")
        if not src:
            continue
        f0 = ctx.f(float(it["start"]))
        total = ctx.f(float(it["end"]) - float(it["start"]))
        fit = it.get("fit") or "card"
        full = fit in ("cover", "contain")
        drift = it.get("drift")
        d0, d1 = (float(drift["from"]), float(drift["to"])) if drift else ((1.0, 1.04) if full else (1.0, 1.08))
        cid = ctx.proj.uid(f"insert-{it.get('id') or f'{i + 1:02d}'}")
        s, d = tb.span(f0, f0 + total, ctx.fps)
        eid = f"{cid}-e"
        mstyle = f"width:100%; height:100%; object-fit:{'contain' if fit == 'contain' else 'cover'};"
        media = _media(eid, src, is_video, d, mstyle, pts_lag(ctx, it["src"]), ctx.fps)
        if full:
            body = (f'        <div class="fill"><div id="{eid}" class="fill" style="opacity:0; overflow:hidden; '
                    f'background-color:#000;">{media}</div></div>')
            box = [0, 0, ctx.W, ctx.H]
        else:
            body = (f'        <div class="fill" style="justify-content:flex-start; align-items:center;">'
                    f'<div id="{eid}" style="width:780px; height:500px; margin-top:90px; border-radius:28px; '
                    f'overflow:hidden; opacity:0; box-shadow:0 18px 50px rgba(0,0,0,0.45);">{media}</div></div>')
            box = [ctx.W / 2 - 430, 40, 860, 620]
        o = {"id": eid, "fps": ctx.fps, "total": total, "full": full, "d0": d0, "d1": d1,
             "spring": it.get("enter") == "spring"}
        ctx.proj.sub(cid, FILL, body, f"          PrismaHF.layers.insertShort(tl, {js(o)});", fonts=False)
        ctx.proj.host(cid, f0, f0 + total, 6 + i % 2, "graphics", 10, "inserts", box)


def build_split(ctx):
    """Split screen. 9:16: shortform CustomGraphics SplitFrame (art band on top/bottom);
    16:9: longform/src/Split.tsx (art column left/right). Window edges carry VIDEO_LAG."""
    W, H, fps = ctx.W, ctx.H, ctx.fps
    long = ctx.fmt == "long"
    LAYOUT = {"top": (1.25, 400), "bottom": (1.0, 225)}
    for i, it in enumerate(ctx.ed.get("splitInserts") or []):
        src, art_video = _src(ctx, it["src"], f"split {it.get('id') or i + 1}")
        if not src:
            continue
        a = ctx.f(float(it["start"])) + tb.TEMPLATE_LAG
        b = ctx.f(float(it["end"])) + tb.TEMPLATE_LAG
        if b <= a:
            continue
        total = b - a
        cid = ctx.proj.uid(f"split-{it.get('id') or i + 1}")
        s, d = tb.span(a, b, fps)
        fit = it.get("fit") or "cover"
        base_v = (f'<video id="{cid}-v" class="clip" src="assets/base.mp4" data-start="0" data-duration="{d}" '
                  f'data-media-start="{tb.media_t(a, fps)}" muted playsinline style="position:absolute; {{pos}}"></video>')
        art_style = f"width:100%; height:100%; object-fit:{fit};"
        if art_video:   # flat-mounted in Remotion: plays at the GLOBAL time
            art = (f'<video id="{cid}-a" class="clip" src="{src}" data-start="0" data-duration="{d}" '
                   f'data-media-start="{tb.media_t(max(0, a - pts_lag(ctx, it["src"])), fps)}" muted playsinline style="{art_style}"></video>')
        else:
            art = f'<img id="{cid}-a" src="{src}" alt="" style="{art_style}" />'
        if long:
            art_left = (it.get("layout") or "top") in ("top", "left")
            art_w = round(W * min(max(float(it.get("bandW") or 0.5), 0.3), 0.7))
            col_w = W - art_w
            zoom = float(it.get("zoom") or 1.12)
            fx, fy = float(it.get("focusX") or 0.55), float(it.get("focusY") or 0.5)
            vw, vh = W * zoom, H * zoom
            left = min(max(col_w / 2 - fx * vw, col_w - vw), 0)
            top = min(max(H / 2 - fy * vh, H - vh), 0)
            seam = max(2, round(H / 540))
            body = (f'        <div class="fill" style="background-color:#0a0a0c;">'
                    f'<div style="position:absolute; top:0; height:{H}px; width:{col_w}px; left:{art_w if art_left else 0}px; overflow:hidden;">'
                    + base_v.replace("{pos}", f"width:{_n(vw)}px; height:{_n(vh)}px; left:{_n(left)}px; top:{_n(top)}px;")
                    + f'</div><div style="position:absolute; top:0; height:{H}px; width:{art_w}px; left:{0 if art_left else col_w}px; overflow:hidden;">'
                    + art + f'</div><div style="position:absolute; top:0; height:{H}px; width:{seam}px; '
                    f'left:{_n((art_w if art_left else col_w) - seam / 2)}px; background:rgba(255,255,255,0.5);"></div></div>')
        else:
            layout = it.get("layout") or "top"
            zoom, focus_y = LAYOUT.get(layout, LAYOUT["top"])
            band_h = float(it.get("bandH") or 750)
            video_h = 1920 - band_h
            band_top = 0 if layout == "top" else video_h
            video_top = band_h if layout == "top" else 0
            fade = ('<div style="position:absolute; left:0; bottom:0; width:100%; height:110px; '
                    'background:linear-gradient(180deg,rgba(10,10,12,0),rgba(10,10,12,0.75));"></div>') if layout == "top" else ""
            body = (f'        <div class="fill" style="background-color:#0a0a0c;">'
                    f'<div style="position:absolute; left:0; top:{_n(video_top)}px; width:1080px; height:{_n(video_h)}px; overflow:hidden;">'
                    + base_v.replace("{pos}", f"width:{_n(1080 * zoom)}px; height:{_n(1920 * zoom)}px; "
                                              f"left:{_n(-(1080 * (zoom - 1)) / 2)}px; top:{_n(-focus_y * zoom)}px;")
                    + f'</div><div style="position:absolute; left:0; top:{_n(band_top)}px; width:1080px; height:{_n(band_h)}px; overflow:hidden;">'
                    + art + fade + "</div></div>")
        o = {"id": f"{cid}-a", "fps": fps, "total": total}
        ctx.proj.sub(cid, FILL, body, f"          PrismaHF.layers.split(tl, {js(o)});", fonts=False)
        ctx.proj.host(cid, a, b, 8, "graphics", 15, "splitInserts", [0, 0, W, H])


def build_fade(ctx):
    fade = float(ctx.ed.get("fadeOut") or 0)
    if fade <= 0:
        return
    n = max(1, ctx.f(min(fade, ctx.N / ctx.fps / 2)))
    cid = ctx.proj.uid("fade-out")
    ctx.proj.sub(cid, f"        #{cid}-b {{ position:absolute; inset:0; background:#000; opacity:0; }}",
                 f'        <div id="{cid}-b"></div>',
                 f"          PrismaHF.layers.fade(tl, {js({'id': f'{cid}-b', 'fps': ctx.fps, 'total': n})});", fonts=False)
    ctx.proj.host(cid, ctx.N - n, ctx.N, 5, "graphics", 100, "fadeOut", [0, 0, ctx.W, ctx.H])
