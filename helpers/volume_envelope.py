"""Apply a time-varying volume curve to an audio track — not a single fixed level.

Not a port: HyperFrames's automation envelopes
(packages/engine/src/services/audioVolumeEnvelope.ts) run inside its Web Audio
API render graph — again TypeScript with no ffmpeg equivalent, same situation
as audio_chain.py. What's worth taking is the IDEA: today the Prisma preview's
soundtrack fader (assets/preview/app.js, `S.musicVol` / `editData.soundtrack.
volume`) saves exactly ONE number for the whole track. A track that should
duck for the intro, hold during a quiet passage, and swell for the outro has
no way to say that — this fills that gap for any audio track (soundtrack,
processed voice, sfx bed), independent of the preview's single-fader UI.

Keyframes are (time_s, level) pairs, level on the same 0-1 scale the preview
fader already uses (so a flat envelope with one keyframe reproduces today's
fixed-volume behavior exactly). Between keyframes the level is linearly
interpolated; ffmpeg's `volume` filter evaluates the interpolation once per
frame via `eval=frame`, so the curve is continuous, not a staircase of
`afade`/`enable=between()` segments.

Usage:
    uv run python helpers/volume_envelope.py trilha.mp3 -o trilha_env.mp3 \\
        --keyframe 0:0.05 --keyframe 5:0.22 --keyframe 140:0.22 --keyframe 153:0.35
    uv run python helpers/volume_envelope.py trilha.mp3 -o trilha_env.mp3 \\
        --keyframes-json envelope.json   # [[0,0.05],[5,0.22],...]
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
import json
import subprocess
import sys
from pathlib import Path


def parse_keyframe(spec: str) -> tuple[float, float]:
    if ":" not in spec:
        sys.exit(f"--keyframe espera tempo:nivel, recebido: {spec!r}")
    t, v = spec.split(":", 1)
    try:
        return float(t), float(v)
    except ValueError:
        sys.exit(f"--keyframe com valores não numéricos: {spec!r}")


def build_expr(keyframes: list[tuple[float, float]]) -> str:
    """Piecewise-linear interpolation as a single ffmpeg `volume` expression,
    evaluated once per frame (eval=frame). Nested if()s, innermost segment
    first — ffmpeg's expression evaluator has no loops, so the curve has to be
    unrolled into one expression covering every segment.

    Before the first keyframe: hold its level (no fade-up from silence the
    user never asked for). After the last: hold its level (no fade to zero).
    """
    kf = sorted(keyframes, key=lambda k: k[0])
    if len(kf) == 1:
        return f"{kf[0][1]}"

    expr = f"{kf[-1][1]}"  # after the last keyframe: hold
    for i in range(len(kf) - 1, 0, -1):
        t0, v0 = kf[i - 1]
        t1, v1 = kf[i]
        if t1 <= t0:
            sys.exit(f"keyframes precisam de tempos estritamente crescentes: "
                     f"{t0} >= {t1}")
        # linear interpolation between (t0,v0) and (t1,v1)
        seg = f"({v0}+({v1}-{v0})*(t-{t0})/{t1 - t0})"
        expr = f"if(lt(t,{t1}),{seg},{expr})"
    expr = f"if(lt(t,{kf[0][0]}),{kf[0][1]},{expr})"
    return expr


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Apply a piecewise-linear volume envelope to an audio track")
    ap.add_argument("audio", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--keyframe", action="append", default=[], metavar="TIME_S:LEVEL",
                    help="repeatable, e.g. --keyframe 0:0.05 --keyframe 5:0.22")
    ap.add_argument("--keyframes-json", type=Path, default=None,
                    help="path to a JSON file: [[time_s, level], ...] — "
                         "alternative to repeating --keyframe")
    args = ap.parse_args()

    if not args.audio.exists():
        sys.exit(f"áudio não encontrado: {args.audio}")

    if args.keyframes_json:
        raw = json.loads(args.keyframes_json.read_text(encoding="utf-8"))
        keyframes = [(float(t), float(v)) for t, v in raw]
    elif args.keyframe:
        keyframes = [parse_keyframe(k) for k in args.keyframe]
    else:
        sys.exit("forneça --keyframe (repetível) ou --keyframes-json")

    expr = build_expr(keyframes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(args.audio),
          "-af", f"volume=eval=frame:volume='{expr}'",
          "-c:a", "libmp3lame", "-b:a", "192k", str(args.output)]

    kf_desc = ", ".join(f"{t:g}s→{v:g}" for t, v in sorted(keyframes))
    print(f"envelope: {kf_desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        sys.exit("ffmpeg falhou")

    print(f"  saved: {args.output.name}")


if __name__ == "__main__":
    main()
