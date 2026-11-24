"""modelos_picker.py: what the Estilo tab's "Modelos de edição" section shows and checks.

The preview server calls `catalogo()` (GET /api/modelos) and `media_path()` (GET /modelos-media/<slug>/<file>);
`validate_picks()` is the same rule set the UI applies, kept here so the skill can re-check a saved pick.

Rules (the library's own): at most MAX_ACENTOS modelos with `acento: true`, and one modelo per family in
EXCLUSIVAS (two captions fight for the same words). The demos live in the gallery folder, outside git.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import modelos_demo as D  # noqa: E402
import modelos_receitas as R  # noqa: E402

MEDIA = ("demo.mp4", "poster.jpg")
# What the user sees as the kind of thing a modelo is. A modelo's own `categoria` wins; else its family.
CATEGORIAS = ["Legenda", "Título", "Card", "Formato", "Efeito", "Transição", "Câmera", "Velocidade", "Corte",
              "Estilo pronto"]
CATEGORIA_DA_FAMILIA = {"legenda": "Legenda", "grafismo": "Card", "formato": "Formato", "transicao": "Transição",
                        "camera": "Câmera", "velocidade": "Velocidade", "corte": "Corte"}
EXCLUSIVAS = ("legenda",)
MAX_ACENTOS = R.MAX_ACENTOS


def _galeria() -> Path | None:
    try:
        return D.galeria_root()
    except SystemExit:
        return None


def categoria(m: R.Modelo) -> str:
    if m.nivel == "estilo":
        return "Estilo pronto"
    return m.dados.get("categoria") or CATEGORIA_DA_FAMILIA.get(m.familia, "Efeito")


def resumo(m: R.Modelo, limite: int = 120) -> str:
    """First sentence of "O que é", short enough to read on a card."""
    t = " ".join(D._secao(m, "## O que é").split())
    first = t.split(". ")[0].rstrip(".")
    if len(first) > limite:
        first = first[: limite - 1].rsplit(" ", 1)[0] + "…"
    return first


def catalogo() -> dict:
    g = _galeria()
    out = []
    for slug, m in sorted(R.load_all().items(), key=lambda kv: (kv[1].nivel != "estilo", kv[1].familia, kv[0])):
        out.append({"slug": slug, "nivel": m.nivel, "nome": m.dados.get("nome", slug), "familia": m.familia,
                    "categoria": categoria(m), "resumo": resumo(m), "origem": m.dados.get("origem", ""),
                    "host": m.host, "acento": bool(m.dados.get("acento")),
                    "oQueE": D._secao(m, "## O que é"), "quandoUsar": D._secao(m, "## Quando usar"),
                    "quandoNaoUsar": D._secao(m, "## Quando não usar"),
                    "tipos": m.dados.get("tipos", []),
                    "demo": bool(g and (g / slug / "demo.mp4").exists() and D.demo_status(slug) == "✅")})
    usadas = {m["categoria"] for m in out}
    return {"modelos": out, "categorias": [c for c in CATEGORIAS if c in usadas], "maxAcentos": MAX_ACENTOS,
            "exclusivas": list(EXCLUSIVAS)}


def media_path(slug: str, name: str) -> Path | None:
    """The demo video / poster of a modelo, or None. Only those two files, only inside the gallery."""
    g = _galeria()
    if not g or name not in MEDIA or not slug or "/" in slug or "\\" in slug or slug.startswith("."):
        return None
    p = (g / slug / name).resolve()
    try:
        p.relative_to(g.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def validate_picks(slugs: list[str]) -> tuple[list[str], list[str]]:
    todos = R.load_all()
    probs, ok = [], []
    for s in slugs:
        if s not in todos:
            probs.append(f"modelo '{s}' não existe")
        else:
            ok.append(s)
    acentos = [s for s in ok if todos[s].dados.get("acento")]
    if len(acentos) > MAX_ACENTOS:
        probs.append(f"{len(acentos)} modelos de acento ({', '.join(acentos)}); o limite é {MAX_ACENTOS}")
    for fam in EXCLUSIVAS:
        dup = [s for s in ok if todos[s].familia == fam]
        if len(dup) > 1:
            probs.append(f"mais de um modelo de {fam} ({', '.join(dup)}): escolha um")
    return ok, probs
