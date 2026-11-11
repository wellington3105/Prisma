"""Segunda escuta: recupera trechos com voz que a transcricao principal perdeu.

Problema documentado ("um take que a transcricao perdeu"): o transcritor devolve
palavras para quase tudo e deixa buracos onde ha energia de fala e nenhuma
palavra (VAD que descartou, modelo que desistiu). O corte, que confia no texto,
joga a fala fora sem avisar.

Procedimento, igual para qualquer engine:
  1. janelas de 50 ms acima do limiar adaptativo (speech_level.py) = voz;
  2. voz que nenhuma palavra cobre, por pelo menos MIN_VOZ_S, e dentro de
     [MIN_BURACO_S, MAX_BURACO_S] = buraco;
  3. cada buraco e transcrito de novo com um pouco de contexto (PAD_S) dos dois
     lados — o motor precisa de um pouco de som em volta;
  4. so entram as palavras cujo PONTO MEDIO cai dentro do buraco: o contexto
     reentrega as palavras vizinhas e elas ficam de fora (nada duplica). Palavra
     com mais de MAX_PALAVRA_S e alinhamento esticado sobre silencio: descartada.
As palavras recuperadas levam `recovered: True`.
"""
from __future__ import annotations

import re
from typing import Callable

import numpy as np

from speech_level import JANELA_S, niveis_por_janela

MIN_VOZ_S = 0.45        # voz sem palavra por menos que isto e ruido/respiracao
MIN_BURACO_S = 0.45
MAX_BURACO_S = 25.0     # acima disso e outro problema (falha do motor inteiro)
JUNTAR_ATE_S = 0.25     # pausas menores que isto nao partem um buraco
PAD_S = 0.4
MAX_PALAVRA_S = 1.0     # palavra recuperada mais longa que isto e alinhamento esticado sobre silencio: descarta
MARGEM_PALAVRA_S = 0.05


def _plausivel(w: dict) -> bool:
    """Descarta lixo de decodificacao: caractere invalido ou sem nenhuma letra."""
    t = w.get("word") or ""
    return "�" not in t and re.search(r"[^\W\d_]", t) is not None


def achar_buracos(words: list[dict], onda, taxa: int, limiar_db: float) -> list[tuple[float, float]]:
    """Trechos [a, b] (s) com voz e sem palavra."""
    niveis = niveis_por_janela(onda, taxa)
    if niveis.size == 0:
        return []
    centros = (np.arange(niveis.size) + 0.5) * JANELA_S
    voz = niveis > limiar_db
    for w in words:
        s, e = w.get("start"), w.get("end")
        if s is None or e is None:
            continue
        voz &= ~((centros >= s - MARGEM_PALAVRA_S) & (centros <= e + MARGEM_PALAVRA_S))
    idx = np.flatnonzero(voz)
    if idx.size == 0:
        return []
    corridas: list[list[int]] = []
    for i in idx:
        if corridas and (i - corridas[-1][1]) * JANELA_S <= JUNTAR_ATE_S + JANELA_S:
            corridas[-1][1] = int(i)
            corridas[-1][2] += 1
        else:
            corridas.append([int(i), int(i), 1])
    timed = [w for w in words if w.get("start") is not None and w.get("end") is not None]
    ends = [w["end"] for w in timed]
    starts = [w["start"] for w in timed]
    out: list[tuple[float, float]] = []
    for i0, i1, n in corridas:
        a, b = i0 * JANELA_S, (i1 + 1) * JANELA_S
        if n * JANELA_S < MIN_VOZ_S or b - a < MIN_BURACO_S:
            continue
        # Speech usually trails off at the edges of a lost stretch (quieter than
        # the threshold), so listen to the WHOLE word-free span around the voiced
        # run, up to the neighbouring words — not only to the loud part.
        antes = [en for en in ends if en <= a + 1e-6]
        depois = [st for st in starts if st >= b - 1e-6]
        lo = max(antes) if antes else 0.0
        hi = min(depois) if depois else len(onda) / taxa
        if hi - lo <= MAX_BURACO_S:
            a, b = min(a, lo), max(b, hi)
        if b - a <= MAX_BURACO_S and not (out and a < out[-1][1]):
            out.append((a, b))
        elif out and a < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
    return out


def segunda_escuta(
    words: list[dict],
    onda,
    taxa: int,
    limiar_db: float,
    transcrever_trecho: Callable[[float, float], list[dict]],
    verbose: bool = False,
) -> tuple[list[dict], dict]:
    """Devolve (palavras, {gaps, words}). `transcrever_trecho(a, b)` recebe um
    intervalo em segundos (ja com o contexto) e devolve palavras
    {word,start,end} em tempo ABSOLUTO."""
    total = len(onda) / taxa
    buracos = achar_buracos(words, onda, taxa, limiar_db)
    novas: list[dict] = []
    for a, b in buracos:
        try:
            got = transcrever_trecho(max(0.0, a - PAD_S), min(total, b + PAD_S))
        except Exception as e:  # um buraco que falha nao derruba a transcricao
            if verbose:
                print(f"    segunda escuta {a:.2f}-{b:.2f}s falhou: {e}", flush=True)
            continue
        dentro = [dict(w, recovered=True) for w in got
                  if a <= (w["start"] + w["end"]) / 2 < b and w["end"] - w["start"] <= MAX_PALAVRA_S and _plausivel(w)]
        if verbose:
            print(f"    segunda escuta {a:7.2f}-{b:7.2f}s: {len(dentro)} palavra(s)", flush=True)
        novas += dentro
    merged = sorted(words + novas, key=lambda w: (w["start"], w["end"])) if novas else words
    return merged, {"gaps": len(buracos), "words": len(novas)}
