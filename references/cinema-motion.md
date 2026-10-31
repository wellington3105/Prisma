# Cinema-motion — modern cinematic AND dynamic edits (VFX, motion, narrative sound)

Read this when the ask is "cara de cinema", "cinema atual", "cinemático mas dinâmico",
"VFX/motion" — car, product, lifestyle films built from takes + music. It sits on
top of `beat-sync.md` (grid, ramps, analyser) and `color-multitake.md` (per-take
correction). Origin: BMAD round 2026-10-06 (Mary research, Winston architecture,
Sally style bible, John plan — `Marketing Wellington/tools/bmad-sandbox/output/cinema-vfx-motion/`).

## The rule that makes it cinema, not a template
**Every effect needs a motive the image or the sound already gives.** Removal test:
if taking the effect out doesn't make the shot worse, it goes. Rhythm is
pressure × breathing — at two scales: breathing shots inside a block (no fx,
constant speed) and a whole breathing block (interior, muffled music) before the
biggest payoff. The v2 Taycan looked like a template because it had effects on
9 of 19 cuts, constant pressure, and sound that followed instead of telling.

## Grammar (defaults from the Taycan v3 bible)
- **Primary transition = hard cut on the beat with a speed ramp** ("the car brakes, the cut accelerates"). Accents are COUNTED: ≤ 3 motivated whips (only over a move the take already has), ≤ 2 light-hits (drops only). Out: RGB split, zoom-blur transitions, white flash, glitch, light leak, letterbox, fake DOF/2.5D, light trails.
- **Match cut by light line**: a horizontal light (headlight stroke → tail-light bar → PORSCHE bar) at the same screen height across the cut — `cinema_edit.py` measures the bright line in both plates and shifts the incoming one (`"match": "prev"`).
- **One camera move per shot**, already in the take; synthetic push-in ≤ 8 % only on near-static takes.
- **Slow by default** (0.55–0.75x, analyser), ramps only at cut borders, 120 fps takes at 0.25x real slow motion.
- **24 fps + 180° shutter** for every shot (speed_ramp carries the shutter even at 1.0x). A/B against 30p if whips judder.
- **Look** (film_look.py, per shot): halation .25 base / .8 peak, bloom .15 / .35 at hook and drops, anamorphic streaks only where a light source exists (≤ 2 shots), light sweep on paint (≤ 2), print curve, hue fixes (paint hue target, tail-light red not pink). Grain constant over the whole film (screen-space layer, soft-light, never switches on/off). "Pista" veil (dark gradients top 18 % / bottom 22 %) instead of letterbox — densifies the frame AND protects the Reels UI.
- **Typography**: one family (brand: Archivo variable — voices thesis/statement/label/signature), expo-out motion, HUD callouts that DRAW (1.5 px line in 8 frames, text lands after), one yellow target per film, ≥ 1.2 s per text, safe box x 72–900 · y 260–1480. Numbers only with a source (ledger) — no source, the callout goes.
- **Sound tells the story**: music filtered closed in the intro and inside the cabin (opens over the block), half-beat SILENCE before each drop, sub drop on the hit, reverse whoosh peaking on the cut, door "TUM" masking a bar-cut music edit, real room tone from the takes, UI ticks when a callout finishes drawing. No fake engine sound on an EV.

## Tools
| step | helper |
|---|---|
| per-take correction (no look) | `color_pipeline.py` |
| shake/move analysis, stabilisation | `take_analyzer.py`, `stabilize.py` |
| music map at the delivery cadence | `beat_map.py --fps 24` |
| synthesised SFX kit + diegetic room tone | `sfx_synth.py -o sfx_cinema --room-tone takes…` |
| film look + light VFX per shot | `film_look.py` (halation, bloom, streaks, sweep, light-hit, print curve, hue fix) |
| whole film: segments (music edit), 24p/180°, plates, grain, veil, graphics, narrative mix | `cinema_edit.py plan.json -o edit/hyperframes_cinema` |

`cinema_edit.py` plan schema is in its docstring (shots in TRACK beat numbers;
`segments` cut the music by bars with an equal-power crossfade; `audio.lpf/gain/
silence/cues/beds` build the mix offline, two-pass loudnorm to −14 LUFS / −1 dBTP).

## Choosing the data (client feedback, Taycan v5 — applies to any car)
- Show what the viewer **cannot see** and what **adds value**: the build's
  optional equipment (for Porsche: the factory option list from the VIN /
  vehicle-data sticker in the service book / dealer build sheet), version-specific
  performance, and true segment differentiators. Never caption what the shot
  already shows (e.g. "full-width tail light", "4-point LED DRL").
- Year + version + option list come **before** writing any card; generic specs
  pulled from encyclopedias are a fallback, not the content.
- Motion must mean something: a counter only when the number is a measurement
  in progress (0–100, a range climbing); a static fact (800 V) reveals, it does
  not count.
- ~2.8 s on screen per card; one fact per card; usable as paid-traffic creative.

## Measured on the Taycan v3 (2026-10-06)
- Mix: silence before drop 1 at −66.8 dB (vs −11.6 dB just before); cabin music
  centroid 429 Hz opening to 3.8 kHz across the block; intro 486 Hz → 3.1 kHz.
- Light sweep: flat white added in linear light washed the dark-blue paint to
  grey → the sweep now rides the paint's own sheen (reflection, not paint).

## Backlog (needs download authorisation)
Depth Anything V2 **Small** only (Apache-2.0; Base/Large are CC-BY-NC — forbidden
for client work) for DOF/2.5D; SAM 2.1 tiny (Apache-2.0) car mask; RIFE (MIT)
interpolation; onnxruntime-directml for the RTX GPU.
