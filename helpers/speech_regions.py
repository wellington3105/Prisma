"""Print true acoustic speech regions of a video using ffmpeg silencedetect.

PHASE 1 cut helper. Whisper word timestamps drift and STRETCH a word's end
across following silence, so they are unreliable for cut points. This runs
silencedetect on the source audio and prints the speech intervals (the
complement of the detected silences) — the acoustic truth to snap cuts to.

Snap each segment's START to a speech onset (a region start) and its END to a
speech offset (a region end), with a tiny lead (~30ms) and a decay-preserving
trail (~60ms) so the last letter/sibilant is never clipped.

Usage:
    python helpers/speech_regions.py <video>
    python helpers/speech_regions.py <video> --noise -33dB --min-silence 0.10  # fixed
    python helpers/speech_regions.py <video> --start 30 --end 40
"""
from __future__ import annotations

# Windows consoles default to cp1252 and raise UnicodeEncodeError on the arrows
# and box characters these helpers print. Force UTF-8 so a status line can never
# kill a run (measured: transcribe.py + preview_server.py, 2026-08-18).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_level import analisar, filtro_de_ganho  # noqa: E402


def detect_silences(video: Path, noise: str, min_silence: float,
                    gain_db: float = 0.0) -> list[tuple[float, float]]:
    pre = filtro_de_ganho(gain_db)
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(video),
        "-af", f"{pre + ',' if pre else ''}silencedetect=noise={noise}:d={min_silence}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", text)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", text)]
    # pair them; a leading silence_start at 0 may have no preceding speech
    pairs: list[tuple[float, float]] = []
    ei = 0
    for s in starts:
        # find the first end greater than s
        while ei < len(ends) and ends[ei] <= s:
            ei += 1
        e = ends[ei] if ei < len(ends) else None
        pairs.append((s, e if e is not None else s))
    return pairs


def resolve_noise(video: Path, noise: str) -> tuple[str, float]:
    """('auto' | '-NNdB') -> (limiar do silencedetect, ganho de analise em dB)."""
    if str(noise).lower() != "auto":
        return noise, 0.0
    a = analisar(video)
    return f"{a['limiar_db']}dB", a["ganho_db"]


def speech_regions(video: Path, noise: str, min_silence: float,
                   min_speech: float = 0.15) -> list[tuple[float, float]]:
    noise, gain = resolve_noise(video, noise)
    # total duration
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(video)],
        capture_output=True, text=True).stdout.strip() or 0.0)

    silences = detect_silences(video, noise, min_silence, gain)
    # Build speech regions = gaps between silences
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start > cursor:
            regions.append((cursor, s_start))
        cursor = max(cursor, s_end)
    if cursor < dur:
        regions.append((cursor, dur))
    # drop tiny blips
    return [(a, b) for a, b in regions if (b - a) >= min_speech]


def main() -> None:
    ap = argparse.ArgumentParser(description="Print acoustic speech regions (silencedetect)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--noise", default="auto",
                    help="silence threshold: 'auto' (default; measured from the speaker level "
                         "and noise floor, see speech_level.py) or explicit like -33dB")
    ap.add_argument("--min-silence", type=float, default=0.10, help="min silence seconds (default 0.10)")
    ap.add_argument("--min-speech", type=float, default=0.15, help="drop speech regions shorter than this")
    ap.add_argument("--start", type=float, default=0.0, help="only show regions overlapping [start,end]")
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"not found: {args.video}")

    noise, gain = resolve_noise(args.video, args.noise)
    regions = speech_regions(args.video, args.noise, args.min_silence, args.min_speech)
    hi = args.end if args.end is not None else 1e9
    print(f"speech regions (noise={noise}{' [auto]' if str(args.noise).lower() == 'auto' else ''}, "
          f"analysis gain={gain:+.1f}dB, min_silence={args.min_silence}s):")
    for a, b in regions:
        if b < args.start or a > hi:
            continue
        print(f"  {a:8.2f} -> {b:8.2f}   ({b - a:5.2f}s)")


if __name__ == "__main__":
    main()
