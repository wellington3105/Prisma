"""Optional speaker diarization — labels who's speaking, word by word.

Not a port: AutoSubs (tmoroney/auto-subs, MIT) does diarization in a Rust
Tauri sidecar (crates/diarize, with a vendored C++ kaldi-native-fbank under
it) — there is no Python source there to adapt into a Python skill. This
module delivers the same outcome AutoSubs's C1/C2 stories describe (speaker
labels on a transcript, captions that can style per speaker) via
pyannote.audio (MIT), the library actually used for this in Python.

Reads an existing transcript JSON (from transcribe.py), runs diarization on
the source video's audio, and rewrites each word's speaker_id in place —
transcribe.py itself is untouched, so the default path stays 100% offline
with no account anywhere. Diarization is opt-in for two reasons:
  1. It's dead weight for the common case (talking-head solo, one speaker) —
     the skill's own transcripts default every word to "speaker_0" already.
  2. pyannote's pretrained pipeline is gated on HuggingFace: the *code* is
     MIT, but downloading the model weights the first time requires a (free)
     HF account and accepting the model's terms at
     huggingface.co/pyannote/speaker-diarization-3.1. That is exactly the
     kind of "second thing to sign up for" the skill avoids requiring, so it
     only happens if the user explicitly asks for --diarize.

Usage:
    uv run python helpers/diarize.py <video> --edit-dir <edit_dir>
    uv run python helpers/diarize.py <video> --edit-dir <edit_dir> --num-speakers 2
    HF_TOKEN=hf_xxx uv run python helpers/diarize.py <video> --edit-dir <edit_dir>

Requires: uv sync --extra diarize
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
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _extract_wav(video: Path, dest: Path) -> None:
    """16kHz mono WAV — pyannote's expected input format."""
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
          "-c:a", "pcm_s16le", str(dest)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _diarize_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def run_diarization(audio_path: Path, num_speakers: int | None = None,
                    hf_token: str | None = None) -> list[dict]:
    """Returns [{start, end, speaker}, ...] speaker turns, sorted by start.

    speaker labels come back as pyannote's own "SPEAKER_00", "SPEAKER_01", ...
    — remapped to the skill's "speaker_0", "speaker_1", ... by the caller.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError as e:
        raise RuntimeError(
            "pyannote.audio is missing from this environment. It is an opt-in "
            "dependency (heavy: torch + pretrained models), so it needs a separate "
            "install:\n    uv sync --extra diarize"
        ) from e

    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError(
            "pyannote's pretrained pipeline is gated on HuggingFace: create a free "
            "account, accept the terms at "
            "https://huggingface.co/pyannote/speaker-diarization-3.1, then create a "
            "read token at https://huggingface.co/settings/tokens and pass it via "
            "--hf-token or the HF_TOKEN environment variable."
        )

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                        use_auth_token=token)
    pipeline.to(__import__("torch").device(_diarize_device()))

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    diarization = pipeline(str(audio_path), **kwargs)

    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append({"start": float(turn.start), "end": float(turn.end), "speaker": speaker})
    turns.sort(key=lambda t: t["start"])
    return turns


def _speaker_at(turns: list[dict], t: float) -> str | None:
    """The turn covering timestamp t, or the nearest one if t falls in a gap
    (diarization turns rarely tile the timeline perfectly)."""
    best, best_dist = None, float("inf")
    for turn in turns:
        if turn["start"] <= t <= turn["end"]:
            return turn["speaker"]
        dist = min(abs(t - turn["start"]), abs(t - turn["end"]))
        if dist < best_dist:
            best, best_dist = turn["speaker"], dist
    return best


def label_transcript(transcript: dict, turns: list[dict]) -> tuple[dict, int]:
    """Rewrites each word entry's speaker_id from diarization turns.
    Returns (transcript, speaker_count)."""
    seen: dict[str, str] = {}
    words = transcript.get("words", [])
    for w in words:
        if w.get("type") != "word":
            continue
        mid = (float(w["start"]) + float(w["end"])) / 2
        raw_speaker = _speaker_at(turns, mid)
        if raw_speaker is None:
            continue
        if raw_speaker not in seen:
            seen[raw_speaker] = f"speaker_{len(seen)}"
        w["speaker_id"] = seen[raw_speaker]

    # spacing entries inherit the speaker of the word that follows them, so
    # caption-styling code that walks the flat list stays coherent.
    for i, w in enumerate(words):
        if w.get("type") == "spacing":
            nxt = next((x for x in words[i + 1:] if x.get("type") == "word"), None)
            if nxt:
                w["speaker_id"] = nxt["speaker_id"]

    return transcript, len(seen)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Label transcript words with speaker IDs via pyannote.audio (opt-in)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, required=True,
                    help="edit dir containing transcripts/<video_stem>.json (see transcribe.py)")
    ap.add_argument("--num-speakers", type=int, default=None,
                    help="if known, improves accuracy; omit to auto-detect")
    ap.add_argument("--hf-token", type=str, default=None,
                    help="HuggingFace read token; falls back to HF_TOKEN env var")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    transcript_path = args.edit_dir / "transcripts" / f"{video.stem}.json"
    if not transcript_path.exists():
        sys.exit(f"transcript not found: {transcript_path}\n"
                 f"run first: python helpers/transcribe.py '{video}' --edit-dir '{args.edit_dir}'")

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    print(f"  extracting audio from {video.name}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / f"{video.stem}.wav"
        _extract_wav(video, wav)
        print("  running diarization (pyannote.audio) — first run downloads "
              "~150MB of models", flush=True)
        turns = run_diarization(wav, num_speakers=args.num_speakers, hf_token=args.hf_token)

    if not turns:
        sys.exit("diarization returned no speaker turns — nothing to label")

    transcript, speaker_count = label_transcript(transcript, turns)
    transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    print(f"  saved: {transcript_path.name} — {speaker_count} speaker(s), "
          f"{len(turns)} turns")


if __name__ == "__main__":
    main()
