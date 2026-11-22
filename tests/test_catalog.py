"""The catalogue stays connected: helpers, references, aliases and routes agree.

    python tests/test_catalog.py          (or: pytest tests/test_catalog.py)

Fails when:
- a helper exists but is not in references/tool-map.md, or the map names one that does not exist;
- a reference .md is linked from nowhere (SKILL.md, tool-map.md or another reference);
- a file the tool map points to does not exist;
- skill-aliases/ and references/external-video-skill-routes.json list different resources;
- an alias still carries the old "Remotion-only Phase 2" rule.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REF = SKILL / "references"
MAP = REF / "tool-map.md"


def _helpers() -> set[str]:
    return {p.stem for p in (SKILL / "helpers").glob("*.py") if p.stem != "__init__"}


def _map_names() -> list[str]:
    rows = [l for l in MAP.read_text(encoding="utf-8").splitlines() if l.startswith("| **")]
    names = []
    for r in rows:
        cell = re.sub(r"\([^)]*\)", "", r.split("|")[2])   # "(interno de `render`)" is a note, not a listing
        names += re.findall(r"`([a-z0-9_]+)`", cell)
    return names


def test_every_helper_is_mapped_once():
    names = _map_names()
    helpers = _helpers()
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, f"helpers listed more than once in tool-map.md: {dup}"
    missing = sorted(helpers - set(names))
    assert not missing, f"helpers missing from references/tool-map.md: {missing}"
    ghost = sorted(set(names) - helpers)
    assert not ghost, f"tool-map.md names helpers that do not exist: {ghost}"


def test_map_references_exist():
    text = MAP.read_text(encoding="utf-8")
    for name in set(re.findall(r"`([\w.-]+\.md)`", text)):
        assert (REF / name).exists() or (SKILL / name).exists(), f"tool-map.md points to a missing file: {name}"


def test_every_reference_is_linked():
    corpus = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for p in REF.glob("*.md"):
        corpus += p.read_text(encoding="utf-8")
    orphans = []
    for p in REF.glob("*.md"):
        if p.name.startswith("_"):
            continue      # working inventories, not routing material
        others = corpus.replace(p.read_text(encoding="utf-8"), "")
        if p.name not in others and p.stem not in others:
            orphans.append(p.name)
    assert not orphans, f"references linked from nowhere: {orphans}"
    assert "references/tool-map.md" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_aliases_match_routes():
    routes = json.loads((REF / "external-video-skill-routes.json").read_text(encoding="utf-8"))["routes"]
    slugs = {r["slug"] for r in routes}
    aliases = {p.name[len("prisma-ext-"):] for p in (SKILL / "skill-aliases").glob("prisma-ext-*")}
    assert aliases == slugs, f"only in aliases: {sorted(aliases - slugs)}; only in routes: {sorted(slugs - aliases)}"
    for p in (SKILL / "skill-aliases").glob("*/SKILL.md"):
        assert "Remotion-only" not in p.read_text(encoding="utf-8"), f"stale Remotion-only rule in {p.parent.name}"


def test_modelos_check():
    sys.path.insert(0, str(SKILL / "helpers"))
    import modelos_receitas
    assert modelos_receitas.check() == [], modelos_receitas.check()


if __name__ == "__main__":
    fails = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
