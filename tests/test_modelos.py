"""The editing-models library: recipes, check, apply, demos, gallery.

    python tests/test_modelos.py          (or: pytest tests/test_modelos.py)

Everything runs in temporary folders (PRISMA_MODELOS, PRISMA_MODELOS_GALERIA, PRISMA_PERFIS):
the real library, gallery and profiles are never touched unless a test says so.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))

SHEET = "# {t}\n\n## O que é\nx\n\n## Quando usar\nx\n\n## Quando não usar\nx\n\n## Contenção\nx\n"


@contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def receitas():
    import modelos_receitas
    return importlib.reload(modelos_receitas)


def write_modelo(root: Path, nivel: str, slug: str, data: dict, sheet: str | None = None):
    d = root / ("tipos" if nivel == "tipo" else "estilos") / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "modelo.json").write_text(json.dumps({"slug": slug, "nivel": nivel, **data}), encoding="utf-8")
    (d / "MODELO.md").write_text(sheet if sheet is not None else SHEET.format(t=slug), encoding="utf-8")


WHIP = {"familia": "transicao", "host": "montagem", "acento": True,
        "aplica": {"por_plano": {"transition": "whip-{dir}"}},
        "parametros": {"dir": {"valores": ["left", "right", "up", "down"], "padrao": "left"}}}


# ---------------------------------------------------------------- Task 1
def test_beat_edit_vocab():
    import beat_edit
    assert "speed" in beat_edit.TRANSITIONS and "whip-left" in beat_edit.TRANSITIONS
    assert "pulse" in beat_edit.FX


def test_beat_edit_rejects_unknown_transition():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        plan = {"music": "m.mp3", "beats": "b.json", "shots": [{"src": "a.mp4", "beats": 2, "transition": "wipe-diagonal"}]}
        (d / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        p = subprocess.run([sys.executable, str(HELPERS / "beat_edit.py"), str(d / "plan.json"), "-o", str(d / "out")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert p.returncode != 0
        assert "unknown transition" in (p.stderr + p.stdout)
        assert not (d / "out").exists()


def test_check_catches_bad_recipe():
    with tempfile.TemporaryDirectory() as d, env(PRISMA_MODELOS=d):
        root = Path(d)
        write_modelo(root, "tipo", "whip-pan", WHIP)
        assert receitas().check() == []
        bad = dict(WHIP, aplica={"por_plano": {"transition": "whip-diagonal"}}, parametros={})
        write_modelo(root, "tipo", "whip-errado", bad)
        probs = receitas().check()
        assert len(probs) == 1 and "whip-errado" in probs[0] and "whip-diagonal" in probs[0], probs


def test_check_requires_sheet_sections():
    with tempfile.TemporaryDirectory() as d, env(PRISMA_MODELOS=d):
        write_modelo(Path(d), "tipo", "whip-pan", WHIP, sheet="# x\n\n## O que é\nx\n\n## Quando usar\nx\n\n## Contenção\nx\n")
        probs = receitas().check()
        assert any("Quando não usar" in p for p in probs), probs


def test_estilo_unknown_tipo():
    with tempfile.TemporaryDirectory() as d, env(PRISMA_MODELOS=d):
        root = Path(d)
        write_modelo(root, "tipo", "whip-pan", WHIP)
        write_modelo(root, "estilo", "teste", {"familia": "estilo", "host": "montagem", "tipos": ["whip-pan", "nao-existe"],
                                               "regras": {"primaria": "whip-pan", "max_acentos": 3}, "sinais": ["x"]})
        probs = receitas().check()
        assert any("nao-existe" in p for p in probs), probs


if __name__ == "__main__":
    fails = 0
    only = sys.argv[1:]
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f) and (not only or name in only):
            try:
                f()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
