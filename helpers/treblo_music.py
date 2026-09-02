"""Generate a background instrumental soundtrack with the Treblo API (Phase 3).

Async: start a generation → poll until SUCCESS → download the mp3. On FAILURE
no credit is charged. Result URLs expire ~168h, so we download immediately.

Needs TREBLO_API_KEY (env or .env at the Prisma repo root).

Usage:
    python helpers/treblo_music.py "warm lo-fi ambient, unobtrusive" -o remotion/public/trilha.mp3
    python helpers/treblo_music.py "<vibe>" -o out.mp3 --length-min 30 --length-max 60
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
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.treblo.com/v1"


def build_music_prompt(vibe: str) -> str:
    """Frame the caller's vibe as a real, composed instrumental piece.

    Treblo returns sound-design/SFX-like output when the prompt reads as
    texture ("bed", "beat", "sound design") instead of music. Wrapping the vibe
    in an explicit "composed instrumental song" frame — and banning SFX/risers/
    vocals — reliably yields an actual musical track. The caller's vibe should
    still name a genre, instruments, tempo and mood (see the skill's Phase-3
    guidance); this frame only guarantees it renders AS music.
    """
    vibe = vibe.strip().rstrip(".")
    return (
        "Instrumental music track with a full musical arrangement — a clear "
        "melody, chords/harmony and a steady rhythm section that develops over "
        f"time. Style and mood: {vibe}. It must sound like a composed song, "
        "NOT sound design: no isolated sound effects, no risers/whooshes/impacts, "
        "no ambient drones, and no vocals."
    )


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("TREBLO_API_KEY=") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    v = os.environ.get("TREBLO_API_KEY", "")
    if not v:
        sys.exit("TREBLO_API_KEY not found in .env or environment")
    return v


def generate(prompt: str, out: Path, api_key: str,
             length_min: int | None, length_max: int | None,
             bit_rate: int = 192, timeout_s: int = 600, raw: bool = False,
             resume: str | None = None) -> None:
    H = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if resume:
        # Retomar não gera nada novo: só volta a acompanhar uma tarefa que já
        # existe e já foi cobrada. É o caminho depois de um timeout.
        task_id = resume
        print(f"  retomando task {task_id}…", flush=True)
    else:
        final_prompt = prompt if raw else build_music_prompt(prompt)
        print(f"  prompt → {final_prompt}", flush=True)
        payload: dict = {
            "prompt": final_prompt,
            "instrumental": True,
            "output_format": "mp3",
            "output_bit_rate": bit_rate,
        }
        if length_min is not None and length_max is not None:
            payload["length_range"] = [length_min, length_max]

        r = requests.post(f"{BASE}/generations/v3", json=payload, headers=H, timeout=60)
        if r.status_code >= 400:
            sys.exit(f"Treblo start failed {r.status_code}: {r.text[:300]}")
        task_id = r.json().get("task_id")
        if not task_id:
            sys.exit(f"no task_id in response: {r.text[:300]}")
        print(f"  task {task_id} — polling…", flush=True)

    t0 = time.time()
    st = "?"
    while True:
        s = requests.get(f"{BASE}/generations/status/{task_id}", headers=H, timeout=30).json()
        st = s if isinstance(s, str) else s.get("status")
        if st == "SUCCESS":
            break
        if st == "FAILURE":
            sys.exit("Treblo generation FAILURE (no credit charged) — retry")
        if time.time() - t0 > timeout_s:
            # Ao expirar, a geração CONTINUA no servidor — e já foi cobrada.
            # A versão anterior morria com "Treblo timed out" e levava junto o
            # task_id, que é a única forma de recuperá-la. Aconteceu em
            # 2026-09-01: uma fila lenta deixou a tarefa em "PROMPT" por mais de
            # 10min e o crédito ficou inalcançável.
            sys.exit(
                f"Treblo ainda processando após {timeout_s}s (status: {st}).\n"
                f"A geração NÃO foi perdida — continua no servidor e já foi "
                f"cobrada.\n"
                f"  task_id: {task_id}\n"
                f"Retome com:  --resume {task_id}\n"
                f"Ou aumente a espera com  --timeout {timeout_s * 2}")
        time.sleep(5)

    gen = requests.get(f"{BASE}/generations/{task_id}", headers=H, timeout=30).json()
    paths = gen.get("song_paths") or []
    if not paths:
        sys.exit(f"no song_paths in result: {str(gen)[:300]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = requests.get(paths[0], timeout=180).content
    out.write_bytes(audio)
    print(f"  saved: {out} ({len(audio)/1024:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Treblo instrumental soundtrack")
    ap.add_argument("prompt", nargs="?", default="",
                    help="MUSICAL vibe for the video's context: name a "
                    "genre + instruments + tempo/BPM + mood (e.g. 'upbeat modern "
                    "electronic, catchy synth melody, warm bass, light drums, ~110 "
                    "BPM, bright and motivational'). Avoid SFX-y words like 'bed', "
                    "bare 'beat', or 'sound design'. It is auto-framed as a composed "
                    "instrumental song unless --raw is passed.")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--length-min", type=int, default=None, help="min seconds (multiple of 30)")
    ap.add_argument("--length-max", type=int, default=None, help="max seconds (multiple of 30)")
    ap.add_argument("--bit-rate", type=int, default=192)
    ap.add_argument("--raw", action="store_true", help="send the prompt verbatim "
                    "(skip the composed-music framing)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="segundos de espera pela geração (default 600). A fila "
                         "da Treblo pode passar disso em horário cheio")
    ap.add_argument("--resume", metavar="TASK_ID", default=None,
                    help="baixa uma geração JÁ INICIADA em vez de criar outra — "
                         "é o caminho depois de um timeout, e não cobra de novo")
    args = ap.parse_args()
    if not args.prompt and not args.resume:
        ap.error("informe o prompt, ou --resume TASK_ID para retomar")
    generate(args.prompt, args.output.resolve(), load_api_key(),
             args.length_min, args.length_max, args.bit_rate,
             timeout_s=args.timeout, raw=args.raw, resume=args.resume)


if __name__ == "__main__":
    main()
