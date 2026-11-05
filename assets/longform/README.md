# Longform template (YouTube 16:9) — DATA-DRIVEN

Phase-2 Remotion composition for horizontal longform. **The code is immutable**
— write `public/edit-data.json`; never read or edit `src/Main.tsx`. Graphics
punctuate, they don't saturate. Captions are OFF by default — ship a `.srt`
(`captions_srt.py`) for YouTube CC. Burned captions are optional
(`captions.enabled`, for Reels horizontal): see the `captions` block below.

## Scaffold (one command)

```bash
cp -R <skill>/assets/longform/. <edit>/remotion/ && cd <edit>/remotion && npm install
```

Copy `cut.mp4` into `public/`, then write `public/edit-data.json`.

## edit-data.json schema (times in seconds on the cut timeline)

```jsonc
{
  "width": 1920, "height": 1080,      // match cut.mp4 exactly (4K: 3840×2160)
  "fps": 30,                           // exact source fps (23.976 → 23.976)
  "durationSec": 512.4,                // EXACT cut.mp4 duration (ffprobe)
  "accent": "#33e0a3",                 // brand accent for bars/cards/callouts
  "broll": [                           // full-frame cutaways over narration
    {"kind": "image", "src": "broll/x.jpg", "start": 12, "dur": 4},
    {"kind": "video", "src": "broll/y.mp4", "start": 40, "dur": 6}
  ],
  "lowerThirds": [                     // name/title card, bottom-left
    {"name": "Seu Nome", "title": "Criador · Prisma", "start": 6, "dur": 4}
  ],
  "chapters": [                        // title card at each chapter start
    {"title": "O que é isso", "start": 14, "dur": 2.4}
  ],
  "callouts": [                        // emphasis chip at a normalized x/y
    {"text": "2x mais rápido", "start": 33, "dur": 3, "x": 0.62, "y": 0.28}
  ],
  "soundtrack": {"enabled": false, "file": "trilha.mp3", "volume": 0.1},
  "captions": {                        // OPTIONAL burned captions (omit = none)
    "enabled": true,                   // false → YouTube file (use the .srt)
    "style": "karaoke",                // karaoke | simples | serifada | classica
    "maxWords": 6,                     // words per line (classica: 14, two lines)
    "fontScale": 1,                    // multiplies the base size (5.8% of height)
    "highlight": "#33e0a3"             // karaoke only: colour of the spoken word
  }
}
```

### Camera, cuts, prism words, spring (VFX — all optional, same keys as shortform)

```jsonc
{
  "camera": {                          // elements.zoomCuts / zoomAuto / tracking
    "enabled": true,
    "zooms": [1.08, 1.14, 1.10],       // zoomCuts: hard zoom ON each cut, cycles.
                                       //   16:9 → 1.06–1.14 (9:16 uses 1.10–1.22). All 1.0 = off
    "pushIn": 0.03,                    // zoomAuto: slow push-in per segment (9:16: 0.04). 0 = off
    "targetX": 0.5, "targetY": 0.4     // tracking: where the face is pinned (never reveals an edge)
  },
  "transitions": [                     // elements.flashCut (+ displace/refract = shaderCut)
    {"at": 12.0, "type": "whip-pan"}   // flash (default) | whip-pan | glitch; intensity, sfx, volume
  ],
  "broll": [
    {"kind": "video", "src": "broll/y.mp4", "start": 40, "dur": 6,
     "enter": "spring",                // elements.springIn — omit = original ease, byte-identical
     "flash": "flash"}                 // flash | whip-pan | glitch on the cutaway's in AND out
  ],
  "highlights": {                      // elements.glassPanel — keyword in a 3D glass-prism frame
    "enabled": true, "variant": "prism",   // "prism" | "pill"
    "offsetS": 0.8,                    // delay after the word is said (so it doesn't duplicate the caption)
    "items": [{"text": "Mercedes CLA", "label": "modelo", "at": 40.2, "dur": 3.2,
               "x": 0.26, "y": 0.32}]  // default left of the speaker, ~1/3 of the width
  }
}
```

Needs `public/segments.json` (`{"segments":[{"start","dur"}]}`, cut boundaries on the
output timeline — the scaffold writes it) and `public/track.json` (`face_track.py`;
tracking OFF → keep the neutral `[[0.5,0.4]]` the template ships). Without
`camera` the base frame is the raw cut. Sizes of the prism card come from the
frame HEIGHT; `x`/`y` are 0..1 of the frame — put it on the empty side of the speaker.

### Captions (burned, optional)

Reads `public/captions.json` (word level —
`captions_for_remotion.py --transcript transcripts/cut.json -o public/captions.json`;
the template ships an empty `[]`). Layout is landscape and relative to the
frame, so 1080p and 4K match: font ≈ 5.8% of height, baseline 10% of height from
the bottom, max line width 70% of width. Drawn above B-roll/glass/transitions.
`stacked` and `scatter` exist too (block in the free third beside the speaker,
`captions.side`: `left` default | `right` | `center`; `stacked` reads
`public/caption-cues.json` from `caption_style.py`). To deliver both versions
render the SAME edit-data twice: `enabled: true` → Reels, `false` → YouTube (+ `.srt`).

### Headline, split screen, PiP

```jsonc
{
  "hook": {"enabled": true, "endSec": 4,        // false/omitted = none
           "text": "Esse Mercedes CLA 200 surpreende por dentro",  // re-broken into TWO lines
           "style": "outline",                   // outline | card | realce | misto
           "side": "left",                       // left | center | right (default left)
           "accent": "#ff5200",                  // realce / misto colour (default = edit-data accent)
           "logo": null, "sign": null},          // card only
  "splitInserts": [                              // side-by-side; same key as 9:16
    {"src": "broll/art.jpg", "start": 12, "end": 18,   // image or video
     "layout": "top",                            // top = art LEFT (id split) | bottom = art RIGHT (id split2)
     "bandW": 0.5, "zoom": 1.12, "focusX": 0.55, "focusY": 0.5,
     "flash": "whip-pan"}                        // transition on the layout change (in + out)
  ],
  "broll": [{"kind": "video", "src": "broll/y.mp4", "start": 40, "dur": 6,
             "pip": true}]                       // PiP: speaker in a top-right window
}
```

Sizes come from the frame (headline ≈ 8–10% of height, ≤ 50% of the width), so
1080p and 4K match. `hook.fontSizePx` / `safeWidth` / `paddingTop` are optional
overrides read at a 1080p basis.

## Render

`npx remotion render Longform out/render.mp4`, loudnorm → `edit/final.mp4`.
Keep the last ~20s visually calm (YouTube end cards).
