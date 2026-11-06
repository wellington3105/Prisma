"""Engine opcional do transcribe.py: Parakeet TDT 0.6B v3 via sherpa-onnx (CPU).

Modelo: NVIDIA Parakeet TDT 0.6B v3 (CC-BY-4.0), versao int8 ONNX.
Runtime: sherpa-onnx (Apache-2.0). Instalar: `uv sync --extra parakeet`.
Arquivos do modelo (encoder/decoder/joiner .int8.onnx + tokens.txt) numa pasta:
  $PRISMA_PARAKEET_DIR, ou ~/.edvid/modelos/parakeet-tdt-0.6b-v3-int8, ou
  ~/.prisma/modelos/parakeet-tdt-0.6b-v3-int8. Veja references/transcription.md.

Restricoes tratadas aqui:
  - O v3 detecta o idioma sozinho e, em trecho longo, "escorrega" para outro
    (portugues vira espanhol/ingles): o audio e processado em pedacos de ~60 s
    cortados em PAUSAS (nunca no meio de uma palavra).
  - O encoder tem limite (~13 min) e a memoria cresce com o trecho: o pedaco
    nunca passa de PEDACO_TETO_S, mesmo sem pausa para cortar.
  - O motor devolve tokens com instante (frames de 80 ms), nao palavras: aqui
    os tokens viram palavras e o fim da palavra e o ultimo token + CAUDA_S.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import numpy as np

TAXA = 16_000
FRAME_S = 0.08
CAUDA_S = 0.08
PEDACO_ALVO_S = 60.0
PEDACO_TETO_S = 120.0
PAUSA_MIN_S = 0.25
ARQUIVOS = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
NOME_DA_PASTA = "parakeet-tdt-0.6b-v3-int8"


def pasta_do_modelo() -> Path | None:
    cands = []
    if os.environ.get("PRISMA_PARAKEET_DIR"):
        cands.append(Path(os.environ["PRISMA_PARAKEET_DIR"]))
    home = Path.home()
    cands += [home / ".edvid" / "modelos" / NOME_DA_PASTA,
              home / ".prisma" / "modelos" / NOME_DA_PASTA]
    return next((c for c in cands if all((c / f).exists() for f in ARQUIVOS)), None)


def _pausas(onda, limiar_db: float) -> list[tuple[float, float]]:
    """Pausas (s) = janelas de 50 ms abaixo do limiar, >= PAUSA_MIN_S seguidas."""
    from speech_level import JANELA_S, niveis_por_janela
    niv = niveis_por_janela(onda, TAXA)
    mudo = niv <= limiar_db
    out, ini = [], None
    for i, m in enumerate(np.append(mudo, False)):
        if m and ini is None:
            ini = i
        elif not m and ini is not None:
            if (i - ini) * JANELA_S >= PAUSA_MIN_S:
                out.append((ini * JANELA_S, i * JANELA_S))
            ini = None
    return out


def pedacos(duracao: float, pausas: list[tuple[float, float]],
            alvo: float = PEDACO_ALVO_S, teto: float = PEDACO_TETO_S) -> list[tuple[float, float]]:
    """Fatias que comecam e terminam em pausa, perto de `alvo` s cada; sem pausa
    a mao, corta no alvo mesmo (perder uma silaba vale menos que estourar)."""
    if duracao <= 0:
        return []
    pontos = [0.0]
    while duracao - pontos[-1] > alvo * 1.5:
        ini = pontos[-1]
        lim = min(ini + teto, ini + alvo * 1.5)
        meios = [(a + b) / 2 for a, b in pausas if ini + alvo * 0.5 <= (a + b) / 2 <= lim]
        pontos.append(min(meios, key=lambda t: abs(t - (ini + alvo))) if meios
                      else min(ini + alvo, duracao))
    pontos.append(duracao)
    return [(a, b) for a, b in zip(pontos, pontos[1:]) if b > a]


def tokens_para_palavras(tokens: list[str], instantes: list[float]) -> list[dict]:
    """Tokens SentencePiece -> palavras {word,start,end}. O marcador de inicio de
    palavra chega como ESPACO na frente do token."""
    ws: list[dict] = []
    for tok, t in zip(tokens, instantes):
        if tok.startswith(" ") or not ws:
            ws.append({"word": tok.strip(), "start": float(t), "last": float(t)})
        else:
            ws[-1]["word"] += tok
            ws[-1]["last"] = float(t)
    for cur, nxt in zip(ws, ws[1:]):
        cur["end"] = min(nxt["start"], cur["last"] + CAUDA_S)
    if ws:
        ws[-1]["end"] = ws[-1]["last"] + CAUDA_S
    return [{"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
            for w in ws if w["word"].strip()]


def carregar(threads: int = 0):
    try:
        import sherpa_onnx
    except ImportError as e:
        raise RuntimeError("sherpa-onnx nao instalado. Rode: uv sync --extra parakeet") from e
    md = pasta_do_modelo()
    if md is None:
        raise RuntimeError(
            "modelo Parakeet nao encontrado. Coloque os 4 arquivos (encoder/decoder/joiner "
            f".int8.onnx + tokens.txt) em $PRISMA_PARAKEET_DIR ou ~/.prisma/modelos/{NOME_DA_PASTA} "
            "— veja references/transcription.md (nao baixa sozinho).")
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=threads or max(1, (os.cpu_count() or 4) // 2), sample_rate=TAXA,
        feature_dim=128, decoding_method="greedy_search", model_type="nemo_transducer")


def decodificar(rec, onda, a: float, b: float) -> list[dict]:
    """Palavras de onda[a:b] em tempo ABSOLUTO. Sem somar `a` o video inteiro
    se empilha nos primeiros segundos."""
    stream = rec.create_stream()
    stream.accept_waveform(TAXA, onda[int(a * TAXA):int(b * TAXA)])
    rec.decode_stream(stream)
    r = stream.result
    return tokens_para_palavras(list(r.tokens), [float(t) + a for t in r.timestamps])


def call_parakeet(onda, limiar_db: float, verbose: bool = False, second_listen: bool = True) -> dict:
    """`onda`: float32 mono 16 kHz, ja com o ganho de analise. Mesmo formato de
    saida do call_whisperx ({words,text,language,_aligned})."""
    from second_listen import segunda_escuta
    rec = carregar()
    dur = len(onda) / TAXA
    words: list[dict] = []
    for a, b in pedacos(dur, _pausas(onda, limiar_db)):
        words += decodificar(rec, onda, a, b)
        if verbose:
            print(f"    pedaco {a:6.1f}-{b:6.1f}s ({len(words)} palavras)", flush=True)
    for p, n in zip(words, words[1:]):
        if n["start"] < p["start"] - FRAME_S:
            raise RuntimeError(f"tempo voltou de {p['start']:.2f}s para {n['start']:.2f}s entre pedacos")
    stats = None
    if second_listen:
        words, stats = segunda_escuta(words, onda, TAXA, limiar_db,
                                      lambda a, b: decodificar(rec, onda, a, b), verbose)
    return {"words": words, "text": " ".join(w["word"] for w in words),
            "language": "", "_aligned": True, "_second_listen": stats}
