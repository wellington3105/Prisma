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


# ---------------------------------------------------------------- Task 4
def _reel(tmp: Path, phase: int = 2, segments: int | None = 3, edit_data: bool = True, client: str | None = None) -> Path:
    edit = tmp / "edit"
    pub = edit / "remotion" / "public"
    pub.mkdir(parents=True)
    st = {"phase": phase, "style": {"edit": "broll", "elements": {}}}
    if client:
        st["client"] = client
    (edit / "state.json").write_text(json.dumps(st), encoding="utf-8")
    if edit_data:
        (pub / "edit-data.json").write_text(json.dumps({"camera": {"enabled": True, "zooms": [1.0], "pushIn": 0.0}}), encoding="utf-8")
    if segments:
        segs = [{"start": round(i * 4.0, 2), "dur": 4.0} for i in range(segments)]
        (pub / "segments.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
    return edit


def _ed(edit: Path) -> dict:
    return json.loads((edit / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8"))


def _st(edit: Path) -> dict:
    return json.loads((edit / "state.json").read_text(encoding="utf-8"))


def _refused(fn, *args) -> str:
    try:
        fn(*args)
    except SystemExit as e:
        return str(e)
    raise AssertionError("expected a refusal")


def test_reel_refuses_before_phase2():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d), phase=1)
        before = (edit / "state.json").read_text(encoding="utf-8")
        msg = _refused(receitas().apply_file, "push-in", edit, None, {})
        assert "corte aprovado" in msg
        assert (edit / "state.json").read_text(encoding="utf-8") == before


def test_push_in():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d))
        receitas().apply_file("push-in", edit, None, {})
        assert _ed(edit)["camera"]["pushIn"] == 0.04 and _ed(edit)["camera"]["enabled"] is True
        st = _st(edit)
        assert st["style"]["elements"]["zoomAuto"] is True and st["awaitingStyle"] is True
        assert st["modelos"][-1]["slug"] == "push-in"


def test_flash_on_every_cut():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d), segments=3)
        R = receitas()
        R.apply_file("flash-na-troca", edit, None, {})
        R.apply_file("flash-na-troca", edit, None, {})          # idempotent: no duplicates
        tr = _ed(edit)["transitions"]
        assert [(t["at"], t["type"]) for t in tr] == [(4.0, "flash"), (8.0, "flash")], tr


def test_flash_too_many_cuts_needs_plano():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d), segments=8)
        R = receitas()
        msg = _refused(R.apply_file, "flash-na-troca", edit, None, {})
        assert "--plano" in msg and "4.0" in msg
        R.apply_file("flash-na-troca", edit, [0, 3], {})
        assert [t["at"] for t in _ed(edit)["transitions"]] == [4.0, 16.0]


def test_flash_without_segments():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d), segments=None)
        before = json.dumps(_ed(edit))
        msg = _refused(receitas().apply_file, "flash-na-troca", edit, None, {})
        assert "segments.json" in msg
        assert json.dumps(_ed(edit)) == before and "flashCut" not in _st(edit)["style"]["elements"]


def test_only_style_when_no_edit_data():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d), edit_data=False)
        receitas().apply_file("zoom-nos-cortes", edit, None, {})
        assert _st(edit)["style"]["elements"]["zoomCuts"] is True
        assert not (edit / "remotion" / "public" / "edit-data.json").exists()


def test_estilo_reel():
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        edit = _reel(Path(d))
        receitas().apply_file("reel-fala-broll", edit, None, {})
        st = _st(edit)
        assert st["style"]["captions"] == "scatter" and st["style"]["elements"]["brollFull"] is True
        cam = _ed(edit)["camera"]
        assert cam["zooms"] == [1.06, 1.12, 1.04, 1.10] and cam["pushIn"] == 0.04


def test_profile_rules_printed():
    import io
    from contextlib import redirect_stdout
    os.environ.pop("PRISMA_MODELOS", None)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "perfis" / "x").mkdir(parents=True)
        (d / "perfis" / "x" / "profile.json").write_text(json.dumps({"cliente": "x", "rules": [{"text": "sem grão", "origin": "t"}]}), encoding="utf-8")
        edit = _reel(d, client="x")
        buf = io.StringIO()
        with env(PRISMA_PERFIS=d / "perfis"), redirect_stdout(buf):
            receitas().apply_file("push-in", edit, None, {})
        assert "sem grão" in buf.getvalue()


# ---------------------------------------------------------------- Task 5
PEXELS_VIDEO = {"id": 123, "duration": 8, "user": {"name": "Ana"}, "url": "https://www.pexels.com/video/123/",
                "video_files": [
                    {"id": 1, "quality": "sd", "file_type": "video/mp4", "width": 360, "height": 640, "link": "https://x/sd.mp4"},
                    {"id": 2, "quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://x/hd.mp4"},
                    {"id": 3, "quality": "uhd", "file_type": "video/mp4", "width": 2160, "height": 3840, "link": "https://x/uhd.mp4"}]}


def test_pick_video_file():
    import pexels_search
    assert pexels_search.pick_video_file(PEXELS_VIDEO)["id"] == 2
    only4k = dict(PEXELS_VIDEO, video_files=[PEXELS_VIDEO["video_files"][2]])
    assert pexels_search.pick_video_file(only4k, max_side=1920) is None


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
