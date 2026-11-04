"""Beat-synced montage → HyperFrames editor project (takes + music, cuts on the beat).

You describe the edit as a plan; this places every shot on the music's beat
grid (beat_map.py), renders speed ramps (speed_ramp.py) so each one fills its
beats exactly, and writes a HyperFrames project where every cut — and every
transition peak — lands on a beat frame. Each shot is its own sub-composition
(one row in Studio): its video plus its entrance, in-shot fx and exit. The
project opens in Prisma's EDITOR tab for hand tweaks and exports from there.

plan.json
{
  "music": "audio/track.mp3",            # paths relative to the plan file
  "beats": "beats.json",                 # beat_map.py output for that track
  "start_beat": 24,                      # montage starts on this beat of the track
  "fps": 30, "size": "1080x1920",
  "music_fade_out": 0.6,
  "fade_out": 0.6,                       # fade to black over the last N seconds
  "riser_before_beat": 16,               # riser SFX that lands on this beat (the drop)
  "sfx": true,                           # whoosh on whip/zoom, bass impact on flash/shake, glitch on rgb-split
  "titles": [{"text": "TAYCAN 4S", "sub": "PORSCHE", "at_beat": 16, "beats": 4, "pos": "top"}],
  "shots": [
    {"src": "takes/A.mp4", "in": 1.2, "beats": 4},                         # plain, 4 beats
    {"src": "takes/B.mp4", "in": 0.0, "out": 3.0, "beats": 2, "ramp": "whip-slow",
     "transition": "whip-left"},                                           # 3 s of source ramped into 2 beats
    {"src": "takes/C.mp4", "in": 4.0, "beats": 4, "transition": "flash", "fx": ["pulse"]},
    {"src": "takes/D.mp4", "in": 2.0, "beats": 8, "transition": "zoom", "fx": ["push", "shake@0"]}
  ]
}

transition (into this shot; the outgoing half is written into the previous shot):
  cut | flash | whip-left | whip-right | whip-up | whip-down | zoom | rgb-split | shake
  speed   the speed-ramp transition: previous shot "ramp": "speed-out", this one
          "speed-in"/"speed-in-slow" — a cut hidden in motion blur at peak speed (+ whoosh)

per shot (or plan-wide default_*):
  speed      number or "auto" (take_analyzer.py) — constant slow-down when no ramp
  stabilize  true | "auto" — stabilize.py, cached per take, kept only if shake drops ≥ 20 %
  ramp       preset (speed_ramp.py); "out" optional — computed from the curve, capped by the take
plan-wide: "analysis": "takes_analysis.json" (take_analyzer.py output)
fx (inside the shot):
  pulse      scale bump on every beat of the shot (punch on the kick)
  push       slow push-in across the shot
  shake@N    impact shake starting at beat N of the shot (0 = on the cut)

Usage:
  python helpers/beat_edit.py plan.json -o edit/hyperframes_beat [--interp blend]
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
import shutil
import subprocess

import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = {"name": "hyperframes", "private": True, "type": "module",
       "scripts": {"dev": "npx --yes hyperframes@latest preview", "check": "npx --yes hyperframes@latest check",
                   "render": "npx --yes hyperframes@latest render"}}
HFJSON = {"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
          "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
          "media": {"autoProxy": True}, "authoringSkill": "general-video"}
T = 0.20  # each half of a transition (s): exit = last T of the outgoing shot, entrance = first T of the next


def f3(x: float) -> float:
    return round(x, 3)


def whip_axis(tr: str, W: int, H: int):
    """A whip moves the picture inside a 1.3x overscan (never uncovering the
    frame: 0.14 x size < the 0.15 slack) while a heavy directional blur sells
    the speed — no black gap, the two shots smear into each other."""
    d = tr.split("-")[1]
    axis = "x" if d in ("left", "right") else "y"
    sign = -1 if d in ("left", "up") else 1
    return axis, sign, (W if axis == "x" else H) * 0.14, ("80 0" if axis == "x" else "0 80")


def shot_comp(cid: str, asset: str, media_start: float, dur: float, beat_offsets: list[float],
              tr_in: str, tr_out: str, fx: list[str], W: int, H: int) -> str:
    whip = tr_in.startswith("whip-") or tr_out.startswith("whip-")
    base_filter = f"url(#blur-{cid})" if whip else f"url(#rgb-{cid})" if tr_in == "rgb-split" else "none"
    js = [f'tl.set("#push-{cid}", {{scale:1}}, 0);', f'tl.set("#frame-{cid}", {{scale:1, x:0, y:0, rotation:0}}, 0);',
          f'tl.set("#v-{cid}", {{x:0, y:0, scale:1, filter:"{base_filter}"}}, 0);']
    extra = ""
    # entrance
    if tr_in == "flash":
        extra += f'\n        <div id="flash-{cid}" style="position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none"></div>'
        js.append(f'tl.fromTo("#flash-{cid}", {{opacity:0.95}}, {{opacity:0, duration:0.18, ease:"power2.out", immediateRender:false}}, 0);')
    elif tr_in.startswith("whip-"):
        axis, sign, dist, blur = whip_axis(tr_in, W, H)
        js.append(f'tl.fromTo("#v-{cid}", {{{axis}:{-sign * dist:.0f}, scale:1.3}}, {{{axis}:0, scale:1, duration:{T}, ease:"power3.out", immediateRender:false}}, 0);')
        js.append(f'tl.fromTo("#bb-{cid}", {{attr:{{stdDeviation:"{blur}"}}}}, {{attr:{{stdDeviation:"0 0"}}, duration:{T}, ease:"power3.out", immediateRender:false}}, 0);')
    elif tr_in == "zoom":
        js.append(f'tl.fromTo("#v-{cid}", {{scale:1.3, filter:"blur(12px)"}}, {{scale:1, filter:"blur(0px)", duration:{T + 0.05}, ease:"power3.out", immediateRender:false}}, 0);')
    elif tr_in == "rgb-split":
        # real chromatic split: the SVG filter separates R/G/B and offsets R and B
        # (a CSS drop-shadow only shows outside a full-frame video's edge, i.e. nowhere)
        js.append(f'tl.fromTo("#ro-{cid}", {{attr:{{dx:22}}}}, {{attr:{{dx:0}}, duration:0.28, ease:"steps(6)", immediateRender:false}}, 0);')
        js.append(f'tl.fromTo("#bo-{cid}", {{attr:{{dx:-22}}}}, {{attr:{{dx:0}}, duration:0.28, ease:"steps(6)", immediateRender:false}}, 0);')
    elif tr_in == "shake":
        fx = list(fx) + ["shake@0"]
    # exit (the next shot's transition, outgoing half)
    if tr_out.startswith("whip-"):
        axis, sign, dist, blur = whip_axis(tr_out, W, H)
        js.append(f'tl.to("#v-{cid}", {{{axis}:{sign * dist:.0f}, scale:1.3, duration:{T}, ease:"power2.in"}}, {f3(dur - T)});')
        js.append(f'tl.fromTo("#bb-{cid}", {{attr:{{stdDeviation:"0 0"}}}}, {{attr:{{stdDeviation:"{blur}"}}, duration:{T}, ease:"power2.in", immediateRender:false}}, {f3(dur - T)});')
    elif tr_out == "zoom":
        js.append(f'tl.to("#v-{cid}", {{scale:1.35, filter:"blur(10px)", duration:{T}, ease:"power3.in"}}, {f3(dur - T)});')
    # in-shot fx
    for e in fx:
        if e == "pulse":
            gap = min(beat_offsets[1] - beat_offsets[0], 0.5) if len(beat_offsets) > 1 else 0.5
            for bt in beat_offsets:
                js.append(f'tl.fromTo("#frame-{cid}", {{scale:1.045}}, {{scale:1, duration:{gap * 0.8:.3f}, ease:"power2.out", immediateRender:false}}, {bt});')
        elif e == "push":
            js.append(f'tl.fromTo("#push-{cid}", {{scale:1}}, {{scale:1.08, duration:{dur}, ease:"none", immediateRender:false}}, 0);')
        elif e.startswith("shake@"):
            k = int(e.split("@")[1])
            bt = beat_offsets[min(k, len(beat_offsets) - 1)]
            for j, (dx, dy, rot) in enumerate([(18, -10, 1.2), (-14, 8, -1), (10, -6, 0.6), (-6, 4, -0.4), (0, 0, 0)]):
                js.append(f'tl.to("#frame-{cid}", {{x:{dx}, y:{dy}, rotation:{rot}, duration:0.045, ease:"none"}}, {f3(bt + j * 0.045)});')
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head><meta charset="UTF-8"></head>
  <body>
    <template>
      <style>
        #root {{ position: absolute; inset: 0; overflow: hidden; background: #000; }}
        .layer {{ position: absolute; inset: 0; transform-origin: 50% 50%; }}
        video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 50% 50%; }}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}">
        <svg width="0" height="0" style="position:absolute" aria-hidden="true">
          <filter id="blur-{cid}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur id="bb-{cid}" stdDeviation="0 0"/></filter>
          <filter id="rgb-{cid}" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">
            <feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r"/>
            <feOffset id="ro-{cid}" in="r" dx="0" dy="0" result="r2"/>
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="g"/>
            <feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="b"/>
            <feOffset id="bo-{cid}" in="b" dx="0" dy="0" result="b2"/>
            <feBlend in="r2" in2="g" mode="screen" result="rg"/><feBlend in="rg" in2="b2" mode="screen"/>
          </filter>
        </svg>
        <div id="push-{cid}" class="layer"><div id="frame-{cid}" class="layer">
          <video id="v-{cid}" class="clip" src="{asset}" data-start="0" data-duration="{dur}" data-media-start="{media_start}" data-track-index="0" muted playsinline></video>
        </div></div>{extra}
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


def title_comp(cid: str, text: str, sub: str, top: float, dur: float, W: int, H: int) -> str:
    """Kinetic title: letters track in from wide spacing while coming into focus,
    a thin rule draws, the sub-line follows; everything softly exits at the end."""
    out_at = max(0.6, dur - 0.35)
    mid = (len(text) - 1) / 2
    letters = "".join(f'<span class="ch" style="display:inline-block">{"&nbsp;" if c == " " else c}</span>' for c in text)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head><meta charset="UTF-8"></head>
  <body>
    <template>
      <style>
        #root {{ position: absolute; inset: 0; }}
        .t {{ position: absolute; left: 0; right: 0; text-align: center; color: #fff; font-family: "Poppins", sans-serif;
              text-shadow: 0 4px 30px rgba(0,0,0,.55); }}
        #t1-{cid} {{ top: {top:.0f}px; font-weight: 800; font-size: 128px; line-height: 1; letter-spacing: 0.10em; opacity: 0; }}
        #rule-{cid} {{ position: absolute; top: {top + 160:.0f}px; left: 50%; width: 260px; height: 3px; margin-left: -130px; background: #fff; transform: scaleX(0); }}
        #t2-{cid} {{ top: {top + 188:.0f}px; font-weight: 500; font-size: 34px; letter-spacing: 0.55em; color: #d6defa; opacity: 0; }}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}">
        <div id="t1-{cid}" class="t">{letters}</div>
        <div id="rule-{cid}"></div>
        <div id="t2-{cid}" class="t">{sub}</div>
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
          // tracking-in done with transforms (letter-spacing snaps to device pixels and stutters when seeked)
          tl.fromTo("#t1-{cid}", {{opacity:0, filter:"blur(14px)"}}, {{opacity:1, filter:"blur(0px)", duration:0.6, ease:"power3.out", immediateRender:false}}, 0.02);
          tl.fromTo("#t1-{cid} .ch", {{x:(i) => (i - {mid}) * 46}}, {{x:0, duration:0.7, ease:"power3.out", immediateRender:false}}, 0.02);
          tl.fromTo("#rule-{cid}", {{scaleX:0}}, {{scaleX:1, duration:0.45, ease:"power3.out", immediateRender:false}}, 0.25);
          tl.fromTo("#t2-{cid}", {{opacity:0, y:12}}, {{opacity:1, y:0, duration:0.4, ease:"power2.out", immediateRender:false}}, 0.35);
          tl.to(["#t1-{cid}", "#t2-{cid}", "#rule-{cid}"], {{opacity:0, filter:"blur(8px)", duration:0.3, ease:"power1.in"}}, {out_at:.3f});
          window.__timelines["{cid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Beat-synced montage → HyperFrames project")
    ap.add_argument("plan", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--interp", default="mci", choices=["mci", "blend", "none"], help="speed-ramp interpolation")
    a = ap.parse_args()
    base = a.plan.parent
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    bd = json.loads((base / plan["beats"]).read_text(encoding="utf-8"))
    beats = bd["beats"]
    fps = plan.get("fps", bd.get("fps", 30))
    W, H = (int(v) for v in plan.get("size", "1080x1920").split("x"))
    snap = lambda t: round(round(t * fps) / fps, 4)

    out = a.out
    for d in ["assets/video", "assets/audio", "compositions"]:
        (out / d).mkdir(parents=True, exist_ok=True)
    _sys.path.insert(0, str(HERE))
    from hf_version import recorded, stamp
    prev = recorded(out)  # um projeto refeito mantém a versão com que nasceu
    (out / "package.json").write_text(json.dumps(PKG, indent=2), encoding="utf-8")
    stamp(out, prev)      # troca o @latest dos scripts pela versão fixa
    (out / "hyperframes.json").write_text(json.dumps(HFJSON, indent=2), encoding="utf-8")
    music = base / plan["music"]
    shutil.copy(music, out / "assets/audio" / music.name)

    # pass 1: timings
    b0 = plan.get("start_beat", 0)
    t0 = beats[b0]
    shots, cur = [], b0
    for i, sh in enumerate(plan["shots"]):
        nb = int(sh["beats"])
        if cur + nb >= len(beats):
            raise SystemExit(f"shot {i}: beat {cur + nb} is past the end of the grid ({len(beats)} beats)")
        # integer frames: shot k ends on the exact frame shot k+1 starts. Rounded
        # seconds left 0.0003 s gaps that the renderer turned into black frames.
        fa, fb = round((beats[cur] - t0) * fps), round((beats[cur + nb] - t0) * fps)
        start, end = round(fa / fps, 6), round(fb / fps, 6)
        offs = [round((round((beats[cur + k] - t0) * fps) - fa) / fps, 4) for k in range(nb)]
        shots.append(dict(sh, i=i, nb=nb, b=cur, start=start, end=end, dur=round((fb - fa) / fps, 6), offs=offs,
                          tr=sh.get("transition", "cut") if i else "cut"))
        cur += nb

    # pass 2: media + sub-compositions
    hosts, report = [], []
    analysis = json.loads((base / plan["analysis"]).read_text(encoding="utf-8")) if plan.get("analysis") else {}
    (out / "assets/stab").mkdir(parents=True, exist_ok=True)
    for k, s in enumerate(shots):
        cid = f"shot-{s['i']:02d}"
        src = base / s["src"]
        info = analysis.get(src.stem, {})
        take_dur = info.get("duration") or float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
            capture_output=True, text=True).stdout.strip() or 0)
        # ---- stabilise (cached per take; kept only if it really reduces shake) ----
        stab = s.get("stabilize", plan.get("default_stabilize", False))
        if stab == "auto":
            stab = info.get("stabilize", "none") != "none"
        if stab:
            sp = out / "assets/stab" / f"{src.stem}.mp4"
            if not sp.exists():
                sm = info.get("vidstab_smoothing") or 12
                subprocess.run(["uv", "run", "python", str(HERE / "stabilize.py"), str(src), "-o", str(sp),
                                "--smoothing", str(sm), "--keep-if-better"], cwd=str(HERE.parent), check=True,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            src = sp
        # ---- speed: constant slow-down per take (auto = take_analyzer recommendation) ----
        spd = s.get("speed", plan.get("default_speed", 1.0))
        if spd == "auto":
            spd = info.get("speed", 1.0)
        if s.get("ramp", "none") == "none" and float(spd) < 0.999:
            s["ramp"], s["curve"] = "speed", f"0:{spd},1:{spd}"
            s["out"] = min(s.get("in", 0) + s["dur"] * float(spd), take_dur - 0.03)
        if s.get("ramp", "none") != "none":
            if "out" not in s:
                # source the curve wants at its nominal speeds, capped by the take
                import importlib.util
                spec = importlib.util.spec_from_file_location("speed_ramp", HERE / "speed_ramp.py")
                sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)
                u, v = sr.parse_curve(s.get("curve") or sr.PRESETS[s["ramp"]])
                xs = np.linspace(0, 1, 2001)
                mean_v = float(np.trapezoid(sr.speed_at(xs, u, v), xs))
                s["out"] = round(min(s.get("in", 0) + s["dur"] * mean_v, take_dur - 0.03), 3)
            rp = out / "assets/video" / f"{cid}_ramp.mp4"
            cmd = ["uv", "run", "python", str(HERE / "speed_ramp.py"), str(src), "--in", str(s["in"]), "--out", str(s["out"]),
                   "--duration", str(s["dur"]), "--fps", str(fps), "--interp", a.interp, "-o", str(rp)]
            cmd += ["--curve", s["curve"]] if "curve" in s else ["--preset", s["ramp"]]
            if s.get("width"):
                cmd += ["--width", str(s["width"])]
            r = subprocess.run(cmd, cwd=str(HERE.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode:
                raise SystemExit(f"{cid}: speed_ramp failed\n{r.stderr[-800:]}")
            asset, ms = f"assets/video/{rp.name}", 0
            note = f"ramp {s['ramp']}{' (stab)' if stab else ''} · " + r.stdout.strip().split(":", 1)[-1].strip()
        else:
            dst = out / "assets/video" / f"{cid}{src.suffix}"
            shutil.copy(src, dst)
            asset, ms = f"assets/video/{dst.name}", s.get("in", 0)
            note = f"src {ms}s"
        tr_out = shots[k + 1]["tr"] if k + 1 < len(shots) else "cut"
        (out / f"compositions/{cid}.html").write_text(
            shot_comp(cid, asset, ms, s["dur"], s["offs"], s["tr"], tr_out, s.get("fx", []), W, H), encoding="utf-8")
        hosts.append(f'    <div id="{cid}" class="clip" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                     f'data-start="{s["start"]}" data-duration="{s["dur"]}" data-track-index="0" data-track-kind="video" '
                     f'data-width="{W}" data-height="{H}" style="z-index:{10 + k % 2}"></div>')
        report.append(f"{cid}: beats {s['b']}-{s['b'] + s['nb']}  {s['start']:.3f}-{s['end']:.3f}s  in:{s['tr']}  {note}")

    total = shots[-1]["end"]

    # ---- titles (kinetic: tracking-in + blur-out-of-focus, soft exit) ----
    for n, tt in enumerate(plan.get("titles", [])):
        cid = f"titulo-{n}"
        fa = round((beats[b0 + tt["at_beat"]] - t0) * fps)
        fb = round((beats[b0 + tt["at_beat"] + tt.get("beats", 4)] - t0) * fps)
        ts, td = round(fa / fps, 6), round((fb - fa) / fps, 6)
        top = {"center": H * 0.40, "top": H * 0.14, "bottom": H * 0.66}[tt.get("pos", "center")]
        (out / f"compositions/{cid}.html").write_text(title_comp(cid, tt["text"], tt.get("sub", ""), top, td, W, H), encoding="utf-8")
        hosts.append(f'    <div id="{cid}" class="clip" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" '
                     f'data-start="{ts}" data-duration="{td}" data-track-index="3" data-track-kind="graphics" '
                     f'data-width="{W}" data-height="{H}" style="z-index:30"></div>')
    # ---- fade to black ----
    if plan.get("fade_out"):
        fo = float(plan["fade_out"])
        (out / "compositions/fim.html").write_text(
            f'<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body><template><style>#root{{position:absolute;inset:0}}'
            f'#k{{position:absolute;inset:0;background:#000;opacity:0}}</style><div id="root" data-composition-id="fim" '
            f'data-width="{W}" data-height="{H}"><div id="k"></div></div><script>(function(){{const tl=gsap.timeline({{paused:true}});'
            f'tl.to("#k",{{opacity:1,duration:{fo},ease:"power1.in"}},0);window.__timelines["fim"]=tl;}})();</script></template></body></html>',
            encoding="utf-8")
        ff = round((total - fo) * fps) / fps
        hosts.append(f'    <div id="fim" class="clip" data-composition-id="fim" data-composition-src="compositions/fim.html" '
                     f'data-start="{round(ff, 6)}" data-duration="{round(total - ff, 6)}" data-track-index="5" '
                     f'data-track-kind="graphics" data-width="{W}" data-height="{H}" style="z-index:50"></div>')
    # ---- sound design: whoosh on whips/zoom, bass impact on flashes, glitch on rgb-split ----
    if plan.get("sfx", True):
        lib = HERE.parent.parent / "media-use/audio/assets/sfx"
        kit = HERE.parent / "assets/shortform/public/sfx"
        # flash: impact.wav do kit (D9, 2026-11-03). O impact-bass-1 antigo é um
        # drone de sub de 2 s em −1 dB de 0,1 a 1,0 s: em fone/TV cobre voz e
        # música por 2 s; no celular sobra o ataque fino. Mesmo volume → mesmo
        # ataque na banda do celular (−13,0 vs −13,4 dB). Alinhado pelo ATAQUE
        # ("start"), não pelo pico: o pico de 0,05 s é o sub; por ele o transiente
        # soava 50 ms ANTES do flash (medido no mix) — áudio adiantado se percebe
        # a partir de ~45 ms (ITU-R BT.1359); atrasado, só a partir de ~125 ms.
        pick = {"whip": ("whoosh-short.mp3", -0.16, 0.55), "zoom": ("whoosh-cinematic.mp3", -0.30, 0.5),
                "flash": (kit / "impact.wav", "start", 0.8), "rgb-split": ("glitch-1.mp3", 0.0, 0.45),
                "shake": ("impact-bass-2.mp3", -0.02, 0.6),
                "speed": ("whoosh.mp3", -0.22, 0.5)}
        n, lanes = 0, []          # lanes: end time per audio track, so cues never overlap on one track
        cap = {"whip": 0.9, "zoom": 1.2, "flash": 1.1, "rgb-split": 0.8, "shake": 1.5, "speed": 0.8}
        for s in shots[1:]:
            key = "whip" if s["tr"].startswith("whip-") else s["tr"]
            if key not in pick:
                continue
            src, off, vol = pick[key]
            src = Path(src) if Path(src).is_absolute() else lib / src
            if not src.exists():
                continue
            fn = src.name
            if isinstance(off, str):   # alinhamento medido no arquivo (sfx_peak), não suposto
                from sfx_peak import shift
                off = -shift(src, off)
            shutil.copy(src, out / "assets/audio" / fn)
            d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                      str(src)], capture_output=True, text=True).stdout.strip() or 1)
            st = max(0.0, s["start"] + off)
            d = min(d, cap[key], total - st)
            lane = next((j for j, e in enumerate(lanes) if e <= st), None)
            if lane is None:
                lanes.append(0.0); lane = len(lanes) - 1
            lanes[lane] = st + d
            hosts.append(f'    <audio id="sfx-{n}" src="assets/audio/{fn}" data-start="{round(st, 3)}" data-duration="{round(d, 3)}" '
                         f'data-track-index="{11 + lane}" data-volume="{vol}" data-audio-group="sfx" data-fade-out="0.15"></audio>')
            n += 1
        rb = plan.get("riser_before_beat")
        if rb is not None and (lib / "riser.mp3").exists():
            shutil.copy(lib / "riser.mp3", out / "assets/audio/riser.mp3")
            d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                      str(lib / "riser.mp3")], capture_output=True, text=True).stdout.strip() or 2)
            hit = round((beats[b0 + rb] - t0) * fps) / fps
            st = max(0.0, hit - d)
            hosts.append(f'    <audio id="riser" src="assets/audio/riser.mp3" data-start="{round(st, 3)}" '
                         f'data-duration="{round(hit - st, 3)}" data-media-start="{round(max(0, d - hit), 3)}" '
                         f'data-track-index="{11 + len(lanes)}" data-volume="0.5" data-audio-group="sfx"></audio>')
    hosts.append(f'    <audio id="music" src="assets/audio/{music.name}" data-start="0" data-duration="{total}" '
                 f'data-media-start="{f3(t0)}" data-track-index="9" data-volume="1" data-timeline-role="music" '
                 f'data-audio-group="musica" data-fade-out="{plan.get("music_fade_out", 0.6)}"></audio>')
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
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{total}">
{chr(10).join(hosts)}
  </div>
  <script>
    window.__timelines["main"] = gsap.timeline({{ paused: true }});
  </script>
  </body>
</html>
"""
    (out / "index.html").write_text(index, encoding="utf-8")
    (out / "beat_edit_report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"ok {total}s · {len(shots)} shots · beats {b0}→{cur} ({bd['tempo']} BPM) → {out}")


if __name__ == "__main__":
    main()
