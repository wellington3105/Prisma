"""Tempo até o pico de um efeito sonoro — medido no arquivo, nunca suposto (F3.0).

Todo agendador de SFX do Prisma coloca o arquivo pelo PRIMEIRO sample; um som
cujo golpe está no meio (whoosh, whip-hit, riser) bate depois do evento.
Medido 2026-11-03: `whip_hit.wav` tem o golpe em 0,29 s, e o whip-pan do PPF X6
soava ~9 frames depois da imagem nas 4 transições. Com `align`:

    "start" — o arquivo começa no evento (clique, pop, ding)
    "peak"  — o golpe cai no evento (impacto, whoosh, whip) → at − pico
    "end"   — o arquivo termina no evento (riser)           → at − duração

    from sfx_peak import shift
    at_efetivo = at - shift(path, "peak")
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 48000
HOP = 0.005


@lru_cache(maxsize=256)
def _measure(path: str) -> tuple[float, float]:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    if not len(x):
        return 0.0, 0.0
    n = int(HOP * SR)
    k = max(1, len(x) // n)
    env = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(1)) if len(x) >= n else np.abs(x)
    return float(np.argmax(env) * HOP), len(x) / SR


def peak_time(path: Path | str) -> float:
    return _measure(str(path))[0]


def duration(path: Path | str) -> float:
    return _measure(str(path))[1]


def shift(path: Path | str, align: str | None) -> float:
    """Quanto adiantar o início do arquivo para o alinhamento pedido."""
    if align == "peak":
        return peak_time(path)
    if align == "end":
        return duration(path)
    return 0.0
