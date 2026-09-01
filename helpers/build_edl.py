"""Monta o EDL a partir do transcript, com pausa ASSIMÉTRICA.

Existe porque cortar todas as pausas por igual mata o ritmo — e foi o que
produziu o vídeo reprovado em 2026-09-01. A regra de ofício (PRP 2026-09-01) é
explícita e assimétrica:

  - pausa de rotina: aparar para **0.10–0.25s**;
  - pausa ANTES de revelação, nome ou promessa: preservar **0.30–0.60s**.

E o porquê, que é o que importa: *"cortar rápido demais antes de o cérebro
registrar o plano cria fadiga cognitiva; segurar depois que o espectador
extraiu todo o valor cria tédio."* A pausa antes do ponto **é ferramenta**, não
defeito — é ela que faz a frase seguinte chegar.

Como o helper sabe onde está o ponto: pela mesma heurística do
`highlight_words.py`. Se a primeira palavra depois da pausa é número, nome
próprio ou substantivo longo, a pausa está preparando algo — e fica.

Uso:
    uv run python helpers/build_edl.py transcripts/source.json source.mp4 -o edl.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Faixas de ofício, em segundos.
PAUSA_ROTINA = 0.18       # meio da faixa 0.10–0.25
PAUSA_ANTES_DO_PONTO = 0.45   # meio da faixa 0.30–0.60
# Abaixo disto não é pausa, é a respiração natural entre palavras.
PAUSA_MINIMA = 0.28
# Bloco de fala curto demais vira staccato; funde com o vizinho.
MIN_BLOCO = 0.8

VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "em",
    "na", "no", "nas", "nos", "por", "para", "pra", "com", "sem", "que", "e",
    "ou", "mas", "se", "eu", "voce", "ele", "ela", "nos", "entao", "dai", "ai",
    "tipo", "assim", "ja", "so", "tambem", "nao", "sim", "bem", "muito", "mais",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _prepara_algo(palavra: str) -> bool:
    """A palavra depois da pausa merece que a pausa fique?

    Mesma leitura do highlight_words: número, nome próprio ou substantivo com
    carga. Se sim, a pausa está construindo expectativa e cortá-la rouba o
    efeito da frase.
    """
    limpo = palavra.strip().strip(".,!?;:—-\"'()")
    n = _norm(limpo)
    if not limpo or n in VAZIAS:
        return False
    if re.search(r"\d", limpo):
        return True
    if limpo[0].isupper():
        return True
    return len(limpo) >= 8


def montar(transcript: Path, video: Path, grade: str) -> dict:
    d = json.loads(transcript.read_text(encoding="utf-8"))
    palavras = [w for w in d.get("words", []) if w.get("text", "").strip()]
    if not palavras:
        raise SystemExit("transcript sem palavras")

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True).stdout.strip())

    # Blocos separados nas pausas reais; cada corte guarda a folga que MERECE.
    blocos: list[dict] = []
    ini = float(palavras[0]["start"])
    prev = float(palavras[0]["end"])
    pad_entrada = PAUSA_ROTINA

    for w in palavras[1:]:
        gap = float(w["start"]) - prev
        if gap >= PAUSA_MINIMA:
            # A folga do FIM deste bloco e do INÍCIO do próximo são a mesma
            # pausa, vista dos dois lados. Se o que vem depois é um ponto, ela
            # fica inteira; se é continuação, apara.
            folga = PAUSA_ANTES_DO_PONTO if _prepara_algo(w["text"]) else PAUSA_ROTINA
            blocos.append({
                "start": round(max(0.0, ini - pad_entrada), 2),
                "end": round(min(dur, prev + folga), 2),
                "pausa_seguinte": round(folga, 2),
                "prepara": _prepara_algo(w["text"]),
                "proxima": w["text"].strip(),
            })
            ini = float(w["start"])
            pad_entrada = folga
        prev = float(w["end"])

    blocos.append({
        "start": round(max(0.0, ini - pad_entrada), 2),
        "end": round(min(dur, prev + PAUSA_ROTINA), 2),
        "pausa_seguinte": PAUSA_ROTINA,
        "prepara": False,
        "proxima": "",
    })

    # Blocos curtos demais soam picotados — funde com o anterior.
    fundidos: list[dict] = []
    for b in blocos:
        if fundidos and (b["end"] - b["start"]) < MIN_BLOCO:
            fundidos[-1]["end"] = b["end"]
        else:
            fundidos.append(b)

    ranges = [{"source": "src", "start": b["start"], "end": b["end"]}
              for b in fundidos]
    total = round(sum(r["end"] - r["start"] for r in ranges), 2)

    return {
        "edl": {
            "version": 1,
            "sources": {"src": str(video.resolve())},
            "grade": grade,
            "voice_master": True,
            "ranges": ranges,
            "total_duration_s": total,
        },
        "resumo": {
            "blocos": len(ranges),
            "duracao_s": total,
            "original_s": round(dur, 2),
            "cortado_s": round(dur - total, 2),
            "pausas_preservadas": sum(1 for b in fundidos if b["prepara"]),
            "detalhe": [
                {"ate": b["end"], "folga": b["pausa_seguinte"],
                 "porque": ("prepara '" + b["proxima"] + "'") if b["prepara"] else "rotina"}
                for b in fundidos[:8]
            ],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcript", type=Path)
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--grade", default="eq=contrast=1.06:saturation=1.05",
                    help="filtro de grade; 'auto' usa detect_color.py")
    args = ap.parse_args()

    r = montar(args.transcript, args.video, args.grade)
    args.out.write_text(json.dumps(r["edl"], ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), **r["resumo"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
