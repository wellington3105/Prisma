"""Cenas: self-contained HyperFrames scenes built from data (host "cena" of the modelos library).

    python tests/test_cenas.py

Builds projects only (no render): fast, no network, no client media.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))


def _photo(d: Path) -> Path:
    f = d / "carro.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xdddddd:s=800x600", "-frames:v", "1",
                    str(f)], check=True)
    return f


def _dados(d: Path, **kw) -> dict:
    base = {"foto": str(_photo(d)), "titulo": "Porsche 911", "versao": "GT3 RS",
            "pilulas": [{"icone": "cor", "texto": "Cinza Gelo", "cor": "#d9dde0"},
                        {"icone": "cronometro", "texto": "3,2s"}, {"icone": "cambio", "texto": "manual"}],
            "frase": "Do 911 ao hipercarro, movido por uma obsessão: desempenho.", "assinatura": "@sualoja"}
    base.update(kw)
    return base


def test_build_writes_a_hyperframes_project():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("card-ficha", _dados(d), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert 'data-composition-id="main"' in html
        assert 'data-width="1080"' in html and 'data-height="1920"' in html
        dur = float(re.search(r'data-duration="([\d.]+)"', html).group(1))
        assert abs(dur - cenas.CENAS["card-ficha"]["duracao"]) < 1e-6, dur
        assert (out / "assets" / "media" / "carro.jpg").exists()
        assert "Porsche 911" in html and "GT3 RS" in html and "@sualoja" in html
        assert html.count('class="pilula"') == 3
        assert 'window.__timelines["main"]' in html
        assert "cdn.jsdelivr" not in html, "GSAP local, não CDN (check offline)"
        assert (out / "assets" / "vendor" / "gsap.min.js").exists()


def test_text_is_escaped():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("card-ficha", _dados(d, titulo="A<b>&C"), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "A&lt;b&gt;&amp;C" in html and "A<b>&C" not in html


def test_typewriter_has_one_span_per_char():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        frase = "Movido por uma obsessão."
        out = cenas.build("card-ficha", _dados(d, frase=frase), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert html.count('class="ch"') == len(frase)


def test_without_sentence_is_shorter_and_has_no_typing():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("card-ficha", _dados(d, frase=""), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        dur = float(re.search(r'data-duration="([\d.]+)"', html).group(1))
        assert dur < cenas.CENAS["card-ficha"]["duracao"]
        assert 'class="ch"' not in html


def test_validate_rejects_bad_data():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ok = _dados(d)
        assert cenas.validate("card-ficha", ok) == []
        probs = cenas.validate("card-ficha", dict(ok, foto=str(d / "nao.jpg")))
        assert any("foto" in p for p in probs), probs
        probs = cenas.validate("card-ficha", dict(ok, pilulas=ok["pilulas"] + [{"icone": "km", "texto": "0 km"}]))
        assert any("pílulas" in p for p in probs), probs
        probs = cenas.validate("card-ficha", dict(ok, pilulas=[{"icone": "foguete", "texto": "x"}]))
        assert any("foguete" in p for p in probs), probs
        probs = cenas.validate("card-ficha", dict(ok, titulo=""))
        assert any("titulo" in p for p in probs), probs
        assert cenas.validate("nao-existe", ok)


def test_scene_is_pinned_to_the_cena_release():
    """0.8.93 leaves a 4-8 px black strip at the right edge of every frame; 0.9.85 does not."""
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("card-ficha", _dados(d), d / "proj")
        pkg = json.loads((out / "package.json").read_text(encoding="utf-8"))
        assert pkg["prisma"]["hyperframes"] == cenas.CENA_HF_PIN != "0.8.93"


def test_card_takes_its_tone_from_the_photo():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("card-ficha", _dados(d), d / "proj")      # photo is flat #dddddd
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "rgb(221, 221, 221)" in html, "card começa no tom do rodapé da foto"
        out = cenas.build("card-ficha", _dados(d, fundo="#123456"), d / "proj2")
        assert "background: #123456" in (out / "index.html").read_text(encoding="utf-8")


def test_cli_build():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        f = d / "dados.json"
        f.write_text(json.dumps(_dados(d), ensure_ascii=False), encoding="utf-8")
        p = subprocess.run([sys.executable, str(HELPERS / "cenas.py"), "build", "card-ficha", str(f), "-o", str(d / "p")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert p.returncode == 0, p.stdout + p.stderr
        assert (d / "p" / "index.html").exists()


def test_modelos_check_knows_host_cena():
    import modelos_receitas as R
    probs = R.check()
    assert not [p for p in probs if "card-ficha" in p], probs
    m = R.load("card-ficha")
    assert m.host == "cena" and m.dados["cena"] == "card-ficha"


def test_modelos_apply_cena_builds_project_from_params():
    import modelos_receitas as R
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        foto = _photo(d)
        R.apply_file("card-ficha", d / "edit", None, {"foto": str(foto), "titulo": "Jeep Compass", "versao": "Limited",
                                                      "assinatura": "@sualoja"})
        proj = d / "edit" / "cenas" / "card-ficha"
        html = (proj / "index.html").read_text(encoding="utf-8")
        assert "Jeep Compass" in html and "Limited" in html
        dados = json.loads((proj / "dados.json").read_text(encoding="utf-8"))
        assert dados["titulo"] == "Jeep Compass" and dados["pilulas"], dados


# ---------------------------------------------------------------- titulo-misto
def _clip(d: Path, dur: float = 5.0) -> Path:
    f = d / "fala.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=720x1280:d={dur}:r=30",
                    "-f", "lavfi", "-i", f"sine=f=220:d={dur}", "-shortest", "-pix_fmt", "yuv420p", str(f)], check=True)
    return f


def _titulo(d: Path, **kw) -> dict:
    base = {"video": str(_clip(d)), "de": 0.5, "ate": 4.5, "esquerda": "Faça", "direita": "melhores",
            "palavra": "Roteiros", "sub": "com esta fórmula", "cards": [str(_photo(d))]}
    base.update(kw)
    return base


def test_titulo_misto_builds_over_the_clip_with_its_sound():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("titulo-misto", _titulo(d), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        dur = float(re.search(r'data-duration="([\d.]+)"', html).group(1))
        assert abs(dur - 4.0) < 1e-6, dur
        assert re.search(r'<video[^>]+data-media-start="0.5"[^>]+muted', html), "o vídeo entra mudo, a partir de 'de'"
        assert re.search(r'<audio[^>]+data-media-start="0.5"', html), "o som original vem num <audio> separado"
        assert (out / "assets" / "media" / "fala.mp4").exists()
        for w in ("Faça", "melhores", "Roteiros"):
            assert w in html
        assert html.count('class="sw"') == 3, "sublinha palavra por palavra"
        assert html.count('class="cartao"') == 1
        assert html.count('class="px"') >= 6, "blocos de pixel na entrada da palavra gigante"


def test_titulo_misto_validates():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ok = _titulo(d)
        assert cenas.validate("titulo-misto", ok) == []
        assert any("palavra" in p for p in cenas.validate("titulo-misto", dict(ok, palavra="")))
        assert any("video" in p for p in cenas.validate("titulo-misto", dict(ok, video=str(d / "x.mp4"))))
        assert any("ate" in p for p in cenas.validate("titulo-misto", dict(ok, de=3, ate=2)))
        assert any("cards" in p for p in cenas.validate("titulo-misto", dict(ok, cards=[ok["cards"][0]] * 3)))
        assert any("campo" in p for p in cenas.validate("titulo-misto", dict(ok, titulo="x")))


def test_titulo_misto_accent_word_is_the_serif_italic():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("titulo-misto", _titulo(d, acento="fórmula", sub="com esta fórmula"), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert re.search(r'class="sw acento"[^>]*>fórmula<', html), html[-3000:]
        assert "PrismaLora" in html


def test_modelos_apply_titulo_misto_splits_cards():
    import modelos_receitas as R
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        clip, foto = _clip(d), _photo(d)
        R.apply_file("titulo-misto", d / "edit", None, {"video": str(clip), "ate": "3.5", "palavra": "Garantia",
                                                        "cards": f"{foto}|{foto}"})
        dados = json.loads((d / "edit" / "cenas" / "titulo-misto" / "dados.json").read_text(encoding="utf-8"))
        assert dados["cards"] == [str(foto), str(foto)], dados


# ---------------------------------------------------------------- lyric-carro
def _lyric(d: Path, **kw) -> dict:
    base = {"video": str(_clip(d, 6.0)), "de": 1.0, "ate": 5.0, "palavras": "ACELERA@0.4|SEM@0.9|MEDO@1.3"}
    base.update(kw)
    return base


def test_lyric_words_from_the_param_string():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = cenas.build("lyric-carro", _lyric(d), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert abs(float(re.search(r'data-duration="([\d.]+)"', html).group(1)) - 4.0) < 1e-6
        assert html.count('class="lw ') == 3
        for w in ("ACELERA", "SEM", "MEDO"):
            assert f">{w}<" in html
        styles = re.findall(r'class="lw (\w+)"', html)
        assert len(set(styles)) == 3, styles     # the palette cycles
        assert re.search(r'<audio[^>]+data-media-start="1.0"', html)


def test_lyric_words_from_a_transcript_inside_the_stretch():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        tr = d / "musica.json"
        tr.write_text(json.dumps({"words": [
            {"text": "fora", "start": 0.2, "end": 0.5, "type": "word"},
            {"text": " ", "start": 0.5, "end": 0.6, "type": "spacing"},
            {"text": "Cala", "start": 1.5, "end": 1.8, "type": "word"},
            {"text": "a", "start": 1.9, "end": 2.0, "type": "word"},
            {"text": "boca!", "start": 2.2, "end": 2.6, "type": "word"},
            {"text": "depois", "start": 5.5, "end": 5.8, "type": "word"}]}), encoding="utf-8")
        out = cenas.build("lyric-carro", _lyric(d, palavras=None, letra=str(tr)), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        assert re.findall(r'class="lw \w+"[^>]*>([^<]+)<', html) == ["CALA", "A", "BOCA!"]
        dados = json.loads((out / "dados.json").read_text(encoding="utf-8"))
        assert dados["letra"] == str(tr)


def test_lyric_bursts_from_the_beat_map():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bm = d / "beats.json"
        bm.write_text(json.dumps({"downbeats": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5], "drops": [3.5]}), encoding="utf-8")
        out = cenas.build("lyric-carro", _lyric(d, beats=str(bm)), d / "proj")
        html = (out / "index.html").read_text(encoding="utf-8")
        # downbeats 1.5, 2.5, 3.5, 4.5 fall inside 1.0..5.0 -> relative 0.5, 1.5, 2.5, 3.5, alternating
        assert html.count('class="rajada"') >= 1 and html.count('class="raios"') >= 1
        assert len(re.findall(r'/\* burst (\w+) @([\d.]+) \*/', html)) == 4
        assert re.findall(r'/\* flash @([\d.]+) \*/', html) == ["2.5"]


def test_lyric_validates():
    import cenas
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ok = _lyric(d)
        assert cenas.validate("lyric-carro", ok) == []
        assert any("palavras" in p for p in cenas.validate("lyric-carro", dict(ok, palavras="")))
        assert any("@" in p for p in cenas.validate("lyric-carro", dict(ok, palavras="ACELERA|SEM@x")))
        assert any("letra" in p for p in cenas.validate("lyric-carro", dict(ok, palavras=None, letra=str(d / "n.json"))))


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
