"""Headline in the first seconds — longform/src/Hook.tsx and shortform Main.tsx HookInner.

Four styles (outline | card | realce | misto), always two lines balanced by
MEASURED width, size fitted to them — the template's own maths, measured in
Chrome with the same Poppins files.
"""
from __future__ import annotations

import math
from pathlib import Path

from ..project import FONT_STACK, esc, js

Z = 60
LONG = {"outline": ((800, 800), 0.095, 1.02, 0.07), "card": ((900, 900), 0.08, 1.06, 0.06),
        "realce": ((900, 900), 0.085, 1.04, 0.07), "misto": ((400, 900), 0.1, 0.98, 0.07)}
SHORT = {"outline": ((800, 800), 92, 900, 1.02, 330), "card": ((900, 900), 82, 820, 1.06, 120),
         "realce": ((900, 900), 86, 830, 1.04, 300), "misto": ((400, 900), 98, 900, 0.98, 300)}


def _n(x: float) -> str:
    return repr(float(x)) if x != int(x) else str(int(x))


def build(ctx):
    Hk = ctx.ed.get("hook") or {}
    W, H, fps, M = ctx.W, ctx.H, ctx.fps, ctx.meas
    long = ctx.fmt == "long"
    style_id = Hk.get("style") or "outline"
    raw = (Hk.get("text") or " ".join(Hk.get("lines") or [])).strip()
    text = raw.upper() if style_id == "card" else raw
    k = H / 1080 if long else 1.0
    if long:
        weights, capr, lh0, topr = LONG.get(style_id, LONG["outline"])
        ls_of = lambda size: f"{_n(-size * 0.01)}px"
    else:
        weights, cap0, safe0, lh0, top0 = SHORT.get(style_id, SHORT["outline"])
        ls_of = lambda size: "-1px"

    def hlw(t, size, wt):
        return M.width(t, size, wt, ls_of(size)) if t else 0.0

    ws = text.split()
    if len(ws) < 2:
        lines = [ws[0] if ws else "", ""]
    else:
        best, bd = [ws[0], " ".join(ws[1:])], math.inf
        for i in range(1, len(ws)):
            a, b = " ".join(ws[:i]), " ".join(ws[i:])
            d = abs(hlw(a, 100, weights[0]) - hlw(b, 100, weights[1]))
            if d < bd:
                bd, best = d, [a, b]
        lines = best

    if long:
        cap = (Hk.get("fontSizePx") or Hk.get("maxFontPx") or 0) * k or capr * H
        pad = 0.92 if style_id == "card" else 0.84 if style_id == "realce" else 1
        safe = (Hk["safeWidth"] * (W / 1920) if Hk.get("safeWidth") else W * 0.5) * pad
        mn = 40 * k
    else:
        cap = Hk.get("fontSizePx") or Hk.get("maxFontPx") or cap0
        safe = Hk.get("safeWidth") or safe0
        mn = 40
    widest = lambda size: max(hlw(lines[0], size, weights[0]), hlw(lines[1], size, weights[1]))
    size = math.floor((safe / max(1, widest(100))) * 100)
    size = min(max(math.floor((safe / max(1, widest(size))) * size), mn), cap)
    size = math.floor(size * float(Hk.get("scale") or 1))
    lh = Hk.get("lineHeight") or lh0
    accent = Hk.get("accent") or ctx.ed.get("accent") or "#ff5200"
    if long:
        top = Hk["paddingTop"] * k if Hk.get("paddingTop") is not None else topr * H
        side = Hk.get("side") or "left"
        align = {"left": "flex-start", "right": "flex-end"}.get(side, "center")
        talign = "center" if side == "center" else side
        frame = (f"justify-content:flex-start; align-items:{align}; padding-top:{_n(top)}px; "
                 f"padding-left:{_n(W * 0.04)}px; padding-right:{_n(W * 0.04)}px;")
        ls = f"{_n(-size * 0.01)}px"
    else:
        top = Hk.get("paddingTop") if Hk.get("paddingTop") is not None else top0
        align, talign = "center", "center"
        frame = f"justify-content:flex-start; align-items:center; padding-top:{_n(top)}px;"
        ls = "-1px"
        accent = "#ff5200"   # the 9:16 template hardcodes the orange for realce/misto
    shell = (f"opacity:0; text-align:{talign}; font-family:{FONT_STACK}; line-height:{_n(lh)}; "
             f"letter-spacing:{ls}; white-space:nowrap;")
    kk = lambda v: _n(v * k)
    rows = [l for l in lines if l]
    if style_id == "realce":
        inner = "".join(f'<div style="background:{accent}; color:#fff; font-weight:900; font-size:{size}px; '
                        f'padding:0.08em 0.3em 0.16em; border-radius:{kk(12)}px; '
                        f'box-shadow:0 {kk(10)}px {kk(28)}px rgba(0,0,0,0.45);">{esc(l)}</div>' for l in rows)
        body = (f'<div id="hk-e" style="{shell} display:flex; flex-direction:column; align-items:{align}; '
                f'gap:{kk(10)}px;">{inner}</div>')
    elif style_id == "misto":
        body = (f'<div id="hk-e" style="{shell} filter:drop-shadow(0 {kk(6)}px {kk(16)}px rgba(0,0,0,0.55));">'
                f'<div style="font-weight:400; font-size:{size}px; color:#fff;">{esc(lines[0])}</div>'
                f'<div style="font-weight:900; font-size:{size}px; color:{accent};">{esc(lines[1])}</div></div>')
    elif style_id == "card":
        logo_row = ""
        imgs = []
        for key, wpx, extra in (("logo", 240 if long else 300, "border-radius:{r}px; box-shadow:0 {a}px {b}px rgba(0,0,0,0.4);"),
                                ("sign", 100 if long else 128, "filter:drop-shadow(0 {a2}px {b2}px rgba(0,0,0,0.45));")):
            if Hk.get(key):
                p = ctx.pub / Hk[key]
                if not p.exists():
                    ctx.notes.append(f"hook.{key}: {Hk[key]} não existe em public/ — fora do HyperFrames")
                    continue
                src = ctx.proj.asset(p, "media")
                st = extra.format(r=kk(14 if long else 18), a=kk(12), b=kk(34), a2=kk(8), b2=kk(20))
                imgs.append(f'<img src="{src}" alt="" style="width:{kk(wpx)}px; {st}" />')
        if imgs:
            logo_row = f'<div style="display:flex; align-items:center; gap:{kk(26 if long else 34)}px;">{"".join(imgs)}</div>'
        padv, padh, rad = (24 * k, 40 * k, 22 * k) if long else (28, 46, 24)
        card = (f'<div style="background:#232326; border-radius:{_n(rad)}px; padding:{_n(padv)}px {_n(padh)}px; '
                f'text-align:{talign}; font-family:{FONT_STACK}; font-weight:900; font-size:{size}px; color:#fff; '
                f'line-height:{_n(lh)}; letter-spacing:{ls}; text-shadow:0 {kk(4)}px {kk(20)}px rgba(0,0,0,0.55); '
                f'box-shadow:0 {kk(18)}px {kk(50)}px rgba(0,0,0,0.45);">'
                + "".join(f"<div>{esc(l)}</div>" for l in rows) + "</div>")
        body = (f'<div id="hk-e" style="opacity:0; display:flex; flex-direction:column; align-items:{align}; '
                f'gap:{kk(22 if long else 28)}px;">{logo_row}{card}</div>')
    else:
        stroke = (float(Hk.get("strokePx") or 12)) * k * 0.75 if long else float(Hk.get("strokePx") or 12)
        extra = "" if long else " padding:0 60px;"
        body = (f'<div id="hk-e" style="{shell} font-weight:800; font-size:{size}px; color:#fff; '
                f'-webkit-text-stroke:{_n(stroke)}px #000; paint-order:stroke fill; '
                f'filter:drop-shadow(0 {kk(6)}px {kk(14)}px rgba(0,0,0,0.45));{extra}">'
                + "".join(f"<div>{esc(l)}</div>" for l in rows) + "</div>")
    total = ctx.f(float(Hk.get("endSec") or 4))
    cid = ctx.proj.uid("headline")
    body = body.replace('id="hk-e"', f'id="{cid}-e"')
    style = (f"        .fill {{ position:absolute; top:0; left:0; right:0; bottom:0; width:100%; height:100%; display:flex; "
             f"flex-direction:column; {frame} }}")
    ctx.proj.sub(cid, style, f'        <div class="fill">{body}</div>',
                 f"          PrismaHF.layers.hook(tl, {js({'id': f'{cid}-e', 'fps': fps, 'total': total, 'k': k})});")
    # parity box: generous rectangle around the two lines
    lw = widest(size) * 1.25 + 120 * k
    lhpx = size * float(lh) * 2 + 80 * k
    if long:
        x0 = W * 0.04 if align == "flex-start" else (W - W * 0.04 - lw if align == "flex-end" else W / 2 - lw / 2)
    else:
        x0 = W / 2 - lw / 2
    ctx.proj.host(cid, 0, total, 3, "graphics", Z, "hook", [x0 - 20, top - 20, lw + 40, lhpx + 60])
