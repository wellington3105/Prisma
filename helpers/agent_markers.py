"""Marcadores do Claude na timeline do preview — dúvidas e alertas no ponto exato.

Até aqui, toda dúvida do agente ia para o chat ("tem outro take bom em 12s"), e a
pessoa tinha de achar o ponto sozinha. Os marcadores vão para a trilha
"Marcações" do preview, em azul (os da pessoa são vermelhos), ancorados no
TEMPO DA FONTE — não no da timeline — para sobreviverem a um novo corte: se o
range muda, o marcador vai junto; se o trecho sai do corte, ele fica esmaecido
na borda mais próxima, com "(fora do corte)". Adaptado de
`LeiteZ/fluxo-de-edicao` (marcadores na linha do tempo em vez de listas no chat, MIT).

Arquivo: `<edit>/agent_markers.json` — [{id, kind, source, at, end?, text}].

Tipos:
  duvida_take  havia outro take bom — diga onde
  hesitacao    pensou em cortar uma hesitação e não cortou
  nota         nota de edição falada de confiança baixa ou não entendida
  sugestao     ex.: reordenar
  alerta       técnico (sync duvidoso, transcrição ruim no trecho)
  borda        borda da pessoa que corta palavra (refine_edges grava sozinho)

Uso:
    uv run python helpers/agent_markers.py add <edit> --source C0103 --at 12.40 --kind duvida_take --text "take 2 em 31.2s também está limpo"
    uv run python helpers/agent_markers.py list <edit>
    uv run python helpers/agent_markers.py clear <edit> [--kind borda]
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
import sys
import time
from pathlib import Path

FILE = "agent_markers.json"
KINDS = {"duvida_take": "dúvida de take", "hesitacao": "hesitação mantida",
         "nota": "nota não entendida", "sugestao": "sugestão", "alerta": "alerta técnico",
         "borda": "borda a conferir"}


def load(edit: Path) -> list[dict]:
    p = Path(edit) / FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save(edit: Path, items: list[dict]) -> None:
    items.sort(key=lambda m: (m.get("source", ""), float(m.get("at", 0))))
    (Path(edit) / FILE).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def add(edit: Path, source: str, at: float, kind: str, text: str, end: float | None = None,
        dedupe: bool = True) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind inválido: {kind} (use {', '.join(KINDS)})")
    items = load(edit)
    if dedupe:  # o mesmo aviso no mesmo ponto não se repete a cada rodada
        items = [m for m in items if not (m.get("kind") == kind and m.get("source") == source
                                          and abs(float(m.get("at", -9)) - at) < 0.05)]
    m = {"id": f"c{int(time.time() * 1000)}{len(items)}", "kind": kind, "source": source,
         "at": round(float(at), 3), "text": text}
    if end is not None and end > at:
        m["end"] = round(float(end), 3)
    items.append(m)
    save(edit, items)
    return m


def clear(edit: Path, kind: str | None = None) -> int:
    items = load(edit)
    keep = [m for m in items if kind and m.get("kind") != kind]
    save(edit, keep)
    return len(items) - len(keep)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("edit", type=Path)
    a.add_argument("--source", required=True)
    a.add_argument("--at", type=float, required=True, help="segundos NA FONTE")
    a.add_argument("--end", type=float, help="fim do trecho, na fonte (opcional)")
    a.add_argument("--kind", required=True, choices=list(KINDS))
    a.add_argument("--text", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("edit", type=Path)
    c = sub.add_parser("clear")
    c.add_argument("edit", type=Path)
    c.add_argument("--kind", choices=list(KINDS))
    args = ap.parse_args()
    if args.cmd == "add":
        m = add(args.edit, args.source, args.at, args.kind, args.text, args.end)
        print(f"  + {m['id']} {KINDS[m['kind']]} · {m['source']} {m['at']}s · {m['text']}")
    elif args.cmd == "list":
        items = load(args.edit)
        for m in items:
            print(f"  {m['id']}  {KINDS.get(m['kind'], m['kind']):<20} {m['source']} {m['at']}s  {m['text']}")
        print(f"  {len(items)} marcador(es)")
    else:
        print(f"  {clear(args.edit, args.kind)} removido(s)")


if __name__ == "__main__":
    main()
