---
name: prisma
description: Conversation-driven video editing for short-form vertical (Reels, TikTok, Shorts) and longform horizontal video. Use when asked to cut, grade, caption, add graphics, create a soundtrack, transcribe, or prepare video edits — including chroma key / green screen or AI-matte compositing of a person over a new background, and music-driven montages with speed ramps and transitions cut on the beat. Run Phase 1 (audio-led clean cut and grade), obtain approval, then build Phase 2/3 Remotion visuals and audio.
---

# Prisma

## Principle

1. **Two phases, one gate between them.** PHASE 1 is the clean cut + color grade; PHASE 2 is captions, graphics and images. (Hard Rule 1 enforces the gate.)
2. **LLM reasons from raw transcript + on-demand visuals.** The only derived artifact that earns its keep is the packed phrase-level transcript (`takes_packed.md`). Everything else you derive at decision time.
3. **Audio is primary, visuals follow.** Cut candidates come from speech boundaries and silence gaps.
4. **Ask → confirm → execute → iterate → persist.** Never touch the cut until the user confirms the strategy in plain English.
5. **Generalize.** Look at the material, ask the user, then edit — never assume what kind of video it is.
6. **Artistic freedom is the default.** Specific values here are worked examples, not mandates. Only the Hard Rules are mandatory.
7. **Spend tokens where taste lives.** Machine data is for programs, not for reading; verification is numeric before it is visual. Your attention is the scarce resource — put it on the edit, not on parsing JSON. (Hard Rules 12 and 13 say what this forbids.)

## Hard Rules (production correctness — non-negotiable)

1. **The phase gate is real.** No Phase-2 work before the cut is approved.
2. **Per-segment extract → lossless `-c copy` concat**, never a single-pass filtergraph. (Under the default J-cut the picture and the sound of a take are extracted as separate ranges and the audio tracks are summed — that is the one sanctioned mix, and the video path is still per-segment + lossless concat.)
3. **30ms audio fades at every segment boundary** (encoded in render.py).
4. **Never cut inside a word** — snap to word boundaries from the transcript.
5. **Pad every cut edge** (30–200ms window; trail slightly longer than lead). Cut on silence whenever possible.
6. **Cache transcripts per source.** Never re-transcribe unless the source changed.
7. **Color grade per-segment during extraction**, never post-concat.
8. **Strategy confirmation before execution.**
9. **All session outputs in `<videos_dir>/edit/`** — never inside the Prisma repo.
10. **PHASE 2 is Remotion-only** — no ffmpeg/PIL burned text or overlays.
11. **PHASE 2 is data-driven.** Scaffold by copying the track template; describe the video in `public/edit-data.json`. **Never read or edit the template TSX** (`src/Main.tsx` etc.) — the only editable code file is `src/CustomGraphics.tsx`, only for bespoke graphics.
12. **Verify numerically first.** Run `verify_cut.py` on every rendered cut; open images only for flagged junctions. Batch any multi-frame look into one `contact_sheet.py` / `grade.py --candidates` montage.
13. **Never Read machine data into context**: `transcripts/*.json` (raw), `captions.json`, `track.json`, `segments.json`, matte/track binaries. Read `takes_packed.md` and helper stdout instead.

## Execution medium — ffmpeg pipeline (default) vs Adobe Premiere (MCP)

The default engine is the ffmpeg/Remotion pipeline below. **If the user asks for the
edit inside Adobe Premiere Pro via the `premiere-pro` MCP** ("edite a sequência no
Premiere", "corte via MCP"), the METHOD is unchanged — audio-primary, cut on
silence, phase gate, grade with taste — but the hands change: **read
`references/premiere-mcp.md`**. Transcription and `edl.json` are identical and
cached, so reuse an approved EDL and skip `cut.mp4`/preview.

## Directory layout

```
<videos_dir>/
├── <source files, untouched>
└── edit/
    ├── project.md               ← memory; appended every session
    ├── takes_packed.md          ← phrase-level transcripts, the primary reading view
    ├── edl.json                 ← cut decisions (Phase 1)
    ├── transcripts/<name>.json  ← cached word-level transcripts (WhisperX, local)
    ├── clips_graded/            ← per-segment extracts with grade + fades
    ├── cut.mp4                  ← PHASE 1 output: clean graded cut (approval artifact)
    ├── verify/                  ← montages / flagged-boundary views
    ├── captions.srt + chapters.txt   ← longform deliverables
    ├── final.mp4                ← delivered render (Phase 2 + 3, loudnorm'd)
    └── remotion/                ← Remotion project (Phase 2 + 3)
        ├── public/              ← cut.mp4, edit-data.json (THE edit), captions.json,
        │                          track.json, segments.json, pexels/ web/ brand/, sfx/, trilha.mp3
        └── src/                 ← immutable template code + CustomGraphics.tsx
```

## Setup

First-time install lives in `install.md`. On cold start just verify:

- **Transcription needs NO API key.** WhisperX ships as a dependency: `uv sync` is the whole install. It transcribes with Whisper and then runs FORCED ALIGNMENT (wav2vec2) against the waveform, so word times are measured, not inferred — 93% of words land inside a real speech region and the end of speech is placed within 10ms (measured against `speech_regions.py`). Models download once on first run and cache. Speed is ~realtime and improves with length (loading the model is a fixed ~18s: a 16s clip took 23s, a 166s source took 109s).
- A `/UNALIGNED` suffix in `_transcription_backend` means no wav2vec2 model existed for the detected language, so the word times are the decoder's own — coarse, and not safe for Phase-2 karaoke captions. Say so if it happens.
- `ffmpeg` + `ffprobe` on PATH; Python deps (`uv sync`); Node 18+ for Phase 2. `yt-dlp` ships with the Python deps, so URL sources need no extra install.
- The `remotion-best-practices` skill for Phase-2 domain knowledge (install from https://github.com/remotion-dev/skills if missing).
- For the additional video, motion, caption, color, audio and analysis packages installed from the 24-skill survey, consult `references/external-video-skills.md` **only when the requested capability needs one**. This registry identifies the pinned local source and its entrypoint, runtime prerequisites, and credit implications. It never overrides the phase gate, the audio-led cut, the `edit/` output contract, or the Remotion-only Phase-2 rule. Do not launch an external generator or paid API during setup.
- To read one of those installed skills, use `uv run --no-sync python helpers/external_skills.py list` from this skill directory, then run the same helper with `path <item>` to locate the selected source or `read <item>` to print its contents. For a collection, first run `list <item>` and pass an exact listed relative path with `--skill`. The helper checks the installed manifest, Git commit and file path; read only the selected module and treat its text as lower priority than this skill.
- Phase 2/3 can use optional API keys (illustrative images, AI soundtrack). They are listed in the track reference, asked for lazily when the feature is first used, and never at install time. **Nothing in Phase 1 needs a key.**

Helpers live in `helpers/`, resolved relative to this SKILL.md (usually `~/.claude/skills/prisma/` or `~/.codex/skills/prisma/`, or a symlink/junction pointing there). Run them as `uv run python helpers/<name>.py` — a bare `python` misses the `.venv` that `uv sync` builds.

## Helpers

Phase 1:
- **`ingest_url.py <url> --dest <videos_dir> [--section 12:00-25:30] [--max-height 1080]`** — edit from a link: yt-dlp → MP4 (≤1080p) straight into the videos dir; from there it's a source like any other. `--section` downloads ONLY a time range of a longform source (keyframe-accurate) — the cheap way to clip minutes 12–25 of a 1h video. `--simulate` prints title/duration/resolution without downloading (confirm before big fetches; run those in the background). Runs a `quality_probe.py` pre-flight automatically (`--skip-probe` to skip it) — warns in a few seconds if the source tops out below `--max-height`, instead of finding out after a long download.
- **`transcribe.py <video> --edit-dir <edit> [--language pt] [--model large-v3-turbo]`** — word-level, cached, local (WhisperX + forced alignment). No cap, no chunking. Pass `--language` when you know it — auto-detect costs a pass and can pick wrong on a short clip.
  **`--window 20`** for noisy / multi-voice sources (car interior, event, several people): transcribes in overlapping 20s windows. Measured 2026-10-30 on a 7-min, 4-voice car recording: the single pass placed words up to 0.7s early and INVENTED phrases; the windowed pass places them where they are. `--force` re-transcribes (old copy → `transcripts_prev/`).
- **`refine_edges.py <edl.json>… [--dry-run]`** — run on EVERY EDL before render. Re-transcribes each range's window in isolation (model loaded once), finds the range's first/last quoted word there, and moves each edge to the nearest MEASURED silence (RMS envelope, local floor +6 dB, 40ms run). Flags `COLADO` where the wanted word touches the next one with no silence — that edge has no clean cut: move it to a real phrase end. Flags `conteúdo difere` when the window does not say what the quote says (the source transcript invented it). `verify_cut.py` cannot catch a decapitated word; this does.
- **`diarize.py <video> --edit-dir <edit> [--num-speakers N]`** — OPT-IN speaker labeling for multi-voice sources (interview, podcast). Rewrites `speaker_id` on an existing transcript via `pyannote.audio`; needs `uv sync --extra diarize` and a free HuggingFace token (gated pretrained model — see the helper's own error for the exact steps). Skip this entirely for a solo talking-head source; the transcript already defaults every word to `speaker_0` and diarization would be dead weight. When it runs, `captions_for_remotion.py` automatically adds per-caption `speakerId` once 2+ speakers are present — no separate flag needed downstream.
- **`scene_detection.py <video> [--engine transnetv2]`** — shot-boundary detection (PySceneDetect by default, no model download; `transnetv2` opt-in via `uv sync --extra scenes-neural` for harder cuts/flashes). Feeds `reframe.py`'s per-scene camera analysis; also useful standalone to sanity-check "how many real cuts does this source have" before deciding on a multi-take strategy.
- **`reframe.py <video> --edit-dir <edit> [--aspect-ratio 9:16]`** — automatic 9:16 reframe with face/speaker tracking (MediaPipe), for turning a 16:9/4K source into a vertical cut that follows the subject instead of a fixed center crop. Needs `uv sync --extra reframe`. Use this BEFORE Phase 1 cutting when the source is landscape and the target is vertical — it produces the vertical source `transcribe.py`/`render.py` then work from, same as any other ingest step.
- **`clip_finder.py <video> --edit-dir <edit> [--min-seconds 20] [--max-seconds 45]`** — decupagem: turns one long transcribed source into a shortlist of candidate clip windows (duration-bounded, snapped to real word boundaries, no LLM/API required). Run it after `transcribe.py` on a long source when the ask is "find me N Reels in this recording" rather than a single edit — each candidate becomes its own `edl.json`/Phase-1 pass.
- **`transcribe_batch.py <videos_dir>`** — every source in a directory, one at a time (local inference already uses every core). Per-file cached, and a failure on one source doesn't lose the ones already done.
- **`pack_transcripts.py --edit-dir <dir>`** — transcripts → `takes_packed.md` (phrase-level, breaks on ≥0.5s silence). **The** reading view: 1/10 the tokens of raw JSON.
- **`speech_regions.py <video>`** — acoustic speech intervals via silencedetect. The source of truth for cut EDGES (Whisper times drift/stretch). Answers *where* speech is — never *how loud* it is.
- **`voice_levels.py <video> [--edit-dir <dir>] [--edl edl.json] [--drop-db 5]`** — the source of truth for speech LEVEL. Flags every phrase, run and EDL range ≥5 dB under the speaker's own median and sizes a `gain_db`. It catches what nothing else does: a whispered aside where the transcript is perfect, `speech_regions` says "speech" and `verify_cut` finds no fault — and the viewer still cannot hear it. **Run it before writing the EDL.**
- **`detect_color.py <video> [--json]`** — resolves NORMAL vs LOG from the file instead of asking — metadata first, image statistics when the metadata is silent (common: a transcode drops the tags). Returns profile, **confidence**, evidence and the `grade` to apply. Only `confidence: low` should send you back to the user; the identification detail is in `references/log-grade.md`.
- **`render.py <edl.json> -o cut.mp4 --no-subtitles [--voice-master] [--keep-resolution] [--jobs N] [--no-jcut] [--jcut-lead N] [--jcut-tail-trim N]`** — per-segment extract (grade + fades, **parallel**) → **J-cut overlap assembly (default)** or lossless concat → optional voice master → loudnorm. Writes `jcut_timeline` into the EDL: the real output positions, which is what everything downstream must index off. Short-form fps is automatic: **30fps for 30fps+ sources, else 24** (longform keeps source fps via `--keep-resolution`). Set `edit-data.json` `fps` to match the resulting `cut.mp4`.
- **`verify_cut.py <edl.json> <cut.mp4> [--min-silence 1.2]`** — numeric self-eval: duration, per-junction pop/clipped-word probes, dead air, black frames, clipping, **and range level balance** (each range's RMS vs the median range; `LOW-LEVEL` under −4 dB). ~350 tokens of text instead of N images. The range-balance line is the convergence test for a `gain_db` fix.
- **`grade.py <in> -o <out>`** — grade presets/raw filters. **`--candidates "a=<filter>;b=<preset>;original=" --frame <t> -o cmp.png`** renders N looks on the SAME frame into one labeled montage.
- **`timeline_view.py <video> <start> <end>`** — filmstrip+waveform PNG for ONE flagged spot, not a scan tool.
- **`contact_sheet.py <video> --times t1 t2 … -o sheet.png`** — N frames in one labeled grid; the way to eyeball several moments **you already know**.
- **`watch_video.py <video> [--mode scene|keyframe|uniform] [--times t1 t2 …] [--start/--end] [--max-frames 24]`** — "what is IN this footage?" when you *don't* know where to look: scene detection + perceptual dedup → labeled contact sheets in `edit/verify/watch_<stem>/`, one Read per sheet. For visual inventory of unknown material, and for surveying `cut.mp4` beyond verify_cut's numbers. `--times` pins transcript-cue frames: deictic moments from `takes_packed.md` ("olha isso", "como você pode ver") are LOW visual change and invisible to scene detection — pin them to decide B-roll/callout/zoom placement in Phase 2.

Phase 2/3 helpers (captions, face tracking, image search, music) are listed in
the track reference you load after the gate.

Compositing & beat-synced montage (details in the two references below):
- **`chroma_key.py <gs.mp4> -o subject.webm [--garbage person] [--qc t…]`** — colour-difference keyer for green/blue screen: matte levels, core fill (glasses glare), choke/feather, despill. `--selftest <alpha.webm>` measures it on a synthetic screen.
- **`matte_refine.py --fg fg.webm --src src.mp4 -o clean.webm`** — no screen: cleans an RVM matte (`person_matte.py`) with a MediaPipe person gate + an edge-band texture rule (chairs, headrests).
- **`composite.py --fg subject.webm --bg plate.jpg -o comp.mp4`** — makes the subject belong: colour/light match, light wrap, edge, grain, shadow, plate depth, handheld shake. `--qc` = plain paste vs comp.
- **`beat_map.py track.mp3 -o beats.json`** — tempo, beats (steady grid fitted over intros), downbeats, hits, drops, ranked cut points + PNG.
- **`speed_ramp.py take.mp4 --in A --out B --beats beats.json --from-beat N --n-beats K -o r.mp4`** — eased speed curve fitted to exact beats, motion-compensated slow-mo, real shutter motion blur.
- **`beat_edit.py plan.json -o edit/hyperframes_beat`** — takes + music → HyperFrames project (one sub-composition per shot) with cuts and transitions (flash, whip, zoom, rgb-split, shake, speed) on beat frames, per-take slow-down and stabilisation; opens in the EDITOR tab.
- **`take_analyzer.py takes/*.mp4 -o takes_analysis.json`** — camera shake (velocity jitter, whips excluded) and intended move per take → stabilise none/light/strong + recommended speed.
- **`stabilize.py take.mp4 -o stab.mp4 --smoothing 12 --keep-if-better`** — RANSAC global-motion stabiliser (robust to reflections on glossy cars), one fixed zoom; vid.stab optional.
- **`film_look.py shot.mp4 -o plate.mp4 --params '{…}'`** — film emulation + light VFX per shot: halation, bloom, anamorphic streaks, light sweep on paint, light-hit pulse, print curve, hue fixes.
- **`sfx_synth.py -o sfx_cinema [--room-tone takes…]`** — synthesised cinematic SFX kit (sub swell/drop, risers, whooshes, ticks, door "TUM", leather) + diegetic room/cabin tone. Phone-audible set (2026-10-30): `impact`, `glass_ping`, `whoosh_air`, `whip_hit`, `riser_tonal` — energy in 150 Hz–8 kHz, where a phone speaker plays; `sub_drop`/`ui_tick` alone vanish there.
- **`hf_motion_scenes.py`** (library) — motion-HTML scenes for the HyperFrames finishing pass, in the same glass-prism look as the GlassCard `prism`: `count`, `rank`, `compare`, `awd`, `lane`, `shield`, `brand`, `chips` + `index_html()` (Remotion render as base + scenes on top). Workflow and the two measured colour traps in `references/shortform.md` "Acabamento".
- **`deliver_mix.py <edit> [--voice-chain noisy|clean] [--stems]`** — the Phase-2 delivery WITH a mix: treated voice (latency-compensated), soundtrack ducked under the voice and level-calibrated from measurement, `sfxCues` + transition SFX, two-pass loudnorm. Run after `render_phase2.py`; details in `references/shortform.md` Phase 3.
- **`cinema_edit.py plan.json -o edit/hyperframes_cinema`** — cinema-motion assembly: bar-cut music segments, 24p/180° plates, film look, match cuts by light line, grain/veil layers, brand typography + drawn HUD, narrative mix (LPF/silence/cues/beds). See `references/cinema-motion.md`.
- **`color_pipeline.py takes/*.mp4 --out graded/ --ref hero.mp4 --look "…"`** — multi-take / low-light colour: denoise → neutral white balance → protected-shadow exposure curve (asymmetric match) → shared look → clarity; report + before/after sheet. See `references/color-multitake.md`.

Interface:
- **`preview_server.py --root <edit> [--port 4820]`** — serves the standard preview interface (see the Preview interface section). App code lives at `assets/preview/` and is IMMUTABLE.

## Preview interface (standard — launch it at the start of every edit)

Every edit session gets the same interactive interface in the user's preview panel: a video-editor timeline (video track with filmstrip + audio track with waveform), a live playhead that scrubs the render in real time, per-take trim handles and take removal, and — from Phase 2 — caption and insert tracks. The layout follows the source aspect on its own: **vertical** sources put a tall player on the right with the transport + timeline on the left; **horizontal** sources keep the player stacked above the timeline. Dark glass, Prisma brand. **Never build a UI per session** — feed the standard interface with `state.json`. Editing `assets/preview/` is allowed only when the user asks for a UI change; it is shared, so the improvement lands for every project.

**Launch (do this when a session starts, even before the first render — the UI shows a waiting state):**
1. Write `<edit>/state.json`:
   ```json
   {"project": "Nome — C0000", "phase": 1, "video": "cut.mp4", "edl": "edl.json",
    "captions": "remotion/public/captions.json", "editData": "remotion/public/edit-data.json",
    "finalVideo": "final.mp4", "fps": 24, "message": "Fase 1 — cortando",
    "sourceDurations": {"C0000": 1038.5},
    "awaitingStyle": false,
    "style": {"edit": "split", "captions": "karaoke",
              "elements": {"tracking": false, "zoomAuto": true, "zoomCuts": true, "musicAI": false}}}
   ```
   (`captions`/`editData`/`finalVideo` only when they exist; the Fase-2 tab plays `finalVideo` — the render WITH captions/inserts — while Fase 1 plays the clean cut; `sourceDurations` lets the UI clamp take extensions; `awaitingStyle`/`style` drive the Estilo tab below.)
2. Select the runtime adapter; never invoke another host's tools.

   - **Claude Code:** ensure `.claude/launch.json` has the config (adjust `--root` per session). The server takes the port by flag only, so pass the harness-assigned `$PORT` and set `autoPort`: `{"name": "prisma-preview", "runtimeExecutable": "sh", "runtimeArgs": ["-c", "exec python3 <skill>/helpers/preview_server.py --root '<edit>' --port \"$PORT\""], "autoPort": true, "port": 4820}`. Run `preview_start` with name `prisma-preview`, then arm `Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'", description="escolhas e marcações salvas no preview", persistent=true)` **in the same turn**.
   - **Codex desktop / CLI:** start `uv run python helpers/preview_server.py --root '<edit>' --port 4820` as a background local process when the environment can keep it alive. Once it responds, use the `control-in-app-browser` skill to open `http://127.0.0.1:4820` in the in-app Browser automatically and leave that tab on the preview. Do not assume `preview_start`, `Monitor`, or `.claude/launch.json` exists. If the Browser capability or a persistent local process is unavailable, give the user the command and local URL instead. After showing the preview, tell the user to save and reply in this task. On every subsequent user message, before any other work, check for `preview_edits.json` and `preview_style.json`; read, validate, apply, then remove only `preview_edits.json`.

   A preview save must always lead to an agent-visible action: Claude Code uses the persistent watcher; Codex uses the user's next task message as the notification boundary.

**Preview aberto e vazio para sempre = permissão, não render.** On macOS the
privacy layer guards `~/Documents`, `~/Desktop`, `~/Downloads` and iCloud Drive:
an app that was never granted Files-and-Folders access gets `PermissionError
[Errno 1] Operation not permitted` writing `state.json`, and the UI then waits
on a file that will never appear. `preview_server.py` refuses to start on an
unwritable root and prints the fix — read that output instead of re-rendering.
**If the user says the permissions are already enabled, the answer is to restart
the Mac**: the permission cache goes stale and shows the toggle on while still
denying. Confirmed in production; nothing in Settings fixed it.

**Keep state.json fresh** — bump `phase` and `message` at each milestone (cut rendered, cut approved, Phase 2 rendered…). The UI polls and hot-reloads by itself; waveform + filmstrip regenerate automatically when cut.mp4 changes.

The timeline shows one track per KIND: markers, captions, video, audio (the mix),
**A1 / A2** (the J-cut takes), **text** overlays (hook), **images** (inserts + any
data-driven CustomGraphics windows), soundtrack. Anything you leave in code instead
of data simply will not appear.

**A1 / A2** are the J-cut takes, folded inside the audio track behind a caret that
only appears when the EDL carries a `jcut_timeline`. The hatched orange head on a
block is the lead — how much voice arrives before that take's picture.

**What the user can do in the UI:** scrub, trim take edges, delete takes, drag
insert/hook chips — and **mark correction ranges**: park the needle, press `M`
(or the IN button), move to the end of the problem, press `M` again — the note box
opens centred over the timeline — then type what should change. Many ranges per pass. Zoom: the slider is anchored on the needle, trackpad pinch
on the pointer. Shortcuts live behind the **?** button at the bottom right.

### The EDITOR tab — HyperFrames Studio inside Prisma (hand editing)

Prisma decides the edit; the **EDITOR** tab is where the person edits it by hand,
live, with the full HyperFrames Studio embedded (Apache-2.0): every take, caption
line, keyword card, split image, flash, the soundtrack and the fade are separate
clips — trim, extend (takes point into the FULL source), split, move, delete,
volume, fades, carve. No agent round-trip, no render until **Export**.

- **ONE editor.** The EDITOR tab is the only timeline the person sees (the legacy
  Fase 1 / Fase 2 review tabs are hidden). Build it as soon as `cut.mp4` passes
  `verify_cut.py` — a Phase-1 export holds just the takes — and point the person
  at it for the cut review. Run the export AGAIN after Fase 2 data exists: it
  reads the takes back from the editor (hand cuts survive) and lays captions,
  cards, split images and music onto them by SOURCE time, dropping whatever falls
  in a stretch that was cut by hand.
  `uv run python helpers/export_hyperframes.py <edit>` → `<edit>/hyperframes/`,
  writes `state.json.hyperframes`; the tab picks it up. The tab's own
  "Criar editor desta edição" button runs the same export through the server.
- **Picture and sound are a pair per take**: a muted `<video>` plus an `<audio>`
  with the same src/start/media-start/duration in group `voz`. An unmuted
  `<video data-has-audio>` renders with sound but the Studio player never plays
  it — the first version of the editor was silent for exactly this reason.
  Needs the HyperFrames CLI (`npm i -g hyperframes@latest`) and keeps the bed
  UN-carved in `edit-data.json` `soundtrack.raw` — HyperFrames carves it live
  against the `voz` group (a pre-carved file would be carved twice).
- **Never re-export over Studio work.** The export fingerprints the project
  (index + compositions, ignoring the `data-hf-id` Studio stamps on open); once
  captions/cards exist and anything changed since, it refuses unless `--force`
  ("Recriar do Prisma" asks first). To fix something structural in an edited
  project, patch `index.html` in place instead (keep the person's attributes,
  e.g. a `data-fade-out` they dragged) and re-run `hyperframes check`. Edits made in the Editor live in `<edit>/hyperframes/`, not in the
  Prisma EDL — to change them, edit there, not `edl.json`.
- **The final video from this path is the Editor's Export** (HyperFrames render),
  not `render_phase2.py`. Say which one was delivered.
- Structure notes: one caption LINE per clip on the captions track is on
  purpose — Studio 0.8.x's native caption track does not persist timing edits.
  Takes are butt cuts (no J-cut overlap); the in-take push-in is not ported.
- `preview_server.py` owns the Studio process (`--studio-port`, default
  `--port + 10`) and stops it on exit.

### The Estilo tab (between Fase 1 and Fase 2)

The cut is approved and nothing about the LOOK of Fase 2 is decided. **Do not ask
the style questions in chat** — the gate screen exists so the user SEES what each
style does, and a chat list of names asks them to choose blind. Set
`"awaitingStyle": true` in `state.json`; the UI opens its own tab and
`watch_edits.py` notifies you when they save `<edit>/preview_style.json`.

**READ the picks — never state them from memory.** Run
`watch_edits.py <edit>` (or read `preview_style.json`) and quote what it
returns. What you clicked while demonstrating the UI, what you proposed
earlier, or what you assume is a sensible default are all different from what
the user actually chose. This has already gone wrong once: four elements were
reported when eight were ticked, because the interface was read from an earlier
screenshot instead of from the file. The file is the only source of truth, and
it costs one command.

The catalog of options and what each pick means is in the track reference, which
you read next anyway — **`references/shortform.md`** or **`references/longform.md`**.

**The gate works in BOTH aspects.** It reads the decoded frame (the same
`portrait` body class the player layout uses) and draws each edit-style mockup
for the real aspect, so a 16:9 job is offered 16:9 layouts. Set `awaitingStyle`
on longform jobs too; do not fall back to asking the layer questions in chat.

**The landscape layouts are NOT the portrait ones rotated.** 9:16 splits the
frame because it is tall; 16:9 uses a **full-frame cutaway** — the B-roll covers
the picture while narration continues, which is both the editorial norm and what
`assets/longform` actually renders (`broll[]` is "full-frame image (Ken-Burns) or
muted video cutaways"). Splitting a widescreen frame down the middle would
squeeze the presenter into a portrait sliver and describe a render the template
never builds. Hence the names differ per aspect:

| id | 9:16 | 16:9 |
|---|---|---|
| `limpa` | Limpa | Limpa |
| `split` | Tela dividida (arte em cima) | B-roll em tela cheia |
| `split2` | Tela dividida 2 (arte embaixo) | B-roll com apresentador (PiP) |

**Caption styles are short-form only.** `assets/longform` ships none of them on
purpose — a 16:9 upload gets a real `.srt` the viewer can toggle, and burning
type in fights YouTube's own CC layer. The gate therefore offers the six burned
styles in portrait and only `srt` + `Nenhum` in landscape; `captions: "srt"`
means run `captions_srt.py` and deliver the sidecar, not render text into the
picture. Options carry `portraitOnly` / `landscapeOnly` and are HIDDEN, not
disabled, in the aspect that cannot build them — and a pick that dies when the
aspect changes is snapped to a valid one before the cards are drawn
(`reconcileStyleWithAspect`).

**When the user saves timeline edits**, the UI writes `<edit>/preview_edits.json`
(never touches edl.json) and `watch_edits.py` notifies you automatically. To apply:
- `notes[]` — free-text correction requests, each with `start`/`end` on the draft
  timeline plus `renderedStart`/`renderedEnd` on the current `cut.mp4`, and the
  `phase` tab the user was on. Use the RENDERED pair to find the moment in the
  existing render. These are instructions in the user's words — read them, then do
  the edit they describe (re-cut, re-grade, swap an insert, fix a caption…).
- `edl.changes` / `edl.removed` — validate each new edge against
  `speech_regions.py` (warn if an edge clips a word — the user's intent wins, but
  say so), update `edl.json`, re-render, `verify_cut.py`.
- `editData` — insert/hook/behind timings → edit-data.json → re-render Phase 2.
- `editData.levels` — `{voice, music, sfx}`, each `{value, was}`, from the faders
  on the audio tracks. **Every audio track has one, and the saved number is
  EXACTLY what the user set** — no rounding to a nicer value. Apply all three in
  the delivery mix: `voice` on cut.mp4's stream, `music` on the soundtrack input,
  `sfx` requires a Remotion re-render (it is baked into the caption layer).
  Voice and music are audible in the preview immediately; sfx is declared only,
  and the chip says which mode it is in.
- `editData.soundtrack` — `{volume, was}` from the slider on the music track.
  Apply it by re-running the delivery ffmpeg with the new `volume=` — **never
  re-render Remotion for this**, the soundtrack is mixed in the final ffmpeg
  pass. Write the value into `edit-data.json` `soundtrack.volume` too, or the
  chip stays dirty forever.

**After applying a style pick, WRITE IT BACK to `state.json` as `style` — this
is not bookkeeping.** The Estilo tab rebuilds itself from `state.style`; without
it the tab reopens on the defaults and the user sees their picks gone, which
reads as "saving does nothing". Measured in production: the file on disk said
`split` + tracking + flash while the tab showed `limpa` with both off, because
the write-back was skipped. Delete `preview_style.json` in the same step.

**Carve the music instead of burying it** (`music_carve.py`, full rationale in
`references/toolbox.md`). Splitting the track and side-chaining only the band the
voice occupies lets the soundtrack sit at ~0.22 instead of ~0.10 — measured
−8.7 dB under speech in 250–2200 Hz, with bass and air untouched. Run it BEFORE
the delivery mix and feed the carved file in place of `trilha.mp3`. Two traps,
both measured: `amix` divides by input count (sum the bands, set the volume
after), and comparing full mixes shows nothing because the voice masks the music
— render the music path alone to verify.

**The slider's value IS the decision — never ask the user to confirm a number
they already set.** Before any re-render that touches audio, read
`edit-data.json` `soundtrack.volume` (kept current by every preview save) and
use it. Asking "qual volume?" after they dragged the slider makes the control
decorative.

**Make the soundtrack slider a REAL control** — write a music-free render next
to the delivery and point `state.json` `videoNoMusic` at it. The preview then
plays that picture with the soundtrack on its own `<audio>`, so dragging the
slider is audible immediately (measured drift: 7ms over 5s, video is the clock).
Without it the slider can only state a value for the next render, and a user who
drags it hears nothing change — which reads as broken, not as deferred. One
extra ffmpeg pass at the delivery step:
```bash
ffmpeg -y -i out/render.mp4 -filter_complex "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid];[0:a]loudnorm=I=-14:TP=-1:LRA=11[out]" \
  -map "[vid]" -map "[out]" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 192k -ar 48000 -t "$VD" -movflags +faststart ../preview_novoice.mp4
```
The chip says "ao vivo" when the pair exists and "próximo render:" when it does
not — never let it look the same in both states.

Then delete `preview_edits.json` and update `state.json`.

---

# PHASE 1 — Clean cut + color grade

Goal: best take of every beat, cut on silence, graded image, clean `cut.mp4` for approval. No text, no graphics.

1. **Inventory.** URL source? `ingest_url.py` first (`--section` when only a range of a longform video matters). `ffprobe` every source. `transcribe_batch.py` (or `transcribe.py`) → `pack_transcripts.py` → read `takes_packed.md`. Note dimensions/orientation and whether it looks flat/LOG. Material you can't picture from the transcript → `watch_video.py` for a one-Read visual survey.
2. **Pre-scan** `takes_packed.md` for verbal slips, mis-speaks, and dead-air-stretched words (Whisper stretches a word's end across silence — verify long "phrases" against `speech_regions.py`/waveform before trusting them). **Then run `voice_levels.py` on every source** — the transcript is level-blind, so an inaudible passage reads exactly like a normal one. Anything it flags is a decision to make BEFORE the EDL: boost it with `gain_db`, or cut the take entirely.
3. **Converse.** Describe what you see; ask questions shaped by the material (content type, target length/aspect, pacing, must-keep/must-cut). No fixed checklist.
4. **Detect the colour profile — do NOT ask.** Run `detect_color.py <source>`.
   The answer is in the file; asking put a measurable question on the user.
   - **`rec709` (normal)** → no grade. `"grade": ""`. A standard profile already
     carries its look; "improving" it loses the match with the user's other material.
   - **LOG / HLG / PQ** → apply the helper's `grade` field and say so in one line.
     Apple Log uses its approved preset; any other LOG gets an expansion **measured
     from that footage**, not a guessed vendor curve.
   - **`confidence: low`** → the ONLY case that still asks. It means the statistics
     are ambiguous — a bright, shadowless scene has the same lifted black floor as
     a LOG curve. Show what was measured, then ask.
   Still show the `--candidates` montage before committing a LOG grade: detection
   picks the curve, the user picks the look.
5. **Propose the cut strategy** (4–8 sentences: shape, takes, cut direction, grade direction, length estimate). **Wait for confirmation.**
6. **Execute.** Produce `edl.json` (schema below; editor sub-agent brief for multi-take). Set cut edges from `speech_regions.py`, not raw Whisper times. Render: `render.py edl.json -o cut.mp4 --no-subtitles` (+`--voice-master` if wanted; longform: `--keep-resolution`). **The J-cut runs by default** — see below; you do not ask for it and you do not configure it per project.
7. **Self-eval (numeric first).** `verify_cut.py edl.json cut.mp4` (longform: `--min-silence 1.2`). Clean → done. Flags → `timeline_view` ONLY the flagged junctions, fix, re-render. Cap 3 loops, then surface remaining flags to the user.
8. **Show `cut.mp4` and wait for approval.** The phase gate.
9. **Open the Estilo tab** — `"awaitingStyle": true` in `state.json`, and let the
   user pick the editing style, the caption style and the edit elements in the UI
   (see "The Estilo tab"). Do NOT ask this in chat. Only then read the track
   reference: **`references/shortform.md`** or **`references/longform.md`**.

## J-cut — the default Phase-1 cleanup

Takes are OVERLAPPED, not butted. The outgoing take's audio runs to its natural
end; the incoming take's audio starts `lead` frames earlier **on its own track**
and the two are summed; the incoming PICTURE starts where the outgoing audio ends,
skipping `lead` frames of its own head. The voice arrives before the face.

Why it is the default: a straight concat leaves a beat of silence at every
junction — the outgoing take keeps its trailing pad and the incoming one starts
with its own. Measured on a real 3-take edit: **130ms and 140ms**. Small on paper,
a clear pause in the room. The J-cut removes it and the takes interlock.

Defaults, in `render.py`: **lead up to 5 frames**, **tail trim up to 2 frames**.
Override per project with `"jcut": {"lead_frames": N, "tail_trim_frames": N}`;
turn it off with `"jcut": false` or `--no-jcut` (single-range EDLs skip it anyway).

Four things that are not obvious:

- **The lead is capped per seam by the silence actually there.** The overlap only
  sums room tone while `lead ≤ outgoing tail silence (after the trim) + incoming
  head silence`; past that the incoming voice is laid over the outgoing one.
  `render.py` measures both sides the way `refine_edges.py` places edges (voice
  band 250–3500 Hz, quiet = below local floor + 6 dB; a fixed −35 dB read no
  silence at all under road noise) and lowers that seam's lead (log: `lead Nf
  (limitado …)`), down to 0 = butt join on a seam with no room. Why 5 and not
  16: 16f (533ms) was the default for a while. On PPF X6 (2026-11-03, tight
  edges from `refine_edges.py`) it erased "ou qualquer parte" and garbled "700
  mil" in the transcript of the cut; 5f was clean. Even `build_edl.py`'s 0.18s
  pads give only 360ms of silence per seam. The real lead of each take is in
  `jcut_timeline[].lead_frames`, so read it there, not from the EDL's `jcut` block.
- **Tighten with the TAIL, not the lead.** A bigger lead also pushes the picture
  deeper into the incoming take's speech, which reads as entering mid-word. The
  tail trim tightens the seam and leaves the picture entry alone. Measured: 5f
  lead alone gave 62/46ms of interlock; adding a 2f tail trim doubled it to
  129/112ms with the picture still entering 140ms into the speech.
- **The tail trim is measured, never blind.** `render.py` reads the silence
  actually present at the end of each range and trims at most that (keeping 10ms).
  A fixed 2 frames would eventually decapitate a word on a take that ends tight.
- **Sync is by construction:** `video_in = audio_in + lead` and
  `video_offset = audio_offset + lead`. Break that pairing and the take drifts.

`render.py` writes a `jcut_timeline` block into the EDL — the real output
positions. Everything downstream (preview timeline, `segments.json`, Phase-2
overlays) must index off THAT, not off the sum of the ranges: the J-cut output is
shorter than `Σ(end−start)`, so summing places every take after the first too late.

## Color grade

Reason about the image, don't preset-blind. Mental model ASC CDL: per channel `out = (in*slope + offset)**power`, then saturation. Applied per-segment at extraction (Hard Rule 7).

- **Iterate on ONE frame via a candidates montage, and let the user choose:**
  `grade.py <src> --candidates "punch=eq=contrast=1.15:saturation=1.25;suave=…;original=" --frame <t> -o edit/verify/grades.png` — one image, all looks labeled, side by side. Only render the full cut once the grade is locked.
- **Build from spaceless filters** so the string survives the EDL: `eq=…`, `colorbalance=…`, `colorlevels=…`. No `curves` with spaces (breaks filtergraph parsing).
- **The grade always runs at 8-bit.** `render.py` prepends `format=yuv420p` to the
  grade segment of the vf chain, because ffmpeg's `colorlevels` is broken on 9–14
  bit RGB — on a 10-bit source it collapses the frame to a constant TV black
  (measured `YAVG=64/1023`, `YBITDEPTH=1` on an iPhone Apple Log ProRes) while
  behaving correctly at 8- and 16-bit. `curves`, `colorbalance`, `hue` and `eq` are
  bit-depth-safe. Keep that guard in front of any new grade caller.
- **Standard/Rec.709** → light corrective or none. A user `.cube` goes first as `lut3d=`.
- **Many takes and/or low light** (montage, showroom, interior, night) → don't put one look on unmatched takes: run `color_pipeline.py` (denoise → balance → protected-shadow exposure → look → clarity) and read `references/color-multitake.md`. Keep contrast out of the look; check the report's shadow p20 never falls.

### LOG / HDR sources

`detect_color.py` resolves the profile and returns the `grade` to apply, so the
normal path needs nothing here. When it returns LOG/HLG/PQ, reports
`confidence: low`, or you are adding a vendor preset, **read
`references/log-grade.md`** — it carries the identification table (Apple Log has
no tag that names it), the Apple Log preset's two load-bearing details, and why
the grade must run at 8-bit.

Still show the candidates montage and get a pick — a preset is a starting point,
not permission to skip the approval.
- **Skin is the guardrail.** The moment skin goes orange/magenta/clipped, back off. Check a mid-shot face at each step.
- **Relative tweaks** ("+1 exposure", "mais saturação") → nudge that one term, re-montage the same frame, show again.
- **Rec.709 is the only color space allowed to leave Phase 1.** `render.py` handles
  this (tonemaps HDR, converts wide-gamut SDR, tags every output bt709/tv) — but
  VERIFY on the rendered cut: `ffprobe -v error -select_streams v:0
  -show_entries stream=color_space,color_primaries,color_range cut.mp4` must read
  bt709 / bt709 / tv. Anything else means a second interpretation is still alive
  downstream: Chrome (Remotion's decoder in Phase 2) re-reads those tags and
  silently re-grades the image — typically ~1.2 gamma darker with a hue shift — so
  the Phase-2 render stops matching the cut the user approved. Phone/mirrorless
  sources routinely write bt2020 primaries with `color_transfer=unknown`; that is
  wide-gamut SDR, **not** HDR, and an HDR-only check will miss it.

## Voice EQ + mastering (optional Phase-1 audio polish)

Opt-in: `render.py … --voice-master` or `"voice_master": true` in the EDL. Runs after compositing, before loudnorm. Chain (`VOICE_MASTER_CHAIN` in render.py): highpass 80 → mud cut −2.5dB@200 → compressor (3:1, −20dB, makeup 3) → presence +2.5dB@3.2k → air +3dB@9k shelf → deesser → limiter 0.95.

Tune per voice: brighter → raise treble/3.2k; warmer → back those off, lift ~200Hz; more "radio" → lower threshold / raise ratio; more natural → ratio 2, threshold −24dB. **Verify:** `ffmpeg -i cut.mp4 -af astats -vn -f null -` → Flat factor 0, peak < 0dB; loudnorm summary ≈ −14 LUFS / TP ≤ −1. Then let the user hear it.

## Cut craft

- Silences ≥ 400ms are the cleanest cuts; 150–400ms usable with a check; < 150ms unsafe.
- Preserve peaks (laughs, punchlines, emphasis) — extend past a punchline to include the reaction.
- Every cut must work on audio AND video.

**Check the TAIL of every cut for EXTRA words, not only missing ones.** A speaker who drags the last word ("bacanaaa", "vaaai") stretches it in the transcript; the end edge then lands after the NEXT speaker's first words (measured: XC60 r03 ended "bem bacana. É, Fabrício. E eu acho…", r07 "…a gente vai. E…"). A word-diff against the quote misses it — the expected words are all there. Read the last 8 words of the re-transcribed cut.

**Never split a phrase on transcript gaps alone.** A "pause" is real only when the AUDIO is quiet there. Splitting continuous speech at a stretched/misplaced word removes words the transcript did not show (measured: Volvo XC60 r01 lost a whole clause this way). Cut only where `refine_edges.py`/`speech_regions.py` measure silence, and prefer whole phrases over trimmed fragments.

**Fine-comb the silences — Whisper times are NOT cut edges:**
- Onsets drift early (bakes dead air at a segment head); ends stretch across silence (a 4s "phrase" may be 1s of talk); restarts get collapsed into one stretched word (the doubled take is invisible in text but audible).
- Fix: edges from `speech_regions.py` — start → region onset −30ms, end → offset +50–80ms (the trail keeps the word's decay; cutting at the offset clips the last sibilant). Inside merged speech blocks, place the edge by eye on a fine `timeline_view`.
- If the user flags a gap/clip after render, re-run `speech_regions.py` around that timestamp — don't nudge blindly.
- **A stretched word can hide a false start, and the stretch also mis-attributes every word around it.** When "de" spans 6.16→8.64, the words the source transcript places on either side may belong to *different takes* — the speaker trailed off, paused, and restarted the whole sentence. The text shows one clean sentence; the audio holds two attempts.
- **Never conclude a range is missing content from the SOURCE transcript's word times.** Extract the exact range and transcribe it in isolation — no surrounding context for the LM to complete from. A model reading the full file completes from context; the same model on a 3-second extract cannot. If the answer changes a deliverable (a caption rewrite, dropping a take), also check the range against `speech_regions.py` and the waveform — agreement between the isolated transcript and the acoustics is what makes it trustworthy.
- **Rotation:** phone clips are often stored landscape with a ±90° display-matrix; render.py handles it — don't force dimensions.

**Level the takes — presence is not audibility:**
- People drop their voice on asides, parentheticals and sentence tails ("além de, *claro*, …"). It sounds natural in the room and disappears on a phone speaker. The transcript is perfect, so nothing in the text pipeline flags it.
- Find it with `voice_levels.py --edl edl.json`: it reports each range's average AND the worst low run inside it, and suggests a `gain_db`. Size the gain off the **worst run**.
- Fix it per-range with `gain_db`, never with a global compressor.
- Confirm with `verify_cut.py`'s range-balance line. Target a ~2 dB spread between ranges — that is levelled. Driving it to 0 dB flattens the delivery and lifts room tone for nothing.
- Room tone is the real ceiling on a boost, not clipping. Before committing a large gain, compare the boosted take's internal pause against a pause elsewhere in the cut; if the boosted one is now the louder pause, back off.

## Editor sub-agent brief (multi-take selection)

```
You are editing a <type> video. Pick the best take of each beat and assemble
chronologically by beat, not clip order.
INPUTS: takes_packed.md; narrative context (2 sentences); speaker note;
expected structure (archetype or invent); verbal slips to avoid; target runtime.
Archetypes: launch (HOOK→PROBLEM→SOLUTION→BENEFIT→EXAMPLE→CTA); tutorial
(INTRO→SETUP→STEPS→GOTCHAS→RECAP); interview (Q→A→FOLLOWUP…); essay
(COLD-OPEN→THESIS→POINTS→COUNTER→CONCLUSION→CTA); vlog; or invent.
RULES: edges on word boundaries; pad 30–200ms; prefer ≥400ms silences; keep
unavoidable slips only if no better take (note in "reason"); if over budget,
drop a beat or trim tails and report.
OUTPUT (JSON array, no prose):
[{"source":"C0103","start":2.42,"end":6.85,"beat":"HOOK","quote":"…","reason":"…"}]
```

For a single long source (longform), the main context can pick cuts directly from `takes_packed.md`; for sources > ~30 min, delegate to the sub-agent so the full transcript never enters the main context.

## EDL format (Phase 1)

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4"},
  "grade": "eq=contrast=1.06:saturation=1.05",
  "voice_master": true,
  "jcut": {"lead_frames": 5, "tail_trim_frames": 2},
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK",
     "quote": "…", "reason": "…", "gain_db": 0,
     "chapter": "Only on longform section openers"}
  ],
  "total_duration_s": 87.4
}
```

`grade`: preset name, raw filter, or `"auto"` — normally whatever `detect_color.py`
returned. `chapter` fields feed `chapters.py` (longform).

`jcut`: optional. **Omit it and the J-cut runs with the defaults** (lead up to 5f,
capped per seam by measured silence; tail trim up to 2f); `false` butt-joins
instead. After a render, `render.py` adds a `jcut_timeline` array — the real
per-take video/audio offsets and the lead each take actually got. That
block, not `Σ(end−start)`, is the timeline Phase 2 and the preview must use.

`gain_db`: per-range level correction in dB, sized by `voice_levels.py`. Applied at
extraction, before the edge fades, with a limiter on any boost so a loud syllable
inside a quiet take cannot clip. This is the fix for an under-level take — not a
global compressor, which would pump the good takes to rescue the bad one.
Cap around +12 dB: past that the room tone rises with the voice and the take
starts sounding like a different microphone.

---

# PHASE 2 + 3 — read the track reference (after the gate)

**First, re-read `preview_style.json`** — the picks drive every decision below,
and building from memory means building the wrong video. Every element in the
`fora` list is an instruction too: it is what must stay OUT.

The cut is approved and the user picked the style in the UI (`preview_style.json`)
→ load **one** file and build exactly what was picked:

- **Vertical / Reels / TikTok / Shorts → read `references/shortform.md`.** Karaoke captions, static hook headline, dynamic camera, inserts, behind-the-subject, SFX, soundtrack.
- **Horizontal / YouTube / tutorial / vlog → read `references/longform.md`.** Retention cut is there too (read it BEFORE Phase 1 on longform jobs), B-roll, lower-thirds, chapter cards, callouts, .srt + chapters, soundtrack.

**Both tracks, before choosing any transition or animation → read `references/direction.md`.** The track reference tells you WHICH layers exist; `direction.md` tells you *when* to use a transition, *how long* it lasts and *with which curve* — energy/mood matrices, the six named presets with their GSAP→Remotion easing map, and the rule that governs the rest: one primary transition (60–70% of changes) plus one or two accents, never a different one per scene.

Both tracks: scaffold with one `cp -R` of the template, describe the video in `public/edit-data.json`, verify with montage stills, render, loudnorm, deliver `edit/final.mp4`. Load the `remotion-best-practices` skill when writing any Remotion code (CustomGraphics).

**3D / WebGL layers (glass panels, tracked inserts, displacement transitions).** The template ships `@remotion/three` + `three` + `@react-three/fiber`. `render_phase2.py` detects a 3D scene from `edit-data.json` and passes `--gl=angle` on its own — a 2D edit gets no flag and renders exactly as before. Never call `remotion render` by hand on a 3D composition without a `--gl` backend: headless Chromium may expose no WebGL and the canvas renders **black**, which looks like a broken shader and sends you debugging the wrong file. To check WebGL on a new machine, render the `GLProbe` composition: an orange cube in perspective on a dark-blue field means the pipeline is alive; a fully black frame means the backend is wrong.

## Compositing and music-driven montages (both phases)

- **A subject over a new background** (react overlay, presenter "at" an event,
  product on a new set) → **read `references/compositing.md`** first. Decide the
  path from how it was SHOT: green/blue screen → `chroma_key.py`; no screen →
  `person_matte.py` + `matte_refine.py`; then always `composite.py` so it
  belongs (light wrap, colour match, grain, camera). Say which path you are on —
  AI matting is not chroma key. Brief the user on the shooting checklist in that
  file before their next shoot; perspective and light direction are decided on
  set, not in post.
- **Takes + a track, cut to the music** (speed ramps, "transições no beat",
  car/product/travel montages) → **read `references/beat-sync.md`**. The music is
  the timeline: `beat_map.py` → plan on downbeats/drops → `beat_edit.py` (renders
  `speed_ramp.py` ramps itself). This replaces Phase 1's speech-led cut for that
  job; the phase gate becomes "approve the plan + a draft render". Ask the user
  for 60 fps (120 if possible) takes when slow-mo is wanted. Before planning, run
  `take_analyzer.py` and `color_pipeline.py`; nearly every take goes in slowed
  (`"default_speed": "auto"`), stabilised only where the analyser says so.

- **"Cara de cinema", cinematic-but-dynamic, VFX/motion** → **read `references/cinema-motion.md`** (restraint rule, counted accents, film look, narrative sound) and build with `cinema_edit.py`.

## Publishing (optional, after delivery)

- **`publish.py <final.mp4> --integration <channel> --caption "…" [--schedule <ISO8601> | --draft]`** — posts the delivered video to a connected social channel via the Postiz HTTP API (needs `POSTIZ_API_KEY`; `--list-integrations` to see connected channels). Only reach for this when the user actually asks to publish/schedule — it is a separate, explicit action from rendering `final.mp4`, never automatic.

## Asset provenance (optional, across projects)

- **`media_ledger.py record <file> --source <helper> --query "…" --license "…" --credit "…" --project <edit_dir>`** — after downloading a stock image/track (`pexels_search.py`, `wikimedia_images.py`, `treblo_music.py`, …), record it once. `find --query "…"` before a new search checks whether an earlier project already has a usable asset with the right license/credit, saving a repeat API call. Bookkeeping, not a blocking step — skip it for a one-off asset that will never be reused.

## Memory — `project.md`

Append one section per session at `<edit>/project.md`:

```markdown
## Session N — YYYY-MM-DD
**Phase reached:** …  **Strategy:** …
**Decisions:** takes, cuts, grade (LOG?), layer choices + why
**Outstanding:** deferred items
```

On startup, read it if it exists and summarize the last session in one sentence before asking whether to continue.

## Anti-patterns
- **Fixing in the video what the user asked to fix in Prisma.** When the user corrects a Prisma behaviour (a style element, a default, a cut rule), change the SKILL — template, reference, catalog, checks — and then the video. Patching only the project's edit-data makes the same correction come back next project; the user has had to repeat the glass-panel request several times for exactly this reason.
- Every mistake under **Cut craft** — Whisper times as edges, cutting at a word's
  offset, judging level by the transcript, sizing `gain_db` off a range average,
  chasing the low-run numbers to zero, fixing one quiet take with a global
  compressor. They are stated there as procedure; this is the reminder that they
  are also the way Phase 1 goes wrong.
- Committing a grade without the one-frame candidates montage + user pick.
- Shipping a `cut.mp4` that is not tagged bt709/tv — Phase 2 will re-interpret it and the approved grade drifts.
- Butt-joining the takes. The J-cut is the default; `--no-jcut` is a deliberate exception, not a shortcut.
- Tightening a J-cut seam by raising the lead. That buys tightness by shoving the picture deeper into the incoming take's speech. Trim the outgoing TAIL instead.
- A fixed tail trim. It must be bounded by the silence actually measured at that range's end, or it eventually cuts a word off.
- `adelay` in milliseconds when placing overlapped audio, or `-shortest` on the mux. `adelay`'s integer-ms rounding leaves the mix a fraction short of the video and `-shortest` then amputates whole FRAMES of picture — and whether it bites depends on which way the numbers round, so it passes by luck until it doesn't. Delay in samples (`=NS`), and pin the length with `-t`.
- Re-transcribing cached sources; re-rendering Phase 1 when only Phase 2 changed.
- Launching the preview without arming `watch_edits.py` in the same turn. This
  is the one failure mode where the user reasonably believes they handed you a
  decision and you never got it — the toast says saved, the file is written, and
  no one is reading it.
- Applying `preview_edits.json` blindly — validate new edges against `speech_regions.py` first (flag clipped words to the user).
- Asking "NORMAL ou LOG?", or assuming the profile without running `detect_color.py`. It reads the answer off the file; ask only on `confidence: low`.
