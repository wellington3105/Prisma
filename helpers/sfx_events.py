"""Eventos visíveis da Fase 2 → rascunho de `sfxCues` pelas regras do sfx-craft (F3.2 + F3.3).

Lê o `edit-data.json` (hook, inserts, splits, destaques de vidro, transições),
lista cada EVENTO VISÍVEL com um id estável (tipo + tempo + referência: não muda
numa rodada nova se o evento não mudou) e escolhe um som para cada um pelo
índice (`sfx_index.py`), aplicando as regras de `references/sfx-craft.md`:

  - o som segue o que se vê: só eventos visíveis; transição já tem o próprio
    som (`transitions[].sfx`, tocado pelo deliver_mix) → nada empilhado nela;
  - um protagonista por momento: eventos a < 0,15 s viram um só;
  - escalada: o MAIOR impacto no ápice do hook; nada maior depois;
  - respiro: nenhum outro som nos 0,5 s antes do maior impacto;
  - variação: o mesmo arquivo não repete em 20 s (exceto a assinatura dos
    destaques prisma, `glass_ping`);
  - celular: só sons que "tocam bem" ou "perdem corpo" no alto-falante (índice);
  - alinhamento: o do índice (`peak` para whoosh/impacto) — o `deliver_mix`
    desconta o pico do próprio arquivo.

Saída: imprime o rascunho e as violações; `--apply` grava `sfxCues` no
edit-data (backup antes) e copia para `remotion/public/sfx/` os sons que vierem
de outra biblioteca, para o deliver_mix achá-los.

Uso:
    uv run python helpers/sfx_events.py <edit> [--apply] [--index sfx_index.json]
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

ROOT = Path(__file__).resolve().parent.parent
REPEAT_S = 20.0
BREATH_S = 0.5
MERGE_S = 0.15
SIGNATURE = "glass_ping.wav"
# papel → candidatos por ordem de preferência (o índice confirma celular/align)
ROLE = {
    "hook":      (["impact.wav"], 0.45),
    "entrada":   (["whoosh_air.wav", "whoosh-short.mp3", "whoosh.mp3", "whoosh-cinematic.mp3"], 0.28),
    "destaque":  ([SIGNATURE], 0.30),
}


def events(ed: dict) -> list[dict]:
    ev = []
    hook = ed.get("hook") or {}
    if hook.get("enabled", True) and hook.get("text"):
        ev.append({"type": "hook", "t": 0.05, "ref": "hook", "what": f"headline \"{hook['text'][:30]}\""})
    for key in ("inserts", "splitInserts"):
        for n, it in enumerate(ed.get(key) or []):
            ref = it.get("id") or f"{key}[{n}]"
            ev.append({"type": "entrada", "t": float(it["start"]), "ref": ref,
                       "what": f"{'card' if key == 'inserts' else 'split'} {Path(str(it.get('src', ''))).name}"})
    hl = ed.get("highlights") or {}
    if hl.get("enabled"):
        off = float(hl.get("offsetS", 0.8))
        for n, it in enumerate(hl.get("items") or []):
            ev.append({"type": "destaque", "t": float(it["at"]) + off, "ref": f"hl[{n}]",
                       "what": f"vidro \"{it.get('text', '')}\""})
    for n, tr in enumerate(ed.get("transitions") or []):
        ev.append({"type": "transicao", "t": float(tr["at"]), "ref": f"tr[{n}]",
                   "what": f"transição {tr.get('type', 'flash')} (som próprio: {tr.get('sfx', 'cut-click.mp3')})"})
    ev.sort(key=lambda e: e["t"])
    for e in ev:
        e["id"] = f"{e['type']}@{e['t']:.2f}:{e['ref']}"
    return ev


def pick(role: str, idx: dict, recent: dict, t: float) -> tuple[str | None, str]:
    cands, _ = ROLE[role]
    for f in cands:
        e = idx.get(f)
        if not e:
            continue
        if not e.get("phone_ok", True):
            continue
        if f != SIGNATURE and t - recent.get(f, -1e9) < REPEAT_S:
            continue
        return f, e.get("align", "peak")
    # todos repetiriam: o menos recente
    pool = [f for f in cands if f in idx]
    if not pool:
        return None, "peak"
    f = min(pool, key=lambda x: recent.get(x, -1e9))
    return f, idx[f].get("align", "peak")


def draft(ed: dict, idx: dict) -> tuple[list[dict], list[str]]:
    ev = events(ed)
    trans_t = [e["t"] for e in ev if e["type"] == "transicao"]
    cues, notes, recent = [], [], {}
    last_t = -1e9
    for e in ev:
        if e["type"] == "transicao":
            continue  # som próprio
        if any(abs(e["t"] - tt) < MERGE_S for tt in trans_t):
            notes.append(f"{e['id']}: coincide com uma transição — a transição já soa, sem segundo principal")
            continue
        if e["t"] - last_t < MERGE_S:
            notes.append(f"{e['id']}: colado no evento anterior — um protagonista por momento")
            continue
        # Dentro da cauda do som anterior → dois principais encavalados. Medido
        # 2026-11-03 (Cayenne): um whoosh em 0,40 s caía no meio do impacto do hook
        # (0,05 s, 0,89 s úteis) — o impacto já cobre a abertura.
        if cues:
            prev = cues[-1]
            tail = min(0.6, float(idx.get(prev["src"], {}).get("useful_s", 0.3)))
            if e["t"] - prev["at"] < tail:
                notes.append(f"{e['id']}: dentro da cauda de {prev['src']} ({e['t'] - prev['at']:.2f}s < {tail:.2f}s) — sem segundo principal")
                continue
        f, align = pick(e["type"], idx, recent, e["t"])
        if not f:
            notes.append(f"{e['id']}: nenhum som da biblioteca serve — sem som (anote o que faltou)")
            continue
        recent[f] = e["t"]
        last_t = e["t"]
        cues.append({"src": f, "at": round(e["t"], 3), "volume": ROLE[e["type"]][1], "align": align,
                     "note": f"principal · {e['type']} · {e['what']} · {'assinatura' if f == SIGNATURE else align}",
                     "event": e["id"]})
    # escalada + respiro: o maior impacto é o do hook; nada nos 0,5 s antes dele
    big = next((c for c in cues if c["event"].startswith("hook@")), None)
    if big:
        before = [c for c in cues if c is not big and big["at"] - BREATH_S <= c["at"] < big["at"]]
        for c in before:
            cues.remove(c)
            notes.append(f"{c['event']}: removido — respiro de {BREATH_S}s antes do maior impacto")
    return cues, notes


def violations(cues: list[dict], idx: dict) -> list[str]:
    out, last = [], {}
    big = max((c["volume"] for c in cues), default=0)
    hook = next((c for c in cues if c["event"].startswith("hook@")), None)
    for c in sorted(cues, key=lambda c: c["at"]):
        if "align" not in c or "note" not in c:
            out.append(f"{c['event']}: sem papel/alinhamento declarado")
        if c["src"] != SIGNATURE and c["at"] - last.get(c["src"], -1e9) < REPEAT_S:
            out.append(f"{c['event']}: {c['src']} repete em {c['at'] - last[c['src']]:.1f}s")
        last[c["src"]] = c["at"]
        e = idx.get(c["src"])
        if e and not e.get("phone_ok", True):
            out.append(f"{c['event']}: {c['src']} perde o grave no celular — sobra só o ataque "
                       f"({e.get('phone_peak_dbfs', float('nan')):.0f} dBFS)")
        if hook and c is not hook and c["volume"] > hook["volume"]:
            out.append(f"{c['event']}: mais alto que o impacto do hook (escalada)")
    if hook and big > hook["volume"]:
        out.append("o maior som não é o do hook")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--index", type=Path, default=ROOT / "sfx_index.json")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    edit = a.edit.resolve()
    pub = edit / "remotion" / "public"
    ed_p = pub / "edit-data.json"
    ed = json.loads(ed_p.read_text(encoding="utf-8"))
    idx = {e["file"]: e for e in json.loads(a.index.read_text(encoding="utf-8"))}
    ev = events(ed)
    print(f"  {len(ev)} evento(s) visível(is):")
    for e in ev:
        print(f"    {e['id']:<40} {e['what']}")
    cues, notes = draft(ed, idx)
    print(f"  rascunho: {len(cues)} cue(s)")
    for c in cues:
        print(f"    {c['at']:7.2f}s  {c['src']:<22} vol {c['volume']:.2f}  align {c['align']:<5}  {c['event']}")
    for n in notes:
        print(f"    · {n}")
    v = violations(cues, idx)
    print(f"  violações das regras do sfx-craft: {len(v)}")
    for x in v:
        print(f"    ✗ {x}")
    if a.apply:
        if v:
            sys.exit("não aplico um rascunho com violações")
        (pub / "sfx").mkdir(parents=True, exist_ok=True)
        for c in cues:
            dst = pub / "sfx" / c["src"]
            if not dst.exists() and c["src"] in idx:
                shutil.copy2(idx[c["src"]]["path"], dst)
        bak = ed_p.with_name(f"edit-data.before_sfx.{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(ed_p, bak)
        ed["sfxCues"] = [{k: c[k] for k in ("src", "at", "volume", "align", "note", "event")} for c in cues]
        ed_p.write_text(json.dumps(ed, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  gravado sfxCues ({len(cues)}) · backup {bak.name}")


if __name__ == "__main__":
    main()
