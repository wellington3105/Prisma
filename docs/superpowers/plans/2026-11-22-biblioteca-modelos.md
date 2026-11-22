# Biblioteca de modelos de edição: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a library of named editing types and styles that the Prisma applies with one command and shows as rendered demos in a gallery.

**Architecture:** recipes are JSON + a Markdown sheet under `modelos/`. Three flat helpers do the work: `modelos.py` (CLI: list/show/check/apply/demo/galeria), `modelos_receitas.py` (load, validate, apply per host) and `modelos_demo.py` (demo material, demo render, gallery). Recipes only write formats the current tools read: the `beat_edit` plan (host `montagem`), and `state.json.style` + `edit-data.json` (host `reel-fala`).

**Tech Stack:** Python 3.13 (Prisma `.venv`, `uv run --no-sync`), ffmpeg, HyperFrames 0.8.93 via `hfkit.project.hf_cli()`, Pexels and Epidemic APIs through the existing helpers.

**Spec:** `docs/superpowers/specs/2026-11-22-biblioteca-modelos-design.md`

## Global Constraints

- Repository is public: recipes and sheets go into git; demos, demo material and any path of the user's machine do not.
- Gallery root: `$PRISMA_MODELOS_GALERIA`, else `$OneDrive/Prisma/modelos-galeria/`; demo material in `<galeria>/_material/`.
- Demo material for montage demos: Pexels clips + one Epidemic track, each recorded with `media_ledger.py record` (license + credit). `modelos/_demo/demo.json` stores only Pexels/Epidemic IDs.
- Max 3 accent transitions per video; the primary transition of a style does not count.
- `apply` always writes a backup `<file>.antes-<slug>-<YYYYmmdd-HHMMSS><ext>`, prints a unified diff, appends `{slug, file, when}` to `state.json.modelos[]` when a `state.json` sits next to the target.
- `apply` on host `reel-fala` refuses unless `state.json.phase` ≥ 2.
- A demo enters the gallery only if `motion_gates.py render` passes G0 and G2.
- HyperFrames stays pinned (`hfkit/project.py` `HF_PIN = "0.8.93"`); render command: `hf_cli() + ["render", "--fps", "30", "--quality", "delivery", "-o", <out>]` with `cwd=<project>`.
- Every new helper goes into `references/tool-map.md` (row **Modelos de edição**); `tests/test_catalog.py` must stay green.
- UTF-8 stdout on every new helper (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`).

## Review Focus

- A recipe whose `transition`/`ramp`/`fx` value was renamed in `beat_edit.py`: `check` must fail, not the render (Task 1).
- `apply` run twice with the same tipo on the same shots: the second run must not duplicate fx entries nor count accents twice (Task 3).
- `flash-na-troca` on an edit whose `segments.json` is missing: refuse with a message naming the file, write nothing (Task 4).
- Applying an estilo over a plan that already has 3 accents set by hand: refuse and list the offending shots (Task 3).
- Gallery built while one demo is missing or failed its gates: the card shows "sem demo", the page still builds (Task 7).

---

### Task 1: Vocabulary as constants + recipe loader and `check`

**Files:**
- Modify: `helpers/beat_edit.py` (add constants near `T = 0.20`; validate plan values in the shot loop)
- Create: `helpers/modelos_receitas.py`
- Create: `helpers/modelos.py`
- Create: `modelos/README.md` (one paragraph: what tipo/estilo are, link to the spec)
- Test: `tests/test_modelos.py`

**Interfaces:**
- Produces in `beat_edit.py`: `TRANSITIONS: tuple[str, ...] = ("cut", "flash", "whip-left", "whip-right", "whip-up", "whip-down", "zoom", "rgb-split", "shake", "speed")`, `FX: tuple[str, ...] = ("pulse", "push", "shake")` (fx `shake@N` validates by prefix). Unknown values raise `SystemExit("beat_edit: unknown transition '<v>' in shot <i>")`.
- Produces in `modelos_receitas.py`:
  - `ROOT: Path` (= `<prisma>/modelos`)
  - `REEL_ELEMENTS: tuple[str, ...] = ("zoomAuto", "zoomCuts", "flashCut", "shaderCut", "tracking", "glassPanel", "springIn", "brollFull", "tracked3d", "musicAI")`
  - `@dataclass class Modelo: slug: str; nivel: str; familia: str; host: str; dados: dict; pasta: Path`
  - `load_all() -> dict[str, Modelo]`
  - `load(slug: str) -> Modelo` (SystemExit with the list of known slugs when missing)
  - `check() -> list[str]` (empty list = valid)
- Produces in `modelos.py`: CLI `list [--nivel] [--familia]`, `show <slug>`, `check` (exit 1 when `check()` returns problems).

- [ ] **Step 1: Write the failing tests** in `tests/test_modelos.py`:
  - `test_beat_edit_vocab()`: `beat_edit.TRANSITIONS` contains `"speed"` and `"whip-left"`; `"pulse" in beat_edit.FX`.
  - `test_beat_edit_rejects_unknown_transition(tmp)`: a minimal plan with `"transition": "wipe-diagonal"` makes `beat_edit.py plan.json -o out` exit non-zero with `"unknown transition"` in stderr, before any render.
  - `test_check_catches_bad_recipe(tmp)`: with `PRISMA_MODELOS=<tmp>`, a tipo whose `aplica.por_plano.transition` is `"whip-diagonal"` makes `check()` return one problem naming the slug and the value; a valid `whip-pan` recipe returns `[]`.
  - `test_check_requires_sheet_sections(tmp)`: a `MODELO.md` missing "Quando não usar" is reported.
  - `test_estilo_unknown_tipo(tmp)`: an estilo listing `"nao-existe"` is reported.
- [ ] **Step 2: Run** `uv run --no-sync python tests/test_modelos.py`. Expected: FAIL (`modelos_receitas` not found).
- [ ] **Step 3: Implement.** `ROOT` honours `PRISMA_MODELOS` (tests). `check()` validates: folder name == `slug`; `nivel` ∈ {tipo, estilo}; `host` ∈ {montagem, reel-fala}; `MODELO.md` has the headings `## O que é`, `## Quando usar`, `## Quando não usar`, `## Contenção`; for host `montagem`, every `transition` (after `{param}` substitution with each allowed value) ∈ `beat_edit.TRANSITIONS`, every `ramp` ∈ `speed_ramp.PRESETS`, every fx base ∈ `beat_edit.FX`; for host `reel-fala`, every `style.elements` key ∈ `REEL_ELEMENTS` and every `edit_data.transitions_em_cada_corte.type` ∈ {flash, whip-pan, glitch, displace, refract}; every tipo named by an estilo exists. Import `beat_edit`/`speed_ramp` constants without running their `main()`.
- [ ] **Step 4: Run** the tests again. Expected: PASS. Also `uv run --no-sync python helpers/lint_undefined.py` → `0 nome(s) indefinido(s)`.
- [ ] **Step 5: Commit** `feat(modelos): vocabulary constants, recipe loader and check`.

### Task 2: The v1 recipes and sheets

**Files:**
- Create: `modelos/tipos/{speed-ramp,transicao-velocidade,bullet-time,velocity-edit,whip-pan,flash,zoom-through,rgb-split,shake-impacto,zoom-punch}/{modelo.json,MODELO.md}` (host `montagem`)
- Create: `modelos/tipos/{zoom-nos-cortes,push-in,flash-na-troca,distorcao-na-troca}/{modelo.json,MODELO.md}` (host `reel-fala`)
- Create: `modelos/estilos/{montagem-na-batida,reel-fala-broll}/{modelo.json,MODELO.md}`
- Test: `tests/test_modelos.py` (add)

**Interfaces:**
- Consumes: `check()` from Task 1.
- Produces the recipe shapes Tasks 3–4 apply:
  - montagem tipo: `{"aplica": {"por_plano": {<campo>: <valor>}, "fx": [<fx>...], "ramp_saida": <preset>, "ramp_entrada": <preset>}, "parametros": {...}, "acento": bool}`. `transicao-velocidade` uses `ramp_saida: "speed-out"` on shot N−1 and `ramp_entrada: "speed-in"` + `transition: "speed"` on shot N. `velocity-edit` applies to a shot range: alternating `ramp` `"ramp-out"`/`"ramp-in"`, `fx: ["pulse"]` on every shot, `transition: "flash"` on the first, `fx` `"shake@0"` on the last.
  - reel-fala tipo: `{"style": {"elements": {<el>: true}}, "edit_data": {...}}`, where `edit_data` keys are one of `camera` (merge), `transitions_em_cada_corte` (`{"type": …, "preset"?: …}`).
  - estilo: `{"tipos": [...], "regras": {"primaria": <slug>, "max_acentos": 3}, "sinais": [...], "padroes": {...}}`; `reel-fala-broll.padroes.style` = `{"edit": "broll", "headline": "misto", "captions": "scatter", "elements": {"zoomCuts": true, "zoomAuto": true, "brollFull": true}}` (from `shortform.md` "B-roll em tela cheia").
- Values: `zoom-nos-cortes` → `camera.zooms` cycling `[1.06, 1.12, 1.04, 1.10]` (the approved GLE 53 values); `push-in` → `camera.pushIn = 0.04`; `flash-na-troca` → type `flash`; `distorcao-na-troca` → type `displace`, `style.elements.shaderCut = true`.
- Sheets cite their source (`beat-sync.md`, `shortform.md`, `cinema-motion.md`, `direction.md` mood table) and state contention in one line (e.g. whip pan: "1–2 por vídeo; os dois planos precisam de movimento na mesma direção").

- [ ] **Step 1: Write the failing test** `test_v1_set_is_complete_and_valid()`: `load_all()` has exactly the 14 tipos and 2 estilos above; `check() == []`; every estilo's `regras.max_acentos == 3`.
- [ ] **Step 2: Run** it. Expected: FAIL (missing slugs).
- [ ] **Step 3: Write the 16 recipes and sheets.**
- [ ] **Step 4: Run** `uv run --no-sync python tests/test_modelos.py` and `uv run --no-sync python helpers/modelos.py check`. Expected: PASS, `check` prints `16 modelos, 0 problemas`.
- [ ] **Step 5: Commit** `feat(modelos): v1 recipes — 14 tipos, 2 estilos`.

### Task 3: `apply` on host `montagem`

**Files:**
- Modify: `helpers/modelos_receitas.py`
- Modify: `helpers/modelos.py` (subcommand `apply`)
- Test: `tests/test_modelos.py` (add)

**Interfaces:**
- Consumes: `load()`, recipe shapes (Task 2).
- Produces:
  - `apply_montagem(m: Modelo, plan: dict, planos: list[int] | None, params: dict[str, str]) -> dict` (pure: returns the new plan; `planos` None = all shots for an estilo; a tipo without `--plano` → SystemExit asking for it)
  - `count_accents(plan: dict) -> list[int]` (shot indices carrying an accent transition)
  - `apply_file(slug: str, target: Path, planos: list[int] | None, params: dict[str, str]) -> Path` (detects host from the file name: `edit-data.json` → reel-fala, else montagem; writes backup, prints diff, records in `state.json.modelos[]`; returns the backup path)

- [ ] **Step 1: Write the failing tests:**
  - `test_whip_pan_on_shot(tmp)`: plan of 4 shots; `apply_file("whip-pan", plan, [2], {"dir": "right"})` → shot 2 `transition == "whip-right"`, backup file exists, other shots unchanged.
  - `test_transicao_velocidade_pairs(tmp)`: applied at shot 2 → shot 1 `ramp == "speed-out"`, shot 2 `ramp == "speed-in"` and `transition == "speed"`.
  - `test_apply_twice_is_idempotent(tmp)`: `zoom-punch` twice on shot 1 → `fx` contains `"pulse"` once.
  - `test_accent_limit(tmp)`: plan already with accents on shots 0, 1, 2; `flash` on shot 3 → SystemExit whose message lists `0, 1, 2`; file unchanged.
  - `test_estilo_montagem(tmp)`: `montagem-na-batida` on an 8-shot plan → every cut uses the primary (`speed` pair), `count_accents()` ≤ 3.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Accent = transition ∈ {flash, whip-*, zoom, rgb-split, shake}; `cut` and `speed` are not accents. The diff is `difflib.unified_diff` over `json.dumps(…, indent=2, ensure_ascii=False)`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(modelos): apply on beat_edit plans with accent limit`.

### Task 4: `apply` on host `reel-fala`

**Files:**
- Modify: `helpers/modelos_receitas.py`
- Test: `tests/test_modelos.py` (add)

**Interfaces:**
- Consumes: `apply_file()` dispatch (Task 3), recipe shapes (Task 2).
- Produces: `apply_reel(m: Modelo, edit: Path) -> tuple[dict, dict | None]` (new `state.json`, new `edit-data.json` or None when the edit-data does not exist yet). Edit-data path: `<edit>/remotion/public/edit-data.json` if present, else `<edit>/edit-data.json`. Cut points: `segments.json` (`{"segments": [{"start", "dur"}]}`) in the same folder as the edit-data; one transition `at = start` for every segment after the first.

- [ ] **Step 1: Write the failing tests:**
  - `test_reel_refuses_before_phase2(tmp)`: `state.json` `{"phase": 1}` → SystemExit mentioning "corte aprovado"; nothing written.
  - `test_push_in(tmp)`: phase 2, edit-data with `camera` → `camera.pushIn == 0.04`, `state.style.elements.zoomAuto is True`, `state.awaitingStyle is True`.
  - `test_flash_on_every_cut(tmp)`: `segments.json` with 3 segments → `transitions` has 2 entries of type `flash` at the 2nd and 3rd starts.
  - `test_flash_without_segments(tmp)`: no `segments.json` → SystemExit naming `segments.json`; nothing written.
  - `test_only_style_when_no_edit_data(tmp)`: no edit-data → only `state.json` changes, message says the edit-data layer will come from the Phase 2 build.
  - `test_profile_rules_printed(tmp, capsys)`: `state.client = "x"` with a profile in `PRISMA_PERFIS` → the profile rules are printed before the diff.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** (accent count over `transitions[]`, same limit and refusal as Task 3).
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(modelos): apply on talking-head reels (style + edit-data)`.

### Task 5: Pexels video search

**Files:**
- Modify: `helpers/pexels_search.py`
- Test: `tests/test_modelos.py` (add, offline)

**Interfaces:**
- Produces: `pexels_search.py <query> --out-dir D --videos [--orientation portrait] [--min-s 3] [--max-s 15] [--count N]` → downloads the best ≤1080-wide-or-high MP4 file of each hit to `D/pexels-<id>.mp4`, prints `id`, author, page URL; and `pick_video_file(video: dict, max_side: int = 1920) -> dict | None` (pure).
- Endpoint: `https://api.pexels.com/videos/search` (same `PEXELS_API_KEY` header as the photo search).

- [ ] **Step 1: Write the failing test** `test_pick_video_file()` over a literal Pexels JSON sample with files 640×360, 1080×1920 and 2160×3840: returns the 1080×1920 file; returns `None` when only 4K exists and `max_side=1920`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `--videos` and `pick_video_file`. Photo behaviour unchanged.
- [ ] **Step 4: Run.** Expected: PASS. Manual: `uv run --no-sync python helpers/pexels_search.py "sports car driving" --videos --orientation portrait --count 1 --out-dir <tmp>` downloads one file (needs the key).
- [ ] **Step 5: Commit** `feat(pexels_search): --videos mode`.

### Task 6: Demo material and demo render

**Files:**
- Create: `helpers/modelos_demo.py`
- Create: `modelos/_demo/demo.json`
- Modify: `helpers/modelos.py` (subcommands `material`, `demo`)
- Test: `tests/test_modelos.py` (add)

**Interfaces:**
- Consumes: `apply_montagem`, `apply_reel` (Tasks 3–4); `pexels_search.py --videos` (Task 5); `epidemic_music.py search|download`; `beat_map.py <audio> -o beats.json`; `media_ledger.py record`; `motion_gates.run_render(video, out, profile, expect)`; `tests/fixture_phase2/make_fixture.py <work>`; `render_phase2.py --edit <e> --engine hyperframes --skip-delivery`.
- Produces:
  - `galeria_root() -> Path` (env, then OneDrive, else SystemExit with the two options)
  - `material(force: bool = False) -> dict` (reads `demo.json` IDs; downloads missing files to `<galeria>/_material/`; records each in the ledger; returns `{"clips": [Path…], "music": Path, "beats": Path}`)
  - `demo_plan(m: Modelo, mat: dict) -> dict` (a 4-shot `beat_edit` plan, 4–6 s, the recipe applied to shot 2 for a tipo, to all shots for an estilo)
  - `render_demo(slug: str, force: bool = False) -> Path` (writes `<galeria>/<slug>/demo.mp4`, `poster.jpg` (frame at 50 %), `gates.json`; deletes `demo.mp4` and raises when G0/G2 fail)
- `demo.json` shape: `{"pexels_videos": [<id>, …4], "epidemic_track": "<id>", "epidemic_start_s": <float>}`; the first material run picks the IDs (query `"sports car driving"`, portrait, 3–15 s; Epidemic `"energetic electronic"`, 110–130 bpm) and writes them, so every later run uses the same material.

- [ ] **Step 1: Write the failing tests** (offline, with a fake material dict of two `testsrc2` clips and a synthetic beats file):
  - `test_demo_plan_tipo()`: `demo_plan(load("whip-pan"), mat)` has 4 shots and only shot 2 carries `whip-*`.
  - `test_demo_plan_estilo()`: `montagem-na-batida` plan passes `count_accents() <= 3`.
  - `test_galeria_root_env(tmp)`: `PRISMA_MODELOS_GALERIA=<tmp>` → that path; with neither env → SystemExit naming both variables.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Reel-fala demos: build the fixture into `<galeria>/_work/fixture`, copy the `v916` edit, set `state.json.phase = 2`, `apply_reel`, render with `render_phase2.py --skip-delivery`, take `remotion/out/render.mp4` or the HyperFrames output it reports.
- [ ] **Step 4: Run** the tests (PASS), then for real: `uv run --no-sync python helpers/modelos.py material` and `uv run --no-sync python helpers/modelos.py demo whip-pan` → `demo.mp4` exists, `gates.json` G0/G2 PASS; and `modelos.py demo push-in` (reel-fala path).
- [ ] **Step 5: Commit** `feat(modelos): demo material and demo render` (only `modelos_demo.py`, `modelos.py`, `demo.json`, tests).

### Task 7: Gallery

**Files:**
- Modify: `helpers/modelos_demo.py`
- Modify: `helpers/modelos.py` (subcommand `galeria [--abrir]`)
- Test: `tests/test_modelos.py` (add)

**Interfaces:**
- Produces: `build_galeria() -> Path` (`<galeria>/index.html`: one card per modelo, grouped by `nivel` then `familia`; card = looping muted `<video>` with poster, name, "O que é" first line, "Quando usar", G0/G2 badges; a modelo without demo shows "sem demo"; estilos list their tipos). Relative `src` paths so the folder works when shared from OneDrive. `--abrir` prints the `file://` URL for the browser pane.
- Produces: `demo_status(slug: str) -> str` (`"✅"` when `<galeria>/<slug>/demo.mp4` and a passing `gates.json` exist, else `"🧪"`); `modelos.py list` prints it before each slug (spec §5.3).

- [ ] **Step 1: Write the failing tests** `test_galeria_missing_demo(tmp)`: two modelos, one demo folder present → HTML contains one `<video` and one `sem demo`; build does not raise. `test_list_shows_demo_status(tmp)`: the same setup → `modelos.py list` prints `✅` for one slug and `🧪` for the other.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the test (PASS); render all 16 demos (`modelos.py demo --all`, background), build the gallery, open it in the browser pane and screenshot it.
- [ ] **Step 5: Commit** `feat(modelos): gallery`.

### Task 8: Wiring into the catalogue and docs

**Files:**
- Modify: `references/tool-map.md` (row **Modelos de edição**: `modelos`, `modelos_receitas`, `modelos_demo` → `modelos/README.md`)
- Modify: `tests/test_catalog.py` (`test_modelos_check()`: `modelos_receitas.check() == []`)
- Modify: `SKILL.md` (Helpers: one entry for `modelos.py`; Phase 2: "a named type or style → `modelos.py show`, then `apply`")
- Modify: `modelos/README.md` (how to add a modelo; the queue from spec §6)
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write the failing test** `test_modelos_check()` in `tests/test_catalog.py`.
- [ ] **Step 2: Run** `uv run --no-sync python tests/test_catalog.py`. Expected: FAIL (helpers missing from the tool map).
- [ ] **Step 3: Edit the four files.**
- [ ] **Step 4: Run** every suite: `test_catalog`, `test_modelos`, `test_motion_gates`, `test_auto_color`, `test_client_profile`, plus `lint_undefined.py`, `regress.py --phase2` (Task 1 touched `beat_edit.py`; Phase 2 is the render path). Expected: all PASS.
- [ ] **Step 5: Commit** `docs(modelos): tool map, catalogue test, SKILL.md`.
