"""The 12 measured eases (motionmaxxing) on the Python side: names, durations, defaults.

The curves themselves run in the browser: assets/hyperframes/vendor/prisma-eases.js
registers them as named GSAP eases ("softLand", "accelExit", ...), and every Prisma
HyperFrames index.html loads that file. This module lets a helper that WRITES a
composition choose a name and a duration from the measurement instead of guessing
"power3.out, 0.5 s".

Source and evidence: helpers/vendor/motionmaxxing/PROVENANCE.md and
references/motion-craft.md §2.1. Existing layers ported for Remotion parity keep
their curves; use these for new motion.
"""
from __future__ import annotations

from pathlib import Path

JS_FILE = Path(__file__).resolve().parents[2] / "assets" / "hyperframes" / "vendor" / "prisma-eases.js"


def script_inline() -> str:
    """The eases as one inline <script>, for writers that load GSAP from a CDN and
    copy no vendor files (cinema_edit, beat_edit, hf_motion_scenes, export_hyperframes).
    Put it right after the GSAP <script> tag."""
    return "<script>\n" + JS_FILE.read_text(encoding="utf-8") + "\n</script>"

# Measured median duration of each curve, in frames at 30 fps (motion.js EASE_FRAMES).
FRAMES_30 = {
    "crashIn": 10, "popOver": 15, "bounceHard": 22, "snapSettle": 11, "softLand": 12,
    "whip": 7, "glide": 10, "cruise": 9, "softInOut": 9, "gentleIn": 9,
    "accelExit": 13, "crashOut": 17,
}
NAMES = tuple(FRAMES_30)

# What to use when nothing else decides (motion.md R1.1, R1.4, R1.5; §2.1).
ROLE = {
    "enter": "softLand",      # text rises, panels slide, scale-ins
    "hero": "snapSettle",     # hero / CTA entry
    "cta": "snapSettle",
    "move": "glide",          # medium x/y/scale moves, camera push
    "whip": "whip",           # big fast move
    "exit": "accelExit",      # leaving: accelerate, end at peak speed
    "exit_cut": "crashOut",   # leaving into a hard cut
    "fade": "cruise",         # opacity, drift, counters
    "blur": "softInOut",
    "overshoot": "popOver",   # at most one visible spring per film
}


def ease(role: str) -> str:
    """GSAP ease name for a role; KeyError on an unknown role, so a typo is loud."""
    return ROLE[role]


def seconds(name: str, fps: float = 30, frames: int | None = None) -> float:
    """Duration in seconds: the measured median for `name`, or `frames` at `fps`.

    The count is in 30 fps frames because the measurement was made at 30 fps.
    """
    if name not in FRAMES_30:
        raise KeyError(f"unknown ease {name!r}; known: {', '.join(NAMES)}")
    n = FRAMES_30[name] if frames is None else frames
    return round(n / 30.0, 4)


def tween(role: str, frames: int | None = None) -> str:
    """A GSAP vars fragment, for example  'duration:0.4, ease:"softLand"'."""
    name = ease(role)
    return f'duration:{seconds(name, frames=frames)}, ease:"{name}"'
