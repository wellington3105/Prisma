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

O cliente é o que o USUÁRIO diz ("esse é da Deocar"), nunca deduzido de pasta,
placa, logo ou nome do projeto. `set` grava no state.json; daí em diante
`seed`/`learn` com outro nome são recusados.

Uso:
    uv run python helpers/client_profile.py set <edit> <cliente>               # quando o usuário diz de quem é
    uv run python helpers/client_profile.py learn <cliente> --from <edit>      # depois da aprovação
    uv run python helpers/client_profile.py seed <cliente> <edit>             # antes do gate de Estilo
    uv run python helpers/client_profile.py rule <cliente> --text "zoom nos cortes ≤ 1.10" --origin "pedido em 03/11, Cayenne"
    uv run python helpers/client_profile.py show <cliente>
    uv run python helpers/client_profile.py list                              # com o estado do backup
    uv run python helpers/client_profile.py backup [<cliente>]                # força uma cópia agora
    uv run python helpers/client_profile.py restore <cliente> [--version arquivo] [--force]

Backup: `perfis/` fica fora do git (dado de cliente; o repositório é público).
Toda gravação (`learn`, `rule`) copia o perfil para `<backup>/<cliente>/profile.json`
e guarda a versão anterior em `<backup>/<cliente>/historico/` (as 50 últimas).
`<backup>` = $PRISMA_PERFIS_BACKUP, senão `$OneDrive/Prisma/perfis-backup`
(privado e sincronizado). `PRISMA_PERFIS_BACKUP=off` desliga. Uma falha no
backup avisa e não impede a gravação do perfil.
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
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERFIS = Path(os.environ.get("PRISMA_PERFIS") or ROOT / "perfis")
HISTORY_KEEP = 50


def backup_root() -> Path | None:
    v = os.environ.get("PRISMA_PERFIS_BACKUP", "").strip()
    if v.lower() == "off":
        return None
    if v:
        return Path(v)
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    return Path(od) / "Prisma" / "perfis-backup" if od else None


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
    backup(cliente)
    return p


def backup(cliente: str, quiet: bool = False) -> Path | None:
    """Copia o perfil para o backup; a versão que estava lá vai para historico/.

    Nunca derruba a gravação: um erro aqui (OneDrive fora, disco cheio) vira aviso."""
    src, root = ppath(cliente), backup_root()
    if root is None:
        if not quiet:
            print("  aviso: perfil SEM backup (defina PRISMA_PERFIS_BACKUP ou o OneDrive)", file=sys.stderr)
        return None
    try:
        dst = root / slug(cliente) / "profile.json"
        hist = dst.parent / "historico"
        hist.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.read_bytes() == src.read_bytes():
                return dst
            shutil.copy2(dst, hist / f"profile-{time.strftime('%Y%m%d-%H%M%S')}.json")
            for old in sorted(hist.glob("profile-*.json"))[:-HISTORY_KEEP]:
                old.unlink()
        shutil.copy2(src, dst)
        if not quiet:
            print(f"  backup: {dst}", file=sys.stderr)
        return dst
    except OSError as e:
        print(f"  aviso: backup do perfil '{cliente}' falhou ({e}); o perfil local foi gravado", file=sys.stderr)
        return None


def backup_state(cliente: str) -> str:
    root = backup_root()
    if root is None:
        return "SEM backup"
    dst = root / slug(cliente) / "profile.json"
    if not dst.exists():
        return "SEM backup"
    return "backup ok" if dst.read_bytes() == ppath(cliente).read_bytes() else "backup DESATUALIZADO"


def restore(cliente: str, version: Path | None, force: bool) -> Path:
    root = backup_root()
    if version is None:
        if root is None:
            sys.exit("sem pasta de backup (PRISMA_PERFIS_BACKUP / OneDrive)")
        version = root / slug(cliente) / "profile.json"
    if not version.exists():
        sys.exit(f"não há backup em {version}")
    json.loads(version.read_text(encoding="utf-8"))          # recusa um arquivo corrompido
    dst = ppath(cliente)
    if dst.exists() and dst.read_bytes() != version.read_bytes():
        if not force:
            sys.exit(f"o perfil local '{cliente}' é diferente do backup; para substituí-lo use --force "
                     "(o local é guardado ao lado como .antes-restore-<data>)")
        shutil.copy2(dst, dst.with_name(f"profile.antes-restore-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(version, dst)
    return dst


def project_name(edit: Path) -> str:
    try:
        st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        if st.get("project"):
            return st["project"]
    except (OSError, json.JSONDecodeError):
        pass
    return f"{edit.parent.name}/{edit.name}"


def bind(edit: Path, cliente: str, force: bool = False) -> dict:
    """Grava no state.json de quem é o vídeo — o nome que o USUÁRIO disse.

    O cliente nunca é deduzido (pasta, placa, logo, nome do projeto): no PPF X6 a
    placa dizia DEOCAR e a pasta "PPF X6", e nenhum dos dois é o usuário dizendo.
    Uma vez gravado, `seed` e `learn` com outro nome são recusados — o perfil
    errado contaminaria o próximo vídeo do cliente certo."""
    sp = edit / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    if st.get("client") and slug(st["client"]) != slug(cliente) and not force:
        sys.exit(f"este projeto é do cliente '{st['client']}' (dito pelo usuário), não de "
                 f"'{cliente}' — se o usuário mandou trocar, use `set … --force`")
    st["client"] = cliente
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def learn(cliente: str, edit: Path) -> dict:
    prof = load(cliente, must=False)
    bind(edit, cliente)
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
    bind(edit, cliente)
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
    b = sub.add_parser("set"); b.add_argument("edit", type=Path); b.add_argument("cliente")
    b.add_argument("--force", action="store_true", help="trocar um cliente já gravado (só se o usuário mandou)")
    l = sub.add_parser("learn"); l.add_argument("cliente"); l.add_argument("--from", dest="src", type=Path, required=True)
    s = sub.add_parser("seed"); s.add_argument("cliente"); s.add_argument("edit", type=Path)
    r = sub.add_parser("rule"); r.add_argument("cliente"); r.add_argument("--text", required=True); r.add_argument("--origin", required=True)
    sh = sub.add_parser("show"); sh.add_argument("cliente")
    sub.add_parser("list")
    bk = sub.add_parser("backup"); bk.add_argument("cliente", nargs="?")
    rs = sub.add_parser("restore"); rs.add_argument("cliente")
    rs.add_argument("--version", type=Path, help="um arquivo de historico/ (padrão: o backup mais recente)")
    rs.add_argument("--force", action="store_true", help="substituir um perfil local diferente")
    a = ap.parse_args()
    if a.cmd == "set":
        bind(a.edit.resolve(), a.cliente, force=a.force)
        tem = ppath(a.cliente).exists()
        print(f"  {a.edit}: cliente = '{a.cliente}' (dito pelo usuário) · "
              + ("perfil existe → `seed` antes do Estilo" if tem else "sem perfil ainda → `learn` depois da aprovação"))
    elif a.cmd == "learn":
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
    elif a.cmd == "backup":
        names = [a.cliente] if a.cliente else [p.parent.name for p in sorted(PERFIS.glob("*/profile.json"))]
        for n in names:
            load(n)
            d = backup(n, quiet=True)
            print(f"  {n}: " + (f"backup → {d}" if d else "SEM backup (defina PRISMA_PERFIS_BACKUP ou o OneDrive)"))
    elif a.cmd == "restore":
        print(f"  perfil '{a.cliente}' restaurado → {restore(a.cliente, a.version, a.force)}")
    else:
        for p in sorted(PERFIS.glob("*/profile.json")) if PERFIS.exists() else []:
            prof = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {p.parent.name:<24} {prof.get('style_origin', '—')} · {len(prof.get('rules', []))} regra(s) · {backup_state(p.parent.name)}")


if __name__ == "__main__":
    main()
