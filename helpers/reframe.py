"""Auto-reframe a horizontal video to 9:16, following the speaker's face.

Adapted from OpenShorts (mutonby/openshorts, MIT — reframe_v2.py, plus the
SmoothedCameraman / SpeakerTracker / detect_face_candidates /
analyze_scenes_strategy pieces of main.py, all at the repo root, outside
cloud/). Ported because a fixed centre crop throws the speaker out of frame
the moment they move, and re-framing a 20-minute interview by hand is the
single most expensive step in cutting Reels from longform footage.

Two passes, no raw-frame piping:

  1. ANALYSIS — one ffmpeg decode at <=640px feeds MediaPipe BlazeFace into a
     tracker + damped "heavy tripod" camera, producing a crop-x per frame.
  2. RENDER — one ffmpeg per scene: dynamic crop driven by a sendcmd script
     (TRACK scenes) or a blurred-background fit (GENERAL scenes); segments are
     concatenated with stream copy and the source audio mapped straight in.

WHAT WAS CUT from the original, and why:
  * SPLIT / SCREENCAST / INSET / ALTERNATE / WIDE layouts and their modules
    (split_layout, screencast_layout, camera_inset, active_speaker,
    punch_in). They serve a podcast/screen-share SaaS; screencast_layout also
    calls the Gemini API, which this skill has no key for by design. Only
    TRACK and GENERAL survive — the two that matter for talking-head footage.
  * `crop_overrides` / `force_strategy`, which existed to serve a web editor's
    manual framing UI. `--force-strategy` is kept as a CLI flag because it is
    one line and answers "the tracker got this clip wrong"; the per-scene
    fraction map is not.
  * The YOLO person fallback (main.detect_person_yolo): it needs ultralytics
    plus a model download for a case BlazeFace already covers on talking-head
    footage. When no face is found the camera simply holds its last target.
  * NVENC encode tiers, loudness normalisation, metadata scrubbing beyond the
    basics, and the parallel-clip DETECT_LOCK (this runs one clip at a time).

Prints JSON to stdout; progress goes to stderr.

Usage:
    uv run python helpers/reframe.py <video> --edit-dir <dir>
    uv run python helpers/reframe.py <video> -o out.mp4 --aspect-ratio 9:16
    uv run python helpers/reframe.py <video> --edit-dir <dir> --force-strategy TRACK
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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

# Analysis decodes at this width; detectors get relative coords from MediaPipe
# so the boxes map back to the source exactly.
ANALYSIS_MAX_WIDTH = 640

# Detect every Nth frame — the camera interpolates between updates.
DETECT_STRIDE = max(int(os.environ.get("PRISMA_DETECT_STRIDE", "4")), 1)

# Short-form platforms expect a 1080-wide vertical upload; anything narrower
# reads as low quality. A 720p source only yields a 405x720 crop, so it gets
# scaled up to this floor rather than shipping sub-HD. Sources already wider
# are left alone (never downscale what the user supplied).
DELIVERY_MIN_WIDTH = 1080

# How much of the frame height the real content fills in a GENERAL scene.
# Fitting 16:9 to the full output width leaves it 32% of a 1920px frame — a
# thumbnail floating in blurred soup. 0.42 keeps ~76% of the source width while
# reaching 42% of the height. Set 0.32 to restore full-width behaviour.
GENERAL_CONTENT_HEIGHT_RATIO = float(
    os.environ.get("PRISMA_GENERAL_CONTENT_RATIO", "0.42"))

# A target that teleports further than the safe zone in one detection is far
# more often a detector error (a second face, a box snapping to a shoulder)
# than a person who moved. Big moves must repeat this many times before the
# camera commits. 1 restores the undamped behaviour.
JUMP_CONFIRM_FRAMES = max(int(os.environ.get("PRISMA_JUMP_CONFIRM", "3")), 1)


def log(msg: str) -> None:
    """Progress goes to stderr so stdout stays parseable JSON."""
    print(msg, file=sys.stderr, flush=True)


# --- pure helpers -----------------------------------------------------------

def parse_aspect(text: str) -> float:
    """'9:16' -> 0.5625. Also accepts a bare float."""
    if ":" in text:
        w, h = text.split(":", 1)
        return float(w) / float(h)
    return float(text)


def delivery_size(orig_w: int, orig_h: int, aspect_ratio: float) -> tuple[int, int]:
    """Output (width, height): the largest crop the source allows, upscaled to
    DELIVERY_MIN_WIDTH if narrower. Both even — x264 rejects odd dimensions."""
    out_h = orig_h
    out_w = int(out_h * aspect_ratio)
    if out_w > orig_w:
        out_w = orig_w
        out_h = int(out_w / aspect_ratio)

    if out_w < DELIVERY_MIN_WIDTH:
        out_w = DELIVERY_MIN_WIDTH
        out_h = int(round(out_w / aspect_ratio))

    return out_w + (out_w % 2), out_h + (out_h % 2)


def dedupe_sendcmd_lines(xs: list[int], fps: float, target: str = "crop@c") -> list[str]:
    """sendcmd lines setting crop x per frame, deduped to change-points.
    Timestamps are relative to the segment (the render seeks per scene)."""
    lines = []
    prev = None
    for i, x in enumerate(xs):
        if x != prev:
            lines.append(f"{i / fps:.4f} {target} x {x};")
            prev = x
    return lines


def scene_frame_ranges(scene_boundaries, strategies, total_frames):
    """Clamp scene (start, end) ranges to the decoded frame count, dropping
    empty ones. Each range carries its own strategy so dropping one can't
    misalign the rest."""
    ranges = []
    for i, (start_f, end_f) in enumerate(scene_boundaries):
        strategy = strategies[i] if i < len(strategies) else "TRACK"
        start_f = max(0, min(start_f, total_frames))
        end_f = max(start_f, min(end_f, total_frames))
        if end_f > start_f:
            ranges.append((start_f, end_f, strategy))
    return ranges


def concat_list_content(segment_paths) -> str:
    # Single quotes per the concat-demuxer spec; paths are tempfile-generated
    # so they carry no quotes of their own.
    return "".join(f"file '{p}'\n" for p in segment_paths)


def general_filtergraph(out_w: int, out_h: int) -> str:
    """Blurred-background layout for group/landscape scenes: the background
    fills the frame centre-cropped and blurred, the content is scaled to a
    readable share of the height and centred, overflowing the sides rather
    than floating small in the middle."""
    fg_h = int(out_h * GENERAL_CONTENT_HEIGHT_RATIO)
    fg_h += fg_h % 2
    return (
        f"[0:v]split=2[bga][fga];"
        f"[bga]scale=-2:{out_h},crop=w=min(iw\\,{out_w}):h={out_h},"
        f"scale={out_w}:{out_h},gblur=sigma=12[bg];"
        # Scale by HEIGHT then trim the overflow. crop centres by default, and
        # min() makes it a no-op for sources already narrower than the frame.
        f"[fga]scale=-2:{fg_h},crop=w=min(iw\\,{out_w}):h=ih[fg];"
        f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2,setsar=1[v]"
    )


# --- camera -----------------------------------------------------------------

class SmoothedCameraman:
    """A "heavy tripod": the camera only moves when the subject leaves a
    centre safe zone, and then it pans linearly rather than snapping."""

    def __init__(self, video_width: int, video_height: int, aspect_ratio: float):
        self.video_width = video_width
        self.video_height = video_height

        self.current_center_x = video_width / 2
        self.target_center_x = video_width / 2

        self.crop_height = video_height
        self.crop_width = int(self.crop_height * aspect_ratio)
        if self.crop_width > video_width:
            self.crop_width = video_width
            self.crop_height = int(self.crop_width / aspect_ratio)
        # Even dimensions: this crop feeds an x264 encode.
        self.crop_width -= self.crop_width % 2
        self.crop_height -= self.crop_height % 2

        # While the target sits inside this radius of the current centre, hold.
        self.safe_zone_radius = self.crop_width * 0.25

        self.jump_confirm_frames = JUMP_CONFIRM_FRAMES
        self._pending_target = None
        self._pending_count = 0

    def update_target(self, face_box) -> None:
        """Update the target centre from a detection, ignoring lone big jumps."""
        if not face_box:
            return
        x, _y, w, _h = face_box
        new_center = x + w / 2

        if abs(new_center - self.target_center_x) > self.safe_zone_radius:
            # Same big move as last time? Count it. Otherwise start counting
            # afresh — two contradictory outliers must not confirm each other.
            if (self._pending_target is not None
                    and abs(new_center - self._pending_target) <= self.safe_zone_radius):
                self._pending_count += 1
            else:
                self._pending_target = new_center
                self._pending_count = 1
            if self._pending_count < self.jump_confirm_frames:
                return  # not convinced yet — hold the frame

        self._pending_target = None
        self._pending_count = 0
        self.target_center_x = new_center

    def get_crop_x(self, force_snap: bool = False) -> int:
        """Advance the camera one frame and return the crop's left edge."""
        if force_snap:
            self.current_center_x = self.target_center_x
        else:
            diff = self.target_center_x - self.current_center_x
            if abs(diff) > self.safe_zone_radius:
                direction = 1 if diff > 0 else -1
                # A huge gap means a scene change or a genuinely fast move —
                # close it quickly. Otherwise pan slowly.
                speed = 15.0 if abs(diff) > self.crop_width * 0.5 else 3.0
                self.current_center_x += direction * speed
                # Never overshoot: that is what starts an oscillation.
                new_diff = self.target_center_x - self.current_center_x
                if (direction == 1 and new_diff < 0) or (direction == -1 and new_diff > 0):
                    self.current_center_x = self.target_center_x

        half = self.crop_width / 2
        if self.current_center_x - half < 0:
            self.current_center_x = half
        if self.current_center_x + half > self.video_width:
            self.current_center_x = self.video_width - half

        return max(0, min(int(self.current_center_x - half),
                          self.video_width - self.crop_width))


class SpeakerTracker:
    """Keeps the camera on one person across frames: matches faces to IDs by
    proximity, scores them by size with decay, and applies hysteresis plus a
    cooldown so a blink or a head-turn cannot trigger a switch."""

    def __init__(self, stabilization_frames: int = 15, cooldown_frames: int = 30):
        self.active_speaker_id = None
        self.speaker_scores: dict[int, float] = {}
        self.stabilization_threshold = stabilization_frames
        self.switch_cooldown = cooldown_frames
        self.last_switch_frame = -1000
        self.locked_counter = 0
        self.next_id = 0
        self.known_faces: list[dict] = []

    def get_target(self, face_candidates, frame_number: int, width: int):
        current: list[dict] = []

        # 1. Match detections to known IDs by horizontal distance.
        for face in face_candidates:
            x, _y, w, _h = face["box"]
            center_x = x + w / 2

            best_id = -1
            min_dist = width * 0.15  # tight radius so groups don't swap IDs
            for kf in self.known_faces:
                if frame_number - kf["last_frame"] > 30:  # forget after ~1s
                    continue
                dist = abs(center_x - kf["center"])
                if dist < min_dist:
                    min_dist = dist
                    best_id = kf["id"]

            if best_id == -1:
                best_id = self.next_id
                self.next_id += 1

            self.known_faces = [kf for kf in self.known_faces if kf["id"] != best_id]
            self.known_faces.append(
                {"id": best_id, "center": center_x, "last_frame": frame_number})
            current.append({"id": best_id, "box": face["box"], "score": face["score"]})

        # 2. Decay old scores, add the new ones (score == face area).
        for pid in list(self.speaker_scores):
            self.speaker_scores[pid] *= 0.85
            if self.speaker_scores[pid] < 0.1:
                del self.speaker_scores[pid]
        for cand in current:
            raw = cand["score"] / (width * width * 0.05)
            self.speaker_scores[cand["id"]] = self.speaker_scores.get(cand["id"], 0) + raw

        if not current:
            return None

        # 3. Pick the best, with a heavy stickiness bonus for whoever holds
        #    the frame right now.
        best = None
        max_score = -1.0
        for cand in current:
            total = self.speaker_scores.get(cand["id"], 0)
            if cand["id"] == self.active_speaker_id:
                total *= 3.0
            if total > max_score:
                max_score = total
                best = cand

        if not best:
            return None

        if best["id"] == self.active_speaker_id:
            self.locked_counter += 1
            return best["box"]

        # A new person. The cooldown has to hold whether or not the current
        # speaker was detected in THIS frame — a blink or a motion-blurred
        # frame is exactly when it is needed. Returning None makes the camera
        # keep its existing target instead of lurching across the frame.
        if frame_number - self.last_switch_frame < self.switch_cooldown:
            old = next((c for c in current if c["id"] == self.active_speaker_id), None)
            return old["box"] if old else None

        self.active_speaker_id = best["id"]
        self.last_switch_frame = frame_number
        self.locked_counter = 0
        return best["box"]


# --- detection --------------------------------------------------------------

# BlazeFace weights for the MediaPipe Tasks face detector. Kept next to the
# skill so a reframe never depends on a network call mid-render; downloaded on
# first use if missing (~230KB).
MODEL_DIR = Path(__file__).resolve().parent.parent / "assets" / "models"
BLAZEFACE_MODEL = MODEL_DIR / "blaze_face_short_range.tflite"
BLAZEFACE_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
                 "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")


class FaceDetector:
    """MediaPipe BlazeFace when available, Haar cascade otherwise.

    OpenShorts used the legacy `mp.solutions.face_detection` API, which
    mediapipe 1.x deleted — this is the Tasks-API equivalent (verified against
    the same footage: 12/12 frames, one face each, where the cascade also
    reported a spurious second face on one of them).

    NOTE the model file must be the one under `mediapipe-models/.../*.tflite`,
    not the same-named file under `mediapipe-assets/`: the latter ships without
    NormalizationOptions metadata and the Tasks API refuses to load it.

    The cascade fallback exists so reframe.py still runs on a base install: it
    misses profile faces and jitters more, but a worse follow beats an
    ImportError. `uv sync --extra reframe` gets the good one.
    """

    def __init__(self):
        self.backend = "haar"
        self._det = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            self._mp = mp
            if not BLAZEFACE_MODEL.exists():
                import urllib.request
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                log("   downloading BlazeFace weights (~230KB)")
                urllib.request.urlretrieve(BLAZEFACE_URL, BLAZEFACE_MODEL)

            options = vision.FaceDetectorOptions(
                base_options=mp_python.BaseOptions(
                    model_asset_path=str(BLAZEFACE_MODEL)),
                running_mode=vision.RunningMode.IMAGE,
                min_detection_confidence=0.5)
            self._det = vision.FaceDetector.create_from_options(options)
            self.backend = "mediapipe"
        except Exception as e:
            log(f"   mediapipe unavailable ({type(e).__name__}) — Haar cascade")
            self._cascade = cv2.CascadeClassifier(
                os.path.join(cv2.data.haarcascades,
                             "haarcascade_frontalface_default.xml"))

    def detect(self, frame) -> list[dict]:
        """Faces in this frame's pixel coords, as {'box': [x,y,w,h], 'score'}."""
        if self.backend == "mediapipe":
            img = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB,
                data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = self._det.detect(img)
            out = []
            for det in (result.detections or []):
                box = det.bounding_box
                bw, bh = int(box.width), int(box.height)
                if bw <= 0 or bh <= 0:
                    continue
                out.append({"box": [int(box.origin_x), int(box.origin_y), bw, bh],
                            "score": bw * bh})
            return out

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, 1.1, 5, minSize=(24, 24))
        return [{"box": [int(x), int(y), int(fw), int(fh)], "score": int(fw * fh)}
                for (x, y, fw, fh) in faces]


# --- scenes -----------------------------------------------------------------

def get_video_info(path: str) -> tuple[int, int, float, int]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"could not open video: {path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return w, h, float(fps), total


def detect_scene_boundaries(path: str, fps: float, total_frames: int) -> list[tuple[int, int]]:
    """(start, end) frame pairs. Falls back to one scene covering the whole
    clip — a missing shot list costs smoothness at cuts, not correctness."""
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        log("   scenedetect not installed — treating the clip as one scene")
        return [(0, total_frames)]

    try:
        video = open_video(path)
        manager = SceneManager()
        manager.add_detector(ContentDetector())
        manager.detect_scenes(video=video, show_progress=False)
        scenes = manager.get_scene_list()
    except Exception as e:
        log(f"   scene detection failed ({type(e).__name__}: {e}) — one scene")
        return [(0, total_frames)]

    if not scenes:
        return [(0, total_frames)]
    bounds = [(s.get_frames(), e.get_frames()) for s, e in scenes]
    return _merge_short_scenes(bounds, fps, 0.4)


def _merge_short_scenes(bounds, fps: float, min_sec: float):
    """Absorb scenes shorter than min_sec into a neighbour. Ultra-short scenes
    cause camera-snap bursts and starve the per-scene strategy sampling."""
    if len(bounds) <= 1 or min_sec <= 0:
        return bounds
    min_frames = max(1, int(round(min_sec * fps)))
    merged: list[tuple[int, int]] = []
    for s, e in bounds:
        if merged and (e - s) < min_frames:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_frames:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)
    return merged


def analyze_scene_strategies(path: str, boundaries, detector: FaceDetector,
                             fps: float) -> list[str]:
    """TRACK (one person, follow them) or GENERAL (crowd or landscape, fit with
    a blurred background) per scene, from 5 sampled frames each."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return ["TRACK"] * len(boundaries)

    strategies = []
    for s_f, e_f in boundaries:
        # Sample inside the scene: start+5/end-5 lands outside a scene shorter
        # than ~10 frames.
        margin = min(2, max(0, (e_f - s_f - 1) // 2))
        idxs = sorted({int(round(f))
                       for f in np.linspace(s_f + margin, e_f - 1 - margin, 5)})

        counts = []
        for f_idx in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ok, frame = cap.read()
            if not ok:
                continue
            # Near-black frames (fades, cut-to-black) carry no faces and used to
            # drag single-person scenes into GENERAL.
            if frame.mean() < 16:
                continue
            counts.append(len(detector.detect(_downscale(frame))))

        avg = sum(counts) / len(counts) if counts else 0
        # 0 faces -> landscape/B-roll; >1.2 -> a group. Both want GENERAL.
        strategies.append("GENERAL" if (avg > 1.2 or avg < 0.5) else "TRACK")

    cap.release()

    # Hysteresis: a short scene whose neighbours agree on the opposite verdict
    # is almost always a sampling miss (a profile face, an insert shot). Every
    # flip is a full on-screen layout change, so flapping is worse than an
    # occasional wrong-but-stable choice.
    max_flip = int(2.0 * fps)
    for i in range(1, len(strategies) - 1):
        dur = boundaries[i][1] - boundaries[i][0]
        if (dur < max_flip
                and strategies[i - 1] == strategies[i + 1] != strategies[i]):
            strategies[i] = strategies[i - 1]

    return strategies


def _downscale(frame):
    h, w = frame.shape[:2]
    if w <= ANALYSIS_MAX_WIDTH:
        return frame
    scale = w / ANALYSIS_MAX_WIDTH
    return cv2.resize(frame, (ANALYSIS_MAX_WIDTH, max(int(h / scale), 2)),
                      interpolation=cv2.INTER_AREA)


# --- analysis ---------------------------------------------------------------

def analyze_trajectory(path: str, boundaries, strategies, orig_w: int, orig_h: int,
                       detector: FaceDetector, cameraman: SmoothedCameraman,
                       tracker: SpeakerTracker) -> list[int | None]:
    """Per-frame crop x (None on GENERAL frames), from one downscaled decode."""
    small_w = min(ANALYSIS_MAX_WIDTH, orig_w)
    small_w -= small_w % 2
    small_h = max(int(orig_h * small_w / orig_w), 2)
    small_h += small_h % 2
    scale = orig_w / small_w
    frame_bytes = small_w * small_h * 3

    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", path,
         "-vf", f"scale={small_w}:{small_h}",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=frame_bytes * 4)

    xs: list[int | None] = []
    frame_number = 0
    scene_idx = 0
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape((small_h, small_w, 3))

            if scene_idx < len(boundaries):
                _start_f, end_f = boundaries[scene_idx]
                if frame_number >= end_f and scene_idx < len(boundaries) - 1:
                    scene_idx += 1

            strategy = strategies[scene_idx] if scene_idx < len(strategies) else "TRACK"

            if strategy == "GENERAL":
                # No trajectory needed; keep the camera parked so the next
                # TRACK scene starts from centre rather than a stale target.
                cameraman.current_center_x = orig_w / 2
                cameraman.target_center_x = orig_w / 2
                xs.append(None)
            else:
                if frame_number % DETECT_STRIDE == 0:
                    candidates = detector.detect(frame)
                    for cand in candidates:
                        cand["box"] = [int(v * scale) for v in cand["box"]]
                        cand["score"] = cand["box"][2] * cand["box"][3]
                    target = tracker.get_target(candidates, frame_number, orig_w)
                    if target:
                        cameraman.update_target(target)

                is_scene_start = (scene_idx < len(boundaries)
                                  and frame_number == boundaries[scene_idx][0])
                xs.append(cameraman.get_crop_x(force_snap=is_scene_start))

            frame_number += 1
            if frame_number % 500 == 0:
                log(f"   analyzed {frame_number} frames")
    finally:
        proc.stdout.close()
        proc.wait()

    return xs


# --- render -----------------------------------------------------------------

def _run(cmd) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')[-800:]}")


def render(path: str, out_path: str, xs, ranges, crop_w: int, crop_h: int,
           out_w: int, out_h: int, fps: float) -> None:
    workdir = tempfile.mkdtemp(prefix="prisma_reframe_")
    segments = []
    try:
        for idx, (start_f, end_f, strategy) in enumerate(ranges):
            seg_path = os.path.join(workdir, f"seg_{idx:03d}.mp4")
            ss = start_f / fps
            dur = (end_f - start_f) / fps

            if strategy == "GENERAL":
                graph = general_filtergraph(out_w, out_h)
            else:
                seg_xs = [x if x is not None else 0 for x in xs[start_f:end_f]]
                cmd_path = os.path.join(workdir, f"cmd_{idx:03d}.txt")
                lines = dedupe_sendcmd_lines(seg_xs, fps)
                with open(cmd_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                # sendcmd needs a forward-slash path even on Windows, and ':'
                # after a drive letter would be read as an option separator.
                esc = cmd_path.replace("\\", "/").replace(":", "\\:")
                graph = (
                    f"[0:v]sendcmd=f='{esc}',"
                    f"crop@c=w={crop_w}:h={crop_h}:x={seg_xs[0]}:y=0,"
                    f"scale={out_w}:{out_h},setsar=1[v]"
                )

            _run(["ffmpeg", "-y", "-loglevel", "error",
                  "-ss", f"{ss:.4f}", "-t", f"{dur:.4f}", "-i", path,
                  "-filter_complex", graph, "-map", "[v]",
                  "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-an", seg_path])
            segments.append(seg_path)
            log(f"   rendered scene {idx + 1}/{len(ranges)} ({strategy})")

        list_path = os.path.join(workdir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(concat_list_content(segments))

        # Concat the video segments (stream copy) and map audio from the source.
        # +faststart moves the moov atom to the front so a browser <video> can
        # start playing before the whole file downloads — a plain concat leaves
        # it at the end and the preview spins forever.
        _run(["ffmpeg", "-y", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", list_path,
              "-i", path,
              "-map", "0:v:0", "-map", "1:a:0?",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-map_metadata", "-1", "-map_chapters", "-1",
              "-movflags", "+faststart", "-shortest", out_path])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --- entry point ------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reframe a horizontal video to 9:16, following the speaker.")
    ap.add_argument("video")
    ap.add_argument("--edit-dir", default=None,
                    help="edit directory; output lands in <dir>/reframed/")
    ap.add_argument("-o", "--output", default=None,
                    help="explicit output path (overrides --edit-dir)")
    ap.add_argument("--aspect-ratio", default="9:16",
                    help="target aspect, e.g. 9:16 (default) or 4:5")
    ap.add_argument("--force-strategy", choices=["TRACK", "GENERAL"], default=None,
                    help="apply one strategy to every scene, skipping the classifier")
    ap.add_argument("--start", type=float, default=None,
                    help="only reframe from this many seconds in")
    ap.add_argument("--duration", type=float, default=None,
                    help="only reframe this many seconds")
    args = ap.parse_args()

    src = Path(args.video)
    if not src.exists():
        print(json.dumps({"error": f"video not found: {src}"}))
        return 1

    if args.output:
        out_path = Path(args.output)
    elif args.edit_dir:
        out_path = Path(args.edit_dir) / "reframed" / f"{src.stem}_9x16.mp4"
    else:
        out_path = src.with_name(f"{src.stem}_9x16.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    aspect = parse_aspect(args.aspect_ratio)
    workdir = None

    try:
        # A --start/--duration window is cut first so every later pass (scene
        # detection, analysis, render) sees the same timeline and the frame
        # indices line up.
        path = str(src)
        if args.start is not None or args.duration is not None:
            workdir = tempfile.mkdtemp(prefix="prisma_reframe_src_")
            trimmed = os.path.join(workdir, "trimmed.mp4")
            cut = ["ffmpeg", "-y", "-loglevel", "error"]
            if args.start is not None:
                cut += ["-ss", f"{args.start:.4f}"]
            cut += ["-i", path]
            if args.duration is not None:
                cut += ["-t", f"{args.duration:.4f}"]
            cut += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                    "-c:a", "aac", trimmed]
            _run(cut)
            path = trimmed
            log(f"   trimmed source window -> {args.duration or 'end'}s")

        orig_w, orig_h, fps, total = get_video_info(path)
        out_w, out_h = delivery_size(orig_w, orig_h, aspect)
        log(f"   source {orig_w}x{orig_h} @ {fps:.2f}fps -> {out_w}x{out_h}")

        detector = FaceDetector()
        log(f"   face backend: {detector.backend}")

        boundaries = detect_scene_boundaries(path, fps, total)
        log(f"   {len(boundaries)} scene(s)")

        if args.force_strategy:
            strategies = [args.force_strategy] * len(boundaries)
        else:
            strategies = analyze_scene_strategies(path, boundaries, detector, fps)
        log(f"   TRACK={strategies.count('TRACK')} GENERAL={strategies.count('GENERAL')}")

        cameraman = SmoothedCameraman(orig_w, orig_h, aspect)
        tracker = SpeakerTracker(cooldown_frames=30)
        xs = analyze_trajectory(path, boundaries, strategies, orig_w, orig_h,
                                detector, cameraman, tracker)
        if not xs:
            raise RuntimeError("analysis produced no frames")

        ranges = scene_frame_ranges(boundaries, strategies, len(xs))
        if not ranges:
            raise RuntimeError("no usable scene ranges")

        tracked = [x for x in xs if x is not None]
        motion = (max(tracked) - min(tracked)) if tracked else 0

        render(path, str(out_path), xs, ranges, cameraman.crop_width,
               cameraman.crop_height, out_w, out_h, fps)

        print(json.dumps({
            "output": str(out_path),
            "width": out_w,
            "height": out_h,
            "fps": round(fps, 3),
            "frames": len(xs),
            "scenes": len(ranges),
            "strategies": {"TRACK": strategies.count("TRACK"),
                           "GENERAL": strategies.count("GENERAL")},
            "face_backend": detector.backend,
            "crop_x_range": motion,
            "crop_size": [cameraman.crop_width, cameraman.crop_height],
        }))
        return 0
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
