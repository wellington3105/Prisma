"""Phase-2 parity fixture: two 12 s edits (9:16 and 16:9), one layer per window.

    uv run python tests/fixture_phase2/make_fixture.py <work_dir>   # → <work>/v916/edit, <work>/h169/edit

Footage comes from the Phase-1 fixture (tests/fixture/cayenne_clip.mp4 — client
material, local use only), cropped to each aspect; captions are synthetic word
timings (the karaoke maths only needs times and text). Each edit gets a
remotion/ project (template copy + the shared runtime junction) so the SAME
edit-data renders on both engines. Used by `regress.py --phase2`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
CLIP = SKILL / "tests" / "fixture" / "cayenne_clip.mp4"
RUNTIME = Path(os.environ.get("PRISMA_REMOTION_RUNTIME") or Path.home() / ".prisma" / "remotion-runtime") / "node_modules"
FPS, DUR = 30, 12.0
WORDS = ("Esse carro tem um motor que surpreende, e o consumo na cidade ficou abaixo do esperado. "
         "A garantia vai até o fim do ano que vem, revisões feitas na concessionária. "
         "Agora repara no acabamento interno: couro, costura dupla e painel digital.").split()

V916 = {
    "width": 1080, "height": 1920, "fps": FPS, "durationSec": DUR, "accent": "#ff5200",
    "camera": {"enabled": True, "zooms": [1.1, 1.18, 1.14], "pushIn": 0.05, "targetX": 0.5, "targetY": 0.4},
    "hook": {"enabled": True, "endSec": 2.2, "text": "O consumo desse carro me surpreendeu", "style": "card"},
    "captions": {"enabled": True, "style": "karaoke", "fontSize": 70, "maxWords": 3, "safeWidth": 900,
                 "paddingBottom": 380, "windows": [{"start": 8.4, "end": 10.2, "paddingBottom": 1110}]},
    "inserts": [{"id": "i01", "src": "fx/card.png", "start": 2.6, "end": 4.6},
                {"id": "i02", "src": "fx/broll.mp4", "start": 5.0, "end": 6.8, "fit": "cover", "enter": "spring"}],
    "splitInserts": [{"id": "s01", "src": "fx/card.png", "start": 8.4, "end": 10.2, "layout": "top", "bandH": 750}],
    "highlights": {"enabled": True, "variant": "prism", "offsetS": 0, "items": [
        {"text": "12 km/l", "label": "CONSUMO", "at": 6.9, "dur": 1.5, "y": 0.28}]},
    "soundtrack": {"enabled": False, "file": "trilha.mp3"},
    "behind": [], "fadeOut": 0.6,
}
H169 = {
    "width": 1920, "height": 1080, "fps": FPS, "durationSec": DUR, "accent": "#ff5200",
    "camera": {"enabled": True, "zooms": [1.06, 1.12, 1.09], "pushIn": 0.03, "targetX": 0.5, "targetY": 0.4},
    "hook": {"enabled": True, "endSec": 2.2, "text": "O consumo desse carro me surpreendeu", "style": "outline"},
    "captions": {"enabled": True, "style": "karaoke", "maxWords": 6, "fontScale": 1, "highlight": "#ff5200"},
    "broll": [{"id": "b01", "kind": "video", "src": "fx/broll.mp4", "start": 2.6, "dur": 1.8},
              {"id": "b02", "kind": "image", "src": "fx/card.png", "start": 4.8, "dur": 1.6}],
    "splitInserts": [{"id": "s01", "src": "fx/card.png", "start": 8.6, "end": 10.2, "layout": "left", "bandW": 0.45}],
    "highlights": {"enabled": True, "variant": "pill", "offsetS": 0, "items": [
        {"text": "12 km/l", "label": "CONSUMO", "at": 6.7, "dur": 1.6}]},
    "lowerThirds": [], "chapters": [], "callouts": [],
    "soundtrack": {"enabled": False, "file": "trilha.mp3"},
}


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, a)], check=True)


def captions() -> list[dict]:
    out, t, i = [], 0.25, 0
    while t < DUR - 0.6 and i < len(WORDS):
        w = WORDS[i]
        d = 0.18 + 0.03 * min(len(w), 8)
        out.append({"text": w, "startMs": round(t * 1000), "endMs": round((t + d) * 1000), "timestampMs": None,
                    "confidence": None})
        t += d + (0.5 if w.endswith((".", ":")) else 0.07)
        i += 1
    return out


def make(work: Path, name: str, ed: dict, tpl: str) -> Path:
    edit = work / name / "edit"
    pub = edit / "remotion" / "public"
    (pub / "fx").mkdir(parents=True, exist_ok=True)
    W, H = ed["width"], ed["height"]
    crop = "crop=ih*9/16:ih" if H > W else "crop=iw:iw*9/16"
    ff("-ss", 3, "-t", DUR, "-i", CLIP, "-vf", f"{crop},scale={W}:{H}:flags=lanczos,fps={FPS},format=yuv420p",
       "-c:v", "libx264", "-crf", "16", "-g", FPS, "-c:a", "aac", "-ar", "48000", "-color_range", "tv",
       "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart",
       edit / "cut.mp4")
    shutil.copy2(edit / "cut.mp4", pub / "cut.mp4")
    shutil.copytree(SKILL / "assets" / tpl / "public" / "sfx", pub / "sfx", dirs_exist_ok=True)  # Remotion's own SFX
    ff("-ss", 22, "-t", 3, "-i", CLIP, "-an", "-vf", f"{crop},scale={W}:{H},fps={FPS},format=yuv420p",
       "-c:v", "libx264", "-crf", "18", "-g", FPS, pub / "fx" / "broll.mp4")
    ff("-ss", 30, "-i", CLIP, "-frames:v", 1, "-vf", "scale=1280:-2", pub / "fx" / "card.png")
    seams = [0.0, 2.4, 5.2, 7.6, 10.4]
    segs = [{"start": s, "dur": round((seams[i + 1] if i + 1 < len(seams) else DUR) - s, 4)} for i, s in enumerate(seams)]
    (pub / "segments.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
    (pub / "captions.json").write_text(json.dumps(captions(), ensure_ascii=False), encoding="utf-8")
    (pub / "track.json").write_text(json.dumps({"fps": FPS, "points": [[0.5, 0.4]], "neutral": True}), encoding="utf-8")
    (pub / "caption-cues.json").write_text(json.dumps({"fps": FPS, "cues": []}), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps(ed, ensure_ascii=False, indent=1), encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({"version": 1, "sources": {}, "ranges": []}), encoding="utf-8")
    rem = edit / "remotion"
    src = SKILL / "assets" / tpl
    for item in ("src", "package.json", "remotion.config.ts", "tsconfig.json"):
        p = src / item
        (shutil.copytree if p.is_dir() else shutil.copy2)(p, rem / item)
    if not (rem / "node_modules").exists():
        if sys.platform == "win32":
            import _winapi
            _winapi.CreateJunction(str(RUNTIME), str(rem / "node_modules"))
        else:
            os.symlink(RUNTIME, rem / "node_modules")
    return edit


def main() -> None:
    work = Path(sys.argv[1]).resolve()
    for name, ed, tpl in (("v916", V916, "shortform"), ("h169", H169, "longform")):
        print(make(work, name, ed, tpl))


if __name__ == "__main__":
    main()
