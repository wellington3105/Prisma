"""Takes cut by hand in the HyperFrames Studio (Phase 2) → back to the EDL.

In Phase 2 the picture is `assets/base.mp4` = cut.mp4, and the voice is cut.mp4's
audio mixed by deliver_mix. A take trimmed, split or deleted in the Studio no
longer matches that audio — so it is never rendered as is (decision 1): the cut
goes back to the EDL, cut.mp4 is re-rendered (~1–2 min) and the builder
re-applies the overlays.

    uv run python helpers/hf_pull_takes.py <edit> [--dry-run]

  1. compares every `<video id="take-NN">` in hyperframes/index.html with the
     registry the builder wrote in .prisma-export.json;
  2. writes <edit>/preview_edits.json (`edl.ranges/removed/splits`, the format the
     preview UI already writes);
  3. then, as for any preview edit: apply_preview_edits.py → refine_edges.py →
     render.py → verify_cut.py → build_hyperframes.py --force.

A take MOVED in time (same media, new start) cannot be expressed on top of one
audio track; it is reported and left out. Extending a take past its cut is not
possible on base.mp4 — ask for it as an EDL change.

`changed_takes(root)` is used by render_phase2 to refuse a delivery with takes
edited and not pulled.
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
import re
from pathlib import Path

TOL = 0.004  # s


def _takes_now(index_html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<video([^>]*)>", index_html):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        if not a.get("id", "").startswith("take-") or "base.mp4" not in a.get("src", ""):
            continue
        out.append({"id": a["id"], "start": float(a.get("data-start", 0)), "dur": float(a.get("data-duration", 0)),
                    "media": float(a.get("data-media-start", a.get("data-start", 0)))})
    return sorted(out, key=lambda t: t["start"])


def _registry(root: Path):
    mark = root / ".prisma-export.json"
    try:
        m = json.loads(mark.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    info = {}
    try:
        info = json.loads((root / "render.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return (m.get("takes") if m.get("builder") == "build_hyperframes" else None), info


def changed_takes(root: Path) -> list[str]:
    """Ids of takes whose cut differs from what the builder wrote ([] = untouched)."""
    reg, info = _registry(root)
    if not reg or not (root / "index.html").exists():
        return []
    fps = int(info.get("fps") or 30)
    now = {t["id"]: t for t in _takes_now((root / "index.html").read_text(encoding="utf-8"))}
    diffs = []
    for t in reg:
        n = now.pop(t["id"], None)
        if n is None:
            diffs.append(f"{t['id']} removido")
            continue
        if abs(n["media"] - t["f0"] / fps) > TOL or abs(n["start"] - t["f0"] / fps) > TOL \
                or abs(n["start"] + n["dur"] - t["f1"] / fps) > TOL:
            diffs.append(f"{t['id']} aparado/movido")
    diffs += [f"{k} novo (split)" for k in now]
    return diffs


def pull(edit: Path, dry: bool) -> int:
    root = edit / "hyperframes"
    reg, info = _registry(root)
    if not reg:
        raise SystemExit("sem registro de takes do build_hyperframes (.prisma-export.json) — nada a comparar")
    fps = int(info.get("fps") or 30)
    lag = int(info.get("lagFrames") or 1) / fps
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    R = edl["ranges"]
    jt = edl.get("jcut_timeline") or []
    if len(jt) != len(R) or len(reg) != len(R):
        raise SystemExit(f"EDL ({len(R)} ranges, jcut_timeline {len(jt)}) não casa com os {len(reg)} takes do projeto — "
                         "o cut.mp4 mudou depois da montagem? Remonte com build_hyperframes.py")
    now = _takes_now((root / "index.html").read_text(encoding="utf-8"))
    # cut-time picture window of every original take
    orig = [{"k": k, "c0": max(0.0, t["f0"] / fps - lag), "c1": t["f1"] / fps - lag} for k, t in enumerate(reg)]
    out, used, moved = [], set(), []
    for n in now:
        c0, c1 = n["media"] - lag, n["media"] + n["dur"] - lag
        k = max(orig, key=lambda o: min(o["c1"], c1) - max(o["c0"], c0))["k"]
        o = orig[k]
        if min(o["c1"], c1) - max(o["c0"], c0) <= 0:
            moved.append(n["id"])
            continue
        if abs(n["start"] - n["media"]) > TOL:
            moved.append(n["id"])     # timeline position no longer equals the cut position
        r = dict(R[k])
        head = max(0.0, c0 - o["c0"])          # picture trimmed at the head
        tail = max(0.0, o["c1"] - c1)          # … and at the tail
        r["start"] = round(R[k]["start"] + head, 3) if head > TOL else R[k]["start"]
        r["end"] = round(R[k]["end"] - tail, 3) if tail > TOL else R[k]["end"]
        out.append(r)
        used.add(k)
    removed = [dict(R[k]) for k in range(len(R)) if k not in used]
    splits = max(0, len(out) - len(used))
    changed = changed_takes(root)
    print(f"takes no projeto: {len(now)} · originais: {len(R)} · removidos {len(removed)} · splits {splits}")
    for c in changed:
        print(f"  {c}")
    for m in moved:
        print(f"  ⚠ {m}: take movido no tempo — não cabe sobre um áudio só; fica como estava no corte")
    if not changed:
        print("nenhum take mudou — nada a puxar")
        return 0
    pe = edit / "preview_edits.json"
    body = json.loads(pe.read_text(encoding="utf-8")) if pe.exists() else {}
    body["edl"] = {"ranges": out, "removed": removed, "splits": splits, "source": "hf_pull_takes"}
    if dry:
        print("--dry-run: nada gravado")
        return 1
    pe.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gravado {pe.name}. Agora: apply_preview_edits.py → refine_edges.py → render.py → verify_cut.py → "
          f"build_hyperframes.py --force")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if pull(a.edit.resolve(), a.dry_run) == 0 else 3)


import sys  # noqa: E402

if __name__ == "__main__":
    main()
