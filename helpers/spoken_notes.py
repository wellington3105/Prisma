"""Notas de edição faladas na gravação — achar, interpretar, tirar do corte (F4.1).

Costume sugerido a quem grava: deixar instruções para o editor no próprio
áudio — "nota de edição, usa o segundo take dessa frase, fim da nota". Este
helper acha cada nota nos transcripts (tolerando o que o Whisper faz com as
palavras: acento, vírgula, "nota da edição"), guarda o texto e a etapa a que se
refere, e — com `--strip` — tira o trecho inteiro da nota do `edl.json` (das
palavras de abertura até as de fechamento). Adaptado de
`LeiteZ/fluxo-de-edicao` (etapa preparar, MIT).

Regras:
  - a nota vale para o que acabou de ser falado, salvo se disser outra coisa;
  - abertura sem fechamento termina na próxima pausa ≥ 1 s, com confiança BAIXA
    (vira marcador do Claude no preview, para a pessoa conferir);
  - o trecho removido leva uma folga pequena nas pontas; `refine_edges.py`
    ajusta as bordas novas no silêncio depois.

Saída: `<edit>/spoken_notes.json` — [{id, source, start, end, text, stage, confidence}].

Uso:
    uv run python helpers/spoken_notes.py <edit>                       # acha e lista
    uv run python helpers/spoken_notes.py <edit> --strip               # e tira do edl.json
    uv run python helpers/spoken_notes.py <edit> --open "nota de edição" --close "fim da nota"
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
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OPEN = ["nota de edicao", "nota da edicao", "nota edicao", "nota de edicao do"]
CLOSE = ["fim da nota", "fim de nota", "fim nota", "final da nota"]
MATCH = 0.80        # similaridade mínima por janela de palavras
MAX_NOTE_S = 60.0   # uma nota não dura mais que isso
PAUSE_END = 1.0     # sem fechamento: termina na próxima pausa deste tamanho
PAD_IN, PAD_OUT = 0.05, 0.15
STAGES = [("cortes", r"\b(take|corta|cortar|tira|tirar|usa|usar|repete|refaz|frase)\b"),
          ("inserts", r"\b(logo|imagem|arte|foto|print|animacao|card|mostra|mostrar|grafico|tela)\b"),
          ("camera", r"\b(zoom|camera|aproxima|enquadra)\b"),
          ("som", r"\b(som|musica|trilha|efeito|barulho)\b"),
          ("cor", r"\b(cor|luz|escuro|claro)\b")]


def norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w)


def words_of(path: Path) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    ws = d.get("words") if isinstance(d, dict) else d
    out = []
    for w in ws or []:
        if w.get("type", "word") != "word" or w.get("start") is None:
            continue
        t = (w.get("text") or w.get("word") or "").strip()
        if norm(t):
            out.append({"w": norm(t), "raw": t, "s": float(w["start"]), "e": float(w["end"])})
    return out


def find(ws: list[dict], phrases: list[str], i0: int = 0) -> list[tuple[int, int, float]]:
    """(início, fim inclusive, similaridade) de cada ocorrência de qualquer frase."""
    hits = []
    for ph in phrases:
        tgt = [norm(x) for x in ph.split()]
        k = len(tgt)
        for i in range(i0, len(ws) - k + 1):
            r = difflib.SequenceMatcher(None, " ".join(tgt), " ".join(w["w"] for w in ws[i:i + k])).ratio()
            if r >= MATCH:
                hits.append((i, i + k - 1, r))
    hits.sort(key=lambda h: (h[0], -h[2]))
    out, last = [], -1
    for h in hits:  # sem sobreposição: a melhor de cada lugar
        if h[0] > last:
            out.append(h)
            last = h[1]
    return out


def stage_of(text: str) -> str:
    t = " ".join(norm(x) for x in text.split())
    for name, rx in STAGES:
        if re.search(rx, t):
            return name
    return "geral"


def detect(ws: list[dict], source: str, opens: list[str], closes: list[str]) -> list[dict]:
    notes = []
    o_hits = find(ws, opens)
    for n, (a, b, r) in enumerate(o_hits):
        nxt_open = o_hits[n + 1][0] if n + 1 < len(o_hits) else len(ws)
        c = next((h for h in find(ws, closes, b + 1)
                  if h[0] < nxt_open and ws[h[1]]["e"] - ws[a]["s"] <= MAX_NOTE_S), None)
        if c:
            body, end_i, conf = ws[b + 1:c[0]], c[1], "alta"
        else:
            end_i = None
            for j in range(b + 1, min(len(ws), nxt_open)):
                if j + 1 >= len(ws) or ws[j + 1]["s"] - ws[j]["e"] >= PAUSE_END:
                    end_i = j
                    break
            end_i = end_i if end_i is not None else b
            body, conf = ws[b + 1:end_i + 1], "baixa"
        text = " ".join(w["raw"] for w in body).strip(" ,.;:")
        # Onde cortar: no MEIO da pausa antes e depois da nota, não colado na
        # palavra. Medido 2026-11-03: com o corte a 50 ms antes de "Nota", o
        # refine_edges achou a borda COLADA e a empurrou 20 ms para dentro dela.
        s_note, e_note = ws[a]["s"], ws[end_i]["e"]
        prev_e = ws[a - 1]["e"] if a > 0 else None
        next_s = ws[end_i + 1]["s"] if end_i + 1 < len(ws) else None
        cut_s = (prev_e + min(0.30, (s_note - prev_e) / 2)) if prev_e is not None and s_note > prev_e else s_note - PAD_IN
        cut_e = (next_s - min(0.30, (next_s - e_note) / 2)) if next_s is not None and next_s > e_note else e_note + PAD_OUT
        notes.append({"source": source, "start": round(max(0.0, cut_s), 3),
                      "end": round(cut_e, 3), "text": text,
                      "stage": stage_of(text), "confidence": conf,
                      "match": round(r, 2)})
    return notes


def strip(edl_p: Path, notes: list[dict], ws_by_src: dict[str, list[dict]]) -> list[str]:
    edl = json.loads(edl_p.read_text(encoding="utf-8"))
    out, log = [], []
    for r in edl["ranges"]:
        pieces = [(float(r["start"]), float(r["end"]))]
        for nt in (x for x in notes if x["source"] == r["source"]):
            nxt = []
            for s, e in pieces:
                if nt["end"] <= s or nt["start"] >= e:
                    nxt.append((s, e))
                    continue
                log.append(f"  − {r['source']} {max(s, nt['start']):.2f}–{min(e, nt['end']):.2f}s (nota: \"{nt['text']}\")")
                if nt["start"] - s > 0.25:
                    nxt.append((s, nt["start"]))
                if e - nt["end"] > 0.25:
                    nxt.append((nt["end"], e))
            pieces = nxt
        for s, e in pieces:
            q = dict(r)
            q["start"], q["end"] = round(s, 3), round(e, 3)
            if (s, e) != (float(r["start"]), float(r["end"])):
                # o quote velho descreve o range inteiro; o novo vem das palavras do trecho
                ws = ws_by_src.get(r["source"]) or []
                q["quote"] = " ".join(w["raw"] for w in ws if w["s"] >= s - 0.02 and w["e"] <= e + 0.02)
            out.append(q)
    if log:
        bak = edl_p.with_name(f"edl.before_notes.{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(edl_p, bak)
        edl["ranges"] = out
        edl.pop("jcut_timeline", None)
        edl["total_duration_s"] = round(sum(x["end"] - x["start"] for x in out), 2)
        edl_p.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
        log.append(f"  gravado ({len(out)} ranges; backup {bak.name}) — rode refine_edges.py nas bordas novas")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--open", action="append", help="frase de abertura (repetível)")
    ap.add_argument("--close", action="append", help="frase de fechamento (repetível)")
    ap.add_argument("--strip", action="store_true", help="tira as notas do edl.json")
    a = ap.parse_args()
    edit = a.edit.resolve()
    opens, closes = a.open or OPEN, a.close or CLOSE
    tdir = edit / "transcripts"
    srcs = sorted(tdir.glob("*.json")) if tdir.exists() else []
    if not srcs:
        sys.exit(f"sem transcripts em {tdir}")
    notes, ws_by_src = [], {}
    for p in srcs:
        ws = words_of(p)
        ws_by_src[p.stem] = ws
        notes += detect(ws, p.stem, opens, closes)
    for i, nt in enumerate(notes, 1):
        nt["id"] = f"n{i:02d}"
    (edit / "spoken_notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    if not notes:
        print("nenhuma nota de edição falada")
    for nt in notes:
        flag = "" if nt["confidence"] == "alta" else "  ⚠ sem fechamento — confira"
        print(f"  {nt['id']} {nt['source']} {nt['start']:.2f}–{nt['end']:.2f}s [{nt['stage']}] "
              f"\"{nt['text']}\"{flag}")
    try:
        import agent_markers
        agent_markers.clear(edit, "nota")
        for nt in notes:
            if nt["confidence"] != "alta":
                agent_markers.add(edit, nt["source"], nt["start"], "nota",
                                  f"nota sem fechamento: \"{nt['text']}\" — terminei na pausa; confira", nt["end"])
    except Exception:
        pass
    if a.strip:
        edl_p = edit / "edl.json"
        if not edl_p.exists():
            sys.exit("sem edl.json para --strip")
        for line in strip(edl_p, notes, ws_by_src) or ["  nenhum range continha nota"]:
            print(line)


if __name__ == "__main__":
    main()
