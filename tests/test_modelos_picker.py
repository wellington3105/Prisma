"""The Estilo tab's "Modelos de edição" section: catalogue for the UI, media route, digest, rules.

    python tests/test_modelos_picker.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))


def _galeria(d: Path, with_demo: list[str]) -> None:
    for s in with_demo:
        (d / s).mkdir(parents=True, exist_ok=True)
        (d / s / "demo.mp4").write_bytes(b"x")
        (d / s / "poster.jpg").write_bytes(b"x")
        (d / s / "gates.json").write_text(json.dumps([{"id": "G0", "status": "PASS"}, {"id": "G2", "status": "PASS"}]),
                                          encoding="utf-8")


def test_catalogo_lists_every_modelo_with_demo_flag():
    import modelos_picker as P
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _galeria(d, ["whip-pan"])
        os.environ["PRISMA_MODELOS_GALERIA"] = str(d)
        try:
            cat = P.catalogo()
        finally:
            os.environ.pop("PRISMA_MODELOS_GALERIA")
    by = {m["slug"]: m for m in cat["modelos"]}
    assert {"whip-pan", "card-ficha", "titulo-misto", "legenda-mista", "antes-depois"} <= set(by)
    assert by["whip-pan"]["demo"] is True and by["card-ficha"]["demo"] is False
    m = by["titulo-misto"]
    assert m["nome"] and m["familia"] == "grafismo" and m["host"] == "cena" and m["acento"] is True
    assert m["oQueE"] and m["quandoUsar"] and m["quandoNaoUsar"]
    assert cat["maxAcentos"] == 3
    assert "legenda" in cat["exclusivas"], "uma legenda por vez"


def test_media_path_only_serves_demo_files_inside_the_gallery():
    import modelos_picker as P
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _galeria(d, ["whip-pan"])
        os.environ["PRISMA_MODELOS_GALERIA"] = str(d)
        try:
            assert P.media_path("whip-pan", "demo.mp4") == d / "whip-pan" / "demo.mp4"
            assert P.media_path("whip-pan", "poster.jpg") == d / "whip-pan" / "poster.jpg"
            assert P.media_path("whip-pan", "gates.json") is None
            assert P.media_path("..", "demo.mp4") is None
            assert P.media_path("whip-pan/../../x", "demo.mp4") is None
            assert P.media_path("nao-existe", "demo.mp4") is None
        finally:
            os.environ.pop("PRISMA_MODELOS_GALERIA")


def test_validate_picks_enforces_the_rules():
    import modelos_picker as P
    ok, probs = P.validate_picks(["titulo-misto", "legenda-mista", "whip-pan"])
    assert probs == [] and ok
    _, probs = P.validate_picks(["legenda-mista", "legenda-palavra-chave"])
    assert any("legenda" in p for p in probs), probs
    acentos = [s for s, m in __import__("modelos_receitas").load_all().items() if m.dados.get("acento")][:4]
    _, probs = P.validate_picks(acentos)
    assert any("acento" in p for p in probs), probs
    _, probs = P.validate_picks(["nao-existe"])
    assert any("nao-existe" in p for p in probs), probs


def test_style_digest_reports_the_picked_modelos_and_how_to_apply():
    import watch_edits as W
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "preview_style.json"
        f.write_text(json.dumps({"edit": "limpa", "headline": "outline", "captions": "karaoke", "elements": {},
                                 "modelos": ["titulo-misto", "whip-pan"],
                                 "modelosNames": ["Título misto", "Whip pan"]}), encoding="utf-8")
        out = W.style_digest(f)
    assert "modelos" in out and "titulo-misto" in out and "whip-pan" in out
    assert "modelos.py apply" in out, "o digest diz como aplicar"
    assert "cenas.py render" in out


def test_style_digest_without_modelos_is_unchanged():
    import watch_edits as W
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "preview_style.json"
        f.write_text(json.dumps({"edit": "limpa", "headline": "outline", "captions": "karaoke", "elements": {}}),
                     encoding="utf-8")
        assert "modelos" not in W.style_digest(f)


def test_app_has_the_section_and_sends_the_picks():
    html = (SKILL / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    js = (SKILL / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert 'id="optModelos"' in html
    assert "/api/modelos" in js and "modelosNames" in js and "modelos: [" in js.replace("modelos: S.style.modelos", "modelos: [")


if __name__ == "__main__":
    fails = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"PASS {name}")
            except (Exception, SystemExit) as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
