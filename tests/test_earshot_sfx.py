"""earshot as a foley source: generation into the Prisma SFX library, ledger, index.

    python tests/test_earshot_sfx.py

A fake earshot (writes a 0.3 s tone and prints a line like the real one) stands in for the real
binary, and PRISMA_SFX_EARSHOT / PRISMA_MEDIA_LEDGER point at temporary folders: the real library
and ledger are never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HELPERS = SKILL / "helpers"
sys.path.insert(0, str(HELPERS))

FAKE = '''import subprocess, sys
args = sys.argv[1:]
if args[0] == "--version":
    print("earshot 1.0.0"); sys.exit(0)
out = args[args.index("-o") + 1]
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=0.3", out], check=True)
print(f"{out.rsplit(chr(92), 1)[-1]}: fake/tone (0.30 s, peak at 0.01 s, -16 LUFS, clean)")
if "esportivo" in args[1]:
    print("also (the pick is a guess: earshot makes no such sound; fake/tone is only the nearest sound it has)")
'''


def _env(d: Path) -> dict:
    fake = d / "fake_earshot.py"
    fake.write_text(FAKE, encoding="utf-8")
    return dict(os.environ, PRISMA_EARSHOT=f'"{sys.executable}" "{fake}"', PRISMA_SFX_EARSHOT=str(d / "lib"),
                PRISMA_MEDIA_LEDGER=str(d / "ledger.json"))


def run(env, *args):
    return subprocess.run([sys.executable, str(HELPERS / "earshot_sfx.py"), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


def test_make_writes_library_and_ledger():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        e = _env(d)
        p = run(e, "make", "porta de carro batendo", "--name", "porta")
        assert p.returncode == 0, p.stderr
        assert (d / "lib" / "porta.wav").exists()
        led = json.loads((d / "ledger.json").read_text(encoding="utf-8"))
        rows = list(led["entries"].values())
        assert any(r.get("source") == "earshot" and "porta" in str(r.get("query", "")) for r in rows), led


def test_guess_is_reported():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p = run(_env(d), "make", "motor esportivo acelerando", "--name", "motor")
        assert p.returncode == 0 and "palpite" in p.stdout, p.stdout


def test_kit_carro():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p = run(_env(d), "kit", "carro")
        assert p.returncode == 0, p.stderr
        names = sorted(f.stem for f in (d / "lib").glob("*.wav"))
        assert names == ["camera_obturador", "carro_partida", "carro_passando", "chave_fechadura", "pneu_cantando", "porta_carro"], names


def test_missing_binary_says_how_to_install():
    with tempfile.TemporaryDirectory() as d:
        e = dict(_env(Path(d)), PRISMA_EARSHOT=str(Path(d) / "nao-existe.exe"))
        p = run(e, "make", "porta")
        assert p.returncode != 0 and "pip install" in (p.stdout + p.stderr)


def test_sfx_index_reads_the_earshot_library():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "lib").mkdir()
        os.environ["PRISMA_SFX_EARSHOT"] = str(d / "lib")
        try:
            import importlib
            import sfx_index
            importlib.reload(sfx_index)
            assert (d / "lib").resolve() in [p.resolve() for p in sfx_index.default_dirs()]
        finally:
            os.environ.pop("PRISMA_SFX_EARSHOT")


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
