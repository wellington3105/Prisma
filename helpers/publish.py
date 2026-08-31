"""Publish a rendered video to social platforms via the Postiz HTTP API.

Not a port: Postiz (gitroomhq/postiz-app) is AGPL-3.0. AGPL is viral copyleft
that reaches network use — copying its code into Prisma would force Prisma
itself under AGPL. Consuming its HTTP API is a different thing entirely: no
Postiz source lives in this file, only requests against a public, documented
REST contract (docs.postiz.com/public-api), the same way any Postiz user's
own script would. Zero AGPL code in this repo.

Three-step flow, matching the Postiz API's own shape:
  1. POST /upload  (multipart) — get back {id, path} for the rendered video
  2. GET /integrations — resolve a channel name (e.g. "instagram") to its
     integration ID, so the caller doesn't need to know Postiz's internal IDs
  3. POST /posts — create the post (now / schedule / draft) referencing the
     uploaded media and the target integration

Needs a Postiz API key (Postiz Settings → API). Cloud vs self-hosted only
changes the base URL — see --base-url / POSTIZ_BASE_URL.

Usage:
    export POSTIZ_API_KEY=...
    uv run python helpers/publish.py <video> --integration instagram --caption "..."
    uv run python helpers/publish.py <video> --integration instagram --caption "..." \\
        --schedule 2026-08-20T18:00:00Z
    uv run python helpers/publish.py <video> --integration youtube --caption "..." --draft
    uv run python helpers/publish.py --list-integrations
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
import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_BASE_URL = "https://api.postiz.com/public/v1"


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "POSTIZ_API_KEY":
                    return v.strip().strip('"').strip("'")
    v = os.environ.get("POSTIZ_API_KEY", "")
    if not v:
        sys.exit("POSTIZ_API_KEY not found in .env or environment "
                 "(Postiz Settings → API)")
    return v


def _headers(api_key: str) -> dict:
    return {"Authorization": api_key}


def list_integrations(base_url: str, api_key: str) -> list[dict]:
    r = requests.get(f"{base_url}/integrations", headers=_headers(api_key), timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_integration(base_url: str, api_key: str, name_or_id: str) -> dict:
    """Match by integration id, exact identifier (platform, e.g. "instagram"),
    or case-insensitive channel name — whichever the caller passed."""
    integrations = list_integrations(base_url, api_key)
    for it in integrations:
        if it.get("id") == name_or_id:
            return it
    for it in integrations:
        if it.get("identifier", "").lower() == name_or_id.lower():
            return it
    for it in integrations:
        if it.get("name", "").lower() == name_or_id.lower():
            return it
    available = ", ".join(f"{it.get('name')} ({it.get('identifier')})" for it in integrations)
    sys.exit(f"no integration matches '{name_or_id}'. Connected channels: {available or '(none)'}")


def upload_file(base_url: str, api_key: str, path: Path) -> dict:
    with open(path, "rb") as f:
        r = requests.post(f"{base_url}/upload", headers=_headers(api_key),
                          files={"file": (path.name, f)}, timeout=600)
    r.raise_for_status()
    return r.json()


def create_post(base_url: str, api_key: str, integration_id: str, caption: str,
                media: dict, post_type: str = "now", date_iso: str | None = None,
                settings: dict | None = None) -> dict:
    body = {
        "type": post_type,
        "date": date_iso or "2024-12-14T10:00:00.000Z",  # ignored when type == "now"
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": [{"content": caption, "image": [media] if media else []}],
            }
        ],
    }
    if settings:
        body["posts"][0]["settings"] = settings
    r = requests.post(f"{base_url}/posts", headers={**_headers(api_key),
                      "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=60)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Publish a video to a social platform via the Postiz API")
    ap.add_argument("video", type=Path, nargs="?", help="rendered video file to upload")
    ap.add_argument("--integration", type=str, default=None,
                    help="integration id, identifier (e.g. 'instagram'), or channel name")
    ap.add_argument("--caption", type=str, default="")
    ap.add_argument("--schedule", type=str, default=None,
                    help="ISO 8601 UTC datetime; omit to publish immediately")
    ap.add_argument("--draft", action="store_true", help="save as draft instead of publishing")
    ap.add_argument("--settings", type=str, default=None,
                    help="JSON string merged as the post's provider-specific settings "
                         "(must include __type — see docs.postiz.com/public-api/providers)")
    ap.add_argument("--base-url", type=str,
                    default=os.environ.get("POSTIZ_BASE_URL", DEFAULT_BASE_URL),
                    help="Postiz API base URL (self-hosted: https://<domain>/api/public/v1)")
    ap.add_argument("--list-integrations", action="store_true",
                    help="print connected channels and exit")
    args = ap.parse_args()

    api_key = load_api_key()
    base_url = args.base_url.rstrip("/")

    if args.list_integrations:
        integrations = list_integrations(base_url, api_key)
        print(json.dumps(integrations, ensure_ascii=False, indent=2))
        return

    if not args.video or not args.integration:
        sys.exit("provide <video> and --integration, or use --list-integrations")
    if not args.video.exists():
        sys.exit(f"video not found: {args.video}")

    target = resolve_integration(base_url, api_key, args.integration)
    print(f"  channel: {target.get('name')} ({target.get('identifier')})", file=sys.stderr)

    print(f"  uploading {args.video.name}...", file=sys.stderr)
    media = upload_file(base_url, api_key, args.video)
    print(f"  uploaded: {media.get('path')}", file=sys.stderr)

    post_type = "draft" if args.draft else ("schedule" if args.schedule else "now")
    settings = json.loads(args.settings) if args.settings else None

    result = create_post(base_url, api_key, target["id"], args.caption, media,
                         post_type=post_type, date_iso=args.schedule, settings=settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
