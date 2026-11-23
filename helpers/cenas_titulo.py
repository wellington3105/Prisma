"""cenas_titulo.py: the "titulo-misto" cena (called by cenas.py; not a CLI of its own).

Reverse-engineered on 2026-11-23 from a reference Reel (F3 in Prisma-Suite
docs/analises/2026-11-22-formatos-de-referencia.md; study only, nothing of it is copied):
a hook title in three voices over the talking head:
  - two small sans words that frame the title (left above its start, right above its end);
  - one giant heavy word in the accent colour, born as a red glow with scattered pixel blocks,
    announced by a thin streak falling from the top, then sharp;
  - a sub line word by word (blur to sharp), one word of it may be the serif-italic accent;
  - up to two photo cards that fly in from the bottom left with a light flash and land tilted.
Measured at 8 fps: small words settle in ~0.15 s, streak 0.15 s, giant word sharp in ~0.4 s,
pixel blocks gone ~0.35 s later, sub words every ~0.14 s, cards ~0.4 s each, 0.15 s apart.
Fonts are ours (Poppins 900 / 600, Lora 700 italic); curves are prisma-eases.js.
"""
from __future__ import annotations

import json
import random
import subprocess
import tempfile
from pathlib import Path

from hfkit.project import FONT_STACK, Project, esc, font_faces

W, H = 1080, 1920
MAX_CARDS = 2


def validate(dados: dict) -> list[str]:
    probs = []
    v = dados.get("video")
    if not v or not Path(v).exists():
        probs.append(f"video não encontrado: {v!r}")
    if not str(dados.get("palavra", "")).strip():
        probs.append("palavra (a gigante) vazia")
    de, ate = float(dados.get("de", 0)), float(dados.get("ate", 0))
    if ate <= de:
        probs.append(f"ate ({ate}) precisa ser maior que de ({de})")
    elif v and Path(v).exists():
        dur = _probe_dur(Path(v))
        if dur and ate > dur + 0.05:
            probs.append(f"ate ({ate}) passa do fim do video ({dur:.2f} s)")
    cards = dados.get("cards") or []
    if len(cards) > MAX_CARDS:
        probs.append(f"{len(cards)} cards (no máximo {MAX_CARDS})")
    for c in cards:
        if not Path(c).exists():
            probs.append(f"card não encontrado: {c!r}")
    ac = str(dados.get("acento", "") or "")
    if ac and ac not in str(dados.get("sub", "")).split():
        probs.append(f"acento '{ac}' precisa ser uma palavra da sub")
    return probs


def _probe_dur(v: Path) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(v)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def _ink(video: Path, t: float, altura: float) -> str:
    """Dark ink over a light background, white over a dark one (mean luma of the title band)."""
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", str(f)],
                       capture_output=True)
        if not f.exists():
            return "#ffffff"
        im = Image.open(f).convert("L")
        y = int(H * altura)
        band = im.crop((0, max(0, y - 220), W, min(H, y + 320))).resize((1, 1), Image.BILINEAR)
        return "#151515" if band.getpixel((0, 0)) > 140 else "#ffffff"


def _js(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def build(proj: Project, dados: dict) -> Path:
    out = proj.root
    video = Path(dados["video"])
    src = proj.asset(video)
    de, ate = float(dados.get("de", 0)), float(dados["ate"])
    dur = round(ate - de, 6)
    altura = float(dados.get("altura", 0.17))
    t0 = float(dados.get("entra", 0.25))
    cor = dados.get("cor", "#c8102e")
    ink = _ink(video, de + min(dur, t0 + 1.2), altura)
    shade = "rgba(255,255,255,.55)" if ink != "#ffffff" else "rgba(0,0,0,.45)"

    palavra = str(dados["palavra"])
    fs = int(min(230, 880 / (0.72 * max(1, len(palavra)))))
    word_w = int(min(900, 0.72 * fs * len(palavra)))
    cy = int(H * altura)
    small = max(40, int(fs * 0.27))
    sub_fs = max(40, int(fs * 0.24))

    sub = str(dados.get("sub", "") or "").split()
    acento = str(dados.get("acento", "") or "")
    sub_html = " ".join(
        f'<span class="sw acento">{esc(w)}</span>' if w == acento else f'<span class="sw">{esc(w)}</span>'
        for w in sub)

    rnd = random.Random(palavra)          # same word, same scatter: deterministic renders
    px = []
    for i in range(9):
        s = rnd.choice((26, 32, 40, 48))
        x = int(W / 2 + rnd.uniform(-0.62, 0.62) * word_w)
        y = int(cy + rnd.uniform(-0.75, 0.85) * fs)
        op = rnd.choice((1.0, 0.75, 0.45))
        px.append(f'<div class="px" id="px{i}" style="left:{x}px;top:{y}px;width:{s}px;height:{s}px;'
                  f'opacity:0;--o:{op}"></div>')

    cards = [proj.asset(Path(c)) for c in (dados.get("cards") or [])]
    card_y = cy + int(fs * 0.62) + sub_fs + 70
    rest = [(-8, 70, card_y), (-17, 30, card_y + 110)]
    cards_html = "".join(
        f'<div class="cartao" id="cd{j}" style="left:{rest[j][1]}px;top:{rest[j][2]}px;z-index:{5 - j}">'
        f'<img src="{esc(c)}" alt=""><div class="brilho"></div></div>' for j, c in enumerate(cards))

    tl = ["const tl = gsap.timeline({ paused: true });"]
    a = lambda sel, fr, to, at: tl.append(f'tl.fromTo("{sel}", {_js(fr)}, {_js(to)}, {round(at, 3)});')  # noqa: E731
    if dados.get("esquerda"):
        a("#esq", {"opacity": 0, "x": -70, "filter": "blur(12px)"},
          {"opacity": 1, "x": 0, "filter": "blur(0px)", "duration": 0.28, "ease": "whip"}, t0)
    if dados.get("direita"):
        a("#dir", {"opacity": 0, "x": 70, "filter": "blur(12px)"},
          {"opacity": 1, "x": 0, "filter": "blur(0px)", "duration": 0.28, "ease": "whip"}, t0 + 0.05)
    a("#risco", {"scaleY": 0, "opacity": 1}, {"scaleY": 1, "duration": 0.15, "ease": "cruise"}, t0 + 0.3)
    tl.append(f'tl.to("#risco", {{"opacity":0,"duration":0.1}}, {round(t0 + 0.45, 3)});')
    a("#palavra", {"opacity": 0, "scale": 1.15, "filter": "blur(26px)"},
      {"opacity": 1, "scale": 1, "filter": "blur(0px)", "duration": 0.42, "ease": "softLand"}, t0 + 0.45)
    a("#brilho", {"opacity": 0}, {"opacity": 0.95, "duration": 0.08, "ease": "cruise"}, t0 + 0.45)
    tl.append(f'tl.to("#brilho", {{"opacity":0,"duration":0.6,"ease":"glide"}}, {round(t0 + 0.55, 3)});')
    for i in range(9):
        on = t0 + 0.45 + i * 0.02
        tl.append(f'tl.set("#px{i}", {{opacity: getComputedStyle(document.getElementById("px{i}"))'
                  f'.getPropertyValue("--o")}}, {round(on, 3)});')
        tl.append(f'tl.set("#px{i}", {{opacity: 0.25}}, {round(on + 0.14, 3)});')
        tl.append(f'tl.set("#px{i}", {{opacity: 0.9}}, {round(on + 0.22, 3)});')
        tl.append(f'tl.set("#px{i}", {{opacity: 0}}, {round(t0 + 0.75 + i * 0.03, 3)});')
    for k in ("#orn0", "#orn1"):
        a(k, {"opacity": 0, "scale": 0, "rotation": -40},
          {"opacity": 1, "scale": 1, "rotation": 18, "duration": 0.45, "ease": "popOver"}, t0 + 0.55)
    for i in range(len(sub)):
        a(f".sw:nth-child({i + 1})", {"opacity": 0, "y": 12, "filter": "blur(10px)"},
          {"opacity": 1, "y": 0, "filter": "blur(0px)", "duration": 0.3, "ease": "softLand"}, t0 + 0.95 + i * 0.14)
    for j in range(len(cards)):
        at = t0 + 1.0 + j * 0.15
        a(f"#cd{j}", {"opacity": 0, "x": -420, "y": 520, "rotation": -35, "filter": "blur(14px)"},
          {"opacity": 1, "x": 0, "y": 0, "rotation": rest[j][0], "filter": "blur(0px)", "duration": 0.42,
           "ease": "whip"}, at)
        a(f"#cd{j} .brilho", {"opacity": 0.9}, {"opacity": 0, "duration": 0.4, "ease": "glide"}, at + 0.2)

    eases = (Path(__file__).resolve().parent.parent / "assets" / "hyperframes" / "vendor" / "prisma-eases.js").read_text(
        encoding="utf-8")
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
{font_faces(weights=(600, 900))}
{font_faces(families=("PrismaLora",), weights=(700,))}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: #000;
               font-family: {FONT_STACK}; }}
      #v {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      .t {{ position: absolute; left: 0; right: 0; text-align: center; white-space: nowrap; }}
      #pequenas {{ position: absolute; left: {(W - word_w) // 2}px; width: {word_w}px; top: {cy - int(fs * 0.62) - small}px;
                   display: flex; justify-content: space-between; font-weight: 600; font-size: {small}px;
                   color: {ink}; letter-spacing: -0.02em; text-shadow: 0 2px 14px {shade}; }}
      #esq, #dir {{ opacity: 0; }}
      #dir {{ margin-top: {int(small * 0.18)}px; }}
      #palavra, #brilho {{ top: {cy - int(fs * 0.6)}px; font-weight: 900; font-size: {fs}px; line-height: 1;
                           letter-spacing: -0.045em; color: {esc(cor)}; }}
      #palavra {{ opacity: 0; text-shadow: 0 6px 30px rgba(0,0,0,.18); }}
      #brilho {{ opacity: 0; filter: blur(34px); }}
      #risco {{ position: absolute; left: {W // 2 - 3}px; top: 0; width: 6px; height: {cy}px; background: {esc(cor)};
                transform-origin: 50% 0; transform: scaleY(0); }}
      .px {{ position: absolute; background: {esc(cor)}; }}
      .orn {{ position: absolute; top: {cy - 18}px; width: 34px; height: 34px; border: 4px solid {ink};
              border-radius: 10px; opacity: 0; }}
      #orn0 {{ left: {(W - word_w) // 2 - 64}px; }}
      #orn1 {{ left: {(W + word_w) // 2 + 30}px; }}
      #sub {{ top: {cy + int(fs * 0.46)}px; font-weight: 600; font-size: {sub_fs}px; color: {ink};
              letter-spacing: -0.02em; text-shadow: 0 2px 14px {shade}; }}
      .sw {{ display: inline-block; opacity: 0; }}
      .sw.acento {{ font-family: 'PrismaLora', serif; font-style: italic; font-weight: 700; color: {esc(cor)};
                    font-size: 1.18em; }}
      .cartao {{ position: absolute; width: 230px; height: 300px; border-radius: 22px; overflow: hidden;
                 border: 6px solid #fff; box-shadow: 0 24px 40px rgba(0,0,0,.35); opacity: 0; }}
      .cartao img {{ width: 100%; height: 100%; object-fit: cover; }}
      .brilho {{ position: absolute; inset: 0; background: #fff; opacity: 0; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <video id="v" class="clip" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="0" muted playsinline></video>
    <audio id="a" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="9" data-volume="1"></audio>
    <div id="risco"></div>
    <div id="brilho" class="t">{esc(palavra)}</div>
    {''.join(px)}
    <div id="palavra" class="t">{esc(palavra)}</div>
    <div id="pequenas"><span id="esq">{esc(dados.get("esquerda", ""))}</span><span id="dir">{esc(dados.get("direita", ""))}</span></div>
    <div class="orn" id="orn0"></div><div class="orn" id="orn1"></div>
    <div id="sub" class="t">{sub_html}</div>
    {cards_html}
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
