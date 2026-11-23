"""cenas_antes.py: the "antes-depois" cena (called by cenas.py; not a CLI of its own).

Reverse-engineered on 2026-11-23 from two reference Reels (study only; F1 and F8 in Prisma-Suite
docs/analises/2026-11-22-formatos-de-referencia.md):

  lado (F8)       two phones on a dark vignette, playing in sync: a small "Antes" on the left and
                  behind (~32 % of the width, 24-60 % of the height), a big "Depois" on the right
                  (~55 % of the width, 15-70 % of the height), each with a white label pill on its
                  top edge; a fixed two-line CTA below (small grey line + bold white line).
  sequencia (F1)  full frame: the raw take first, then a hard cut (one-frame flash) to the edited
                  take; one white pill at the top swaps its label on the cut.

The sound is the edited take's in "lado" (`som` = antes to swap); in "sequencia" each part keeps its own.
"""
from __future__ import annotations

from pathlib import Path

from cenas_titulo import _probe_dur
from hfkit.project import FONT_STACK, Project, esc, font_faces

W, H = 1080, 1920
LAYOUTS = ("lado", "sequencia")
MAX_DUR = 30.0
# phone boxes (left, top, width, height) in px, 9:16 screens
BOX_ANTES = (65, 461, 346, 615)
BOX_DEPOIS = (410, 288, 594, 1056)


def validate(dados: dict) -> list[str]:
    probs = []
    lay = dados.get("layout", "lado")
    if lay not in LAYOUTS:
        probs.append(f"layout '{lay}' não existe (use {', '.join(LAYOUTS)})")
    dur = float(dados.get("duracao", 0) or 0)
    if not 0 < dur <= MAX_DUR:
        probs.append(f"duracao {dur} s (entre 0 e {MAX_DUR:g} s)")
    corte = float(dados.get("corte", 1.6))
    if lay == "sequencia" and not 0 < corte < dur:
        probs.append(f"corte {corte} s precisa cair dentro da duracao ({dur} s)")
    need = {"antes": corte if lay == "sequencia" else dur,
            "depois": (dur if lay == "lado" else corte + (dur - corte))}
    for k in ("antes", "depois"):
        v = dados.get(k)
        if not v or not Path(v).exists():
            probs.append(f"{k}: vídeo não encontrado: {v!r}")
            continue
        n = _probe_dur(Path(v))
        de = float(dados.get(f"de_{k}", 0))
        if n and de + need[k] > n + 0.05:
            probs.append(f"{k}: de_{k} + {need[k]:g} s passa do fim do vídeo ({n:.2f} s)")
    if dados.get("som", "depois") not in ("antes", "depois"):
        probs.append("som: use antes ou depois")
    return probs


def build(proj: Project, dados: dict) -> Path:
    out = proj.root
    lay = dados.get("layout", "lado")
    dur = float(dados["duracao"])
    a, b = proj.asset(Path(dados["antes"])), proj.asset(Path(dados["depois"]))
    da, db = float(dados.get("de_antes", 0)), float(dados.get("de_depois", 0))
    ra, rb = str(dados.get("rotulo_antes", "Antes")), str(dados.get("rotulo_depois", "Depois"))
    cta = [x for x in str(dados.get("cta", "") or "").split("|") if x][:2]
    fundo = dados.get("fundo", "radial-gradient(circle at 50% 40%, #3a3a3c 0%, #1a1a1b 70%, #111 100%)")
    tl = ["const tl = gsap.timeline({ paused: true });"]

    if lay == "lado":
        def fone(cls, vid, src, de, box, rot):
            x, y, w, h = box
            return (f'<div class="fone {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">'
                    f'<video id="{vid}" class="clip" src="{esc(src)}" data-start="0" data-duration="{dur:g}" '
                    f'data-media-start="{de:g}" data-track-index="{0 if cls == "antes" else 1}" muted playsinline></video>'
                    f'<div class="pilula">{esc(rot)}</div></div>')
        corpo = fone("antes", "va", a, da, BOX_ANTES, ra) + fone("depois", "vb", b, db, BOX_DEPOIS, rb)
        som_src, som_de = (a, da) if dados.get("som") == "antes" else (b, db)
        audio = (f'<audio id="a" src="{esc(som_src)}" data-start="0" data-duration="{dur:g}" '
                 f'data-media-start="{som_de:g}" data-track-index="9" data-volume="1"></audio>')
        tl += ['tl.fromTo(".fone.antes", {opacity:0, y:60, scale:0.94}, {opacity:1, y:0, scale:1, duration:0.5, ease:"softLand"}, 0);',
               'tl.fromTo(".fone.depois", {opacity:0, y:80, scale:0.94}, {opacity:1, y:0, scale:1, duration:0.55, ease:"softLand"}, 0.08);',
               'tl.fromTo(".pilula", {opacity:0, scale:0.6}, {opacity:1, scale:1, duration:0.3, ease:"popOver", stagger:0.08}, 0.35);',
               'tl.fromTo("#cta", {opacity:0, y:20}, {opacity:1, y:0, duration:0.45, ease:"softLand"}, 0.5);']
        cta_html = ""
        if cta:
            l1 = f'<div class="l1">{esc(cta[0])}</div>' if len(cta) == 2 else ""
            cta_html = f'<div id="cta">{l1}<div class="l2">{esc(cta[-1])}</div></div>'
        css = f"""
      .fone {{ position: absolute; border-radius: 46px; border: 7px solid #0d0d0e; background: #000;
               box-shadow: 0 30px 60px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.08); opacity: 0; }}
      .fone video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 39px; }}
      .fone.antes {{ z-index: 1; border-radius: 30px; border-width: 5px; }}
      .fone.antes video {{ border-radius: 25px; }}
      .fone.depois {{ z-index: 2; }}
      .pilula {{ position: absolute; left: 50%; top: -20px; transform: translateX(-50%); background: #fff; color: #161616;
                 font-weight: 600; font-size: 24px; line-height: 1; padding: 8px 20px; border-radius: 999px; z-index: 3;
                 box-shadow: 0 4px 12px rgba(0,0,0,.35); }}
      .fone.antes .pilula {{ font-size: 20px; padding: 6px 16px; top: -16px; }}
      #cta {{ position: absolute; left: 0; right: 0; top: {int(H * 0.765)}px; text-align: center; opacity: 0; }}
      #cta .l1 {{ color: #b9b9bb; font-size: 36px; font-weight: 400; }}
      #cta .l2 {{ color: #fff; font-size: 58px; font-weight: 800; margin-top: 6px; letter-spacing: -0.01em; }}"""
    else:
        corte = float(dados.get("corte", 1.6))
        corpo = (f'<video id="va" class="clip cheia" src="{esc(a)}" data-start="0" data-duration="{corte:g}" '
                 f'data-media-start="{da:g}" data-track-index="0" muted playsinline></video>'
                 f'<video id="vb" class="clip cheia" src="{esc(b)}" data-start="{corte:g}" data-duration="{dur - corte:g}" '
                 f'data-media-start="{db + corte:g}" data-track-index="1" muted playsinline></video>'
                 f'<div class="pilula topo"><span id="ra">{esc(ra)}</span><span id="rb">{esc(rb)}</span></div>'
                 f'<div id="flash"></div>')
        audio = (f'<audio id="aa" src="{esc(a)}" data-start="0" data-duration="{corte:g}" data-media-start="{da:g}" '
                 f'data-track-index="8" data-volume="1"></audio>'
                 f'<audio id="ab" src="{esc(b)}" data-start="{corte:g}" data-duration="{dur - corte:g}" '
                 f'data-media-start="{db + corte:g}" data-track-index="9" data-volume="1"></audio>')
        tl += ['tl.fromTo(".pilula", {opacity:0, y:-20}, {opacity:1, y:0, duration:0.35, ease:"softLand"}, 0.1);',
               f"/* corte @{corte:g} */",
               f'tl.set("#ra", {{display:"none"}}, {corte}); tl.set("#rb", {{display:"inline"}}, {corte});',
               f'tl.set("#flash", {{opacity:0.9}}, {corte}); tl.to("#flash", {{opacity:0, duration:0.15, ease:"glide"}}, {corte + 1 / 30:.4f});',
               f'tl.fromTo(".pilula", {{scale:1.18}}, {{scale:1, duration:0.25, ease:"popOver", immediateRender:false}}, {corte});']
        cta_html = ""
        css = f"""
      .cheia {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      .pilula.topo {{ position: absolute; left: 50%; top: {int(H * 0.055)}px; transform: translateX(-50%); background: #fff;
                      color: #161616; font-weight: 600; font-size: 34px; line-height: 1; padding: 12px 30px; border-radius: 999px;
                      box-shadow: 0 6px 18px rgba(0,0,0,.3); opacity: 0; z-index: 3; }}
      #rb {{ display: none; }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; z-index: 4; }}"""

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
{font_faces(weights=(400, 600, 800))}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #111; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: {fundo};
               font-family: {FONT_STACK}; }}{css}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{dur:g}">
    {corpo}
    {audio}
    {cta_html}
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
