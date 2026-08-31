"""Gera cartões de dados como PNG, para ancorar na cena 3D.

OPUS-VFX-3D. Os elementos que a referência do Instagram mostra flutuando pelo
ambiente — "62%", "2.4K", "Squats", "Hiit training" — são cartões pequenos com
um número grande e um rótulo. Aqui eles viram PNG com transparência, e o
`TrackedScene` os ancora como qualquer outro objeto.

Por que PNG e não texto 3D: o caminho via `troika-three-text` está fechado (o
Web Worker que gera SDF não conclui no Chromium headless do Remotion — quatro
tentativas, todas com quadro sem glifo). Um cartão rasterizado ancorado num
plano tem a mesma perspectiva e a mesma âncora; o que perde é escalar sem
borrar, e num cartão pequeno isso não aparece.

Usa Pillow, que já vem com as dependências da skill.

Uso:
    uv run python helpers/make_card.py "62%" --label "conversão" --out card.png
    uv run python helpers/make_card.py "2.4K" --label "seguidores" --accent "#7fd4ff"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw, ImageFont

# Proporção e escala pensadas para o cartão ser lido em 1080x1920 quando ocupa
# ~25% da largura. Gerar grande e deixar o 3D reduzir é mais nítido que o
# inverso.
W, H = 640, 400
RADIUS = 46


def _font(size: int, bold: bool = False):
    """Fonte do sistema, com fallback explícito.

    Windows tem Segoe UI; um Linux mínimo pode não ter fonte nenhuma, e nesse
    caso o Pillow devolve a bitmap embutida — feia, mas melhor que quebrar o
    render por causa de um cartão.
    """
    for nome in (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]):
        try:
            return ImageFont.truetype(nome, size)
        except OSError:
            continue
    try:
        return ImageFont.truetype(
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _centered(d: ImageDraw.ImageDraw, y: int, txt: str, font, fill):
    box = d.textbbox((0, 0), txt, font=font)
    d.text(((W - (box[2] - box[0])) / 2 - box[0], y), txt, font=font, fill=fill)
    return box[3] - box[1]


def make_card(value: str, label: str | None, accent: str, dark: bool) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Vidro fosco: um retângulo semi-transparente. A borda é o que dá
    # legibilidade sobre fundo claro — sem ela o cartão some, o mesmo defeito
    # que o GlassSlab teve antes de calibrar.
    corpo = (14, 20, 32, 190) if dark else (255, 255, 255, 168)
    d.rounded_rectangle([6, 6, W - 6, H - 6], RADIUS, fill=corpo,
                        outline=accent, width=5)

    # Número grande, rótulo pequeno abaixo. A hierarquia é o conteúdo: o
    # espectador lê o valor num relance e o rótulo se quiser contexto.
    fg = (255, 255, 255, 255) if dark else (16, 22, 34, 255)

    # Tamanho ajustado à largura disponível. Com corpo fixo, "62%" cabia e
    # "Squats" transbordava pelas bordas — e um cartão com a palavra cortada é
    # pior que um cartão menor.
    disponivel = W - 2 * RADIUS
    tam = 168
    while tam > 48:
        f = _font(tam, bold=True)
        box = d.textbbox((0, 0), value, font=f)
        if box[2] - box[0] <= disponivel:
            break
        tam -= 6
    fonte = _font(tam, bold=True)

    if label:
        _centered(d, 96 + (168 - tam) // 2, value, fonte, fg)
        _centered(d, 288, label.upper(), _font(46), accent)
    else:
        _centered(d, 140 + (168 - tam) // 2, value, fonte, fg)
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("value", help='o número/destaque, ex: "62%%"')
    ap.add_argument("--label", help="rótulo abaixo do valor")
    ap.add_argument("--accent", default="#7fd4ff", help="cor da borda e do rótulo")
    ap.add_argument("--dark", action="store_true",
                    help="cartão escuro (para cenas claras)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    img = make_card(args.value, args.label, args.accent, args.dark)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"{out}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
