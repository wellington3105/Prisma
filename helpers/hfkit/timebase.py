"""Frames ↔ HyperFrames clip seconds — the rules measured on HyperFrames 0.8.93.

Measured in F0 (2026-11-08, probe in %TEMP%/hfmig/probe, CLA200 cut, 300 frames):
  - HF samples frame k at exactly k/fps: a clip [start, start+dur) shows frames
    ceil(start·fps) … ; an onUpdate proxy reads integer frames (ramp probe).
  - HF's own picture lag is 0: render frame k == base.mp4 frame k (296/298 frames,
    the other two were static frames tied with k-1).
  - Remotion 4.0.482 shows cut.mp4 frame k at output frame k: on CLA200 the
    picture cut lands on the same frame in cut.mp4 and in remotion/out/render.mp4
    at every seam outside a B-roll (179, 204, 349, 542). The templates' VIDEO_LAG
    (+1) therefore no longer describes the picture — it only delays the zoom step,
    the split and the caption windows one frame after the cut, and that IS what the
    Remotion render draws, so the port keeps it (TEMPLATE_LAG). The HF base is
    cut.mp4 UNSHIFTED (plan §1.5 A emulates Remotion; it no longer needs a shift).
    deliver_mix still delays the voice one frame (`lag = 48000/fps`) — unchanged,
    identical for both engines.
  - Root duration is written (N − 0.5)/fps (traps §1: 0.8.93 rounds duration·fps
    UP past a small tolerance); clip edges get a 0.1 ms lead so a 6-decimal value
    never lands on the wrong side of a frame boundary.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PICTURE_LAG = 0          # frames: Remotion 4.0.482 shows cut frame k at output frame k (measured, below)
TEMPLATE_LAG = 1         # frames: the templates' VIDEO_LAG constant — zoom steps, split and caption
                         # windows start one frame AFTER the cut. Reproduced as written (parity).
HF_NATIVE_LAG = 0        # frames: measured, see module docstring
EDGE = 1e-4              # s: lead on clip edges


def r6(x: float) -> float:
    """6 decimals, never 3 (traps §1)."""
    return round(x + 0.0, 6)


def t_at(frame: int, fps: int) -> float:
    """Clip start for a clip whose first visible frame is `frame`."""
    return max(0.0, r6(frame / fps - EDGE)) if frame > 0 else 0.0


def media_t(frame: int, fps: int) -> float:
    """data-media-start for a clip whose first frame shows media frame `frame`.

    HyperFrames picks the media frame by FLOOR of the media time and counts it from
    the clip's first frame: a media-start a hair below k/fps shows frame k-1
    (measured on CLA200: every take one frame late until this). So the lead goes
    the other way here: +0.1 ms."""
    return r6(frame / fps + EDGE) if frame > 0 else 0.0


def span(f0: int, f1: int, fps: int) -> tuple[float, float]:
    """(data-start, data-duration) for frames [f0, f1)."""
    s = t_at(f0, fps)
    e = r6(f1 / fps - EDGE)
    return s, r6(max(e - s, 1e-3))


def root_duration(n_frames: int, fps: int) -> float:
    return r6((n_frames - 0.5) / fps)


def fround(sec: float, fps: int) -> int:
    """Remotion's Math.round(sec * fps) (JS rounds .5 up; Python banker's — not here)."""
    return int(math.floor(sec * fps + 0.5))


def load_segments(pub: Path) -> list[dict]:
    try:
        return (json.loads((pub / "segments.json").read_text(encoding="utf-8")) or {}).get("segments") or []
    except (OSError, json.JSONDecodeError):
        return []


def seam_frames(segs: list[dict], fps: int, n_frames: int) -> list[int]:
    """Output frame where each take's PICTURE starts (Remotion: segment start + VIDEO_LAG).

    The first take starts at 0 (frame 0 holds cut frame 0). A segment that starts
    at or past the end is dropped (check_camadas_vazias warns about those)."""
    out = [0]
    for s in segs[1:]:
        f = fround(float(s["start"]), fps) + TEMPLATE_LAG
        if out[-1] < f < n_frames:
            out.append(f)
    return out
