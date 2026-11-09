"""Prisma preview server — serves the standard editing interface + session media.

The interface app (assets/preview/) is IMMUTABLE and lives in the skill repo;
per-session it is fed by data only:
  - <edit>/state.json          written by the skill (phase, files, message)
  - <edit>/edl.json            the cut (segments shown/trimmed on the timeline)
  - <edit>/cut.mp4             current render (played + scrubbed)
  - <edit>/preview_edits.json  WRITTEN BY THE UI when the user saves timeline
                               adjustments — the skill reads, validates, applies
                               and re-renders. The UI never touches edl.json.
  - <edit>/preview_style.json  WRITTEN BY THE UI at the Fase 1 → Fase 2 gate:
                               editing style, caption style, edit elements.

Routes:
  /                     the app (from <skill>/assets/preview/)
  /assets/<file>        app files (css/js/logo)
  /media/<path>         files under --root (the edit dir) — Range supported
  /gen/waveform.json    min/max audio peaks of cut.mp4 (auto-(re)generated)
  /gen/thumbs/<n>.jpg   timeline filmstrip thumbs (auto-generated, 1 per 2s)
  /api/state    GET     state.json + mtimes (UI polls this to hot-reload)
  /api/save     POST    body → <edit>/preview_edits.json (atomic), or
                        <edit>/preview_style.json when body.type=="style-setup"
  /api/render   POST    kick off render_phase2.py in the background (one at a
                        time; a new request supersedes a running one)
  /api/render   GET     {running, startedAt, finishedAt, ok, log}

Usage:
    uv run helpers/preview_server.py --root <videos_dir>/edit [--port 4820]
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
import array
import atexit
import http.client
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "assets" / "preview"
PEAKS_PER_SEC = 40
THUMB_EVERY_S = 2.0
THUMB_HEIGHT = 90

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    # without this the brand mark is served as application/octet-stream and the
    # browser refuses to draw it — the alt text shows instead of the logo
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".srt": "text/plain; charset=utf-8",
}

_thumb_lock = threading.Lock()
_thumb_state: dict[str, float] = {}  # video path -> mtime generated


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def gen_waveform(video: Path, out_json: Path) -> None:
    """Decode audio to mono s16 and store min/max peak pairs per bucket (0-100)."""
    rate = 8000
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn",
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    per_bucket = max(1, rate // PEAKS_PER_SEC)
    mins: list[int] = []
    maxs: list[int] = []
    for i in range(0, len(samples), per_bucket):
        chunk = samples[i:i + per_bucket]
        if not chunk:
            continue
        mins.append(round(min(chunk) / 32768 * 100))
        maxs.append(round(max(chunk) / 32768 * 100))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "peaksPerSec": PEAKS_PER_SEC,
        "duration": len(samples) / rate,
        "min": mins,
        "max": maxs,
        "srcMtime": video.stat().st_mtime,
    }), encoding="utf-8")
    tmp.replace(out_json)


def gen_thumbs(video: Path, out_dir: Path) -> None:
    """Filmstrip thumbs: one small jpg every THUMB_EVERY_S seconds."""
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1/{THUMB_EVERY_S},scale=-2:{THUMB_HEIGHT}",
         "-q:v", "6", str(out_dir / "%04d.jpg")],
        check=False, capture_output=True,
    )
    (out_dir / "meta.json").write_text(json.dumps({
        "everySec": THUMB_EVERY_S,
        "count": len(list(out_dir.glob("*.jpg"))),
        "srcMtime": video.stat().st_mtime,
    }), encoding="utf-8")


class RenderJob:
    """Runs render_phase2.py in the background, one at a time.

    Auto-render is what makes a timeline handle feel real: you drag, and the
    picture eventually agrees. But a render is minutes long, so two rules keep
    it from turning into a queue of stale work:

      * ONE at a time. A request while a render is running marks `superseded`
        and re-runs once the current one finishes — the last edit wins instead
        of every intermediate drag getting its own four minutes.
      * The UI debounces before asking at all, so a burst of nudges is one job.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()
        self.running = False
        self.superseded = False
        self.started_at = 0.0
        self.finished_at = 0.0
        self.ok: bool | None = None
        self.log = ""

    def status(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "superseded": self.superseded,
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "ok": self.ok,
                "log": self.log[-1200:],
            }

    def request(self) -> dict:
        with self.lock:
            if self.running:
                self.superseded = True
                return {"queued": True, "running": True}
            self.running = True
            self.superseded = False
            self.started_at = time.time()
            self.finished_at = 0.0
            self.ok = None
            self.log = ""
        threading.Thread(target=self._run, daemon=True).start()
        return {"queued": True, "running": True}

    def _run(self) -> None:
        while True:
            script = Path(__file__).resolve().parent / "render_phase2.py"
            cmd = [sys.executable, str(script), "--edit", str(self.root)]
            # the engine chosen for this video (state.json `engine`, set by render_phase2
            # / the Estilo tab); absent = render_phase2's default (`auto`)
            try:
                eng = json.loads((self.root / "state.json").read_text(encoding="utf-8")).get("engineRequest")
            except (OSError, json.JSONDecodeError):
                eng = None
            if eng in ("hyperframes", "remotion", "auto"):
                cmd += ["--engine", eng]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
                out = (r.stdout or "") + (r.stderr or "")
                ok = r.returncode == 0
            except OSError as e:
                out, ok = f"falha ao iniciar o render: {e}", False
            with self.lock:
                self.log = out
                self.ok = ok
                again = self.superseded
                self.superseded = False
                if not again:
                    self.running = False
                    self.finished_at = time.time()
                    return
                self.started_at = time.time()


class Studio:
    """The Prisma EDITOR: HyperFrames Studio, hosted by this server.

    Prisma decides the edit; the person edits it live in Studio, which the UI
    embeds in its Editor tab. This owns the Studio process (one per session),
    started lazily the first time the tab asks, and the export that (re)builds
    the HyperFrames project from the Prisma edit (export_hyperframes.py).
    """

    def __init__(self, root: Path, port: int) -> None:
        self.root = root
        self.port = port
        self.proc: "subprocess.Popen | None" = None
        self.dir: "Path | None" = None
        self.lock = threading.Lock()
        self.export = {"running": False, "ok": None, "log": "", "finishedAt": 0.0}

    def _project(self) -> "Path | None":
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        p = state.get("hyperframes")
        if not p:
            return None
        p = Path(p)
        p = p if p.is_absolute() else (self.root / p)
        return p if (p / "hyperframes.json").exists() else None

    def _alive(self) -> bool:
        # the PORT answering is what counts: on Windows a Studio started by a
        # previous run can outlive it (the .cmd shim dies, node does not)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=1):
                return True
        except OSError:
            return False

    def status(self, start: bool = False) -> dict:
        proj = self._project()
        with self.lock:
            if proj and start and (self.dir != proj or not self._alive()):
                self._start(proj)
            up = self._alive()
            return {
                "available": bool(proj),
                "project": str(proj) if proj else None,
                "running": up,
                # same origin as Prisma: relayed by Handler._proxy
                "url": f"/?hfstudio=1#project/{proj.name}" if (proj and up) else None,
                "export": dict(self.export),
            }

    def _start(self, proj: Path) -> None:
        if self._alive() and self.dir in (None, proj):
            self.dir = proj  # a live Studio from an earlier run: reuse it
            return
        self.stop()
        hf = shutil.which("hyperframes")
        if not hf:
            self.export["log"] = "HyperFrames CLI não encontrado (npm i -g hyperframes@latest)"
            return
        cmd = [hf]
        # Versão fixa por projeto (hf_version.py): o Studio — e portanto o Export
        # final — roda com a versão com que o projeto nasceu, não a instalada.
        try:
            from hf_version import check, recorded
            warn = check(proj)
            if warn and shutil.which("npx"):
                cmd = [shutil.which("npx"), "--yes", f"hyperframes@{recorded(proj)}"]
                print(f"  {warn} → abrindo o Studio com hyperframes@{recorded(proj)}", flush=True)
                self.export["log"] = warn
        except Exception:
            pass
        self.proc = subprocess.Popen(
            [*cmd, "preview", str(proj), "--port", str(self.port), "--no-open"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.dir = proj
        for _ in range(60):  # the Studio bundle takes a few seconds to come up
            if self._alive():
                return
            time.sleep(0.5)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None

    def run_export(self, force: bool) -> dict:
        with self.lock:
            if self.export["running"]:
                return dict(self.export)
            self.export = {"running": True, "ok": None, "log": "", "finishedAt": 0.0}

        def job() -> None:
            script = Path(__file__).resolve().parent / "export_hyperframes.py"
            cmd = [sys.executable, str(script), str(self.root)] + (["--force"] if force else [])
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            with self.lock:
                self.export = {"running": False, "ok": r.returncode == 0,
                               "log": ((r.stdout or "") + (r.stderr or ""))[-1500:],
                               "finishedAt": time.time()}
                if r.returncode == 0:
                    self.stop()  # a fresh project: restart Studio on it next time the tab asks

        threading.Thread(target=job, daemon=True).start()
        return dict(self.export)


class Handler(BaseHTTPRequestHandler):
    root: Path  # set on the class by main()
    render_job: "RenderJob | None" = None  # set on the class by main()
    studio: "Studio | None" = None  # set on the class by main()
    protocol_version = "HTTP/1.1"

    # ---- helpers ----
    def _hdr(self, code: int, ctype: str, length: int | None = None,
             extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._hdr(code, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        """Static file with HTTP Range support (video scrubbing needs it)."""
        if not path.is_file():
            self._json({"error": f"not found: {path.name}"}, 404)
            return
        size = path.stat().st_size
        ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                code = 206
        length = end - start + 1
        extra = {"Content-Range": f"bytes {start}-{end}/{size}"} if code == 206 else None
        self._hdr(code, ctype, length, extra)
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _safe(self, base: Path, rel: str) -> Path | None:
        p = (base / rel.lstrip("/")).resolve()
        return p if str(p).startswith(str(base.resolve())) else None

    def _current_video(self) -> Path | None:
        state_p = self.root / "state.json"
        rel = "cut.mp4"
        if state_p.exists():
            try:
                rel = json.loads(state_p.read_text(encoding="utf-8")).get("video") or rel
            except json.JSONDecodeError:
                pass
        p = self._safe(self.root, rel)
        return p if p and p.exists() else None

    # ---- the Editor, served SAME-ORIGIN ----
    # The Studio used to be framed from its own port. A cross-origin frame is a
    # second-class citizen in Chrome — its media stayed silent inside Prisma even
    # with `allow="autoplay"`, while the same Studio opened alone had sound. So
    # every request that is not one of Prisma's own is relayed to the Studio
    # process: one origin, one page, nothing for the browser to fence off.
    HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
           "proxy-authorization", "proxy-authenticate", "host", "content-length"}

    def _proxy(self) -> None:
        st = self.studio
        if not st:
            self._json({"error": "unknown route"}, 404)
            return
        if not st._alive():
            st.status(start=True)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in self.HOP}
        conn = http.client.HTTPConnection("127.0.0.1", st.port, timeout=600)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
        except OSError as e:
            self._json({"error": f"editor indisponível: {e}"}, 502)
            return
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() not in self.HOP:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        stream = "text/event-stream" in (resp.getheader("Content-Type") or "")
        try:
            while True:
                chunk = resp.read1(65536) if stream else resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                if stream:
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            conn.close()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy()

    # ---- routes ----
    def do_GET(self) -> None:  # noqa: N802
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html") and "hfstudio" in query:
            self._proxy()  # the Editor's own entry page
        elif path in ("/", "/index.html"):
            self._send_file(APP_DIR / "index.html")
        elif path.startswith("/assets/"):
            p = self._safe(APP_DIR, path[len("/assets/"):])
            if p and p.exists():
                self._send_file(p)
            else:
                self._proxy()  # the Studio's own bundle lives under /assets/ too
        elif path.startswith("/media/"):
            p = self._safe(self.root, path[len("/media/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path == "/gen/waveform.json":
            self._waveform()
        elif path.startswith("/gen/thumbs/"):
            self._thumbs(path[len("/gen/thumbs/"):])
        elif path == "/api/render":
            self._json(self.render_job.status() if self.render_job
                       else {"error": "render indisponível"})
        elif path == "/api/studio":
            self._json(self.studio.status(start=True) if self.studio else {"available": False})
        elif path == "/api/state":
            self._state()
        elif path == "/api/engines":
            self._engines()
        else:
            self._proxy()

    def _engines(self) -> None:
        """Which Phase-2 layers HyperFrames draws (hfkit LAYERS) and, for this video,
        which ON layers send it to Remotion — the Estilo tab labels those "via Remotion"."""
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from hfkit.layers import public_table, unported
            pub = self.root / "remotion" / "public"
            ed_p = pub / "edit-data.json"
            ed = json.loads(ed_p.read_text(encoding="utf-8")) if ed_p.exists() else {}
            miss = unported(ed, pub, self.root) if ed else []
            st = {}
            if (self.root / "state.json").exists():
                st = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
            self._json({"layers": public_table(), "unported": miss,
                        "engine": st.get("engine") or ("remotion" if miss else "hyperframes"),
                        "engineFallback": st.get("engineFallback") or miss})
        except Exception as e:  # never break the UI over a status call
            self._json({"error": str(e)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route == "/api/studio/export":
            force = "force=1" in (self.path.split("?", 1)[1] if "?" in self.path else "")
            self._json(self.studio.run_export(force) if self.studio else {"error": "studio indisponível"})
            return
        if route == "/api/render":
            if not self.render_job:
                self._json({"error": "render indisponível"}, 503)
                return
            self._json(self.render_job.request())
            return
        if route != "/api/save":
            self._proxy()  # the Editor saving its own edits
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        body["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # The style pick goes to its own file. It is a one-time setup decision,
        # not a correction, and sharing preview_edits.json would make one save
        # clobber the other (they are written at different moments, by different
        # screens, and the skill consumes+deletes them independently).
        name = "preview_style.json" if body.get("type") == "style-setup" else "preview_edits.json"
        out = self.root / name
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
        applied = self._apply_timings(body) if name == "preview_edits.json" else []
        self._json({"ok": True, "file": str(out), "applied": applied})

    def _apply_timings(self, body: dict) -> list:
        """Write insert/hook timings straight into edit-data.json.

        Saving used to only drop preview_edits.json and wait for the agent. From
        the user's side that reads as "I dragged the handle, I pressed save, and
        nothing happened" — the timeline redrew, the file on disk still held the
        old times, and the player kept playing the previous render. Timings are
        plain numbers with no editorial judgement in them, so the server applies
        them itself and the drawing and the data agree immediately.

        What this does NOT do is re-render. The picture is a rendered file; only
        a new render changes it. The UI says so through its own stale pill, which
        keys off edit-data.json being newer than the video.
        """
        applied_caps = self._apply_captions(body)
        ed_data = (body.get("editData") or {})
        if not ed_data:
            return applied_caps
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
            rel = state.get("editData")
            if not rel:
                return []
            p = self._safe(self.root, rel)
            if not p or not p.exists():
                return []
            ed = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        applied = []
        for key in ("inserts", "splitInserts", "splitVideos", "behind"):
            for item in ed_data.get(key) or []:
                ref = item.get("ref")
                target = ed.get(key) or []
                if not isinstance(ref, int) or not (0 <= ref < len(target)):
                    continue
                entry = target[ref]
                before = (entry.get("start"), entry.get("end"), entry.get("dur"))
                if "start" in item:
                    entry["start"] = item["start"]
                if "end" in item:
                    entry["end"] = item["end"]
                if "dur" in item:
                    entry["dur"] = item["dur"]
                after = (entry.get("start"), entry.get("end"), entry.get("dur"))
                if before != after:
                    applied.append(f"{key}[{ref}]")

        # keyword glass cards (GlassCard.tsx): same contract as the inserts, keyed
        # on `at` (the moment the word is said) + `dur`
        cards = (ed.get("highlights") or {}).get("items") or []
        for item in ed_data.get("highlights") or []:
            ref = item.get("ref")
            if not isinstance(ref, int) or not (0 <= ref < len(cards)):
                continue
            entry = cards[ref]
            before = (entry.get("at"), entry.get("dur"))
            for k in ("at", "dur"):
                if isinstance(item.get(k), (int, float)):
                    entry[k] = item[k]
            if item.get("delete"):
                entry["_deleted"] = True
            if before != (entry.get("at"), entry.get("dur")) or item.get("delete"):
                applied.append(f"highlights[{ref}]")
        if any(c.get("_deleted") for c in cards):
            ed["highlights"]["items"] = [c for c in cards if not c.get("_deleted")]

        hook = ed_data.get("hook")
        if hook and isinstance(hook.get("endSec"), (int, float)) and ed.get("hook"):
            if ed["hook"].get("endSec") != hook["endSec"]:
                ed["hook"]["endSec"] = hook["endSec"]
                applied.append("hook.endSec")

        st = ed_data.get("soundtrack")
        if st and isinstance(st.get("volume"), (int, float)) and ed.get("soundtrack"):
            if ed["soundtrack"].get("volume") != st["volume"]:
                ed["soundtrack"]["volume"] = st["volume"]
                applied.append("soundtrack.volume")

        if applied:
            t = p.with_suffix(".tmp")
            t.write_text(json.dumps(ed, ensure_ascii=False, indent=2), encoding="utf-8")
            t.replace(p)
        return applied_caps + applied

    def _apply_captions(self, body: dict) -> list:
        """Write the caption words the user edited straight into captions.json.

        Text and word timings are the user's decision, not an editorial call, so
        the same rule as the insert timings applies: the file agrees with the
        timeline the moment they save. Validated hard — a malformed list would
        break the Remotion bundle, so anything off keeps the old file.
        """
        words = body.get("captions")
        if not isinstance(words, list) or not words:
            return []
        clean = []
        for w in words:
            try:
                text = str(w["text"]).strip()
                a, b = int(w["startMs"]), int(w["endMs"])
            except (KeyError, TypeError, ValueError):
                return []
            if not text or b <= a or a < 0:
                return []
            clean.append({"text": text, "startMs": a, "endMs": b})
        clean.sort(key=lambda w: w["startMs"])
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
            p = self._safe(self.root, state.get("captions") or "")
        except (OSError, json.JSONDecodeError):
            return []
        if not p or not p.exists():
            return []
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = None
        # keep any extra per-word fields the generator wrote (speakerId…) when
        # the word survived unchanged
        if isinstance(old, list):
            extra = {(o.get("text"), o.get("startMs")): o for o in old if isinstance(o, dict)}
            clean = [{**extra.get((w["text"], w["startMs"]), {}), **w} for w in clean]
        t = p.with_suffix(".tmp")
        t.write_text(json.dumps(clean, ensure_ascii=False), encoding="utf-8")
        t.replace(p)
        return [f"captions ({len(clean)} palavras)"]

    # ---- dynamic bits ----
    def _state(self) -> None:
        state_p = self.root / "state.json"
        state: dict = {}
        try:
            if state_p.exists():
                state = json.loads(state_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"error": "state.json inválido"}
        except OSError as e:
            # A read that is refused (macOS privacy, or a permission change made
            # after startup) used to raise here and 500 the endpoint, which the
            # UI shows as its ordinary waiting screen — indistinguishable from
            # "the cut is not rendered yet". Say what happened instead.
            state = {"error": f"sem permissão para ler state.json: {e}"}
        # attach small data files + mtimes so the UI hot-reloads on change
        mtimes: dict[str, float] = {}
        for key in ("video", "finalVideo", "videoNoMusic", "edl", "captions", "editData",
                    "soundtrack"):
            rel = state.get(key)
            if not rel:
                continue
            p = self._safe(self.root, rel)
            if p and p.exists():
                mtimes[key] = p.stat().st_mtime
        edl = None
        rel = state.get("edl") or "edl.json"
        p = self._safe(self.root, rel)
        if p and p.exists():
            try:
                edl = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        edits_p = self.root / "preview_edits.json"
        video = self._current_video()
        try:
            from staleness import check as _stale
            stale = _stale(self.root, state if "error" not in state else None)
        except Exception:
            stale = []
        try:
            from agent_markers import load as _markers
            agent_markers = _markers(self.root)
        except Exception:
            agent_markers = []
        self._json({
            "state": state,
            "edl": edl,
            "mtimes": mtimes,
            "staleness": stale,
            "agentMarkers": agent_markers,
            "videoDuration": probe_duration(video) if video else 0,
            "hasPendingEdits": edits_p.exists(),
            "now": time.time(),
        })

    def _waveform(self) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out = self.root / ".preview_cache" / "waveform.json"
        stale = True
        if out.exists():
            try:
                stale = json.loads(out.read_text(encoding="utf-8")).get("srcMtime") != video.stat().st_mtime
            except json.JSONDecodeError:
                pass
        if stale:
            gen_waveform(video, out)
        self._send_file(out)

    def _thumbs(self, name: str) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out_dir = self.root / ".preview_cache" / "thumbs"
        meta = out_dir / "meta.json"
        with _thumb_lock:
            stale = True
            if meta.exists():
                try:
                    stale = json.loads(meta.read_text(encoding="utf-8")).get("srcMtime") != video.stat().st_mtime
                except json.JSONDecodeError:
                    pass
            if stale:
                gen_thumbs(video, out_dir)
        p = self._safe(out_dir, name)
        self._send_file(p) if p else self._json({"error": "bad path"}, 400)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # quiet


def _check_access(root: Path) -> None:
    """Fail loudly, at startup, when the edit dir cannot be read or written.

    Without this the failure is silent in the worst way: the server starts, the
    UI opens on its waiting screen, and it waits forever for a state.json that
    the skill was never allowed to write. The user sees a working preview with
    no video and nothing to act on.

    The errno is the diagnosis on macOS. Its privacy layer (TCC) guards
    ~/Documents, ~/Desktop, ~/Downloads and iCloud Drive, and denies with
    EPERM (1) "Operation not permitted" — an app the user never granted Files
    and Folders access to gets that even though the file permissions are fine.
    Ordinary permission or ownership problems come back as EACCES (13). The two
    need completely different fixes, so do not merge the messages.
    """
    probe = root / ".prisma_write_probe"
    err: OSError | None = None
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        for _ in root.iterdir():
            break
    except OSError as exc:
        # Bind outside the handler: Python deletes the `except` name on exit.
        err = exc
    if err is None:
        return

    where = f"{root}"
    if getattr(err, "errno", None) == 1 and sys.platform == "darwin":
        raise SystemExit(
            f"sem permissão para escrever em {where}\n"
            "\n"
            "No macOS isso é a proteção de privacidade do sistema, não a permissão\n"
            "do arquivo: ~/Documents, ~/Desktop, ~/Downloads e o iCloud Drive são\n"
            "protegidos, e o app precisa ser autorizado uma vez.\n"
            "\n"
            "  Ajustes do Sistema → Privacidade e Segurança → Arquivos e Pastas\n"
            "  (ou Acesso Total ao Disco) → ligue para o Claude / o Terminal\n"
            "\n"
            "Depois feche e reabra o app.\n"
            "\n"
            "SE AS PERMISSÕES JÁ ESTIVEREM LIGADAS: reinicie o Mac. O cache de\n"
            "permissões do macOS às vezes fica preso mostrando a chave ativa sem\n"
            "conceder o acesso, e só o reinício resolve. (Visto em produção — foi\n"
            "exatamente isso, e nenhuma mexida nos Ajustes tinha efeito.)\n"
            "\n"
            "Se preferir não lidar com permissão, mova a pasta dos vídeos para fora\n"
            "dessas três pastas — por exemplo ~/Videos."
        )
    raise SystemExit(
        f"sem permissão para ler/escrever em {where}: {err}\n"
        "Confira o dono e as permissões da pasta."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Prisma preview interface server")
    ap.add_argument("--root", type=Path, required=True, help="the session <edit> dir")
    ap.add_argument("--port", type=int, default=4820)
    ap.add_argument("--studio-port", type=int, default=0,
                    help="port for the embedded HyperFrames Studio (default: --port + 10)")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"edit dir not found: {root}")
    _check_access(root)
    if not (APP_DIR / "index.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")

    Handler.root = root
    Handler.render_job = RenderJob(root)
    # the Editor tab's Studio runs next to this server; stopped with it
    Handler.studio = Studio(root, args.studio_port or args.port + 10)
    atexit.register(Handler.studio.stop)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True  # the Editor's live event stream must not block shutdown
    print(f"Prisma preview → http://127.0.0.1:{args.port}  (root: {root})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
