"""Cenas de motion HTML (HyperFrames) no estilo vidro-prisma da série XC60.

Cada função devolve o HTML de UMA sub-composição (contrato HyperFrames:
<template>, #root com data-composition-id, timeline GSAP pausada registrada em
window.__timelines, só transforms/opacity/strokes animados, nada aleatório).
O conteúdo é escrito estático no HTML — editável no Studio.

Linguagem visual = GlassCard `prism` do Remotion: placa fosca com backdrop blur,
espessura recuada em Z, perspectiva que gira devagar, aro iridescente fino em
anel (máscara), reflexo especular que varre a placa, rótulo com traço laranja.
"""
from __future__ import annotations

ACCENT = "#ff5200"

BASE_CSS = """
#root{position:absolute;inset:0;overflow:hidden;pointer-events:none;font-family:"Poppins",Inter,sans-serif;color:#fff}
.p-scrim{position:absolute;left:0;right:0;top:0;height:66%;opacity:0;
  background:linear-gradient(180deg,rgba(0,0,0,.6) 0%,rgba(0,0,0,.34) 55%,rgba(0,0,0,0) 100%)}
.p-stage{position:absolute;left:0;right:0;top:__TOP__px;display:flex;justify-content:center;perspective:1500px}
.p-slab{position:relative;transform-style:preserve-3d;opacity:0}
.p-depth{position:absolute;inset:0;border-radius:38px;transform:translateZ(-24px);
  background:linear-gradient(160deg,rgba(255,255,255,.16),rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.18);box-shadow:0 60px 110px rgba(0,0,0,.55)}
.p-card{position:relative;border-radius:38px;overflow:hidden;width:__W__px;padding:46px 56px 52px;
  backdrop-filter:blur(20px) saturate(1.45) brightness(1.04);-webkit-backdrop-filter:blur(20px) saturate(1.45) brightness(1.04);
  background:linear-gradient(135deg,rgba(255,255,255,.24) 0%,rgba(255,255,255,.07) 42%,rgba(14,18,28,.6) 100%);
  box-shadow:inset 0 2px 0 rgba(255,255,255,.62),inset 0 -2px 0 rgba(0,0,0,.35),-3px 0 16px rgba(255,50,110,.22),3px 0 16px rgba(50,150,255,.24)}
.p-ring{position:absolute;inset:0;border-radius:38px;padding:2.5px;z-index:4;
  background:conic-gradient(from var(--ang,0deg),rgba(255,90,130,.85),rgba(255,220,120,.75),rgba(120,255,210,.7),rgba(110,190,255,.9),rgba(200,130,255,.8),rgba(255,90,130,.85));
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
.p-sweepT{position:absolute;inset:0;z-index:3}
.p-sweep{position:absolute;top:-40%;bottom:-40%;left:-45%;width:38%;transform:rotate(18deg);
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.42),transparent);mix-blend-mode:screen}
.p-label{position:relative;display:flex;align-items:center;gap:16px;font-size:27px;font-weight:600;letter-spacing:6px;
  text-transform:uppercase;color:rgba(255,255,255,.88);margin-bottom:28px}
.p-label i{display:block;width:46px;height:3px;border-radius:2px;background:__A__;box-shadow:0 0 14px __A__}
.p-disp{text-shadow:-1.5px 0 rgba(255,60,110,.42),1.5px 0 rgba(60,170,255,.42),0 4px 22px rgba(0,0,0,.45)}
.p-num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
"""

IN_OUT_JS = """
var slab=root.querySelector(".p-slab"),scrim=root.querySelector(".p-scrim"),ring=root.querySelector(".p-ring"),sw=root.querySelector(".p-sweepT");
gsap.set(slab,{rotationY:-36,rotationX:14,scale:.86,opacity:0,transformPerspective:1500});
tl.to(scrim,{opacity:1,duration:.4,ease:"power2.out"},0);
tl.to(slab,{rotationY:-12,rotationX:6,scale:1,opacity:1,duration:.75,ease:"back.out(1.4)"},.05);
tl.to(slab,{rotationY:-4,rotationX:3,duration:Math.max(.1,D-1.25),ease:"sine.inOut"},.8);
tl.fromTo(ring,{"--ang":"0deg"},{"--ang":"360deg",duration:D,ease:"none"},0);
gsap.set(sw,{x:-260});
tl.to(sw,{x:1500,duration:.75,ease:"power2.inOut"},.3);
tl.set(sw,{x:-260},Math.max(1.2,D*.55)-.01);
tl.to(sw,{x:1500,duration:.9,ease:"power2.inOut"},Math.max(1.2,D*.55));
tl.to(slab,{opacity:0,rotationY:10,scale:.96,duration:.34,ease:"power2.in"},D-.42);
tl.to(scrim,{opacity:0,duration:.34,ease:"power2.in"},D-.42);
"""


def _scene(cid: str, dur: float, body: str, css: str, js: str, top: int = 360, width: int = 860) -> str:
    base = BASE_CSS.replace("__TOP__", str(top)).replace("__W__", str(width)).replace("__A__", ACCENT)
    return f"""<!doctype html>
<html lang="pt" data-composition-id="{cid}" data-composition-duration="{dur:.2f}">
  <head><meta charset="UTF-8" /><title>{cid}</title></head>
  <body>
    <template>
      <div id="root" data-composition-id="{cid}" data-duration="{dur:.2f}" data-fps="30" data-width="1080" data-height="1920">
        <style>{base}{css}</style>
        <div class="p-scrim"></div>
        <div class="p-stage"><div class="p-slab">
          <div class="p-depth"></div>
          <div class="p-card">
            <div class="p-sweepT"><div class="p-sweep"></div></div>
            {body}
          </div>
          <div class="p-ring"></div>
        </div></div>
        <script>
          (function () {{
            "use strict";
            var root = document.getElementById("root");
            var D = {dur:.3f};
            var tl = gsap.timeline({{ paused: true }});
            {IN_OUT_JS}
            {js}
            tl.seek(0);
            window.__timelines = window.__timelines || {{}};
            window.__timelines["{cid}"] = tl;
          }})();
        </script>
      </div>
    </template>
  </body>
</html>
"""


def _count_rows(sel: str, a: float, b: float, t0: float, dur: float, fmt: str) -> str:
    """Contagem determinística: um tl.set por frame (sem callbacks)."""
    return f"""
(function(){{var el=root.querySelector("{sel}");var n=Math.max(1,Math.round({dur}*30));var ez=gsap.parseEase("power2.out");
for(var f=0;f<=n;f++){{var v={a}+({b}-{a})*ez(f/n);tl.set(el,{{textContent:{fmt}}},{t0}+{dur}*(f/n));}}}})();
"""


# ----------------------------------------------------------------------------- cenas

def count(cid, dur, start, end, suffix, label, sub, prefix=""):
    """Número grande contando + texto. Ex.: 0→19 alto-falantes; 1º→3º no ranking."""
    css = """
.c-row{position:relative;display:flex;align-items:center;gap:40px}
.c-val{font-size:190px;font-weight:800;line-height:.9;letter-spacing:-6px;color:#fff}
.c-val small{font-size:.42em;letter-spacing:0;color:__A__;margin-left:4px;vertical-align:top}
.c-txt{font-size:44px;font-weight:600;line-height:1.12}
.c-txt span{display:block;font-weight:400;font-size:32px;color:rgba(255,255,255,.78);margin-top:10px}
""".replace("__A__", ACCENT)
    body = f"""<div class="p-label"><i></i>{label}</div>
<div class="c-row"><div class="c-val p-disp p-num">{prefix}<b class="c-n">{start}</b><small>{suffix}</small></div>
<div class="c-txt p-disp">{sub[0]}<span>{sub[1]}</span></div></div>"""
    js = _count_rows(".c-n", start, end, .55, 1.1, "Math.round(v)") + """
var row=root.querySelector(".c-row"),val=root.querySelector(".c-val");
gsap.set(row,{opacity:0,y:30});tl.to(row,{opacity:1,y:0,duration:.5,ease:"power3.out"},.35);
tl.to(val,{scale:1.08,duration:.16,ease:"power3.out"},1.65);tl.to(val,{scale:1,duration:.2,ease:"power2.out"},1.81);
"""
    return _scene(cid, dur, body, css, js)


def rank(cid, dur, label, rows, hi):
    """Pódio: linhas 1º, 2º… com a linha `hi` em destaque (barra laranja + pulso)."""
    css = """
.r-row{position:relative;display:flex;align-items:center;gap:30px;height:104px;margin-top:16px;padding:0 30px;border-radius:24px;
  background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12)}
.r-row.hi{background:linear-gradient(90deg,rgba(255,82,0,.38),rgba(255,82,0,.08));border-color:rgba(255,140,80,.55)}
.r-ord{font-size:64px;font-weight:800;width:110px}
.r-name{font-size:50px;font-weight:700;letter-spacing:2px}
.r-row.dim .r-name{color:rgba(255,255,255,.45);font-weight:500}
"""
    rws = "".join(
        f'<div class="r-row{" hi" if i == hi else " dim" if r[1] in ("", "—") else ""}"><div class="r-ord p-disp">{r[0]}</div>'
        f'<div class="r-name p-disp">{r[1] or "—"}</div></div>' for i, r in enumerate(rows))
    body = f'<div class="p-label"><i></i>{label}</div>{rws}'
    js = f"""
var rs=root.querySelectorAll(".r-row");gsap.set(rs,{{opacity:0,x:-60}});
rs.forEach(function(r,i){{tl.to(r,{{opacity:1,x:0,duration:.45,ease:"power3.out"}},.45+i*.18);}});
var h=rs[{hi}];tl.to(h,{{scale:1.05,duration:.18,ease:"power3.out"}},.45+{len(rows)}*.18+.15);
tl.to(h,{{scale:1,duration:.22,ease:"power2.out"}},.45+{len(rows)}*.18+.33);
"""
    return _scene(cid, dur, body, css, js)


def compare(cid, dur, label, rows, chip):
    """Barras comparando valores. rows = [(nome, valor_num, texto_fmt, pct, destaque)]."""
    css = """
.k-row{position:relative;margin-top:30px}
.k-top{display:flex;justify-content:space-between;align-items:baseline;font-size:36px;font-weight:600}
.k-top .k-v{font-size:58px;font-weight:800}
.k-track{position:relative;height:34px;margin-top:14px;border-radius:17px;background:rgba(255,255,255,.1);overflow:hidden}
.k-fill{position:absolute;left:0;top:0;bottom:0;width:100%;border-radius:17px;transform-origin:0 50%;background:rgba(255,255,255,.55)}
.k-row.hi .k-fill{background:linear-gradient(90deg,#ff7a2e,__A__);box-shadow:0 0 22px rgba(255,82,0,.55)}
.k-row.hi .k-v{color:#ffb38a}
.k-chip{position:relative;display:inline-block;margin-top:34px;padding:12px 26px;border-radius:999px;font-size:32px;font-weight:700;
  background:rgba(255,82,0,.22);border:1px solid rgba(255,140,80,.6)}
""".replace("__A__", ACCENT)
    body = f'<div class="p-label"><i></i>{label}</div>' + "".join(
        f'<div class="k-row{" hi" if r[4] else ""}"><div class="k-top"><span class="p-disp">{r[0]}</span>'
        f'<span class="k-v p-disp p-num" id="{cid}-v{i}">R$ 0 mil</span></div>'
        f'<div class="k-track"><div class="k-fill" id="{cid}-f{i}"></div></div></div>' for i, r in enumerate(rows)) + \
        f'<div class="k-chip p-disp">{chip}</div>'
    js = ""
    for i, r in enumerate(rows):
        t0 = .55 + i * .35
        js += f'gsap.set(root.querySelector("#{cid}-f{i}"),{{scaleX:0}});' \
              f'tl.to(root.querySelector("#{cid}-f{i}"),{{scaleX:{r[3]},duration:1.1,ease:"power3.out"}},{t0});'
        js += _count_rows(f"#{cid}-v{i}", 0, r[1], t0, 1.1, '"R$ "+Math.round(v)+" mil"')
    js += """var ch=root.querySelector(".k-chip");gsap.set(ch,{opacity:0,scale:.8});
tl.to(ch,{opacity:1,scale:1,duration:.4,ease:"back.out(2)"},2.3);"""
    return _scene(cid, dur, body, css, js)


def awd(cid, dur, label, chips):
    """Carro visto de cima: rodas acendendo em sequência, linhas de torque e bolsas de ar."""
    css = """
.a-wrap{position:relative;display:flex;gap:44px;align-items:center}
.a-svg{width:300px;height:470px;flex:0 0 auto}
.a-chips{display:flex;flex-direction:column;gap:20px}
.a-chip{padding:16px 26px;border-radius:20px;font-size:34px;font-weight:600;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16)}
.a-chip b{color:#ffb38a}
"""
    wheels = [(38, 92), (232, 92), (38, 318), (232, 318)]
    svg = ['<svg class="a-svg" viewBox="0 0 300 470">',
           '<rect x="62" y="20" width="176" height="430" rx="70" fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.75)" stroke-width="4"/>',
           '<path d="M88 132 Q150 104 212 132 L204 182 Q150 166 96 182 Z" fill="rgba(140,200,255,.22)" stroke="rgba(255,255,255,.5)" stroke-width="3"/>',
           '<path d="M96 330 Q150 344 204 330 L210 372 Q150 392 90 372 Z" fill="rgba(140,200,255,.18)" stroke="rgba(255,255,255,.45)" stroke-width="3"/>']
    for i, (x, y) in enumerate(wheels):
        cx, cy = x + 15, y + 30
        svg.append(f'<line class="a-tq" x1="150" y1="235" x2="{cx}" y2="{cy}" stroke="{ACCENT}" stroke-width="5" stroke-linecap="round" stroke-dasharray="240" stroke-dashoffset="240"/>')
    svg.append(f'<circle cx="150" cy="235" r="16" fill="{ACCENT}" opacity=".9"/>')
    for i, (x, y) in enumerate(wheels):
        svg.append(f'<rect class="a-w" x="{x}" y="{y}" width="30" height="60" rx="9" fill="rgba(255,255,255,.35)"/>')
        svg.append(f'<circle class="a-air" cx="{x + 15}" cy="{y + 30}" r="40" fill="none" stroke="rgba(120,220,255,.85)" stroke-width="3" opacity="0"/>')
    svg.append("</svg>")
    body = f'<div class="p-label"><i></i>{label}</div><div class="a-wrap">{"".join(svg)}<div class="a-chips">' + \
           "".join(f'<div class="a-chip p-disp">{c}</div>' for c in chips) + "</div></div>"
    js = f"""
var tq=root.querySelectorAll(".a-tq"),w=root.querySelectorAll(".a-w"),air=root.querySelectorAll(".a-air"),ch=root.querySelectorAll(".a-chip");
gsap.set(ch,{{opacity:0,x:40}});
tq.forEach(function(l,i){{tl.to(l,{{strokeDashoffset:0,duration:.45,ease:"power2.out"}},.6+i*.14);
  tl.to(w[i],{{fill:"{ACCENT}",duration:.2}},.85+i*.14);}});
air.forEach(function(a,i){{tl.fromTo(a,{{opacity:.9,scale:.4,transformOrigin:"50% 50%"}},{{opacity:0,scale:1.25,duration:.9,ease:"power2.out"}},1.5+i*.08);
  tl.fromTo(a,{{opacity:.7,scale:.4,transformOrigin:"50% 50%"}},{{opacity:0,scale:1.25,duration:.9,ease:"power2.out"}},2.6+i*.08);}});
ch.forEach(function(c,i){{tl.to(c,{{opacity:1,x:0,duration:.45,ease:"power3.out"}},1.1+i*.3);}});
"""
    return _scene(cid, dur, body, css, js, width=900)


def lane(cid, dur, label, readout):
    """HUD de assistência: pista em perspectiva, faixas tracejadas correndo, carro da frente travado."""
    css = """
.l-svg{display:block;width:760px;height:520px;margin:0 auto}
.l-read{display:flex;justify-content:space-between;margin-top:18px;font-size:32px;font-weight:600}
.l-read b{color:#7fe7ff}
"""
    body = f"""<div class="p-label"><i></i>{label}</div>
<svg class="l-svg" viewBox="0 0 760 520">
 <path d="M300 30 L40 520 L720 520 L460 30 Z" fill="rgba(255,255,255,.05)"/>
 <path class="l-edge" d="M300 30 L40 520" stroke="rgba(127,231,255,.9)" stroke-width="6" fill="none" stroke-dasharray="560" stroke-dashoffset="560"/>
 <path class="l-edge" d="M460 30 L720 520" stroke="rgba(127,231,255,.9)" stroke-width="6" fill="none" stroke-dasharray="560" stroke-dashoffset="560"/>
 <path class="l-dash" d="M380 30 L380 520" stroke="rgba(255,255,255,.75)" stroke-width="5" fill="none" stroke-dasharray="34 30" stroke-dashoffset="0" opacity="0"/>
 <g class="l-lead"><rect x="335" y="110" width="90" height="62" rx="14" fill="rgba(255,255,255,.18)" stroke="#fff" stroke-width="3"/></g>
 <path class="l-lock" d="M318 96 L318 80 L334 80 M426 80 L442 80 L442 96 M318 186 L318 202 L334 202 M426 202 L442 202 L442 186" stroke="{ACCENT}" stroke-width="5" fill="none" opacity="0"/>
 <path class="l-gap" d="M380 190 L380 420" stroke="{ACCENT}" stroke-width="4" stroke-dasharray="230" stroke-dashoffset="230" fill="none"/>
 <rect x="320" y="420" width="120" height="84" rx="18" fill="{ACCENT}" opacity=".9"/>
</svg>
<div class="l-read p-disp"><span>{readout[0]}</span><span><b>{readout[1]}</b></span></div>"""
    js = """
var e=root.querySelectorAll(".l-edge"),d=root.querySelector(".l-dash"),lk=root.querySelector(".l-lock"),g=root.querySelector(".l-gap"),rd=root.querySelector(".l-read");
gsap.set(rd,{opacity:0,y:20});
tl.to(e,{strokeDashoffset:0,duration:.7,ease:"power2.out",stagger:.1},.5);
tl.to(d,{opacity:1,duration:.3},.9);tl.fromTo(d,{strokeDashoffset:0},{strokeDashoffset:-640,duration:Math.max(.5,D-1.1),ease:"none"},.9);
tl.fromTo(lk,{opacity:0,scale:1.35,transformOrigin:"50% 50%"},{opacity:1,scale:1,duration:.35,ease:"back.out(2)"},1.35);
tl.to(g,{strokeDashoffset:0,duration:.6,ease:"power2.out"},1.6);
tl.to(rd,{opacity:1,y:0,duration:.45,ease:"power3.out"},1.9);
"""
    return _scene(cid, dur, body, css, js)


def shield(cid, dur, label, title, sub):
    """Escudo se desenhando com brilho + título."""
    css = """
.s-row{display:flex;align-items:center;gap:44px}
.s-svg{width:220px;height:260px;flex:0 0 auto}
.s-t{font-size:84px;font-weight:800;line-height:1}
.s-t span{display:block;font-size:34px;font-weight:500;color:rgba(255,255,255,.8);margin-top:14px;line-height:1.2}
"""
    body = f"""<div class="p-label"><i></i>{label}</div><div class="s-row">
<svg class="s-svg" viewBox="0 0 220 260">
 <path class="s-glow" d="M110 14 L196 48 L190 138 Q182 204 110 246 Q38 204 30 138 L24 48 Z" fill="{ACCENT}" opacity="0"/>
 <path class="s-path" d="M110 14 L196 48 L190 138 Q182 204 110 246 Q38 204 30 138 L24 48 Z" fill="rgba(255,255,255,.08)" stroke="#fff" stroke-width="7" stroke-linejoin="round" stroke-dasharray="720" stroke-dashoffset="720"/>
 <path class="s-chk" d="M72 132 L102 162 L152 102" fill="none" stroke="{ACCENT}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="140" stroke-dashoffset="140"/>
</svg><div class="s-t p-disp">{title}<span>{sub}</span></div></div>"""
    js = """
var p=root.querySelector(".s-path"),c=root.querySelector(".s-chk"),gl=root.querySelector(".s-glow"),t=root.querySelector(".s-t");
gsap.set(t,{opacity:0,x:40});
tl.to(p,{strokeDashoffset:0,duration:.9,ease:"power2.inOut"},.45);
tl.to(c,{strokeDashoffset:0,duration:.45,ease:"power3.out"},1.25);
tl.fromTo(gl,{opacity:0},{opacity:.35,duration:.25,ease:"power2.out"},1.4);tl.to(gl,{opacity:.12,duration:.6,ease:"power2.out"},1.65);
tl.to(t,{opacity:1,x:0,duration:.5,ease:"power3.out"},.9);
"""
    return _scene(cid, dur, body, css, js)


def brand(cid, dur, label, word, sub):
    """Revelação de marca: letras em serifada subindo uma a uma + brilho correndo por cima.

    O brilho é uma SEGUNDA camada do mesmo texto com o degradê recortado
    (background-clip:text). Recortar o degradê no próprio texto que tem as letras
    em inline-block deixa as letras invisíveis — o `check` acusa text_not_painted."""
    css = """
.b-box{position:relative;text-align:center}
.b-word,.b-shine{font-family:"Playfair Display",serif;font-size:118px;font-weight:700;letter-spacing:10px;line-height:1.1}
.b-word{color:#fff}
.b-word span{display:inline-block}
.b-shine{position:absolute;left:0;right:0;top:0;opacity:0;
  background:linear-gradient(100deg,rgba(255,255,255,0) 35%,rgba(255,215,184,.95) 50%,rgba(255,255,255,0) 65%);background-size:300% 100%;background-position:100% 0;
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}
.b-line{height:2px;margin:24px auto 0;width:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.8),transparent);transform-origin:50% 50%}
.b-sub{margin-top:22px;text-align:center;font-size:34px;font-weight:600;letter-spacing:14px;color:rgba(255,255,255,.85)}
"""
    letters = "".join(f"<span>{ch}</span>" for ch in word)
    body = (f'<div class="p-label"><i></i>{label}</div><div class="b-box"><div class="b-word p-disp">{letters}</div>'
            f'<div class="b-shine">{word}</div></div><div class="b-line"></div><div class="b-sub p-disp">{sub}</div>')
    js = """
var L=root.querySelectorAll(".b-word span"),sh=root.querySelector(".b-shine"),ln=root.querySelector(".b-line"),sb=root.querySelector(".b-sub");
gsap.set(L,{opacity:0,y:40});gsap.set(ln,{scaleX:0});gsap.set(sb,{opacity:0});
tl.to(L,{opacity:1,y:0,duration:.5,ease:"power3.out",stagger:.06},.45);
tl.to(ln,{scaleX:1,duration:.7,ease:"power3.inOut"},1.0);
tl.to(sb,{opacity:1,duration:.5,ease:"power2.out"},1.3);
tl.set(sh,{opacity:1},1.5);
tl.fromTo(sh,{backgroundPosition:"100% 0"},{backgroundPosition:"0% 0",duration:1.2,ease:"power2.inOut"},1.5);
"""
    return _scene(cid, dur, body, css, js, width=900)


def chips(cid, dur, label, items):
    """Chips de recursos surgindo em sequência (apps, espelhamento)."""
    css = f"""
.h-wrap{{display:flex;flex-wrap:wrap;gap:20px}}
.h-chip{{display:flex;align-items:center;gap:16px;padding:20px 30px;border-radius:999px;font-size:40px;font-weight:600;
  background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.2)}}
.h-chip i{{display:block;width:16px;height:16px;border-radius:8px;background:{ACCENT};box-shadow:0 0 14px {ACCENT}}}
"""
    body = f'<div class="p-label"><i></i>{label}</div><div class="h-wrap">' + \
           "".join(f'<div class="h-chip p-disp"><i></i>{t}</div>' for t in items) + "</div>"
    js = """
var c=root.querySelectorAll(".h-chip");gsap.set(c,{opacity:0,scale:.7,y:20});
tl.to(c,{opacity:1,scale:1,y:0,duration:.42,ease:"back.out(1.8)",stagger:.22},.5);
"""
    return _scene(cid, dur, body, css, js)


def index_html(dur: float, mounts: list[dict]) -> str:
    """Raiz: vídeo base (render Remotion) + cenas montadas por cima."""
    hosts = "\n".join(
        f'      <div id="{m["id"]}" class="clip" data-composition-id="{m["id"]}" data-composition-src="compositions/{m["id"]}.html" '
        f'data-start="{m["start"]:.2f}" data-duration="{m["dur"]:.2f}" data-track-index="{i + 1}" data-track-kind="graphics" '
        f'data-width="1080" data-height="1920" data-layout-allow-overlap style="position:absolute;inset:0;z-index:{i + 2}"></div>'
        for i, m in enumerate(mounts))
    return f"""<!doctype html>
<html lang="pt" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 1080px; height: 1920px; overflow: hidden; }}
      #base {{ position: absolute; inset: 0; width: 1080px; height: 1920px; object-fit: cover; z-index: 1; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1080" data-height="1920">
      <video id="base" class="clip" src="assets/base.mp4" data-start="0" data-duration="{dur:.3f}" data-track-index="0" muted playsinline></video>
{hosts}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
