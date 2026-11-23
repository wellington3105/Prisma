"""Demos and gallery for the editing-models library.

  material   downloads the demo material once (4 Pexels clips + 1 Epidemic track, IDs pinned in
             modelos/_demo/demo.json) into <galeria>/_material/, each recorded in the media ledger
  demo       renders a 4-6 s demo of one modelo, gates it with motion_gates (G0/G2) and writes
             <galeria>/<slug>/demo.mp4 + poster.jpg + gates.json
  galeria    builds <galeria>/index.html (see build_galeria)

The gallery lives OUTSIDE git (heavy files): $PRISMA_MODELOS_GALERIA, else
$OneDrive/Prisma/modelos-galeria/. Spec §5.5: docs/superpowers/specs/2026-11-22-biblioteca-modelos-design.md
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
import modelos_receitas as R  # noqa: E402

PY = sys.executable
DEMO_SHOTS = 4
DEMO_BEATS_PER_SHOT = 2
PEXELS_QUERY = "sports car driving"
EPIDEMIC_TERM = "energetic electronic"


def galeria_root() -> Path:
    v = os.environ.get("PRISMA_MODELOS_GALERIA", "").strip()
    if v:
        return Path(v)
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if od:
        return Path(od) / "Prisma" / "modelos-galeria"
    raise SystemExit("sem pasta para a galeria: defina PRISMA_MODELOS_GALERIA ou tenha o OneDrive configurado")


def _demo_json() -> Path:
    return R._root() / "_demo" / "demo.json"


def _run(cmd: list, cwd: Path | None = None, log: Path | None = None) -> None:
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if log:
        log.write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(map(str, cmd[:3]))}…\n{(p.stderr or p.stdout)[-1200:]}")


def _ledger(f: Path, source: str, query: str, license_: str, credit: str, url: str) -> None:
    _run([PY, HERE / "media_ledger.py", "record", f, "--source", source, "--query", query,
          "--license", license_, "--credit", credit, "--url", url])


# ---------------------------------------------------------------- material
def material(force: bool = False) -> dict:
    import requests
    import pexels_search
    cfg_path = _demo_json()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    mat = galeria_root() / "_material"
    mat.mkdir(parents=True, exist_ok=True)

    key = None
    if not cfg.get("pexels_videos") or force:
        key = pexels_search.load_api_key()
        vids = pexels_search.search_videos(PEXELS_QUERY, key, DEMO_SHOTS, "portrait", 3, 15)
        cfg["pexels_videos"] = [v["id"] for v in vids if pexels_search.pick_video_file(v)][:DEMO_SHOTS]
    clips = []
    for vid in cfg["pexels_videos"]:
        dest = mat / f"pexels-{vid}.mp4"
        if not dest.exists():
            key = key or pexels_search.load_api_key()
            r = requests.get(f"https://api.pexels.com/videos/videos/{vid}", headers={"Authorization": key}, timeout=60)
            r.raise_for_status()
            v = r.json()
            pexels_search.download(pexels_search.pick_video_file(v)["link"], dest)
            _ledger(dest, "pexels", PEXELS_QUERY, "Pexels License", v.get("user", {}).get("name", "?"), v.get("url", ""))
        clips.append(dest)

    if not cfg.get("epidemic_track") or force:
        shortlist = mat / "epidemic_shortlist.json"
        _run([PY, HERE / "epidemic_music.py", "search", EPIDEMIC_TERM, "--bpm", "110-130", "-n", "5", "--json", shortlist])
        cfg["epidemic_track"] = json.loads(shortlist.read_text(encoding="utf-8"))[0]["id"]
    music = mat / f"epidemic-{cfg['epidemic_track']}.mp3"
    if not music.exists():
        _run([PY, HERE / "epidemic_music.py", "download", cfg["epidemic_track"], "-o", music])
        _ledger(music, "epidemic", EPIDEMIC_TERM, "Epidemic Sound (assinatura)", "Epidemic Sound", "")
    beats = mat / f"beats-{cfg['epidemic_track']}.json"
    if not beats.exists():
        _run([PY, HERE / "beat_map.py", music, "-o", beats])

    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bl = json.loads(beats.read_text(encoding="utf-8"))["beats"]
    start = float(cfg.get("epidemic_start_s", 0))
    start_beat = next((i for i, t in enumerate(bl) if t >= start), 0)
    return {"clips": clips, "music": music, "beats": beats, "start_beat": start_beat}


# ---------------------------------------------------------------- demo plan + render
def demo_plan(m: R.Modelo, mat: dict) -> dict:
    """A 4-shot beat_edit plan with the recipe applied: shot 2 for a tipo, every shot for a range tipo or an estilo."""
    clips = mat["clips"]
    shots = [{"src": str(clips[i % len(clips)]), "in": 0.3, "beats": DEMO_BEATS_PER_SHOT} for i in range(DEMO_SHOTS)]
    plan = {"music": str(mat["music"]), "beats": str(mat["beats"]), "start_beat": mat.get("start_beat", 0),
            "fps": 30, "size": "1080x1920", "music_fade_out": 0.3, "fade_out": 0.3, "sfx": True, "shots": shots}
    if m.nivel == "estilo":
        return R.apply_montagem(m, plan, None, {})
    planos = list(range(1, DEMO_SHOTS)) if m.dados.get("intervalo") else [2]   # plano 0 has no incoming cut
    return R.apply_montagem(m, plan, planos, {})


def _render_montagem(m: R.Modelo, work: Path) -> Path:
    from hfkit.project import hf_cli
    plan_f = work / "plan.json"
    plan_f.write_text(json.dumps(demo_plan(m, material()), ensure_ascii=False, indent=2), encoding="utf-8")
    proj = work / "hf"
    _run([PY, HERE / "beat_edit.py", plan_f, "-o", proj, "--interp", "blend"], log=work / "beat_edit.log")
    _run(hf_cli() + ["render", "--fps", "30", "--quality", "delivery", "-o", "out/render.mp4"], cwd=proj,
         log=work / "render.log")
    return proj / "out" / "render.mp4"


def _fixture(work_root: Path) -> Path:
    fx = work_root / "fixture"
    v916 = fx / "v916" / "edit"
    if not v916.exists():
        _run([PY, SKILL / "tests" / "fixture_phase2" / "make_fixture.py", fx])
    return v916


def neutral_edit_data(ed: dict) -> dict:
    """The fixture ships with zooms, a push-in, inserts, highlights and a hook already on; a demo
    keeps only the presenter and the captions, so the recipe's effect is the only thing that moves."""
    out = json.loads(json.dumps(ed))
    cam = out.setdefault("camera", {})
    cam["zooms"], cam["pushIn"] = [1.0], 0.0
    out["transitions"] = []
    out["inserts"], out["splitInserts"] = [], []
    for k in ("hook", "highlights"):
        if isinstance(out.get(k), dict):
            out[k]["enabled"] = False
    return out


def _render_reel(m: R.Modelo, work: Path) -> Path:
    src = _fixture(work.parent)
    edit = work / "edit"
    if edit.exists():
        shutil.rmtree(edit)
    shutil.copytree(src, edit, symlinks=True)
    sp = edit / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    st.update(phase=2)
    st.setdefault("style", {})
    sp.write_text(json.dumps(st), encoding="utf-8")
    ed_path = R._edit_data_path(edit)
    ed_path.write_text(json.dumps(neutral_edit_data(json.loads(ed_path.read_text(encoding="utf-8"))),
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    acento = any(t.dados.get("acento") for t in R._reel_tipos(m))
    R.apply_reel_file(m, edit, [0] if acento else None)
    _run([PY, HERE / "render_phase2.py", "--edit", edit, "--engine", "auto", "--skip-delivery"], log=work / "render.log")
    outs = [p for p in (edit / "hyperframes" / "out" / "render.mp4", edit / "remotion" / "out" / "render.mp4") if p.exists()]
    if not outs:
        raise SystemExit(f"{m.slug}: o render da Fase 2 não gerou vídeo (ver {work / 'render.log'})")
    return max(outs, key=lambda p: p.stat().st_mtime)


def clear_demo(slug: str) -> None:
    """A forced re-render starts clean: a render that then fails must not leave the old demo marked ✅."""
    d = galeria_root() / slug
    for f in ("demo.mp4", "gates.json", "poster.jpg"):
        (d / f).unlink(missing_ok=True)


def _render_corte(m: R.Modelo, work: Path) -> Path:
    """Host "corte": the Phase-1 fixture EDL (9 ranges of the regression clip) with the recipe's
    EDL patch, rendered by render.py."""
    edl = json.loads((SKILL / "tests" / "fixture" / "edl_input.json").read_text(encoding="utf-8"))
    edl["sources"] = {k: str((SKILL / "tests" / "fixture" / "cayenne_clip.mp4").resolve()) for k in edl["sources"]}
    edl = R._merge(edl, m.dados.get("edl", {}))
    f = work / "edl.json"
    f.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    out = work / "cut.mp4"
    _run([PY, HERE / "render.py", f, "-o", out, "--no-subtitles"], log=work / "render.log")
    return out


def demo_photo() -> Path:
    """The still used by host "cena" demos: a Pexels studio photo pinned in demo.json (pexels_photo)."""
    import requests
    import pexels_search
    cfg = json.loads(_demo_json().read_text(encoding="utf-8"))
    pid = cfg["pexels_photo"]
    dest = galeria_root() / "_material" / f"pexels-foto-{pid}.jpg"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        key = pexels_search.load_api_key()
        r = requests.get(f"https://api.pexels.com/v1/photos/{pid}", headers={"Authorization": key}, timeout=60)
        r.raise_for_status()
        p = r.json()
        pexels_search.download(p["src"]["large2x"], dest)
        _ledger(dest, "pexels", "car studio photo", "Pexels License", p.get("photographer", "?"), p.get("url", ""))
    return dest


def _render_cena(m: R.Modelo, work: Path) -> Path:
    """Host "cena": the recipe's demo data, built and rendered by cenas.py. In the demo data "{foto}" is the
    pinned studio photo and "{fala}" the regression talking-head clip (local only, git-ignored)."""
    import cenas
    subs = {"{foto}": lambda: str(demo_photo()), "{fala}": lambda: str(SKILL / "tests" / "fixture" / "cayenne_clip.mp4")}

    def fill(v):
        if isinstance(v, str) and v in subs:
            return subs[v]()
        if isinstance(v, list):
            return [fill(x) for x in v]
        return v
    dados = R.cena_dados(m, {k: fill(v) for k, v in m.dados.get("demo", {}).items()}, {})
    proj = cenas.build(m.dados["cena"], dados, work / "cena")
    return cenas.render(proj, log=work / "render.log")


def render_demo(slug: str, force: bool = False) -> Path:
    import motion_gates
    m = R.load(slug)
    dest = galeria_root() / slug
    demo = dest / "demo.mp4"
    if demo.exists() and not force:
        print(f"  {slug}: demo já existe (use --force para refazer)")
        return demo
    if force:
        clear_demo(slug)
    work = galeria_root() / "_work" / slug
    work.mkdir(parents=True, exist_ok=True)
    video = (_render_montagem(m, work) if m.host == "montagem" else
             _render_corte(m, work) if m.host == "corte" else
             _render_cena(m, work) if m.host == "cena" else _render_reel(m, work))
    res = motion_gates.run_render(video, work / "look", "reels", None)
    gates = {g["id"]: g for g in res["gates"]}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "gates.json").write_text(json.dumps(res["gates"], ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [g for g in ("G0", "G2") if gates.get(g, {}).get("status") != "PASS"]
    if bad:
        demo.unlink(missing_ok=True)
        raise SystemExit(f"{slug}: demo reprovada em {', '.join(bad)} ({[gates[g]['why'] for g in bad if g in gates]}); "
                         f"não entra na galeria")
    shutil.copy2(video, demo)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(demo)],
                               capture_output=True, text=True).stdout.strip() or 2)
    _run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{dur / 2:.2f}", "-i", demo, "-frames:v", "1",
          "-vf", "scale=540:-1", dest / "poster.jpg"])
    print(f"  {slug}: demo → {demo}  (G0/G2 PASS)")
    return demo


# ---------------------------------------------------------------- gallery
def demo_status(slug: str) -> str:
    """✅ when the demo exists and its gates passed, else 🧪."""
    try:
        d = galeria_root() / slug
    except SystemExit:
        return "🧪"
    g = d / "gates.json"
    if not (d / "demo.mp4").exists() or not g.exists():
        return "🧪"
    st = {x.get("id"): x.get("status") for x in json.loads(g.read_text(encoding="utf-8"))}
    return "✅" if st.get("G0") == "PASS" and st.get("G2") == "PASS" else "🧪"


def _secao(m: R.Modelo, titulo: str) -> str:
    txt = (m.pasta / "MODELO.md").read_text(encoding="utf-8") if (m.pasta / "MODELO.md").exists() else ""
    if titulo not in txt:
        return ""
    return txt.split(titulo, 1)[1].split("\n## ", 1)[0].strip()


def build_galeria() -> Path:
    import html
    root = galeria_root()
    root.mkdir(parents=True, exist_ok=True)
    todos = R.load_all()
    grupos: dict[tuple[str, str], list[R.Modelo]] = {}
    for m in sorted(todos.values(), key=lambda m: (m.nivel != "estilo", m.familia, m.slug)):
        grupos.setdefault((m.nivel, "" if m.nivel == "estilo" else m.familia), []).append(m)
    cards = []
    for (nivel, familia), ms in grupos.items():
        titulo = "Estilos" if nivel == "estilo" else f"Tipos · {html.escape(familia)}"
        cards.append(f'<h2>{titulo}</h2><div class="grid">')
        for m in ms:
            nome = html.escape(m.dados.get("nome", m.slug))
            ok = demo_status(m.slug) == "✅"
            midia = (f'<video src="{m.slug}/demo.mp4" poster="{m.slug}/poster.jpg" autoplay loop muted playsinline></video>'
                     if ok else '<div class="vazio">sem demo</div>')
            tipos = ""
            if m.nivel == "estilo":
                tipos = "<p class='tipos'>Tipos: " + ", ".join(html.escape(t) for t in m.dados.get("tipos", [])) + "</p>"
            cards.append(f'<article>{midia}<h3>{nome}</h3><p class="slug">{m.slug} · {m.host}</p>'
                         f'<p>{html.escape(_secao(m, "## O que é"))}</p>'
                         f'<p><b>Quando usar:</b> {html.escape(_secao(m, "## Quando usar"))}</p>{tipos}'
                         f'<p class="gates">{"G0 ✓ G2 ✓" if ok else ""}</p></article>')
        cards.append("</div>")
    page = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Prisma · modelos de edição</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0d0d10;color:#e8e8ea;margin:32px}}
h1{{font-weight:700}} h2{{margin-top:40px;border-bottom:1px solid #2a2a30;padding-bottom:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px}}
article{{background:#17171c;border-radius:10px;padding:12px}}
video,.vazio{{width:100%;aspect-ratio:9/16;border-radius:8px;background:#000;object-fit:cover}}
.vazio{{display:flex;align-items:center;justify-content:center;color:#777}}
h3{{margin:10px 0 2px}} .slug{{color:#888;font-size:12px;margin:0 0 6px}} p{{font-size:13px;line-height:1.4}}
.gates{{color:#3ce6ac;font-size:12px}} .tipos{{color:#aaa}}
</style></head><body><h1>Prisma · biblioteca de modelos de edição</h1>
<p>{len(todos)} modelos · aplique com <code>helpers/modelos.py apply &lt;slug&gt;</code></p>
{''.join(cards)}</body></html>"""
    out = root / "index.html"
    out.write_text(page, encoding="utf-8")
    return out
