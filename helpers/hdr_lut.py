"""LUT 3D (.cube) HDR -> Rec.709 SDR, para ffmpeg sem zscale.

O caminho padrao do render.py e zscale+tonemap. Alguns builds do ffmpeg nao
trazem o zscale (libzimg); sem ele o render de uma fonte HLG/PQ falhava. Este
modulo gera, uma vez, um .cube que faz o mesmo trabalho aproximado e que o
`lut3d` (presente em qualquer build) aplica:

  codigo HLG/PQ BT.2020  ->  luz linear  ->  (HLG: OOTF gamma 1,2)  ->
  primarias BT.2020 -> BT.709  ->  curva Hable por canal  ->  OETF BT.709

Uso (a cadeia fica no render.py): converter para RGB tagueado BT.2020 de 10
bits, `lut3d=file=<cube>:interp=tetrahedral`, depois para yuv BT.709 tv.
O .cube e gravado em helpers/_cache/ e reaproveitado.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

TAMANHO = 33
CACHE = Path(__file__).resolve().parent / "_cache"
# Luz de referencia: 1.0 linear = 100 nits (mesmo npl=100 do zscale).
BRANCO_NITS = 100.0
PICO_HLG_NITS = 1000.0
PICO_TONEMAP = 10.0  # pico do sinal (em unidades de 100 nits) que o Hable comprime
# Calibrado contra a saida do zscale (media de uma cena real marcada como HLG):
# 1.7 zera o desvio medio de brilho; 1.0 ficava ~21/255 mais escuro.
EXPOSICAO = 1.7

_M_2020_709 = np.array([[1.6605, -0.5876, -0.0728],
                        [-0.1246, 1.1329, -0.0083],
                        [-0.0182, -0.1006, 1.1187]])


def _hlg_para_linear(e):
    a, b = 0.17883277, 0.28466892
    c = 0.55991073
    return np.where(e <= 0.5, e * e / 3.0, (np.exp((e - c) / a) + b) / 12.0)


def _pq_para_nits(e):
    m1, m2 = 2610 / 16384, 2523 / 4096 * 128
    c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    p = np.power(np.clip(e, 0, 1), 1 / m2)
    return 10000.0 * np.power(np.maximum(p - c1, 0) / (c2 - c3 * p), 1 / m1)


def _hable(x):
    a, b, c, d, e, f = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30
    return (x * (x * a + b * c) + d * e) / (x * (x * a + b) + d * f) - e / f


def _oetf_709(l):
    l = np.clip(l, 0, 1)
    return np.where(l < 0.018, 4.5 * l, 1.099 * np.power(l, 0.45) - 0.099)


def gerar_cubo(transferencia: str = "hlg", exposicao: float = EXPOSICAO) -> str:
    """Texto de um .cube. transferencia: 'hlg' ou 'pq'."""
    n = TAMANHO
    eixo = np.linspace(0.0, 1.0, n)
    # cube: o indice vermelho varia mais rapido (ordem R,G,B com R no laco interno)
    b, g, r = np.meshgrid(eixo, eixo, eixo, indexing="ij")
    rgb = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    if transferencia == "pq":
        lin = _pq_para_nits(rgb) / BRANCO_NITS
    else:
        cena = _hlg_para_linear(rgb)
        y = (0.2627 * cena[:, 0] + 0.6780 * cena[:, 1] + 0.0593 * cena[:, 2])[:, None]
        lin = cena * np.power(np.maximum(y, 1e-6), 0.2) * (PICO_HLG_NITS / BRANCO_NITS)
    lin = np.clip(lin @ _M_2020_709.T, 0, None) * exposicao
    saida = _oetf_709(_hable(lin) / _hable(np.float64(PICO_TONEMAP)))
    linhas = [f"# prisma hdr->709 ({transferencia}, hable)", f"TITLE \"prisma_{transferencia}_to_709\"",
              f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    linhas += [f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in np.clip(saida, 0, 1)]
    return "\n".join(linhas) + "\n"


def cubo(transferencia: str = "hlg") -> Path:
    """Caminho do .cube (gera e guarda em helpers/_cache/ na primeira vez)."""
    tr = "pq" if transferencia in ("pq", "smpte2084") else "hlg"
    dest = CACHE / f"hdr_{tr}_to_709_hable.cube"
    if not dest.exists():
        CACHE.mkdir(exist_ok=True)
        dest.write_text(gerar_cubo(tr), encoding="utf-8")
    return dest
