# Compositing — chroma key, AI matting, and making the subject BELONG

Read this before putting a person (or anything) over a new background: a
react/news overlay, a presenter "inside" an event, a product on a new set.

## 0. Pick the path from the footage, not from the wish

| Footage | Path | Quality ceiling |
|---|---|---|
| Shot on a green/blue screen | **chroma key** → `chroma_key.py` | broadcast — hair, motion blur, transparency |
| Shot anywhere else, subject is a person | **AI matte** → `person_matte.py` (RVM) → `matte_refine.py` | good on bodies; edges/hair softer; furniture that touches the person needs the refine pass |
| Static camera, empty "clean plate" available | difference matte (ffmpeg `backgroundkey`) | fragile: noise, light changes, similar colours |
| Object, not a person | `npx hyperframes remove-background` (u2net) or rotoscope | varies |

**Ask the user how it was shot.** The term is *chroma key*; "green screen" is the
everyday name. AI matting is NOT chroma key — say which one you are doing.

## 1. Chroma key (`chroma_key.py`)

Colour-difference keyer (the Keylight/Primatte principle), not ffmpeg's
`chromakey` similarity test:

```
d = S − max(other two)          S = screen channel (G or B, auto-detected)
a = 1 − clamp((d/d_key − clip_black) / (clip_white − clip_black))
```

Order of operations and what each knob is for:

| Step | Flag | Default | Use |
|---|---|---|---|
| key colour | `--color R,G,B` | auto (median of the frame border) | pass it only for unevenly lit screens |
| matte levels | `--clip-black / --clip-white` | 0.15 / 0.85 | raise black if the subject has see-through holes; lower white if screen noise survives as grey |
| garbage matte | `--garbage person` or `x0,y0,x1,y1` | off | kills light stands, screen edges, tracking markers |
| core fill | `--fill-holes` | 0.005 of the frame | enclosed holes ≤ that size are filled — green glare in glasses, a green logo |
| choke | `--choke px` | 0 | eat a bright fringe (1 px is usually enough) |
| feather | `--feather px` | 0.8 | soften the matte edge |
| despill | `--despill 0..1`, `--spill-limit` | 1.0 / 1.0 | S' = min(S, mean(others)×limit) — removes the green bounce on skin/hair/shirt |

**Always QC the matte, not the comp**: `--qc t1 t2` writes matte (black/white)
+ comp on checker side by side. Holes and grey noise are obvious in the matte
and invisible on a busy background until it is too late.

Measured (`--selftest`, synthetic screen with uneven light, noise and rim spill):
matte MAE 0.30%, rim green excess 11.8 → −2.0 after despill. The one classic
failure it reproduced: **green reflections in glasses punch holes** — fixed by
the core fill (`--fill-holes`), which treats enclosed semi-transparent streaks
(a < 0.9) as holes.

### How to SHOOT for a clean key (tell the user before the shoot)
- Screen lit **evenly and separately** from the person (2 soft lights on the screen, no hot spots, no shadows on it).
- Person **1.5–3 m in front of the screen**: less green bounce (spill), no shadow on the screen.
- Expose the screen bright and saturated — underexposed green = noise = grey matte.
- **No green clothing**, no shiny/reflective items; glasses tilted slightly down to avoid reflecting the screen.
- Matte (non-shiny) fabric, stretched without wrinkles.
- **Light the person like the target plate** (direction, colour, hardness). This
  matters more than any post trick: a face lit from the left cannot sit in a
  plate lit from the right.
- Shoot at the delivery orientation and with headroom; 4K if possible (key at 4K, deliver 1080).
- Camera locked (tripod) unless you will track; shutter 1/50–1/60 at 25–30 fps for natural motion blur.

## 2. AI matte without a screen (`person_matte.py` → `matte_refine.py`)

`person_matte.py --model resnet50` (RVM) gives temporally stable edges but keeps
anything touching the person (chair backs, headrests, mic stands).
`matte_refine.py` fixes that with a MediaPipe person gate and a texture rule
limited to the silhouette border — see the helper's docstring for the measured
thresholds. Model: `assets/models/selfie_multiclass_256x256.tflite` (Google,
16 MB, local).

Limits to state honestly: a close, seated selfie framing cannot become a
standing full-body shot; hair against a busy background will be softer than a
key; fast hand motion blurs into the background.

## 3. Make it BELONG (`composite.py`)

A cutout reads fake for measurable reasons. Each flag fixes one:

| Cue | Flag | Typical | Why |
|---|---|---|---|
| colour & light | `--match` | 0.5–0.7 | LAB mean/std of the subject pulled toward the plate (luma full, tint ×0.6) |
| **light wrap** | `--wrap`, `--wrap-px` | 0.5, 28 | blurred plate bleeds onto the subject's rim — the #1 integration cue |
| hard edge | `--edge px` | 1–1.5 | kills the "sticker" line |
| grain/texture | `--grain auto` | auto | adds the plate's noise to the subject + a unifying grain |
| contact | `--shadow dx,dy,blur,op` | 0,30,40,0.35 | grounds a full-body or tabletop subject |
| depth | `--bg-blur px` | 3–6 | plate softer than the subject = lens depth of field; also hides an upscaled plate |
| camera | `--shake px` | 4–8 | handheld drift + micro-rotation on the FINAL comp: both layers move as one camera |
| framing | `--bg-zoom`, `--bg-focus x,y` | — | place the plate's subject (car, stage) where the composition needs it |

`--qc t` writes plain paste vs comp side by side — show that to the user.

### Composition rules that no flag fixes
1. **Perspective & scale**: camera height and lens of the plate must match the
   subject's. A close selfie (wide lens, low distance) over a plate shot from far
   with a long lens reads as a cutout no matter the colour work.
2. **Light direction**: key light on the subject must come from the plate's light source side.
3. **Eye line / interaction**: the subject should look at or point to plate
   elements; a still photo plate + a moving talker is the weakest version — use
   a video plate, or add slow camera motion to the plate.
4. **Resolution parity**: an upscaled 720p plate behind a 4K subject betrays
   itself; blur/grain the plate (depth) rather than sharpen it.

### Post-mortem — BMW Série 3 presenter piece (2026-10)
What made it "not good": no green screen (AI matte with a chair attached),
**selfie framing over a photo plate** (perspective/scale mismatch), still photo
plates behind a moving person, plates upscaled from phone screenshots, only a
CSS drop-shadow as "rim light", no grain or light wrap. The fixes that exist now
— `matte_refine.py`, `composite.py` — cover the post side; the shoot side
(section 1) is what makes the result convincing.
