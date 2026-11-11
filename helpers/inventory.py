"""Inventário das fontes da Fase 1 — ordem de gravação, fps real, alertas.

Roda ANTES de transcrever. Para cada vídeo da pasta (ou dos arquivos dados):
duração, resolução, fps, codec, áudio, perfil de cor e data de gravação, em
ORDEM DE GRAVAÇÃO (metadado `creation_time` / `com.apple.quicktime.creationdate`;
sem metadado, pelo nome). Multi-take de concessionária sai de vários celulares
com nomes que não seguem a ordem real — o nome sozinho já trocou takes de lugar.

Alertas:
  VFR        — taxa de quadros variável (gravação de tela, celular em pouca luz).
               Medida pelo intervalo REAL entre frames dos primeiros ~10 s, não
               só por r_frame_rate × avg_frame_rate: um arquivo pode declarar 30
               nas duas e variar por dentro. Problema para sync e para o corte.
  FPS MISTO  — fontes com fps diferentes entre si.
  SEM ÁUDIO  — o corte da Fase 1 é guiado pelo áudio.
  ILEGÍVEL   — ffprobe não abriu.

Adaptado de `LeiteZ/fluxo-de-edicao` (etapa preparar, MIT).

Uso:
    uv run python helpers/inventory.py <videos_dir>
    uv run python helpers/inventory.py a.mp4 b.mov --json
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
import statistics
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".mxf"}
VFR_SAMPLE_S = 10
VFR_JITTER = 0.10   # desvio-padrão do intervalo / média acima disto = VFR


def ffprobe(path: Path) -> dict | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
                        str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def rate(s: str | None) -> float:
    try:
        f = Fraction(s or "0")
        return float(f) if f.denominator else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


NOMINAL = (23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 59.94, 60.0, 119.88, 120.0)


def nominal(f: float) -> float:
    return min(NOMINAL, key=lambda n: abs(n - f))


def frame_jitter(path: Path) -> tuple[float, int]:
    """(desvio/média do intervalo entre frames, nº de frames medidos)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals",
                        f"%+{VFR_SAMPLE_S}", "-show_entries", "packet=pts_time", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    ts = sorted(float(x) for x in r.stdout.split() if x.replace(".", "", 1).replace("-", "", 1).isdigit())
    d = [b - a for a, b in zip(ts, ts[1:]) if b - a > 0]
    if len(d) < 10:
        return 0.0, len(d)
    return statistics.pstdev(d) / statistics.mean(d), len(d)


def created(fmt: dict, vs: dict) -> str | None:
    tags = {**(vs.get("tags") or {}), **(fmt.get("tags") or {})}
    for k in ("com.apple.quicktime.creationdate", "creation_time", "date"):
        if tags.get(k):
            return tags[k]
    return None


def probe(path: Path) -> dict:
    d = ffprobe(path)
    if d is None:
        return {"file": path.name, "path": str(path), "alerts": ["ILEGÍVEL"]}
    fmt = d.get("format") or {}
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    alerts = []
    if v is None:
        return {"file": path.name, "path": str(path), "alerts": ["SEM VÍDEO"]}
    r_fps, avg_fps = rate(v.get("r_frame_rate")), rate(v.get("avg_frame_rate"))
    jitter, n = frame_jitter(path)
    vfr = (jitter > VFR_JITTER) or (r_fps and avg_fps and abs(r_fps - avg_fps) / r_fps > 0.01)
    if vfr:
        alerts.append(f"VFR (variação {jitter * 100:.0f}% em {n} frames; r={r_fps:.3f} avg={avg_fps:.3f})")
    if a is None:
        alerts.append("SEM ÁUDIO")
    return {
        "file": path.name, "path": str(path),
        "created": created(fmt, v),
        "duration_s": round(float(fmt.get("duration") or 0), 2),
        "size": f"{v.get('width')}x{v.get('height')}",
        "fps": round(avg_fps or r_fps, 3), "vfr": bool(vfr),
        "codec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "color": "/".join(str(v.get(k) or "?") for k in ("color_primaries", "color_transfer")),
        "audio": f"{a.get('codec_name')} {a.get('sample_rate')}Hz {a.get('channels')}ch" if a else None,
        "alerts": alerts,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    files: list[Path] = []
    for p in a.paths:
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in EXTS and f.is_file())
        elif p.is_file():
            files.append(p)
    if not files:
        sys.exit("nenhum vídeo encontrado")
    rows = [probe(f) for f in files]
    # ordem de gravação: com data primeiro (cronológica), sem data depois (pelo nome)
    rows.sort(key=lambda r: (r.get("created") is None, r.get("created") or "", r["file"]))
    fps_set = {r["fps"] for r in rows if r.get("fps")}
    # Compara a taxa NOMINAL: 29,993 e 29,999 (celular) são o mesmo 30; 29,97 e 30
    # não são — a diferença de 0,1% vira descompasso crescente no fim do vídeo.
    mixed = len({nominal(f) for f in fps_set}) > 1
    if a.json:
        print(json.dumps({"sources": rows, "mixed_fps": mixed}, ensure_ascii=False, indent=1))
        return
    for i, r in enumerate(rows, 1):
        if "duration_s" not in r:
            print(f"{i:02d}. {r['file']}  ⚠ {', '.join(r['alerts'])}")
            continue
        when = r["created"] or "sem data (ordem pelo nome)"
        print(f"{i:02d}. {r['file']}  {r['duration_s']}s  {r['size']}  {r['fps']}fps  {r['codec']}"
              f"  cor {r['color']}  áudio {r['audio'] or '—'}  gravado {when}")
        for al in r["alerts"]:
            print(f"      ⚠ {al}")
    if mixed:
        print(f"⚠ FPS MISTO entre as fontes: {sorted(fps_set)} — o render usa uma taxa só; confira o resultado")
    if any(r.get("vfr") for r in rows):
        print("⚠ Fonte VFR: converta para CFR antes do corte (ex.: ffmpeg -fps_mode cfr -r <fps>) ou "
              "confira o sync no render — os tempos da transcrição e os do vídeo podem divergir")


if __name__ == "__main__":
    main()
