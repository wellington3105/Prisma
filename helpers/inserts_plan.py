"""Plano de inserts numerado — o gate entre o Estilo e o edit-data.json (F2.1).

Até aqui a Fase 2 ia do gate de Estilo direto para o `edit-data.json`, e um
conceito fraco só aparecia depois do render: mudar custava uma rodada inteira.
Agora cada insert é proposto como `i01…iNN` (tempo, formato, conceito numa
frase, palavra-gatilho, intenção da câmera; storyboard obrigatório no hook), a
pessoa aprova, risca ou ajusta POR NÚMERO, e só então o `edit-data.json` é
escrito — `apply` recusa enquanto o plano não estiver aprovado. Adaptado de
`LeiteZ/fluxo-de-edicao` (etapa motion-mapa, MIT).

Arquivo: `<edit>/inserts_plan.json`
    {"status": "rascunho"|"aprovado", "hookEnd": 3.6, "items": [
      {"id": "i01", "start": 3.6, "end": 11.2, "format": "split",
       "concept": "a Cayenne nova ao lado do preço", "trigger": {"word": "Cayenne", "t": 4.1},
       "camera": "rosto sobe para dar lugar à arte",
       "storyboard": {"conceito": "…", "camadas": "…", "camera": "…", "batidas": "…",
                      "heroi": "…", "vida": "…", "saida": "…"},
       "edit": {"src": "art/cayenne_nova.jpg", "layout": "top", "fit": "cover"},
       "status": "proposto"|"aprovado"|"riscado", "note": "…"}]}

Formatos → onde entram no edit-data:  card, cover → `inserts[]` (cover = fit
"cover") · split → `splitInserts[]` · outros (behind, highlight, transition…)
ficam no plano e são escritos à mão, com aviso.

Uso:
    uv run python helpers/inserts_plan.py check <edit> [--fix]   # valida; --fix encosta bordas no corte
    uv run python helpers/inserts_plan.py show <edit>            # tabela numerada para o chat
    uv run python helpers/inserts_plan.py approve <edit> [i01 i03 … | --all]
    uv run python helpers/inserts_plan.py strike <edit> i04
    uv run python helpers/inserts_plan.py set <edit> i02 --start 12.0 --end 15.2
    uv run python helpers/inserts_plan.py apply <edit> [--replace]
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

PLAN = "inserts_plan.json"
STORY_KEYS = ("conceito", "camadas", "camera", "batidas", "heroi", "vida", "saida")
KEY_OF = {"card": "inserts", "cover": "inserts", "split": "splitInserts"}
SNAP = 0.30        # borda a menos disto de um corte → encosta no corte
MIN_DUR = 2.0      # fonte: um insert explica algo em ≥ ~2 s (motion-craft §5, hipótese)
MAX_DUR = 12.0     # acima disso, dividir em cenas


def paths(edit: Path) -> tuple[Path, Path]:
    pub = edit / "remotion" / "public"
    return edit / PLAN, pub / "edit-data.json"


def load(edit: Path) -> dict:
    p, _ = paths(edit)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        sys.exit(f"sem {PLAN} válido em {edit}")


def save(edit: Path, plan: dict) -> None:
    plan["items"].sort(key=lambda i: float(i.get("start", 0)))
    p, _ = paths(edit)
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


def cut_times(edit: Path) -> tuple[list[float], float | None]:
    """Cortes reais (início de cada take no cut) e duração. segments.json medido
    primeiro; jcut_timeline (exato desde a F0.2) como reserva."""
    pub = edit / "remotion" / "public"
    try:
        seg = json.loads((pub / "segments.json").read_text(encoding="utf-8"))["segments"]
        cuts = [float(s["start"]) for s in seg[1:]]
        return cuts, float(seg[-1]["start"]) + float(seg[-1]["dur"])
    except (OSError, json.JSONDecodeError, KeyError, IndexError):
        pass
    try:
        jt = json.loads((edit / "edl.json").read_text(encoding="utf-8"))["jcut_timeline"]
        cuts = [float(t["video_start_in_output"]) for t in jt[1:]]
        return cuts, float(jt[-1]["video_start_in_output"]) + float(jt[-1]["video_duration"])
    except (OSError, json.JSONDecodeError, KeyError, IndexError):
        return [], None


def check(edit: Path, fix: bool) -> list[str]:
    plan = load(edit)
    items = plan.get("items") or []
    cuts, total = cut_times(edit)
    hook_end = float(plan.get("hookEnd") or 0)
    problems, fixes = [], []
    seen = set()
    for it in items:
        iid = it.get("id", "?")
        if iid in seen:
            problems.append(f"{iid}: id repetido")
        seen.add(iid)
        if it.get("status") == "riscado":
            continue
        s, e = float(it.get("start", 0)), float(it.get("end", 0))
        if e <= s:
            problems.append(f"{iid}: fim {e} não é depois do início {s}")
            continue
        if total is not None and e > total + 0.05:
            problems.append(f"{iid}: termina em {e:.2f}s, depois do fim do corte ({total:.2f}s)")
        d = e - s
        if d < MIN_DUR:
            problems.append(f"{iid}: dura {d:.1f}s (< {MIN_DUR}s — mal dá para ler/entender)")
        if d > MAX_DUR:
            problems.append(f"{iid}: dura {d:.1f}s (> {MAX_DUR}s — dividir em cenas)")
        for k in ("concept", "format"):
            if not it.get(k):
                problems.append(f"{iid}: falta '{k}'")
        tr = it.get("trigger") or {}
        if "t" in tr and not (s - 0.05 <= float(tr["t"]) <= e):
            problems.append(f"{iid}: gatilho '{tr.get('word')}' em {tr['t']}s fora do insert ({s:.2f}–{e:.2f})")
        if s < hook_end:  # o hook pesa mais na retenção: storyboard completo
            sb = it.get("storyboard") or {}
            miss = [k for k in STORY_KEYS if not sb.get(k)]
            if miss:
                problems.append(f"{iid}: está no hook (< {hook_end}s) e falta storyboard: {', '.join(miss)}")
        src = (it.get("edit") or {}).get("src")
        if it.get("format") in KEY_OF and not src:
            problems.append(f"{iid}: formato '{it['format']}' sem edit.src (asset)")
        elif src and not (edit / "remotion" / "public" / src).exists():
            # o export pula insert sem arquivo — antes, em silêncio (medido 2026-11-03)
            problems.append(f"{iid}: ASSET FALTANDO — {src} não existe em remotion/public "
                            f"(peça à pessoa ou busque; não aprove sem ele)")
        # borda colada num corte usa o TEMPO DO CORTE (a folga das bordas põe o corte
        # 0,1–0,3 s antes da 1ª palavra; marcado pela palavra, o insert vaza no take vizinho)
        for edge in ("start", "end"):
            v = float(it[edge])
            near = min(cuts, key=lambda c: abs(c - v)) if cuts else None
            if near is not None and 0.001 < abs(near - v) <= SNAP:
                if fix:
                    it[edge] = round(near, 3)
                    fixes.append(f"{iid}: {edge} {v:.3f} → {near:.3f} (corte)")
                else:
                    problems.append(f"{iid}: {edge} {v:.3f}s a {abs(near - v) * 1000:.0f} ms do corte {near:.3f}s — use o tempo do corte (--fix)")
    # mesmo formato sobreposto no tempo
    live = sorted((i for i in items if i.get("status") != "riscado"), key=lambda i: float(i["start"]))
    for a, b in zip(live, live[1:]):
        if a.get("format") == b.get("format") and float(b["start"]) < float(a["end"]) - 0.01:
            problems.append(f"{a['id']} e {b['id']}: dois '{a['format']}' sobrepostos ({b['start']} < {a['end']})")
    if fix and fixes:
        save(edit, plan)
    for f in fixes:
        print(f"  ✓ {f}")
    return problems


def show(edit: Path) -> None:
    plan = load(edit)
    print(f"Plano de inserts — {plan.get('status', 'rascunho')}"
          + (f" · hook até {plan['hookEnd']}s" if plan.get("hookEnd") else ""))
    for it in plan.get("items") or []:
        st = {"aprovado": "✓", "riscado": "✗"}.get(it.get("status"), "·")
        tr = it.get("trigger") or {}
        gat = f" · gatilho \"{tr.get('word')}\" {tr.get('t')}s" if tr else ""
        cam = f"\n        câmera: {it['camera']}" if it.get("camera") else ""
        print(f"  {st} {it['id']}  {float(it['start']):6.2f}–{float(it['end']):6.2f}s  [{it.get('format')}]  "
              f"{it.get('concept', '')}{gat}{cam}")
        sb = it.get("storyboard")
        if sb:
            print("        storyboard: " + " · ".join(f"{k}: {sb[k]}" for k in STORY_KEYS if sb.get(k)))
        if it.get("note"):
            print(f"        nota: {it['note']}")


def set_status(edit: Path, ids: list[str], status: str, all_: bool = False) -> None:
    plan = load(edit)
    found = set()
    for it in plan.get("items") or []:
        if all_ or it["id"] in ids:
            if all_ and it.get("status") == "riscado":
                continue
            it["status"] = status
            found.add(it["id"])
    miss = set(ids) - found
    if miss:
        sys.exit(f"ids não encontrados: {', '.join(sorted(miss))}")
    live = [i for i in plan["items"] if i.get("status") != "riscado"]
    if live and all(i.get("status") == "aprovado" for i in live):
        plan["status"] = "aprovado"
        plan["approvedAt"] = time.strftime("%Y-%m-%d %H:%M")
    else:
        plan["status"] = "rascunho"
        plan.pop("approvedAt", None)
    save(edit, plan)
    print(f"  {', '.join(sorted(found)) or 'nada'} → {status} · plano: {plan['status']}")


def set_times(edit: Path, iid: str, start: float | None, end: float | None) -> None:
    plan = load(edit)
    it = next((i for i in plan.get("items") or [] if i["id"] == iid), None)
    if it is None:
        sys.exit(f"{iid} não existe")
    if start is not None:
        it["start"] = round(start, 3)
    if end is not None:
        it["end"] = round(end, 3)
    if it.get("status") == "aprovado":  # mudou depois de aprovado → aprovar de novo
        it["status"] = "proposto"
        plan["status"] = "rascunho"
    save(edit, plan)
    print(f"  {iid}: {it['start']}–{it['end']}s (volta a 'proposto' — aprove de novo)")


def apply(edit: Path, replace: bool) -> None:
    plan = load(edit)
    if plan.get("status") != "aprovado":
        sys.exit("GATE: o plano não está aprovado — mostre (`show`), aprove por número "
                 "(`approve`) e só então aplique. Nenhum edit-data foi escrito.")
    problems = check(edit, fix=False)
    if problems:
        sys.exit("GATE: o plano aprovado tem problemas — corrija antes de aplicar:\n  " + "\n  ".join(problems))
    _, ed_p = paths(edit)
    if not ed_p.exists():
        sys.exit(f"sem {ed_p} — rode o scaffold_phase2.py primeiro")
    ed = json.loads(ed_p.read_text(encoding="utf-8"))
    live = [i for i in plan["items"] if i.get("status") == "aprovado"]
    groups: dict[str, list[dict]] = {}
    manual = []
    for it in live:
        key = KEY_OF.get(it.get("format"))
        if not key:
            manual.append(it)
            continue
        entry = dict(it.get("edit") or {})
        entry.update({"id": it["id"], "start": float(it["start"]), "end": float(it["end"])})
        if it["format"] == "cover":
            entry["fit"] = "cover"
        groups.setdefault(key, []).append(entry)
    for key, entries in groups.items():
        old = ed.get(key) or []
        orphans = [o for o in old if o.get("id") not in {e["id"] for e in entries}]
        if orphans and not replace:
            sys.exit(f"GATE: {key} já tem {len(orphans)} item(ns) fora do plano "
                     f"(ex.: {json.dumps(orphans[0], ensure_ascii=False)[:120]}). Ponha-os no plano, "
                     f"ou rode com --replace para descartá-los.")
        ed[key] = sorted(entries, key=lambda e: e["start"])
    bak = ed_p.with_name(f"edit-data.before_plan.{time.strftime('%Y%m%d-%H%M%S')}.json")
    shutil.copy2(ed_p, bak)
    ed_p.write_text(json.dumps(ed, ensure_ascii=False, indent=1), encoding="utf-8")
    for key, entries in groups.items():
        print(f"  {key}: {len(entries)} → {', '.join(e['id'] for e in entries)}")
    for it in manual:
        print(f"  ⚠ {it['id']} [{it.get('format')}] não tem destino automático — escreva no edit-data à mão, com \"id\": \"{it['id']}\"")
    print(f"  gravado (backup: {bak.name})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "show", "approve", "strike", "set", "apply"):
        p = sub.add_parser(name)
        p.add_argument("edit", type=Path)
        if name == "check":
            p.add_argument("--fix", action="store_true")
        if name in ("approve", "strike"):
            p.add_argument("ids", nargs="*")
            if name == "approve":
                p.add_argument("--all", action="store_true")
        if name == "set":
            p.add_argument("id")
            p.add_argument("--start", type=float)
            p.add_argument("--end", type=float)
        if name == "apply":
            p.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    edit = a.edit.resolve()
    if a.cmd == "check":
        probs = check(edit, a.fix)
        for p in probs:
            print(f"  ✗ {p}")
        print(f"  {len(probs)} problema(s)")
        sys.exit(1 if probs else 0)
    if a.cmd == "show":
        show(edit)
    elif a.cmd == "approve":
        set_status(edit, a.ids, "aprovado", a.all)
    elif a.cmd == "strike":
        set_status(edit, a.ids, "riscado")
    elif a.cmd == "set":
        set_times(edit, a.id, a.start, a.end)
    else:
        apply(edit, a.replace)


if __name__ == "__main__":
    main()
