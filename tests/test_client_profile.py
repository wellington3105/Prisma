"""Client profiles: learn/seed still work, and every save is backed up with history.

    python tests/test_client_profile.py          (or: pytest tests/test_client_profile.py)

Everything runs in temporary folders (PRISMA_PERFIS / PRISMA_PERFIS_BACKUP): the real
profiles and the real backup are never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
CP = SKILL / "helpers" / "client_profile.py"


def run(env, *args, ok=True):
    p = subprocess.run([sys.executable, str(CP), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if ok:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


def _setup(d: Path, backup: str | None):
    env = dict(os.environ, PRISMA_PERFIS=str(d / "perfis"))
    env.pop("OneDrive", None)
    env.pop("OneDriveConsumer", None)
    env["PRISMA_PERFIS_BACKUP"] = backup if backup is not None else str(d / "backup")
    edit = d / "proj" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "Teste A", "style": {"edit": "split", "accent": "#ff5200"}}), encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({"grade": "warm"}), encoding="utf-8")
    return env, edit


def test_learn_seed_and_backup_history():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        env, edit = _setup(d, None)
        run(env, "set", edit, "Cliente X")
        run(env, "learn", "Cliente X", "--from", edit)
        bk = d / "backup" / "cliente-x" / "profile.json"
        local = d / "perfis" / "cliente-x" / "profile.json"
        assert bk.read_bytes() == local.read_bytes()
        assert not list((bk.parent / "historico").glob("*.json"))         # first copy: nothing to keep yet
        run(env, "rule", "Cliente X", "--text", "sem grão", "--origin", "teste")
        hist = list((bk.parent / "historico").glob("profile-*.json"))
        assert len(hist) == 1 and "sem grão" not in hist[0].read_text(encoding="utf-8")
        assert "sem grão" in bk.read_text(encoding="utf-8")
        assert "backup ok" in run(env, "list").stdout
        # seed still fills a fresh project and still refuses to overwrite a different style
        fresh = d / "novo" / "edit"; fresh.mkdir(parents=True)
        (fresh / "state.json").write_text("{}", encoding="utf-8")
        run(env, "seed", "Cliente X", fresh)
        st = json.loads((fresh / "state.json").read_text(encoding="utf-8"))
        assert st["style"]["accent"] == "#ff5200" and st["awaitingStyle"] is True
        (fresh / "state.json").write_text(json.dumps({"style": {"edit": "outro"}}), encoding="utf-8")
        assert run(env, "seed", "Cliente X", fresh, ok=False).returncode != 0


def test_restore_refuses_then_keeps_local():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        env, edit = _setup(d, None)
        run(env, "learn", "Cliente X", "--from", edit)
        local = d / "perfis" / "cliente-x" / "profile.json"
        saved = local.read_text(encoding="utf-8")
        local.write_text(saved.replace("split", "LOCAL-EDITADO"), encoding="utf-8")
        assert "DESATUALIZADO" in run(env, "list").stdout
        assert run(env, "restore", "Cliente X", ok=False).returncode != 0          # differs: needs --force
        run(env, "restore", "Cliente X", "--force")
        assert local.read_text(encoding="utf-8") == saved
        kept = list(local.parent.glob("profile.antes-restore-*.json"))
        assert len(kept) == 1 and "LOCAL-EDITADO" in kept[0].read_text(encoding="utf-8")


def test_restore_after_disk_loss():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        env, edit = _setup(d, None)
        run(env, "learn", "Cliente X", "--from", edit)
        local = d / "perfis" / "cliente-x" / "profile.json"
        saved = local.read_bytes()
        local.unlink()
        run(env, "restore", "Cliente X")
        assert local.read_bytes() == saved


def test_backup_off_warns_but_saves():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        env, edit = _setup(d, "off")
        p = run(env, "learn", "Cliente X", "--from", edit)
        assert (d / "perfis" / "cliente-x" / "profile.json").exists()
        assert "SEM backup" in p.stderr
        assert "SEM backup" in run(env, "list").stdout


if __name__ == "__main__":
    fails = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
