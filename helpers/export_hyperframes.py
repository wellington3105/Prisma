"""Export a Prisma edit as an editable HyperFrames project — the Prisma EDITOR.

Prisma decides the edit (cut by speech, grade, audio, style gate, captions,
images, cards, soundtrack); HyperFrames Studio is where the person edits it,
live, inside Prisma's own Editor tab (preview_server.py hosts it). The render
of the final video is HyperFrames' Export.

Every take becomes its own <video> clip pointing into the FULL source proxy
with data-media-start, so it can be trimmed/extended, moved, split or deleted.
Every caption line, card, split band and flash is its own sub-composition clip
(one file each, unique id) so each can be moved and trimmed on its track. One
line per caption clip is deliberate: Studio 0.8.x's native caption track does
not persist timing edits.

Usage:
    uv run python helpers/export_hyperframes.py <edit> [--out <dir>] [--force]

Safety: the project records a fingerprint of what it wrote. If index.html was
changed since (i.e. the person edited in Studio), the export refuses unless
--force — re-exporting would silently throw that work away.
"""
import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(description="Prisma → HyperFrames editor project")
ap.add_argument("edit", type=Path, help="the Prisma <edit> dir")
ap.add_argument("--out", type=Path, default=None, help="project dir (default: <edit>/hyperframes)")
ap.add_argument("--force", action="store_true", help="overwrite even if edited in Studio")
ap.add_argument("--no-proxy", action="store_true", help="reuse existing source proxies")
args = ap.parse_args()

EDIT = args.edit.resolve()
PUB = EDIT / "remotion" / "public"
ROOT = (args.out or (EDIT / "hyperframes")).resolve()

def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


edl = json.loads((EDIT / "edl.json").read_text(encoding="utf-8"))
# Phase-2 inputs are optional: in Phase 1 the editor holds the cut alone
ed = _load(PUB / "edit-data.json", {})
caps = _load(PUB / "captions.json", [])
seg = (_load(PUB / "segments.json", {}) or {}).get("segments") or []
R = edl["ranges"]
FPS = int(ed.get("fps") or edl.get("fps") or 30)
def _cut_size():
    """Phase 1 has no edit-data.json: follow the cut's own aspect (a 16:9 job must not
    become a 1080×1920 editor). Long side capped at 1920 — the editor works on proxies."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", str(EDIT / "cut.mp4")],
                             capture_output=True, text=True, check=True).stdout.strip().split(",")
        w, h = int(out[0]), int(out[1])
    except Exception:
        return 1080, 1920
    k = 1920 / max(w, h)
    return (int(round(w * k / 2)) * 2, int(round(h * k / 2)) * 2) if k < 1 else (w, h)


W, H = (int(ed["width"]), int(ed["height"])) if ed.get("width") and ed.get("height") else _cut_size()
# render.py caps the J-cut lead per seam by the silence there, so the real lead of
# each take is in jcut_timeline; the EDL's lead_frames is only the ceiling.
_JT = edl.get("jcut_timeline") or []
if len(_JT) == len(R) and all("lead_frames" in j for j in _JT):
    LEADS = [j["lead_frames"] / FPS for j in _JT]
else:
    _l = (edl.get("jcut") or {}).get("lead_frames", 5) / FPS if edl.get("jcut") is not False else 0.0
    LEADS = [0.0] + [_l] * (len(R) - 1)
LEAD = max(LEADS)
HF = shutil.which("hyperframes")
if not HF:
    raise SystemExit("HyperFrames CLI não encontrado — instale com: npm i -g hyperframes@latest")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(map(str, cmd))}\n{r.stdout[-800:]}{r.stderr[-800:]}")
    return r


def project_sig(root):
    """What the person could have changed: index + every composition, with the
    ids Studio stamps on open (data-hf-id) stripped — opening the editor is not
    an edit, and a byte hash called it one."""
    h = hashlib.sha1()
    files = [root / "index.html"] + sorted((root / "compositions").glob("*.html"))
    for f in files:
        if f.exists():
            t = re.sub(r'\sdata-hf-id="[^"]*"', "", f.read_text(encoding="utf-8"))
            h.update(f.name.encode())
            h.update(t.encode("utf-8"))  # read_text already normalised newlines
    return h.hexdigest()


# ---- project setup (init once; refuse to clobber Studio edits) ----
MARK = ROOT / ".prisma-export.json"
EXISTING, EXISTING_HAS_OVERLAYS = "", False
if (ROOT / "hyperframes.json").exists():
    EXISTING = (ROOT / "index.html").read_text(encoding="utf-8") if (ROOT / "index.html").exists() else ""
    EXISTING_HAS_OVERLAYS = "compositions/cap-" in EXISTING or "compositions/card-" in EXISTING
    edited = False
    if MARK.exists():
        was = json.loads(MARK.read_text(encoding="utf-8")).get("index_sha1")
        edited = bool(was) and was != project_sig(ROOT)
    # Takes cut by hand are carried over (see base takes below). What cannot be
    # carried over are hand edits to captions/cards/images: refuse to erase them.
    if edited and EXISTING_HAS_OVERLAYS and not args.force:
        raise SystemExit("legendas/cards/imagens foram editados no editor depois da última exportação — "
                         "reexportar apagaria essas edições. Use --force para sobrescrever mesmo assim.")
else:
    ROOT.parent.mkdir(parents=True, exist_ok=True)
    run([HF, "init", ROOT.name, "--non-interactive", "--example=blank", "--skill=general-video"], cwd=ROOT.parent)
COMP = ROOT / "compositions"
COMP.mkdir(exist_ok=True)
for c in COMP.glob("*.html"):
    c.unlink()
for d in ("assets/split", "assets/audio", "assets/fonts"):
    (ROOT / d).mkdir(parents=True, exist_ok=True)
for f in (SKILL / "assets" / "hyperframes" / "fonts").glob("*"):
    shutil.copy2(f, ROOT / "assets" / "fonts" / f.name)

# ---- one full-length edit proxy per source: target size, dense keyframes
# (smooth scrubbing), the Phase-1 voice master baked in so it sounds like Prisma
VOICE = ("highpass=f=80,equalizer=f=200:t=q:w=1.1:g=-2.5,acompressor=threshold=-20dB:ratio=3:"
         "attack=12:release=200:makeup=3:knee=6,equalizer=f=3200:t=q:w=1.6:g=2.5,treble=g=3:f=9000,"
         "deesser=i=0.35,alimiter=limit=0.95,")
# the Phase-1 grade (edl.json `grade`: a raw filter or a grade.py preset name)
# is baked into the edit proxy, so the editor shows — and exports — the look
# that was approved. 8-bit first: colorlevels breaks on 10-bit (see render.py).
_g = (edl.get("grade") or "").strip()
if _g and "=" not in _g:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grade import PRESETS  # noqa: E402
    _g = PRESETS.get(_g, "")
GRADE = f",{_g},format=yuv420p" if _g else ""
SRC = {}
for key, path in (edl.get("sources") or {}).items():
    out = ROOT / "assets" / f"{key}.mp4"
    SRC[key] = f"assets/{key}.mp4"
    if out.exists() and args.no_proxy:
        continue
    af = (VOICE if edl.get("voice_master") else "") + "loudnorm=I=-14:TP=-1.5:LRA=11"
    print(f"proxy {key} …", flush=True)
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},format=yuv420p{GRADE}",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-g", "15", "-keyint_min", "15",
         "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)])

# ---- Prisma cut time -> source time (only needed for Phase-2 overlays) ----
if seg:
    seams = [round(x["start"] * FPS) for x in seg]  # picture start frame of each take in cut.mp4
    assert len(seams) == len(R), (len(seams), len(R))
    astart = [seams[k] / FPS - LEADS[k] for k in range(len(R))]  # audio start in cut
else:
    astart = []


def cut_to_src(t):
    k = max(i for i in range(len(R)) if astart[i] <= t + 1e-6)
    return R[k]["source"], R[k]["start"] + (t - astart[k]), k


# ---- base takes: the EDITOR's own cut when the person already cut there,
# otherwise the Prisma EDL butt-joined. One editor, one cut: a Phase-2 export
# must never throw away takes trimmed/split/deleted by hand in Phase 1.
def editor_takes(html_text):
    out = []
    for m in re.finditer(r"<video([^>]*)>", html_text):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        if not a.get("id", "").startswith("take-"):
            continue
        src = a.get("src", "")
        key = next((k for k, v in SRC.items() if v == src), None)
        if key is None or "data-media-start" not in a:
            continue
        s0 = float(a["data-media-start"]); d = float(a["data-duration"])
        out.append({"source": key, "src0": s0, "src1": s0 + d, "hf0": float(a["data-start"]), "beat": ""})
    return sorted(out, key=lambda x: x["hf0"])


base = []
if EXISTING and not EXISTING_HAS_OVERLAYS and not args.force:
    base = editor_takes(EXISTING)
    if base:
        print(f"takes do editor: {len(base)} (cortes feitos à mão preservados)", flush=True)
if not base:
    t = 0.0
    for r in R:
        base.append({"source": r["source"], "src0": r["start"], "src1": r["end"], "hf0": t, "beat": r.get("beat", "")})
        t += r["end"] - r["start"]
for k, b in enumerate(base):
    b["k"] = k
TOTAL = round(max(b["hf0"] + b["src1"] - b["src0"] for b in base), 3)


def src_to_hf(source, s, tol=0.02):
    """source time -> editor time; None when that moment is not in the cut"""
    for b in base:
        if b["source"] == source and b["src0"] - tol <= s < b["src1"] + tol:
            return b["hf0"] + (min(max(s, b["src0"]), b["src1"]) - b["src0"])
    return None


def cut_to_hf(tc):
    src, s, _ = cut_to_src(tc)
    return src_to_hf(src, s)


# ---- split windows -> source windows -> clips framed for the split ----
zooms = (ed.get("camera") or {}).get("zooms") or [1.0]
splits = []
for i, sp in enumerate(ed.get("splitInserts") or [] if astart else []):
    src, s, k = cut_to_src(sp["start"] + LEAD + 1e-3)  # picture-side
    if s - R[k]["start"] < 0.35:  # opens on a take cut: start WITH the take, no sliver
        s = R[k]["start"]
    src_e, s_e, _ = cut_to_src(sp["end"] - 1e-3)
    splits.append({"i": i, "source": src, "src": s, "src_end": s_e, "img": sp["src"],
                   "zoom": sp.get("zoom", 1.25), "focusY": sp.get("focusY", 400),
                   "bandH": sp.get("bandH", 750)})
# a split that opens inside a take cuts that take in two (same source, straight cut)
clips = []
for b in base:
    cuts = sorted({round(sp["src"], 3) for sp in splits
                   if sp["source"] == b["source"] and b["src0"] + 0.05 < sp["src"] < b["src1"] - 0.05})
    edges = [b["src0"]] + cuts + [b["src1"]]
    for a, e in zip(edges, edges[1:]):
        clips.append({"k": b["k"], "src0": a, "src1": e, "hf0": b["hf0"] + (a - b["src0"]),
                      "beat": b["beat"], "source": b["source"]})
for n, c in enumerate(clips):
    c["id"] = f"take-{n + 1:02d}"
    c["zoom"] = zooms[c["k"] % len(zooms)]
    c["split"] = None
    mid = c["src0"] + (c["src1"] - c["src0"]) / 2
    for sp in splits:
        if c["source"] == sp["source"] and sp["src"] - 0.05 <= mid <= sp["src_end"] + 0.05:
            c["split"] = sp
# a split band spans exactly the clips it frames (none left → the band is gone)
for sp in splits:
    mine = [c for c in clips if c["split"] is sp]
    sp["hf0"] = mine[0]["hf0"] if mine else None
    sp["hf1"] = (mine[-1]["hf0"] + (mine[-1]["src1"] - mine[-1]["src0"])) if mine else None
splits = [sp for sp in splits if sp["hf0"] is not None]


def fr(x):
    return round(x, 3)


def clip_style(c):
    base = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;"
    sp = c["split"]
    if sp:
        z, fy, bh = sp["zoom"], sp["focusY"], sp["bandH"]
        left = -(W * (z - 1)) / 2
        top = bh - fy * z
        return base + f"transform-origin:0 0;transform:translate({left:.1f}px,{top:.1f}px) scale({z})"
    return base + f"transform-origin:50% 40%;transform:scale({c['zoom']})"


# ---- captions: lines of <=4 words, break on punctuation / gaps ----
words = []
for w in (caps if astart else []):
    a = cut_to_hf(w["startMs"] / 1000)
    b = cut_to_hf(w["endMs"] / 1000)
    if a is None:  # that word's moment was cut in the editor
        continue
    if b is None or b <= a:
        b = a + 0.3
    words.append({"t": w["text"], "a": a, "b": max(b, a + 0.08)})
cues, cur = [], []
for i, w in enumerate(words):
    cur.append(w)
    nxt = words[i + 1] if i + 1 < len(words) else None
    end = (len(cur) >= 4 or w["t"][-1:] in ".,?!…" or nxt is None
           or nxt["a"] - w["b"] > 0.4 or w["b"] - cur[0]["a"] > 1.9)
    if end:
        cues.append(cur)
        cur = []

# ---- file templates ----
GSAP = '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'


def sub(cid, style, body, script):
    return f"""<!doctype html>
<html lang="pt-BR">
  <head><meta charset="UTF-8" /></head>
  <body>
    <template>
      <style>
        #root {{ position: absolute; inset: 0; }}
{style}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}">
{body}
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
{script}
          window.__timelines["{cid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""


hosts = []  # root-level host divs


def host(cid, start, dur, track, kind, z):
    hosts.append(
        f'    <div id="{cid}" class="clip" data-composition-id="{cid}" '
        f'data-composition-src="compositions/{cid}.html" data-start="{fr(start)}" '
        f'data-duration="{fr(dur)}" data-track-index="{track}" data-track-kind="{kind}" '
        f'data-width="{W}" data-height="{H}" style="z-index:{z}"></div>')


# captions — "Disperso": Lora, lowercase, ragged lines, one word at a time
CAP_STYLE = """        @font-face { font-family: "Lora"; font-weight: 400; font-style: normal;
                     src: url("assets/fonts/lora-latin-400-normal.woff2") format("woff2"); }
        @font-face { font-family: "Lora"; font-weight: 700; font-style: italic;
                     src: url("assets/fonts/lora-latin-700-italic.woff2") format("woff2"); }
        .line { position: absolute; left: 0; right: 0; display: flex; justify-content: center; gap: 0 22px; }
        .w { font-family: "Lora", Georgia, serif; font-size: 72px; line-height: 1; text-transform: lowercase;
             color: #f5f1ea; opacity: 0;
             /* a dark halo, not a plate: the speaker wears a white shirt and the
                caption sits on his chest — without it the words wash out */
             text-shadow: 0 0 3px rgba(0,0,0,.9), 0 2px 10px rgba(0,0,0,.85), 0 0 28px rgba(0,0,0,.6);
             display: inline-block; }
        .w.hl { font-weight: 700; font-style: italic; color: #a9dcff; }"""
for n, cue in enumerate(cues):
    cid = f"cap-{n + 1:03d}"
    start = cue[0]["a"]
    nxt = cues[n + 1][0]["a"] if n + 1 < len(cues) else TOTAL
    # ends a frame before the next line starts, so two lines never share a frame
    dur = max(0.3, min(nxt - 1 / FPS, cue[-1]["b"] + 0.6) - start)
    longest = max(cue, key=lambda w: len(w["t"].strip(".,?!…")))
    hl = longest if len(longest["t"].strip(".,?!…")) >= 7 else None
    # 1–2 ragged lines, horizontal offset hashed off the cue index (deterministic)
    lines = [cue[:2], cue[2:]] if len(cue) > 2 else [cue]
    body, script = [], []
    y0 = 1382 - (len(lines) - 1) * 48
    for li, ln in enumerate(lines):
        dx = ((n * 37 + li * 53) % 120) - 60
        spans = []
        for w in ln:
            j = cue.index(w)
            cls = "w hl" if w is hl else "w"
            spans.append(f'<span id="{cid}-w{j}" class="{cls}">{html.escape(w["t"].strip(".,…"))}</span>')
        body.append(f'        <div class="line" style="top:{y0 + li * 96}px;transform:translateX({dx}px)">{"".join(spans)}</div>')
    for j, w in enumerate(cue):
        rel = fr(max(0.0, w["a"] - start))
        sel = f'"#{cid}-w{j}"'
        if w is hl:
            script.append(f'          tl.fromTo({sel}, {{opacity:0, scale:1.62, filter:"blur(22px)"}}, '
                          f'{{opacity:1, scale:1, filter:"blur(0px)", duration:0.38, ease:"power3.out"}}, {rel});')
        else:
            script.append(f'          tl.fromTo({sel}, {{opacity:0}}, {{opacity:1, duration:0.16, ease:"power1.out"}}, {rel});')
    (COMP / f"{cid}.html").write_text(sub(cid, CAP_STYLE, "\n".join(body), "\n".join(script)), encoding="utf-8")
    host(cid, start, dur, 4, "captions", 30)

# headline — "Contorno": white, thick black stroke, two lines
hook = ed.get("hook") or {}
if hook.get("enabled"):
    text = hook.get("text") or " ".join(hook.get("lines") or [])
    ws = text.split()
    # two lines balanced by character count
    best = min(range(1, len(ws)), key=lambda i: abs(len(" ".join(ws[:i])) - len(" ".join(ws[i:]))))
    l1, l2 = " ".join(ws[:best]), " ".join(ws[best:])
    # always two lines: fit the size to the longer one (Poppins Black ≈ 0.62em
    # per character) inside the title-safe width, capped at 78px
    size = min(78, int(880 / (0.62 * max(len(l1), len(l2)))))
    style = """        #hl { position: absolute; left: 60px; right: 60px; top: 330px; text-align: center; white-space: nowrap;
              font-family: "Poppins", sans-serif; font-weight: 900; font-size: SIZEpx; line-height: 1.12;""".replace("SIZE", str(size)) + """
              color: #fff; -webkit-text-stroke: 12px #000; paint-order: stroke fill; letter-spacing: -1px; }
        #hl { display: flex; flex-direction: column; align-items: center; gap: 14px; }
        #hl div { display: block; }"""
    body = f'        <div id="hl"><div id="hl-a">{html.escape(l1)}</div><div id="hl-b">{html.escape(l2)}</div></div>'
    dur = float(hook.get("endSec", 4))
    script = (f'          tl.fromTo("#hl-a", {{opacity:0, y:24}}, {{opacity:1, y:0, duration:0.35, ease:"power3.out"}}, 0.15);\n'
              f'          tl.fromTo("#hl-b", {{opacity:0, y:24}}, {{opacity:1, y:0, duration:0.35, ease:"power3.out"}}, 0.25);\n'
              f'          tl.to("#hl", {{opacity:0, y:-12, duration:0.3, ease:"power2.in"}}, {dur - 0.35});')
    (COMP / "headline.html").write_text(sub("headline", style, body, script), encoding="utf-8")
    host("headline", 0, dur, 3, "graphics", 25)

# keyword glass cards
hl_block = ed.get("highlights") or {}
off = hl_block.get("offsetS", 0.8)
CARD_STYLE = """        .card { position: absolute; transform-origin: 100% 50%; max-width: 760px; padding: 22px 34px 26px;
                display: flex; flex-direction: column; align-items: center; gap: 10px;
                border-radius: 30px; background: rgba(12,17,28,.62); border: 2px solid rgba(255,255,255,.22);
                backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
                box-shadow: 0 18px 50px rgba(0,0,0,.35); text-align: center; white-space: nowrap; }
        .lab { font-family: "Poppins", sans-serif; font-weight: 700; font-size: 22px; letter-spacing: 3px;
               text-transform: uppercase; color: #8fd3ff; line-height: 1; }
        .txt { font-family: "Poppins", sans-serif; font-weight: 700; font-size: 54px; color: #fff; line-height: 1.05; }"""
for n, h in enumerate(hl_block.get("items") or []):
    cid = f"card-{n + 1:02d}"
    y = h.get("y", 0.24) * H  # right-anchored on the title-safe margin (10% of width) so no card leaves the frame
    body = (f'        <div class="card" id="{cid}-c" style="right:{W * 0.1:.0f}px;top:{y:.0f}px;translate:0 -50%;rotate:{h.get("tilt", -2)}deg">'
            f'<div class="lab">{html.escape(h.get("label", ""))}</div><div class="txt">{html.escape(h["text"])}</div></div>')
    dur = h.get("dur", 3.2)
    script = (f'          tl.fromTo("#{cid}-c", {{opacity:0, scale:0.82}}, {{opacity:1, scale:1, duration:0.45, ease:"back.out(1.7)"}}, 0);\n'
              f'          tl.to("#{cid}-c", {{opacity:0, scale:0.96, duration:0.25, ease:"power2.in"}}, {dur - 0.25});')
    (COMP / f"{cid}.html").write_text(sub(cid, CARD_STYLE, body, script), encoding="utf-8")
    at = cut_to_hf(h["at"]) if astart else None
    if at is None:  # the word it annotates was cut
        (COMP / f"{cid}.html").unlink(missing_ok=True)
        continue
    host(cid, at + off, dur, 3, "graphics", 20)

# split bands + the flash that announces each one
for sp in splits:
    cid = f"split-{sp['i'] + 1}"
    img = "assets/split/" + Path(sp["img"]).name  # root-relative: Studio serves from the project root
    shutil.copy2(PUB / sp["img"], ROOT / img)
    style = f"""        #band {{ position: absolute; left: 0; top: 0; width: {W}px; height: {sp['bandH']}px; overflow: hidden; background: #0a0a0c; }}
        #img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
        #fade {{ position: absolute; left: 0; right: 0; bottom: 0; height: 110px;
                 background: linear-gradient(180deg, rgba(10,10,12,0), rgba(10,10,12,.75)); }}"""
    body = f'        <div id="band"><img id="img" src="{img}" alt="" /><div id="fade"></div></div>'
    dur = sp["hf1"] - sp["hf0"]
    script = f'          tl.fromTo("#img", {{scale:1}}, {{scale:1.03, duration:{fr(dur)}, ease:"none"}}, 0);'
    (COMP / f"{cid}.html").write_text(sub(cid, style, body, script), encoding="utf-8")
    host(cid, sp["hf0"], dur, 1, "graphics", 5)
# one flash per layout CHANGE: a band that starts where the previous one ended
# is an image swap inside the same split, not a new layout
flash_at = [sp["hf0"] for i, sp in enumerate(splits)
            if i == 0 or sp["hf0"] - splits[i - 1]["hf1"] > 0.05]
for n, a in enumerate(flash_at):
    cid = f"flash-{n + 1}"
    # a light beam that sweeps across (no full-frame wash: a white wash behind
    # the caption dropped its contrast to ~1.1:1). The beam starts off-frame on
    # purpose, hence data-layout-allow-overflow.
    style = """        #beam { position: absolute; top: -10%; width: 360px; height: 120%; left: 0;
                background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,.8), rgba(255,255,255,0));
                filter: blur(16px); rotate: 14deg; }"""
    body = '        <div id="beam" data-layout-allow-overflow></div>'
    script = '          tl.fromTo("#beam", {x:-420}, {x:1180, duration:0.26, ease:"power2.inOut"}, 0);'
    (COMP / f"{cid}.html").write_text(sub(cid, style, body, script), encoding="utf-8")
    host(cid, max(0, a - 2 / FPS), 0.3, 2, "graphics", 28)  # below captions (30)

# inserts (edit-data `inserts[]`): full-frame B-roll cutaways and data cards.
# Each becomes its own editable clip, placed by SOURCE time like everything
# else; a B-roll entry also gets the flash + click the Prisma render gives it.
ins_vids, n_ins, broll_flash = [], 0, []
(ROOT / "assets" / "inserts").mkdir(parents=True, exist_ok=True)
for n, it in enumerate(ed.get("inserts") or [] if astart else []):
    a = cut_to_hf(it["start"])
    if a is None:  # the moment it covered was cut in the editor
        continue
    b = cut_to_hf(it["end"] - 1e-3)
    if b is None or b <= a:
        b = a + (it["end"] - it["start"])
    srcp = PUB / it["src"]
    if not srcp.exists():
        continue
    dst = "assets/inserts/" + srcp.name
    shutil.copy2(srcp, ROOT / dst)
    n_ins += 1
    if srcp.suffix.lower() in (".mp4", ".mov", ".webm", ".m4v"):
        # overlapping B-roll (one entering over the other) needs two lanes
        track = 6 if n % 2 == 0 else 7
        ins_vids.append(
            f'    <video id="broll-{n + 1:02d}" class="clip" src="{dst}" data-start="{fr(a)}" '
            f'data-duration="{fr(b - a)}" data-media-start="0" data-track-index="{track}" '
            f'muted playsinline style="position:absolute;inset:0;width:100%;height:100%;'
            f'object-fit:cover;z-index:{3 + n % 2}"></video>')
        broll_flash.append(a)
    else:  # data card: the Prisma card geometry (780x500, 90px from the top)
        cid = f"insert-{n + 1:02d}"
        style = """        #c { position: absolute; left: 150px; top: 90px; width: 780px; height: 500px; object-fit: contain;
             filter: drop-shadow(0 18px 40px rgba(0,0,0,.35)); }"""
        body = f'        <img id="c" src="{dst}" alt="" />'
        d = b - a
        script = (f'          tl.fromTo("#c", {{opacity:0, y:20}}, {{opacity:1, y:0, duration:0.35, ease:"power3.out"}}, 0);\n'
                  f'          tl.to("#c", {{opacity:0, duration:0.25, ease:"power2.in"}}, {fr(max(0.3, d - 0.25))});')
        (COMP / f"{cid}.html").write_text(sub(cid, style, body, script), encoding="utf-8")
        host(cid, a, d, 8, "graphics", 20)
for n, a in enumerate(sorted(broll_flash)):
    cid = f"flash-broll-{n + 1:02d}"
    style = """        #beam { position: absolute; top: -10%; width: 360px; height: 120%; left: 0;
                background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,.8), rgba(255,255,255,0));
                filter: blur(16px); rotate: 14deg; }"""
    body = '        <div id="beam" data-layout-allow-overflow></div>'
    script = '          tl.fromTo("#beam", {x:-420}, {x:1180, duration:0.26, ease:"power2.inOut"}, 0);'
    (COMP / f"{cid}.html").write_text(sub(cid, style, body, script), encoding="utf-8")
    host(cid, max(0, a - 2 / FPS), 0.3, 2, "graphics", 28)

# ending fade to black
fade = float(ed.get("fadeOut") or 0)
if fade:
    style = "        #blk { position: absolute; inset: 0; background: #000; opacity: 0; }"
    script = f'          tl.fromTo("#blk", {{opacity:0}}, {{opacity:1, duration:{fade}, ease:"none"}}, 0);'
    (COMP / "fade-out.html").write_text(sub("fade-out", style, '        <div id="blk"></div>', script), encoding="utf-8")
    host("fade-out", TOTAL - fade, fade, 5, "graphics", 50)

# ---- index.html ----
vids = []
for n, c in enumerate(clips):
    d = c["src1"] - c["src0"]
    auto = ""
    if fade and n == len(clips) - 1:
        auto = (f""" data-automation='{{"version":1,"lanes":[{{"target":"volume","points":"""
                f"""[{{"t":0,"v":1}},{{"t":{fr(d - fade)},"v":1}},{{"t":{fr(d)},"v":0}}]}}]}}'""")
    # picture and sound as a PAIR, per the core contract: the <video> is muted
    # and a matching <audio> (same src, start, media-start, duration) carries
    # the voice. An unmuted <video data-has-audio> is mixed in the render but
    # the Studio player never plays it — the editor was silent.
    vids.append(
        f'    <video id="{c["id"]}" class="clip" src="{SRC[c["source"]]}" data-start="{fr(c["hf0"])}" '
        f'data-duration="{fr(d)}" data-media-start="{fr(c["src0"])}" data-track-index="0" '
        f'muted playsinline style="{clip_style(c)}"></video>')
    vids.append(
        f'    <audio id="{c["id"]}-a" src="{SRC[c["source"]]}" data-start="{fr(c["hf0"])}" '
        f'data-duration="{fr(d)}" data-media-start="{fr(c["src0"])}" data-track-index="9" '
        f'data-volume="1" data-audio-group="voz"{auto}></audio>')
st = ed.get("soundtrack") or {}
music = []
MUSIC = None
# the bed goes in UN-carved (soundtrack.raw): HyperFrames carves it live
# against the "voz" group, and a pre-carved file would be carved twice
raw = PUB / (st.get("raw") or st.get("file") or "trilha.mp3")
if (st.get("enabled") or st.get("file")) and raw.exists():
    MUSIC = f"assets/audio/{raw.name}"
    shutil.copy2(raw, ROOT / MUSIC)
    vol = st.get("volume", 0.25)
    lanes = [{"t": 0, "v": 0}, {"t": 0.4, "v": 1}, {"t": fr(TOTAL - 1.5), "v": 1}, {"t": TOTAL, "v": 0}]
    music.append(
        f'    <audio id="trilha" src="{MUSIC}" data-start="0" data-duration="{TOTAL}" '
        f'data-track-index="10" data-volume="{vol}" data-audio-group="musica" '
        f"""data-automation='{json.dumps({"version": 1, "lanes": [{"target": "volume", "points": lanes}]})}'></audio>""")
click = PUB / "sfx" / "cut-click.mp3"
if click.exists():
    shutil.copy2(click, ROOT / "assets" / "audio" / "cut-click.mp3")
for n, a in enumerate(sorted(flash_at + broll_flash) if click.exists() else []):
    music.append(f'    <audio id="click-{n + 1}" src="assets/audio/cut-click.mp3" data-start="{fr(a)}" '
                 f'data-duration="0.1" data-track-index="11" data-volume="0.5" data-audio-group="sfx"></audio>')

index = f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    {GSAP}
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #000; }}
      video.clip {{ z-index: 0; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="{TOTAL}">
{chr(10).join(vids)}
{chr(10).join(ins_vids)}
{chr(10).join(hosts)}
{chr(10).join(music)}
  </div>
  <script>
    window.__timelines["main"] = gsap.timeline({{ paused: true }});
  </script>
  </body>
</html>
"""
(ROOT / "index.html").write_text(index, encoding="utf-8")

# ---- live voice carve (HyperFrames' own, editable in Studio) ----
CARVE = Path.home() / ".claude" / "skills" / "hyperframes-audio" / "scripts" / "carve.mjs"
if MUSIC and CARVE.exists():
    if not (ROOT / "node_modules" / "@hyperframes" / "core").exists():
        ver = run([HF, "--version"]).stdout.strip().splitlines()[-1]
        run(["npm", "i", "-D", "--silent", f"@hyperframes/core@{ver}"], cwd=ROOT, shell=sys.platform == "win32")
    run(["node", str(CARVE), "--comp", "index.html", "--bed", "trilha"], cwd=ROOT)

# ---- fingerprint + tell the Prisma preview where its editor lives ----
MARK.write_text(json.dumps({"index_sha1": project_sig(ROOT),
                            "edit": str(EDIT)}, indent=1), encoding="utf-8")
st_p = EDIT / "state.json"
if st_p.exists():
    state = json.loads(st_p.read_text(encoding="utf-8"))
    state["hyperframes"] = str(ROOT)
    st_p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
print(f"total {TOTAL}s · {len(clips)} video clips · {len(cues)} caption lines · "
      f"{len(hl_block.get('items') or [])} cards · {len(splits)} splits · {n_ins} inserts · "
      f"{len(flash_at) + len(broll_flash)} flashes")
