"""Propõe onde o B-roll entra: nos pontos de emenda, cobrindo o jump cut.

Existe porque o Prisma sabia fazer as duas coisas e nunca as ligou. O EDL
conhece cada emenda — são os pontos onde blocos de fala se juntam — e o
`brollFull` sabe preencher a tela. A literatura de montagem une os dois com uma
frase: *"aparar pausas de um talking head produz jump cuts, que você cobre com
B-roll ou um corte de apoio"*.

Ou seja: o B-roll não é enfeite posto onde sobra espaço. Ele tem uma **função de
reparo** — e o melhor lugar para ele é exatamente onde a edição deixou cicatriz.

Duas regras de ofício que o plano respeita:

  - **2 a 4 segundos por inserção.** Menos que isso o espectador não reconhece
    a imagem; mais, esquece quem estava falando.
  - **Padrão rosto → cobertura → rosto.** A cobertura entra no meio do
    pensamento, com a narração por baixo, e o rosto volta para a conclusão.
    Por isso o plano nunca cobre a última emenda: o fecho é do apresentador.

Uso:
    uv run python helpers/broll_plan.py edl.json --transcript transcripts/cut.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DUR_PADRAO = 3.0      # meio da faixa 2–4s
DUR_MIN = 2.0
DUR_MAX = 4.0
# O B-roll entra um pouco ANTES da emenda: ele precisa já estar na tela quando
# o corte acontece, senão a troca de imagem denuncia o ponto em vez de escondê-lo.
ANTECIPACAO = 0.4
# Duas coberturas coladas viram sequência de B-roll, não apoio à fala.
GAP_MIN = 6.0


def planejar(edl: Path, transcript: Path | None, dur: float) -> dict:
    d = json.loads(edl.read_text(encoding="utf-8"))
    ranges = d.get("ranges", [])
    if len(ranges) < 2:
        return {"ok": False, "reason": "EDL com menos de 2 blocos — não há emenda a cobrir",
                "inserts": []}

    # Emendas na TIMELINE DE SAÍDA: o EDL guarda tempos da fonte, e o vídeo
    # montado os concatena. Somar as durações é o que dá o instante real.
    emendas: list[float] = []
    acc = 0.0
    for r in ranges[:-1]:
        acc += float(r["end"]) - float(r["start"])
        emendas.append(round(acc, 2))

    total = acc + (float(ranges[-1]["end"]) - float(ranges[-1]["start"]))

    # Palavras por emenda, para sugerir o que a cobertura deve mostrar.
    palavras: list[dict] = []
    if transcript and transcript.exists():
        try:
            t = json.loads(transcript.read_text(encoding="utf-8"))
            palavras = [w for w in t.get("words", []) if w.get("text", "").strip()]
        except (OSError, json.JSONDecodeError):
            palavras = []

    def contexto(seg: float) -> str:
        janela = [w["text"].strip() for w in palavras
                  if seg <= float(w.get("start", -1)) < seg + dur]
        return " ".join(janela[:8])

    inserts = []
    ultimo = -999.0
    # A ÚLTIMA emenda fica de fora: o padrão de ofício devolve o rosto para a
    # conclusão, e cobrir o fecho tira do apresentador a frase que fecha.
    for e in emendas[:-1] if len(emendas) > 1 else emendas:
        ini = round(max(0.0, e - ANTECIPACAO), 2)
        if ini - ultimo < GAP_MIN:
            continue
        inserts.append({
            "start": ini,
            "end": round(min(total, ini + dur), 2),
            "fit": "cover",
            "src": "BROLL_AQUI.mp4",
            "_emenda": e,
            "_sugestao": contexto(e) or "(sem transcript)",
        })
        ultimo = ini

    return {
        "ok": bool(inserts),
        "reason": (f"{len(inserts)} cobertura(s) para {len(emendas)} emenda(s) "
                   f"em {total:.1f}s"
                   if inserts else
                   "emendas próximas demais entre si — nenhuma cobertura cabe "
                   f"sem violar o intervalo mínimo de {GAP_MIN}s"),
        "timeline_s": round(total, 2),
        "emendas": emendas,
        "inserts": inserts,
        "nota": ("Troque `src` pelo clipe de cada cobertura. `_emenda` e "
                 "`_sugestao` são anotações — remova-os do edit-data.json."),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edl", type=Path)
    ap.add_argument("--transcript", type=Path, default=None,
                    help="transcripts/cut.json — sugere o que cada cobertura mostra")
    ap.add_argument("--dur", type=float, default=DUR_PADRAO,
                    help=f"segundos por cobertura ({DUR_MIN}–{DUR_MAX}, default {DUR_PADRAO})")
    ap.add_argument("--out", type=Path, help="grava a lista de inserts")
    args = ap.parse_args()

    dur = max(DUR_MIN, min(DUR_MAX, args.dur))
    r = planejar(args.edl, args.transcript, dur)

    if args.out and r["ok"]:
        args.out.write_text(json.dumps(
            [{k: v for k, v in i.items() if not k.startswith("_")}
             for i in r["inserts"]], ensure_ascii=False, indent=1), encoding="utf-8")
        r["out"] = str(args.out)

    print(json.dumps(r, ensure_ascii=False, indent=1))
    if not r["ok"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
