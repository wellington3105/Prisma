"""Checks for the AI auto colour (auto_color.py) and its per-source grades in render.py.

    python tests/test_auto_color.py          (or: pytest tests/test_auto_color.py)

The end-to-end check needs ffmpeg and torch; it is skipped when one is missing.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))

import render  # noqa: E402


def test_source_grade_override():
    edl = {"grade": "warm", "grades": {"a.mov": "lut3d=file=grade/a.cube,hqdn3d=1.5"}}
    assert render.source_grade(edl, "a.mov", "x") == "lut3d=file=grade/a.cube,hqdn3d=1.5"
    assert render.source_grade(edl, "b.mov", "x") is None          # not listed: global grade
    assert render.source_grade({"grade": "warm"}, "a.mov", "x") is None
    assert render.source_grade({"grades": {"a.mov": "auto"}}, "a.mov", "x") == ""   # auto per source = no override filter


def test_nlmeans_goes_back_to_yuv():
    # The 8 px black band on the right at width 1080: nlmeans fed with RGB. render.py inserts
    # format=yuv420p before nlmeans unless it is already there.
    src = (HELPERS / "render.py").read_text(encoding="utf-8")
    pat = re.search(r're\.sub\((r"[^"]+"), ("[^"]+"), grade_filter\)', src)
    assert pat, "the nlmeans guard is missing from render.py"
    rx, repl = eval(pat.group(1)), eval(pat.group(2))
    assert re.sub(rx, repl, "lut3d=file=x.cube,nlmeans=s=2") == "lut3d=file=x.cube,format=yuv420p,nlmeans=s=2"
    assert re.sub(rx, repl, "lut3d=x,format=yuv420p,nlmeans=s=2") == "lut3d=x,format=yuv420p,nlmeans=s=2"


def test_auto_color_end_to_end():
    if not shutil.which("ffmpeg") or importlib.util.find_spec("torch") is None:
        print("  skip: ffmpeg or torch missing")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / "src.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=s=640x360:r=30:d=3,eq=saturation=0.6:brightness=-0.05",
                        "-pix_fmt", "yuv420p", str(src)], check=True)
        edit = d / "edit"
        p = subprocess.run([sys.executable, str(HELPERS / "auto_color.py"), "--edit-dir", str(edit), "--video", str(src)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert p.returncode == 0, p.stderr[-800:]
        cubes = sorted((edit / "grade").glob("ia_src_paired_*.cube"))
        assert [c.stem.rsplit("_", 1)[1] for c in cubes] == ["100", "50", "70"], cubes
        head = cubes[0].read_text(encoding="utf-8")[:400]
        assert "LUT_3D_SIZE" in head
        assert (edit / "verify" / "auto_color_src.png").exists()


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
