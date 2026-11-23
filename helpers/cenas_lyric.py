"""cenas_lyric.py: the "lyric-carro" cena (called by cenas.py; not a CLI of its own).

Reverse-engineered on 2026-11-23 from a reference car lyric edit (F5 in Prisma-Suite
docs/analises/2026-11-22-formatos-de-referencia.md; study only, nothing of it is copied): over a
montage already cut on the beat, the song's words pop one at a time as tilted 3D titles (extruded,
outlined, glowing; gold / cyan / white-on-red, cycling), each on its syllable, placed around the car;
on the bar lines the frame gets a manga speed-line burst or a halftone sunburst, and a white flash on
the drop. The AI-drawn interludes and the wheel-tracked light rings of the source are left out.

Word times: `palavras` ("TEXTO@t|…", t from the start of the stretch) or `letra` (a transcribe.py
transcript of the song; the words inside de..ate). Bursts: `rajadas` / `flashes` ("t|t…") or `beats`
(a beat_map.py map: downbeats alternate speed lines and rays, drops flash).
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from cenas_titulo import _probe_dur
from hfkit.project import FONT_STACK, Project, esc, font_faces

W, H, FPS = 1080, 1920, 30
ESTILOS = ("ouro", "ciano", "branco")
# (x, y) of the word centre as fractions of the frame, rotationY, rotationZ, size factor
SLOTS = [(0.34, 0.20, -24, -6, 1.0), (0.64, 0.34, 22, 5, 0.9), (0.5, 0.64, -12, -3, 1.1),
         (0.40, 0.47, 26, -8, 0.85), (0.60, 0.16, -18, 6, 0.95)]
BURST = 0.45


def _times(v) -> list[float]:
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v]
    return [float(x) for x in str(v).split("|") if x.strip()]


def _parse_palavras(v) -> list[dict]:
    if isinstance(v, list):
        return [{"texto": str(p["texto"]), "t": float(p["t"])} for p in v]
    out = []
    for item in filter(None, (x.strip() for x in str(v or "").split("|"))):
        texto, _, t = item.rpartition("@")
        out.append({"texto": texto, "t": float(t)})
    return out


def _from_letra(path: Path, de: float, ate: float) -> list[dict]:
    words = json.loads(Path(path).read_text(encoding="utf-8")).get("words", [])
    out = []
    for w in words:
        if w.get("type", "word") != "word":
            continue
        txt = str(w.get("text", "")).strip()
        st = w.get("start")
        if txt and st is not None and de <= float(st) < ate:
            out.append({"texto": txt, "t": round(float(st) - de, 3)})
    return out


def validate(dados: dict) -> list[str]:
    probs = []
    v = dados.get("video")
    if not v or not Path(v).exists():
        probs.append(f"video não encontrado: {v!r}")
    de, ate = float(dados.get("de", 0)), float(dados.get("ate", 0))
    if ate <= de:
        probs.append(f"ate ({ate}) precisa ser maior que de ({de})")
    elif v and Path(v).exists():
        dur = _probe_dur(Path(v))
        if dur and ate > dur + 0.05:
            probs.append(f"ate ({ate}) passa do fim do video ({dur:.2f} s)")
    letra = dados.get("letra")
    if letra:
        if not Path(letra).exists():
            probs.append(f"letra (transcript da música) não encontrada: {letra!r}")
    else:
        try:
            ws = _parse_palavras(dados.get("palavras"))
            if not ws:
                probs.append("sem palavras: dê palavras (TEXTO@t|…) ou letra (transcript da música)")
        except ValueError:
            probs.append("palavras: use TEXTO@segundos separados por | (ex.: ACELERA@0.4|SEM@0.9)")
    for k in ("beats",):
        if dados.get(k) and not Path(dados[k]).exists():
            probs.append(f"{k} não encontrado: {dados[k]!r}")
    for k in ("rajadas", "flashes"):
        try:
            _times(dados.get(k))
        except ValueError:
            probs.append(f"{k}: use segundos separados por |")
    for e in dados.get("paleta") or []:
        if e not in ESTILOS:
            probs.append(f"paleta: '{e}' não existe (use {', '.join(ESTILOS)})")
    return probs


def _speed_lines(seed: int) -> str:
    rnd = random.Random(seed)
    cx, cy, R = W / 2, H / 2, math.hypot(W, H) / 2 * 1.15
    polys = []
    for _ in range(70):
        a = rnd.uniform(0, 2 * math.pi)
        r0 = rnd.uniform(0.42, 0.62) * R
        wd = rnd.uniform(0.004, 0.012)
        p = [(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
             (cx + math.cos(a - wd) * R, cy + math.sin(a - wd) * R),
             (cx + math.cos(a + wd) * R, cy + math.sin(a + wd) * R)]
        polys.append('<polygon points="' + " ".join(f"{x:.0f},{y:.0f}" for x, y in p) +
                     f'" fill="#fff" fill-opacity="{rnd.uniform(0.55, 0.95):.2f}"/>')
    return "".join(polys)


def build(proj: Project, dados: dict) -> Path:
    out = proj.root
    video = Path(dados["video"])
    src = proj.asset(video)
    de, ate = float(dados.get("de", 0)), float(dados["ate"])
    dur = round(ate - de, 6)
    ws = _from_letra(Path(dados["letra"]), de, ate) if dados.get("letra") else _parse_palavras(dados.get("palavras"))
    ws = [w for w in ws if 0 <= w["t"] < dur]
    paleta = list(dados.get("paleta") or ESTILOS)

    bursts = [(t, "rajada" if i % 2 == 0 else "raios") for i, t in enumerate(_times(dados.get("rajadas")))]
    flashes = _times(dados.get("flashes"))
    if dados.get("beats"):
        bm = json.loads(Path(dados["beats"]).read_text(encoding="utf-8"))
        if not bursts:
            dbs = [round(t - de, 3) for t in bm.get("downbeats", []) if de <= t < ate]
            bursts = [(t, "rajada" if i % 2 == 0 else "raios") for i, t in enumerate(dbs)]
        if not flashes:
            flashes = [round(t - de, 3) for t in bm.get("drops", []) if de <= t < ate]

    words_html, tl = [], ["const tl = gsap.timeline({ paused: true });"]
    for i, w in enumerate(ws):
        texto = w["texto"].upper()
        x, y, ry, rz, k = SLOTS[i % len(SLOTS)]
        fs = int(min(300 * k, 960 / (0.72 * max(1, len(texto)))))
        est = paleta[i % len(paleta)]
        hw = 0.38 * fs * len(texto) + 50          # half the drawn width, extrusion and tilt included
        cx = int(min(max(x * W, hw), W - hw)) if hw * 2 < W else W // 2
        words_html.append(f'<div class="lw {est}" id="w{i}" style="left:{cx}px;top:{int(y * H)}px;'
                          f'font-size:{fs}px">{esc(texto)}</div>')
        t = w["t"]
        nxt = ws[i + 1]["t"] if i + 1 < len(ws) else dur
        hold = max(0.28, min(1.0, nxt - t + 0.12))
        hold = min(hold, dur - t)
        tl.append(f'tl.set("#w{i}", {{xPercent:-50, yPercent:-50, transformPerspective:900, rotationY:{ry}}}, 0);')
        tl.append(f'tl.fromTo("#w{i}", {{opacity:0, scale:1.7, rotation:{rz - 12}, filter:"blur(8px)"}}, '
                  f'{{opacity:1, scale:1, rotation:{rz}, filter:"blur(0px)", duration:0.14, ease:"crashIn"}}, {t});')
        tl.append(f'tl.to("#w{i}", {{scale:1.06, duration:{max(0.05, hold - 0.22):.3f}, ease:"cruise"}}, {t + 0.14:.3f});')
        tl.append(f'tl.to("#w{i}", {{opacity:0, scale:1.25, duration:0.08, ease:"accelExit"}}, {t + hold - 0.08:.3f});')

    has_r = any(kd == "rajada" for _, kd in bursts)
    has_s = any(kd == "raios" for _, kd in bursts)
    for t, kd in bursts:
        if t >= dur:
            continue
        tl.append(f"/* burst {kd} @{t:g} */")
        if kd == "rajada":
            steps = int(BURST * 15)
            for j in range(steps):
                tl.append(f'tl.set(".sl", {{opacity:0}}, {t + j / 15:.3f}); '
                          f'tl.set("#sl{j % 3}", {{opacity:1}}, {t + j / 15:.3f});')
            tl.append(f'tl.set(".sl", {{opacity:0}}, {t + steps / 15:.3f});')
        else:
            tl.append(f'tl.fromTo("#raios", {{opacity:0, rotation:0, scale:1.1}}, '
                      f'{{opacity:1, duration:0.06, ease:"cruise", immediateRender:false}}, {t});')
            tl.append(f'tl.to("#raios", {{rotation:14, scale:1, duration:{BURST + 0.1}, ease:"cruise"}}, {t});')
            tl.append(f'tl.to("#raios", {{opacity:0, duration:0.12, ease:"cruise"}}, {t + BURST - 0.05:.3f});')
    for t in flashes:
        if t < dur:
            tl.append(f"/* flash @{t:g} */")
            # set + to, not fromTo: a fromTo renders its "from" at once (a white frame from t = 0)
            tl.append(f'tl.set("#flash", {{opacity:0.95}}, {t}); '
                      f'tl.to("#flash", {{opacity:0, duration:0.18, ease:"glide"}}, {t + 1 / FPS:.3f});')

    rajada_html = (''.join(f'<svg class="sl" id="sl{v}" viewBox="0 0 {W} {H}">{_speed_lines(v + 7)}</svg>'
                           for v in range(3))) if has_r else ""
    if has_r:
        rajada_html = f'<div class="rajada">{rajada_html}</div>'
    raios_html = '<div class="raios" id="raios"></div>' if has_s else ""

    eases = (Path(__file__).resolve().parent.parent / "assets" / "hyperframes" / "vendor" / "prisma-eases.js").read_text(
        encoding="utf-8")

    def extr(col: str, n: int = 9) -> str:
        return ", ".join(f"{d}px {d}px 0 {col}" for d in range(1, n + 1))

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={W}, height={H}">
    <script src="assets/vendor/gsap.min.js"></script>
    <script>
{eases}
    </script>
    <style>
{font_faces(weights=(900,))}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: #000; font-family: {FONT_STACK}; }}
      #v {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      .lw {{ position: absolute; white-space: nowrap; font-weight: 900; line-height: 1; letter-spacing: -0.02em;
             opacity: 0; transform-origin: 50% 50%; }}
      .lw.ouro {{ color: #ffd23f; -webkit-text-stroke: 3px #7a4600;
                  text-shadow: {extr("#8a5200")}, 0 0 28px rgba(255,200,60,.75), 0 0 70px rgba(255,170,0,.45); }}
      .lw.ciano {{ color: #63f3ff; -webkit-text-stroke: 3px #0b5560;
                   text-shadow: {extr("#064048")}, 0 0 28px rgba(90,240,255,.85), 0 0 70px rgba(0,200,255,.45); }}
      .lw.branco {{ color: #ffffff; -webkit-text-stroke: 4px #d4122c;
                    text-shadow: {extr("#8c0018")}, 0 0 26px rgba(255,60,80,.65), 0 0 60px rgba(255,0,40,.35); }}
      .rajada, .sl {{ position: absolute; inset: 0; width: {W}px; height: {H}px; }}
      .sl {{ opacity: 0; }}
      .raios {{ position: absolute; left: -{W // 2}px; top: -{H // 4}px; width: {W * 2}px; height: {int(H * 1.5)}px;
                opacity: 0; mix-blend-mode: screen;
                background: repeating-conic-gradient(from 0deg, #e0234e 0deg 9deg, transparent 9deg 18deg,
                            #2a6bff 18deg 27deg, transparent 27deg 36deg);
                -webkit-mask-image: radial-gradient(circle, transparent 0 22%, #000 42%),
                                    radial-gradient(circle, #000 2.2px, transparent 2.6px);
                -webkit-mask-size: 100% 100%, 12px 12px;
                -webkit-mask-composite: source-in; mask-composite: intersect; }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <video id="v" class="clip" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="0" muted playsinline></video>
    <audio id="a" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="9" data-volume="1"></audio>
    {raios_html}
    {rajada_html}
    {''.join(words_html)}
    <div id="flash"></div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    {chr(10).join("    " + ln for ln in tl).strip()}
    window.__timelines["main"] = tl;
  </script>
  </body>
</html>
"""
    (out / "index.html").write_text(html, encoding="utf-8")
    return out
