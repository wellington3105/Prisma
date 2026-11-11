"""Keyword cards — GlassCard.tsx `prism` (the default) and `pill`, both formats.

The card enters at `at + offsetS` (offsetS default 0.8 — the karaoke caption has
moved on by then: text REINFORCES, never duplicates) and stays `dur` (3.2).
Sizes follow the template per format (9:16: a share of the WIDTH; 16:9: of the
HEIGHT). 9:16 passes no font family to the cards, so they inherit the page font
exactly as in Remotion.
"""
from __future__ import annotations

from ..project import FONT_STACK, esc, js


def _n(x: float) -> str:
    return repr(float(x)) if x != int(x) else str(int(x))


def build(ctx):
    hl = ctx.ed.get("highlights") or {}
    variant = hl.get("variant") or "prism"
    long = ctx.fmt == "long"
    W, H, fps = ctx.W, ctx.H, ctx.fps
    Z = 90 if long else 50   # longform paints the cards last; shortform below hook/captions
    fam = hl.get("fontFamily")
    font = f"font-family:{FONT_STACK};" if long and not fam else (f"font-family:{fam};" if fam else "")
    delay = ctx.f(float(hl.get("offsetS", 0.8) if hl.get("offsetS") is not None else 0.8))
    for i, h in enumerate(hl.get("items") or []):
        text = str(h.get("text") or "")
        total = ctx.f(float(h.get("dur") or 3.2))
        f0 = ctx.f(float(h["at"])) + delay
        cid = ctx.proj.uid(f"card-{h.get('id') or i + 1}")
        tilt = float(h.get("tilt") if h.get("tilt") is not None else (0 if variant == "prism" else -2))
        if variant == "prism":
            exc = max(1.0, len(text) / 16)
            size = ((H * 0.056) if long else (W * 0.052)) / exc * float(h.get("scale") or 1)
            R = size * 0.62
            x = h.get("x") if h.get("x") is not None else (0.26 if long else 0.5)
            y = h.get("y") if h.get("y") is not None else (0.32 if long else 0.3)
            accent = h.get("accent") or "#ff5200"
            tz = -14 if long else -18
            label = ""
            if h.get("label"):
                label = (f'<div style="display:flex; align-items:center; gap:{_n(size * 0.28)}px; margin-bottom:{_n(size * 0.16)}px;">'
                         f'<div style="width:{_n(size * 0.9)}px; height:3px; border-radius:2px; background:{accent}; '
                         f'box-shadow:0 0 12px {accent};"></div>'
                         f'<div style="font-size:{_n(size * 0.46)}px; font-weight:600; letter-spacing:{_n(size * 0.09)}px; '
                         f'color:rgba(255,255,255,0.86); text-transform:uppercase;">{esc(h["label"])}</div></div>')
            sweeps = "".join(
                f'<div id="{cid}-c-s{j + 1}" style="position:absolute; top:-40%; bottom:-40%; left:-140%; width:45%; '
                f'transform:rotate(18deg); background:linear-gradient(90deg, transparent, rgba(255,255,255,{a}), transparent); '
                f'mix-blend-mode:screen;"></div>' for j, a in enumerate((0.5, 0.22)))
            body = (
                f'        <div class="fill" style="pointer-events:none; perspective:1500px;">'
                f'<div id="{cid}-c" style="position:absolute; left:{_n(x * 100)}%; top:{_n(y * 100)}%; opacity:0; '
                f'transform-style:preserve-3d; max-width:{"40%" if long else "82%"};">'
                f'<div style="position:absolute; inset:0; border-radius:{_n(R)}px; transform:translateZ({tz}px); '
                f'background:linear-gradient(160deg, rgba(255,255,255,0.18), rgba(255,255,255,0.03)); '
                f'border:1px solid rgba(255,255,255,0.18); box-shadow:0 50px 90px rgba(0,0,0,0.5);"></div>'
                f'<div style="position:relative; border-radius:{_n(R)}px; '
                f'box-shadow:-3px 0 14px rgba(255,50,110,0.22), 3px 0 14px rgba(50,150,255,0.24);">'
                f'<div id="{cid}-c-rim" style="position:absolute; inset:0; padding:2.5px; border-radius:{_n(R)}px; '
                f'-webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); '
                f'-webkit-mask-composite:xor; mask-composite:exclude; z-index:2;"></div>'
                f'<div style="position:relative; overflow:hidden; border-radius:{_n(R)}px; '
                f'padding:{_n(size * 0.5)}px {_n(size * 0.95)}px {_n(size * 0.58)}px; '
                f'backdrop-filter:blur(16px) saturate(1.5) brightness(1.06); -webkit-backdrop-filter:blur(16px) saturate(1.5) brightness(1.06); '
                f'background:linear-gradient(135deg, rgba(255,255,255,0.26) 0%, rgba(255,255,255,0.07) 42%, rgba(14,18,28,0.42) 100%); '
                f'box-shadow:inset 0 2px 0 rgba(255,255,255,0.65), inset 0 -2px 0 rgba(0,0,0,0.35), inset 0 0 30px rgba(255,255,255,0.10); '
                f'white-space:nowrap; {font} text-align:left;">'
                f'{sweeps}{label}'
                f'<div style="position:relative; font-size:{_n(size * 1.22)}px; font-weight:800; line-height:1.04; '
                f'letter-spacing:0.5px; color:#fff; text-shadow:-1.5px 0 rgba(255,60,110,0.45), 1.5px 0 rgba(60,170,255,0.45), '
                f'0 4px 22px rgba(0,0,0,0.45);">{esc(text)}</div>'
                f'</div></div></div></div>')
            o = {"id": f"{cid}-c", "fps": fps, "total": total, "tilt": tilt}
            script = f"          PrismaHF.layers.prism(tl, {js(o)});"
            bw = min(W * (0.4 if long else 0.82), size * (1.22 * 0.62 * max(len(text), len(h.get('label') or '') * 0.6) + 2.4))
            bh = size * (1.22 * 1.04 + 1.08 + (0.62 if h.get("label") else 0))
        else:  # pill
            exc = max(1.0, len(text) / 12)
            size = ((H * 0.05) if long else (W * 0.046)) / exc * float(h.get("scale") or 1)
            x = h.get("x") if h.get("x") is not None else (0.74 if long else 0.72)
            y = h.get("y") if h.get("y") is not None else 0.24
            accent = h.get("accent") or "#7fd4ff"
            dark = h.get("dark", True) is not False
            label = ""
            if h.get("label"):
                label = (f'<div style="font-size:{_n(size * 0.58)}px; font-weight:600; letter-spacing:3px; color:{accent}; '
                         f'margin-bottom:{_n(size * 0.18)}px; text-transform:uppercase;">{esc(h["label"])}</div>')
            body = (
                f'        <div class="fill" style="justify-content:flex-start; align-items:center; pointer-events:none;">'
                f'<div id="{cid}-c" style="position:absolute; left:{_n(x * 100)}%; top:{_n(y * 100)}%; opacity:0; '
                f'backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px); '
                f'background:{"rgba(12,17,28,0.62)" if dark else "rgba(255,255,255,0.58)"}; '
                f'border:2px solid {"rgba(255,255,255,0.22)" if dark else "rgba(255,255,255,0.75)"}; '
                f'border-radius:{_n(size * 1.5)}px; padding:{_n(size * 0.52)}px {_n(size * 1.1)}px; '
                f'box-shadow:0 28px 70px rgba(0,0,0,0.35); text-align:center; white-space:nowrap; '
                f'max-width:{"40%" if long else "52%"}; {font}">'
                f'{label}<div style="font-size:{_n(size * 1.15)}px; font-weight:700; line-height:1.08; letter-spacing:0.5px; '
                f'color:{"#fff" if dark else "#0c111c"};">{esc(text)}</div></div></div>')
            o = {"id": f"{cid}-c", "fps": fps, "total": total, "tilt": tilt}
            script = f"          PrismaHF.layers.pill(tl, {js(o)});"
            bw = min(W * (0.4 if long else 0.52), size * (1.15 * 0.62 * len(text) + 2.4))
            bh = size * (1.15 * 1.08 + 1.04 + (0.76 if h.get("label") else 0))
        style = ("        .fill { position:absolute; top:0; left:0; right:0; bottom:0; width:100%; height:100%; "
                 "display:flex; flex-direction:column; }")
        ctx.proj.sub(cid, style, body, script)
        cx, cy = float(x) * W, float(y) * H
        box = [cx - bw / 2 - 30, cy - bh / 2 - 30, bw + 60, bh + 60]
        ctx.proj.host(cid, f0, f0 + total, 5, "graphics", Z, "highlights", box)
