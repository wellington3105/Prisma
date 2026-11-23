#!/usr/bin/env python3
"""cenas.py: self-contained HyperFrames scenes built from data (host "cena" of the modelos library).

  python helpers/cenas.py build card-ficha dados.json -o <pasta>      # writes the project
  python helpers/cenas.py render <pasta>                               # -> <pasta>/out/render.mp4
  python helpers/cenas.py check card-ficha dados.json

A cena is a whole short clip (a spec card, a title card) that the edit then uses as an insert or a
B-roll, like any other clip. The data is the car's, the motion is the model's.

card-ficha — reverse-engineered on 2026-11-22 from a 10.5 s reel with no cuts (study, see
Prisma-Suite docs/analises/2026-11-22-formatos-de-referencia.md, F4). One continuous camera over
one card: the card grows in with an exposure flash, the camera pushes into the photo, slides down
while the spec pills come in, settles on the name (blur to sharp) and the version in grey, pulls
out to the whole card, pushes back in on the sentence while it types and pans along it, and pulls
out to rest. Our own layout, fonts (Poppins) and curves (prisma-eases.js); no asset of the source.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from hfkit.project import FONT_STACK, Project, esc, font_faces, hf_cli, run  # noqa: E402

W, H, FPS = 1080, 1920, 30
# Cenas render with their own HyperFrames release, not the Phase-2 pin (hfkit.project.HF_PIN):
# 0.8.93 leaves a 4-8 px black strip at the right edge of every frame (measured 2026-11-23 on a bare
# page); 0.9.85 does not. A cena has no Remotion parity to keep, so it can move first.
CENA_HF_PIN = "0.9.85"

# Icons drawn as inline SVG (stroke = currentColor). "cor" is a colour swatch (pill's "cor" key).
ICONES = {
    "cor": None,
    "cronometro": '<circle cx="12" cy="13" r="8"/><path d="M12 13l4-3M10 3h4M12 3v2"/>',
    "cambio": '<circle cx="12" cy="12" r="9"/><path d="M8 8v8M12 8v8M16 8v4M8 12h8"/>',
    "motor": '<path d="M4 10h3l2-2h5l2 2h2v6h-2l-2 2H9l-2-2H4z"/><path d="M1 12h3M20 13h3"/>',
    "km": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
    "ano": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
    "combustivel": '<path d="M5 20V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v15M4 20h11M14 9h2l2 2v6a1.5 1.5 0 0 0 3 0V9l-3-3"/>',
    "potencia": '<path d="M13 2L5 14h6l-1 8 8-12h-6z"/>',
}
MAX_PILULAS = 3

# Card geometry (px, 1080x1920 frame): 3:4 card, ~58 % of the width, like the source.
CW, CH = 620, 830
PHOTO_H = 440
PAD = 40

CENAS = {
    "card-ficha": {"duracao": 10.5, "duracao_sem_frase": 6.5,
                   "campos": ["foto", "titulo", "versao", "pilulas", "frase", "assinatura", "fundo", "foco", "zoom"]},
    # The hook of a talking-head Reel: a stretch of the clip (de..ate) with the three-voice title over it.
    "titulo-misto": {"campos": ["video", "de", "ate", "esquerda", "direita", "palavra", "sub", "acento", "cor",
                                "cards", "altura", "entra"]},
}


def validate(cena: str, dados: dict) -> list[str]:
    if cena not in CENAS:
        return [f"cena '{cena}' não existe (use {', '.join(CENAS)})"]
    probs = [f"campo '{k}' não é da cena {cena} (campos: {', '.join(CENAS[cena]['campos'])})"
             for k in dados if k not in CENAS[cena]["campos"]]
    if cena == "titulo-misto":
        import cenas_titulo
        return probs + cenas_titulo.validate(dados)
    foto = dados.get("foto")
    if not foto or not Path(foto).exists():
        probs.append(f"foto não encontrada: {foto!r}")
    if not str(dados.get("titulo", "")).strip():
        probs.append("titulo vazio")
    pills = dados.get("pilulas") or []
    if len(pills) > MAX_PILULAS:
        probs.append(f"{len(pills)} pílulas (no máximo {MAX_PILULAS}: o card respira)")
    for p in pills:
        if p.get("icone") and p["icone"] not in ICONES:
            probs.append(f"ícone '{p['icone']}' não existe (use {', '.join(ICONES)})")
    return probs


def _fit(text: str, max_px: int, width: int, em: float = 0.62) -> int:
    """Font size that fits `text` on one line of `width` px (Poppins bold ~0.62 em per char)."""
    n = max(1, len(text))
    return int(min(max_px, width / (em * n)))


def _icon(p: dict) -> str:
    ic = p.get("icone")
    if not ic:
        return ""
    if ic == "cor":
        return f'<span class="sw" style="background:{esc(p.get("cor", "#e6e6e6"))}"></span>'
    return (f'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONES[ic]}</svg>')


def _pill(p: dict) -> str:
    ic = _icon(p)
    txt = f'<span class="pt">{esc(p.get("texto", ""))}</span>'
    # The swatch leads, a symbol trails (as on the source card).
    inner = ic + txt if p.get("icone") == "cor" else txt + ic
    return f'<div class="pilula">{inner}</div>'


def _cam(s: float, fx: float, fy: float, ry: float = 0.0) -> dict:
    """Camera state that puts card point (fx, fy) (fractions of the card) at the frame centre."""
    dx, dy = (fx - 0.5) * CW, (fy - 0.5) * CH
    return {"scale": round(s, 4), "x": round(-dx * s, 2), "y": round(-dy * s, 2), "rotationY": ry}


def _photo_tone(foto: Path) -> tuple[int, int, int]:
    """Mean colour of the photo's bottom rows: where the photo fades into the card."""
    from PIL import Image
    im = Image.open(foto).convert("RGB")
    w, h = im.size
    band = im.crop((0, int(h * 0.80), w, h)).resize((1, 1), Image.BILINEAR)
    return band.getpixel((0, 0))


def _mix(c: tuple[int, int, int], k: float, to: int = 255) -> str:
    r, g, b = (round(v + (to - v) * k) for v in c)
    return f"rgb({r}, {g}, {b})"


def _js(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def _project(out: Path, dados: dict) -> Project:
    proj = Project(out, W, H, FPS)
    proj.init(None)
    pkg_f = out / "package.json"
    pkg = json.loads(pkg_f.read_text(encoding="utf-8"))
    pkg.setdefault("prisma", {})["hyperframes"] = CENA_HF_PIN
    pkg_f.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return proj


def _eases() -> str:
    return (HERE.parent / "assets" / "hyperframes" / "vendor" / "prisma-eases.js").read_text(encoding="utf-8")


def build(cena: str, dados: dict, out: Path) -> Path:
    probs = validate(cena, dados)
    if probs:
        raise SystemExit("dados da cena com problemas:\n  " + "\n  ".join(probs))
    proj = _project(Path(out), dados)
    if cena == "titulo-misto":
        import cenas_titulo
        return cenas_titulo.build(proj, dados)
    return _build_card(proj, cena, dados)


def _build_card(proj: Project, cena: str, dados: dict) -> Path:
    out = proj.root
    tone = _photo_tone(Path(dados["foto"]))
    foto = proj.asset(Path(dados["foto"]))

    titulo, versao = str(dados["titulo"]), str(dados.get("versao", ""))
    frase = str(dados.get("frase", "") or "").strip()
    fundo = dados.get("fundo") or _mix(tone, 0.45)
    card_bg = (f"linear-gradient(180deg, {_mix(tone, 0)} 0px, {_mix(tone, 0)} {int(PHOTO_H * 0.75)}px, "
               f"{_mix(tone, 0.32)} {PHOTO_H + 70}px, {_mix(tone, 0.4)} 100%)")
    foco = dados.get("foco", "center 62%")
    zoom = float(dados.get("zoom", 1.0))
    pills = dados.get("pilulas") or []
    tw = CW - 2 * PAD
    fs_t = _fit(titulo, 66, tw)
    fs_v = _fit(versao, 66, tw) if versao else 0
    dur = CENAS[cena]["duracao"] if frase else CENAS[cena]["duracao_sem_frase"]

    chars = "".join(f'<span class="ch">{esc(c)}</span>' for c in frase)
    y_pills = PHOTO_H + 38
    y_title = y_pills + 78
    y_ver = y_title + int(fs_t * 1.02)
    y_frase = y_ver + int((fs_v or fs_t) * 1.15) + 14

    # Camera path (seconds). Fractions of the card: photo ~.3, pills ~.6, name ~.73, sentence ~.9.
    fy_p = (y_pills + 26) / CH
    fy_t = (y_title + fs_t) / CH
    fy_f = (y_frase + 30) / CH
    tl = [
        ("set", "#cam", {**_cam(0.42, .5, .5, -10)}, 0),
        ("to", "#cam", {**_cam(1.0, .5, .5, 0), "duration": 0.62, "ease": "softLand"}, 0),
        ("fromTo", "#flash", [{"opacity": 0}, {"opacity": 0.62, "duration": 0.12, "ease": "cruise"}], 0.88),
        ("to", "#flash", {"opacity": 0, "duration": 0.35, "ease": "glide"}, 1.0),
        ("fromTo", "#foto", [{"filter": "blur(0px)"}, {"filter": "blur(7px)", "duration": 0.12, "ease": "cruise"}], 0.88),
        ("to", "#foto", {"filter": "blur(0px)", "duration": 0.3, "ease": "glide"}, 1.0),
        ("to", "#cam", {**_cam(2.15, .62, .32, 0), "duration": 0.42, "ease": "whip"}, 1.32),
        ("to", "#cam", {**_cam(2.0, .5, fy_p, 0), "duration": 1.0, "ease": "softInOut"}, 1.74),
        ("to", "#cam", {**_cam(1.9, .42, fy_t, 0), "duration": 1.1, "ease": "softInOut"}, 2.74),
        ("to", "#cam", {**_cam(1.0, .5, .5, 0), "duration": 0.38, "ease": "whip"}, 4.0),
        ("to", "#cam", {**_cam(0.94, .5, .5, 5), "duration": 1.0 if frase else 2.1, "ease": "cruise"}, 4.38),
    ]
    for i in range(len(pills)):
        tl.append(("fromTo", f"#pl{i}", [{"opacity": 0, "y": 18, "filter": "blur(8px)"},
                                         {"opacity": 1, "y": 0, "filter": "blur(0px)", "duration": 0.36,
                                          "ease": "softLand"}], round(2.0 + 0.13 * i, 3)))
    tl.append(("fromTo", "#titulo", [{"opacity": 0, "filter": "blur(14px)"},
                                     {"opacity": 1, "filter": "blur(0px)", "duration": 0.5, "ease": "softInOut"}], 2.7))
    if versao:
        tl.append(("fromTo", "#versao", [{"opacity": 0, "filter": "blur(14px)"},
                                         {"opacity": 1, "filter": "blur(0px)", "duration": 0.5, "ease": "softInOut"}],
                   3.0))
    if frase:
        t0, t1 = 6.0, 8.4
        step = (t1 - t0) / max(1, len(frase))
        tl += [
            ("to", "#cam", {**_cam(1.75, .36, fy_f - .03, 0), "duration": 0.55, "ease": "whip"}, 5.38),
            ("to", "#cam", {**_cam(1.75, .62, fy_f, 0), "duration": t1 - 5.93 + 0.2, "ease": "cruise"}, 5.93),
            ("to", "#cam", {**_cam(1.0, .5, .5, 0), "duration": 0.4, "ease": "whip"}, 8.6),
            ("to", "#cam", {**_cam(1.04, .5, .5, -3), "duration": dur - 9.0, "ease": "cruise"}, 9.0),
        ]
        tl.append(("chars", ".ch", step, t0))
    else:
        tl.append(("to", "#cam", {**_cam(1.0, .5, .5, 0), "duration": dur - 5.4, "ease": "cruise"}, 5.4))

    lines = ["const tl = gsap.timeline({ paused: true });"]
    for op, sel, v, at in tl:
        if op == "set":
            lines.append(f'tl.set("{sel}", {_js(v)}, {at});')
        elif op == "to":
            lines.append(f'tl.to("{sel}", {_js(v)}, {at});')
        elif op == "fromTo":
            lines.append(f'tl.fromTo("{sel}", {_js(v[0])}, {_js(v[1])}, {at});')
        elif op == "chars":
            lines.append(f'document.querySelectorAll("{sel}").forEach((c, i) => tl.set(c, {{ opacity: 1 }}, '
                         f'{at} + i * {round(v, 5)}));')

    pills_html = "".join(_pill(p).replace('<div class="pilula">', f'<div class="pilula" id="pl{i}">', 1)
                         for i, p in enumerate(pills))
    eases = (HERE.parent / "assets" / "hyperframes" / "vendor" / "prisma-eases.js").read_text(encoding="utf-8")
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
{font_faces(weights=(400, 600, 700))}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {esc(fundo)}; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: {esc(fundo)};
               font-family: {FONT_STACK}; perspective: 2200px; }}
      #cam {{ position: absolute; inset: 0; transform-origin: 50% 50%; will-change: transform; }}
      #card {{ position: absolute; left: {(W - CW) // 2}px; top: {(H - CH) // 2}px; width: {CW}px; height: {CH}px;
               border-radius: 44px; overflow: hidden; background: {card_bg};
               box-shadow: 0 46px 70px rgba(0,0,0,.24), 0 14px 24px rgba(0,0,0,.12); }}
      #foto {{ position: absolute; left: 0; top: 0; width: {CW}px; height: {PHOTO_H}px; object-fit: cover;
               object-position: {esc(foco)}; transform: scale({zoom}); transform-origin: {esc(foco)};
               -webkit-mask-image: linear-gradient(to bottom, #000 78%, transparent);
               mask-image: linear-gradient(to bottom, #000 78%, transparent); }}
      #pilulas {{ position: absolute; left: {PAD}px; top: {y_pills}px; display: flex; gap: 16px; }}
      .pilula {{ height: 50px; padding: 0 20px; border-radius: 25px; display: flex; align-items: center; gap: 10px;
                 background: linear-gradient(180deg, #d2d2d2, #c6c6c6); color: #3b3b3b; font-weight: 600;
                 font-size: 23px; box-shadow: inset 0 2px 4px rgba(0,0,0,.2), 0 1px 0 rgba(255,255,255,.85);
                 opacity: 0; }}
      .sw {{ width: 26px; height: 26px; border-radius: 50%; box-shadow: inset 0 1px 3px rgba(0,0,0,.3), 0 0 0 2px #f4f4f4; }}
      .ic {{ width: 28px; height: 28px; }}
      #titulo {{ position: absolute; left: {PAD}px; top: {y_title}px; font-size: {fs_t}px; font-weight: 700;
                 letter-spacing: -0.03em; line-height: 1; color: #2a2a2a; white-space: nowrap; opacity: 0; }}
      #versao {{ position: absolute; left: {PAD + 2}px; top: {y_ver}px; font-size: {fs_v}px; font-weight: 600;
                 letter-spacing: -0.02em; line-height: 1; color: #8b8b8b; white-space: nowrap; opacity: 0; }}
      #frase {{ position: absolute; left: {PAD}px; top: {y_frase}px; width: {tw}px; font-size: 24px; font-weight: 400;
                line-height: 1.32; color: #303030; }}
      .ch {{ opacity: 0; }}
      #assinatura {{ position: absolute; left: 0; right: 0; bottom: 18px; text-align: center; font-size: 16px;
                     font-weight: 600; color: #8f8f8f; }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; pointer-events: none; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <div id="cam">
      <div id="card">
        <img id="foto" src="{esc(foto)}" alt="">
        <div id="pilulas">{pills_html}</div>
        <div id="titulo">{esc(titulo)}</div>
        {f'<div id="versao">{esc(versao)}</div>' if versao else ''}
        {f'<div id="frase">{chars}</div>' if frase else ''}
        <div id="assinatura">{esc(dados.get("assinatura", ""))}</div>
      </div>
    </div>
    <div id="flash"></div>
  </div>
  <script>
    window.__timelines = window.__timelines || {{}};
    {chr(10).join("    " + ln for ln in lines).strip()}
    window.__timelines["main"] = tl;
  </script>
  </body>
</html>
"""
    (out / "index.html").write_text(html, encoding="utf-8")
    return out


def render(proj: Path, log: Path | None = None) -> Path:
    proj = Path(proj)
    r = run(hf_cli(CENA_HF_PIN) + ["render", "--fps", str(FPS), "--quality", "delivery", "-o", "out/render.mp4"], cwd=str(proj))
    if log:
        Path(log).write_text((r.stdout or "") + (r.stderr or ""), encoding="utf-8")
    return proj / "out" / "render.mp4"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("cena", choices=sorted(CENAS))
    b.add_argument("dados", type=Path)
    b.add_argument("-o", "--out", type=Path, required=True)
    b.add_argument("--render", action="store_true")
    r = sub.add_parser("render")
    r.add_argument("proj", type=Path)
    c = sub.add_parser("check")
    c.add_argument("cena")
    c.add_argument("dados", type=Path)
    a = ap.parse_args()
    if a.cmd == "build":
        out = build(a.cena, json.loads(a.dados.read_text(encoding="utf-8")), a.out)
        print(f"  cena {a.cena} → {out}")
        if a.render:
            print(f"  render → {render(out)}")
    elif a.cmd == "render":
        print(f"  render → {render(a.proj)}")
    else:
        probs = validate(a.cena, json.loads(a.dados.read_text(encoding="utf-8")))
        for p in probs:
            print("  problema:", p)
        return 1 if probs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
