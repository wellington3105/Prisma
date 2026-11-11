"""Karaoke captions — longform/src/Captions.tsx (16:9) and shortform Main.tsx Karaoke (9:16).

One caption LINE = one clip (`cap-NNN`), one file each, so a line can be moved or
trimmed on its track (Studio 0.8.x's caption track does not persist timing
edits — export_hyperframes.py). Grouping and fit are the template's, measured
with the same font in Chrome (measure.py), not estimated per character.
"""
from __future__ import annotations

import json
import re

from ..project import FONT_STACK, esc, js

Z = 70
_PUNCT_END = re.compile(r"[.,!?…]+$")


def clean_w(t: str) -> str:
    return _PUNCT_END.sub("", t)


def is_break(t: str) -> bool:
    return bool(re.search(r"[.,!?…]$", t))


def words(ctx) -> list[dict]:
    try:
        caps = json.loads((ctx.pub / "captions.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return caps if isinstance(caps, list) else []


def _num(x: float) -> str:
    return repr(float(x)) if x != int(x) else str(int(x))


def build_long(ctx, caps):
    C = ctx.ed.get("captions") or {}
    W, H, fps = ctx.W, ctx.H, ctx.fps
    size = H * 0.058 * float(C.get("fontScale") or 1)
    budget = W * 0.7
    ls = f"{_num(-size * 0.016)}px"
    M = ctx.meas

    def width_of(ws):
        return M.width(" ".join(clean_w(w["text"]) for w in ws), size, 900, ls)

    lines, cur = [], []
    for i, w in enumerate(caps):
        if cur and (len(cur) >= int(C.get("maxWords") or 6) or width_of(cur + [w]) > budget):
            lines.append(cur)
            cur = []
        cur.append(w)
        nxt = caps[i + 1] if i + 1 < len(caps) else None
        if is_break(w["text"]) or (nxt and nxt["startMs"] - w["endMs"] > 450):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)

    gap = size * 0.28
    hl = C.get("highlight") or None
    shadow = f"0 {_num(size * 0.06)}px {_num(size * 0.32)}px rgba(0,0,0,0.6), 0 0 {_num(size * 0.1)}px rgba(0,0,0,0.5)"
    style = (f"        .fill {{ position:absolute; top:0; left:0; right:0; bottom:0; width:100%; height:100%; display:flex; "
             f"flex-direction:column; justify-content:flex-end; align-items:center; padding-bottom:{_num(H * 0.1)}px; }}\n"
             f"        .ln {{ font-family:{FONT_STACK}; font-weight:900; font-size:{_num(size)}px; color:white; line-height:1; "
             f"letter-spacing:{ls}; white-space:nowrap; text-shadow:{shadow}; }}\n"
             f"        .w {{ display:inline-block; opacity:0; }}")
    for i, line in enumerate(lines):
        f0 = ctx.f(line[0]["startMs"] / 1000)
        nxt = ctx.f(lines[i + 1][0]["startMs"] / 1000) if i + 1 < len(lines) else ctx.N
        last_end = ctx.f(line[-1]["endMs"] / 1000) + fps
        total = max(1, min(nxt, last_end) - f0)
        widths = M.widths([{"text": clean_w(w["text"]), "size": size, "weight": 900, "letterSpacing": ls} for w in line])
        full = sum(widths) + gap * (len(line) - 1)
        fit = min(1.0, budget / full) if full else 1.0
        acc, targets = 0.0, []
        for j, wd in enumerate(widths):
            acc += wd + (gap if j else 0)
            targets.append((full - acc) / 2)
        cid = ctx.proj.uid(f"cap-{i + 1:03d}")
        spans = "".join(f'<span id="{cid}-w{j}" class="w" style="margin-right:{0 if j == len(line) - 1 else _num(gap)}px">'
                        f'{esc(clean_w(w["text"]))}</span>' for j, w in enumerate(line))
        body = (f'        <div class="fill"><div id="{cid}-l" class="ln" style="scale:{_num(fit)}">{spans}</div></div>')
        o = {"id": f"{cid}-l", "words": [f"{cid}-w{j}" for j in range(len(line))], "fps": fps, "total": total,
             "starts": [w["startMs"] / 1000 * fps - f0 for w in line], "ends": [w["endMs"] / 1000 * fps - f0 for w in line],
             "targets": targets, "fit": fit, "size": size, "highlight": hl}
        ctx.proj.sub(cid, style, body, f"          PrismaHF.layers.karaokeLong(tl, {js(o)});")
        lw = full * fit
        box = [W / 2 - lw / 2 - 4, H - H * 0.1 - size * 1.0 - size * 0.5 - 4, lw + 8, size * 1.5 + 12]
        ctx.proj.host(cid, f0, f0 + total, 4, "captions", Z, "captions", box)


def build_short(ctx, caps):
    C = ctx.ed.get("captions") or {}
    fps = ctx.fps
    max_words = int(C.get("maxWords") or 3)
    lines, cur = [], []
    for w in caps:
        cur.append(w)
        if len(cur) >= max_words or is_break(w["text"]):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    fs = float(C.get("fontSize") or 70)
    safe = float(C.get("safeWidth") or 900)
    pb = float(C.get("paddingBottom") or 0)
    wins = [[ctx.f(float(w["start"])) + 1, ctx.f(float(w["end"])) + 1, float(w["paddingBottom"])]
            for w in (C.get("windows") or [])]
    style = (f"        .fill {{ position:absolute; top:0; left:0; right:0; bottom:0; width:100%; height:100%; display:flex; "
             f"flex-direction:column; justify-content:flex-end; align-items:center; }}\n"
             f"        .ln {{ font-family:{FONT_STACK}; font-weight:900; font-size:{_num(fs)}px; color:white; line-height:1; "
             f"letter-spacing:-1px; white-space:nowrap; text-shadow:0 4px 20px rgba(0,0,0,0.55); }}\n"
             f"        .w {{ display:inline-block; opacity:0; margin-right:18px; }}")
    for i, line in enumerate(lines):
        f0 = ctx.f(line[0]["startMs"] / 1000)
        nxt = ctx.f(lines[i + 1][0]["startMs"] / 1000) if i + 1 < len(lines) else ctx.N
        total = max(1, nxt - f0)
        width = ctx.meas.width(" ".join(clean_w(w["text"]) for w in line), fs, 900, "-1px")
        fit = min(1.0, safe / width) if width else 1.0
        cid = ctx.proj.uid(f"cap-{i + 1:03d}")
        spans = "".join(f'<span id="{cid}-w{j}" class="w">{esc(clean_w(w["text"]))}</span>' for j, w in enumerate(line))
        body = (f'        <div id="{cid}-s" class="fill" style="padding-bottom:{_num(pb)}px">'
                f'<div class="ln" style="scale:{_num(fit)}">{spans}</div></div>')
        o = {"shell": f"{cid}-s", "words": [f"{cid}-w{j}" for j in range(len(line))], "fps": fps, "total": total,
             "from": f0, "starts": [w["startMs"] / 1000 * fps - f0 for w in line], "paddingBottom": pb, "windows": wins}
        ctx.proj.sub(cid, style, body, f"          PrismaHF.layers.karaokeShort(tl, {js(o)});")
        lw = (width + 18 * len(line)) * fit
        box = [ctx.W / 2 - lw / 2 - 4, ctx.H - pb - fs * 1.6 - 4, lw + 8, fs * 1.6 + 40]
        ctx.proj.host(cid, f0, f0 + total, 4, "captions", Z, "captions", box)


def build(ctx):
    caps = words(ctx)
    if not caps:
        ctx.notes.append("legenda ligada mas captions.json vazio — nenhuma linha")
        return
    (build_long if ctx.fmt == "long" else build_short)(ctx, caps)
