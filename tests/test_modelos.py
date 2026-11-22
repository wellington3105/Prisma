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


# ---------------------------------------------------------------- Task 2
V1_TIPOS = {"speed-ramp", "transicao-velocidade", "bullet-time", "velocity-edit", "whip-pan", "flash", "zoom-through",
            "rgb-split", "shake-impacto", "zoom-punch", "zoom-nos-cortes", "push-in", "flash-na-troca", "distorcao-na-troca"}
V1_ESTILOS = {"montagem-na-batida", "reel-fala-broll"}


def test_v1_set_is_complete_and_valid():
    os.environ.pop("PRISMA_MODELOS", None)
    R = receitas()
    todos = R.load_all()
    assert {s for s, m in todos.items() if m.nivel == "tipo"} == V1_TIPOS, sorted(todos)
    assert {s for s, m in todos.items() if m.nivel == "estilo"} == V1_ESTILOS
    assert R.check() == [], R.check()
    for s in V1_ESTILOS:
        assert todos[s].dados["regras"]["max_acentos"] == 3


# ---------------------------------------------------------------- Task 3
def _plan(tmp: Path, n: int, accents: dict | None = None) -> Path:
    shots = [{"src": f"t{i}.mp4", "beats": 2} for i in range(n)]
    for i, tr in (accents or {}).items():
        shots[i]["transition"] = tr
    f = tmp / "plan.json"
    f.write_text(json.dumps({"music": "m.mp3", "beats": "b.json", "shots": shots}), encoding="utf-8")
    return f


def _read(f: Path) -> dict:
    return json.loads(f.read_text(encoding="utf-8"))


def test_whip_pan_on_shot():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 4)
        bk = receitas().apply_file("whip-pan", f, [2], {"dir": "right"})
        shots = _read(f)["shots"]
        assert shots[2]["transition"] == "whip-right"
        assert bk.exists() and "whip-pan" in bk.name
        assert all("transition" not in shots[i] for i in (0, 1, 3))


def test_transicao_velocidade_pairs():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 4)
        receitas().apply_file("transicao-velocidade", f, [2], {})
        shots = _read(f)["shots"]
        assert shots[1]["ramp"] == "speed-out"
        assert shots[2]["ramp"] == "speed-in" and shots[2]["transition"] == "speed"


def test_apply_twice_is_idempotent():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 3)
        R = receitas()
        R.apply_file("zoom-punch", f, [1], {})
        R.apply_file("zoom-punch", f, [1], {})
        assert _read(f)["shots"][1]["fx"] == ["pulse"]


def test_accent_limit():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 5, {0: "flash", 1: "whip-left", 2: "shake"})
        before = f.read_text(encoding="utf-8")
        try:
            receitas().apply_file("flash", f, [3], {})
        except SystemExit as e:
            msg = str(e)
        else:
            raise AssertionError("a 4th accent must be refused")
        assert "0, 1, 2" in msg, msg
        assert f.read_text(encoding="utf-8") == before


def test_estilo_montagem():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 8)
        R = receitas()
        R.apply_file("montagem-na-batida", f, None, {})
        plan = _read(f)
        assert all(plan["shots"][k]["transition"] == "speed" for k in range(1, 8))
        assert len(R.count_accents(plan)) <= 3


def test_velocity_edit_range():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 6)
        receitas().apply_file("velocity-edit", f, [1, 2, 3, 4], {})
        sh = _read(f)["shots"]
        assert [sh[i]["ramp"] for i in (1, 2, 3, 4)] == ["ramp-out", "ramp-in", "ramp-out", "ramp-in"]
        assert sh[1]["transition"] == "flash" and "shake@0" in sh[4]["fx"]
        assert all("pulse" in sh[i]["fx"] for i in (1, 2, 3, 4))


def test_state_records_modelo():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        f = _plan(d, 3)
        (d / "state.json").write_text("{}", encoding="utf-8")
        receitas().apply_file("flash", f, [1], {})
        rec = json.loads((d / "state.json").read_text(encoding="utf-8"))["modelos"]
        assert rec[-1]["slug"] == "flash" and rec[-1]["file"].endswith("plan.json")


def test_tipo_needs_plano():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        f = _plan(Path(d), 3)
        try:
            receitas().apply_file("flash", f, None, {})
        except SystemExit as e:
            assert "--plano" in str(e)
        else:
            raise AssertionError("a tipo without --plano must ask for it")


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
