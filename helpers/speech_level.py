"""Nivel da fala, ganho de analise e limiar de silencio automatico.

Dois defeitos medidos, um em cada ponta:

  - Sala com eco (showroom CLA200): o silencedetect fixo a -33 dB nao achou
    NENHUMA pausa, porque a reverberacao mantem o "silencio" acima disso. Foi
    preciso calibrar a mao em -23 dB / 0,45 s.
  - Gravacao muito baixa (fala a ~-43 dB RMS): tudo cai abaixo de -33 dB, o
    video inteiro vira "silencio" e o transcritor devolve zero palavras.

A regra. Mede-se o audio em janelas de 50 ms (RMS em dBFS):
  - nivel da fala = percentil 90 (as janelas mais altas sao a voz);
  - piso de ruido = percentil 10 (as mais baixas sao pausa/ambiente).

(a) GANHO DE ANALISE — somado SO ao audio que o transcritor e o detector de
    silencio escutam; o video cortado nunca muda de volume. Leva a fala ao alvo
    (-20 dB) com freios: so se faltarem >= 6 dB (gravacao normal fica
    intocada), nunca acima do que o topo (p99) permite sem passar de -10 dB,
    nunca mais que 30 dB (alem disso nao ha fala, ha silencio), e com limitador
    (alimiter) na cadeia do ffmpeg para pico nao estourar.

(b) LIMIAR DE SILENCIO — entre o piso e a fala: piso + K * (fala - piso),
    preso a [-45, -18] dB e, no maximo, a FOLGA_MIN_DB abaixo da fala. Em sala
    com eco o piso e alto, entao o limiar sobe junto; em gravacao silenciosa o
    limiar desce junto com a fala.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ALVO_DA_FALA_DB = -20.0
GANHO_MINIMO_DB = 6.0
GANHO_MAXIMO_DB = 30.0
TOPO_MAXIMO_DB = -10.0       # p99 depois do ganho nunca passa disto
JANELA_S = 0.05
MINIMO_DE_JANELAS = 20       # < 1 s nao da percentil que preste
PERCENTIL_FALA = 90
PERCENTIL_PISO = 10
K_LIMIAR = 0.5               # posicao do limiar entre piso (0) e fala (1)
LIMIAR_MIN_DB = -45.0
LIMIAR_MAX_DB = -18.0
FOLGA_MIN_DB = 8.0           # limiar fica pelo menos isto abaixo da fala
LIMIAR_PADRAO_DB = -33.0     # quando nao da para medir (audio curto/mudo)
TAXA = 16_000


def ler_onda(media: Path, taxa: int = TAXA):
    """Audio como float32 mono em `taxa` Hz (via ffmpeg)."""
    import numpy as np
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-i", str(media),
         "-map", "0:a:0", "-ac", "1", "-ar", str(taxa), "-f", "s16le", "-"],
        capture_output=True, check=False)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"nao consegui ler o audio de {Path(media).name}")
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def niveis_por_janela(onda, taxa: int = TAXA, janela_s: float = JANELA_S):
    """RMS em dBFS de cada janela de `janela_s` segundos."""
    import numpy as np
    n = max(1, int(taxa * janela_s))
    q = int(onda.size // n)
    if q < 1:
        return np.zeros(0)
    rms = np.sqrt((onda[:q * n].reshape(q, n).astype(np.float64) ** 2).mean(axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-9))


def medir(niveis) -> dict | None:
    """{fala_db, piso_db, topo_db}; None se houver janelas de menos."""
    import numpy as np
    if niveis is None or len(niveis) < MINIMO_DE_JANELAS:
        return None
    return {"fala_db": float(np.percentile(niveis, PERCENTIL_FALA)),
            "piso_db": float(np.percentile(niveis, PERCENTIL_PISO)),
            "topo_db": float(np.percentile(niveis, 99))}


def ganho_de_analise(m: dict | None) -> float:
    """dB a somar ao audio da analise; 0.0 quando nao vale mexer."""
    if not m:
        return 0.0
    g = min(ALVO_DA_FALA_DB - m["fala_db"], TOPO_MAXIMO_DB - m["topo_db"], GANHO_MAXIMO_DB)
    return round(float(g), 1) if g >= GANHO_MINIMO_DB else 0.0


def limiar_de_silencio(m: dict | None, ganho_db: float = 0.0) -> float:
    """Limiar do silencedetect (dB), no mesmo referencial do audio ja com ganho."""
    if not m:
        return LIMIAR_PADRAO_DB
    fala, piso = m["fala_db"] + ganho_db, m["piso_db"] + ganho_db
    lim = piso + K_LIMIAR * (fala - piso)
    lim = min(lim, fala - FOLGA_MIN_DB)
    return round(max(LIMIAR_MIN_DB, min(LIMIAR_MAX_DB, lim)), 1)


def filtro_de_ganho(ganho_db: float) -> str:
    """Trecho de `-af` do ffmpeg: ganho + limitador, ou '' sem ganho."""
    if ganho_db <= 0:
        return ""
    return f"volume={ganho_db:.1f}dB,alimiter=limit=0.95:level=disabled"


def amplificar(onda, ganho_db: float):
    """Onda com o ganho e um limitador simples (clip suave em 0.95)."""
    import numpy as np
    if ganho_db <= 0:
        return onda
    return np.tanh(onda * float(10 ** (ganho_db / 20.0)) / 0.95) * 0.95


def analisar(media: Path) -> dict:
    """Mede um arquivo e devolve tudo que o transcritor/detector precisam."""
    try:
        m = medir(niveis_por_janela(ler_onda(media)))
    except RuntimeError:
        m = None
    ganho = ganho_de_analise(m)
    return {"medida": m, "ganho_db": ganho, "limiar_db": limiar_de_silencio(m, ganho)}


if __name__ == "__main__":
    import sys
    import json
    print(json.dumps(analisar(Path(sys.argv[1])), indent=2))
