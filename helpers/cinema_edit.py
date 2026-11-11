"""Cinema-motion edit: plan → per-shot plates (retime 24p/180° + film look + light VFX)
→ HyperFrames project (grain, veil, typography, HUD) → narrative audio mix.

The BMAD "Cinema-VFX-Motion" pack's assembly stage. Differences from beat_edit.py:
  * cadence is a plan property (24 fps default) with integer-frame shot boundaries
  * the MUSIC can be edited by bars (segments + crossfade) and automated
    (low-pass sweeps, gain/duck, silence windows) — rendered offline into one mix
  * every shot goes through speed_ramp.py (even 1.0x: it carries the 180° shutter)
    and film_look.py (halation/bloom/streaks/sweep/light-hit/print curve/hue fixes)
  * restraint is data: transitions/fx are listed per shot; nothing is automatic
  * screen-space layers: film grain (constant), "Pista" veil, vignette
  * brand typography (variable Archivo) with drawn HUD callouts, a target, end card

plan (paths relative to the plan file):
{
  "fps": 24, "shutter": 180, "size": "1080x1920",
  "music": "audio/track.mp3", "beats": "beats_24.json",
  "segments": [{"from": 56, "to": 92}, {"from": 108, "to": 136, "tail": 1.2}], "xfade_ms": 120,
  "takes_dir": "graded_v2", "stab_dir": "hyperframes_v2/assets/stab",
  "look": {"halation": .25, "bloom": .15, "curve": .6, "hue_fix": [...]},          # global
  "grain": {"amount": 0.10, "size": 1.0}, "veil": true, "vignette": 0.12,
  "fonts": {"archivo": "fonts/Archivo-variable.ttf"}, "monogram": "fonts/wb-monogram.svg",
  "shots": [{"take": "113411", "in": 1.9, "from": 56, "to": 58, "speed": 0.5 | "curve": "0:1,1:0.25",
             "reverse_to": 2.9, "look": {...}, "streaks": 0.7, "sweep": {...}, "hit": true,
             "push": [1.0, 1.08], "transition": "cut|whip-left|whip-right", "match": "prev",
             "black_end": 4}],
  "graphics": [{"type": "statement|title|cota|target|endcard", ...beats in TRACK numbering}],
  "audio": {"lpf": [[b0, b1, f0, f1]], "gain": [[b, dB]], "silence": [[b0, b1]],
            "cues": [{"at": b, "sfx": "sub_drop", "db": -2, "align": "start|end"}],
            "beds": [{"sfx": "room_tone", "from": b0, "to": b1, "db": -38}],
            "fade_out": 0.8, "sfx_dir": "sfx_cinema"}
}
All "beats" (from/to/at) are TRACK beat numbers (fractional allowed, e.g. 63.5);
the segment map turns them into video time.

Usage:
  python helpers/cinema_edit.py plan_v3.json -o edit/hyperframes_v3 [--interp mci|blend] [--only-audio]
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import butter, sosfilt

HERE = Path(__file__).resolve().parent
SR = 48000


def load_mod(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ time ----
class Timeline:
    def __init__(self, beats, segments, fps):
        self.b, self.segs, self.fps = beats, segments, fps
        self.off = []
        acc = 0.0
        for s in segments:
            self.off.append(acc)
            acc += self.bt(s["to"]) - self.bt(s["from"])
        self.music_len = acc
        self.total = acc + segments[-1].get("tail", 0.0)

    def bt(self, bf: float) -> float:
        """track time of a (fractional) beat number."""
        i = int(math.floor(bf)); f = bf - i
        i = max(0, min(i, len(self.b) - 2))
        return self.b[i] + f * (self.b[i + 1] - self.b[i])

    def vt(self, bf: float) -> float:
        for k, s in enumerate(self.segs):
            if s["from"] - 1e-6 <= bf <= s["to"] + 1e-6:
                return self.off[k] + self.bt(bf) - self.bt(s["from"])
        if bf > self.segs[-1]["to"]:
            return self.off[-1] + self.bt(self.segs[-1]["to"]) - self.bt(self.segs[-1]["from"]) + (self.bt(bf) - self.bt(self.segs[-1]["to"]))
        raise ValueError(f"beat {bf} is not inside any music segment")

    def frame(self, bf: float) -> int:
        return int(round(self.vt(bf) * self.fps))


# --------------------------------------------------------------- shots ------
def probe_dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip() or 0)


def key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def run(cmd):
    r = subprocess.run(cmd, cwd=str(HERE.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"failed: {' '.join(map(str, cmd[:4]))}…\n{r.stderr[-1500:]}")
    return r.stdout.strip()


def bright_line_row(frame: np.ndarray) -> float | None:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    prof = (g > 0.8).mean(1)
    prof = np.convolve(prof, np.ones(9) / 9, mode="same")
    return float(np.argmax(prof)) if prof.max() > 0.02 else None


def edge_frame(p: Path, last: bool) -> np.ndarray:
    cap = cv2.VideoCapture(str(p)); n = int(cap.get(7))
    cap.set(1, max(0, n - 1) if last else 0); ok, f = cap.read()
    return f


# ----------------------------------------------------------- HyperFrames ----
def comp(cid, body, style, js, W, H, fonts_css=""):
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head><meta charset="UTF-8"></head>
  <body>
    <template>
      <style>
        {fonts_css}
        #root {{ position: absolute; inset: 0; overflow: hidden; }}
{style}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}">
{body}
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
          {(chr(10) + "          ").join(js)}
          window.__timelines["{cid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""


FONT_CSS = ('@font-face {{ font-family: "Archivo"; src: url("assets/fonts/{f}") format("truetype"); '
            'font-weight: 100 900; font-stretch: 62% 125%; font-display: block; }}')
VOICE = {  # Sally §2.5 — Archivo voices. SINGLE quotes only: these go inside style="…"
    "thesis": "font-family:'Archivo',sans-serif;font-variation-settings:'wdth' 62,'wght' 720;font-stretch:62%;font-weight:720;text-transform:uppercase;letter-spacing:-0.01em;",
    "statement": "font-family:'Archivo',sans-serif;font-variation-settings:'wdth' 100,'wght' 300;font-weight:300;",
    "label": "font-family:'Archivo',sans-serif;font-variation-settings:'wdth' 75,'wght' 650;font-stretch:75%;font-weight:650;text-transform:uppercase;letter-spacing:0.15em;font-variant-numeric:tabular-nums;",
    "signature": "font-family:'Archivo',sans-serif;font-variation-settings:'wdth' 125,'wght' 500;font-stretch:125%;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;",
}
EASE = '"expo.out"'
WHITE, STEEL, YELLOW = "#F4F4F2", "#A0A4A9", "#F4C300"


def counter_js(el_id, v0, v1, decimals, dur, at, ease="power3.out", comma=True):
    """seek-safe count-up: a proxy tweened on the paused timeline writes the text."""
    # decimal comma built from char codes: replace(".", ",") showed a dot mid-count in renders
    if comma and decimals:
        fmt = (f'(function(s){{ const p=s.split(String.fromCharCode(46)); '
               f'return p[0]+String.fromCharCode(44)+p[1]; }})(o.v.toFixed({decimals}))')
    else:
        fmt = f'o.v.toFixed({decimals})'
    return ('(function(){ const o={v:%s}; const el=document.getElementById("%s"); const w=()=>{ el.textContent=%s; }; w(); '
            'tl.fromTo(o, {v:%s}, {v:%s, duration:%s, ease:"%s", onUpdate:w, immediateRender:false}, %.3f); })();'
            % (v0, el_id, fmt, v0, v1, dur, ease, at))


def cota(g, cid, fps, body, shadow, out_at):
    """Data with motion: the leader line DRAWS to the anchor, label and value reveal
    from a mask (shutter), the number counts up (or punches in), optional arc draws."""
    x, y = g["x"], g["y"]
    free = "anchor" not in g   # no anchor: a short rule draws under the value and stays with the text
    if free:
        ax, ay = x + g.get("rule", 140), y + 116
        L, ang = float(g.get("rule", 140)), 0.0
    else:
        ax, ay = g["anchor"]
        L = math.hypot(ax - x, ay - (y + 100)); ang = math.degrees(math.atan2(ay - (y + 100), ax - x))
    draw = 8 / fps
    js = []
    scrim = g.get("scrim")   # soft local shade for cards over bright floor/walls (label contrast)
    if scrim:
        body.append(f'<div id="s-{cid}" style="position:absolute;left:0;top:{y - 110}px;width:1080px;height:340px;opacity:0;'
                    f'background:radial-gradient(ellipse 60% 50% at 30% 50%, rgba(0,0,0,{float(scrim):.2f}), rgba(0,0,0,0) 100%)"></div>')
        js.append(f'tl.fromTo("#s-{cid}", {{opacity:0}}, {{opacity:1, duration:0.4, ease:"power1.out", immediateRender:false}}, 0.0);')
    body.append(f'<div style="position:absolute;left:{x}px;top:{y}px;overflow:hidden;height:40px;width:820px">'
                f'<div id="a-{cid}" style="color:{STEEL};font-size:30px;{VOICE["label"]}{shadow}transform:translateY(110%)">{g["label"]}</div></div>')
    num = g.get("num")
    counting = num is not None and g.get("count")
    # only a COUNTING number needs its own span; a punched value animates the whole line
    # (an inline-block span measured rendering AFTER its text: "MOTORES ELÉTRICOS2")
    val = (f'<span id="n-{cid}">{num}</span>{g.get("rest", "")}' if counting
           else (f'{num}{g.get("rest", "")}' if num is not None else g["value"]))
    body.append(f'<div style="position:absolute;left:{x}px;top:{y + 36}px;overflow:hidden;height:74px;width:920px">'
                f'<div id="b-{cid}" style="color:{WHITE};font-size:56px;line-height:74px;{VOICE["label"]}letter-spacing:0.06em;{shadow}'
                f'transform:translateY(105%)">{val}</div></div>')
    body.append(f'<div id="k-{cid}" style="position:absolute;left:{x}px;top:{y + (116 if free else 100)}px;width:{L:.0f}px;height:{3 if free else 1.5}px;'
                f'background:{YELLOW if free else WHITE};transform-origin:0 50%;transform:rotate({ang:.2f}deg) scaleX(0)"></div>')
    body.append(f'<div id="d-{cid}" style="position:absolute;left:{ax - 7}px;top:{ay - 7}px;width:14px;height:14px;border-radius:50%;'
                f'border:1.5px solid {WHITE};opacity:0;display:{"none" if free else "block"}"></div>')
    targets = [f'"#a-{cid}"', f'"#b-{cid}"', f'"#k-{cid}"', f'"#d-{cid}"']
    keep = [f'"#a-{cid}"', f'"#b-{cid}"'] + ([f'"#s-{cid}"'] if scrim else [])
    if scrim:
        targets.append(f'"#s-{cid}"')
    if g.get("arc") and not free:
        r = g["arc"].get("r", 150); per = math.pi * r
        body.append(f'<svg style="position:absolute;left:{ax - r - 10}px;top:{ay - r - 10}px" width="{2 * r + 20}" height="{r + 20}">'
                    f'<path id="c-{cid}" d="M 10 {r + 10} A {r} {r} 0 0 1 {2 * r + 10} {r + 10}" fill="none" stroke="{WHITE}" '
                    f'stroke-width="1.5" stroke-dasharray="{per:.1f}" stroke-dashoffset="{per:.1f}" opacity="0.85"/></svg>')
        js.append('tl.fromTo("#c-%s", {attr:{"stroke-dashoffset":%.1f}}, {attr:{"stroke-dashoffset":0}, duration:0.7, ease:"power2.out", immediateRender:false}, %.3f);'
                  % (cid, per, draw))
        targets.append(f'"#c-{cid}"')
    js += [f'tl.fromTo("#k-{cid}", {{scaleX:0, rotation:{ang:.2f}}}, {{scaleX:1, rotation:{ang:.2f}, duration:{draw:.3f}, ease:"power2.out", immediateRender:false}}, 0.02);',
           f'tl.fromTo("#d-{cid}", {{opacity:0, scale:0.3}}, {{opacity:1, scale:1, duration:0.3, ease:{EASE}, immediateRender:false}}, {draw:.3f});',
           f'tl.fromTo("#a-{cid}", {{y:"110%"}}, {{y:"0%", duration:0.7, ease:{EASE}, immediateRender:false}}, {draw:.3f});',
           f'tl.fromTo("#b-{cid}", {{y:"105%"}}, {{y:"0%", duration:0.75, ease:{EASE}, immediateRender:false}}, {draw + 0.12:.3f});']
    if num is not None:
        c = g.get("count")
        if c:
            v1 = float(str(num).replace(",", "."))
            js.append(counter_js(f"n-{cid}", c.get("from", 0), v1, int(c.get("decimals", 0)), c.get("dur", 0.7), draw + 0.1))
        if g.get("punch"):
            js.append(f'tl.fromTo("#b-{cid}", {{scale:1.18, transformOrigin:"0% 60%"}}, {{scale:1, duration:0.45, ease:{EASE}, immediateRender:false}}, {draw + 0.08:.3f});')
    a_out = g.get("_anchor_out")
    if a_out is not None and a_out < out_at:
        anchored = [t for t in targets if t not in keep]
        js.append(f'tl.to([{",".join(anchored)}], {{opacity:0, duration:0.2, ease:"power1.in"}}, {max(0.1, a_out - 0.2):.3f});')
        targets = keep
    js.append(f'tl.to([{",".join(targets)}], {{opacity:0, duration:0.35, ease:"power1.in"}}, {out_at:.3f});')
    return js


def target(g, cid, body, shadow, out_at):
    """0–100: a speed counter runs 0→100 km/h with a filling bar (the measurement),
    then the time PUNCHES in while the yellow corners close on the car."""
    x0, y0, x1, y1 = g["box"]; c = 46
    for cx, cy, bt_, bl in [(x0, y0, "top", "left"), (x1 - c, y0, "top", "right"),
                            (x0, y1 - c, "bottom", "left"), (x1 - c, y1 - c, "bottom", "right")]:
        body.append(f'<div class="q-{cid}" style="position:absolute;left:{cx}px;top:{cy}px;width:{c}px;height:{c}px;'
                    f'border-{bt_}:3px solid {YELLOW};border-{bl}:3px solid {YELLOW};opacity:0"></div>')
    tx, ty = g["tx"], g["ty"]
    body.append(f'<div id="a-{cid}" style="position:absolute;left:{tx}px;top:{ty}px;color:{STEEL};font-size:30px;{VOICE["label"]}{shadow}opacity:0">'
                f'0–<span id="s-{cid}">0</span> KM/H</div>')
    body.append(f'<div id="bar-{cid}" style="position:absolute;left:{tx}px;top:{ty + 44}px;width:360px;height:3px;background:rgba(244,244,242,.25);opacity:0">'
                f'<div id="f-{cid}" style="width:100%;height:100%;background:{YELLOW};transform:scaleX(0);transform-origin:0 50%"></div></div>')
    body.append(f'<div id="b-{cid}" style="position:absolute;left:{tx}px;top:{ty + 64}px;color:{WHITE};font-size:112px;line-height:1;{VOICE["thesis"]}{shadow}'
                f'text-transform:none;opacity:0;transform-origin:0 60%">{g["value"]}</div>')  # units stay lowercase: 3,7 s
    run_ = g.get("run", 0.6)
    js = ['gsap.utils.toArray(".q-%s").forEach((q, i) => { tl.fromTo(q, {opacity:0, x:(i %% 2 ? 60 : -60), y:(i < 2 ? -60 : 60)}, '
          '{opacity:1, x:0, y:0, duration:0.5, ease:%s, immediateRender:false}, 0.02); });' % (cid, EASE),
          f'tl.fromTo(["#a-{cid}","#bar-{cid}"], {{opacity:0}}, {{opacity:1, duration:0.25, ease:{EASE}, immediateRender:false}}, 0.05);',
          counter_js(f"s-{cid}", 0, 100, 0, run_, 0.1, ease="power2.in", comma=False),
          f'tl.fromTo("#f-{cid}", {{scaleX:0}}, {{scaleX:1, duration:{run_}, ease:"power2.in", immediateRender:false}}, 0.1);',
          f'tl.fromTo("#b-{cid}", {{opacity:0, scale:1.4}}, {{opacity:1, scale:1, duration:0.4, ease:{EASE}, immediateRender:false}}, {0.1 + run_:.3f});',
          ]
    a_out = g.get("_anchor_out")
    if a_out is not None and a_out < out_at:
        js.append(f'tl.to(".q-{cid}", {{opacity:0, duration:0.2, ease:"power1.in"}}, {max(0.1, a_out - 0.2):.3f});')
        js.append(f'tl.to(["#a-{cid}","#b-{cid}","#bar-{cid}"], {{opacity:0, duration:0.35, ease:"power1.in"}}, {out_at:.3f});')
    else:
        js.append(f'tl.to([".q-{cid}","#a-{cid}","#b-{cid}","#bar-{cid}"], {{opacity:0, duration:0.35, ease:"power1.in"}}, {out_at:.3f});')
    return js


def graphic(g, cid, dur, fps, W, H, font_file):
    css = FONT_CSS.format(f=font_file)
    js, body, style = [], [], []
    shadow = "text-shadow:0 2px 24px rgba(0,0,0,.55);"
    out_at = max(0.4, dur - 0.3)
    t = g["type"]
    if t == "statement":
        body.append(f'<div id="s-{cid}" style="position:absolute;left:{g.get("x", 72)}px;top:{g["y"]}px;width:{g.get("w", 830)}px;'
                    f'color:{WHITE};font-size:{g.get("size", 86)}px;line-height:1;{VOICE["statement"]}{shadow}opacity:0">{g["text"]}</div>')
        js += [f'tl.fromTo("#s-{cid}", {{opacity:0, y:14}}, {{opacity:1, y:0, duration:0.55, ease:{EASE}, immediateRender:false}}, 0.02);',
               f'tl.to("#s-{cid}", {{opacity:0, duration:0.3, ease:"power1.in"}}, {out_at:.3f});']
    elif t == "title":
        size = g.get("size", 150)
        body.append(f'<div id="t-{cid}" style="position:absolute;left:0;right:0;top:{g["y"]}px;text-align:center;color:{WHITE};'
                    f'font-size:{size}px;line-height:1;{VOICE["thesis"]}{shadow}opacity:0">{g["text"]}</div>')
        body.append(f'<div id="l-{cid}" style="position:absolute;top:{g["y"] + size + 18}px;left:50%;width:{g.get("line_w", 420)}px;'
                    f'margin-left:-{g.get("line_w", 420) // 2}px;height:1.5px;background:{WHITE};transform:scaleX(0);transform-origin:0 50%"></div>')
        if g.get("sub"):
            body.append(f'<div id="u-{cid}" style="position:absolute;left:0;right:0;top:{g["y"] + size + 40}px;text-align:center;color:{STEEL};'
                        f'font-size:30px;{VOICE["label"]}opacity:0">{g["sub"]}</div>')
        js += [f'tl.fromTo("#l-{cid}", {{scaleX:0}}, {{scaleX:1, duration:{8 / fps:.3f}, ease:"power2.out", immediateRender:false}}, 0.02);',
               f'tl.fromTo("#t-{cid}", {{opacity:0, y:18}}, {{opacity:1, y:0, duration:0.6, ease:{EASE}, immediateRender:false}}, {8 / fps:.3f});']
        if g.get("sub"):
            js.append(f'tl.fromTo("#u-{cid}", {{opacity:0}}, {{opacity:1, duration:0.4, ease:{EASE}, immediateRender:false}}, {8 / fps + 0.2:.3f});')
        sel = f'"#t-{cid}","#l-{cid}"' + (f',"#u-{cid}"' if g.get("sub") else "")
        js.append(f'tl.to([{sel}], {{opacity:0, duration:0.3, ease:"power1.in"}}, {out_at:.3f});')
    elif t in ("label", "tag"):
        body.append(f'<div id="g-{cid}" style="position:absolute;left:{g.get("x", 72)}px;top:{g["y"]}px;color:{g.get("color", STEEL)};'
                    f'font-size:{g.get("size", 24)}px;{VOICE["label"]}{shadow}opacity:0">{g["text"]}</div>')
        js += [f'tl.fromTo("#g-{cid}", {{opacity:0}}, {{opacity:1, duration:0.4, ease:{EASE}, immediateRender:false}}, 0.02);',
               f'tl.to("#g-{cid}", {{opacity:0, duration:0.3, ease:"power1.in"}}, {out_at:.3f});']
    elif t == "cota":
        js += cota(g, cid, fps, body, shadow, out_at)
    elif t == "target":
        js += target(g, cid, body, shadow, out_at)
    elif t == "endcard":
        # end card = the CLIENT's mark (the store), not the editor's
        body.append(f'<div id="t-{cid}" style="position:absolute;left:0;right:0;top:{g.get("y", 380)}px;text-align:center;color:{WHITE};'
                    f'font-size:150px;line-height:1;{VOICE["thesis"]}{shadow}opacity:0">{g["text"]}</div>')
        items = [f'"#t-{cid}"']
        if g.get("logo"):
            lw = g.get("logo_w", 360); ly = g.get("logo_y", 1180)
            body.append(f'<div id="lb-{cid}" style="position:absolute;left:0;right:0;top:{ly - 90}px;height:{g.get("logo_h", 300) + 180}px;opacity:0;'
                        f'background:linear-gradient(180deg, rgba(11,12,13,0), rgba(11,12,13,.55) 35%, rgba(11,12,13,.55) 65%, rgba(11,12,13,0))"></div>')
            body.append(f'<img id="m-{cid}" src="assets/fonts/{Path(g["logo"]).name}" style="position:absolute;left:50%;top:{ly}px;'
                        f'width:{lw}px;margin-left:-{lw // 2}px;opacity:0">')
            items += [f'"#lb-{cid}"', f'"#m-{cid}"']
        if g.get("signature"):
            sy = g.get("sy", 1380)
            body.append(f'<div id="s-{cid}" style="position:absolute;left:0;right:0;top:{sy}px;text-align:center;color:{WHITE};'
                        f'font-size:28px;{VOICE["signature"]}text-shadow:0 0 14px rgba(0,0,0,.8);opacity:0">{g["signature"]}</div>')
            items.append(f'"#s-{cid}"')
        js += [f'tl.fromTo("#t-{cid}", {{opacity:0, y:18}}, {{opacity:1, y:0, duration:0.8, ease:{EASE}, immediateRender:false}}, 0.05);']
        if len(items) > 1:
            js.append(f'tl.fromTo([{",".join(items[1:])}], {{opacity:0, y:10}}, {{opacity:1, y:0, duration:0.8, ease:{EASE}, stagger:0.12, immediateRender:false}}, 0.6);')
    return comp(cid, "\n".join("        " + b for b in body), "\n".join(style), js, W, H, css)


def whip_axis(tr, W, H):
    d = tr.split("-")[1]
    axis = "x" if d in ("left", "right") else "y"
    sign = -1 if d in ("left", "up") else 1
    return axis, sign, (W if axis == "x" else H) * 0.14, ("80 0" if axis == "x" else "0 80")


def shot_comp(cid, asset, dur, fps, s, tr_out, W, H, match_dy):
    js, extra = [], ""
    T = 0.2
    whip_in = s.get("transition", "cut").startswith("whip-")
    whip_out = tr_out.startswith("whip-")
    base_scale = 1.0 + (abs(match_dy) * 2 / H + 0.012 if match_dy else 0)
    js.append(f'tl.set("#cam-{cid}", {{x:0, y:0, rotation:0}}, 0);')
    js.append(f'tl.set("#push-{cid}", {{scale:{s.get("push", [1, 1])[0]}}}, 0);')
    js.append(f'tl.set("#v-{cid}", {{x:0, y:{match_dy:.1f}, scale:{base_scale:.4f}, filter:"{"url(#blur-" + cid + ")" if (whip_in or whip_out) else "none"}"}}, 0);')
    if s.get("push"):
        p0, p1 = s["push"]
        js.append(f'tl.fromTo("#push-{cid}", {{scale:{p0}}}, {{scale:{p1}, duration:{dur:.3f}, ease:"none", immediateRender:false}}, 0);')
    if s.get("hit"):
        kf = ",".join("{x:%s, y:%.1f}" % (dx, -dx * 0.6) for dx in [6, -4, 2.5, -1.2, 0])
        js.append('tl.to("#cam-%s", {keyframes:[%s], duration:%.4f, ease:"none"}, 0);' % (cid, kf, 5 / fps))  # one tween: no overlaps
    if whip_in:
        axis, sign, dist, blur = whip_axis(s["transition"], W, H)
        js.append(f'tl.fromTo("#v-{cid}", {{{axis}:{-sign * dist:.0f}, scale:{base_scale * 1.3:.3f}}}, {{{axis}:{0 if axis == "x" else match_dy:.1f}, scale:{base_scale:.4f}, duration:{T}, ease:"power3.out", immediateRender:false}}, 0);')
        js.append(f'tl.fromTo("#bb-{cid}", {{attr:{{stdDeviation:"{blur}"}}}}, {{attr:{{stdDeviation:"0 0"}}, duration:{T}, ease:"power3.out", immediateRender:false}}, 0);')
    if whip_out:
        axis, sign, dist, blur = whip_axis(tr_out, W, H)
        js.append(f'tl.to("#v-{cid}", {{{axis}:{sign * dist:.0f}, scale:{base_scale * 1.3:.3f}, duration:{T}, ease:"power2.in"}}, {dur - T:.3f});')
        js.append(f'tl.fromTo("#bb-{cid}", {{attr:{{stdDeviation:"0 0"}}}}, {{attr:{{stdDeviation:"{blur}"}}, duration:{T}, ease:"power2.in", immediateRender:false}}, {dur - T:.3f});')
    if s.get("black_end"):
        nb = int(s["black_end"])
        extra += f'\n          <div id="k-{cid}" style="position:absolute;inset:0;background:#000;opacity:0"></div>'
        js.append(f'tl.set("#k-{cid}", {{opacity:1}}, {dur - nb / fps:.4f});')
    body = f"""        <svg width="0" height="0" style="position:absolute" aria-hidden="true">
          <filter id="blur-{cid}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur id="bb-{cid}" stdDeviation="0 0"/></filter>
        </svg>
        <div id="cam-{cid}" class="layer"><div id="push-{cid}" class="layer">
          <video id="v-{cid}" class="clip" src="{asset}" data-start="0" data-duration="{dur}" data-media-start="0" data-track-index="0" muted playsinline></video>
        </div></div>{extra}"""
    style = """        #root { background: #000; }
        .layer { position: absolute; inset: 0; transform-origin: 50% 50%; }
        video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 50% 50%; }"""
    return comp(cid, body, style, js, W, H)


# ----------------------------------------------------------------- audio ----
def read_audio(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, "<i2").reshape(-1, 2).astype(np.float32) / 32768


def write_wav(p: Path, x: np.ndarray) -> None:
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def build_audio(plan, tl: Timeline, base: Path, out_wav: Path) -> dict:
    au = plan.get("audio", {})
    music = read_audio(base / plan["music"])
    xf = int(plan.get("xfade_ms", 120) / 1000 * SR)
    total = int(round(tl.total * SR))
    mix_m = np.zeros((total + SR, 2), np.float32)
    for k, s in enumerate(tl.segs):
        a = int(round(tl.bt(s["from"]) * SR)) - (xf // 2 if k else 0)
        b = int(round(tl.bt(s["to"]) * SR)) + (xf // 2 if k < len(tl.segs) - 1 else int(s.get("tail", 0) * SR))
        seg = music[max(0, a):b].copy()
        if k:
            seg[:xf] *= np.sin(np.linspace(0, np.pi / 2, xf))[:, None]
        if k < len(tl.segs) - 1:
            seg[-xf:] *= np.cos(np.linspace(0, np.pi / 2, xf))[:, None]
        pos = int(round(tl.off[k] * SR)) - (xf // 2 if k else 0)
        pos = max(0, pos)
        n = min(len(seg), len(mix_m) - pos)
        mix_m[pos:pos + n] += seg[:n]
    mix_m = mix_m[:total]
    t = np.arange(total) / SR
    # low-pass automation: crossfade between pre-filtered versions (log cutoff)
    cut = np.full(total, 20000.0)
    for b0, b1, f0, f1 in au.get("lpf", []):
        t0, t1 = tl.vt(b0), tl.vt(b1)
        m = (t >= t0) & (t <= t1)
        u = (t[m] - t0) / max(t1 - t0, 1e-6)
        cut[m] = f0 * (f1 / f0) ** u
    if (cut < 19999).any():
        F = np.array([250, 400, 550, 700, 1000, 1500, 2200, 3300, 5000, 8000, 12000, 20000], float)
        vers = [sosfilt(butter(4, f, btype="low", fs=SR, output="sos"), mix_m, axis=0) if f < 20000 else mix_m for f in F]
        li = np.interp(np.log(np.clip(cut, F[0], F[-1])), np.log(F), np.arange(len(F)))
        i0 = np.floor(li).astype(int); i1 = np.minimum(i0 + 1, len(F) - 1); w = (li - i0)[:, None]
        V = np.stack(vers)                           # (n_versions, total, 2)
        idx = np.arange(total)
        mix_m = V[i0, idx] * (1 - w) + V[i1, idx] * w
    # gain automation + silence windows + final fade
    gdb = np.zeros(total)
    pts = sorted((tl.vt(b), db) for b, db in au.get("gain", []))
    if pts:
        gdb = np.interp(t, [p[0] for p in pts], [p[1] for p in pts], left=pts[0][1], right=pts[-1][1])
    g = 10 ** (gdb / 20)
    for b0, b1 in au.get("silence", []):
        t0, t1 = tl.vt(b0), tl.vt(b1)
        r = 0.015
        g *= 1 - np.clip(np.minimum((t - (t0 - r)) / r, ((t1 + r) - t) / r), 0, 1)
    fo = au.get("fade_out", 0.8)
    g *= np.clip((tl.music_len + plan["segments"][-1].get("tail", 0) - t) / fo, 0, 1)
    mix_m *= g[:, None]
    # beds + cues
    sfx_dir = base / au.get("sfx_dir", "sfx_cinema")
    fx = np.zeros_like(mix_m)
    for bd in au.get("beds", []):
        src = read_audio(sfx_dir / f'{bd["sfx"]}.wav')
        t0, t1 = int(tl.vt(bd["from"]) * SR), int(tl.vt(bd["to"]) * SR)
        n = t1 - t0
        rep = np.tile(src, (n // len(src) + 1, 1))[:n] * 10 ** (bd.get("db", -36) / 20)
        ramp = min(int(0.3 * SR), n // 4)
        env = np.ones(n); env[:ramp] = np.linspace(0, 1, ramp); env[-ramp:] = np.linspace(1, 0, ramp)
        fx[t0:t1] += rep * env[:, None]
    for c in au.get("cues", []):
        src = read_audio(sfx_dir / f'{c["sfx"]}.wav') * 10 ** (c.get("db", -6) / 20)
        tt = tl.vt(c["at"]) if "at" in c else c["t"]
        # align: "end" (riser termina no evento) | "peak" (o golpe cai no evento,
        # medido no próprio arquivo — F3.0) | início (padrão)
        if c.get("align") == "end":
            s0 = int(round(tt * SR)) - len(src)
        elif c.get("align") == "peak":
            s0 = int(round(tt * SR)) - int(np.argmax(np.abs(src).max(axis=1) if src.ndim > 1 else np.abs(src)))
        else:
            s0 = int(round(tt * SR))
        s0 = max(0, s0); n = min(len(src), total - s0)
        fx[s0:s0 + n] += src[:n]
    mix = mix_m + fx
    raw = out_wav.with_suffix(".raw.wav")
    write_wav(raw, mix / max(1.0, np.max(np.abs(mix))))
    # two-pass loudnorm to −14 LUFS / −1 dBTP
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                           "-f", "null", "-"], capture_output=True, text=True).stderr
    js = json.loads(meas[meas.rfind("{"):meas.rfind("}") + 1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
                    f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,"
                    f"alimiter=limit=0.88:level=false", "-ar", str(SR), str(out_wav)], check=True)
    raw.unlink(missing_ok=True)
    return {"duration": round(total / SR, 3), "input_lufs": js["input_i"]}


# ------------------------------------------------------------------ main ----
def main() -> None:
    ap = argparse.ArgumentParser(description="Cinema-motion edit (24p, film look, light VFX, narrative audio)")
    ap.add_argument("plan", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--interp", default="mci", choices=["mci", "blend", "none"])
    ap.add_argument("--only-audio", action="store_true")
    a = ap.parse_args()
    base = a.plan.parent
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    fps = plan.get("fps", 24)
    W, H = (int(v) for v in plan.get("size", "1080x1920").split("x"))
    beats = json.loads((base / plan["beats"]).read_text(encoding="utf-8"))["beats"]
    tl = Timeline(beats, plan["segments"], fps)
    out = a.out
    for d in ["assets/video", "assets/audio", "assets/fonts", "compositions"]:
        (out / d).mkdir(parents=True, exist_ok=True)
    cache = base / "cache_cinema"; cache.mkdir(exist_ok=True)

    # ---- audio ----
    ainfo = build_audio(plan, tl, base, out / "assets/audio/mix.wav")
    print(f"audio: mix.wav {ainfo['duration']} s (music in {ainfo['input_lufs']} LUFS → −14)")
    if a.only_audio:
        return

    # ---- shots: retime (24p/180°) → film look ----
    sr_mod = load_mod("speed_ramp")
    glook = plan.get("look", {})
    analysis = json.loads((base / plan["analysis"]).read_text(encoding="utf-8")) if plan.get("analysis") else {}
    shots = plan["shots"]
    frames = []
    for k, s in enumerate(shots):
        f0, f1 = tl.frame(s["from"]), tl.frame(s["to"])
        if k == len(shots) - 1:
            f1 = int(round(tl.total * fps))
        frames.append((f0, f1))
    for k in range(1, len(frames)):
        assert frames[k][0] == frames[k - 1][1], f"gap between shot {k - 1} and {k}"
    report = []
    plates = []
    for k, s in enumerate(shots):
        cid = f"shot-{k:02d}"
        f0, f1 = frames[k]; nf = f1 - f0; dur = nf / fps
        take = base / plan.get("takes_dir", "graded_v2") / f"20261005_{s['take']}.mp4" if len(s["take"]) == 6 else base / s["take"]
        stab = base / plan.get("stab_dir", "") / take.name if plan.get("stab_dir") else None
        if plan.get("stabilize_all") and s.get("stabilize", True) and not (stab and stab.exists()):
            sdir = cache / "stab"; sdir.mkdir(exist_ok=True)
            stab = sdir / take.name
            if not stab.exists():
                tmp = stab.with_name("tmp_" + stab.name)
                run(["uv", "run", "python", str(HERE / "stabilize.py"), str(take), "-o", str(tmp), "--smoothing", "12", "--keep-if-better"])
                tmp.replace(stab)
        src = stab if stab and stab.exists() and s.get("stabilize", True) else take
        take_dur = probe_dur(src)
        sp = s.get("speed", 1.0)
        ein = plan.get("ease_in")
        if s.get("curve"):
            curve = s["curve"]
        elif ein and sp < 0.999 and s.get("ease", True):
            # the take arrives a bit faster and DECELERATES into its slow motion (log-space
            # smootherstep in speed_ramp) — a constant slow speed reads as "not smoothed"
            curve = f"0:{min(1.0, sp * ein.get('from_mult', 1.7)):.3f},{ein.get('until', 0.35)}:{sp},1:{sp}"
        else:
            curve = f"0:{sp},1:{sp}"
        u, v = sr_mod.parse_curve(curve)
        xs = np.linspace(0, 1, 2001)
        mean_v = float(np.trapezoid(sr_mod.speed_at(xs, u, v), xs))
        span = dur * mean_v
        if "reverse_to" in s:                                   # play [reverse_to, in] backwards
            span = min(span, s["in"] - s["reverse_to"])
            rk = key("rev", str(src), s["in"], span)
            rsrc = cache / f"rev_{rk}.mp4"
            if not rsrc.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s['in'] - span:.4f}", "-t", f"{span:.4f}", "-i", str(src),
                                "-vf", "reverse", "-c:v", "libx264", "-crf", "14", "-an", str(rsrc)], check=True)
            src, t_in, t_out = rsrc, 0.0, span - 0.01
        else:
            t_in = s["in"]; t_out = min(t_in + span, take_dur - 0.03)
        rk = key("retime", str(src), t_in, t_out, nf, fps, curve, plan.get("shutter", 180), a.interp)
        rp = cache / f"retime_{rk}.mp4"
        if not rp.exists():
            tmp = rp.with_name("tmp_" + rp.name)
            run(["uv", "run", "python", str(HERE / "speed_ramp.py"), str(src), "--in", f"{t_in:.4f}", "--out", f"{t_out:.4f}",
                 "--duration", f"{dur:.6f}", "--fps", str(fps), "--shutter", str(plan.get("shutter", 180)),
                 "--curve", curve, "--interp", a.interp, "-o", str(tmp)])
            tmp.replace(rp)  # atomic: a crash never leaves a truncated file the cache would trust
        lp_ = {**glook, **s.get("look", {})}
        gcfg = plan.get("grain") or {}
        if gcfg.get("mode", "baked") == "baked" and gcfg:
            lp_["grain"] = {"amount": gcfg.get("amount", 0.035), "size": gcfg.get("size", 1.0),
                            "seed": gcfg.get("seed", 7), "offset": f0}
        if s.get("streaks"):
            lp_["streaks"] = s["streaks"]
        if s.get("sweep"):
            lp_["sweep"] = s["sweep"]
        if s.get("hit"):
            lp_["hit"] = {"frame": 0, "frames": 4, "gain": 2.2}
        lk = key("look", rk, lp_)
        pp = out / "assets/video" / f"{cid}_{lk}.mp4"
        if not pp.exists():
            for old in (out / "assets/video").glob(f"{cid}_*.mp4"):
                old.unlink()
            pf = cache / f"look_{lk}.json"; pf.write_text(json.dumps(lp_), encoding="utf-8")
            tmp = pp.with_name("tmp_" + pp.name)
            run(["uv", "run", "python", str(HERE / "film_look.py"), str(rp), "-o", str(tmp), "--params-file", str(pf)])
            tmp.replace(pp)
        plates.append(pp)
        report.append(f"{cid}: T{s['take']} beats {s['from']}–{s['to']} frames {f0}–{f1} ({nf}) src {t_in:.2f}–{t_out:.2f}s "
                      f"curve {curve}{' REV' if 'reverse_to' in s else ''}{' STAB' if src == stab else ''}")
        print(report[-1], flush=True)

    # ---- match cuts: align the bright line height across the cut ----
    dys = [0.0] * len(shots)
    for k, s in enumerate(shots):
        if s.get("match") == "prev" and k:
            ra, rb = bright_line_row(edge_frame(plates[k - 1], True)), bright_line_row(edge_frame(plates[k], False))
            if ra is not None and rb is not None:
                dys[k] = float(np.clip(ra - rb, -0.06 * H, 0.06 * H))
                report.append(f"shot-{k:02d}: match cut — light line {rb:.0f}px → {ra:.0f}px (dy {dys[k]:+.0f})")

    # ---- HyperFrames ----
    font = Path(plan["fonts"]["archivo"]); shutil.copy(base / font, out / "assets/fonts" / font.name)
    for g in plan.get("graphics", []):
        if g.get("logo"):
            shutil.copy(base / g["logo"], out / "assets/fonts" / Path(g["logo"]).name)
    hosts = []
    for k, s in enumerate(shots):
        cid = f"shot-{k:02d}"; f0, f1 = frames[k]; dur = round((f1 - f0) / fps, 6)
        tr_out = shots[k + 1].get("transition", "cut") if k + 1 < len(shots) else "cut"
        (out / f"compositions/{cid}.html").write_text(
            shot_comp(cid, f"assets/video/{plates[k].name}", dur, fps, s, tr_out, W, H, dys[k]), encoding="utf-8")
        hosts.append(f'    <div id="{cid}" class="clip" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                     f'data-start="{round(f0 / fps, 6)}" data-duration="{dur}" data-track-index="0" data-track-kind="video" '
                     f'data-width="{W}" data-height="{H}" style="z-index:{10 + k % 2}"></div>')
    total = round(frames[-1][1] / fps, 6)
    # grain: one 2 s plate, tiled as clips (constant texture, screen-space)
    gr = plan.get("grain")
    if gr and gr.get("mode") == "layer":   # screen-space layer (heavy: noise does not compress; ERR_NO_BUFFER_SPACE measured)
        gp = out / "assets/video/grain.mp4"
        if not gp.exists():
            rng = np.random.default_rng(7)
            enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-r", str(fps),
                                    "-i", "-", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p", str(gp)], stdin=subprocess.PIPE)
            sz = gr.get("size", 1.0)
            for _ in range(int(2 * fps)):
                n = rng.normal(0, 1, (H, W)).astype(np.float32)
                if sz > 1:
                    n = cv2.GaussianBlur(n, (0, 0), sz * 0.5)
                n = n / (n.std() + 1e-6)
                enc.stdin.write(np.clip(128 + n * 40, 0, 255).astype(np.uint8).tobytes())
            enc.stdin.close(); enc.wait()
        t0, i = 0.0, 0
        while t0 < total - 1e-6:
            d = round(min(2.0, total - t0), 6)
            hosts.append(f'    <video id="grain-{i}" class="clip" src="assets/video/grain.mp4" data-start="{round(t0, 6)}" data-duration="{d}" '
                         f'data-media-start="0" data-track-index="3" muted playsinline style="position:absolute;inset:0;width:100%;height:100%;'
                         f'object-fit:cover;mix-blend-mode:soft-light;opacity:{gr.get("amount", 0.10)};z-index:40;pointer-events:none"></video>')
            t0 += d; i += 1
    if plan.get("veil", True):
        hosts.append(f'    <div id="veil" style="position:absolute;inset:0;z-index:45;pointer-events:none;background:'
                     f'linear-gradient(180deg, rgba(11,12,13,.35) 0%, rgba(11,12,13,0) 18%, rgba(11,12,13,0) 78%, rgba(11,12,13,.45) 100%)"></div>')
    if plan.get("vignette"):
        hosts.append(f'    <div id="vignette" style="position:absolute;inset:0;z-index:44;pointer-events:none;background:'
                     f'radial-gradient(ellipse 85% 70% at 50% 46%, rgba(0,0,0,0) 60%, rgba(0,0,0,{plan["vignette"]}) 100%)"></div>')
    for n, g in enumerate(plan.get("graphics", [])):
        cid = f"gfx-{n:02d}"
        g0 = int(round(tl.vt(g["from"]) * fps)); g1 = int(round(tl.vt(g["to"]) * fps)) if g["to"] != "end" else frames[-1][1]
        d = round((g1 - g0) / fps, 6)
        if g.get("anchor_until") is not None:
            g["_anchor_out"] = round((int(round(tl.vt(g["anchor_until"]) * fps)) - g0) / fps, 4)
        (out / f"compositions/{cid}.html").write_text(graphic(g, cid, d, fps, W, H, font.name), encoding="utf-8")
        hosts.append(f'    <div id="{cid}" class="clip" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                     f'data-start="{round(g0 / fps, 6)}" data-duration="{d}" data-track-index="{5 + n % 2}" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index:60"></div>')
    if plan.get("end_dim"):
        e0 = int(round(tl.vt(plan["end_dim"]["from"]) * fps))
        d = round((frames[-1][1] - e0) / fps, 6)
        (out / "compositions/fim.html").write_text(comp("fim", '        <div id="k" style="position:absolute;inset:0;background:#0b0c0d;opacity:0"></div>', "",
            [f'tl.to("#k", {{opacity:{plan["end_dim"].get("to", 0.7)}, duration:{d:.3f}, ease:"power1.in"}}, 0);'], W, H), encoding="utf-8")
        hosts.append(f'    <div id="fim" class="clip" data-composition-id="fim" data-composition-src="compositions/fim.html" '
                     f'data-start="{round(e0 / fps, 6)}" data-duration="{d}" data-track-index="7" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index:50"></div>')
    hosts.append(f'    <audio id="mix" src="assets/audio/mix.wav" data-start="0" data-duration="{total}" data-track-index="10" '
                 f'data-volume="1" data-timeline-role="music" data-audio-group="musica"></audio>')
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hf_version import recorded, stamp
    prev = recorded(out)  # um projeto refeito mantém a versão com que nasceu
    for name, d in (("package.json", {"name": "hyperframes", "private": True, "type": "module"}),
                    ("hyperframes.json", {"paths": {"blocks": "compositions", "assets": "assets"}, "media": {"autoProxy": True}})):
        (out / name).write_text(json.dumps(d, indent=2), encoding="utf-8")
    stamp(out, prev)
    index = f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={W}, height={H}">
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #000; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{total}" data-fps="{fps}">
{chr(10).join(hosts)}
  </div>
  <script>
    window.__timelines["main"] = gsap.timeline({{ paused: true }});
  </script>
  </body>
</html>
"""
    (out / "index.html").write_text(index, encoding="utf-8")
    (out / "cinema_report.txt").write_text("\n".join(report), encoding="utf-8")
    black = [frames[k][1] - s["black_end"] for k, s in enumerate(shots) if s.get("black_end")]
    (out / "cinema_meta.json").write_text(json.dumps({"fps": fps, "frames": frames[-1][1], "total": total,
        "intentional_black": [[f, frames[k][1]] for k, (f, s) in enumerate(zip(
            [frames[k][1] - shots[k].get("black_end", 0) for k in range(len(shots))], shots)) if s.get("black_end")]}), encoding="utf-8")
    print(f"ok {total}s · {len(shots)} shots · {frames[-1][1]} frames @ {fps} fps → {out}")


if __name__ == "__main__":
    main()
