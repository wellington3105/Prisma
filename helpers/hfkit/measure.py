"""Measure text in HyperFrames' Chrome with the project's own font files.

    m = Measurer(project_root)            # starts Chrome once (puppeteer-core from the HF install)
    m.widths([{"text": "Olá", "size": 62, "weight": 900, "letterSpacing": "-1px"}])
    m.close()

Same procedure as @remotion/layout-utils measureText (inline-block span,
white-space:pre, getBoundingClientRect().width), same woff2 files as Remotion's
@remotion/google-fonts — so a line breaks where the Remotion template breaks it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .project import FONT_POPPINS, font_faces

HERE = Path(__file__).resolve().parent


def _global_root() -> Path:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    out = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", shell=False).stdout.strip()
    return Path(out)


def _puppeteer() -> Path:
    for base in (_global_root() / "hyperframes" / "node_modules", _global_root()):
        p = base / "puppeteer-core"
        if (p / "package.json").exists():
            return p
    raise SystemExit("puppeteer-core não encontrado (vem com o CLI hyperframes: npm i -g hyperframes@0.8.93)")


def _chrome(hf: list[str]) -> str:
    out = subprocess.run(hf + ["browser", "path"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout.strip().splitlines()
    for line in reversed(out):
        if line.strip() and Path(line.strip()).exists():
            return line.strip()
    out = subprocess.run(hf + ["browser", "ensure"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout.strip().splitlines()
    for line in reversed(out):
        cand = line.split()[-1] if line.split() else ""
        if cand and Path(cand).exists():
            return cand
    raise SystemExit("Chrome do HyperFrames não encontrado — rode `hyperframes browser ensure`")


class Measurer:
    def __init__(self, root: Path, hf: list[str]):
        page = root / ".prisma" / "measure.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        # fonts are referenced relative to the project root
        page.write_text("<!doctype html><html><head><meta charset='utf-8'><style>"
                        + font_faces().replace('url("assets/', 'url("../assets/')
                        + "</style></head><body></body></html>", encoding="utf-8")
        node = shutil.which("node") or "node"
        self.p = subprocess.Popen([node, str(HERE / "measure.mjs"), str(_puppeteer()), _chrome(hf), str(page)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8")
        self.cache: dict[tuple, float] = {}

    def widths(self, items: list[dict]) -> list[float]:
        keys = [(it["text"], it.get("family", FONT_POPPINS), float(it["size"]), int(it["weight"]),
                 it.get("letterSpacing") or "") for it in items]
        todo = [k for k in dict.fromkeys(keys) if k not in self.cache]
        if todo:
            req = {"items": [{"text": k[0], "family": k[1], "size": k[2], "weight": k[3], "letterSpacing": k[4]}
                             for k in todo]}
            self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
            if not line:
                raise SystemExit("medição de texto falhou:\n" + (self.p.stderr.read() or "")[-1500:])
            for k, w in zip(todo, json.loads(line)["widths"]):
                self.cache[k] = float(w)
        return [self.cache[k] for k in keys]

    def width(self, text: str, size: float, weight: int, letter_spacing: str = "") -> float:
        return self.widths([{"text": text, "size": size, "weight": weight, "letterSpacing": letter_spacing}])[0]

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=20)
        except Exception:
            self.p.kill()
