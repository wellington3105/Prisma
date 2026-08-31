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

## HyperFrames (heygen-com/hyperframes, Apache-2.0) — ideas, not code

No HyperFrames source is in this repo. Its audio chain, volume automation,
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
