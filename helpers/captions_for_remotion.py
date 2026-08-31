"""Emit a @remotion/captions Caption[] JSON for the Remotion (Phase 2) project.

Two modes:
  --transcript <cut.json>   PREFERRED. Transcribe the FINAL cut.mp4 first
      (`transcribe.py cut.mp4`), then feed that transcript here. Its word times
      are already on the output timeline and free of the source's stretch/dead
      -air artifacts, so the first word of every segment (e.g. the hook) is
      captioned with correct timing. This is the robust default.
  <edl.json>                Fallback: map per-source word times through the EDL
      offsets. Subject to Whisper stretch at segment edges.

Each spoken word becomes one Caption (word-level) so the word-highlight /
karaoke component can drive per-word timing.

Caption shape (from @remotion/captions): { text, startMs, endMs, timestampMs, confidence }

Usage:
    python helpers/captions_for_remotion.py --transcript <edit>/transcripts/cut.json -o captions.json
    python helpers/captions_for_remotion.py <edl.json> -o captions.json
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
from pathlib import Path


def captions_from_transcript(transcript_path: Path) -> list[dict]:
    """Words already on the output timeline (transcript of the final cut)."""
    words = [w for w in json.loads(transcript_path.read_text(encoding="utf-8")).get("words", [])
             if w.get("type") == "word" and w.get("start") is not None]
    # Per-speaker styling only makes sense with 2+ distinct voices — a solo
    # talking-head transcript is 100% "speaker_0" and speakerId would just be
    # dead weight on every caption. See diarize.py for how speaker_id gets set.
    multi_speaker = len({w.get("speaker_id") for w in words if w.get("speaker_id")}) > 1
    caps: list[dict] = []
    for w in words:
        t = float(w["start"])
        e = float(w.get("end") or w["start"])
        if e <= t:
            e = t + 0.12
        text = (w.get("text") or "").strip()
        if not text:
            continue
        cap = {
            "text": text,
            "startMs": round(t * 1000),
            "endMs": round(e * 1000),
            "timestampMs": round((t + e) / 2 * 1000),
            "confidence": None,
        }
        if multi_speaker:
            cap["speakerId"] = w.get("speaker_id") or "speaker_0"
        caps.append(cap)
    caps.sort(key=lambda c: c["startMs"])
    return caps


def build_captions(edl: dict, edit_dir: Path) -> list[dict]:
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]
    caps: list[dict] = []
    off = 0.0  # output-timeline offset (seconds)

    # Two passes: first check whether ANY source transcript has 2+ speakers,
    # so speakerId is either present on every caption or absent from all of
    # them — never a mix that would make the Remotion side special-case it.
    multi_speaker = False
    for r in edl["ranges"]:
        tr_path = transcripts_dir / f"{r['source']}.json"
        if not tr_path.exists():
            continue
        ws = json.loads(tr_path.read_text(encoding="utf-8")).get("words", [])
        if len({w.get("speaker_id") for w in ws if w.get("speaker_id")}) > 1:
            multi_speaker = True
            break

    for r in edl["ranges"]:
        src = r["source"]
        a, b = float(r["start"]), float(r["end"])
        dur = b - a
        tr_path = transcripts_dir / f"{src}.json"
        if not tr_path.exists():
            off += dur
            continue
        words = [w for w in json.loads(tr_path.read_text(encoding="utf-8")).get("words", [])
                 if w.get("type") == "word" and w.get("start") is not None]
        seg = [w for w in words if (a - 0.08) <= w["start"] < b]
        seg.sort(key=lambda w: w["start"])
        for w in seg:
            t = max(0.0, w["start"] - a) + off
            e = min(dur, max(0.0, (w.get("end") or w["start"]) - a)) + off
            if e <= t:
                e = t + 0.12
            text = (w.get("text") or "").strip()
            if not text:
                continue
            cap = {
                "text": text,
                "startMs": round(t * 1000),
                "endMs": round(e * 1000),
                "timestampMs": round((t + e) / 2 * 1000),
                "confidence": None,
            }
            if multi_speaker:
                cap["speakerId"] = w.get("speaker_id") or "speaker_0"
            caps.append(cap)
        off += dur

    caps.sort(key=lambda c: c["startMs"])
    return caps


def main() -> None:
    ap = argparse.ArgumentParser(description="→ @remotion/captions Caption[] JSON")
    ap.add_argument("edl", type=Path, nargs="?", help="edl.json (fallback mode)")
    ap.add_argument("--transcript", type=Path, default=None,
                    help="Transcript of the final cut.mp4 (preferred mode)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output captions.json path")
    args = ap.parse_args()

    if args.transcript:
        caps = captions_from_transcript(args.transcript.resolve())
    elif args.edl:
        edl_path = args.edl.resolve()
        caps = build_captions(json.loads(edl_path.read_text(encoding="utf-8")), edl_path.parent)
    else:
        ap.error("provide --transcript <cut.json> or an edl.json")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(caps, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.output} — {len(caps)} word captions")


if __name__ == "__main__":
    main()
