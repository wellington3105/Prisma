# motionmaxxing: what is here and where it came from

- Source: https://github.com/Tejashmakwana/motionmaxxing
- Commit: `8c8ec0f2a6f6c9a0da15cd24f7b1298ab298368c` (2026-10-06, "docs: trim license line")
- Licence: Apache-2.0 (`LICENSE`), Copyright Tejas Makwana. Copied 2026-11-21.

| File | Upstream path | Changed? |
|---|---|---|
| `look.py` | `scripts/look.py` | no |
| `lint.mjs` | `scripts/lint.mjs` | no |
| `_cdp.mjs` | `scripts/_cdp.mjs` | no (Chrome path comes from `CHROME_PATH`, set by `helpers/motion_gates.py` on Windows) |
| `slop.md` | `references/slop.md` | no |
| `LICENSE` | `LICENSE` | no |

The 12 eases live in `assets/hyperframes/vendor/prisma-eases.js` (math copied verbatim from
`runtime/motion.js` lines 18-41). Their shapes were checked against the table in upstream
`references/motion.md` §2: all 12 match at 10 / 25 / 50 / 75 % of the time.

Not copied: the GSAP runtime (`runtime/motion.js`, its own seek contract), the render script, brand
capture, voice and image generation, `library/moments.jsonl` and the bundled GSAP / three.js. Prisma
keeps its own pipeline. Update by copying the files from a newer commit, updating the hash above,
then running `python tests/test_motion_gates.py`.

Known limits (upstream `docs/KNOWN-LIMITS.md`): the lint reads the DOM and cannot see text drawn in
`<canvas>`, WebGL, images or video. `look.py` counts frame differences, so heavy grain or shutter blur
moves its numbers.
