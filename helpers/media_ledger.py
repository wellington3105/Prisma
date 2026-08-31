"""A manifest of every downloaded asset — reuse across projects, with provenance kept.

Not a port: HyperFrames's `/media-use` resolves assets through a whole sibling
media pipeline (its own service, cache, and catalog) documented but not open
in this repo's scope — no source to adapt. What's worth taking is the IDEA:
today the Prisma asset helpers (pexels_search.py, wikimedia_images.py,
google_images.py, treblo_music.py) each print a credit line to the console and
then forget it. Ask for "Neymar" in two different projects and you download it
twice, and the license/artist line from the first download is gone by the time
the second video needs it for the credits roll.

This is a flat JSON ledger, one entry per downloaded file, keyed by the file's
own SHA-256 (not by query or filename — two different queries that happen to
resolve to the same underlying image are the same asset, one entry). Fields
kept: source helper, original query, license, artist/credit, source URL, first
seen, and which project directories have used it since.

Not a daemon, not a database: `helpers/*_asset*.py` call `record()` right
after writing a file to disk (or you pipe their stdout `+` lines through a
small wrapper — see --from-lines below for retrofitting existing scripts
without editing them). `find_by_hash()` / `find_by_query()` are how a caller
checks "have I already got this?" before spending an API call on it again.

Usage:
    uv run python helpers/media_ledger.py record <file> --source pexels \\
        --query "hollywood film set" --license "Pexels License" \\
        --credit "John Doe" --url "https://pexels.com/photo/123" --project <edit_dir>
    uv run python helpers/media_ledger.py find --query "Neymar"
    uv run python helpers/media_ledger.py find --hash <sha256>
    uv run python helpers/media_ledger.py use <sha256> --project <edit_dir>
    uv run python helpers/media_ledger.py list
"""
from __future__ import annotations

# Windows consoles default to cp1252 and raise UnicodeEncodeError on the arrows
# and box characters these helpers print. Force UTF-8 so a status line can never
# kill a run (measured: transcribe.py + preview_server.py, 2026-08-18).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

# One ledger for the whole skill install, not per-project — the entire point
# is reuse ACROSS projects. Lives next to the skill, not in any single edit
# dir, mirroring where cookies.txt / .env already live (skill root).
LEDGER_PATH = Path(__file__).resolve().parent.parent / "media_ledger.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load() -> dict:
    if not LEDGER_PATH.exists():
        return {"entries": {}}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"entries": {}}


def _save(data: dict) -> None:
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LEDGER_PATH)


def record(file: Path, source: str, query: str, license_: str, credit: str,
          url: str, project: str | None) -> dict:
    """Add (or update usage of) a ledger entry for `file`. Returns the entry."""
    digest = sha256_file(file)
    data = _load()
    entries = data["entries"]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if digest in entries:
        entry = entries[digest]
        if project and project not in entry["used_by"]:
            entry["used_by"].append(project)
    else:
        entry = {
            "hash": digest,
            "source": source,
            "query": query,
            "license": license_,
            "credit": credit,
            "url": url,
            "first_seen": now,
            "used_by": [project] if project else [],
        }
        entries[digest] = entry

    _save(data)
    return entry


def find_by_hash(digest: str) -> dict | None:
    return _load()["entries"].get(digest)


def find_by_query(query: str) -> list[dict]:
    q = query.lower()
    return [e for e in _load()["entries"].values() if q in e["query"].lower()]


def mark_used(digest: str, project: str) -> dict:
    data = _load()
    entry = data["entries"].get(digest)
    if not entry:
        sys.exit(f"nenhum asset com hash {digest} no ledger")
    if project not in entry["used_by"]:
        entry["used_by"].append(project)
        _save(data)
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-project asset manifest with provenance")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="add a downloaded file to the ledger")
    p_record.add_argument("file", type=Path)
    p_record.add_argument("--source", required=True, help="e.g. pexels, wikimedia, treblo")
    p_record.add_argument("--query", default="")
    p_record.add_argument("--license", default="?", dest="license_")
    p_record.add_argument("--credit", default="?")
    p_record.add_argument("--url", default="")
    p_record.add_argument("--project", default=None, help="edit dir this download is for")

    p_find = sub.add_parser("find", help="search the ledger before downloading again")
    p_find.add_argument("--query", default=None)
    p_find.add_argument("--hash", default=None)

    p_use = sub.add_parser("use", help="mark an existing ledger entry as used by a project")
    p_use.add_argument("hash")
    p_use.add_argument("--project", required=True)

    sub.add_parser("list", help="print every ledger entry")

    args = ap.parse_args()

    if args.cmd == "record":
        if not args.file.exists():
            sys.exit(f"arquivo não encontrado: {args.file}")
        entry = record(args.file, args.source, args.query, args.license_, args.credit,
                       args.url, args.project)
        print(json.dumps(entry, ensure_ascii=False, indent=2))

    elif args.cmd == "find":
        if args.hash:
            entry = find_by_hash(args.hash)
            print(json.dumps(entry, ensure_ascii=False, indent=2) if entry else "null")
        elif args.query:
            results = find_by_query(args.query)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            sys.exit("forneça --query ou --hash")

    elif args.cmd == "use":
        entry = mark_used(args.hash, args.project)
        print(json.dumps(entry, ensure_ascii=False, indent=2))

    elif args.cmd == "list":
        data = _load()
        print(json.dumps(list(data["entries"].values()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
