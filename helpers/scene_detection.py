"""Scene (shot-boundary) detection — feeds reframe.py's per-scene camera work.

Adapted from OpenShorts (mutonby/openshorts, MIT — scene_detection.py, root of
the repo, outside cloud/). Ported because reframe.py needs scene boundaries to
avoid camera-snap bursts across a hard cut, and to sample tracking strategy
once per scene instead of once per frame.

Two engines, same contract — both return (scene_list, fps) where scene_list is
a list of (FrameTimecode, FrameTimecode) pairs, exactly PySceneDetect's own
SceneManager.get_scene_list() shape:

  - PySceneDetect ContentDetector (default here): threshold-based, pure
    Python + OpenCV, no model download. Prisma defaults to this because it
    installs in seconds and needs nothing beyond what's already a dependency.
  - TransNetV2 (opt-in, `--engine transnetv2`): a small neural shot-boundary
    detector, markedly better on fast motion, flashes, and gradual transitions
    (fades/dissolves). Needs `transnetv2-pytorch` + `torch` — install with
    `uv sync --extra scenes-neural`. Any failure (missing package, corrupt
    weights, decode error) falls back to PySceneDetect automatically, so a
    detection edge case can never kill a run.

Environment variables (mirroring the OpenShorts original):
  SCENE_ENGINE          "pyscenedetect" (default here) | "transnetv2"
  SCENE_MIN_SEC         minimum scene length in seconds; shorter scenes are
                        merged into a neighbor (default 0.4, TransNetV2 path
                        only — PySceneDetect's own output is left as-is)
  TRANSNETV2_THRESHOLD  shot-boundary probability threshold (default 0.5)
  TRANSNETV2_DEVICE     torch device: "auto" (default) | "cpu" | "cuda" | "mps"

Usage:
    uv run python helpers/scene_detection.py <video_path>
    uv run python helpers/scene_detection.py <video_path> --engine transnetv2
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
import threading

# TransNetV2 input size (width x height), fixed by the trained model.
_TN2_W, _TN2_H = 48, 27

# One shared model instance across calls in the same process.
_TN2_LOCK = threading.Lock()
_tn2_model = None


def detect_scenes(video_path: str):
    """Detect scenes. Returns (scene_list, fps) — see module docstring."""
    engine = os.environ.get("SCENE_ENGINE", "pyscenedetect").strip().lower()
    if engine == "transnetv2":
        try:
            return _detect_transnetv2(video_path)
        except Exception as e:
            print(f"aviso: TransNetV2 falhou ({type(e).__name__}: {e}) "
                  f"— usando PySceneDetect", file=_sys.stderr)
    return _detect_pyscenedetect(video_path)


# --- default engine: PySceneDetect ------------------------------------------

def _detect_pyscenedetect(video_path: str):
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector())
    scene_manager.detect_scenes(video=video)
    scene_list = scene_manager.get_scene_list()
    fps = video.frame_rate
    return scene_list, fps


# --- optional engine: TransNetV2 --------------------------------------------

def _get_tn2_model():
    global _tn2_model
    if _tn2_model is None:
        from transnetv2_pytorch import TransNetV2
        device = os.environ.get("TRANSNETV2_DEVICE", "auto")
        model = TransNetV2(device=device)
        model.eval()
        _tn2_model = model
    return _tn2_model


def _extract_frames_small(video_path: str):
    """Decode the whole clip as 48x27 RGB frames via ffmpeg (~4KB/frame)."""
    import numpy as np

    cmd = [
        "ffmpeg", "-nostdin", "-i", video_path,
        "-vf", f"scale={_TN2_W}:{_TN2_H}",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True, timeout=900)
    frame_bytes = _TN2_H * _TN2_W * 3
    n = len(proc.stdout) // frame_bytes
    if n == 0:
        raise RuntimeError("ffmpeg produziu zero frames")
    return np.frombuffer(proc.stdout[:n * frame_bytes],
                         dtype=np.uint8).reshape(n, _TN2_H, _TN2_W, 3)


def _detect_transnetv2(video_path: str):
    import cv2
    import numpy as np
    import torch
    from scenedetect import FrameTimecode

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    frames = _extract_frames_small(video_path)
    model = _get_tn2_model()
    threshold = float(os.environ.get("TRANSNETV2_THRESHOLD", "0.5"))

    with _TN2_LOCK, torch.no_grad():
        tensor = torch.from_numpy(np.ascontiguousarray(frames)).to(model.device)
        single_frame_pred, _ = model.predict_frames(tensor, quiet=True)

    # predictions_to_scenes returns [[start, end], ...] with INCLUSIVE ends;
    # downstream expects PySceneDetect's exclusive ends.
    raw = model.predictions_to_scenes(single_frame_pred.numpy(), threshold=threshold)
    bounds = [(int(s), int(e) + 1) for s, e in raw]

    # cv2's frame count can differ by a few frames from what ffmpeg decodes;
    # downstream loops run to the decoder's count, so cover the gap.
    if total_frames > bounds[-1][1]:
        bounds[-1] = (bounds[-1][0], total_frames)

    min_sec = float(os.environ.get("SCENE_MIN_SEC", "0.4"))
    bounds = _merge_short_scenes(bounds, fps, min_sec)

    scene_list = [(FrameTimecode(s, fps), FrameTimecode(e, fps))
                  for s, e in bounds]
    print(f"motor de cena: TransNetV2 — {len(scene_list)} cenas", file=_sys.stderr)
    return scene_list, fps


def _merge_short_scenes(bounds, fps, min_sec):
    """Absorb scenes shorter than min_sec into a neighbor. Ultra-short scenes
    cause camera-snap bursts and starve the per-scene strategy sampling."""
    if len(bounds) <= 1 or min_sec <= 0:
        return bounds
    min_frames = max(1, int(round(min_sec * float(fps))))

    merged = []
    for s, e in bounds:
        if merged and (e - s) < min_frames:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    # The first scene can still be short — fold it into the one after it.
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_frames:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect shot boundaries in a video")
    ap.add_argument("video")
    ap.add_argument("--engine", choices=["pyscenedetect", "transnetv2"], default=None,
                    help="overrides SCENE_ENGINE env var")
    args = ap.parse_args()

    if args.engine:
        os.environ["SCENE_ENGINE"] = args.engine

    scene_list, fps = detect_scenes(args.video)
    scenes = [{"start_s": round(s.get_seconds(), 3), "end_s": round(e.get_seconds(), 3)}
              for s, e in scene_list]
    print(json.dumps({"fps": round(float(fps), 3), "count": len(scenes), "scenes": scenes},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
