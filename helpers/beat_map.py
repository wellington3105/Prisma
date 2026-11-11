"""Music map for beat-synced edits: tempo, beats, downbeats, hits and drops.

The cut grid of a music-driven montage. Every time is snapped to the video
frame grid (--fps) so a cut placed "on the beat" lands on a real frame.

Output JSON (one file, read by speed_ramp.py / beat_edit.py, never by eye):
  tempo        BPM (librosa beat tracker, tightened)
  beats[]      every beat, seconds, frame-snapped
  downbeats[]  beat 1 of each bar (4/4 assumed; phase picked by low-end energy)
  bars[]       {start, end} per bar
  hits[]       {t, strength}: strongest transients (snare/kick/impact), 0..1
  sections[]   {start, end, energy}: energy plateaus; `drop` marks a jump
  drops[]      times where the energy jumps (the "drop" / chorus entry)
  cut_points[] ranked suggestions: drops > downbeats on hits > downbeats > hits

Plus a PNG strip (waveform + beat/downbeat/hit/drop marks) for a one-Read check.

Usage:
  python helpers/beat_map.py music.mp3 -o edit/beats.json [--fps 30] [--start 6 --duration 23]
  python helpers/beat_map.py music.mp3 -o beats.json --meter 3      # waltz / 3-4
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import json
from pathlib import Path

import cv2
import librosa
import numpy as np


def snap(t: float, fps: float) -> float:
    return round(round(t * fps) / fps, 4)


def analyse(path: Path, fps: float, start: float, duration: float | None, meter: int) -> dict:
    y, sr = librosa.load(str(path), sr=22050, mono=True, offset=start, duration=duration)
    hop = 512
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, aggregate=np.median)
    tempo, beat_fr = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop, tightness=120)
    det = librosa.frames_to_time(beat_fr, sr=sr, hop_length=hop)
    # The tracker only locks once the drums enter (a pad intro gets no beats).
    # Music for edits is steady-tempo: fit t = t0 + k·p to the detected beats and
    # extend that grid over the whole file; a grid beat within 70 ms of a
    # detected one takes the detected time.
    dur_s = len(y) / sr
    if len(det) >= 4:
        p = float(np.median(np.diff(det)))
        k = np.round((det - det[0]) / p)
        p, t0 = np.polyfit(k, det, 1)
        ks = np.arange(int(np.floor(-t0 / p)), int(np.ceil((dur_s - t0) / p)) + 1)
        grid = t0 + ks * p
        grid = grid[(grid >= 0) & (grid < dur_s)]
        beats = np.array([det[np.argmin(np.abs(det - g))] if np.min(np.abs(det - g)) < 0.07 else g for g in grid])
        detected = [bool(np.min(np.abs(det - g)) < 0.07) for g in grid]
        tempo = 60.0 / p
    else:
        beats, detected, tempo = det, [True] * len(det), float(np.atleast_1d(tempo)[0])
    beat_fr = librosa.time_to_frames(beats, sr=sr, hop_length=hop)

    # Downbeat phase: the bar's "1" carries the kick — pick the phase whose beats
    # hold the most low-frequency onset energy.
    S = np.abs(librosa.stft(y, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr)
    low = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S[freqs < 150]), sr=sr, hop_length=hop)
    phase_score = [low[beat_fr[k::meter]].sum() if len(beat_fr[k::meter]) else 0 for k in range(meter)]
    phase = int(np.argmax(phase_score))
    downbeats = beats[phase::meter]

    # Hits: transient peaks, normalised 0..1, kept if in the top 30%.
    pk = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.25, wait=4)
    strength = env[pk] / (env.max() + 1e-9)
    keep = strength >= np.quantile(strength, 0.70) if len(strength) else []
    hits = [{"t": snap(float(t), fps), "strength": round(float(s), 3)}
            for t, s in zip(librosa.frames_to_time(pk[keep], sr=sr, hop_length=hop), strength[keep])]

    # Energy per bar → sections and drops (a bar ≥ +4 dB over the previous two).
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rt = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    bar_edges = list(downbeats) + [len(y) / sr]
    bars, bar_db = [], []
    for a, b in zip(bar_edges, bar_edges[1:]):
        m = (rt >= a) & (rt < b)
        db = float(20 * np.log10(rms[m].mean() + 1e-9)) if m.any() else -80.0
        bars.append({"start": snap(a, fps), "end": snap(b, fps), "db": round(db, 1)})
        bar_db.append(db)
    # Drop: the next two bars sit ≥3.5 dB over the previous four (measured on the
    # Treblo test track: +4.5 dB at the chorus entry, while single-bar jumps of
    # +3 dB happen inside verses). Keep the strongest within any 4-bar window.
    cand = []
    for i in range(2, len(bars) - 1):
        jump = float(np.mean(bar_db[i:i + 2]) - np.mean(bar_db[max(0, i - 4):i]))
        if jump >= 3.5 and bar_db[i] > bar_db[i - 1]:
            cand.append((jump, i))
    drops, taken = [], []
    for jump, i in sorted(cand, reverse=True):
        if all(abs(i - j) >= 4 for j in taken):
            taken.append(i)
    drops = sorted(bars[i]["start"] for i in taken)
    sections, cur = [], {"start": bars[0]["start"] if bars else 0.0, "dbs": []}
    for i, bar in enumerate(bars):
        if bar["start"] in drops and cur["dbs"]:
            sections.append({"start": cur["start"], "end": bar["start"], "db": round(float(np.mean(cur["dbs"])), 1)})
            cur = {"start": bar["start"], "dbs": []}
        cur["dbs"].append(bar_db[i])
    if bars:
        sections.append({"start": cur["start"], "end": bars[-1]["end"], "db": round(float(np.mean(cur["dbs"])), 1)})

    hit_t = np.array([h["t"] for h in hits]) if hits else np.array([])
    def near_hit(t, tol=0.07):
        return bool(len(hit_t)) and float(np.min(np.abs(hit_t - t))) <= tol
    cps = [{"t": d, "why": "drop", "rank": 1} for d in drops]
    cps += [{"t": snap(d, fps), "why": "downbeat+hit", "rank": 2} for d in downbeats if near_hit(d) and snap(d, fps) not in drops]
    cps += [{"t": snap(d, fps), "why": "downbeat", "rank": 3} for d in downbeats if not near_hit(d)]
    cps += [{"t": h["t"], "why": "hit", "rank": 4} for h in hits if h["strength"] >= 0.6]
    seen, cut_points = set(), []
    for c in sorted(cps, key=lambda c: (c["rank"], c["t"])):
        if c["t"] not in seen:
            seen.add(c["t"]); cut_points.append(c)
    cut_points.sort(key=lambda c: c["t"])

    return {
        "source": str(path), "offset": start, "duration": round(len(y) / sr, 3), "fps": fps,
        "tempo": round(tempo, 2), "beat_period": round(60.0 / tempo, 4) if tempo else None,
        "meter": meter, "downbeat_phase": phase,
        "beats": [snap(t, fps) for t in beats],
        "beats_detected": detected,
        "downbeats": [snap(t, fps) for t in downbeats],
        "bars": bars, "hits": hits, "sections": sections, "drops": drops, "cut_points": cut_points,
        "_wave": (y, sr),
    }


def draw(m: dict, out: Path) -> None:
    y, sr = m["_wave"]
    W, H = 1800, 260
    img = np.full((H, W, 3), 18, np.uint8)
    n = len(y); px = np.linspace(0, n, W + 1).astype(int)
    for x in range(W):
        seg = np.abs(y[px[x]:px[x + 1]])
        a = int((seg.max() if len(seg) else 0) * (H * 0.42))
        cv2.line(img, (x, H // 2 - a), (x, H // 2 + a), (90, 90, 90), 1)
    X = lambda t: int(t / m["duration"] * W)
    for s in m["sections"]:
        cv2.rectangle(img, (X(s["start"]), H - 14), (X(s["end"]), H - 4), (60, 60, 160), -1)
    for t in m["beats"]:
        cv2.line(img, (X(t), 0), (X(t), 30), (120, 120, 120), 1)
    for t in m["downbeats"]:
        cv2.line(img, (X(t), 0), (X(t), H), (200, 200, 200), 1)
    for h in m["hits"]:
        cv2.circle(img, (X(h["t"]), 40), 2 + int(h["strength"] * 5), (60, 200, 255), -1)
    for d in m["drops"]:
        cv2.line(img, (X(d), 0), (X(d), H), (60, 60, 255), 3)
    cv2.putText(img, f'{m["tempo"]} BPM  {len(m["beats"])} beats  {len(m["drops"])} drops',
                (10, H - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1)
    cv2.imwrite(str(out), img)


def main() -> None:
    ap = argparse.ArgumentParser(description="Music map: tempo, beats, downbeats, hits, drops, cut points")
    ap.add_argument("audio", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--start", type=float, default=0.0, help="analyse from this point of the file (s)")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--meter", type=int, default=4, help="beats per bar (4 = 4/4)")
    a = ap.parse_args()
    m = analyse(a.audio, a.fps, a.start, a.duration, a.meter)
    draw(m, a.output.with_suffix(".png"))
    m.pop("_wave")
    a.output.write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"{m['tempo']} BPM · beat {m['beat_period']}s · {len(m['beats'])} beats · {len(m['downbeats'])} bars · "
          f"{len(m['hits'])} hits · drops {m['drops']}")
    print(f"wrote {a.output} + {a.output.with_suffix('.png').name}")


if __name__ == "__main__":
    main()
