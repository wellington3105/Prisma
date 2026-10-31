# Credits

Third-party code adapted into Prisma. See [`NOTICE`](NOTICE) for the full
license text each entry is under.

## OpenShorts (mutonby/openshorts, MIT)

| Prisma file | Ported from | Notes |
|---|---|---|
| [`helpers/quality_probe.py`](helpers/quality_probe.py) | `quality_probe.py` (repo root) | `load_dotenv()` and the hardcoded `/app/cookies.txt` Docker path removed; `--cookies` made an explicit flag |
| [`helpers/scene_detection.py`](helpers/scene_detection.py) | `scene_detection.py` (repo root) | Default engine swapped from TransNetV2 to PySceneDetect (lighter, no model download) for a local/occasional-use tool; TransNetV2 kept as opt-in (`--engine transnetv2`, `uv sync --extra scenes-neural`) with the same fail-open fallback the original has |
| [`helpers/reframe.py`](helpers/reframe.py) | `reframe_v2.py` + `main.py` (camera state machines: `SmoothedCameraman`, `SpeakerTracker`, face/scene analysis) — repo root | SPLIT/SCREENCAST/INSET/ALTERNATE/WIDE layouts cut (5 modules), most requiring Gemini API which Prisma keeps optional/absent in Phase 1; also cut per-scene crop overrides (web editor UI), YOLO fallback, NVENC. TRACK and GENERAL strategies kept. Face detection ported from MediaPipe's removed `solutions.face_detection` API to the current Tasks API, with the correct BlazeFace `.tflite` weights (the OpenShorts-referenced ones fail metadata validation) |
| [`helpers/clip_finder.py`](helpers/clip_finder.py) | `clip_selection.py` (repo root) | LLM/Gemini-ranking half dropped (Prisma keeps API keys optional everywhere in Phase 1); adapted to Prisma's own transcript schema (`{"words": [...]}` flat entries instead of `{"segments": [...]}` / `{"w","s","e"}`) |

Every ported file lives outside the repo's `cloud/` directory (which carries
a separate commercial license, confirmed unused — see the license audit in
`PLANO-PRISMA.md`, Épico B / B1).

## HyperFrames Studio timeline (Apache-2.0) — design values

The preview timeline wears the HyperFrames Studio look (`PLANO-TIMELINE.md`,
Etapa 1). What was taken are VALUES, catalogued with file:line sources in
[`references/_hf-studio-inventory.md`](references/_hf-studio-inventory.md):

| Prisma file | From `@hyperframes/studio` 0.8.91 | What |
|---|---|---|
| [`assets/preview/timeline-skin.css`](assets/preview/timeline-skin.css) | `styles/theme.css`, `styles/components.css`, `timelineTheme.ts`, `PlayheadIndicator.tsx`, `timelineToolbarStyles.ts` | shell/row/gutter colours, accent `#3ce6ac`, clip and audio-pill styling, selection and handle states, diamond playhead, toolbar button metrics |
| [`assets/preview/app.js`](assets/preview/app.js) `drawRuler` / `drawWave` / `CAPTION_COLORS` | `TimelineRuler.tsx`, `CaptionTimeline.tsx` | ruler tick and label geometry, violet audio pill, caption colour cycle |

Later Etapas port pure logic (snapping, zoom, gaps, marquee); each ported file
will be listed here with its original path.

## HyperFrames Studio as the Prisma EDITOR (Apache-2.0) — embedded, not copied

The EDITOR tab runs the installed HyperFrames CLI (`hyperframes preview`,
started by [`helpers/preview_server.py`](helpers/preview_server.py)) and shows
its Studio in an iframe. No Studio source is vendored.
[`helpers/export_hyperframes.py`](helpers/export_hyperframes.py) writes a
HyperFrames project following its public composition contract
(`/hyperframes-core`) and runs its voice carve (`hyperframes-audio/scripts/carve.mjs`).

Fonts shipped for it in [`assets/hyperframes/fonts/`](assets/hyperframes/fonts/):
Lora (© The Lora Project Authors, SIL Open Font License 1.1 —
`LICENSE-Lora-OFL.txt` alongside), from `@fontsource/lora` 5.3.0.

## HyperFrames (heygen-com/hyperframes, Apache-2.0) — ideas, not code

No HyperFrames source is in this repo outside the timeline values above. Its audio chain, volume automation,
and transitions are implemented as TypeScript/Web Audio/WebGL running inside
its own Puppeteer render context — nothing there translates line-for-line
into Prisma's ffmpeg/Remotion pipeline. The files below were built from
scratch, taking only the documented BEHAVIOR (a fixed voice-processing order,
explicit loudness targets, envelope automation, a media manifest) as the
brief, not their implementation:

| Prisma file | Idea from | Notes |
|---|---|---|
| [`helpers/audio_chain.py`](helpers/audio_chain.py) | `/hyperframes-audio` docs (gate → EQ → compressor → limiter order, loudness targets) | ffmpeg-native (`agate`, `equalizer`, `acompressor`, `alimiter`, `aecho`); reverb is a slap-echo, not true convolution |
| [`helpers/volume_envelope.py`](helpers/volume_envelope.py) | `audioVolumeEnvelope.ts` (keyframed volume, not a fixed level) | Single `volume=eval=frame` expression, piecewise-linear between keyframes |
| [`helpers/media_ledger.py`](helpers/media_ledger.py) | `/media-use` (manifest with provenance) | Flat JSON keyed by file SHA-256, cross-project reuse |
| [`assets/shortform/src/CustomGraphics.tsx`](assets/shortform/src/CustomGraphics.tsx) | `packages/shader-transitions` (WebGL transitions beyond a flash) | `whip-pan` and `glitch` added as CSS/React overlays — CustomGraphics has no access to the video layer underneath, so neither actually blurs/displaces the source pixels the way a shader pass would |

## Compositing and beat-synced montage (2026-10)

| Component | License | Used by |
|---|---|---|
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) `selfie_multiclass_256x256.tflite` (Google) — shipped at `assets/models/` | Apache-2.0 | `helpers/matte_refine.py`, `helpers/chroma_key.py --garbage person` |
| [librosa](https://github.com/librosa/librosa) | ISC | `helpers/beat_map.py` (onset strength, beat tracking, RMS) |
| ffmpeg `minterpolate` (motion-compensated interpolation) | LGPL/GPL (system ffmpeg) | `helpers/speed_ramp.py` |

`chroma_key.py` implements the colour-difference keying principle (as used by
Keylight/Primatte-style keyers) from scratch; `composite.py` (light wrap,
LAB colour transfer, grain match) and `beat_edit.py` (HyperFrames
sub-compositions, GSAP transitions) are original Prisma code.
