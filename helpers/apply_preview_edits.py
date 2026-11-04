"""Aplica no edl.json o corte que a pessoa salvou no preview — e TRAVA as bordas dela.

O preview grava `<edit>/preview_edits.json` com `edl.ranges` (a lista final, já
com splits, remoções e fusões), mas sem `quote`, `gain_db` nem `reason`. Aplicar
isso à mão tinha dois caminhos ruins, os dois medidos em 2026-11-03 numa cópia
do Cayenne reel_01:

  - trocar os ranges e manter o `quote` antigo → `refine_edges.py` reancorava a
    borda na palavra que a pessoa tinha cortado: 2 de 4 edições desfeitas em
    silêncio;
  - trocar os ranges pelos do preview → nada era desfeito, mas também nada era
    conferido, e `gain_db`/`reason` se perdiam.

Este helper faz o terceiro: cada range novo herda os campos do range original
de onde veio (mesma fonte, maior sobreposição), e toda borda que difere da
original ganha `"user_edges"`. O `refine_edges.py` nunca move borda travada —
só confere se ela corta palavra — e reescreve o `quote` a partir do áudio.

Uso:
    uv run python helpers/apply_preview_edits.py <edit_dir> [--dry-run]
    uv run python helpers/refine_edges.py <edit_dir>/edl.json   # confere as bordas
    render.py → verify_cut.py como sempre

Só aplica o bloco `edl`. `notes`, `editData` e o resto do preview_edits.json
continuam com o agente; apague o arquivo depois de tratar tudo.
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
import shutil
import sys
import time
from pathlib import Path

TOL = 0.002  # s — o preview arredonda para ms; abaixo disso a borda não mudou
CARRY = ("quote", "gain_db", "reason", "chapter", "beat")


def overlap(a: dict, b: dict) -> float:
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def origin_of(new: dict, originals: list[dict]) -> dict | None:
    same = [o for o in originals if o["source"] == new["source"]]
    if not same:
        return None
    best = max(same, key=lambda o: (overlap(new, o), o.get("beat") == new.get("beat")))
    return best if overlap(new, best) > 0 else None


def apply(edit: Path, dry: bool) -> None:
    edl_p, pe_p = edit / "edl.json", edit / "preview_edits.json"
    if not pe_p.exists():
        sys.exit(f"sem {pe_p.name} em {edit}")
    pe = json.loads(pe_p.read_text(encoding="utf-8"))
    block = pe.get("edl")
    if not block or not block.get("ranges"):
        print("preview_edits.json não traz mudança de corte (bloco `edl` vazio) — nada a aplicar")
        return
    edl = json.loads(edl_p.read_text(encoding="utf-8"))
    originals = edl["ranges"]

    out, report = [], []
    for n, nr in enumerate(block["ranges"]):
        o = origin_of(nr, originals)
        r = {"source": nr["source"], "start": round(float(nr["start"]), 3),
             "end": round(float(nr["end"]), 3)}
        locks = []
        if o is None:
            locks = ["start", "end"]
            if nr.get("beat"):
                r["beat"] = nr["beat"]
        else:
            for k in CARRY:
                if k in o:
                    r[k] = o[k]
            prev = set(o.get("user_edges") or [])
            for edge in ("start", "end"):
                if abs(r[edge] - o[edge]) > TOL or edge in prev:
                    locks.append(edge)
        if locks:
            r["user_edges"] = locks
        out.append(r)
        if o is None:
            report.append(f"  [{n:02d}] {r['source']} {r['start']:.3f}–{r['end']:.3f}  NOVO (sem original)  trava: {','.join(locks)}")
        elif locks:
            report.append(f"  [{n:02d}] {r['source']} {o['start']:.3f}–{o['end']:.3f} → "
                          f"{r['start']:.3f}–{r['end']:.3f}  trava: {','.join(locks)}")

    removed = block.get("removed") or []
    print(f"== {edit}\n  {len(originals)} ranges → {len(out)}  "
          f"({len(removed)} removidos, {block.get('splits', 0)} splits)")
    print("\n".join(report) if report else "  nenhuma borda mudou")

    if dry:
        print("  --dry-run: nada gravado")
        return
    bak = edit / "edl.before_preview.json"
    if bak.exists():
        bak = edit / f"edl.before_preview.{time.strftime('%Y%m%d-%H%M%S')}.json"
    shutil.copy2(edl_p, bak)
    edl["ranges"] = out
    edl.pop("jcut_timeline", None)  # posições antigas; render.py reescreve
    edl["total_duration_s"] = round(sum(x["end"] - x["start"] for x in out), 2)
    edl_p.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  gravado (backup: {bak.name}). Agora: refine_edges.py {edl_p} — confere as bordas travadas")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit_dir", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.edit_dir.resolve(), a.dry_run)


if __name__ == "__main__":
    main()
