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
# Vao minimo entre dois ranges: nunca se tocam nem se sobrepoem.
GAP_MIN_CORTE = 0.10

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


def _quiet_run(niv, limiar: float, t0: float, direction: int, limite_s: float) -> float:
    """Segundos de silencio REAL (janelas abaixo do limiar adaptativo) a partir
    de t0, para frente (+1) ou para tras (-1), ate `limite_s`."""
    from speech_level import JANELA_S
    i = int(t0 / JANELA_S) + (0 if direction > 0 else -1)
    run = 0
    while 0 <= i < len(niv) and run * JANELA_S < limite_s and niv[i] <= limiar:
        run += 1
        i += direction
    return run * JANELA_S


def _niveis(video: Path):
    """(niveis por janela, limiar dB) do audio do video; (None, None) se nao der.

    O limiar vem de speech_level.py (piso + fala medidos), nunca de um dB fixo:
    sala com eco sobe o limiar, gravacao baixa o desce.
    """
    try:
        from speech_level import amplificar, analisar, ler_onda, niveis_por_janela
        a = analisar(video)
        niv = niveis_por_janela(amplificar(ler_onda(video), a["ganho_db"]))
        return (niv, a["limiar_db"]) if len(niv) else (None, None)
    except Exception as e:  # sem numpy/audio: segue so com os tempos do transcript
        print(f"aviso: sem analise de audio ({e}); pads sem aparo por silencio",
              file=sys.stderr)
        return None, None


def montar(transcript: Path, video: Path, grade: str, usar_revisado: bool = True) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    resolvido = Path(transcript)
    drops: list[dict] = []
    if usar_revisado:
        from revise_transcript import drop_ranges, resolve_transcript
        resolvido = resolve_transcript(Path(transcript))
        drops = drop_ranges(resolvido)
    d = json.loads(resolvido.read_text(encoding="utf-8"))
    todas = [w for w in d.get("words", []) if w.get("text", "").strip()]
    if not todas:
        raise SystemExit("transcript sem palavras")
    palavras = [w for w in todas if not w.get("drop")]
    if not palavras:
        raise SystemExit("revisao descartou todas as palavras")

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True).stdout.strip())
    niv, limiar = _niveis(video)
    idx = {id(w): i for i, w in enumerate(todas)}

    def novo(w):
        return {"w": [w], "folga": PAUSA_ROTINA, "prepara": False,
                "proxima": "", "forcado": False}

    # 1) Grupos separados em pausas reais, ou onde ha trecho descartado no meio.
    grupos = [novo(palavras[0])]
    for w in palavras[1:]:
        prev = grupos[-1]["w"][-1]
        gap = float(w["start"]) - float(prev["end"])
        tem_drop = idx[id(w)] - idx[id(prev)] > 1
        if gap >= PAUSA_MINIMA or tem_drop:
            prepara = _prepara_algo(w["text"])
            grupos[-1].update(folga=PAUSA_ANTES_DO_PONTO if prepara else PAUSA_ROTINA,
                              prepara=prepara, proxima=w["text"].strip(), forcado=tem_drop)
            grupos.append(novo(w))
        else:
            grupos[-1]["w"].append(w)

    def fundir(i):  # funde o grupo i+1 em i (a pausa entre eles vira fala)
        a, b = grupos[i], grupos[i + 1]
        a["w"] += b["w"]
        a.update(folga=b["folga"], prepara=b["prepara"], proxima=b["proxima"],
                 forcado=b["forcado"])
        del grupos[i + 1]

    def fala(g):
        return float(g["w"][-1]["end"]) - float(g["w"][0]["start"])

    # 2) Bloco curto demais soa picotado: funde com o vizinho (nunca atravessa drop).
    i = 0
    while i < len(grupos):
        if fala(grupos[i]) < MIN_BLOCO and len(grupos) > 1:
            if i > 0 and not grupos[i - 1]["forcado"]:
                fundir(i - 1)
                i -= 1
                continue
            if i + 1 < len(grupos) and not grupos[i]["forcado"]:
                fundir(i)
                continue
        i += 1

    # 3) A "folga" e a pausa que SOBRA entre as frases (total, nao por lado).
    #    Se cortar deixaria < GAP_MIN_CORTE fora, nao vale cortar: funde.
    i = 0
    while i < len(grupos) - 1:
        g, nx = grupos[i], grupos[i + 1]
        gap = float(nx["w"][0]["start"]) - float(g["w"][-1]["end"])
        if not g["forcado"] and gap - g["folga"] < GAP_MIN_CORTE:
            fundir(i)
            continue
        i += 1

    # 4) Ranges: 60% da folga como cauda do bloco, 40% como ataque do seguinte.
    ranges: list[dict] = []
    for i, g in enumerate(grupos):
        w0, w1 = g["w"][0], g["w"][-1]
        s0, e1 = float(w0["start"]), float(w1["end"])
        prev_full = todas[idx[id(w0)] - 1] if idx[id(w0)] > 0 else None
        next_full = todas[idx[id(w1)] + 1] if idx[id(w1)] + 1 < len(todas) else None
        lim_ini = float(prev_full["end"]) if prev_full else 0.0
        lim_fim = float(next_full["start"]) if next_full else dur
        pad_in = grupos[i - 1]["folga"] * 0.4 if i > 0 else PAUSA_ROTINA
        pad_out = g["folga"] * 0.6 if i < len(grupos) - 1 else PAUSA_ROTINA
        # nunca entra na palavra vizinha (mesmo descartada)
        pad_out = min(pad_out, max(0.0, lim_fim - e1 - 0.03), max(0.0, dur - e1))
        pad_in = min(pad_in, max(0.0, s0 - lim_ini - 0.03), s0)
        if niv is not None:  # so pad em silencio real (limiar adaptativo)
            pad_out = min(pad_out, _quiet_run(niv, limiar, e1, +1, pad_out))
            pad_in = min(pad_in, _quiet_run(niv, limiar, s0, -1, pad_in))
        ranges.append({
            "source": "src",
            "start": round(s0 - pad_in, 2),
            "end": round(e1 + pad_out, 2),
            "quote": " ".join(w["text"].strip() for w in g["w"]),
        })

    # 5) Garantia final: sem sobreposicao nem encosto (arredondamento incluso).
    for a, b in zip(ranges, ranges[1:]):
        if b["start"] - a["end"] < GAP_MIN_CORTE / 2:
            meio = (a["end"] + b["start"]) / 2
            a["end"] = round(meio - GAP_MIN_CORTE / 4, 2)
            b["start"] = round(meio + GAP_MIN_CORTE / 4, 2)
    for a, b in zip(ranges, ranges[1:]):
        assert a["end"] < b["start"], f"ranges encostam: {a} {b}"
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
            "palavras_no_edl": sum(len(g["w"]) for g in grupos),
            "palavras_descartadas_pela_revisao": len(todas) - len(palavras),
            "trechos_drop": len(drops),
            "limiar_silencio_db": limiar,
            "transcript_usado": str(resolvido),
            "pausas_preservadas": sum(1 for g in grupos if g["prepara"]),
            "detalhe": [
                {"ate": ranges[i]["end"], "folga": g["folga"],
                 "porque": ("prepara '" + g["proxima"] + "'") if g["prepara"] else "rotina"}
                for i, g in enumerate(grupos[:8])
            ],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcript", type=Path)
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--raw", action="store_true",
                    help="ignora a revisao (transcripts/.revised) e usa o transcript cru")
    ap.add_argument("--grade", default="eq=contrast=1.06:saturation=1.05",
                    help="filtro de grade; 'auto' usa detect_color.py")
    args = ap.parse_args()

    r = montar(args.transcript, args.video, args.grade, not args.raw)
    args.out.write_text(json.dumps(r["edl"], ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), **r["resumo"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
