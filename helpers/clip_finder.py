"""Find candidate short-form clips inside a long transcript — the decupagem step.

Adapted from OpenShorts (mutonby/openshorts, MIT — clip_selection.py, root of
the repo, outside cloud/). Ported because the Prisma workflow has always been
"one video, one edit" — this is the piece that turns one long source into a
shortlist of clip windows a user (or an LLM) can pick from, one long recording
in, N candidate Reels out.

What changed from the original:
  - The original is a set of pure helpers meant to be imported by a Gemini-
    backed pipeline (main.py / gemini_worker.py) that does the actual "which
    window is the best moment" judgment call with an LLM. Prisma has no
    required API key anywhere in Phase 1 — that stays true here. This module
    ports the LLM-FREE half only: transcript windowing, clip count/duration
    heuristics, and word-boundary snapping. It does NOT call Gemini and does
    NOT rank windows by "virality" — it produces evenly-spaced candidate
    windows sized to the clip-length band, snapped to real word boundaries,
    and leaves the picking to the user (or to a caller that wants to bolt an
    LLM ranking step on top later — see `--json` output).
  - `MODEL_PRICES` / `lookup_model_prices` (Gemini cost estimation) dropped —
    nothing here calls a model, so there is no cost to estimate.
  - Adapted to Prisma's own transcript schema (`<edit>/transcripts/<stem>.json`,
    a dict with a "words" list of {text, start, end, type, speaker_id} entries
    where type is "word"|"spacing" — see transcribe.py) instead of OpenShorts's
    {"segments": [...]} / {"w","s","e"} shapes. `_load_prisma_transcript`
    below does that conversion; `build_transcript_windows` and
    `snap_clip_to_words` are otherwise unchanged logic from the original.

Usage:
    uv run python helpers/clip_finder.py --edit-dir <edit_dir> <video_path>
    uv run python helpers/clip_finder.py --edit-dir <edit_dir> <video_path> \\
        --min-seconds 20 --max-seconds 45
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
from pathlib import Path


# --- ported pure helpers (clip_selection.py, unchanged logic) --------------

def clip_count_targets(n_windows):
    """How many clips to ask for, given the shortlist size.

    Measured on OpenShorts prod 3-ago-2026: 95% of jobs delivered 3 clips or
    fewer, the mode being ONE. This puts a floor and a realistic ceiling
    instead of leaving the count unbounded.

    ``CLIP_TARGET_MIN`` / ``CLIP_TARGET_MAX`` env vars override both.
    """
    n = max(1, int(n_windows or 1))
    low = max(2, min(6, n // 2 + 2))
    high = min(12, max(4, n * 2))
    low = min(low, high)

    def _override(name, current):
        raw = os.environ.get(name)
        if not raw:
            return current
        try:
            return max(1, int(raw))
        except ValueError:
            return current

    low = _override("CLIP_TARGET_MIN", low)
    high = _override("CLIP_TARGET_MAX", high)
    return low, max(low, high)


def clip_duration_bounds(min_seconds=None, max_seconds=None):
    """The clip length band (seconds). Explicit args win; env vars next;
    15-60s default otherwise. Clamped to platform-sane limits."""
    lo = min_seconds if min_seconds is not None else \
        float(os.environ.get("CLIP_MIN_SECONDS", 15.0))
    hi = max_seconds if max_seconds is not None else \
        float(os.environ.get("CLIP_MAX_SECONDS", 60.0))
    lo = min(max(lo, 5.0), 175.0)
    hi = min(max(hi, 10.0), 180.0)
    if hi < lo + 5.0:
        hi = min(180.0, lo + 5.0)
    return round(lo, 3), round(hi, 3)


def build_transcript_windows(transcript_result, video_duration,
                             window_seconds=90, overlap_seconds=30):
    """Build scoring windows aligned to segment boundaries, so a sentence is
    never cut in half mid-window."""
    segments = []
    for segment in transcript_result.get("segments", []):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        segments.append((float(segment.get("start", 0)), float(segment.get("end", 0)), text))

    windows = []
    window_index = 1
    i = 0
    n = len(segments)
    while i < n:
        w_start = segments[i][0]
        j = i
        while j + 1 < n and segments[j + 1][1] - w_start <= window_seconds * 1.25:
            j += 1
            if segments[j][1] - w_start >= window_seconds:
                break
        w_end = segments[j][1]
        windows.append({
            "id": f"window_{window_index:03d}",
            "start": round(w_start, 3),
            "end": round(w_end, 3),
            "text": " ".join(seg[2] for seg in segments[i:j + 1]),
        })
        window_index += 1

        if j >= n - 1:
            break
        target = w_end - overlap_seconds
        k = i + 1
        while k <= j and segments[k][0] < target:
            k += 1
        i = max(k, i + 1)

    if not windows:
        windows.append({
            "id": "window_001",
            "start": 0.0,
            "end": round(float(video_duration), 3),
            "text": str(transcript_result.get("text", "") or ""),
        })
    return windows


def snap_clip_to_words(start, end, words, video_duration,
                       min_duration=15.0, max_duration=60.0,
                       search_window=1.5, max_lead=0.35, max_tail=0.45):
    """Snap proposed clip boundaries onto real word boundaries plus a bit of
    the surrounding silence, so cuts land in pauses instead of mid-word.

    words: [{'w','s','e'}, ...] for the whole video, sorted by start.
    """
    original = (round(float(start), 3), round(float(end), 3))
    if not words:
        return original

    starts = [float(w.get("s", 0)) for w in words]
    ends = [float(w.get("e", 0)) for w in words]

    new_start = float(start)
    candidates = [s for s in starts if abs(s - new_start) <= search_window]
    if candidates:
        word_start = min(candidates, key=lambda s: abs(s - new_start))
        prev_ends = [e for e in ends if e <= word_start]
        if prev_ends:
            gap = max(0.0, word_start - max(prev_ends))
            lead = min(max_lead, gap / 2)
        else:
            lead = max_lead
        new_start = max(0.0, word_start - lead)

    new_end = float(end)
    candidates = [e for e in ends if abs(e - new_end) <= search_window]
    if candidates:
        word_end = min(candidates, key=lambda e: abs(e - new_end))
        next_starts = [s for s in starts if s >= word_end]
        if next_starts:
            gap = max(0.0, min(next_starts) - word_end)
            tail = min(max_tail, gap / 2)
        else:
            tail = max_tail
        new_end = min(float(video_duration), word_end + tail)

    if new_end - new_start < min_duration:
        target = new_start + min_duration
        later = sorted(e for e in ends if e >= target)
        if later and later[0] - new_start <= max_duration:
            new_end = min(float(video_duration), later[0] + 0.2)
        else:
            return original
    if new_end - new_start > max_duration:
        target = new_start + max_duration
        earlier = [e for e in ends if new_start < e <= target]
        new_end = (max(earlier) + 0.2) if earlier else target
        new_end = min(new_end, new_start + max_duration, float(video_duration))

    if new_end <= new_start or new_end - new_start < min_duration:
        return original
    return (round(new_start, 3), round(new_end, 3))


# --- Prisma-specific glue ----------------------------------------------------

def _load_prisma_transcript(path: Path) -> tuple[dict, list[dict]]:
    """Read a Prisma transcript JSON ({"words": [word/spacing entries]}) and reshape
    it into what the ported helpers above expect:
      - transcript_result: {"segments": [{"start","end","text"}, ...]}
        (segments = phrase-level groups, split on >=0.6s silence gaps —
        the same idea pack_transcripts.py uses, just not markdown)
      - words: [{"w","s","e"}, ...] flat word list, for snap_clip_to_words
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw["words"] if isinstance(raw, dict) else raw
    words = [{"w": e["text"], "s": float(e["start"]), "e": float(e["end"])}
             for e in entries if e.get("type") == "word"]

    segments = []
    cur_words: list[dict] = []
    cur_start = None
    prev_end = None
    GAP = 0.6
    for e in entries:
        if e.get("type") != "word":
            continue
        s, en = float(e["start"]), float(e["end"])
        if prev_end is not None and s - prev_end >= GAP and cur_words:
            segments.append({"start": cur_start, "end": prev_end,
                             "text": " ".join(w["w"] for w in cur_words)})
            cur_words = []
        if not cur_words:
            cur_start = s
        cur_words.append({"w": e["text"], "s": s, "e": en})
        prev_end = en
    if cur_words:
        segments.append({"start": cur_start, "end": prev_end,
                         "text": " ".join(w["w"] for w in cur_words)})

    return {"segments": segments}, words


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def find_clips(video_path: Path, transcript_path: Path,
               min_seconds: float | None = None, max_seconds: float | None = None,
               window_seconds: float = 90, overlap_seconds: float = 30) -> list[dict]:
    """Produce a candidate clip shortlist: one clip window per transcript
    window, duration-bounded and word-snapped. No ranking/scoring — that
    judgment call is left to the caller (a human, or an LLM step bolted on
    top of this JSON later)."""
    duration = _probe_duration(video_path)
    transcript_result, words = _load_prisma_transcript(transcript_path)
    lo, hi = clip_duration_bounds(min_seconds, max_seconds)

    windows = build_transcript_windows(transcript_result, duration,
                                       window_seconds=window_seconds,
                                       overlap_seconds=overlap_seconds)
    low_n, high_n = clip_count_targets(len(windows))
    chosen = windows[:high_n] if len(windows) > high_n else windows

    clips = []
    for w in chosen:
        start, end = w["start"], w["end"]
        if end - start > hi:
            end = start + hi
        start, end = snap_clip_to_words(start, end, words, duration,
                                        min_duration=lo, max_duration=hi)
        if end - start < lo:
            continue
        clips.append({
            "id": w["id"],
            "start_s": start,
            "end_s": end,
            "duration_s": round(end - start, 3),
            "text": w["text"],
        })
    return clips


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Find candidate short-form clip windows in a transcribed video")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, required=True,
                    help="edit dir containing transcripts/<video_stem>.json (see transcribe.py)")
    ap.add_argument("--min-seconds", type=float, default=None)
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--window-seconds", type=float, default=90)
    ap.add_argument("--overlap-seconds", type=float, default=30)
    args = ap.parse_args()

    transcript_path = args.edit_dir / "transcripts" / f"{args.video.stem}.json"
    if not transcript_path.exists():
        sys_exit = (f"transcrição não encontrada: {transcript_path}\n"
                    f"rode primeiro: python helpers/transcribe.py '{args.video}' "
                    f"--edit-dir '{args.edit_dir}'")
        raise SystemExit(sys_exit)

    clips = find_clips(args.video, transcript_path,
                       min_seconds=args.min_seconds, max_seconds=args.max_seconds,
                       window_seconds=args.window_seconds,
                       overlap_seconds=args.overlap_seconds)
    print(json.dumps({"video": str(args.video), "count": len(clips), "clips": clips},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
