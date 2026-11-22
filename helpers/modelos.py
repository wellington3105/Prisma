#!/usr/bin/env python3
"""modelos.py: the editing-models library (named editing types and styles).

  python helpers/modelos.py list [--nivel tipo|estilo] [--familia F]
  python helpers/modelos.py show <slug>
  python helpers/modelos.py check
  python helpers/modelos.py apply <slug> <plan.json | edit dir> [--plano N ...] [--param k=v ...]
  python helpers/modelos.py material [--force]          # demo material, once (Pexels + Epidemic)
  python helpers/modelos.py demo <slug>|--all [--force]  # render demos into the gallery
  python helpers/modelos.py galeria [--abrir]           # build the gallery page

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
    apl = sub.add_parser("apply")
    apl.add_argument("slug")
    apl.add_argument("alvo", type=Path, help="plan.json do beat_edit, ou a pasta edit/ de um Reel de fala")
    apl.add_argument("--plano", type=int, nargs="+", help="índices dos planos (montagem) ou dos cortes (Reel de fala)")
    apl.add_argument("--param", action="append", default=[], help="k=v, ex.: dir=right")
    mt = sub.add_parser("material")
    mt.add_argument("--force", action="store_true")
    dm = sub.add_parser("demo")
    dm.add_argument("slug", nargs="?")
    dm.add_argument("--all", action="store_true")
    dm.add_argument("--force", action="store_true")
    gl = sub.add_parser("galeria")
    gl.add_argument("--abrir", action="store_true")
    a = ap.parse_args()

    if a.cmd == "list":
        for slug, m in sorted(R.load_all().items(), key=lambda kv: (kv[1].nivel, kv[1].familia, kv[0])):
            if (a.nivel and m.nivel != a.nivel) or (a.familia and m.familia != a.familia):
                continue
            import modelos_demo as D
            print(f"  {D.demo_status(slug)} {m.nivel:<6} {m.familia:<12} {slug:<24} {_primeira_linha(m, '## O que é')[:70]}")
    elif a.cmd == "show":
        m = R.load(a.slug)
        print((m.pasta / "MODELO.md").read_text(encoding="utf-8"))
        print("receita:", json.dumps(m.dados, ensure_ascii=False, indent=1))
    elif a.cmd == "apply":
        params = dict(p.split("=", 1) for p in a.param)
        bks = R.apply_file(a.slug, a.alvo, a.plano, params)
        print(f"  {a.slug} aplicado · backup: {', '.join(map(str, bks))}")
    elif a.cmd == "material":
        import modelos_demo as D
        mat = D.material(a.force)
        print(f"  material: {len(mat['clips'])} clipes, música {mat['music'].name}, beat inicial {mat['start_beat']}")
    elif a.cmd == "demo":
        import modelos_demo as D
        slugs = sorted(R.load_all()) if a.all else [a.slug]
        if not slugs or slugs == [None]:
            raise SystemExit("diga o modelo (demo <slug>) ou use --all")
        falhas = []
        for s in slugs:
            try:
                D.render_demo(s, a.force)
            except SystemExit as e:
                falhas.append(s)
                print(f"  {s}: {e}")
        if falhas:
            print(f"  sem demo: {', '.join(falhas)}")
            return 1
    elif a.cmd == "galeria":
        import modelos_demo as D
        page = D.build_galeria()
        print(f"  galeria: {page}")
        if a.abrir:
            print(f"  abrir: {page.as_uri()}")
    else:
        probs = R.check()
        for p in probs:
            print("  problema:", p)
        print(f"  {len(R.load_all())} modelos, {len(probs)} problemas")
        return 1 if probs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
