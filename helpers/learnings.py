"""Caderno de aprendizados — o que uma revisão ensina para os PRÓXIMOS vídeos (F5.2).

Durante a revisão de qualquer fase, toda correção, elogio ou preferência que
vale para outros vídeos vira uma linha no caderno do projeto, na hora:

    - [ ] <fase> · <o que foi pedido, com contexto> · <dd/mm>

"Tira essa frase" é só deste vídeo: não entra. Na dúvida, entra com
"(talvez só deste vídeo)". **Anotar não é mudar**: a skill e o perfil só mudam
quando a pessoa pede ("aplica os aprendizados") — o agente propõe o destino de
cada linha (gosto → perfil do cliente; ofício → a skill; o que vale para todas
as fases → SKILL.md), a pessoa filtra, e só o aprovado é gravado e marcado:

    - [x] … → <onde entrou>          aplicado
    - [-] … (só deste vídeo)         descartado

Linhas nunca são apagadas. Adaptado de `LeiteZ/fluxo-de-edicao`
(`guias/principios-do-fluxo.md` §6, MIT).

Arquivo: `<edit>/aprendizados.md`.

Uso:
    uv run python helpers/learnings.py add <edit> --phase cortes --text "zoom mais sutil" [--maybe]
    uv run python helpers/learnings.py list <edit> [--open]
    uv run python helpers/learnings.py list-all <pasta_de_videos>          # abertos em todos os projetos
    uv run python helpers/learnings.py mark <edit> 3 --to "perfis/x/profile.json · zoomCuts"
    uv run python helpers/learnings.py mark <edit> 4 --only-this-video
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import re
import sys
import time
from pathlib import Path

FILE = "aprendizados.md"
HEAD = ("# Aprendizados\n\nO que esta revisão ensinou para os próximos vídeos. Anotar não é mudar: "
        "aplique quando a pessoa pedir.\n\n")
LINE = re.compile(r"^- \[( |x|-)\] (.+)$")


def path_of(edit: Path) -> Path:
    return Path(edit) / FILE


def read(edit: Path) -> list[str]:
    p = path_of(edit)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def entries(edit: Path) -> list[tuple[int, str, str]]:
    """(nº 1-based entre as linhas de item, estado, texto)."""
    out = []
    for ln in read(edit):
        m = LINE.match(ln)
        if m:
            out.append((len(out) + 1, m.group(1), m.group(2)))
    return out


def add(edit: Path, phase: str, text: str, maybe: bool) -> int:
    p = path_of(edit)
    lines = read(edit) or HEAD.rstrip("\n").splitlines() + [""]
    body = f"{phase} · {text.strip()}{' (talvez só deste vídeo)' if maybe else ''} · {time.strftime('%d/%m')}"
    if any(LINE.match(ln) and body.split(' · ')[1] in ln for ln in lines):
        return -1  # já anotado
    lines.append(f"- [ ] {body}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(entries(edit))


def mark(edit: Path, n: int, to: str | None, only_this: bool) -> str:
    lines = read(edit)
    k = 0
    for i, ln in enumerate(lines):
        m = LINE.match(ln)
        if not m:
            continue
        k += 1
        if k != n:
            continue
        if m.group(1) != " ":
            sys.exit(f"a linha {n} já foi tratada: {ln}")
        txt = m.group(2)
        lines[i] = f"- [-] {txt} (só deste vídeo)" if only_this else f"- [x] {txt} → {to}"
        path_of(edit).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return lines[i]
    sys.exit(f"não há linha {n}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("edit", type=Path)
    a.add_argument("--phase", required=True); a.add_argument("--text", required=True)
    a.add_argument("--maybe", action="store_true")
    l = sub.add_parser("list"); l.add_argument("edit", type=Path); l.add_argument("--open", action="store_true")
    la = sub.add_parser("list-all"); la.add_argument("root", type=Path)
    m = sub.add_parser("mark"); m.add_argument("edit", type=Path); m.add_argument("n", type=int)
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("--to"); g.add_argument("--only-this-video", action="store_true")
    args = ap.parse_args()
    if args.cmd == "add":
        n = add(args.edit, args.phase, args.text, args.maybe)
        print("  já estava anotado" if n < 0 else f"  + linha {n}")
    elif args.cmd == "list":
        es = entries(args.edit)
        for n, st, txt in es:
            if args.open and st != " ":
                continue
            print(f"  {n:>2}. [{st}] {txt}")
        print(f"  {sum(1 for e in es if e[1] == ' ')} aberto(s) de {len(es)}")
    elif args.cmd == "list-all":
        total = 0
        for p in sorted(args.root.rglob(FILE)):
            opn = [e for e in entries(p.parent) if e[1] == " "]
            if opn:
                print(f"== {p.parent}")
                for n, _, txt in opn:
                    print(f"  {n:>2}. {txt}")
                total += len(opn)
        print(f"  {total} aprendizado(s) aberto(s)")
    else:
        print("  " + mark(args.edit, args.n, args.to, args.only_this_video))


if __name__ == "__main__":
    main()
