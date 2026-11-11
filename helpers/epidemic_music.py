"""Epidemic Sound soundtrack + SFX for Phase 3, through the official MCP server.

The Epidemic Sound MCP server (https://www.epidemicsound.com/a/mcp-service/mcp)
is a GraphQL API exposed as MCP tools. This helper speaks MCP over plain HTTP
(JSON-RPC, streamable-HTTP/SSE), so Prisma does not depend on the MCP being
loaded in the agent session — the same key works both ways.

Needs EPIDEMIC_SOUND_MCP_API_KEY (env, .env at the Prisma repo root, or a .env in
the current directory or any parent). It is an MCP Server key from
epidemicsound.com/account/api-keys — NOT a Developer Portal (Partner API) key.
Downloads need an active paid subscription; search works on any account.

Usage:
    python helpers/epidemic_music.py search "upbeat corporate electronic" --bpm 100-125 --min-s 60
    python helpers/epidemic_music.py download <id> -o remotion/public/trilha.mp3
    python helpers/epidemic_music.py download <id> --stem INSTRUMENTS -o stem.mp3
    python helpers/epidemic_music.py fit <id> --duration 47.2 -o remotion/public/trilha.mp3
    python helpers/epidemic_music.py fit <id> --duration 47.2 --pin 62.0-70.0@15.0 -o trilha.mp3
    python helpers/epidemic_music.py sfx "whoosh" -n 5
    python helpers/epidemic_music.py sfx-download <id> -o remotion/public/sfx/whoosh.mp3
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
import re
import sys
import time
from pathlib import Path

import requests

URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
KEY_NAME = "EPIDEMIC_SOUND_MCP_API_KEY"
LICENSE = "Epidemic Sound subscription (licensed to the subscriber's account)"


def load_api_key() -> str:
    v = os.environ.get(KEY_NAME, "").strip()
    if v:
        return v
    here = Path.cwd().resolve()
    candidates = [Path(__file__).resolve().parent.parent / ".env"]
    candidates += [d / ".env" for d in [here, *here.parents]]
    for c in candidates:
        if c.is_file():
            for line in c.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith(KEY_NAME + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{KEY_NAME} not found in the environment or in any .env "
             "(Prisma root, current dir or its parents). Create an MCP Server "
             "key at https://www.epidemicsound.com/account/api-keys")


class MCP:
    """Minimal streamable-HTTP MCP client: initialize once, then tools/call."""

    def __init__(self, key: str):
        self.h = {"Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream",
                  "Authorization": f"Bearer {key}"}
        self.sid: str | None = None
        self.n = 0
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "prisma", "version": "1"}})
        self._rpc("notifications/initialized", {}, notify=True)

    def _rpc(self, method: str, params: dict, notify: bool = False):
        h = dict(self.h)
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        body: dict = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            self.n += 1
            body["id"] = self.n
        r = requests.post(URL, json=body, headers=h, timeout=120)
        if r.status_code == 401:
            sys.exit("Epidemic Sound 401: key rejected (wrong key type, revoked, "
                     "or no active subscription). The response never says which.")
        if r.status_code >= 400:
            sys.exit(f"Epidemic Sound {r.status_code}: {r.text[:300]}")
        self.sid = r.headers.get("mcp-session-id") or self.sid
        if notify:
            return None
        # SSE stream: the first `data:` line is an empty keep-alive, so pick the
        # JSON message whose id matches instead of parsing the first one.
        msgs = []
        for line in r.text.splitlines():
            if line.startswith("data: {"):
                msgs.append(json.loads(line[6:]))
        if not msgs and r.text.lstrip().startswith("{"):
            msgs.append(r.json())
        for m in msgs:
            if m.get("id") == body["id"]:
                if "error" in m:
                    sys.exit(f"MCP error: {m['error']}")
                return m["result"]
        sys.exit(f"no MCP response for {method}: {r.text[:300]}")

    def call(self, tool: str, args: dict, retries: int = 4) -> dict:
        for attempt in range(retries + 1):
            res = self._rpc("tools/call", {"name": tool, "arguments": args})
            text = "".join(c.get("text", "") for c in res.get("content", []))
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                sys.exit(f"{tool}: non-JSON reply: {text[:300]}")
            errs = payload.get("errors") or []
            retry = next((e for e in errs
                          if (e.get("extensions") or {}).get("code") == "RETRY_LATER"), None)
            if retry and attempt < retries:
                # The server asks us to wait; retrying at once only burns the limit.
                wait = (retry.get("extensions") or {}).get("retryAfterSeconds") or 10
                print(f"  RETRY_LATER — waiting {wait}s…", flush=True)
                time.sleep(float(wait))
                continue
            if errs and not payload.get("data"):
                sys.exit(f"{tool} failed: {json.dumps(errs)[:400]}")
            return payload.get("data") or {}
        sys.exit(f"{tool}: still RETRY_LATER after {retries} retries")


def _first(obj, pred):
    """Depth-first search for the first value matching pred(key, value)."""
    stack = [(None, obj)]
    while stack:
        k, v = stack.pop(0)
        if pred(k, v):
            return v
        if isinstance(v, dict):
            stack.extend(v.items())
        elif isinstance(v, list):
            stack.extend((None, x) for x in v)
    return None


def _asset_url(data: dict) -> str:
    url = _first(data, lambda k, v: k in ("assetUrl", "url", "downloadUrl")
                 and isinstance(v, str) and v.startswith("http"))
    if not url:
        sys.exit(f"no download URL in reply: {json.dumps(data)[:400]}")
    return url


def _save(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"  saved: {out} ({len(r.content)/1024:.0f} KB)")


def _range(s: str | None) -> dict | None:
    if not s:
        return None
    lo, _, hi = s.partition("-")
    return {"min": int(float(lo)) if lo else None, "max": int(float(hi)) if hi else None}


def _ledger_hint(out: Path, source: str, query: str, credit: str) -> None:
    print(f'  ledger: uv run python helpers/media_ledger.py record "{out}" '
          f'--source {source} --query "{query}" --license "{LICENSE}" '
          f'--credit "{credit}" --project <edit_dir>')


def cmd_search(m: MCP, a) -> None:
    filt: dict = {}
    if a.bpm:
        filt["bpm"] = _range(a.bpm)
    if a.min_s or a.max_s:
        filt["duration"] = {"min": int(a.min_s * 1000) if a.min_s else None,
                            "max": int(a.max_s * 1000) if a.max_s else None}
    if a.mood:
        filt["moodSlugs"] = {"matchType": "ANY", "values": a.mood.split(",")}
    if a.genre:
        filt["taxonomySlugs"] = {"matchType": "ANY", "values": a.genre.split(",")}
    args: dict = {"query": {"term": a.term}, "first": a.n}
    if filt:
        args["filter"] = filt
    data = m.call("SearchRecordings", args)
    nodes = (data.get("recordings") or {}).get("nodes") or []
    if not nodes:
        print("  no results — loosen the filters or rephrase the term")
    rows = []
    for nd in nodes:
        rec = nd.get("recording") or nd
        tags = rec.get("tags") or []
        mood = [t["displayName"] for t in tags if (t.get("dimension") or {}).get("name") == "mood"]
        genre = [t["displayName"] for t in tags if "genre" in ((t.get("dimension") or {}).get("name") or "")]
        vocal = [t["displayName"] for t in tags if (t.get("dimension") or {}).get("name") == "vocal type"]
        artist = next((c["artist"]["name"] for c in rec.get("credits") or []
                       if c.get("role") == "MAIN_ARTIST"), "?")
        dur = ((rec.get("audioFile") or {}).get("durationInMilliseconds") or 0) / 1000
        stems = ",".join(s.get("type", "") for s in rec.get("stems") or [])
        rows.append({"id": rec.get("id"), "title": rec.get("title"), "artist": artist,
                     "bpm": rec.get("bpm"), "duration_s": round(dur, 1), "mood": mood,
                     "genre": genre, "vocals": vocal, "stems": stems,
                     "preview": (rec.get("audioFile") or {}).get("lqmp3Url")})
        print(f"\n  {rec.get('title')} — {artist}  [{rec.get('bpm')} BPM · {dur:.0f}s]"
              f"\n    id {rec.get('id')}"
              f"\n    {', '.join(genre + mood + vocal)}  · stems: {stems or '—'}"
              f"\n    preview {rows[-1]['preview']}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  wrote {a.json}")


def cmd_download(m: MCP, a) -> None:
    data = m.call("DownloadRecording", {"id": a.id, "options": {
        "fileType": "WAV" if a.wav else "MP3", "stemType": a.stem}})
    _save(_asset_url(data), a.output.resolve())
    _ledger_hint(a.output, "epidemic_music.py", a.id, "Music from Epidemic Sound")


def cmd_fit(m: MCP, a) -> None:
    ms = int(round(a.duration * 1000))
    if ms > 300_000:
        sys.exit("Epidemic edits are capped at 300s — loop or crossfade two edits instead")
    inp: dict = {"targetDurationMs": ms, "downloadAudioFormat": "WAV" if a.wav else "MP3",
                 "skipStems": True, "maxResults": 1, "forceDuration": not a.loose}
    if a.loopable:
        inp["loopable"] = True
    if a.pin:
        pins = []
        for p in a.pin:
            mm = re.fullmatch(r"([\d.]+)-([\d.]+)@([\d.]+)", p)
            if not mm:
                sys.exit(f"--pin must be START-END@OFFSET in seconds, got {p!r}")
            s, e, o = (float(x) for x in mm.groups())
            pins.append({"startMs": int(s * 1000), "endMs": int(e * 1000),
                         "offsetMsInEdit": int(o * 1000)})
        inp["requiredRegionsAtOffsets"] = pins
    if a.job:
        # Retomar não cria outra edição: só volta a acompanhar um job existente.
        job_id = a.job
    else:
        job = m.call("EditRecording", {"id": a.id, "input": inp})
        job_id = _first(job, lambda k, v: k == "id" and isinstance(v, str))
        if not job_id:
            sys.exit(f"no job id in EditRecording reply: {json.dumps(job)[:300]}")
    print(f"  edit job {job_id} — polling…", flush=True)
    t0 = time.time()
    while True:
        st = m.call("PollEditRecordingJob", {"id": job_id})
        status = _first(st, lambda k, v: k == "status" and isinstance(v, str))
        if status == "COMPLETED":
            break
        if status == "FAILED":
            sys.exit(f"edit job FAILED: {json.dumps(st)[:300]}")
        if time.time() - t0 > a.timeout:
            sys.exit(f"edit job still {status} after {a.timeout}s — resume with "
                     f"--job {job_id} (and a longer --timeout)")
        time.sleep(4)
    # The job carries ONE edit as `edit` (object) — measured 2026-11-03; the docs
    # say only one is retrievable whatever maxResults is. Accept a list too.
    edit = _first(st, lambda k, v: k in ("edit", "edits") and isinstance(v, (dict, list)))
    if isinstance(edit, list):
        edit = edit[0] if edit else None
    edit_id = (edit or {}).get("id")
    if not edit_id:
        sys.exit(f"job COMPLETED but no edit id: {json.dumps(st)[:300]}")
    data = m.call("DownloadRecordingEdit", {"input": {"jobId": job_id, "editId": edit_id}})
    _save(_asset_url(data), a.output.resolve())
    _ledger_hint(a.output, "epidemic_music.py", a.id, "Music from Epidemic Sound")


def cmd_sfx(m: MCP, a) -> None:
    data = m.call("SearchSoundEffects", {"query": {"term": a.term}, "first": a.n})
    for nd in (data.get("soundEffects") or {}).get("nodes") or []:
        fx = nd.get("soundEffect") or nd
        dur = ((fx.get("audioFile") or {}).get("durationInMilliseconds") or 0) / 1000
        print(f"\n  {fx.get('title')}  [{dur:.2f}s]\n    id {fx.get('id')}"
              f"\n    preview {(fx.get('audioFile') or {}).get('lqmp3Url')}")


def cmd_sfx_download(m: MCP, a) -> None:
    data = m.call("DownloadSoundEffect", {"id": a.id, "options": {
        "fileType": "WAV" if a.wav else "MP3"}})
    _save(_asset_url(data), a.output.resolve())
    _ledger_hint(a.output, "epidemic_music.py", a.id, "Sound effect from Epidemic Sound")


def main() -> None:
    ap = argparse.ArgumentParser(description="Epidemic Sound music + SFX (MCP)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="find tracks (semantic term + filters)")
    s.add_argument("term", help="what the video needs, in words: 'calm hopeful "
                   "acoustic for a family brand story', not a single genre word")
    s.add_argument("--bpm", help="range, e.g. 100-125")
    s.add_argument("--min-s", type=float, help="min track length in seconds")
    s.add_argument("--max-s", type=float, help="max track length in seconds")
    s.add_argument("--mood", help="comma-separated mood slugs")
    s.add_argument("--genre", help="comma-separated genre/taxonomy slugs")
    s.add_argument("-n", type=int, default=8)
    s.add_argument("--json", type=Path, help="also write the shortlist as JSON")

    d = sub.add_parser("download", help="full track or one stem")
    d.add_argument("id")
    d.add_argument("-o", "--output", type=Path, required=True)
    d.add_argument("--stem", default="FULL", choices=["FULL", "BASS", "DRUMS", "INSTRUMENTS"])
    d.add_argument("--wav", action="store_true")

    f = sub.add_parser("fit", help="Epidemic's own edit of the track to an exact length")
    f.add_argument("id")
    f.add_argument("--duration", type=float, required=True, help="seconds (≤300) — "
                   "the cut.mp4 duration")
    f.add_argument("--pin", action="append", help="START-END@OFFSET (s): put that "
                   "region of the original at OFFSET in the edit (repeatable)")
    f.add_argument("--loopable", action="store_true")
    f.add_argument("--loose", action="store_true", help="allow the edit to miss "
                   "the exact duration slightly (default forces it)")
    f.add_argument("--wav", action="store_true")
    f.add_argument("--timeout", type=int, default=300)
    f.add_argument("--job", metavar="JOB_ID", help="resume an existing edit job "
                   "(after a timeout or failed download) instead of creating one")
    f.add_argument("-o", "--output", type=Path, required=True)

    x = sub.add_parser("sfx", help="search sound effects")
    x.add_argument("term")
    x.add_argument("-n", type=int, default=6)

    xd = sub.add_parser("sfx-download", help="download one sound effect")
    xd.add_argument("id")
    xd.add_argument("-o", "--output", type=Path, required=True)
    xd.add_argument("--wav", action="store_true")

    a = ap.parse_args()
    m = MCP(load_api_key())
    {"search": cmd_search, "download": cmd_download, "fit": cmd_fit,
     "sfx": cmd_sfx, "sfx-download": cmd_sfx_download}[a.cmd](m, a)


if __name__ == "__main__":
    main()
