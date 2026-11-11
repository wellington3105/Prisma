"""Hesitações ("ééé", "hum", "hã") — achar pelo ÁUDIO, não pelo texto (F4.3).

O WhisperX costuma não escrever a hesitação: medido 2026-11-03 num clipe pt-BR
com três hesitações conhecidas, um "éééé" de ~2 s sumiu dentro da palavra
anterior, que ficou esticada de 1,55 s a 5,74 s ("Cayenne."). Pelo texto não
havia nada a cortar. Este helper olha o áudio:

  1. trechos de VOZ (faixa 250–3500 Hz, acima do piso local + 6 dB) e se são
     VOZEADOS (tom: autocorrelação na faixa de 80–400 Hz) — respiração e ruído
     não são hesitação;
  2. um trecho de voz que não é de nenhuma palavra — ou que cai DENTRO de uma
     palavra que já tem o seu próprio trecho (palavra esticada) — é hesitação
     não transcrita;
  3. palavra transcrita que é muleta ("é", "hum", "hã", "ã", "eh", "ahn", "hmm").

Regra de decisão (fluxo-de-edicao, etapa cortes, MIT): só é CANDIDATA A CORTE a
hesitação isolada por silêncio dos dois lados e longa; a colada na fala fica, e
vira marcador para a pessoa julgar — pela transcrição não dá para saber se o
corte ficaria estranho.

Uso:
    uv run python helpers/hesitations.py <video> --edit-dir <edit> [--markers] [--json]
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
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

SR = 16000
HOP = 0.010
ABOVE_FLOOR_DB = 6.0
MIN_REGION = 0.12      # s de voz contínua para valer como trecho
MERGE_GAP = 0.15       # buracos menores que isto são dentro da mesma fala
ISOLATED_GAP = 0.25    # silêncio dos dois lados para ser "isolada"
LONG = 0.35            # duração mínima para ser candidata a corte
VOICED = 0.45          # força mínima de tom (autocorrelação normalizada)
FILLERS = {"e", "ee", "eee", "eh", "hum", "humm", "hmm", "hm", "ha", "haa", "a", "aa", "aaa", "ahn", "an", "um", "uhm"}
# Palavras de verdade em português ("é" verbo, "a" artigo, "um" numeral): só são
# hesitação se ALONGADAS ou isoladas por pausa. Medido 2026-11-03: um "é," colado
# ("…do mundo, é, eu falo") era o "né" da fala, não hesitação.
AMBIGUOUS = {"e", "a", "um"}
AMBIGUOUS_MIN = 0.45


def norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    return re.sub(r"[^a-z]", "", "".join(c for c in w if not unicodedata.combining(c)))


def pcm(path: Path, band: bool) -> np.ndarray:
    af = ["-af", "highpass=f=250,highpass=f=250,lowpass=f=3500"] if band else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), *af, "-ac", "1", "-ar", str(SR),
                        "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def regions(env_db: np.ndarray) -> list[tuple[float, float]]:
    # Piso pelos quadros com som de verdade: silêncio DIGITAL (−180 dB, áudio
    # sintético ou editado) jogava o piso lá embaixo e frases inteiras viravam um
    # trecho só (medido 2026-11-03). E nunca mais de 30 dB abaixo da fala.
    act = env_db[env_db > -100]
    if not len(act):
        return []
    thr = max(float(np.percentile(act, 15)) + ABOVE_FLOOR_DB, float(np.percentile(act, 90)) - 30.0)
    on = env_db > thr
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            out.append([i * HOP, j * HOP])
            i = j
        else:
            i += 1
    merged = []
    for s, e in out:
        if merged and s - merged[-1][1] < MERGE_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if e - s >= MIN_REGION]


def voicing(x: np.ndarray, s: float, e: float) -> float:
    """Mediana da força de tom em quadros de 40 ms (0 = ruído, 1 = tom puro)."""
    seg = x[int(s * SR):int(e * SR)]
    n = int(0.04 * SR)
    lo, hi = int(SR / 400), int(SR / 80)
    vals = []
    for k in range(0, len(seg) - n, n // 2):
        f = seg[k:k + n] - seg[k:k + n].mean()
        den = float((f * f).sum())
        if den < 1e-9:
            continue
        ac = np.correlate(f, f, "full")[n - 1:]
        vals.append(float(ac[lo:hi].max() / den))
    return float(np.median(vals)) if vals else 0.0


def detect(video: Path, words: list[dict]) -> list[dict]:
    band = pcm(video, True)
    full = pcm(video, False)
    k = len(band) // int(HOP * SR)
    env = 20 * np.log10(np.sqrt((band[:k * int(HOP * SR)].reshape(k, -1) ** 2).mean(1)) + 1e-9)
    regs = regions(env)
    ov = lambda a, b: max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    # Cada palavra é dona do trecho onde COMEÇA — o Whisper estica o fim da
    # palavra por cima do silêncio (e da hesitação), não o início. Por maior
    # sobreposição, "Cayenne." esticada até 5,74 s ficava dona do "ééé" e ele
    # sumia (medido 2026-11-03).
    owned = set()
    for w in words:
        if norm(w["raw"]) in FILLERS:
            continue
        own = next((i for i, r in enumerate(regs) if r[0] - 0.15 <= w["s"] <= r[1]), None)
        if own is None:  # começa no silêncio: o primeiro trecho logo depois
            own = next((i for i, r in enumerate(regs) if 0 <= r[0] - w["s"] <= 0.30), None)
        if own is not None:
            owned.add(own)
    cands = []
    for i, r in enumerate(regs):
        if i in owned:
            continue
        hit = [w for w in words if ov(r, (w["s"], w["e"])) > 0]
        filler = [w for w in hit if norm(w["raw"]) in FILLERS]
        if hit and not filler and all(norm(w["raw"]) not in FILLERS for w in hit):
            # cai numa palavra que já tem trecho próprio → palavra esticada por cima de outra coisa
            kind = f"não transcrita (dentro de \"{hit[0]['raw']}\" esticada)"
        elif filler:
            kind = f"muleta transcrita \"{filler[0]['raw']}\""
        else:
            kind = "não transcrita"
        v = voicing(full, *r)
        if v < VOICED:
            continue  # respiração, estalo, ruído
        prev_e = max((x[1] for x in regs if x[1] <= r[0] + 1e-6 and x != r), default=None)
        next_s = min((x[0] for x in regs if x[0] >= r[1] - 1e-6 and x != r), default=None)
        gap_b = r[0] - prev_e if prev_e is not None else 9.9
        gap_a = next_s - r[1] if next_s is not None else 9.9
        isolated = gap_b >= ISOLATED_GAP and gap_a >= ISOLATED_GAP
        dur = r[1] - r[0]
        if filler and all(norm(w["raw"]) in AMBIGUOUS for w in filler) \
                and not isolated and dur < AMBIGUOUS_MIN:
            continue  # "é"/"a"/"um" curto e colado: palavra da frase, não hesitação
        cands.append({"start": round(r[0], 3), "end": round(r[1], 3), "dur": round(dur, 2),
                      "kind": kind, "voicing": round(v, 2), "isolated": isolated,
                      "gap_before": round(gap_b, 2), "gap_after": round(gap_a, 2),
                      "cut_candidate": isolated and dur >= LONG})
    return cands


def load_words(edit: Path, stem: str) -> list[dict]:
    d = json.loads((edit / "transcripts" / f"{stem}.json").read_text(encoding="utf-8"))
    ws = d.get("words") if isinstance(d, dict) else d
    return [{"raw": (w.get("text") or "").strip(), "s": float(w["start"]), "e": float(w["end"])}
            for w in ws or [] if w.get("type", "word") == "word" and w.get("start") is not None]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--markers", action="store_true", help="grava marcadores do Claude (preview)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    video, edit = a.video.resolve(), a.edit_dir.resolve()
    cands = detect(video, load_words(edit, video.stem))
    if a.json:
        print(json.dumps(cands, ensure_ascii=False, indent=1))
    else:
        for c in cands:
            verdict = "CANDIDATA A CORTE (isolada e longa)" if c["cut_candidate"] else \
                      ("isolada, curta — manter" if c["isolated"] else "colada na fala — manter e marcar")
            print(f"  {c['start']:7.2f}–{c['end']:7.2f}s ({c['dur']:.2f}s) {c['kind']} · tom {c['voicing']} · {verdict}")
        print(f"  {len(cands)} hesitação(ões), {sum(c['cut_candidate'] for c in cands)} candidata(s) a corte")
    if a.markers:
        import agent_markers
        agent_markers.clear(edit, "hesitacao")
        for c in cands:
            txt = ("isolada e longa — candidata a corte" if c["cut_candidate"] else "colada/curta — mantida; julgue ouvindo") + f" ({c['kind']})"
            agent_markers.add(edit, video.stem, c["start"], "hesitacao", txt, c["end"])


if __name__ == "__main__":
    main()
