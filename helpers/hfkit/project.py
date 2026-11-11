"""A Prisma HyperFrames project on disk: skeleton, local fonts/GSAP/runtime, writers.

Contract (skill `hyperframes` §Contract): the root holds only hosts, media and
audio; each layer instance is its own `compositions/<id>.html` with a paused
timeline registered in `window.__timelines`. CSS is inline (traps §3: a <link>
changed glyph drawing in the render). GSAP and fonts are local files (traps §2:
the CDN made offline `check` fail).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import timebase as tb

SKILL = Path(__file__).resolve().parents[2]
HF_ASSETS = SKILL / "assets" / "hyperframes"
FONTS = HF_ASSETS / "fonts"
VENDOR = HF_ASSETS / "vendor"
# The version every Phase-2 HyperFrames project is built and rendered with
# (traps §1 "versão fixa por vídeo"). An upgrade happens only with the parity
# fixture green (plan §5).
HF_PIN = "0.8.93"

FONT_POPPINS = "PrismaPoppins"
FONT_STACK = f"'{FONT_POPPINS}', sans-serif"   # single quotes: it goes inside style="…"


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(map(str, cmd))}\n{(r.stdout or '')[-1500:]}{(r.stderr or '')[-1500:]}")
    return r


def hf_cli(pin: str = HF_PIN) -> list[str]:
    """The pinned CLI: the global one when it IS the pin, else `npx --yes hyperframes@pin`."""
    exe = shutil.which("hyperframes")
    if exe:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=60).stdout
            if pin in (out or ""):
                return [exe]
        except Exception:
            pass
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("npx não encontrado no PATH (HyperFrames precisa de Node 22+)")
    return [npx, "--yes", f"hyperframes@{pin}"]


def font_faces(families=(FONT_POPPINS,), weights=None) -> str:
    """@font-face rules for the local files (paths relative to the project root)."""
    man = json.loads((FONTS / "fonts.json").read_text(encoding="utf-8"))
    out = []
    for fam in families:
        for face in man["families"][fam]:
            if weights and face["weight"] not in weights:
                continue
            for sub, fn in face["files"].items():
                ur = man["unicodeRange"].get(sub)
                out.append(f'@font-face {{ font-family: "{fam}"; font-style: {face["style"]}; '
                           f'font-weight: {face["weight"]}; font-display: block; '
                           f'src: url("assets/fonts/{fn}") format("woff2");'
                           + (f" unicode-range: {ur};" if ur else "") + " }")
    return "\n".join(out)


def project_sig(root: Path) -> str:
    """Same fingerprint as export_hyperframes.py: index + compositions, Studio ids stripped."""
    h = hashlib.sha1()
    for f in [root / "index.html"] + sorted((root / "compositions").glob("*.html")):
        if f.exists():
            t = re.sub(r'\sdata-hf-id="[^"]*"', "", f.read_text(encoding="utf-8"))
            h.update(f.name.encode())
            h.update(t.encode("utf-8"))
    return h.hexdigest()


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def js(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


class Project:
    """Writes one HyperFrames project. Times are in FRAMES; tb.span() turns them into seconds."""

    def __init__(self, root: Path, W: int, H: int, fps: int):
        self.root, self.W, self.H, self.fps = root, W, H, fps
        self.comp = root / "compositions"
        self.hosts: list[tuple[int, str]] = []      # (z, html line) — root-level hosts
        self.media: list[tuple[int, str]] = []      # (z, html line) — root-level <video>/<img> wrappers
        self.audio: list[str] = []
        self.root_script: list[str] = []            # tweens on the main timeline (camera)
        self.ids: set[str] = set()
        self.windows: dict[str, list] = {}           # layer key -> [(f0, f1, box, id)] for parity/tone

    # ---- skeleton ----
    def init(self, edit: Path):
        self.root.mkdir(parents=True, exist_ok=True)
        self.comp.mkdir(exist_ok=True)
        for c in self.comp.glob("*.html"):
            c.unlink()
        for d in ("assets/fonts", "assets/vendor", "assets/media"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        for f in FONTS.glob("*"):
            if f.suffix in (".woff2", ".txt"):
                shutil.copy2(f, self.root / "assets" / "fonts" / f.name)
        for f in VENDOR.glob("*.js"):
            shutil.copy2(f, self.root / "assets" / "vendor" / f.name)
        hj = self.root / "hyperframes.json"
        if not hj.exists():
            hj.write_text(json.dumps({
                "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
                "media": {"autoProxy": True}, "authoringSkill": "prisma"}, indent=2), encoding="utf-8")
        mj = self.root / "meta.json"
        if not mj.exists():
            mj.write_text(json.dumps({"id": "hyperframes", "name": "hyperframes"}, indent=2), encoding="utf-8")
        sys.path.insert(0, str(SKILL / "helpers"))
        from hf_version import stamp  # noqa: E402
        stamp(self.root, HF_PIN)

    def asset(self, src: Path, sub: str = "media") -> str:
        """Copy a file into assets/<sub>/ (skipped when identical) and return its project path."""
        dst = self.root / "assets" / sub / src.name
        if not (dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return f"assets/{sub}/{src.name}"

    def uid(self, base: str) -> str:
        cid, n = base, 2
        while cid in self.ids:
            cid, n = f"{base}-{n}", n + 1
        self.ids.add(cid)
        return cid

    # ---- writers ----
    def sub(self, cid: str, style: str, body: str, script: str, fonts: bool = True):
        faces = font_faces() if fonts else ""
        (self.comp / f"{cid}.html").write_text(f"""<!doctype html>
<html lang="pt-BR">
  <head><meta charset="UTF-8" /></head>
  <body>
    <template>
      <style>
{faces}
        #root {{ position: absolute; inset: 0; }}
        #root, #root * {{ box-sizing: border-box; }}
{style}
      </style>
      <div id="root" data-composition-id="{cid}" data-width="{self.W}" data-height="{self.H}">
{body}
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
{script}
          window.__timelines["{cid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
""", encoding="utf-8")

    def host(self, cid: str, f0: int, f1: int, track: int, kind: str, z: int, layer: str = "", box=None):
        s, d = tb.span(f0, f1, self.fps)
        self.hosts.append((z, f'    <div id="{cid}" class="clip" data-composition-id="{cid}" '
                              f'data-composition-src="compositions/{cid}.html" data-start="{s}" '
                              f'data-duration="{d}" data-track-index="{track}" data-track-kind="{kind}" '
                              f'data-width="{self.W}" data-height="{self.H}" style="z-index:{z}"></div>'))
        if layer:
            self.windows.setdefault(layer, []).append({"id": cid, "f0": f0, "f1": f1, "box": box})

    def write_index(self, n_frames: int):
        dur = tb.root_duration(n_frames, self.fps)
        lines = [l for _, l in sorted(self.media, key=lambda x: x[0])]
        lines += [l for _, l in sorted(self.hosts, key=lambda x: x[0])]
        (self.root / "index.html").write_text(f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={self.W}, height={self.H}" />
    <script src="assets/vendor/gsap.min.js"></script>
    <script src="assets/vendor/prisma-hf.js"></script>
    <style>
      * {{ box-sizing: border-box; }}  /* Remotion's default CSS (default-css.js) */
      html, body {{ margin: 0; padding: 0; width: {self.W}px; height: {self.H}px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: {self.W}px; height: {self.H}px; overflow: hidden; background: #000; }}
      .cam {{ position: absolute; left: 0; top: 0; width: {self.W}px; height: {self.H}px; transform-origin: 0 0; }}
      .cam video {{ position: absolute; left: 0; top: 0; width: {self.W}px; height: {self.H}px; object-fit: fill; }}
    </style>
  </head>
  <body>
  <div id="root" data-composition-id="main" data-width="{self.W}" data-height="{self.H}" data-duration="{dur}">
{chr(10).join(lines)}
{chr(10).join(self.audio)}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(self.root_script)}
      window.__timelines["main"] = tl;
    }})();
  </script>
  </body>
</html>
""", encoding="utf-8")
