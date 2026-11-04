"""Índice das bibliotecas de SFX — pico, duração útil, forma, brilho (F3.1).

Escolher um som pede números que nenhum manifesto tinha: um whoosh com pico em
0,4 s precisa começar 0,4 s antes do evento; o que resta até o próximo evento
limita a duração útil; um som "seco" e um "crescendo" servem a papéis diferentes;
e o celular não reproduz grave (medido no Prisma: `sub_drop` e `ui_tick`
somem no alto-falante). Este índice mede isso em todas as bibliotecas:

  - kit sintetizado (`sfx_cinema/`, gerado por sfx_synth.py), `public/sfx` dos
    templates, a biblioteca da skill `media-use` (reaproveita a descrição do
    `manifest.json` dela) e qualquer pasta passada (downloads do Epidemic);

  por arquivo: duração, silêncio no começo, **tempo até o pico**, duração útil,
  forma (seco | médio | crescendo | contínuo), alinhamento sugerido (start |
  peak | end), brilho (centroide → grave | médio | agudo) e quanto o pico CAI
  quando só sobra 150 Hz–8 kHz (o alto-falante do celular): toca bem (≥ −6 dB),
  perde corpo (até −15 dB), só o ataque (abaixo — o grave
  some; o nível do que sobra está em `phone_peak_dbfs`).

Uso:
    uv run python helpers/sfx_index.py build [pastas…] [-o sfx_index.json]
    uv run python helpers/sfx_index.py show [--grep whoosh] [--celular]
O índice fica em `<prisma>/sfx_index.json` (cache por data do arquivo).
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
import subprocess
from pathlib import Path

import numpy as np

SR = 48000
HOP = 0.005
FLOOR_DB = -40.0     # abaixo do pico: começo e fim "úteis" do som
EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "sfx_index.json"


def default_dirs() -> list[Path]:
    cands = [ROOT / "assets" / "shortform" / "public" / "sfx", ROOT / "assets" / "longform" / "public" / "sfx",
             ROOT.parent / "media-use" / "audio" / "assets" / "sfx", ROOT / "assets" / "sfx_cinema"]
    return [c for c in cands if c.is_dir()]


def analyze(path: Path) -> dict | None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32).astype(np.float64)
    if len(x) < int(0.02 * SR):
        return None
    n = int(HOP * SR)
    k = len(x) // n
    env = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1))
    # Sem média móvel: testada (20 ms), deslocou o som seco +10 ms e não fechou o
    # riser (−25 ms). Envelope cru: ±5 ms nos whooshes e no seco; o riser erra
    # ~20 ms no topo quase plano — e riser se alinha pelo FIM, não pelo pico.
    pk = int(np.argmax(env))
    db = 20 * np.log10(env / (env[pk] + 1e-12) + 1e-12)
    above = np.where(db > FLOOR_DB)[0]
    on, off = int(above[0]), int(above[-1])
    peak_s, onset_s = pk * HOP, on * HOP
    useful = (off - on + 1) * HOP
    rise = peak_s - onset_s
    top = float((db[on:off + 1] > -3.0).mean())   # fração do som a ≤ 3 dB do máximo
    if top > 0.4 and useful > 0.5:
        # som contínuo (ronco, cama): o "pico" é arbitrário — alinhe pelo início.
        # Medido: impact-bass-1.mp3 fica a 0–7 dB do máximo de 0,1 s a 2,0 s.
        shape, align = "contínuo", "start"
    elif rise <= 0.03:
        shape, align = "seco", "start"
    elif rise >= 0.4 * useful:
        # riser de verdade (subida longa) termina NO evento; um whip-hit também
        # sobe até o golpe, mas o golpe É o evento → peak (medido: whip_hit 0,30 s)
        riser = useful >= 1.0 and rise >= 0.7 * useful
        shape, align = "crescendo", "end" if riser else "peak"
    else:
        shape, align = "médio", "peak"
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    tot = spec.sum() + 1e-12
    centroid = float((f * spec).sum() / tot)
    # Celular: quanto o PICO cai quando só sobra 150 Hz–8 kHz (o que o
    # alto-falante toca). A fração de energia enganava — um impacto com muito sub
    # dava "0%" e ainda assim soava (impact.wav: cai 12 dB, audível; medido).
    sb = (f >= 150) & (f <= 8000)
    xb = np.fft.irfft(np.fft.rfft(x) * sb, n=len(x))
    eb = np.sqrt((xb[:k * n].reshape(k, n) ** 2).mean(1))
    phone_drop = float(20 * np.log10((eb.max() + 1e-12) / (env.max() + 1e-12)))
    # A queda mede o CARÁTER (quanto do som o alto-falante joga fora), não se ele
    # é ouvido: impact-bass-1 cai 21 dB, mas o que sobra está a −20 dBFS, no nível
    # de chime/click1, que tocam bem (medido 2026-11-03, D9). O nome antigo
    # "quase some" levou a uma conclusão errada — o grave some, o ataque fica.
    # Audibilidade é questão de mix: compare `phone_peak_dbfs` entre os sons.
    phone_peak = float(20 * np.log10(eb.max() + 1e-12))
    phone = "toca bem" if phone_drop >= -6 else ("perde corpo" if phone_drop >= -15 else "só o ataque")
    # Golpe com sub: o pico de banda cheia é o grave, mas o que se ouve primeiro
    # (e o que o celular toca) é o transiente. impact.wav: pico 0,05 s (sub),
    # pico na banda do celular 0,015 s → por "peak" soava 50 ms ANTES do evento
    # (medido no mix do beat_edit, D9). Se o pico audível está colado no início,
    # o som é seco no que importa: alinha pelo início.
    pb = int(np.argmax(eb))
    if align == "peak" and (pb - on) * HOP <= 0.03:
        shape, align = "seco", "start"
    bright = "grave" if centroid < 800 else ("agudo" if centroid > 3000 else "médio")
    return {"file": path.name, "path": str(path), "duration_s": round(len(x) / SR, 3),
            "onset_s": round(onset_s, 3), "peak_s": round(peak_s, 3), "useful_s": round(useful, 3),
            "shape": shape, "align": align, "centroid_hz": round(centroid), "brightness": bright,
            "phone_drop_db": round(phone_drop, 1), "phone_peak_dbfs": round(phone_peak, 1), "phone": phone, "phone_ok": phone_drop >= -15,
            "mtime": path.stat().st_mtime}


def descriptions(d: Path) -> dict:
    m = d / "manifest.json"
    try:
        man = json.loads(m.read_text(encoding="utf-8"))
        return {v.get("file"): v.get("description") for v in man.values() if isinstance(v, dict)}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def build(dirs: list[Path], out: Path) -> list[dict]:
    old = {}
    if out.exists():
        try:
            old = {e["path"]: e for e in json.loads(out.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError, KeyError):
            old = {}
    items = []
    for d in dirs:
        desc = descriptions(d)
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in EXTS:
                continue
            prev = old.get(str(p))
            # campo novo (phone_peak_dbfs, D9) → mede de novo as entradas antigas
            fresh = prev and "phone_peak_dbfs" in prev and abs(prev.get("mtime", 0) - p.stat().st_mtime) < 1
            e = prev if fresh else analyze(p)
            if not e:
                continue
            e["library"] = d.name if d.name != "sfx" else d.parent.parent.name
            if desc.get(p.name):
                e["description"] = desc[p.name]
            items.append(e)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("dirs", nargs="*", type=Path)
    b.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    s = sub.add_parser("show")
    s.add_argument("--grep")
    s.add_argument("--celular", action="store_true", help="só os que tocam no alto-falante do celular")
    s.add_argument("-i", "--index", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    if a.cmd == "build":
        dirs = default_dirs() + [d.resolve() for d in a.dirs if d.is_dir()]
        items = build(dirs, a.out)
        print(f"  {len(items)} sons de {len(dirs)} biblioteca(s) → {a.out}")
        return
    items = json.loads(a.index.read_text(encoding="utf-8"))
    for e in items:
        if a.grep and a.grep.lower() not in (e["file"] + " " + e.get("description", "")).lower():
            continue
        if a.celular and not e["phone_ok"]:
            continue
        print(f"  {e['file']:<26} pico {e['peak_s']:5.2f}s · útil {e['useful_s']:5.2f}s · {e['shape']:<9} · align {e.get('align'):<5} · "
              f"{e['brightness']:<5} · celular {e['phone']} ({e['phone_drop_db']:+.0f} dB, sobra {e.get('phone_peak_dbfs', float('nan')):.0f} dBFS) · {e['library']}")


if __name__ == "__main__":
    main()
