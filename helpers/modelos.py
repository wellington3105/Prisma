#!/usr/bin/env python3
"""modelos.py: the editing-models library (named editing types and styles).

  python helpers/modelos.py list [--nivel tipo|estilo] [--familia F]
  python helpers/modelos.py show <slug>
  python helpers/modelos.py check

A *tipo* is one technique (whip pan, speed ramp, zoom punch…); an *estilo* combines tipos with
rules (max 3 accent transitions, a primary transition). Recipes live in `modelos/`; see
`modelos/README.md` and docs/superpowers/specs/2026-11-22-biblioteca-modelos-design.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modelos_receitas as R  # noqa: E402


def _primeira_linha(m: R.Modelo, secao: str) -> str:
    txt = (m.pasta / "MODELO.md").read_text(encoding="utf-8") if (m.pasta / "MODELO.md").exists() else ""
    if secao not in txt:
        return ""
    corpo = txt.split(secao, 1)[1].split("\n## ", 1)[0]
    return next((l.strip() for l in corpo.splitlines() if l.strip()), "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--nivel", choices=["tipo", "estilo"])
    ls.add_argument("--familia")
    sh = sub.add_parser("show")
    sh.add_argument("slug")
    sub.add_parser("check")
    a = ap.parse_args()

    if a.cmd == "list":
        for slug, m in sorted(R.load_all().items(), key=lambda kv: (kv[1].nivel, kv[1].familia, kv[0])):
            if (a.nivel and m.nivel != a.nivel) or (a.familia and m.familia != a.familia):
                continue
            print(f"  {m.nivel:<6} {m.familia:<12} {slug:<24} {_primeira_linha(m, '## O que é')[:70]}")
    elif a.cmd == "show":
        m = R.load(a.slug)
        print((m.pasta / "MODELO.md").read_text(encoding="utf-8"))
        print("receita:", json.dumps(m.dados, ensure_ascii=False, indent=1))
    else:
        probs = R.check()
        for p in probs:
            print("  problema:", p)
        print(f"  {len(R.load_all())} modelos, {len(probs)} problemas")
        return 1 if probs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
