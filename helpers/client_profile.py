"""Perfil por cliente — o gosto aprovado que o próximo projeto já herda (F5.1).

(Nome `client_profile.py`, não `profile.py`: os helpers rodam com `helpers/` no
início do sys.path, e `profile` é módulo da biblioteca padrão — a primeira
versão sombreou o `cProfile` e quebrou o import do transformers na transcrição.
Medido 2026-11-03 pela regressão.)

Até aqui o gate de Estilo abria nos padrões a cada projeto, e a pessoa refazia
as mesmas escolhas (medido 2026-11-03: os 4 reels do Cayenne têm o MESMO estilo —
split, título misto, legenda scatter, acento #ff5200 — escolhido 4 vezes). O
perfil guarda o que foi APROVADO num projeto, com a origem de cada coisa, e o
próximo projeto do mesmo cliente abre o gate já preenchido, dizendo de onde
veio. Gosto fica aqui; ofício fica na skill (fluxo-de-edicao,
`guias/principios-do-fluxo.md` §7, MIT).

Arquivo: `<prisma>/perfis/<cliente>/profile.json`
    {"cliente", "style", "style_origin", "grade", "grade_origin",
     "rules": [{"text", "origin"}], "history": [...]}

Uso:
    uv run python helpers/client_profile.py learn <cliente> --from <edit>      # depois da aprovação
    uv run python helpers/client_profile.py seed <cliente> <edit>             # antes do gate de Estilo
    uv run python helpers/client_profile.py rule <cliente> --text "zoom nos cortes ≤ 1.10" --origin "pedido em 03/11, Cayenne"
    uv run python helpers/client_profile.py show <cliente>
    uv run python helpers/client_profile.py list
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
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERFIS = ROOT / "perfis"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s:
        sys.exit("nome de cliente vazio")
    return s


def ppath(cliente: str) -> Path:
    return PERFIS / slug(cliente) / "profile.json"


def load(cliente: str, must: bool = True) -> dict:
    p = ppath(cliente)
    if not p.exists():
        if must:
            sys.exit(f"perfil '{cliente}' não existe ({p}) — crie com `learn` depois de um projeto aprovado")
        return {"cliente": cliente, "rules": [], "history": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save(cliente: str, prof: dict) -> Path:
    p = ppath(cliente)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def project_name(edit: Path) -> str:
    try:
        st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        if st.get("project"):
            return st["project"]
    except (OSError, json.JSONDecodeError):
        pass
    return f"{edit.parent.name}/{edit.name}"


def learn(cliente: str, edit: Path) -> dict:
    prof = load(cliente, must=False)
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    style = st.get("style")
    if not style:
        sys.exit("o state.json deste projeto não tem `style` — o gate de Estilo não foi aprovado")
    when = time.strftime("%d/%m/%Y")
    origin = f"aprovado em {project_name(edit)} em {when}"
    prof["style"], prof["style_origin"] = style, origin
    try:
        grade = json.loads((edit / "edl.json").read_text(encoding="utf-8")).get("grade")
        if grade is not None:
            prof["grade"], prof["grade_origin"] = grade, origin
    except (OSError, json.JSONDecodeError):
        pass
    prof.setdefault("history", []).append({"when": when, "from": str(edit), "what": "style + grade"})
    save(cliente, prof)
    return prof


def seed(cliente: str, edit: Path) -> dict:
    prof = load(cliente)
    if not prof.get("style"):
        sys.exit(f"o perfil '{cliente}' ainda não tem estilo")
    sp = edit / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    if st.get("style") and st["style"] != prof["style"]:
        sys.exit("este projeto já tem um estilo escolhido diferente do perfil — não sobrescrevo; "
                 "apague `style` do state.json se quiser recomeçar pelo perfil")
    st["style"] = prof["style"]
    st["awaitingStyle"] = True
    st["styleOrigin"] = f"perfil {cliente} · {prof.get('style_origin', '')}"
    st["message"] = f"Estilo pré-preenchido do perfil '{cliente}' ({prof.get('style_origin', 'origem não registrada')}) — confira e salve"
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("learn"); l.add_argument("cliente"); l.add_argument("--from", dest="src", type=Path, required=True)
    s = sub.add_parser("seed"); s.add_argument("cliente"); s.add_argument("edit", type=Path)
    r = sub.add_parser("rule"); r.add_argument("cliente"); r.add_argument("--text", required=True); r.add_argument("--origin", required=True)
    sh = sub.add_parser("show"); sh.add_argument("cliente")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "learn":
        prof = learn(a.cliente, a.src.resolve())
        print(f"  perfil '{a.cliente}': estilo {json.dumps(prof['style'], ensure_ascii=False)[:120]}…\n  origem: {prof['style_origin']}\n  → {ppath(a.cliente)}")
    elif a.cmd == "seed":
        st = seed(a.cliente, a.edit.resolve())
        print(f"  {a.edit}: state.style ← perfil '{a.cliente}' · awaitingStyle · \"{st['message']}\"")
    elif a.cmd == "rule":
        prof = load(a.cliente, must=False)
        prof.setdefault("rules", []).append({"text": a.text, "origin": a.origin})
        save(a.cliente, prof)
        print(f"  + regra em '{a.cliente}': {a.text} ({a.origin})")
    elif a.cmd == "show":
        print(json.dumps(load(a.cliente), ensure_ascii=False, indent=1))
    else:
        for p in sorted(PERFIS.glob("*/profile.json")) if PERFIS.exists() else []:
            prof = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {p.parent.name:<24} {prof.get('style_origin', '—')} · {len(prof.get('rules', []))} regra(s)")


if __name__ == "__main__":
    main()
