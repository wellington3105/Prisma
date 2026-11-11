# Beat-synced montage — speed ramps, motion transitions, cuts on the music

Read this when the user hands you takes + a track and wants a fast, music-driven
edit ("speed ramp", "transições batendo no áudio", "edit dinâmico", car/
product/travel montages). This is different from a talking-head edit: the
MUSIC is the timeline; picture is cut to it.

## The tools, in order

```
take_analyzer.py takes/*.mp4 -o takes_analysis.json     # shake + move per take → stabilise? how slow?
color_pipeline.py takes/*.mp4 --out graded/ --ref hero.mp4 --look "…"   # per-take correction + one look (references/color-multitake.md)
beat_map.py   track.mp3 -o beats.json [--fps 30]        # the cut grid
speed_ramp.py take.mp4 --in A --out B --beats beats.json --from-beat N --n-beats K -o r.mp4
stabilize.py  take.mp4 -o take_stab.mp4 --smoothing 12 --keep-if-better
beat_edit.py  plan.json -o edit/hyperframes_beat         # whole montage → Prisma EDITOR (runs ramps/stab itself)
```

## Speed is the default, not the effect (car / product / lifestyle montages)

**Nearly every take goes in slowed** — 0.55–0.8x, chosen per take by
`take_analyzer.py` (`"default_speed": "auto"` in the plan). Slowing adds weight
and elegance, reveals the move, and lowers the frequency of handheld shake so it
reads as float instead of jitter — often enough that stabilisation is not needed.
Keep 1.0x only where the take's own motion IS the point (a natural whip at its
end, a fast reveal). 120 fps takes: 0.35–0.5x is real slow motion (no
interpolation needed).

**Stabilise only when it pays**: `"default_stabilize": "auto"` stabilises takes
the analyser flags (`shake_px` ≥ 1.2 px/frame) and keeps the result only if the
re-measured shake (crop magnification removed) drops ≥ 20 %. Engine `opencv`
(RANSAC global motion) by default — vid.stab jumped every 4 frames on a glossy
headlight macro (reflections fool its local-motion fields). Measured: +40 %
(headlight macro), +57 % (low front), +14 % (wheel → original kept).

## Smooth ramps — what makes acceleration/deceleration feel right

- Speed between keys is interpolated in **log space** (4x→0.4x linearly stays
  fast and brakes at the very end; in log the deceleration is even) with a
  **quintic smootherstep** (zero velocity and zero acceleration of the speed at
  every key → no jolt entering or leaving a ramp).
- Presets keep every speed change ≥ ~20 % of the shot; a 2-beat shot should
  ramp in ONE direction (ramp-in / ramp-out / speed-out / speed-in) — a full
  fast→slow→fast needs ≥ 4 beats.
- **Sub-frame blending** kills judder: picking the nearest interpolated frame
  makes the cadence alternate (1,1,2,1,1,2…); blending the two frames around the
  exact source time gives an even cadence. Measured v1 → v2 on the Taycan ramps:
  frame-to-frame motion irregularity −57 %, −38 %, −21 %.
- Each render writes `<clip>.speed.png` (log-scale speed graph) — glance at it.
- **The speed-ramp transition**: shot A `"ramp": "speed-out"` (accelerates to 5x
  into the cut), shot B `"ramp": "speed-in"` / `"speed-in-slow"` with
  `"transition": "speed"` (enters at the same peak, decelerates). The cut hides
  inside the motion blur at max speed; a whoosh marks it. Use it 1–3 times per
  montage, at energy changes.

### 1. Map the music first (`beat_map.py`)
Writes tempo, `beats[]`, `downbeats[]` (bar "1"), `hits[]` (strong transients),
`drops[]` (energy jumps: the chorus/drop entries), `cut_points[]` ranked, and a
PNG strip. Everything is frame-snapped.

Measured on a Treblo track: the tracker only locks when drums enter, so the
helper **fits a steady grid** (t = t0 + k·p) to the detected beats and extends
it over intros/outros — a grid beat within 70 ms of a detected one keeps the
detected time. Drops = next 2 bars ≥ 3.5 dB over the previous 4 (single-bar
+3 dB swells inside verses are not drops). Open the PNG once: downbeat lines
should sit on the starts of the waveform blocks.

### 2. Plan the edit on the grid
Rules that make a montage feel "professional":
- **Cut on downbeats; cut faster as energy rises.** Typical shot lengths: intro
  2–4 bars, build 1 bar → 2 beats, drop 1–2 beats, outro back to bars.
- **The drop gets the strongest moment**: hero shot + flash or whip + speed ramp
  whose slow part lands right after the drop.
- **One primary transition (60–70% of cuts are hard cuts or one style) + 1–2
  accents** (see `direction.md`). A different effect on every cut reads amateur.
- **Speed ramps go fast→slow onto the hit** (`ramp-in`) or slow→fast out of a
  moment into the next cut (`ramp-out`). `whip-slow` = punch in fast, hang on the hero.
- **Motion continuity across cuts**: a whip-left should follow movement to the
  left; a zoom transition wants a centred subject on both sides.
- Hits inside a long shot → `pulse` (scale bump per beat) or `shake@N` on the
  big hit, not a cut.

### 3. Speed ramps (`speed_ramp.py`)
The curve is eased (cosine between keys) and scaled so the source span fills
the beats **exactly** (frame-accurate). Quality comes from two things:
- **Interpolation** for slow parts (`--interp mci`, ffmpeg motion-compensated;
  `blend` for previews). Factor auto-picked from the slowest speed (cap `--max-up 8`).
- **Real motion blur** for fast parts: each output frame averages the source
  frames its shutter saw (`--shutter 180`). At 4x the 180° shutter sweeps 2
  source frames → natural smear; at 0.3x it sees < 1 frame → one sharp frame.

Cost: ~2 min per 4 s of 720p source at x5 `mci` (1080p ≈ 2.3× that). Use
`--interp blend` while iterating, `mci` for the export.

**Shoot for ramps** (tell the user): record at **60 fps (120 if the phone
allows)** with a fast shutter only if you want crisp slow-mo; 30 fps footage
slowed below ~0.5x relies on interpolation and shows warping on fast,
complex motion (hands, wheels, crowds). Keep shots steady at the start/end of
the move so the ramp has somewhere to land.

`r.json` also carries a HyperFrames `data-automation` rate lane — the
editable-in-Studio equivalent (no interpolation/blur there: frames repeat).

### 4. Build the montage (`beat_edit.py`)
`plan.json` lists shots with `beats`, optional `ramp` (+`out`), `transition`
and `fx` — schema in the helper docstring. It renders the ramps, writes one
sub-composition per shot (video + entrance + fx + the exit half of the next
transition) and the music bed. Timing is in **integer frames**: shot k ends on
the exact frame shot k+1 starts (seconds rounded to 3–4 decimals left 0.0003 s
gaps the renderer turned into black frames — measured).

| transition | how it is built | use |
|---|---|---|
| `cut` | — | default; most cuts |
| `flash` | white overlay 0.95→0 in 0.18 s on the first frame | the drop, a big hit |
| `whip-left/right/up/down` | picture moves inside a 1.3× overscan (never uncovers the frame) + SVG directional blur 80 px, exit `power2.in` / entrance `power3.out`, 0.2 s each side | energy, following motion |
| `zoom` | out: scale 1.35 + blur 10 px; in: 1.3→1 + blur 12→0 | punch into a detail |
| `rgb-split` | SVG filter splits R/G/B, R and B offset ±22 px → 0 in 6 steps | glitch accent, tech/product |
| `shake` | 5-step impact shake on the cut | heavy hit |

fx: `pulse` (1.045→1 on every beat), `push` (1→1.08 over the shot), `shake@N`.

### 5. Verify (numbers first)
- `npx hyperframes check` must pass.
- Render a draft and **scan for black frames** (mean < 8) — any outside an
  intended fade is a timing gap.
- `snapshot --at` the cut times ±1 frame: transitions peak on the cut frame.
- The montage length must equal `beats[end] − beats[start]` to the frame.

Registry shader transitions (`whip-pan`, `cinematic-zoom`, `light-leak`,
`glitch`, `flash-through-white` — `/hyperframes-registry`) are available when a
heavier look is wanted; the built-ins above are lighter and seek-safe.
