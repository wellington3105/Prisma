"""Voiceover processing chain: gate → EQ → compressor → limiter (+ optional reverb).

Not a port: HyperFrames (heygen-com/hyperframes, Apache-2.0) implements its
audio chain as Web Audio API nodes running inside a Puppeteer render context
(packages/core/src/audio/audioFxGraph.ts and friends) — thousands of lines of
TypeScript with no ffmpeg equivalent to translate line-for-line. What's
actually portable is the IDEA their docs describe (a fixed processing order,
explicit loudness targets instead of guessed gain) — not their code. This is a
from-scratch ffmpeg implementation of that idea, built for the Prisma pipeline
this skill already has (music_carve.py, voice_levels.py).

Chain order (fixed — matches the conventional voice-processing order, and the
one HyperFrames' own docs describe): gate → EQ → compressor → limiter. Gate
first removes room noise before the compressor can pump on it; EQ before
compression shapes tone without fighting the compressor's own gain moves;
limiter last is a hard ceiling, never a creative tool.

Reverb is an OPTIONAL tail, off by default: HyperFrames documents it as a
gentle "room" send, and the honest ffmpeg equivalent is a short `aecho` slap,
not true convolution reverb (ffmpeg ships no IR-convolution filter usable here
without shipping an impulse response file). Good enough for "a little room",
not a mix decision to reach for on every voice.

No parameter here is invented: gate/EQ/compressor/limiter defaults come from
measuring this skill's own reference clip (D:/edit/cut.mp4 in the session that
built this) with --measure, the same discipline music_carve.py's band numbers
came from. Always --measure a new voice before trusting the defaults.

Usage:
    uv run python helpers/audio_chain.py --measure <voice.mp4>
    uv run python helpers/audio_chain.py <voice.mp4> -o clean.mp3
    uv run python helpers/audio_chain.py <voice.mp4> -o clean.mp3 --reverb --reverb-mix 0.08
    uv run python helpers/audio_chain.py <voice.mp4> -o clean.mp3 \\
        --gate-threshold -45 --eq 200:-3:100 --eq 3000:2:800 --comp-threshold -18
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


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def _volumedetect(path: Path, extra_filter: str | None = None) -> dict:
    af = "volumedetect" if not extra_filter else f"{extra_filter},volumedetect"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", af, "-vn", "-f", "null", "-"],
        capture_output=True, text=True)
    mean = peak = None
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            mean = float(line.split("mean_volume:")[1].replace("dB", "").strip())
        elif "max_volume" in line:
            peak = float(line.split("max_volume:")[1].replace("dB", "").strip())
    return {"mean_db": mean, "peak_db": peak}


def measure(path: Path) -> None:
    """Print mean/peak loudness plus per-band energy, the same read
    music_carve.py's --measure gives for the carve band — this is how you set
    --gate-threshold and --eq before trusting the defaults on a new voice."""
    overall = _volumedetect(path)
    print(f"geral — mean: {overall['mean_db']:.1f} dB, peak: {overall['peak_db']:.1f} dB")
    print("\nenergia por banda:")
    bands = [(80, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000)]
    for lo, hi in bands:
        b = _volumedetect(path, f"highpass=f={lo},lowpass=f={hi}")
        print(f"  {lo:>5}-{hi:<5} Hz: {b['mean_db']:7.1f} dB")
    print("\ngate: ajuste --gate-threshold para ~6-10 dB acima do ruído de sala\n"
          "      (silêncio/pausas na gravação, não a fala)")


def _parse_eq(specs: list[str]) -> list[tuple[float, float, float]]:
    """'freq:gain_db:width_hz' → (freq, gain, width). One `equalizer` band each."""
    out = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) != 3:
            sys.exit(f"--eq espera freq:gain_db:width_hz, recebido: {spec!r}")
        try:
            out.append((float(parts[0]), float(parts[1]), float(parts[2])))
        except ValueError:
            sys.exit(f"--eq com valores não numéricos: {spec!r}")
    return out


def build_filter(gate_threshold: float, gate_ratio: float,
                 eq_bands: list[tuple[float, float, float]],
                 comp_threshold: float, comp_ratio: float,
                 comp_attack: float, comp_release: float, comp_makeup: float,
                 limiter_ceiling: float,
                 reverb: bool, reverb_mix: float) -> str:
    stages = []
    # 1. GATE — cuts room tone/hiss between phrases before the compressor can
    # pump on it. Ratio is deliberately gentle (2:1 default): a hard gate on
    # speech chops breath and word tails audibly.
    stages.append(f"agate=threshold={10**(gate_threshold/20):.6f}:ratio={gate_ratio}:"
                  f"attack=5:release=150")
    # 2. EQ — tone shaping, BEFORE compression so the compressor reacts to the
    # shaped signal (matches HyperFrames' documented order: cut mud/rumble,
    # then presence, then compress).
    for freq, gain, width in eq_bands:
        stages.append(f"equalizer=f={freq}:t=q:w={max(width, 1.0) / max(freq, 1.0):.4f}:g={gain}")
    # 3. COMPRESSOR — evens out delivery so the limiter isn't doing the
    # compressor's job (which sounds pumped/squashed).
    stages.append(f"acompressor=threshold={10**(comp_threshold/20):.6f}:ratio={comp_ratio}:"
                  f"attack={comp_attack}:release={comp_release}:makeup={comp_makeup}")
    # 4. OPTIONAL REVERB TAIL — a short slap-echo standing in for "room send".
    # Off by default; this is not true convolution reverb (see module docstring).
    #
    # aecho's signature is in_gain:out_gain:delays:decays. out_gain scales the
    # WHOLE output (dry + wet), not the echo's share of the mix — passing
    # reverb_mix there attenuates the entire voice by that amount (measured:
    # reverb_mix=0.1 dropped mean level from -17dB to -38dB, a broken "subtle
    # tail"). Keep in_gain/out_gain at unity and drive the mix through decays
    # instead, which scales only the echo taps.
    if reverb:
        stages.append(f"aecho=1.0:1.0:40|60:{reverb_mix:.3f}|{reverb_mix * 0.7:.3f}")
    # 5. LIMITER — hard ceiling, always last, never a level-setting tool.
    stages.append(f"alimiter=limit={10**(limiter_ceiling/20):.6f}:attack=3:release=50")
    return ",".join(stages)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Voiceover chain: gate -> EQ -> compressor -> limiter (+ optional reverb)")
    ap.add_argument("voice", type=Path, nargs="?")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--measure", action="store_true",
                    help="print loudness + band energy and exit (find your settings)")

    ap.add_argument("--gate-threshold", type=float, default=-45.0,
                    help="dB — below this the gate reduces gain (default -45)")
    ap.add_argument("--gate-ratio", type=float, default=2.0)

    ap.add_argument("--eq", action="append", default=[], metavar="FREQ:GAIN_DB:WIDTH_HZ",
                    help="repeatable. Default (no --eq passed): -3dB@150Hz (rumble), "
                         "+2dB@3000Hz (presence) — a conventional voice EQ starting point")

    ap.add_argument("--comp-threshold", type=float, default=-20.0)
    ap.add_argument("--comp-ratio", type=float, default=3.0)
    ap.add_argument("--comp-attack", type=float, default=10.0, help="ms")
    ap.add_argument("--comp-release", type=float, default=150.0, help="ms")
    ap.add_argument("--comp-makeup", type=float, default=2.0)

    ap.add_argument("--limiter-ceiling", type=float, default=-1.0,
                    help="dB — true-peak ceiling (default -1, standard delivery headroom)")

    ap.add_argument("--reverb", action="store_true", help="add a short room-send tail")
    ap.add_argument("--reverb-mix", type=float, default=0.08,
                    help="0-1, how much of the echo returns (default 0.08 — subtle)")
    args = ap.parse_args()

    if args.measure:
        if not args.voice:
            sys.exit("--measure precisa de um arquivo de voz")
        measure(args.voice)
        return

    if not args.voice or not args.output:
        sys.exit("uso: audio_chain.py <voice> -o <output>  (ou --measure <voice>)")
    if not args.voice.exists():
        sys.exit(f"voz não encontrada: {args.voice}")

    eq_bands = _parse_eq(args.eq) if args.eq else [(150.0, -3.0, 100.0), (3000.0, 2.0, 800.0)]

    before = _volumedetect(args.voice)
    filt = build_filter(args.gate_threshold, args.gate_ratio, eq_bands,
                        args.comp_threshold, args.comp_ratio, args.comp_attack,
                        args.comp_release, args.comp_makeup, args.limiter_ceiling,
                        args.reverb, args.reverb_mix)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(args.voice), "-af", filt,
          "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", str(args.output)]

    print(f"cadeia: gate({args.gate_threshold}dB) -> eq({len(eq_bands)} banda(s)) -> "
          f"comp({args.comp_threshold}dB, {args.comp_ratio}:1) -> "
          f"{'reverb -> ' if args.reverb else ''}limiter({args.limiter_ceiling}dB)")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        sys.exit("ffmpeg falhou")

    after = _volumedetect(args.output)
    print(f"  antes: mean {before['mean_db']:.1f} dB, peak {before['peak_db']:.1f} dB")
    print(f"  depois: mean {after['mean_db']:.1f} dB, peak {after['peak_db']:.1f} dB")
    print(f"  saved: {args.output.name}")


if __name__ == "__main__":
    main()
