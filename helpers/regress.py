"""Teste de regressão da Fase 1 — um clipe congelado, saídas esperadas, tolerância.

"Mudança que ninguém pediu é bug." Rode depois de mexer em qualquer helper da
Fase 1 (transcribe, refine_edges, render, verify_cut, speech_regions…). Ele
roda o pipeline inteiro numa pasta temporária sobre `tests/fixture/` e compara
com `tests/fixture/expected.json`:

  transcrição  · nº de palavras (±3%) e texto (similaridade ≥ 0,97)
  refine_edges · nº de ranges e cada borda (±30 ms)
  render       · duração do cut (±1 frame) e lead do J-cut por emenda
  verify_cut   · duration_ok, nº de flags, nº de junções, nível por range (±1 dB)
  loudness     · integrado do cut (±0,5 LU)

Uso:
    uv run python helpers/regress.py              # compara; exit 1 se algo mudou
    uv run python helpers/regress.py --update     # grava o esperado (só quando a
                                                  # mudança foi pedida e conferida)
    uv run python helpers/regress.py --keep       # não apaga a pasta de trabalho

O fixture é um recorte de 35 s (720p) de uma cópia do projeto Cayenne, com 9
ranges de `reel_01`. É material de cliente: uso local, não publique.
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixture"
CLIP = FIX / "cayenne_clip.mp4"
EDL_IN = FIX / "edl_input.json"
EXPECTED = FIX / "expected.json"

TOL_EDGE = 0.030
TOL_LU = 0.5
TOL_LEVEL_DB = 1.0
TOL_WORDS = 0.03
MIN_TEXT_SIM = 0.97


def run(step: str, args: list[str]) -> str:
    t0 = time.time()
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"[{step}] falhou (exit {r.returncode}):\n{(r.stderr or r.stdout)[-1500:]}")
    print(f"  {step:<14} ok ({time.time() - t0:.0f}s)", flush=True)
    return r.stdout


def loudness(path: Path) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "ebur128", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else float("nan")


def transcript_words(edit: Path) -> list[str]:
    d = json.loads(next((edit / "transcripts").glob("*.json")).read_text(encoding="utf-8"))
    ws = d.get("words") or [w for s in d.get("segments", []) for w in s.get("words", [])]
    out = []
    for w in ws:
        t = (w.get("text") or w.get("word") or "").strip().lower()
        t = re.sub(r"[^\w]", "", t)
        if t:
            out.append(t)
    return out


def measure(work: Path) -> dict:
    clip = work / "clip.mp4"
    edit = work / "edit"
    edit.mkdir(parents=True)
    shutil.copy2(CLIP, clip)
    edl = json.loads(EDL_IN.read_text(encoding="utf-8"))
    edl["sources"] = {"clip": str(clip)}
    (edit / "edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    H = ROOT / "helpers"
    run("transcribe", [str(H / "transcribe.py"), str(clip), "--edit-dir", str(edit), "--language", "pt"])
    run("refine_edges", [str(H / "refine_edges.py"), str(edit / "edl.json"), "--language", "pt"])
    run("render", [str(H / "render.py"), str(edit / "edl.json"), "-o", str(edit / "cut.mp4"), "--no-subtitles"])
    vj = json.loads(run("verify_cut", [str(H / "verify_cut.py"), str(edit / "edl.json"),
                                       str(edit / "cut.mp4"), "--json"]))
    refined = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    words = transcript_words(edit)
    return {
        "words": len(words),
        "text": " ".join(words),
        "ranges": [[r["start"], r["end"]] for r in refined["ranges"]],
        "jcut_leads": [t.get("lead_frames") for t in refined.get("jcut_timeline") or []],
        # [planejado, real] por take — o plano só é verdade se forem iguais (F0.2)
        "jcut_frames": [[round(t["video_duration"] * (refined.get("fps") or 30)), t.get("video_frames")]
                        for t in refined.get("jcut_timeline") or []],
        "cut_s": vj.get("actual_s"),
        "duration_ok": vj.get("duration_ok"),
        "flags": vj.get("flags"),
        "junctions": len(vj.get("junctions") or []),
        "range_levels": [x.get("delta_db") for x in vj.get("range_levels") or []],
        "lufs": round(loudness(edit / "cut.mp4"), 2),
        "fps": refined.get("fps") or 30,
    }


def compare(got: dict, exp: dict) -> list[tuple[str, bool, str]]:
    res = []
    dw = abs(got["words"] - exp["words"]) / max(1, exp["words"])
    res.append(("transcrição: nº de palavras", dw <= TOL_WORDS, f"{got['words']} vs {exp['words']}"))
    sim = difflib.SequenceMatcher(None, got["text"].split(), exp["text"].split()).ratio()
    res.append(("transcrição: texto", sim >= MIN_TEXT_SIM, f"similaridade {sim:.3f}"))
    same_n = len(got["ranges"]) == len(exp["ranges"])
    res.append(("refine: nº de ranges", same_n, f"{len(got['ranges'])} vs {len(exp['ranges'])}"))
    if same_n:
        worst = max((abs(a - b) for g, e in zip(got["ranges"], exp["ranges"]) for a, b in zip(g, e)), default=0)
        bad = [f"[{i:02d}] {g[0]:.3f}–{g[1]:.3f} (era {e[0]:.3f}–{e[1]:.3f})"
               for i, (g, e) in enumerate(zip(got["ranges"], exp["ranges"]))
               if max(abs(g[0] - e[0]), abs(g[1] - e[1])) > TOL_EDGE]
        res.append(("refine: bordas", not bad, f"pior desvio {worst * 1000:.0f} ms" + ("; " + "; ".join(bad[:3]) if bad else "")))
    res.append(("render: lead do J-cut", got["jcut_leads"] == exp["jcut_leads"], f"{got['jcut_leads']} vs {exp['jcut_leads']}"))
    # Absoluta (não compara com o esperado): cada take com exatamente os frames
    # do plano. Um +1 aqui é a imagem atrasando em relação à voz em todos os
    # takes seguintes — medido no Cayenne reel_01: 300 ms no take 27 (F0.2).
    off = [i + 1 for i, (p, g) in enumerate(got.get("jcut_frames") or []) if g != p]
    res.append(("render: frames = plano (sync)", not off and bool(got.get("jcut_frames")),
                f"takes fora do plano: {off}" if off else f"{len(got.get('jcut_frames') or [])} takes exatos"))
    frame = 1.0 / (exp.get("fps") or 30)
    ok_d = got["cut_s"] is not None and abs(got["cut_s"] - exp["cut_s"]) <= frame + 0.01
    res.append(("render: duração", ok_d, f"{got['cut_s']} s vs {exp['cut_s']} s"))
    res.append(("verify: duration_ok", got["duration_ok"] == exp["duration_ok"], str(got["duration_ok"])))
    res.append(("verify: flags", got["flags"] == exp["flags"], f"{got['flags']} vs {exp['flags']}"))
    res.append(("verify: junções", got["junctions"] == exp["junctions"], f"{got['junctions']} vs {exp['junctions']}"))
    lv_ok = len(got["range_levels"]) == len(exp["range_levels"]) and all(
        abs(a - b) <= TOL_LEVEL_DB for a, b in zip(got["range_levels"], exp["range_levels"]))
    res.append(("verify: nível por range", lv_ok, f"{got['range_levels']}"))
    res.append(("loudness integrado", abs(got["lufs"] - exp["lufs"]) <= TOL_LU, f"{got['lufs']} vs {exp['lufs']} LUFS"))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="grava o resultado como esperado")
    ap.add_argument("--keep", action="store_true", help="não apaga a pasta de trabalho")
    a = ap.parse_args()
    if not CLIP.exists() or not EDL_IN.exists():
        sys.exit(f"fixture ausente em {FIX}")
    # Poka-Yoke: os helpers rodam com helpers/ no início do sys.path, então um
    # helper com nome de módulo da stdlib SOMBREIA a stdlib. Medido 2026-11-03:
    # um `profile.py` quebrou o cProfile → transformers → a transcrição inteira.
    clash = sorted(p.stem for p in (ROOT / "helpers").glob("*.py")
                   if p.stem in getattr(sys, "stdlib_module_names", ()))
    if clash:
        sys.exit(f"FAIL  helpers com nome de módulo da stdlib (sombreiam a stdlib): {', '.join(clash)} — renomeie")
    work = Path(tempfile.mkdtemp(prefix="prisma-regress-"))
    print(f"== regressão Fase 1 · trabalho em {work}")
    try:
        got = measure(work)
        if a.update:
            EXPECTED.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  esperado gravado em {EXPECTED}")
            return
        if not EXPECTED.exists():
            sys.exit("sem expected.json — rode uma vez com --update num Prisma conferido")
        res = compare(got, json.loads(EXPECTED.read_text(encoding="utf-8")))
        for name, ok, info in res:
            print(f"  {'PASS' if ok else 'FAIL'}  {name:<28} {info}")
        fails = sum(1 for _, ok, _ in res if not ok)
        print(f"== {len(res) - fails}/{len(res)} ok" + (f" — {fails} FALHA(S): mudança que ninguém pediu?" if fails else ""))
        sys.exit(1 if fails else 0)
    finally:
        if a.keep:
            print(f"  pasta mantida: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
