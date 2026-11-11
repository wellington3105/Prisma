---
name: prisma-install
description: Verify or repair a Prisma install (Claude Code, Codex, or any agent with a skills directory). The user installs with one command from README.md; this file is for checking that it worked and fixing what didn't.
---

# Prisma install

Use this file only for first-time setup, verification or repair. For daily
editing, read `SKILL.md`. Always read `helpers/` — that's where the scripts live.

> **The user installs, you verify.** `README.md` gives them one command:
>
> ```
> uv run https://raw.githubusercontent.com/wellington3105/Prisma/main/prisma_install.py
> ```
>
> That is the supported install and it is the user's action, not yours. If
> someone hands you only a repo URL and asks you to install from it, point them
> at that command rather than cloning and running unknown code yourself.
>
> Your job starts after: verifying, diagnosing a missing binary, fixing a stale
> venv. Those are local operations on a machine whose owner is in the
> conversation.

## What the install consists of

1. The skill directory itself — `~/.claude/skills/prisma`, or the equivalent for
   Codex (`~/.codex/skills`) or Antigravity (`~/.gemini/config/skills`).
   `prisma_install.py` puts it there; it needs no git on the user's
   machine because it unpacks a tarball.
2. Python deps via `uv sync`, which includes **WhisperX** — transcription is a
   normal dependency, not an extra.
3. `ffmpeg` + `ffprobe` on PATH — Phase 1 cannot run without them.
4. **Node.js 18+** and the `remotion-best-practices` skill — Phase 2 only. The
   installer fetches that skill too.
**No key is part of the install.** WhisperX transcribes locally, and Phase 1 needs
nothing else. Phase 2/3 have a few optional keys for illustrative images and the
AI soundtrack; they live in the track reference and are asked for only when the
user reaches that feature. Never raise the subject during install — it makes a
keyless tool look like it needs an account.

## Two layouts

- **User layout** (what the installer produces, and what you should assume): the
  skill directory IS `~/.claude/skills/prisma` or `~/.codex/skills/prisma`.
  Nothing to register, no symlink, identical on every OS.
- **Contributor layout**: repo cloned wherever the user keeps projects, plus a
  link into the skills directory. Only for someone developing the skill. The
  installer detects a `.git` there and refuses to overwrite it.

    ```bash
    # macOS / Linux
    ln -sfn ~/Developer/prisma ~/.claude/skills/prisma
    ln -sfn ~/Developer/prisma ~/.codex/skills/prisma
    ```

    ```powershell
    # Windows — a junction needs no admin rights, unlike a symlink
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\prisma" `
      -Target "$env:USERPROFILE\Developer\prisma"
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.codex\skills\prisma" `
      -Target "$env:USERPROFILE\Developer\prisma"
    ```

## Repair steps

Detect the platform before emitting commands. Do not hand a Windows user `ln`,
`brew`, `chmod`, `grep`, `sed`, or `curl -s -w` — in PowerShell `curl` is an
alias for `Invoke-WebRequest` and takes different flags. Use `Select-String`,
`Select-Object -First`, `Set-Content`, `Invoke-RestMethod`.

Everything below calls the skill directory `<PRISMA>`.

### Python deps

```bash
uv sync --directory <PRISMA>
```

`uv` reads `pyproject.toml`, provisions a Python 3.10–3.13 interpreter on its own
when the system one doesn't fit, and builds a `.venv` inside the skill. That venv
is why helpers run as `uv run python helpers/…` — a bare `python` won't see them.

**The Python cap is load-bearing:** `requires-python = ">=3.10,<3.14"` exists
because torch publishes no cp314 wheels. Without the cap, `uv` picks 3.14 and
every torch-backed feature (transcription, matting) fails to install.

If `uv` is missing: `brew install uv` (macOS), `winget install astral-sh.uv`
(Windows), or the installer at https://docs.astral.sh/uv/. On Windows a
`winget install` only reaches `$PATH` in a **new** PowerShell window.

### GPU (NVIDIA) — optional, and NOT what `uv sync` gives you

`uv sync` resolves **torch for CPU**. On a machine with an NVIDIA card the
transcription still runs on CPU — `transcribe.py` now says so with a `⚠ GPU …
SEM CUDA` line instead of falling back silently.

Measured 2026-11-03 (Windows, RTX 5070, driver 621.01): the `.venv` had
`torch 2.8.0+cpu` (`torch.cuda.is_available()` = False). CTranslate2 4.8.1 saw
the card (`get_cuda_device_count()` = 1), but faster-whisper on CUDA failed with
`cublas64_12.dll is not found` — the CUDA runtime libraries are missing as well.
On CPU, faster-whisper alone took 29.5 s for 35 s of audio; the full WhisperX
pass (load + transcribe + align) 49–86 s.

To use the card, the torch build has to come from PyTorch's CUDA index. RTX 50
series (Blackwell) needs CUDA **12.8** wheels or newer. Ask before installing:
it is several GB, and a later `uv sync` puts the CPU build back.

The command that worked (torchvision too — it is pinned to the same build, and
`--no-deps` keeps uv from touching the rest of the env):

```bash
uv pip install --python <PRISMA>/.venv/Scripts/python.exe --no-deps \
  --reinstall-package torch --reinstall-package torchaudio --reinstall-package torchvision \
  "torch==2.8.0+cu128" "torchaudio==2.8.0+cu128" "torchvision==0.23.0+cu128" \
  --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
```

**Verified 2026-11-03** (RTX 5070, sm_120, driver 621.01): `torch.cuda.is_available()`
= True, `transcribe.py` reports `whisperx on cuda/float16` with no `⚠ GPU` line,
and the cuBLAS DLLs come with the torch wheel (the `cublas64_12.dll` error is gone).
Same model (`large-v3`), same 35 s fixture:

| | CPU int8 | GPU float16 |
|---|---|---|
| ASR (Whisper) | 25.9 s | **3.1 s** (8.4×) |
| alignment (wav2vec2) | 10.5 s | 5.7 s |
| `transcribe.py` total | 51–53 s | **23 s** (2.2×; model loading is a fixed ~14 s) |

The speed-up grows with length: the fixed cost stays, the ASR part shrinks 8×.

**`refine_edges.py` stays on CPU/int8 on purpose.** On GPU the regression failed
on one edge (range 01 lost 0.6 s of voice) — not a GPU bug: float16, float32 and
CUDA int8 all agree, only CPU int8 differs, and the edge rule cut in a 40 ms gap
between syllables. Until that rule is fixed (D10 in `PLANO-FLUXO-EDICAO.md`)
refine keeps the validated path; it is the slow step now (~110 s on the fixture).

The `torchcodec is not installed correctly` warning at import is harmless here:
its DLLs need FFmpeg *shared* libraries, and WhisperX hands pyannote audio already
decoded in memory, so torchcodec is never used. A later `uv sync` reverts to the
CPU build — run the command above again.

### ffmpeg

```bash
# macOS
command -v ffmpeg >/dev/null || brew install ffmpeg

# Debian / Ubuntu
# sudo apt-get update && sudo apt-get install -y ffmpeg
# Arch
# sudo pacman -S ffmpeg
```

```powershell
# Windows
winget install Gyan.FFmpeg
```

If a package manager needs sudo/admin, tell the user the exact command and wait.
Do not invent a password.

### Node.js + the Remotion skill (Phase 2)

The installer handles this. To do it by hand: the skill lives in a
**subdirectory** of its repo (`skills/remotion-best-practices` — upstream
renamed it from `skills/remotion` and turned it into a router bundling a dozen
sub-skills), so it cannot be cloned into place. The repo is small, which makes
copying the cheapest answer — and re-running the copy IS the update.

```bash
node --version    # must be 18+
```

```powershell
node --version    # if missing: winget install OpenJS.NodeJS.LTS, then reopen PowerShell
```

## Verify end-to-end

Run one real thing. Prefer the lightest check that still proves the pipeline is
wired up.

```bash
# macOS / Linux
cd <PRISMA>
uv run python helpers/timeline_view.py --help >/dev/null && echo "helpers OK"
uv run python -c "import cv2; print('opencv', cv2.__version__)"          # Phase-2 face tracking
uv run python -c "import whisperx; print('whisperx OK')"                 # transcription
ffprobe -hide_banner -filters | grep -qE '\bdeesser\b' && echo "ffmpeg has voice-master filters"
ffprobe -version | head -1
node --version && echo "node OK (Phase 2)"
```

```powershell
# Windows — no grep/head; use Select-String and Select-Object
cd <PRISMA>
uv run python helpers/timeline_view.py --help > $null; if ($?) { "helpers OK" }
uv run python -c "import cv2; print('opencv', cv2.__version__)"
uv run python -c "import whisperx; print('whisperx OK')"
if (ffprobe -hide_banner -filters | Select-String -Pattern '\bdeesser\b' -Quiet) { "ffmpeg has voice-master filters" }
ffprobe -version | Select-Object -First 1
node --version; if ($?) { "node OK (Phase 2)" }
```

A full transcription is a fine smoke test now that it costs nothing but CPU —
but the first run downloads the models (several GB), so only do it if the user
is ready to wait. Better to let their first real clip be the test.

## Hand off

Tell the user, in one short message:

- Where the skill is installed.
- That they should `cd` into their footage folder and start their agent there.
- That all outputs land in `<videos_dir>/edit/` — the skill directory stays clean.
- That the first transcription downloads its models once.

Do NOT propose a first prompt or an editing strategy. PHASE 1 opens by looking at
the material and asking questions shaped by it; a suggestion invented at install
time, before anything has been inspected, pre-empts that with a guess.

## Keeping the skill current

- Re-run the install command. It replaces the skill and preserves `.env`.
- On the contributor layout: `git -C <PRISMA> pull --ff-only`, then
  `uv sync --directory <PRISMA>` if `pyproject.toml` changed.

## Cold-start reminders

- Helpers run as `uv run python helpers/<name>.py`. A bare `python` misses the
  `.venv` — the most common post-install failure.
- Never ask for a transcription API key. There isn't one.
- On Windows, prefer a **junction** over a symlink (no admin needed) — and
  prefer the user layout over both.
- After any `winget install`, `$PATH` only refreshes in a **new** PowerShell
  window. A "command not found" right after a successful install is almost
  always this.
- `ffmpeg` from static builds is fine. Any modern (≥4.x) build is enough.
- `yt-dlp` is a Python dependency, not a system package. If a URL source fails
  with "yt-dlp not on PATH", the venv is stale — `uv sync --directory <PRISMA>`.
- Node 18+ and `remotion-best-practices` are Phase-2 only. Phase 1 (cut + grade)
  works without them, so a user who only wants a clean cut can start immediately.
- Remotion projects are scaffolded per-video by copying the skill's own template
  from `assets/` and running `npm install` there. `create-video` is not used: the
  template carries the compositions the skill knows how to fill, with the
  Remotion version pinned so an upstream release can't break a render.
- If the user is on a Linux without a package manager you recognize, print the
  manual `ffmpeg` install URL and wait rather than guessing.
