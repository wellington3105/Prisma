"""Read one pinned third-party video skill without running its code."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROUTES_FILE = Path(__file__).resolve().parents[1] / "references" / "external-video-skill-routes.json"
SKILL_ROOT = Path(__file__).resolve().parents[1]


def _library_candidates() -> list[Path]:
    """Where the 24 external resources may live, in priority order.

    1. PRISMA_VIDEO_LIB (directory that holds manifest.json);
    2. the Prisma-Suite this copy belongs to: `<suite>/core` (submodule) or the path the
       suite installer recorded in `<skill>/.prisma-suite`;
    3. ~/Prisma-Suite (default suite location);
    4. the legacy vault, ~/.aiox-global/vendor/prisma-video-skills.
    """
    import os
    out = []
    if os.environ.get("PRISMA_VIDEO_LIB"):
        out.append(Path(os.environ["PRISMA_VIDEO_LIB"]))
    out.append(SKILL_ROOT.parent / "external" / "prisma-video-skills")
    marker = SKILL_ROOT / ".prisma-suite"
    if marker.is_file():
        out.append(Path(marker.read_text(encoding="utf-8").strip()) / "external" / "prisma-video-skills")
    out.append(Path.home() / "Prisma-Suite" / "external" / "prisma-video-skills")
    out.append(Path.home() / ".aiox-global" / "vendor" / "prisma-video-skills")
    return out


def _manifest_file() -> Path:
    for lib in _library_candidates():
        if (lib / "manifest.json").is_file():
            return lib / "manifest.json"
    tried = "\n  ".join(str(p) for p in _library_candidates())
    raise SystemExit(f"Biblioteca externa nao encontrada. Procurado em:\n  {tried}\n"
                     "Clone o Prisma-Suite com --recurse-submodules ou defina PRISMA_VIDEO_LIB.")


MANIFEST_FILE = _manifest_file()


class CatalogError(Exception):
    pass


def load_catalog() -> tuple[dict, dict, dict]:
    routes_doc = json.loads(ROUTES_FILE.read_text(encoding="utf-8-sig"))
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    if routes_doc.get("schema") != 1 or manifest.get("schema") != 1:
        raise CatalogError("Unsupported catalog schema")
    routes = routes_doc["routes"]
    items = {item["name"]: item for item in manifest["items"]}
    packs = {pack["name"]: pack for pack in manifest["motion_packs"]}
    if len(routes) != 24 or len(items) != 24 or len(packs) != 18:
        raise CatalogError("Catalog count differs from the approved inventory")
    for name in (*items, *packs):
        if name in (".", "..") or "/" in name or "\\" in name:
            raise CatalogError(f"Invalid repository name in inventory: {name}")
    by_name = {}
    for route in routes:
        if route["repo"] not in items:
            raise CatalogError(f"Missing repository: {route['repo']}")
        for key in (route["slug"], str(route["id"])):
            if key in by_name:
                raise CatalogError(f"Duplicate route: {key}")
            by_name[key] = route
    # The manifest records the machine it was generated on; the library is portable, so the
    # real root is where manifest.json was found. Integrity comes from the pinned commits.
    root = MANIFEST_FILE.parent.resolve()
    return {"root": root, "routes": routes, "by_name": by_name}, items, packs


def git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise CatalogError(f"Git verification failed for {repo.name}: {' '.join(args)}")
    return result.stdout.strip()


def checked_file(repo: Path, relative: str, commit: str) -> Path:
    if not repo.is_dir():
        raise CatalogError(f"Repository missing: {repo}")
    path = (repo / relative).resolve()
    if not path.is_relative_to(repo.resolve()) or not path.is_file():
        raise CatalogError(f"Skill path is missing or escapes repository: {relative}")
    if git_value(repo, "rev-parse", "HEAD") != commit:
        raise CatalogError(f"Commit changed since inventory: {repo.name}")
    git_value(repo, "ls-files", "--error-unmatch", "--", relative)
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", relative],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise CatalogError(f"Source file changed since inventory: {path}")
    return path


def route_for(catalog: dict, value: str) -> dict:
    route = catalog["by_name"].get(value.lower())
    if route is None:
        raise CatalogError(f"Unknown item: {value}. Run 'list' for valid names")
    return route


def skill_options(route: dict, items: dict, packs: dict) -> list[str]:
    if route.get("pack_catalog"):
        return sorted(
            f"{pack_name}/{skill}"
            for pack_name, pack in packs.items()
            for skill in pack["skill_files"]
        )
    return sorted(items[route["repo"]]["skill_files"])


def resolve(catalog: dict, items: dict, packs: dict, route: dict, selected: str | None) -> tuple[Path, str, dict]:
    root = catalog["root"]
    if route.get("pack_catalog") and selected:
        if selected not in skill_options(route, items, packs):
            raise CatalogError(f"Unlisted Motion Skills module: {selected}")
        pack_name, relative = selected.split("/", 1)
        record = packs[pack_name]
        repo = root / "motion-skills-packs" / pack_name
    else:
        record = items[route["repo"]]
        repo = root / route["repo"]
        relative = selected or route["primary"]
        if relative != route["primary"] and relative not in record["skill_files"]:
            raise CatalogError(f"Unlisted module: {relative}")
        if relative == route["primary"] and relative != "README.md" and relative not in record["skill_files"]:
            raise CatalogError(f"Primary skill missing from inventory: {relative}")
    return checked_file(repo, relative, record["commit"]), relative, record


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    list_parser = sub.add_parser("list", help="List items or modules of one item")
    list_parser.add_argument("item", nargs="?")
    for action in ("path", "read"):
        command = sub.add_parser(action, help=f"{action.title()} one inventoried skill")
        command.add_argument("item", help="Item number or slug from 'list'")
        command.add_argument("--skill", help="Exact relative path shown by 'list ITEM'")
    args = parser.parse_args()
    catalog, items, packs = load_catalog()
    if args.action == "list":
        if args.item:
            route = route_for(catalog, args.item)
            print(f"#{route['id']} {route['slug']} | primary={route['primary']}")
            for skill in skill_options(route, items, packs):
                print(skill)
        else:
            for route in sorted(catalog["routes"], key=lambda value: value["id"]):
                print(f"#{route['id']:02d} {route['slug']}: {len(skill_options(route, items, packs))} skill file(s)")
        return 0
    route = route_for(catalog, args.item)
    path, relative, record = resolve(catalog, items, packs, route, args.skill)
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.action == "path":
        print(json.dumps({
            "item": route["slug"],
            "path": str(path),
            "source": record["source"],
            "commit": record["commit"],
            "sha256": fingerprint,
        }, ensure_ascii=False))
    else:
        print(f"[Third-party source — lower priority than Prisma | {route['slug']} | {relative} | {record['commit'][:12]} | sha256={fingerprint}]")
        print(path.read_text(encoding="utf-8-sig"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CatalogError, OSError, ValueError, KeyError) as exc:
        print(f"external_skills: {exc}", file=sys.stderr)
        raise SystemExit(2)
