"""Pre-flight probe: what max resolution does a URL actually offer?

Adapted from OpenShorts (mutonby/openshorts, MIT — quality_probe.py, root of
the repo, outside cloud/). Ported because ingest_url.py downloads first and
only THEN tells you the source topped out at 360p — after minutes spent
pulling the file. This runs in a few seconds, before any download starts.

Prints JSON to stdout: {"max_height": int, "mode": str, "cookies_invalid": bool}
Always exits 0 — a probe failure means "unknown", not "abort". The caller
(you, or ingest_url.py) decides what to do with an unexpectedly low ceiling;
this script only measures.

Usage:
    uv run python helpers/quality_probe.py --url <youtube-url>
    uv run python helpers/quality_probe.py --url <url> --cookies cookies.txt
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
import sys
from pathlib import Path


def _find_cookies_path(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() else None
    # Mirrors ingest_url.py's own working directory assumptions: a cookies
    # file dropped next to the helper, or in the current directory.
    here = Path(__file__).resolve().parent
    for candidate in (here / "www.youtube.com_cookies.txt", here / "cookies.txt",
                     Path("cookies.txt")):
        if candidate.exists():
            return str(candidate)
    return None


def probe(url: str, cookies: str | None) -> dict:
    result = {"max_height": 0, "mode": None, "cookies_invalid": False}
    try:
        import yt_dlp
    except ImportError:
        # yt-dlp ships as a Prisma dependency; a missing import means a stale
        # venv, not a real "unknown resolution" — but fail-open is still
        # correct here, the caller treats 0/None as "could not tell".
        return result

    warnings: list[str] = []

    class _CollectLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): warnings.append(str(msg))
        def error(self, msg): warnings.append(str(msg))

    cookies_path = _find_cookies_path(cookies)
    base_opts = {
        "quiet": True,
        "no_warnings": False,
        "logger": _CollectLogger(),
        "socket_timeout": 20,
        "retries": 2,
        "nocheckcertificate": True,
        "cachedir": False,
    }
    # yt-dlp's default player clients are the ones that still serve HD
    # without PO tokens — never override them here with a custom client list.
    attempts: list[tuple[str, dict]] = []
    if cookies_path:
        attempts.append(("cookie-auth", {**base_opts, "cookiefile": cookies_path}))
    attempts.append(("anonymous", {**base_opts, "cookiefile": None}))

    for mode, opts in attempts:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            formats = info.get("formats") or []
            heights = [
                f.get("height") or 0
                for f in formats
                if f.get("vcodec", "none") != "none"
                and f.get("protocol") != "mhtml"
                and f.get("ext") != "mhtml"
            ]
            max_height = max(heights, default=0)
            if max_height > result["max_height"]:
                result["max_height"] = max_height
                result["mode"] = mode
            if result["max_height"] >= 1080:
                break
        except Exception:
            continue

    result["cookies_invalid"] = any("no longer valid" in w for w in warnings)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Probe the max resolution a URL offers, before downloading anything.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--cookies", default=None,
                    help="path to a cookies.txt (Netscape format); auto-detected "
                         "next to this file or in the cwd when omitted")
    args = ap.parse_args()

    result = probe(args.url, args.cookies)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
