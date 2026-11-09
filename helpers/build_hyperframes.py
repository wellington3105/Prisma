"""Build the Phase-2 HyperFrames project from the SAME edit-data.json Remotion reads.

    uv run python helpers/build_hyperframes.py <edit> [--out <edit>/hyperframes] [--force]
           [--only base,captions,hook,highlights,broll,inserts,splitInserts,fadeOut]
           [--check] [--render] [--sync-probe] [--allow-unported]

Data root stays `<edit>/remotion/public` (edit-data.json, captions.json,
segments.json, track.json, media) so safe_layout, sfx_events, inserts_plan,
qa_mix, deliver_mix and the Estilo gate do not change. The picture is
`assets/base.mp4` (cut.mp4, already graded in Phase 1, one clip per take); every
layer is its own sub-composition (references/hyperframes-engine.md). The audio of
the HyperFrames render is NEVER delivered: `deliver_mix.py --picture` mixes voice,
soundtrack and SFX (Hard Rule 10).

Refuses when the project was edited in the Studio since the last build (the
fingerprint, as in export_hyperframes.py) unless --force; takes trimmed in the
Studio go back to the EDL with helpers/hf_pull_takes.py first.
Refuses an edit-data with unported layers (the whole video belongs in Remotion,
decision 2) unless --allow-unported, which builds the ported subset for review.

Writes `<out>/render.json`: layer windows (frames + parity boxes), tone times
(base-only frames, for deliver_mix --tone-ref), the takes (for hf_pull_takes).
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
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from hfkit import timebase as tb  # noqa: E402
from hfkit.project import HF_PIN, Project, hf_cli, js, project_sig, run  # noqa: E402
from hfkit.measure import Measurer  # noqa: E402
from hfkit.layers import Ctx, unported, needs_gl  # noqa: E402
from hfkit.layers import base, captions, hook, highlights, media  # noqa: E402

ORDER = ("base", "broll", "inserts", "splitInserts", "highlights", "hook", "captions", "fadeOut")


def detect_format(edit: Path, ed: dict) -> str:
    try:
        root = (edit / "remotion" / "src" / "Root.tsx").read_text(encoding="utf-8")
        if 'id="Longform"' in root:
            return "long"
        if 'id="Reels"' in root:
            return "short"
    except OSError:
        pass
    return "long" if int(ed.get("width") or 1080) > int(ed.get("height") or 1920) else "short"


def tone_times(windows: dict, n: int, fps: int, want: int = 6) -> list[float]:
    """Frames where only the base is on screen, away from seams and layer edges."""
    busy = [False] * n
    for key, wins in windows.items():
        if key in ("base", "syncProbe"):
            continue
        for w in wins:
            for f in range(max(0, w["f0"] - 6), min(n, w["f1"] + 6)):
                busy[f] = True
    for w in windows.get("base", []):
        for f in range(max(0, w["f0"] - 2), min(n, w["f0"] + 3)):
            busy[f] = True
    free = [f for f in range(int(fps), n - int(fps)) if not busy[f]]
    if not free:
        return []
    step = max(1, len(free) // want)
    return [round(f / fps, 4) for f in free[step // 2::step][:want]]


def add_sync_probe(ctx: Ctx):
    caps = captions.words(ctx)
    onsets = sorted({ctx.f(w["startMs"] / 1000) + tb.PICTURE_LAG for w in caps})
    cid = ctx.proj.uid("sync-probe")
    ctx.proj.sub(cid, f"        #{cid}-b {{ position:absolute; left:0; top:0; width:80px; height:80px; background:#fff; opacity:0; }}",
                 f'        <div id="{cid}-b"></div>',
                 f"          PrismaHF.layers.syncProbe(tl, {js({'id': f'{cid}-b', 'fps': ctx.fps, 'total': ctx.N, 'onsets': onsets})});",
                 fonts=False)
    ctx.proj.host(cid, 0, ctx.N, 12, "graphics", 200, "syncProbe", [0, 0, 80, 80])
    return onsets


def main() -> None:
    ap = argparse.ArgumentParser(description="Prisma edit-data → HyperFrames project (Phase 2)")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true", help="overwrite even if edited in the Studio")
    ap.add_argument("--only", default="", help="comma list of layers to build (base is always built)")
    ap.add_argument("--check", action="store_true", help="run `hyperframes check --json` after building")
    ap.add_argument("--render", action="store_true", help="render <out>/out/render.mp4 after building")
    ap.add_argument("--sync-probe", action="store_true", help="flash a square on every word onset (A/V test)")
    ap.add_argument("--allow-unported", action="store_true", help="build the ported layers even if others are on")
    a = ap.parse_args()

    edit = a.edit.resolve()
    pub = edit / "remotion" / "public"
    root = (a.out or (edit / "hyperframes")).resolve()
    ed_p = pub / "edit-data.json"
    if not ed_p.exists():
        raise SystemExit(f"sem edit-data.json em {pub}")
    ed = json.loads(ed_p.read_text(encoding="utf-8"))

    missing = unported(ed, pub, edit)
    if missing and not a.allow_unported:
        raise SystemExit("camadas não portadas para o HyperFrames: " + ", ".join(missing)
                         + " — o vídeo inteiro vai para o Remotion (render_phase2 --engine auto), "
                           "ou use --allow-unported para montar só o resto (revisão)")

    mark = root / ".prisma-export.json"
    if (root / "index.html").exists() and mark.exists() and not a.force:
        was = json.loads(mark.read_text(encoding="utf-8")).get("index_sha1")
        if was and was != project_sig(root):
            raise SystemExit("o projeto foi editado no Studio depois da última montagem — remontar apagaria "
                             "essas edições. Takes cortados: rode helpers/hf_pull_takes.py; overlays: renderize "
                             "direto (render_phase2 --engine hyperframes --no-rebuild); ou use --force.")

    fps = int(ed.get("fps") or 30)
    W, H = int(ed.get("width") or 1080), int(ed.get("height") or 1920)
    N = tb.fround(float(ed.get("durationSec") or 0), fps)
    if N <= 0:
        raise SystemExit("edit-data.durationSec ausente")
    fmt = detect_format(edit, ed)
    t0 = time.time()
    proj = Project(root, W, H, fps)
    proj.init(edit)
    hf = hf_cli()
    meas = Measurer(root, hf)
    segs = tb.load_segments(pub)
    ctx = Ctx(edit=edit, pub=pub, ed=ed, proj=proj, meas=meas, W=W, H=H, fps=fps, N=N, fmt=fmt,
              segs=segs, seams=tb.seam_frames(segs, fps, N) if segs else [0],
              only=set(x.strip() for x in a.only.split(",") if x.strip()) or None)

    try:
        track = json.loads((pub / "track.json").read_text(encoding="utf-8")).get("points") or []
    except (OSError, json.JSONDecodeError):
        track = []

    def track_point(f):
        p = track[min(f, len(track) - 1)] if track else [0.5, 0.4]
        return (p[0] / W if p[0] > 1 else p[0]), (p[1] / H if p[1] > 1 else p[1])
    ctx.track_point = track_point

    try:
        for key in ORDER:
            if key != "base" and not ctx.wants(key):
                continue
            if key == "base":
                base.build(ctx)
            elif key == "captions" and (ed.get("captions") or {}).get("enabled") \
                    and (ed["captions"].get("style") or "karaoke") == "karaoke":
                captions.build(ctx)
            elif key == "hook" and (ed.get("hook") or {}).get("enabled"):
                hook.build(ctx)
            elif key == "highlights" and (ed.get("highlights") or {}).get("enabled") \
                    and (ed["highlights"].get("variant") or "prism") in ("prism", "pill"):
                highlights.build(ctx)
            elif key == "broll" and ed.get("broll"):
                media.build_broll(ctx)
            elif key == "inserts" and ed.get("inserts"):
                media.build_inserts(ctx)
            elif key == "splitInserts" and ed.get("splitInserts"):
                media.build_split(ctx)
            elif key == "fadeOut":
                media.build_fade(ctx)
        onsets = add_sync_probe(ctx) if a.sync_probe else []
    finally:
        meas.close()
    proj.write_index(N)

    tones = tone_times(proj.windows, N, fps)
    info = {"engine": "hyperframes", "hyperframes": HF_PIN, "builder": "build_hyperframes", "format": fmt,
            "fps": fps, "width": W, "height": H, "frames": N, "lagFrames": tb.TEMPLATE_LAG, "pictureLagFrames": tb.PICTURE_LAG,
            "gl": needs_gl(ed, pub), "unported": missing, "windows": proj.windows,
            "toneTimes": tones, "toneCam": [base.cam_for_frame(ctx, int(round(t * fps))) for t in tones],
            "takes": getattr(ctx, "takes", []),
            "syncOnsets": onsets, "notes": ctx.notes, "built": time.strftime("%Y-%m-%d %H:%M:%S")}
    (root / "render.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    mark.write_text(json.dumps({"index_sha1": project_sig(root), "edit": str(edit), "builder": "build_hyperframes",
                                "takes": info["takes"]}, indent=1), encoding="utf-8")
    st_p = edit / "state.json"
    if st_p.exists():
        try:
            state = json.loads(st_p.read_text(encoding="utf-8"))
            state["hyperframes"] = str(root)
            state["hyperframesVersion"] = HF_PIN
            st_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    counts = {k: len(v) for k, v in proj.windows.items()}
    print(f"montado em {time.time() - t0:.1f}s · {fmt} {W}x{H}@{fps} · {N} quadros · "
          + " · ".join(f"{k} {n}" for k, n in counts.items()))
    for n in ctx.notes:
        print(f"⚠ {n}")

    if a.check or a.render:
        r = subprocess.run(hf + ["check", "--json"], cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else "{}"
        try:
            chk = json.loads(out)
        except json.JSONDecodeError:
            chk = {}
        errs = [(sec, f) for sec, v in chk.items() if isinstance(v, dict)
                for f in (v.get("findings") or []) if f.get("severity") == "error"]
        warns = [(sec, f) for sec, v in chk.items() if isinstance(v, dict)
                 for f in (v.get("findings") or []) if f.get("severity") == "warning"]
        print(f"check: {len(errs)} erro(s), {len(warns)} aviso(s)")
        for sec, f in (errs + warns)[:12]:
            print(f"  [{sec}] {f.get('severity')} {f.get('code')}: {str(f.get('message'))[:160]}")
        if errs or not chk.get("ok", False) and errs:
            raise SystemExit("hyperframes check com erros — não renderizado")
    if a.render:
        (root / "out").mkdir(exist_ok=True)
        cmd = hf + ["render", "--fps", str(fps), "--quality", "delivery", "-o", "out/render.mp4"]
        if info["gl"]:
            cmd.append("--browser-gpu")
        t1 = time.time()
        r = run(cmd, cwd=root)
        tail = [l for l in r.stdout.splitlines() if l.strip()][-2:]
        print(f"render HF em {time.time() - t1:.1f}s → {root / 'out' / 'render.mp4'}")
        for l in tail:
            print("  " + l.strip())


if __name__ == "__main__":
    main()
