"""J and L cuts in render.plan_jcut: modes, sync and the default.

    python tests/test_jl_cut.py

edge_quiet (ffmpeg) is replaced by a fixed answer, so this runs without media.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "helpers"))

import render  # noqa: E402

FPS = 30


def _plan(mode=None, quiet=(0.3, 0.3), starts=(1.0, 5.0, 9.0, 13.0)):
    render.edge_quiet = lambda src, a, b: quiet
    edl = {"sources": {"A": "a.mp4"}, "ranges": [{"source": "A", "start": s, "end": s + 3.0} for s in starts]}
    if mode:
        edl["jcut"] = {"mode": mode}
    cfg = render.jcut_settings(edl, FPS)
    return render.plan_jcut(edl, Path("."), cfg)


def _in_sync(p):
    # inside a take, output time and source time move together for picture and sound
    return abs((p["v_off"] - p["a_off"]) - (p["v_in"] - p["a_in"])) < 1e-6


def test_default_is_j_only():
    plan = _plan()
    assert all(p.get("lag_frames", 0) == 0 for p in plan)
    assert [p["lead_frames"] for p in plan][1:] == [5, 5, 5]
    assert all(_in_sync(p) for p in plan)


def test_alternate_mixes_j_and_l():
    plan = _plan("alternate")
    kinds = [p["seam"] for p in plan[1:]]
    assert kinds == ["J", "L", "J"], kinds
    l = plan[2]
    assert l["lead_frames"] == 0 and l["lag_frames"] == 4
    assert abs(l["v_in"] - (l["a_in"] - 4 / FPS)) < 1e-9          # picture enters 4 frames early
    assert abs(plan[1]["v_out"] - (plan[1]["a_out"] - 4 / FPS)) < 1e-9   # outgoing picture leaves early
    assert all(_in_sync(p) for p in plan)


def test_l_only():
    plan = _plan("l")
    assert [p["seam"] for p in plan[1:]] == ["L", "L", "L"]
    assert all(_in_sync(p) for p in plan)


def test_l_needs_source_before_the_range():
    plan = _plan("l", starts=(1.0, 0.05, 9.0))           # take 1 starts 0.05 s into its source
    assert plan[1]["lag_frames"] == 1                     # only 1 frame of source exists before it
    assert all(_in_sync(p) for p in plan)


def test_video_and_audio_lengths_match():
    for mode in (None, "alternate", "l"):
        plan = _plan(mode)
        v = sum(p["v_out"] - p["v_in"] for p in plan)
        last = plan[-1]
        a = last["a_off"] + (last["a_out"] - last["a_in"])
        assert abs(v - a) < 1e-6, (mode, v, a)


if __name__ == "__main__":
    fails = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"PASS {name}")
            except (Exception, SystemExit) as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
