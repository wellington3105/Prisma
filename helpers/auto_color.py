"""auto_color.py — cor automática por IA (nível "ajuste automático" do CapCut), uma LUT por fonte.

Modelo: Image-Adaptive 3D LUT (Zeng et al., TPAMI 2022; pesos sRGB treinados na MIT-Adobe FiveK,
Apache-2.0 — assets/models/ia3dlut/NOTICE.txt). Uma rede pequena olha a imagem e mistura 3 LUTs
base numa LUT própria para aquela cena. Roda na CPU em segundos; não precisa de internet.

Por que uma LUT por FONTE (e não por quadro): os pesos são a MÉDIA sobre quadros amostrados
dentro dos trechos do EDL — a cor não "respira" entre quadros (zero tremulação por construção)
e a LUT entra no render como um lut3d comum (Hard Rule 7: grade por segmento na extração).

Medido 2026-11-16 (Deocar, bancada em Videos/Deocar/autocolor):
  · vídeo 01: ΔE 3,8 contra a cor feita à mão pelo usuário — melhor que a LUT fixa (4,5) e que
    qualquer método clássico; sem treino.
  · vídeo 03 (cena escura que o usuário ESCURECEU de propósito): ΔE 13 — a IA clareia. É um
    "auto" genérico de profissional, não o gosto de um cliente → sempre mostrar o mosaico.
  · vídeo 04: o usuário escolheu IA 70 % entre atual/IA100/IA70/IA-unpaired.
  · variante "unpaired": pele laranja demais no 04 — fica só como opção.

Uso:
  auto_color.py --edit-dir <edit>                     # fontes do edl.json; LUTs 100/70/50 + mosaico
  auto_color.py --edit-dir <edit> --apply 70          # grava edl.json "grades": {fonte: lut3d…}
  auto_color.py --edit-dir <edit> --video x.mp4       # sem EDL: amostra o vídeo inteiro
Opções: --frames 12 · --strengths 100,70,50 · --variant paired|unpaired · --denoise light|none
        --frame <t> (quadro do mosaico, tempo na fonte) · --source <chave> (só uma fonte)

Depois do --apply: render.py como sempre. A global "grade" do EDL é ignorada nas fontes que têm
entrada em "grades". LOG/HLG/PQ: NÃO usar sobre o arquivo cru — a rede foi treinada em sRGB
(converta antes com o grade do detect_color e só então avalie).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

for _s in (sys.stdout, sys.stderr):  # Δ and → crash a captured cp1252 console
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE.parent / "assets" / "models" / "ia3dlut"
DIM = 33
DENOISE = {"light": "format=yuv420p,nlmeans=s=1.6:p=7:pc=5:r=11:rc=7,hqdn3d=1:1:3:3", "none": ""}


# ------------------------------------------------------------------ modelo
def _nets():
    import torch.nn as nn

    def block(i, o, norm):
        layers = [nn.Conv2d(i, o, 3, stride=2, padding=1), nn.LeakyReLU(0.2)]
        if norm:
            layers.append(nn.InstanceNorm2d(o, affine=True))
        return layers

    class Classifier(nn.Module):
        def __init__(self, paired=True):
            super().__init__()
            tail = [nn.Dropout(p=0.5)] if paired else []
            self.model = nn.Sequential(
                nn.Upsample(size=(256, 256), mode="bilinear"),
                nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.LeakyReLU(0.2), nn.InstanceNorm2d(16, affine=True),
                *block(16, 32, paired), *block(32, 64, paired), *block(64, 128, paired), *block(128, 128, False),
                *tail, nn.Conv2d(128, 3, 8, padding=0))

        def forward(self, x):
            return self.model(x)

    return Classifier


_cache: dict = {}


def load(variant: str = "paired"):
    if variant in _cache:
        return _cache[variant]
    import torch
    suf = "" if variant == "paired" else "_unpaired"
    luts = torch.load(WEIGHTS / f"LUTs{suf}.pth", map_location="cpu", weights_only=True)
    clf = _nets()(paired=variant == "paired")
    clf.load_state_dict(torch.load(WEIGHTS / f"classifier{suf}.pth", map_location="cpu", weights_only=True), strict=True)
    clf.eval()
    basis = torch.stack([luts[str(i)]["LUT"] for i in range(3)])  # (3 bases, 3 canais, b, g, r)
    _cache[variant] = (clf, basis)
    return clf, basis


def predict_weights(frames_rgb01: list[np.ndarray], variant: str = "paired") -> np.ndarray:
    import torch
    clf, _ = load(variant)
    out = []
    with torch.no_grad():
        for f in frames_rgb01:
            x = torch.from_numpy(np.ascontiguousarray(f.transpose(2, 0, 1))).float()[None]
            out.append(clf(x).squeeze().numpy())
    return np.array(out)


def lut_from_weights(w, variant: str = "paired", strength: float = 1.0) -> np.ndarray:
    import torch
    _, basis = load(variant)
    lut = (torch.from_numpy(np.asarray(w, dtype=np.float32))[:, None, None, None, None] * basis).sum(0)
    r = torch.linspace(0, 1, DIM)
    b, g, rr = torch.meshgrid(r, r, r, indexing="ij")
    ident = torch.stack([rr, g, b])
    lut = ident + (lut - ident) * strength
    return lut.clamp(0, 1).numpy()


def write_cube(lut: np.ndarray, path: Path, title: str = "") -> None:
    n = lut.shape[1]
    with open(path, "w", encoding="ascii") as f:
        if title:
            f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {n}\n")
        for bi in range(n):          # .cube: vermelho varia mais rápido — mesma ordem da LUT do modelo
            for gi in range(n):
                for ri in range(n):
                    f.write(f"{lut[0, bi, gi, ri]:.6f} {lut[1, bi, gi, ri]:.6f} {lut[2, bi, gi, ri]:.6f}\n")


# ------------------------------------------------------------------ vídeo
def ff_path(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:")


def grade_string(cube: Path, denoise: str) -> str:
    g = f"lut3d=file='{ff_path(cube)}'"
    return f"{g},{DENOISE[denoise]}" if DENOISE.get(denoise) else g


def sample_times(ranges: list[tuple[float, float]], n: int) -> list[float]:
    total = sum(b - a for a, b in ranges)
    ts, acc = [], 0.0
    targets = [(i + 0.5) * total / n for i in range(n)]
    for a, b in ranges:
        for t in targets:
            if acc <= t < acc + (b - a):
                ts.append(a + (t - acc))
        acc += b - a
    return ts


def grab(video: str, t: float, out: Path) -> np.ndarray:
    import cv2
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                    "-vf", "scale=540:-2:flags=area,format=rgb24", str(out)], check=True)
    return cv2.cvtColor(cv2.imread(str(out)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def duration(video: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edit-dir", required=True)
    ap.add_argument("--edl", default="edl.json")
    ap.add_argument("--video", help="sem EDL: um vídeo inteiro (chave = nome do arquivo)")
    ap.add_argument("--source", help="só esta fonte do EDL")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--strengths", default="100,70,50")
    ap.add_argument("--variant", default="paired", choices=["paired", "unpaired"])
    ap.add_argument("--denoise", default="light", choices=list(DENOISE))
    ap.add_argument("--frame", type=float, help="tempo (na fonte) do quadro do mosaico")
    ap.add_argument("--apply", type=int, metavar="PCT", help="grava no EDL a LUT nesta intensidade")
    a = ap.parse_args()

    edit = Path(a.edit_dir).resolve()
    gdir, vdir = edit / "grade", edit / "verify"
    gdir.mkdir(parents=True, exist_ok=True)
    vdir.mkdir(parents=True, exist_ok=True)
    edl_p = edit / a.edl
    edl = json.loads(edl_p.read_text(encoding="utf-8")) if edl_p.exists() else None

    jobs: dict[str, tuple[str, list[tuple[float, float]]]] = {}
    if a.video:
        jobs[Path(a.video).stem] = (a.video, [(0.0, duration(a.video))])
    elif edl:
        for key, path in edl["sources"].items():
            if a.source and key != a.source:
                continue
            rs = [(float(r["start"]), float(r["end"])) for r in edl["ranges"] if r["source"] == key]
            if rs:
                jobs[key] = (str(Path(path) if Path(path).is_absolute() else (edit / path)), rs)
    else:
        print("sem edl.json e sem --video", file=sys.stderr)
        return 2

    strengths = sorted({int(s) for s in a.strengths.split(",")} | ({a.apply} if a.apply else set()), reverse=True)
    applied = {}
    for key, (video, ranges) in jobs.items():
        with tempfile.TemporaryDirectory() as td:
            ts = sample_times(ranges, a.frames)
            frames = [grab(video, t, Path(td) / f"f{i}.png") for i, t in enumerate(ts)]
        w = predict_weights(frames, a.variant)
        mean, spread = w.mean(0), w.std(0)
        print(f"[{key}] {len(frames)} quadros · pesos {[round(float(x), 3) for x in mean]} · variação entre quadros {[round(float(x), 3) for x in spread]}")
        if spread.max() > 0.35:
            print(f"  ⚠ cenas muito diferentes dentro de '{key}' (variação {spread.max():.2f}) — considere separar a fonte por plano")
        cubes = {}
        for s in strengths:
            cube = gdir / f"ia_{key}_{a.variant}_{s}.cube"
            write_cube(lut_from_weights(mean, a.variant, s / 100), cube, f"Prisma auto_color {key} {a.variant} {s}%")
            cubes[s] = cube
            print(f"  {s:3d}% → {cube.name}")
        # mosaico: original × intensidades (com o mesmo denoise que vai para o render)
        t = a.frame if a.frame is not None else ts[len(ts) // 2]
        cands = ["original="] + [f"IA_{s}={grade_string(cubes[s], a.denoise)}" for s in strengths]
        out = vdir / f"auto_color_{key}.png"
        subprocess.run([sys.executable, str(HERE / "grade.py"), video, "--candidates", ";".join(cands),
                        "--frame", f"{t:.2f}", "-o", str(out)], check=True, capture_output=True)
        print(f"  mosaico: {out}")
        if a.apply:
            applied[key] = grade_string(cubes[a.apply], a.denoise)

    if a.apply and edl is not None:
        edl.setdefault("grades", {}).update(applied)
        edl_p.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"edl.json: grades ← IA {a.apply}% para {', '.join(applied)} (a 'grade' global fica para as outras fontes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
