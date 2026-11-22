#!/usr/bin/env python3
"""motion_gates.py: motionmaxxing's render gates and slop lint, adapted to Prisma.

  python motion_gates.py render <video.mp4> [--profile reels|film] [--expect S] [--out DIR]
  python motion_gates.py lint   <hyperframes dir | index.html> [--samples N] [--keep]
  python motion_gates.py all    <video.mp4> <hyperframes dir> [--profile ...] [--out DIR]

render  runs helpers/vendor/motionmaxxing/look.py on the finished video: contact sheet,
        cuts, frozen stretches, loudness, cut-to-sound sync and the gates
          G0 render exists (decodes, not blank, moves, duration with --expect)
          G2 no empty frame (FAIL on a run of more than 3 flat frames)
          G3 end hold <= 1.4 s and last shot <= 25 % of the film
        Profile `reels` (default; a Reels/Short with a presenter): G0 and G2 are gates,
        G3 is a note, because a talking-head video can hold one long take to the end.
        Profile `film` (a motion-graphics piece, an opening, a brand sting): all three gate.

lint    runs helpers/vendor/motionmaxxing/lint.mjs (G5 "no page chrome": corner labels,
        "02 / 05" counters, tracked-caps kickers, deck layouts, letter-typed headlines,
        progress bars, vibe-coded UI cards). The lint reads the DOM of one page and
        cannot see HyperFrames sub-compositions (data-composition-src), so this first
        writes a FLAT copy of index.html next to it (each sub-composition inlined in its
        host, its timeline seeked at local time and hidden outside its window), lints
        that and deletes it (--keep leaves it for inspection).
        Text drawn into <canvas>, images or video is invisible to the lint: a PASS is a
        lead, not a verdict on taste.

Writes <out>/motion_gates.json (default <video dir>/verify/motion_<stem>/). Exit 0 when
every gate of the profile passes, 1 on a FAIL, 2 on a usage or tool error.
Source: github.com/Tejashmakwana/motionmaxxing (Apache-2.0); see
helpers/vendor/motionmaxxing/PROVENANCE.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor" / "motionmaxxing"
CHROME_CANDIDATES = [
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
]
GATING = {"reels": {"G0", "G2"}, "film": {"G0", "G2", "G3"}}


def die(msg: str, code: int = 2):
    print(f"motion_gates: {msg}", file=sys.stderr)
    sys.exit(code)


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    die("Google Chrome not found (set CHROME_PATH)")


# ---------------------------------------------------------------- render (look.py)
def run_render(video: Path, out: Path, profile: str, expect: float | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(VENDOR / "look.py"), str(video), "--out", str(out)]
    if expect is not None:
        cmd += ["--expect", str(expect)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (out / "look.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    gj = out / "gates.json"
    if not gj.exists():
        die(f"look.py produced no gates.json (exit {p.returncode}):\n{(p.stderr or p.stdout)[-1500:]}")
    raw = json.loads(gj.read_text(encoding="utf-8"))
    gates = []
    for g in (raw.get("gates", raw) if isinstance(raw, dict) else raw):
        gid, name, status, why = (g.get("id"), g.get("name"), g.get("status"), g.get("detail", "")) if isinstance(g, dict) else g[:4]
        gating = gid in GATING[profile]
        gates.append({"id": gid, "name": name, "status": status, "gating": gating, "why": why})
    motion = None
    m = re.search(r"mean frame-to-frame luma change ([\d.]+)/255", p.stdout)
    if m:
        motion = float(m.group(1))
    sync = re.search(r"cut sync\s+(.+)", p.stdout)
    misses = re.search(r"near misses:\s+(.+)", p.stdout)
    return {"profile": profile, "gates": gates, "motion_mean": motion,
            "motion_band": "human-made median 6.8, IQR 4.4-9.8 (a question, not a gate)",
            "cut_sync": sync.group(1).strip() if sync else None,
            "cut_near_misses": misses.group(1).strip() if misses else None,
            "sheet": str(out / "sheet.jpg"), "strips": str(out / "strips.jpg"), "log": str(out / "look.txt")}


# ---------------------------------------------------------------- lint (lint.mjs)
TEMPLATE_RX = re.compile(r"<template>(.*)</template>", re.S | re.I)
SCRIPT_RX = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
HOST_RX = re.compile(r'<div\b(?=[^>]*\bdata-composition-src="([^"]+)")[^>]*>\s*</div>', re.I)
ATTR = lambda tag, a: (re.search(rf'\b{a}="([^"]*)"', tag) or [None, None])[1]
YEAR_VALUE_RX = re.compile(r"[·•|\-–—]\s*(19|20)\d{2}\s*$")
STYLE_RX = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)


def scope_css(css: str, scope: str) -> str:
    """Prefix every top-level selector with `scope` (at-rules other than @media are kept as they are)."""
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            out.append(css[i:])
            break
        head = css[i:j]
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        block = css[j:k]
        h = head.strip()
        if h.startswith("@media") or h.startswith("@supports"):
            out.append(head + "{" + scope_css(block[1:-1], scope) + "}")
        elif h.startswith("@"):
            out.append(head + block)
        else:
            sels = []
            for sel in h.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                if sel.startswith(scope):
                    sels.append(sel)
                elif sel in ("html", "body", ":root"):
                    sels.append(scope)
                else:
                    sels.append(f"{scope} {sel}")
            lead = head[: len(head) - len(head.lstrip())]
            out.append(lead + ", ".join(sels) + " " + block)
        i = k
    return "".join(out)


def flatten(index: Path, dest_dir: Path | None = None) -> tuple[Path, int]:
    """Inline every sub-composition into its host so one DOM holds the whole film."""
    src = index.read_text(encoding="utf-8")
    subs: list[dict] = []

    def inline(m: re.Match) -> str:
        tag = m.group(0)
        rel = m.group(1)
        cid = ATTR(tag, "data-composition-id") or ATTR(tag, "id") or f"c{len(subs)}"
        f = (index.parent / rel)
        if not f.exists():
            return tag
        t = TEMPLATE_RX.search(f.read_text(encoding="utf-8"))
        if not t:
            return tag
        body = t.group(1)
        scripts = SCRIPT_RX.findall(body)
        body = SCRIPT_RX.sub("", body)
        rid = "root-" + re.sub(r"[^A-Za-z0-9_-]", "_", cid)
        body = re.sub(r'\bid="root"', f'id="{rid}"', body)
        body = body.replace("#root", "#" + rid)
        # Every sub-composition is its own document in HyperFrames; on one flat page their
        # rules would collide (two `.fill` classes laid out differently), so scope them.
        body = STYLE_RX.sub(lambda s: s.group(1) + scope_css(s.group(2), "#" + rid) + s.group(3), body)
        scripts = [s.replace("#root", "#" + rid).replace('"root"', f'"{rid}"').replace("'root'", f"'{rid}'") for s in scripts]
        subs.append({"cid": cid, "hid": ATTR(tag, "id") or cid,
                     "start": float(ATTR(tag, "data-start") or 0), "dur": float(ATTR(tag, "data-duration") or 0),
                     "scripts": scripts})
        opened = tag[: tag.index(">") + 1]
        opened = opened.replace("data-composition-src=", "data-flat-src=")
        if "style=" in opened:
            opened = re.sub(r'style="', 'style="position:absolute;inset:0;', opened, count=1)
        else:
            opened = opened[:-1] + ' style="position:absolute;inset:0">'
        return opened + body + "</div>"

    flat = HOST_RX.sub(inline, src)
    boot = ["window.__timelines = window.__timelines || {};"]
    for s in subs:
        boot += s["scripts"]
    table = json.dumps([{k: s[k] for k in ("cid", "hid", "start", "dur")} for s in subs])
    boot.append(f"""
(function () {{
  var subs = {table};
  window.__seek = function (t) {{
    var tl = window.__timelines || {{}};
    if (tl.main && tl.main.seek) {{ tl.main.pause(); tl.main.seek(t, false); }}
    subs.forEach(function (s) {{
      var el = document.getElementById(s.hid), local = t - s.start, on = local >= 0 && local < s.dur;
      if (el) el.style.visibility = on ? 'visible' : 'hidden';
      var x = tl[s.cid];
      if (x && x.seek) {{ x.pause(); x.seek(Math.max(0, Math.min(local, s.dur)), false); }}
    }});
  }};
}})();""")
    flat = re.sub(r"</body>", "<script>\n" + "\n".join(boot) + "\n</script>\n</body>", flat, count=1, flags=re.I)
    # The root's own <script> runs before the boot block and may reference window.__timelines.
    flat = flat.replace("<head>", "<head>\n<script>window.__timelines = window.__timelines || {};</script>", 1)
    if dest_dir is None:
        out = index.parent / "_motion_lint_flat.html"
    else:
        # Written OUTSIDE the project (the critic is read-only): a <base> keeps every relative
        # asset path (fonts, media, vendor JS) resolving against the real project folder.
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "_motion_lint_flat.html"
        flat = flat.replace("<head>", f'<head>\n<base href="{index.parent.resolve().as_uri()}/">', 1)
    out.write_text(flat, encoding="utf-8")
    return out, len(subs)


def run_lint(target: Path, samples: int | None, keep: bool, work: Path | None = None) -> dict:
    index = target / "index.html" if target.is_dir() else target
    if not index.exists():
        die(f"no index.html at {target}")
    flat, n_subs = flatten(index, work)
    env = dict(os.environ, CHROME_PATH=chrome())
    cmd = ["node", str(VENDOR / "lint.mjs"), str(flat), "--json"]
    if samples:
        cmd += ["--samples", str(samples)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=900)
    finally:
        if not keep:
            flat.unlink(missing_ok=True)
    try:
        res = json.loads(p.stdout)
    except json.JSONDecodeError:
        die(f"lint.mjs failed (exit {p.returncode}):\n{(p.stderr or p.stdout)[-1500:]}")
    # Prisma exemption: "MODEL · 2022" (a car title with its model year) is how Deocar names
    # a car, not a dashboard "Revenue · $12,400" line. Only V2, only when the value is a year.
    exempt = []
    for r in res.get("rules", []):
        if r.get("id") != "V2":
            continue
        keep = [h for h in (r.get("hits") or []) if not YEAR_VALUE_RX.search(h.get("text") or "")]
        exempt += [h.get("text") for h in (r.get("hits") or []) if YEAR_VALUE_RX.search(h.get("text") or "")]
        r["hits"] = keep
        if not keep:
            r["status"] = "PASS"
    failed = [r.get("id") for r in res.get("rules", []) if r.get("status") == "FAIL"]
    res["failed"], res["gate"] = failed, ("FAIL" if failed else "PASS")
    hits = []
    for r in res.get("rules", []):
        if r.get("status") in ("FAIL", "WARN"):
            ex = (r.get("hits") or [])[:3]
            hits.append({"rule": r.get("id"), "name": r.get("name"), "status": r.get("status"),
                         "examples": [{"t": (e.get("times") or [None])[0], "text": e.get("text"), "bbox": e.get("bbox"), "note": e.get("note")}
                                      for e in ex if isinstance(e, dict)]})
    return {"index": str(index), "subcompositions_inlined": n_subs, "samples": len(res.get("samples") or []),
            "gate": {"id": "G5", "name": "no page chrome", "status": res.get("gate"), "gating": True,
                     "why": ("failed: " + ", ".join(res.get("failed") or [])) if res.get("failed") else "no rule failed"}, "findings": hits,
            "prisma_exempt": [f"V2 model-year title: {t}" for t in exempt],
            "limit": "text inside <canvas>, images or video is not seen"}


# ---------------------------------------------------------------- report
def report(res: dict) -> int:
    gates = list(res.get("render", {}).get("gates", []))
    if "lint" in res:
        gates.append(res["lint"]["gate"])
    bad = False
    print("MOTION GATES" + (f"  (profile {res['render']['profile']})" if "render" in res else ""))
    for g in gates:
        tag = g["status"] if g["gating"] else f"{g['status']} (note)"
        if g["gating"] and g["status"] == "FAIL":
            bad = True
        print(f"  {g['id']:<3} {g['name']:<28} {tag:<12} {g['why']}")
    r = res.get("render")
    if r:
        if r["motion_mean"] is not None:
            print(f"  motion   mean luma change {r['motion_mean']}/255 ({r['motion_band']})")
        if r["cut_sync"]:
            print(f"  cut sync {r['cut_sync']}")
        if r["cut_near_misses"]:
            print(f"           near misses: {r['cut_near_misses']}")
        print(f"  sheet    {r['sheet']}   (judge G1 'proof readable' and G4 'one hero per frame' by eye)")
    L = res.get("lint")
    if L:
        print(f"  lint     {L['subcompositions_inlined']} sub-composition(s) inlined, {L['samples']} samples")
        for h in L["findings"]:
            ex = "; ".join(f"t={e['t']} {e['text']!r}" for e in h["examples"])
            print(f"    {h['rule']:<3} {h['status']:<4} {h['name']}: {ex}")
        for e in L.get("prisma_exempt", []):
            print(f"    exempt   {e}")
    print("RESULT", "FAIL" if bad else "PASS")
    return 1 if bad else 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "all"):
        s = sp.add_parser(name)
        s.add_argument("video", type=Path)
        if name == "all":
            s.add_argument("hf", type=Path)
        s.add_argument("--profile", choices=sorted(GATING), default="reels")
        s.add_argument("--expect", type=float)
        s.add_argument("--out", type=Path)
        s.add_argument("--samples", type=int)
        s.add_argument("--keep", action="store_true")
    s = sp.add_parser("lint")
    s.add_argument("hf", type=Path)
    s.add_argument("--samples", type=int)
    s.add_argument("--keep", action="store_true")
    s.add_argument("--out", type=Path)
    a = ap.parse_args()

    if not shutil.which("node") and a.cmd in ("lint", "all"):
        die("node not on PATH (lint.mjs needs Node 22+)")
    res: dict = {}
    if a.cmd in ("render", "all"):
        if not a.video.exists():
            die(f"no such video: {a.video}")
        out = a.out or (a.video.parent / "verify" / f"motion_{a.video.stem}")
        res["render"] = run_render(a.video, out, a.profile, a.expect)
    else:
        out = a.out or ((a.hf if a.hf.is_dir() else a.hf.parent) / "verify_motion")
    if a.cmd in ("lint", "all"):
        res["lint"] = run_lint(a.hf, a.samples, a.keep, work=out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "motion_gates.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    code = report(res)
    print(f"written  {out / 'motion_gates.json'}")
    sys.exit(code)


if __name__ == "__main__":
    main()
