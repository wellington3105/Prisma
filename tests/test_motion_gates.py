"""Checks for the motionmaxxing port: eases, CSS scoping, flattening, the lint and look.py.

    python tests/test_motion_gates.py          (or: pytest tests/test_motion_gates.py)

The lint and render checks need node, Chrome and ffmpeg; they are skipped when one is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))

import motion_gates as mg  # noqa: E402
from hfkit import eases  # noqa: E402

# Published shape table (upstream references/motion.md §2): % of travel at 10/25/50/75 % of time.
SHAPES = {
    "cruise": (10, 25, 50, 75), "glide": (16, 39, 69, 91), "softInOut": (4, 17, 50, 83),
    "softLand": (30, 59, 85, 95), "gentleIn": (1, 6, 24, 55), "snapSettle": (54, 84, 96, 98),
    "whip": (23, 52, 83, 97), "accelExit": (0, 3, 16, 47), "crashOut": (0, 0, 6, 32),
    "popOver": (10, 46, 96, 108), "crashIn": (91, 118, 110, 103), "bounceHard": (13, 62, 138, 139),
}


def test_eases_match_measured_table():
    js = eases.JS_FILE.as_posix()
    code = (f"const E=require({json.dumps(js)});"
            "console.log(JSON.stringify(Object.fromEntries(E.names.map(k=>[k,[0,.1,.25,.5,.75,1].map(t=>E.fn[k](t))]))))")
    out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert set(out) == set(SHAPES) == set(eases.NAMES)
    for k, want in SHAPES.items():
        v = out[k]
        assert v[0] == 0 and v[-1] == 1, k
        got = tuple(round(x * 100) for x in v[1:5])
        assert all(abs(a - b) <= 1 for a, b in zip(got, want)), (k, got, want)


def test_eases_py():
    assert eases.tween("enter") == 'duration:0.4, ease:"softLand"'
    assert eases.ease("exit") == "accelExit"
    assert eases.seconds("crashOut") == round(17 / 30, 4)
    try:
        eases.ease("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown role must raise")
    assert "registerEase" in eases.script_inline()


def test_index_loads_eases():
    src = (HELPERS / "hfkit" / "project.py").read_text(encoding="utf-8")
    assert src.index("gsap.min.js") < src.index("prisma-eases.js")
    for w in ("beat_edit.py", "cinema_edit.py", "hf_motion_scenes.py", "export_hyperframes.py"):
        assert "{_eases_inline()}" in (HELPERS / w).read_text(encoding="utf-8"), w


def test_scope_css():
    s = mg.scope_css("#root-a{x:1} .fill{y:2} @font-face{f:P} @media (x){.b,.c{z:3}} html{q:1}", "#root-a")
    assert "#root-a .fill" in s and "#root-a .b, #root-a .c" in s and "@font-face{f:P}" in s
    assert "#root-a {q:1}" in s and "#root-a #root-a" not in s


def test_year_exemption():
    assert mg.YEAR_VALUE_RX.search("CABRIO · 2022")
    assert mg.YEAR_VALUE_RX.search("GLE 53 — 2024")
    assert not mg.YEAR_VALUE_RX.search("Revenue · $12,400")
    assert not mg.YEAR_VALUE_RX.search("DEOCAR · 02 / 05")


def _fixture(root: Path, label: str):
    (root / "compositions").mkdir(parents=True)
    (root / "assets" / "vendor").mkdir(parents=True)
    for f in (SKILL / "assets" / "hyperframes" / "vendor").glob("*.js"):
        shutil.copy2(f, root / "assets" / "vendor" / f.name)
    # Two sub-compositions sharing the class name `.fill`, laid out differently: the flat page must keep them apart.
    for cid, css, text in (("top", "justify-content:flex-start;padding-top:248px", "BMW 430i"),
                           ("chrome", "justify-content:flex-end;padding-bottom:20px", label)):
        (root / "compositions" / f"{cid}.html").write_text(f"""<!doctype html><html><head><meta charset="UTF-8"/></head><body><template>
<style>#root{{position:absolute;inset:0}} .fill{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;{css}}}
.t{{font:700 66px sans-serif;color:#fff}} .lab{{position:absolute;left:30px;top:30px;font:600 28px sans-serif;color:#fff;letter-spacing:.2em;text-transform:uppercase}}</style>
<div id="root" data-composition-id="{cid}" data-width="1080" data-height="1920"><div class="fill"><div class="{'t' if cid == 'top' else 'lab'}">{text}</div></div></div>
<script>(function(){{const tl=gsap.timeline({{paused:true}});tl.to({{}},{{duration:4}});window.__timelines["{cid}"]=tl;}})();</script>
</template></body></html>""", encoding="utf-8")
    hosts = "".join(f'<div id="{c}" class="clip" data-composition-id="{c}" data-composition-src="compositions/{c}.html" '
                    f'data-start="0" data-duration="4" data-track-index="{i}" style="z-index:{i + 2}"></div>'
                    for i, c in enumerate(("top", "chrome")))
    (root / "index.html").write_text(f"""<!doctype html><html><head><meta charset="UTF-8"/>
<script src="assets/vendor/gsap.min.js"></script><script src="assets/vendor/prisma-eases.js"></script>
<style>html,body{{margin:0;width:1080px;height:1920px;background:#234}}</style></head><body>
<div id="root" data-composition-id="main" data-width="1080" data-height="1920" data-duration="4">{hosts}</div>
<script>window.__timelines=window.__timelines||{{}};(function(){{const tl=gsap.timeline({{paused:true}});tl.to({{}},{{duration:4}});window.__timelines["main"]=tl;}})();</script>
</body></html>""", encoding="utf-8")


def _have_browser():
    try:
        mg.chrome()
    except SystemExit:
        return False
    return bool(shutil.which("node"))


def test_lint_sees_subcompositions():
    if not _have_browser():
        print("  skip: node or Chrome missing")
        return
    with tempfile.TemporaryDirectory() as d:
        bad, good = Path(d) / "bad", Path(d) / "good"
        _fixture(bad, "DEOCAR · 02 / 05")
        _fixture(good, "")
        rb = mg.run_lint(bad, samples=4, keep=False)
        rg = mg.run_lint(good, samples=4, keep=False)
        assert rb["subcompositions_inlined"] == 2
        assert rb["gate"]["status"] == "FAIL", rb
        assert {"C1", "C2"} <= {h["rule"] for h in rb["findings"]}
        assert rg["gate"]["status"] == "PASS", rg   # the big centred title is not chrome
        assert not (bad / "_motion_lint_flat.html").exists()


def test_render_profile():
    if not shutil.which("ffmpeg"):
        print("  skip: ffmpeg missing")
        return
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "v.mp4"
        # 1 s of moving picture, then 2 s of black: G2 must fail; one still take -> G3 note only under reels.
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=1",
                        "-f", "lavfi", "-i", "color=black:s=320x568:r=30:d=2", "-filter_complex", "[0][1]concat=n=2:v=1",
                        "-pix_fmt", "yuv420p", str(v)], check=True)
        r = mg.run_render(v, Path(d) / "out", "reels", expect=3.0)
        g = {x["id"]: x for x in r["gates"]}
        assert g["G0"]["status"] == "PASS", g["G0"]
        assert g["G2"]["status"] == "FAIL" and g["G2"]["gating"]
        assert not g["G3"]["gating"]
        assert mg.run_render(v, Path(d) / "out2", "film", None)["gates"][2]["gating"]


if __name__ == "__main__":
    fails = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
