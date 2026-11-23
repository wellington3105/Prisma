"""cenas_legenda.py: the "legenda" cena, two styles (called by cenas.py; not a CLI of its own).

Reverse-engineered on 2026-11-23 from two reference Reels (study only; F6 and F7 in Prisma-Suite
docs/analises/2026-11-22-formatos-de-referencia.md):

  mista (F7)          blocks of 2-3 stacked lines over the chest; each word has its own size and
                      colour: linking words small and white, one strong word per block big and in an
                      accent colour (red / yellow / lime, cycling), the rest medium white; a red strike
                      draws across a negation ("não é"); words pop in as they are spoken.
  palavra-chave (F6)  one small white line, word by word; only the key word (a number, a word asked
                      for in `destaques`, else the block's longest word of 8+ letters) grows in teal.

Word times: `legendas` = a Remotion captions.json ([{text, startMs, endMs}]) or a transcribe.py
transcript ({words: [{text, start, end, type}]}); only the words inside de..ate, shifted to 0.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from cenas_titulo import _probe_dur
from hfkit.project import FONT_STACK, Project, esc, font_faces

W, H = 1080, 1920
ESTILOS = ("mista", "palavra-chave")
PAUSA = 0.35          # a silence longer than this opens a new block
MAX_PALAVRAS = 5
STRIKE_DURATION = 0.16
LIGA = {"a", "o", "as", "os", "e", "é", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "um", "uma",
        "que", "se", "por", "pra", "para", "com", "ao", "à", "eu", "tu", "ele", "ela", "me", "te", "lhe", "seu", "sua",
        "só", "já", "mas", "ou", "nem", "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "it", "that",
        "you", "your", "i", "my", "we", "be", "are", "was", "way"}
NEGA = {"não", "nunca", "nem", "jamais", "not", "never", "don't", "isn't"}
CORES_FORTE = ("#ff2a2a", "#ffe100", "#b6ff2e")
COR_CHAVE = "#2ee6d6"


def _norm(w: str) -> str:
    return re.sub(r"[^\wÀ-ÿ'%²³]", "", w.lower())


def load_words(path: Path, de: float, ate: float) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc

    transcript = isinstance(raw, dict)
    entries = raw.get("words") if transcript else raw
    if not isinstance(entries, list):
        raise ValueError("esperada uma lista de legendas Remotion ou um transcript com lista 'words'")
    start_key, end_key, units = ("start", "end", 1) if transcript else ("startMs", "endMs", 1000)

    out = []
    previous_start = -1.0
    for index, word in enumerate(entries, 1):
        if not isinstance(word, dict):
            raise ValueError(f"entrada {index}: esperada uma palavra com texto e tempos")
        if transcript and word.get("type", "word") != "word":
            continue
        text = word.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"entrada {index}: texto da palavra está vazio ou inválido")
        start_raw, end_raw = word.get(start_key), word.get(end_key)
        if isinstance(start_raw, bool) or isinstance(end_raw, bool):
            raise ValueError(f"entrada {index}: {start_key} e {end_key} precisam ser tempos numéricos")
        try:
            start = float(start_raw) / units
            end = float(end_raw) / units if end_raw is not None else start + 0.3
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"entrada {index}: {start_key} ou {end_key} inválido") from exc
        if not (0 <= start <= end and math.isfinite(end)):
            raise ValueError(f"entrada {index}: tempos precisam ser finitos, não negativos e em ordem")
        if start < previous_start:
            raise ValueError(f"entrada {index}: palavras fora de ordem cronológica")
        previous_start = start
        if de <= start < ate:
            out.append({"texto": text.strip(), "t0": round(start - de, 3), "t1": round(end - de, 3)})
    if not out:
        raise ValueError(f"sem palavras com início no trecho de {de:g} a {ate:g} s")
    return out


def _continues(previous: dict, word: dict) -> bool:
    return word["t0"] - previous["t1"] <= PAUSA and not re.search(r"[.!?]$", previous["texto"])


def blocks(words: list[dict], *, keep_negation: bool = False) -> list[list[dict]]:
    out: list[list[dict]] = []
    for i, word in enumerate(words):
        pair = (keep_negation and _norm(word["texto"]) in NEGA and i + 1 < len(words)
                and _continues(word, words[i + 1]))
        # Reserve one slot for the next word in a negation pair.
        if out and len(out[-1]) + int(pair) < MAX_PALAVRAS and _continues(out[-1][-1], word):
            out[-1].append(word)
        else:
            out.append([word])
    return out


def _strong(bloco: list[dict], destaques: set[str], estilo: str) -> int | None:
    for i, w in enumerate(bloco):
        if any(ch.isdigit() for ch in w["texto"]) or _norm(w["texto"]) in destaques:
            return i
    cand = [(len(_norm(w["texto"])), i) for i, w in enumerate(bloco)
            if _norm(w["texto"]) not in LIGA and _norm(w["texto"]) not in NEGA]
    if not cand:
        return None
    n, i = max(cand)
    if estilo == "palavra-chave" and n < 8:
        return None
    return i


def _shown(t: str) -> str:
    """As shown on screen: no trailing comma or full stop (? and ! stay)."""
    return re.sub(r"[,.;:]+$", "", t)


def validate(dados: dict) -> list[str]:
    probs = []
    v = dados.get("video")
    if not v or not Path(v).exists():
        probs.append(f"video não encontrado: {v!r}")
    try:
        de, ate = float(dados.get("de", 0)), float(dados.get("ate", 0))
    except (TypeError, ValueError, OverflowError):
        return probs + ["de e ate precisam ser tempos numéricos"]
    valid_window = 0 <= de < ate and math.isfinite(ate)
    if not valid_window:
        probs.append(f"de ({de}) e ate ({ate}) precisam ser finitos e atender 0 <= de < ate")
    elif v and Path(v).exists():
        dur = _probe_dur(Path(v))
        if dur and ate > dur + 0.05:
            probs.append(f"ate ({ate}) passa do fim do video ({dur:.2f} s)")
    lg = dados.get("legendas")
    if not isinstance(lg, (str, Path)) or not Path(lg).is_file():
        probs.append(f"legendas (captions.json ou transcript) não encontradas: {lg!r}")
    elif valid_window:
        try:
            load_words(Path(lg), de, ate)
        except (OSError, ValueError) as exc:
            probs.append(f"legendas: {exc}")
    if dados.get("estilo", "mista") not in ESTILOS:
        probs.append(f"estilo '{dados.get('estilo')}' não existe (use {', '.join(ESTILOS)})")
    return probs


def _lines(bloco: list[dict], forte: int | None) -> list[list[int]]:
    """Stack a block in lines: the strong word alone on its line, the rest up to ~11 letters per line."""
    lines: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(bloco):
        if i == forte:
            if cur:
                lines.append(cur)
            lines.append([i])
            cur = []
            continue
        if cur and sum(len(bloco[j]["texto"]) + 1 for j in cur) + len(w["texto"]) > 11:
            lines.append(cur)
            cur = []
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


# Measure layout offsets so a font refresh during a seek ignores the word-entry transforms.
_STRIKE_JS = """
    function drawStrike(id, firstId, lastId, at, duration) {
      const strike = document.getElementById(id);
      const first = document.getElementById(firstId);
      const last = document.getElementById(lastId);
      function measure() {
        const left = first.offsetLeft;
        const width = last.offsetLeft + last.offsetWidth - left;
        const firstCenter = first.offsetTop + first.offsetHeight / 2;
        const lastCenter = last.offsetTop + last.offsetHeight / 2;
        strike.style.left = (left - 10) + "px";
        strike.style.width = (width + 20) + "px";
        strike.style.top = ((firstCenter + lastCenter) / 2) + "px";
      }
      measure();
      if (document.fonts) document.fonts.ready.then(measure);
      // Set both components in GSAP to avoid parsing a collapsed CSS matrix.
      gsap.set(strike, {scaleX:0, rotation:-4});
      tl.to(strike, {scaleX:1, duration, ease:"whip"}, at);
    }
"""


def build(proj: Project, dados: dict) -> Path:
    out = proj.root
    video = Path(dados["video"])
    src = proj.asset(video)
    de, ate = float(dados.get("de", 0)), float(dados["ate"])
    dur = round(ate - de, 6)
    estilo = dados.get("estilo", "mista")
    dest = dados.get("destaques") or []
    destaques = {_norm(x) for x in (dest.split("|") if isinstance(dest, str) else dest) if x}
    altura = float(dados.get("altura", 0.42 if estilo == "mista" else 0.74))
    words = load_words(Path(dados["legendas"]), de, ate)
    bls = blocks(words, keep_negation=estilo == "mista")

    html_b, tl = [], ["const tl = gsap.timeline({ paused: true });"]
    strikes = []
    k = 0
    for b, bloco in enumerate(bls):
        forte = _strong(bloco, destaques, estilo)
        b_end = min(dur, (bls[b + 1][0]["t0"] if b + 1 < len(bls) else bloco[-1]["t1"] + 0.6))
        spans = {}
        for i, w in enumerate(bloco):
            n = _norm(w["texto"])
            if estilo == "mista":
                cls = "forte" if i == forte else ("liga" if n in LIGA or n in NEGA else "meio")
                style = f' style="color:{CORES_FORTE[b % len(CORES_FORTE)]}"' if i == forte else ""
            else:
                cls = "chave" if i == forte else "base"
                style = ""
            spans[i] = f'<span class="pw {cls}" id="p{k + i}"{style}>{esc(_shown(w["texto"]))}</span>'
        lines = _lines(bloco, forte) if estilo == "mista" else [range(len(bloco))]
        body = "".join('<div class="linha">' + " ".join(spans[i] for i in line) + "</div>" for line in lines)
        risco = []
        neg = next((i for i, w in enumerate(bloco[:-1]) if _norm(w["texto"]) in NEGA), None)
        if estilo == "mista" and neg is not None:
            following = bloco[neg + 1]
            frame = 1 / proj.fps
            latest_start = b_end - STRIKE_DURATION - frame
            at = following["t1"]
            # If the block is about to end, use the second word's own hold for the strike.
            if at > latest_start:
                first_visible = min(following["t0"] + frame, (following["t0"] + b_end) / 2)
                at = round(max(first_visible, latest_start), 6)
            for line in lines:
                covered = [i for i in line if neg <= i <= neg + 1]
                if covered:
                    strike_id = f"r{b}-{len(risco)}"
                    risco.append(f'<div class="risco" id="{strike_id}"></div>')
                    strikes.append(f'drawStrike("{strike_id}", "p{k + covered[0]}", "p{k + covered[-1]}", '
                                   f'{at}, {STRIKE_DURATION});')
        html_b.append(f'<div class="bloco" id="b{b}">{body}{"".join(risco)}</div>')
        tl.append(f'tl.set("#b{b}", {{opacity:1}}, {bloco[0]["t0"]}); tl.set("#b{b}", {{opacity:0}}, {round(b_end, 3)});')
        for i, w in enumerate(bloco):
            tl.append(f"/* w{k + i} @{w['t0']:g} */")
            big = estilo == "mista" and i == forte
            tl.append(f'tl.fromTo("#p{k + i}", {{opacity:0, scale:{0.55 if big else 0.8}, y:{18 if big else 8}}}, '
                      f'{{opacity:1, scale:1, y:0, duration:{0.16 if big else 0.1}, '
                      f'ease:"{"crashIn" if big else "softLand"}", immediateRender:false}}, {w["t0"]});')
        k += len(bloco)
    if strikes:
        tl.extend([_STRIKE_JS.strip(), *strikes])

    eases = (Path(__file__).resolve().parent.parent / "assets" / "hyperframes" / "vendor" / "prisma-eases.js").read_text(
        encoding="utf-8")
    if estilo == "mista":
        css_words = """
      .linha { display: block; line-height: 0.92; font-size: 0; }
      .pw { display: inline-block; margin: 0 0.13em; opacity: 0; color: #fff; font-weight: 800; letter-spacing: -0.03em;
            text-shadow: 0 4px 18px rgba(0,0,0,.45); }
      .pw.liga { font-size: 62px; font-weight: 600; }
      .pw.meio { font-size: 104px; }
      .pw.forte { font-size: 150px; font-weight: 900; }
      .risco { position: absolute; height: 12px; margin-top: -6px; background: #e8141e; border-radius: 6px;
               transform-origin: 0 50%; }"""
    else:
        css_words = f"""
      .linha {{ display: block; line-height: 1.1; font-size: 0; }}
      .pw {{ display: inline-block; margin: 0 0.14em; opacity: 0; color: #fff; font-weight: 600; font-size: 58px;
             text-shadow: 0 3px 14px rgba(0,0,0,.55); }}
      .pw.chave {{ color: {COR_CHAVE}; font-size: 96px; font-weight: 800; }}"""
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
{font_faces(weights=(600, 800, 900))}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; background: #000; font-family: {FONT_STACK}; }}
      #v {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      .bloco {{ position: absolute; left: 60px; right: 60px; top: {int(H * altura)}px; transform: translateY(-50%);
                text-align: center; opacity: 0; }}{css_words}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <video id="v" class="clip" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="0" muted playsinline></video>
    <audio id="a" src="{esc(src)}" data-start="0" data-duration="{dur}" data-media-start="{de}" data-track-index="9" data-volume="1"></audio>
    {''.join(html_b)}
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
