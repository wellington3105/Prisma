"""Phase-2 layers ported to HyperFrames — registry and the fallback rule.

A layer is `ported` only when its parity fixture is green (hf_parity.py: SSIM in
the layer's box >= 0.95, entry/exit within ±1 frame — plan §3, decision 3).
`unported(ed)` lists every edit-data feature that is ON and NOT ported; when it
is not empty `render_phase2 --engine auto` renders the WHOLE video in Remotion
(decision 2: no hybrid) and says which keys caused it.

Each build module exposes `build(ctx)`. Paint order (z) copies the templates'
Main.tsx (shortform:808-840, longform:413-445).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import timebase as tb


@dataclass
class Ctx:
    edit: Path
    pub: Path
    ed: dict
    proj: object            # hfkit.project.Project
    meas: object            # hfkit.measure.Measurer
    W: int
    H: int
    fps: int
    N: int                  # total frames
    fmt: str                # "short" (9:16 template) | "long" (16:9 template)
    segs: list = field(default_factory=list)
    seams: list = field(default_factory=list)
    only: set | None = None
    notes: list = field(default_factory=list)

    def f(self, sec: float) -> int:
        return tb.fround(sec, self.fps)

    def wants(self, key: str) -> bool:
        return self.only is None or key in self.only


# key -> (ported, needs WebGL)
LAYERS = {
    "base": {"ported": True, "gl": False, "what": "cut.mp4 → assets/base.mp4, um clip por take"},
    "camera.zoomCuts": {"ported": True, "gl": False, "what": "zoom duro em cada emenda (camera.zooms)"},
    "camera.zoomAuto": {"ported": True, "gl": False, "what": "push-in lento (camera.pushIn)"},
    "camera.tracking": {"ported": False, "gl": False, "what": "seguir o rosto (track.json não neutro) — F2"},
    "captions.karaoke": {"ported": True, "gl": False, "what": "legenda karaokê"},
    "captions.stacked": {"ported": False, "gl": False, "what": "F2"},
    "captions.scatter": {"ported": False, "gl": False, "what": "F2"},
    "captions.simples": {"ported": False, "gl": False, "what": "F2"},
    "captions.serifada": {"ported": False, "gl": False, "what": "F2"},
    "captions.classica": {"ported": False, "gl": False, "what": "F2"},
    "hook.outline": {"ported": True, "gl": False, "what": "headline contorno"},
    "hook.card": {"ported": True, "gl": False, "what": "headline card (logo/selo opcionais)"},
    "hook.realce": {"ported": True, "gl": False, "what": "headline realce"},
    "hook.misto": {"ported": True, "gl": False, "what": "headline misto"},
    "highlights.prism": {"ported": True, "gl": False, "what": "card vidro-prisma 2D"},
    "highlights.pill": {"ported": True, "gl": False, "what": "card pílula"},
    "highlights.keynote": {"ported": False, "gl": False, "what": "F2"},
    "highlights.studio": {"ported": False, "gl": False, "what": "F2"},
    "highlights.hud": {"ported": False, "gl": False, "what": "F2"},
    "highlights.chrome": {"ported": False, "gl": True, "what": "F3 (three.js)"},
    "inserts": {"ported": True, "gl": False, "what": "inserts 9:16: card / cover / contain, imagem ou vídeo"},
    "inserts.glass": {"ported": False, "gl": True, "what": "insert refratado no GlassPanel — F3"},
    "broll": {"ported": True, "gl": False, "what": "B-roll 16:9 em tela cheia (imagem Ken-Burns / vídeo)"},
    "broll.pip": {"ported": False, "gl": False, "what": "apresentador em janela sobre o B-roll — F2"},
    "splitInserts": {"ported": True, "gl": False, "what": "tela dividida"},
    "fadeOut": {"ported": True, "gl": False, "what": "fade para preto no fim (imagem)"},
    "transitions": {"ported": False, "gl": False, "what": "flash / whip-pan / glitch — F2"},
    "transitions.shader": {"ported": False, "gl": True, "what": "displace / refract — F3"},
    "lowerThirds": {"ported": False, "gl": False, "what": "F2"},
    "chapters": {"ported": False, "gl": False, "what": "F2"},
    "callouts": {"ported": False, "gl": False, "what": "F2"},
    "behind": {"ported": False, "gl": False, "what": "F2 (matte VP9 com alfa)"},
    "glass": {"ported": False, "gl": True, "what": "F3"},
    "tracked": {"ported": False, "gl": True, "what": "F3"},
    "text3d": {"ported": False, "gl": True, "what": "F3"},
    "scrims": {"ported": False, "gl": False, "what": "F2 (CustomGraphics)"},
    "seriesBadge": {"ported": False, "gl": False, "what": "F2 (CustomGraphics)"},
    "customGraphics": {"ported": False, "gl": False, "what": "CustomGraphics.tsx editado no projeto — F2"},
}


def _track_neutral(pub: Path) -> bool:
    try:
        t = json.loads((pub / "track.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    pts = t.get("points") or []
    return len({(round(p[0], 4), round(p[1], 4)) for p in pts}) <= 1


def _custom_graphics_edited(edit: Path) -> bool:
    """The project's CustomGraphics.tsx differs from the template's (bespoke scenes)."""
    skill = Path(__file__).resolve().parents[3]
    mine = edit / "remotion" / "src" / "CustomGraphics.tsx"
    if not mine.exists():
        return False
    norm = lambda p: p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip()
    for tpl in ("shortform", "longform"):
        t = skill / "assets" / tpl / "src" / "CustomGraphics.tsx"
        if t.exists() and norm(t) == norm(mine):
            return False
    return True


def features(ed: dict, pub: Path | None = None, edit: Path | None = None) -> list[str]:
    """Every LAYERS key the edit-data turns on."""
    on: list[str] = ["base"]
    cam = ed.get("camera") or {}
    if cam.get("enabled"):
        on.append("camera.zoomCuts")
        if cam.get("pushIn"):
            on.append("camera.zoomAuto")
        if pub is not None and not _track_neutral(pub):
            on.append("camera.tracking")
    cap = ed.get("captions") or {}
    if cap.get("enabled"):
        on.append(f"captions.{cap.get('style') or 'karaoke'}")
    hook = ed.get("hook") or {}
    if hook.get("enabled"):
        on.append(f"hook.{hook.get('style') or 'outline'}")
    hl = ed.get("highlights") or {}
    if hl.get("enabled") and hl.get("items"):
        on.append(f"highlights.{hl.get('variant') or 'prism'}")
    for it in ed.get("inserts") or []:
        on.append("inserts.glass" if it.get("frame") == "glass" or it.get("anchor3d") else "inserts")
    for b in ed.get("broll") or []:
        on.append("broll")
        if b.get("pip"):
            on.append("broll.pip")
        if b.get("flash"):
            on.append("transitions")
    for sp in ed.get("splitInserts") or []:
        on.append("splitInserts")
        if sp.get("flash"):
            on.append("transitions")
    for t in ed.get("transitions") or []:
        on.append("transitions.shader" if (t or {}).get("type") in ("displace", "refract") else "transitions")
    if float(ed.get("fadeOut") or 0) > 0:
        on.append("fadeOut")
    for k in ("lowerThirds", "chapters", "callouts", "behind", "scrims"):
        if ed.get(k):
            on.append(k)
    for k in ("glass", "tracked", "text3d"):
        if (ed.get(k) or {}).get("enabled"):
            on.append(k)
    if ed.get("seriesBadge"):
        on.append("seriesBadge")
    if edit is not None and _custom_graphics_edited(edit):
        on.append("customGraphics")
    return list(dict.fromkeys(on))


def unported(ed: dict, pub: Path | None = None, edit: Path | None = None) -> list[str]:
    return [k for k in features(ed, pub, edit) if not LAYERS.get(k, {}).get("ported")]


def needs_gl(ed: dict, pub: Path | None = None) -> bool:
    return any(LAYERS.get(k, {}).get("gl") for k in features(ed, pub))


def public_table() -> dict:
    """For the preview (GET /api/engines)."""
    return {k: {"ported": v["ported"], "gl": v["gl"], "what": v["what"]} for k, v in LAYERS.items()}
