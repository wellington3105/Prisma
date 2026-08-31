"""Voiceover carve — duck the music ONLY in the bands the voice occupies.

The usual fix for "music competing with speech" is to turn the music down. That
works, and it costs you the music: at the level where it stops fighting the
voice it is also barely there (measured on this project: 0.10, audible only in
the pauses).

Carve does something different. It splits the music into three bands, and
side-chains ONLY the mid band against the voice. Bass and air keep their full
level, so the track still has body and shimmer, while the range the voice lives
in gets out of the way — and only while the voice is actually speaking.

Measured on the 1001 source (pt-BR female, conversational):

    80-250 Hz   -25.8 dB
    250-500 Hz  -22.4 dB   <- voice
    500-1000 Hz -22.1 dB   <- voice (peak)
    1000-2000 Hz -24.2 dB  <- voice
    2000-4000 Hz -29.0 dB
    4000-8000 Hz -35.5 dB

Hence the default carve band of 250-2200 Hz. A male voice sits lower; pass
--band-lo/--band-hi after measuring rather than guessing.

Usage:
    uv run python helpers/music_carve.py --voice cut.mp4 --music trilha.mp3 \
        -o carved.mp3 [--volume 0.22] [--reduction 9] [--band-lo 250] [--band-hi 2200]
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


def measure_bands(path: Path) -> list[tuple[str, float]]:
    """Mean level per octave-ish band — this is how you FIND the carve band."""
    bands = [(80, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000)]
    out = []
    for lo, hi in bands:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path),
             "-af", f"highpass=f={lo},lowpass=f={hi},volumedetect",
             "-vn", "-f", "null", "-"],
            capture_output=True, text=True)
        val = 0.0
        for line in r.stderr.splitlines():
            if "mean_volume" in line:
                try:
                    val = float(line.split("mean_volume:")[1].replace("dB", "").strip())
                except (IndexError, ValueError):
                    pass
        out.append((f"{lo}-{hi}", val))
    return out


def build_filter(volume: float, reduction: float, lo: int, hi: int,
                 attack: int, release: int, music_only: bool = False) -> str:
    """Three-way split; sidechain the mid band against the voice.

    The ratio is derived from the requested reduction in dB rather than exposed
    raw: a user asking for "6 dB quieter under speech" should not have to know
    what a 4:1 ratio does at a -24 dB threshold.
    """
    ratio = max(1.5, min(20.0, 1.0 + reduction / 3.0))
    # `amix` DIVIDES by the number of inputs, so reassembling three bands with it
    # costs each ~9.5 dB and the carve vanishes in the sum (measured: delta of
    # -0.10 dB, i.e. nothing). Bands must be SUMMED, and `amix` with
    # normalize=0 does sum — but only when every input is at full scale, which
    # the split bands are. Keep normalize=0 on both mixes and set the music level
    # AFTER reassembly, so the three-way split is gain-neutral.
    # In music-only mode the voice is a KEY and nothing else — splitting it would
    # leave [vmain] unconsumed and ffmpeg refuses a filtergraph with a dangling
    # output label.
    voice_stage = "[0:a]anull[vkey];" if music_only else "[0:a]asplit=2[vmain][vkey];"
    return (
        voice_stage +
        # split the music into three bands at unity gain
        f"[1:a]asplit=3[mlo][mmid][mhi];"
        # low band: untouched — this is what keeps the track's body
        f"[mlo]lowpass=f={lo}[lo];"
        # high band: untouched — keeps air/shimmer, and the voice is weak here
        f"[mhi]highpass=f={hi}[hi];"
        # mid band: the voice's range. Only this ducks, and only while the voice
        # is actually present. threshold is low because the key is a full-scale
        # voice track; at 0.03 it barely triggers.
        f"[mmid]highpass=f={lo},lowpass=f={hi}[mid];"
        f"[mid][vkey]sidechaincompress="
        f"threshold=0.008:ratio={ratio:.2f}:attack={attack}:release={release}:"
        f"makeup=1:level_sc=0.8[midduck];"
        # reassemble (sum), THEN set the music level, then sum with the voice
        f"[lo][midduck][hi]amix=inputs=3:normalize=0[bands];"
        f"[bands]volume={volume}"
        + ("[out]" if music_only else
           f"[music];[vmain][music]amix=inputs=2:duration=first:normalize=0[out]")
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Carve the music under the voice (band-limited sidechain)")
    ap.add_argument("--voice", type=Path, required=True,
                    help="Voice source (cut.mp4 or a wav) — also the sidechain key")
    ap.add_argument("--music", type=Path, required=True, help="Soundtrack file")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--volume", type=float, default=0.22,
                    help="Music level BEFORE carving. Carve lets this sit higher "
                         "than a flat mix would (default 0.22 vs the usual 0.10)")
    ap.add_argument("--reduction", type=float, default=9.0,
                    help="How many dB the mid band drops under speech (default 9)")
    ap.add_argument("--band-lo", type=int, default=250)
    ap.add_argument("--band-hi", type=int, default=2200)
    ap.add_argument("--attack", type=int, default=15, help="ms — fast enough to catch a word")
    ap.add_argument("--release", type=int, default=220,
                    help="ms — long enough not to pump between words. Tuning it "
                         "does NOT open the music back up inside a short pause: "
                         "breath and room tone keep the key above threshold "
                         "(measured 150/220/300ms → -4.3/-4.2/-4.2 dB, identical). "
                         "That is the compressor behaving, not a bug.")
    ap.add_argument("--measure", action="store_true",
                    help="Print the voice's band energy and exit (find your band)")
    ap.add_argument("--music-only", action="store_true",
                    help="Write the CARVED MUSIC alone, without summing the voice "
                         "back in. This is what the delivery mix needs: the voice "
                         "arrives there from cut.mp4, and summing it twice would "
                         "double the narration.")
    args = ap.parse_args()

    if not args.voice.exists():
        sys.exit(f"voz não encontrada: {args.voice}")

    if args.measure:
        print(f"energia por banda — {args.voice.name}")
        rows = measure_bands(args.voice)
        peak = max(rows, key=lambda r: r[1])
        for name, val in rows:
            mark = "  <- pico" if (name, val) == peak else ""
            print(f"  {name:>10} Hz: {val:7.1f} dB{mark}")
        print("\ncarve deve cobrir as bandas mais fortes (tipicamente 250-2200 Hz)")
        return

    if not args.music.exists():
        sys.exit(f"trilha não encontrada: {args.music}")

    dur = probe_duration(args.voice)
    filt = build_filter(args.volume, args.reduction, args.band_lo, args.band_hi,
                        args.attack, args.release, args.music_only)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(args.voice), "-i", str(args.music),
           "-filter_complex", filt, "-map", "[out]",
           "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd.append(str(args.output))

    print(f"carve: música a {args.volume}, -{args.reduction:.0f} dB em "
          f"{args.band_lo}-{args.band_hi} Hz sob a fala")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        sys.exit("ffmpeg falhou")

    size = args.output.stat().st_size / 1024
    print(f"  saved: {args.output.name} ({size:.0f} KB)")
    print("  OUÇA antes de aceitar — o carve é bom quando você não percebe que existe.")


if __name__ == "__main__":
    main()
