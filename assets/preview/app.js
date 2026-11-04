/* Two structural constraints of the timeline gutter, learned the hard way.
   These live here and not in SKILL.md: they matter to whoever EDITS this file,
   not to an agent using the skill, and the skill prompt is resent every turn.

   **Nothing in the ancestor chain of `.track-label` may have `overflow:hidden`** —
   the gutter mask rides `position:sticky` there, and an overflow ancestor makes a
   new scroll container and strands it. That rules out the usual max-height
   accordion; the reveal animates the blocks instead.
   **The panel's `pointerdown` must ignore the gutter.** It falls through to a
   scrub branch that calls `setPointerCapture` on the panel, which retargets the
   following click — a real click on a gutter control was swallowed entirely (while
   a programmatic `.click()` worked, which is what makes it confusing to diagnose)
   and the needle jumped to 0, since the gutter sits left of t=0.
*/
/* Prisma preview — interactive editing timeline.
 * IMMUTABLE app: everything per-session comes from /api/state (state.json,
 * edl.json) + /gen/* (waveform, thumbs) + /media/* (video, captions, edit-data).
 * User adjustments are POSTed to /api/save → <edit>/preview_edits.json and
 * applied by the skill (which re-renders and bumps state).
 *
 * Three interaction rules worth knowing before editing this file:
 *  - The timeline wears the HyperFrames Studio skin (Apache-2.0, see NOTICE and
 *    references/_hf-studio-inventory.md): 48px rows, a track-header column with
 *    icon + name + count, neutral clips, violet audio pills, mono ruler, accent
 *    #3ce6ac. LABEL_W mirrors the CSS var --tl-head (syncLabelW). The gutter masks the lanes with .track-label::before painted in
 *    --panel-bg (the panel is a solid surface for exactly this reason), pinned by
 *    native position:sticky. #gutterLine is the divider, pinned by a scroll-driven
 *    CSS timeline on `translate`. Do NOT re-drive either from a JS scroll handler
 *    or a clip-path animation — both lag a frame and the column visibly breathes
 *    while scrolling. JS only publishes --max-scroll (on zoom/resize).
 *  - Correction markers: M (or the transport button) drops an IN, the next M closes
 *    the range and opens the note editor. They ride in S.notes and ship as
 *    payload.notes on save; watch_edits.py turns each save into a chat notification.
 *  - Zoom: the slider is anchored on the needle, trackpad pinch (wheel+ctrlKey)
 *    on the pointer. Both go through applyZoom(pps, t, anchorX) — never on scroll 0.
 *  - Layout follows the SOURCE aspect: portrait clips get body.portrait (player
 *    right at full column height, transport+timeline left), landscape keeps the
 *    stacked layout. #stage keeps the split from swallowing anything below it.
 *  - Timecode uses a MONOSPACE stack: Poppins ships no tabular figures, so
 *    `font-variant-numeric: tabular-nums` silently does nothing and every digit
 *    change resized the readout, shoving the whole transport row sideways.
 *  - No glows anywhere — depth shadows are fine, coloured halos are not. One
 *    exception, taken from the Studio: the playhead's 6px accent glow.
 *  - The style gate (STYLE_CATALOG → #styleSetup) stands BETWEEN the phases: when
 *    state.awaitingStyle is true it replaces the stage entirely, so the choice of
 *    editing style / caption style / edit elements cannot be skipped. It saves to
 *    <edit>/preview_style.json (never preview_edits.json — different screens,
 *    different moments, one would clobber the other).
 */
'use strict';

// ---------- dom ----------
const $ = (id) => document.getElementById(id);
const video = $('video');
const panel = $('timelinePanel');
const timelineEl = $('timeline');
const rulerCv = $('ruler');
const waveCv = $('wave');
const laneVideo = $('laneVideo');
const laneAudio = $('laneAudio');
const laneCaptions = $('laneCaptions');
const insertTracksEl = $('insertTracks');
const needle = $('needle');
const tooltip = $('tooltip');

// minimal solid icons (design-system consistent — no emoji)
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.2v11.6c0 .9 1 1.5 1.8 1L15 9.2c.8-.5.8-1.7 0-2.2L5.8 1.2C5 .7 4 1.3 4 2.2z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.6" height="12" rx="1"/><rect x="9.4" y="2" width="3.6" height="12" rx="1"/></svg>',
  vol: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11 5.2a3.4 3.4 0 0 1 0 5.6V9.4a2 2 0 0 0 0-2.8V5.2z"/></svg>',
  mute: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11.2 6.2l3.6 3.6m0-3.6l-3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>',
  // track identity — icons replace text labels (data-icon in index.html)
  captions: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3.4" y="8.4" width="4.4" height="1.5" rx=".75"/><rect x="8.9" y="8.4" width="3.7" height="1.5" rx=".75"/></svg>',
  video: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.9v4.2c0 .4.44.64.79.42l3.3-2.1a.5.5 0 0 0 0-.85l-3.3-2.1a.5.5 0 0 0-.79.43z"/></svg>',
  audio: '<svg viewBox="0 0 16 16"><path d="M2.4 6.2v3.6h2.4l3.5 2.8V3.4L4.8 6.2H2.4z"/><path d="M10.5 5.7a3.2 3.2 0 0 1 0 4.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M12.4 3.9a5.7 5.7 0 0 1 0 8.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  inserts: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.2" width="13.6" height="9.6" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.3" cy="6.6" r="1.15"/><path d="M2.6 11.7l3-2.9a1 1 0 0 1 1.34-.05l1.84 1.58 1.5-1.24a1 1 0 0 1 1.29.02l1.72 1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  music: '<svg viewBox="0 0 16 16"><path d="M13.1 1.9 6.6 3.5a.8.8 0 0 0-.6.78v6.06a2.25 2.25 0 1 0 1.5 2.12V6.6l5-1.22v3.5a2.25 2.25 0 1 0 1.5 2.12V2.68a.8.8 0 0 0-.9-.78z"/></svg>',
  text: '<svg viewBox="0 0 16 16"><path d="M2 2.6h12v2.5h-1.5V4.1H8.75v8.1h1.6v1.3H5.65v-1.3h1.6V4.1H3.5v1H2V2.6z"/></svg>',
  notes: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
  flag: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
  // timeline toolbar (HyperFrames Studio layout: fit · − · slider · + · readout)
  fit: '<svg viewBox="0 0 16 16"><path d="M1.5 3v10M14.5 3v10M4 8h8M6 5.8 3.8 8 6 10.2M10 5.8 12.2 8 10 10.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  zoomOut: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M10.4 10.4 14 14M5 7h4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  zoomIn: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M10.4 10.4 14 14M5 7h4M7 5v4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  undo: '<svg viewBox="0 0 16 16"><path d="M5.5 3.5 2.5 6.5l3 3M2.8 6.5H10a3.5 3.5 0 0 1 0 7H7" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  redo: '<svg viewBox="0 0 16 16"><path d="M10.5 3.5l3 3-3 3M13.2 6.5H6a3.5 3.5 0 0 0 0 7h3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  select: '<svg viewBox="0 0 16 16"><path d="M3.5 2.2 12.6 8l-4.1.9 2.3 4.4-1.6.8-2.3-4.4-3 2.9z"/></svg>',
  razor: '<svg viewBox="0 0 16 16"><circle cx="4" cy="12" r="2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="12" cy="12" r="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5.4 10.6 11.5 2.5M10.6 10.6 4.5 2.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  split: '<svg viewBox="0 0 16 16"><path d="M6 3H3.5v10H6M10 3h2.5v10H10M8 1.5v13" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  snap: '<svg viewBox="0 0 16 16"><path d="M3 3v5a5 5 0 0 0 10 0V3h-3v5a2 2 0 0 1-4 0V3z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M3 5.5h3M10 5.5h3" stroke="currentColor" stroke-width="1.4"/></svg>',
};

// Caption segments cycle through these, one colour per line, so neighbouring
// lines stay distinguishable at any zoom. Palette from HyperFrames Studio's
// CaptionTimeline (Apache-2.0, see NOTICE).
const CAPTION_COLORS = ['#3CE6AC', '#FF6B6B', '#4ECDC4', '#FFE66D', '#A78BFA',
  '#F472B6', '#34D399', '#FB923C', '#60A5FA', '#C084FC'];

/* ---------- style catalog (the Fase 1 → Fase 2 gate) ----------
 * The one place that knows which looks Prisma can build. It is APP-level, not
 * session-level: a new editing style or caption style is a new entry here plus
 * its implementation in the track reference — never a per-session UI.
 * The user's pick ships to <edit>/preview_style.json; the skill reads it once,
 * at the gate, and builds Fase 2 from it.
 */
/* Layout mockups are drawn per ORIENTATION, not once for 9:16.
 * `render.py` has always handled landform sources (16:9 longform keeps its own
 * resolution); the gate never did, so a horizontal project was offered three
 * portrait mockups that misdescribed what it would build. Each edit style below
 * ships a `mock(landscape)` that returns the frame for the real aspect.
 *
 * The split geometry is NOT a rotation of the portrait one. In 9:16 the art and
 * the head stack vertically because the frame is tall; in 16:9 the same idea
 * reads as side-by-side, which is how every landscape explainer does it. Rotating
 * the portrait mock would produce a letterbox nobody builds. */
const MOCK_VB = (ls) => (ls ? '0 0 118 66' : '0 0 66 118');
const MOCK_FRAME = (ls) => ls
  ? '<rect x=".5" y=".5" width="117" height="65" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>'
  : '<rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>';

// A caption pill, drawn where that layout actually puts it.
const MOCK_CAPTION = (x, y, w) => `
  <rect x="${x}" y="${y}" width="${w}" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
  <rect x="${x + 4}" y="${y + 4.5}" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
  <rect x="${x + 18}" y="${y + 4.5}" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
  <rect x="${x + 28}" y="${y + 4.5}" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>`;

// The stand-in for B-roll / an inserted image: a photo glyph on an accent field.
const MOCK_ART = (x, y, w, h) => {
  const cx = x + w * 0.24, cy = y + h * 0.3, r = Math.min(w, h) * 0.09;
  const bl = y + h - h * 0.22;
  return `
  <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="rgba(255,119,19,.16)"/>
  <circle cx="${cx}" cy="${cy}" r="${r}" fill="rgba(255,119,19,.6)"/>
  <path d="M${x + w * 0.05} ${bl}l${w * 0.18} -${h * 0.18}a2 2 0 013 0l${w * 0.12} ${h * 0.12} ${w * 0.08} -${h * 0.07}a2 2 0 013 0l${w * 0.18} ${h * 0.13}"
        fill="none" stroke="rgba(255,119,19,.6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
};

// Head-and-shoulders: circle plus the arc of a torso, clipped by the panel.
const MOCK_SUBJECT = (cx, cy, r, baseY, halfW) => `
  <circle cx="${cx}" cy="${cy}" r="${r}" fill="rgba(255,255,255,.16)"/>
  <path d="M${cx - halfW} ${baseY}a${halfW} ${halfW} 0 01${halfW * 2} 0z" fill="rgba(255,255,255,.16)"/>`;

const STYLE_CATALOG = {
  edits: [
    {
      // First on purpose: defaultStyle() takes edits[0], so this is also the
      // default for every new project — a clean full-frame cut, with inserts as
      // something the user opts into.
      id: 'limpa',
      name: 'Limpa',
      mock: (ls) => ls
        ? `<svg viewBox="${MOCK_VB(true)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(true)}
        <rect x="3" y="3" width="112" height="60" rx="5" fill="rgba(255,255,255,.05)"/>
        ${MOCK_SUBJECT(59, 27, 11, 63, 18)}
        <rect x="30" y="11" width="58" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="18.5" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
        ${MOCK_CAPTION(38, 47, 42)}
      </svg>`
        : `<svg viewBox="${MOCK_VB(false)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(false)}
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        ${MOCK_SUBJECT(33, 48, 13, 115, 21)}
        <rect x="14" y="14" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
        <rect x="20" y="21.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
        ${MOCK_CAPTION(12, 74, 42)}
      </svg>`,
    },
    {
      id: 'split',
      /* 9:16 splits the frame; 16:9 does NOT. In widescreen the editorial norm
       * — documentary, YouTube explainer — is a full-frame cutaway: the B-roll
       * covers the picture while the narration keeps running. Splitting a 16:9
       * frame down the middle squeezes the presenter into an awkward portrait
       * sliver, and it is not what `assets/longform` builds either: its
       * `broll[]` layer is "full-frame image (Ken-Burns) or muted video
       * cutaways". The mock has to describe the render, not a symmetry. */
      name: (ls) => (ls ? 'B-roll em tela cheia' : 'Tela dividida'),
      mock: (ls) => ls
        ? `<svg viewBox="${MOCK_VB(true)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(true)}
        ${MOCK_ART(3, 3, 112, 60)}
        <!-- the take continues underneath: a corner of the speaker's frame
             showing through says "cutaway", where a bare photo would read as
             "the video became a slideshow" -->
        <rect x="3" y="3" width="26" height="26" rx="5" fill="#0b0e13" opacity=".82"/>
        ${MOCK_SUBJECT(16, 13, 5, 29, 8)}
        ${MOCK_CAPTION(38, 47, 42)}
      </svg>`
        : `<svg viewBox="${MOCK_VB(false)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(false)}
        ${MOCK_ART(3, 3, 60, 36)}
        <path d="M3 40.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        <rect x="3" y="42" width="60" height="73" rx="5" fill="rgba(255,255,255,.05)"/>
        ${MOCK_SUBJECT(33, 70, 12, 115, 18)}
        ${MOCK_CAPTION(12, 35, 42)}
      </svg>`,
    },
    {
      id: 'split2',
      // The landscape counterpart is the picture-in-picture cutaway: B-roll
      // fills the frame and the talking head stays on screen in a corner. Same
      // material as the option above, different amount of presence.
      name: (ls) => (ls ? 'B-roll com apresentador' : 'Tela dividida 2'),
      mock: (ls) => ls
        ? `<svg viewBox="${MOCK_VB(true)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(true)}
        ${MOCK_ART(3, 3, 112, 60)}
        <rect x="79" y="30" width="34" height="31" rx="4" fill="#0b0e13"/>
        <rect x="79.5" y="30.5" width="33" height="30" rx="3.6" fill="rgba(255,255,255,.07)" stroke="rgba(255,255,255,.28)" stroke-width="1"/>
        ${MOCK_SUBJECT(96, 42, 6, 61, 10)}
        ${MOCK_CAPTION(14, 47, 42)}
      </svg>`
        : `<svg viewBox="${MOCK_VB(false)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(false)}
        <rect x="3" y="3" width="60" height="65" rx="5" fill="rgba(255,255,255,.05)"/>
        ${MOCK_SUBJECT(33, 24, 11, 68, 17)}
        <path d="M3 69.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        ${MOCK_ART(3, 71, 60, 44)}
        ${MOCK_CAPTION(12, 58, 42)}
      </svg>`,
    },
    {
      id: 'broll',
      // O terceiro amount of presence: o B-roll toma o quadro INTEIRO e o
      // apresentador some enquanto ele roda. "Tela dividida 2" o mantém num
      // canto; aqui ele sai. É o corte de cobertura clássico — a voz continua,
      // a imagem troca por completo.
      name: 'B-roll em tela cheia',
      mock: (ls) => ls
        ? `<svg viewBox="${MOCK_VB(true)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(true)}
        ${MOCK_ART(3, 3, 112, 60)}
        ${MOCK_CAPTION(38, 47, 42)}
      </svg>`
        : `<svg viewBox="${MOCK_VB(false)}" xmlns="http://www.w3.org/2000/svg">
        ${MOCK_FRAME(false)}
        ${MOCK_ART(3, 3, 60, 112)}
        ${MOCK_CAPTION(12, 74, 42)}
      </svg>`,
    },
  ],
  // No names on purpose: the sample headline IS the label. Ids and geometry
  // mirror HL_STYLES in the template's Main.tsx — keep the two in step.
  headlines: [
    {id: 'outline', name: 'Contorno', hl: 'outline'},
    {id: 'card', name: 'Cartão', hl: 'card'},
    {id: 'realce', name: 'Realce', hl: 'realce'},
    {id: 'misto', name: 'Misto', hl: 'misto'},
    // Last on purpose: defaultStyle() takes headlines[0]. `hlbox` only so the
    // card matches the height of its siblings in this row.
    {id: 'none', name: 'Nenhum', none: true, hlbox: true},
  ],
  /* Burned-in caption styles are a SHORT-FORM feature. `assets/longform`
   * deliberately ships none of them ("Captions are NOT here — longform ships a
   * .srt for YouTube CC"), because a 16:9 upload gets real closed captions the
   * viewer can turn off, and burning them in fights YouTube's own CC layer.
   * Offering six styles the landscape template cannot build would be the gate
   * lying about the render — the exact failure the aspect-aware mockups fixed. */
  captions: [
    {id: 'karaoke', name: 'Karaokê', demo: 'karaoke', portraitOnly: true},
    {id: 'stacked', name: 'Empilhado', demo: 'stacked', portraitOnly: true},
    {id: 'scatter', name: 'Disperso', demo: 'scatter', portraitOnly: true},
    {id: 'simples', name: 'Simples', stat: 'simples', portraitOnly: true},
    {id: 'serifada', name: 'Serifada', stat: 'serifada', portraitOnly: true},
    {id: 'classica', name: 'Clássica', stat: 'classica', portraitOnly: true},
    {id: 'srt', name: 'Legenda .srt (YouTube CC)', landscapeOnly: true, none: true},
    {id: 'none', name: 'Nenhum', none: true},
  ],
  elements: [
    {
      id: 'tracking',
      name: 'Movimento de tracking',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 5.6V3.4A1.4 1.4 0 013.4 2h2.2M10.4 2h2.2A1.4 1.4 0 0114 3.4v2.2M14 10.4v2.2a1.4 1.4 0 01-1.4 1.4h-2.2M5.6 14H3.4A1.4 1.4 0 012 12.6v-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="2.1"/></svg>',
    },
    {
      id: 'zoomAuto',
      name: 'Automação de zoom in',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.6 10.6L14 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/><path d="M7 5.1v3.8M5.1 7h3.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>',
    },
    {
      id: 'zoomCuts',
      name: 'Zoom in e out nos cortes',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    },
    {
      id: 'flashCut',
      // Turns the beat ON; WHICH transitions[] type (flash/whip-pan/glitch)
      // gets written is an editorial call made in edit-data.json, not a UI
      // choice — see references/shortform.md "Transições na troca de
      // layout". The label stays generic on purpose.
      name: 'Transição na troca de layout',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M3 13.2L13 3.2" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" fill="none"/><path d="M6.6 14L9.4 11.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/><path d="M6.6 4.8L3.8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>',
    },
    {
      id: 'tracked3d',
      // O único elemento que exige um passo OFFLINE antes do render: rodar
      // camera_track.py (gate, segundos) e camera_solve_colmap.py (~2min por
      // 1.5s de clipe) para produzir public/camera.json. Sem esse arquivo o
      // bloco `tracked` não monta e o vídeo renderiza normalmente.
      name: 'Objeto ancorado na cena (3D)',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M8 1.6l5.4 3.1v6.6L8 14.4 2.6 11.3V4.7L8 1.6z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M2.6 4.7L8 7.9l5.4-3.2M8 7.9v6.5" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".6"/></svg>',
    },
    {
      id: 'shaderCut',
      // Unlike flashCut (an overlay), these move the footage's own pixels, so
      // they need the WebGL layer. Which of the two types a given cut gets is
      // an editorial call in edit-data.json — the switch only allows the look.
      name: 'Transição com distorção',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 4.2c1.6 0 1.6 2.2 3.2 2.2S6.8 4.2 8.4 4.2s1.6 2.2 3.2 2.2 1.6-2.2 2.4-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M2 10.4c1.6 0 1.6 2.2 3.2 2.2s1.6-2.2 3.2-2.2 1.6 2.2 3.2 2.2 1.6-2.2 2.4-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity=".6"/></svg>',
    },
    {
      id: 'glassPanel',
      // Palavras-chave da fala numa moldura de VIDRO-PRISMA 3D: `highlights`
      // com variant "prism" (GlassCard.tsx). NÃO é o bloco `glass` — o
      // retângulo vazio que só refratava o vídeo foi reprovado pelo usuário.
      // Ver references/shortform.md "Painel de vidro (3D) = palavras na moldura prisma".
      name: 'Palavras em vidro prisma (3D)',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.6" y="3.4" width="12.8" height="9.2" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4.2 12.2L9.6 3.8M7.4 12.2l4.2-6.6" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".65" stroke-linecap="round"/></svg>',
    },
    {
      id: 'springIn',
      // Entrance curve for inserts. OFF keeps the historical cubic ease, which
      // renders byte-identically to every edit built before this existed —
      // verified, not assumed. ON writes `enter: "spring"` per insert.
      name: 'Entrada com mola',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M1.8 13.4c1.5 0 1.5-3.4 3-3.4s1.5 3.4 3 3.4 1.5-5.6 3-5.6 1.5 2.6 3 2.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="13.6" cy="3.4" r="1.6"/></svg>',
    },
    {
      id: 'brollFull',
      // Promotes inserts from the 780x500 card to the full frame. WHICH clips
      // get promoted, and when, is an editorial call written as `fit: "cover"`
      // per insert in edit-data.json — this switch only says the look is
      // allowed, the same way flashCut turns the beat on without picking the
      // transition type. See references/shortform.md "Inserts — card vs full
      // frame".
      name: 'B-roll em tela cheia',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="2.2" width="13.6" height="11.6" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.4" cy="6.1" r="1.15"/><path d="M2.4 12.4l3.3-3.2a1 1 0 011.34-.05l2 1.72 1.7-1.4a1 1 0 011.29.02l1.6 1.4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    },
    {
      id: 'musicAI',
      name: 'Trilha sonora com IA',
      // OFF by default, unlike the other two defaults-on. Those are free; this
      // is the only element in the catalog that needs an account. Pre-ticked, it
      // walked every first-time user into a signup they never asked for, at the
      // exact moment they expected a finished video. The checkbox is still right
      // there and says what it does — that is discovery enough.
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M12.6 1.6L6.9 3a.7.7 0 00-.55.68v5.6a2 2 0 101.35 1.9V5.9l4.4-1.05v2.9a2 2 0 101.35 1.9V2.3a.7.7 0 00-.85-.7z"/><path d="M2.4 2.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/></svg>',
    },
  ],
};

/* ---------- caption previews: the template's animation, not an impression ----
 * Every number here is lifted from the render (Main.tsx Karaoke/Word and
 * StackedCaptions.tsx STACK_MIXED) and scaled by boxWidth/1080, so the preview
 * shows the real proportions, the real faces and the real motion. If the
 * template's caption look changes, change it HERE too — a preview that lies
 * about the style is worse than no preview.
 */
// The "Nenhum" preview. Deliberately not an empty box: an empty card reads as
// "still loading" next to five that render real type. A struck-through frame
// reads as a choice.
const NONE_MARK = '<svg viewBox="0 0 64 34" style="width:64px;height:34px">'
  + '<rect x="1" y="1" width="62" height="32" rx="5" fill="none" '
  + 'stroke="rgba(255,255,255,.22)" stroke-width="1.5" stroke-dasharray="4 3"/>'
  + '<path d="M14 24L50 10" stroke="rgba(255,255,255,.28)" stroke-width="1.5" '
  + 'stroke-linecap="round"/></svg>';

const CAP_TEXT = 'É assim que sua legenda irá aparecer';
const FPS_REF = 30; // the template's reference fps for frame-based timings

// cubic-bezier solver — the stacked style eases on bezier(.16,1,.3,1)
function bez(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (t) => ((ax * t + bx) * t + cx) * t;
  const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let i = 0; i < 6; i++) {
      const e = fx(t) - x;
      if (Math.abs(e) < 1e-4) break;
      const d = dfx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3); // Easing.out(Easing.cubic)
const easeStack = bez(0.16, 1, 0.3, 1);
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

let capAnims = []; // step(nowSeconds) per visible caption demo

// Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
// rises 34px and fades in over 7 frames; the line is replaced by the next one.
function buildKaraokeDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const lines = [];
  for (let i = 0; i < words.length; i += 3) lines.push(words.slice(i, i + 3));

  const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
  const rise = 34 * s;
  const built = [];
  let t = 0;
  for (const ln of lines) {
    const box = el('div', 'kar-line', wrap);
    box.style.fontSize = `${76 * s}px`;
    const spans = ln.map((w) => {
      const sp = el('span', '', box);
      sp.textContent = w;
      sp.style.marginRight = `${18 * s}px`;
      return sp;
    });
    const start = t;
    t = start + (ln.length - 1) * STEP + ENTER + HOLD;
    built.push({ box, spans, start, end: t });
  }
  const cycle = t + 0.3;

  return (now) => {
    const p = now % cycle;
    for (const L of built) {
      const on = p >= L.start && p < L.end;
      L.box.style.display = on ? '' : 'none';
      if (!on) continue;
      L.spans.forEach((sp, j) => {
        const e = easeOutCubic(clamp01((p - (L.start + j * STEP)) / ENTER));
        sp.style.opacity = e;
        sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      });
    }
  };
}

// Stacked: one cue, lines cycling the STACK_MIXED styles (bold-italic gradient →
// regular small → Playfair italic orange). Words rise 46px with a blur that
// resolves; the cue leaves with the blur_up exit.
const STK_LINES = [
  { words: ['É', 'assim'], style: 0 },
  { words: ['que', 'sua', 'legenda'], style: 1 },
  { words: ['irá', 'aparecer'], style: 2 },
];
function buildStackedDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'stk-cue', wrap);

  const STEP = 0.2, ENTER = 8 / FPS_REF, HOLD = 0.8, EXIT = 7 / FPS_REF;
  const rise = 46 * s, blurIn = 5 * s, upY = 55 * s, cueBlur = 14 * s;
  const shadow = `drop-shadow(0 ${(5 * s).toFixed(2)}px ${(9 * s).toFixed(2)}px rgba(0,0,0,0.5))`;
  const all = [];
  let idx = 0;
  for (const L of STK_LINES) {
    const row = el('div', 'stk-line', cue);
    let size = 86;
    if (L.style === 1) size = Math.round(size * 0.72);
    if (L.style === 2) size = Math.round(size * 0.95);
    row.style.fontSize = `${size * s}px`;
    L.words.forEach((w, i) => {
      // the face/gradient belongs to the WORD, like the template's `...ls` spread
      const sp = el('span', `s${L.style}`, row);
      sp.textContent = w + (i < L.words.length - 1 ? ' ' : '');
      all.push({ sp, start: idx * STEP });
      idx++;
    });
  }
  const exitStart = (idx - 1) * STEP + ENTER + HOLD;
  // short gap after the exit: side by side with the karaoke card, a preview that
  // sits blank for half a second reads as broken rather than as a cue boundary
  const cycle = exitStart + EXIT + 0.15;

  return (now) => {
    const p = now % cycle;
    const ex = clamp01((p - exitStart) / EXIT);
    cue.style.opacity = 1 - ex;
    cue.style.translate = `0px ${(-upY * ex).toFixed(2)}px`;
    cue.style.filter = ex > 0.02 ? `blur(${(cueBlur * ex).toFixed(2)}px)` : '';
    for (const w of all) {
      const e = easeStack(clamp01((p - w.start) / ENTER));
      const eb = (1 - e) * blurIn;
      w.sp.style.opacity = e;
      w.sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      w.sp.style.filter = `${eb > 0.06 ? `blur(${eb.toFixed(2)}px) ` : ''}${shadow}`;
    }
  };
}

/* ---------- headline previews: the template's own hook styles ----------------
 * Same contract as the caption demos — these render what `HookInner` renders,
 * scaled from 1080-wide. The two-line break and the size fit run the SAME
 * algorithm as the template (balance by measured width, then fit to safeW), so
 * the preview shows the real break at the real size, not an approximation.
 * HL_STYLES exists on both sides; change one, change the other.
 */
const HEADLINE_TEXT = 'É assim que vai ficar a sua headline';
const HL_MIN = 40;
const HL_STYLES = {
  outline: { weights: [800, 800], cap: 92, safeW: 900, lh: 1.02 },
  card: { weights: [900, 900], cap: 82, safeW: 820, lh: 1.06 },
  realce: { weights: [900, 900], cap: 86, safeW: 830, lh: 1.04 },
  misto: { weights: [400, 900], cap: 98, safeW: 900, lh: 0.98 },
};

// Measured in RENDER units (1080-wide), scaled to the box only at the end — the
// template's letterSpacing is -1px at 1080, which is NOT proportional once the
// preview shrinks it, so measuring in preview px would break the fit.
let hlMeter = null;
function measureType(text, size, weight, family, tracking) {
  if (!text) return 0;
  if (!hlMeter) {
    hlMeter = document.createElement('span');
    hlMeter.style.cssText =
      'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
    document.body.appendChild(hlMeter);
  }
  hlMeter.style.fontFamily = family || "'Poppins',sans-serif";
  hlMeter.style.letterSpacing = `${tracking == null ? -1 : tracking}px`;
  hlMeter.style.fontSize = `${size}px`;
  hlMeter.style.fontWeight = String(weight);
  hlMeter.textContent = text;
  return hlMeter.offsetWidth;
}
const hlWidth = (text, size, weight) => measureType(text, size, weight);

// Balance by MEASURED width, not word count: "É assim que vai" and "ficar a sua
// headline" are 4 and 3 words but nearly the same width — counting words breaks
// the line in the wrong place.
function hlTwoLines(text, weights) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] || '', ''];
  let best = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) { bestDiff = d; best = [a, b]; }
  }
  return best;
}

function hlFit(lines, S) {
  const widest = (size) =>
    Math.max(hlWidth(lines[0], size, S.weights[0]), hlWidth(lines[1], size, S.weights[1]));
  let size = Math.floor((S.safeW / Math.max(1, widest(100))) * 100);
  size = Math.floor((S.safeW / Math.max(1, widest(size))) * size);
  return Math.max(HL_MIN, Math.min(size, S.cap));
}

function buildHeadlineDemo(host, styleId) {
  const s = host.clientWidth / 1080;
  const S = HL_STYLES[styleId];
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const raw = styleId === 'card' ? HEADLINE_TEXT.toUpperCase() : HEADLINE_TEXT;
  const lines = hlTwoLines(raw, S.weights);
  const size = hlFit(lines, S) * s;
  const box = el('div', `hl-demo hl-${styleId}`, wrap);
  box.style.lineHeight = String(S.lh);
  box.style.letterSpacing = `${-1 * s}px`;

  if (styleId === 'realce') {
    for (const l of lines) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${12 * s}px`;
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'card') {
    box.style.borderRadius = `${24 * s}px`;
    box.style.padding = `${28 * s}px ${46 * s}px`;
  }
  if (styleId === 'outline') {
    box.style.webkitTextStroke = `${12 * s}px #000`;
  }
  lines.forEach((l, i) => {
    if (!l) return;
    const d = el('div', '', box);
    d.style.fontSize = `${size}px`;
    d.style.fontWeight = String(S.weights[i]);
    // var(), not a literal — an inline colour would beat the accent variable and
    // this preview would keep painting orange while the others followed the pick
    if (styleId === 'misto') d.style.color = i === 1 ? 'var(--hl-accent)' : '#fff';
    d.textContent = l;
  });
}

// Scatter ("disperso"): serif, lowercase, one word at a time, off-white with a
// slight darkening toward the baseline. Ordinary words FADE only — no movement;
// the one highlighted word resolves out of a blur and dissolves back into it.
// Mirrors ScatterCaptions.tsx: same line rules, same SPREAD, same hash.
const SCAT = { base: 72, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

function buildScatterDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'scat-cue', wrap);

  const words = CAP_TEXT.toLowerCase().split(' ');
  // highlight = longest word of the cue, and only if it carries weight (>6)
  let hiIdx = -1, hiLen = 6;
  words.forEach((w, i) => { if (w.length > hiLen) { hiLen = w.length; hiIdx = i; } });

  // ragged lines of 3–4 words; the highlighted word takes a line of its own
  const lines = [];
  let line = [];
  words.forEach((w, i) => {
    if (i === hiIdx) {
      if (line.length) lines.push(line);
      lines.push([{ w, i, hi: true }]);
      line = [];
      return;
    }
    line.push({ w, i, hi: false });
    if (line.length >= (scatHash(31 + i) > 0.5 ? 4 : 3)) { lines.push(line); line = []; }
  });
  if (line.length) lines.push(line);

  const STEP = 0.22, ENTER = 7 / FPS_REF, HI_ENTER = 10 / FPS_REF, HOLD = 0.9, EXIT = 8 / FPS_REF;
  const all = [];
  lines.forEach((ln, li) => {
    const row = el('div', 'scat-line', cue);
    row.style.gap = `${SCAT.gap * s}px`;
    let w = 0;
    for (const it of ln) {
      const sp = el('span', it.hi ? 'hi' : '', row);
      sp.textContent = it.w;
      sp.style.fontSize = `${(it.hi ? SCAT.base * SCAT.hiScale : SCAT.base) * s}px`;
      all.push({ sp, start: it.i * STEP, hi: it.hi });
      w += sp.offsetWidth + SCAT.gap * s;
    }
    const room = Math.max(0, (SCAT.safeW * s - w) / 2) * SCAT.spread;
    row.style.translate = `${((scatHash(17 + li * 5 + 3) * 2 - 1) * room).toFixed(1)}px 0px`;
  });

  const exitStart = (words.length - 1) * STEP + ENTER + HOLD;
  const cycle = exitStart + EXIT + 0.35;
  const blurIn = 26 * s, blurOut = 30 * s;

  return (now) => {
    const p = now % cycle;
    const out = clamp01((p - exitStart) / EXIT);
    for (const w of all) {
      const t = easeOutCubic(clamp01((p - w.start) / (w.hi ? HI_ENTER : ENTER)));
      w.sp.style.opacity = t * (1 - out);
      if (w.hi) {
        const b = (1 - t) * blurIn + out * blurOut;
        w.sp.style.filter = b > 0.1 ? `blur(${b.toFixed(2)}px)` : '';
      }
    }
  };
}

/* ---------- the three STATIC caption styles ---------------------------------
 * No animation, so no entry in capAnims — built once and left alone. Mirrors
 * SIMPLE_VARIANTS in SimpleCaptions.tsx, including the rule that matters most:
 * lines are grouped by MEASURED WIDTH, capped at maxWords. That is why a long
 * word ends up alone and short ones ride together.
 */
const STATIC_VARIANTS = {
  simples: {family: "'Poppins',sans-serif", weight: 600, size: 82, maxWords: 3, lines: 1, sx: 0.9, sy: 0.9, tracking: -3, maxW: 860},
  serifada: {family: "'Libre Baskerville',serif", weight: 700, size: 84, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 860},
  classica: {family: "'Inter',sans-serif", weight: 500, size: 52, maxWords: 14, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 840},
};
const ORPHAN_PT = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

function buildStaticDemo(host, id) {
  const V = STATIC_VARIANTS[id];
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const wOf = (ws) => measureType(ws.join(' '), V.size, V.weight, V.family, V.tracking) * V.sx;

  // the WHOLE sentence, cut into cues exactly as the render would
  const cues = [];
  let cur = [];
  for (const w of words) {
    const trial = [...cur, w];
    if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
  }
  if (cur.length) cues.push(cur);

  const boxes = cues.map((cue) => {
    let lines = [cue];
    if (V.lines === 2 && cue.length > 1) {
      let best = 1, bestScore = Infinity;
      for (let i = 1; i < cue.length; i++) {
        const score = Math.abs(wOf(cue.slice(0, i)) - wOf(cue.slice(i))) + (ORPHAN_PT.test(cue[i - 1]) ? 200 : 0);
        if (score < bestScore) { bestScore = score; best = i; }
      }
      lines = [cue.slice(0, best), cue.slice(best)];
    }
    const box = el('div', 'stat-demo', wrap);
    box.style.fontFamily = V.family;
    box.style.fontWeight = String(V.weight);
    box.style.fontSize = `${V.size * s}px`;
    box.style.letterSpacing = `${V.tracking * s}px`;
    box.style.transform = V.sx === 1 && V.sy === 1 ? '' : `scale(${V.sx}, ${V.sy})`;
    for (const ln of lines) el('div', '', box).textContent = ln.join(' ');
    return box;
  });

  // A style with no animation still has a RHYTHM — the cues replacing each other
  // is what the viewer sees. So the card plays the whole sentence, cue by cue,
  // on hard cuts. A single-cue style (the two-line "classica" fits the sentence
  // whole) has nothing to step through and stays still.
  if (boxes.length < 2) return null;
  const HOLD = 0.95;
  const cycle = boxes.length * HOLD;
  return (now) => {
    const i = Math.floor((now % cycle) / HOLD);
    boxes.forEach((b, k) => { b.style.display = k === i ? '' : 'none'; });
  };
}

const CAP_BUILDERS = { karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo };

// .track-label width = content x offset of the lanes. Owned by CSS (--tl-head,
// narrower in the portrait split) and mirrored here — read it back, never hardcode.
let LABEL_W = 48;
function syncLabelW() {
  const v = parseFloat(getComputedStyle(document.body).getPropertyValue('--tl-head'));
  if (v > 0) LABEL_W = v;
}
syncLabelW();
const MIN_SEG = 0.2; // s
const THUMB_EVERY = 2.0;

// ---------- state ----------
let S = {
  state: {}, // state.json
  rendered: [], // ranges as rendered (from edl.json) — the video's truth
  draft: [], // user-editable copy [{source,start,end,beat,removed,orig:{start,end}}]
  videoDuration: 0,
  fps: 24,
  captions: [], // grouped caption lines [{text,start,end}] (rendered space)
  editData: null, // edit-data.json content (phase 2)
  insertsDraft: [], // editable inserts [{kind,label,start,end,ref,orig}]
  wave: null,
  thumbCount: 0,
  tab: 'editor', // ONE editor: HyperFrames Studio; legacy Fase 1/2 timelines are hidden
  pps: 10, // px per second (zoom)
  minPps: 4,
  selected: -1, // selected clip index (draft)
  lastSig: '', // change detection
  savedPending: false,
  notes: [], // correction markers [{id,start,end,text}] — draft-timeline seconds
  pendingIn: null, // an IN is open, waiting for its OUT
  editingNote: null, // id of the note the editor is bound to
  style: null, // current picks {edit, captions, elements:{…}, note}
  jcut: null, // jcut_timeline from edl.json — real output positions per take
  // A1/A2 live folded inside the audio track. They answer "where is the J-cut",
  // which is a question you ask once — so the default is closed, and the choice
  // is remembered rather than re-made every reload.
  jcutOpen: localStorage.getItem('prisma.jcutOpen') === '1',
  // ---- Etapa 2: direct editing (HyperFrames Studio model) ----
  tool: 'select', // 'select' | 'razor'
  snap: localStorage.getItem('prisma.snap') !== '0', // on by default, remembered
  hist: [], // undo stack of draft snapshots
  fut: [], // redo stack
  capSel: -1, // selected caption line (index into S.captions)
  chipSel: -1, // selected overlay chip (index into S.insertsDraft)
  capSig: '', // captions as loaded — dirty test
};

/* First option this aspect can actually render. `captions[0]` is Karaokê, which
 * is portrait-only — on a 16:9 job that default would name a style the longform
 * template never builds. */
function firstFor(group) {
  const ls = isLandscape();
  const o = STYLE_CATALOG[group].find(
    (x) => !(x.portraitOnly && ls) && !(x.landscapeOnly && !ls),
  );
  return (o || STYLE_CATALOG[group][0]).id;
}

function defaultStyle() {
  const elements = {};
  for (const e of STYLE_CATALOG.elements) elements[e.id] = !!e.def;
  return {
    edit: firstFor('edits'),
    headline: firstFor('headlines'),
    captions: firstFor('captions'),
    accent: ACCENT_DEFAULT,
    elements,
    note: '',
  };
}

/* A style saved in one aspect can become unbuildable in another (a project
 * re-cut to 16:9 keeps its "Empilhado" pick). Snap any dead choice back to a
 * valid one instead of shipping it to the renderer. */
function reconcileStyleWithAspect() {
  // an unknown aspect is not "landscape": wait for the decoded frame size
  if (!S.style || !S.aspectKnown) return;
  const ls = isLandscape();
  for (const group of ['edits', 'headlines', 'captions']) {
    const key = group === 'edits' ? 'edit' : group === 'headlines' ? 'headline' : 'captions';
    const cur = STYLE_CATALOG[group].find((o) => o.id === S.style[key]);
    const dead = !cur || (cur.portraitOnly && ls) || (cur.landscapeOnly && !ls);
    if (dead) S.style[key] = firstFor(group);
  }
}

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};

// ---------- draft layout (output-timeline positions) ----------
/* Per-take J-cut geometry, in seconds. `lead` is how far the take's sound runs
 * ahead of its picture; `tail` is what was trimmed off its end. Both are fixed
 * frame counts, so they survive the user trimming a take in the UI. */
function jcutGeom(i) {
  const j = S.jcut && S.jcut[i];
  if (!j) return { lead: 0, tail: 0 };
  return {
    lead: Math.max(0, (j.video_start_in_output || 0) - (j.audio_start_in_output || 0)),
    tail: (j.tail_trim_frames || 0) / (S.fps || 30),
  };
}

/* The draft timeline has to model the J-cut, not just sum the ranges: a take's
 * picture is shorter than its range by the lead it gives up plus the tail it had
 * trimmed. Summing raw ranges made the ruler read 8.07s over a 7.60s render, and
 * every clip after the first sat late by the accumulated lead. Each item also
 * carries its AUDIO placement (aout/adur), which is what the A1/A2 lanes draw —
 * derived here so the lanes follow the user's trims instead of going stale. */
function draftLayout() {
  let t = 0;
  let at = 0;
  return S.draft.map((r) => {
    if (r.removed) return { ...r, out: t, dur: 0, aout: at, adur: 0 };
    // geometry rides on the draft item (set at load, split between the halves
    // of a razor cut) — indexing S.jcut by position broke as soon as a split
    // shifted every later take by one
    const g = r.g || { lead: 0, tail: 0 };
    const span = r.end - r.start;
    const adur = Math.max(0, span - g.tail);
    const dur = Math.max(0, adur - g.lead);
    const item = { ...r, out: t, dur, aout: Math.max(0, at - g.lead), adur, lead: g.lead };
    t += dur;
    at = item.aout + adur;
    return item;
  });
}
function renderedLayout() {
  // Under a J-cut the rendered positions come from render.py, not from summing
  // the ranges — the takes overlap in sound and the picture of each one starts
  // a few frames in. Summing here would place every clip after the first too late.
  if (S.jcut && S.jcut.length === S.rendered.length) {
    return S.rendered.map((r, i) => ({
      ...r,
      out: S.jcut[i].video_start_in_output,
      dur: S.jcut[i].video_duration,
    }));
  }
  let t = 0;
  return S.rendered.map((r) => {
    const dur = r.end - r.start;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
const draftTotal = () => draftLayout().reduce((a, r) => a + r.dur, 0);

/* Draft ↔ rendered mapping goes through SOURCE time, not through the index.
 * A draft item knows which rendered take it came from (`ri`) and where its
 * picture starts in the source (start + lead). That keeps the mapping right
 * after trims (the old version ignored a moved head) and after razor splits
 * (two draft items share one rendered take). */
function renderedPictureStart(k) {
  const R = S.rendered[k];
  return R ? R.start + jcutGeom(k).lead : 0;
}
// draft time → rendered time (for scrubbing the old render while editing)
function draftToRendered(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = dl.length - 1; i >= 0; i--) {
    const d = dl[i];
    if (d.removed || t < d.out) continue;
    const k = d.ri ?? i;
    if (!rl[k]) return Math.min(t, S.videoDuration);
    const src = d.start + (d.g ? d.g.lead : 0) + (t - d.out);
    const off = Math.min(Math.max(0, src - renderedPictureStart(k)), rl[k].dur - 0.02);
    return rl[k].out + off;
  }
  return Math.min(t, S.videoDuration);
}
// rendered time → draft time (needle position during playback)
function renderedToDraft(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let k = rl.length - 1; k >= 0; k--) {
    if (t < rl[k].out) continue;
    const src = renderedPictureStart(k) + (t - rl[k].out);
    const mine = dl.filter((d) => (d.ri ?? -1) === k);
    for (const d of mine) {
      if (d.removed) continue;
      const ps = d.start + (d.g ? d.g.lead : 0);
      if (src >= ps - 1e-6 && src <= ps + d.dur + 1e-6) return d.out + (src - ps);
    }
    // the moment playing was trimmed or removed in the draft → park the needle
    // at the nearest surviving edge of the same take
    if (mine.length) {
      const after = mine.find((d) => d.start + (d.g ? d.g.lead : 0) > src);
      if (after) return after.out;
      const last = mine[mine.length - 1];
      return last.out + last.dur;
    }
    return Math.min(t, draftTotal());
  }
  return t;
}

// ---------- dirty tracking ----------
const clipDirty = (r) => r.removed || r.split || r.start !== r.orig.start || r.end !== r.orig.end;
const chipDirty = (c) => c.deleted || c.start !== c.orig.start || c.end !== c.orig.end;
function edlDirty() {
  return S.draft.some(clipDirty);
}
/* What the cut actually becomes: surviving pieces in order, with pieces that
 * touch in the SAME source merged back. A razor split alone changes nothing on
 * screen — shipping it as two ranges would make render.py put a J-cut seam
 * inside one continuous take and sum its audio with itself (an echo). */
function effectiveRanges() {
  const out = [];
  for (const r of S.draft) {
    if (r.removed) continue;
    const last = out[out.length - 1];
    if (last && last.source === r.source && Math.abs(last.end - r.start) < 1e-6) {
      last.end = r.end;
    } else {
      out.push({ source: r.source, start: r.start, end: r.end, beat: r.beat });
    }
  }
  return out;
}
function cutChanged() {
  const eff = effectiveRanges();
  if (eff.length !== S.rendered.length) return true;
  return eff.some((r, i) => r.source !== S.rendered[i].source ||
    Math.abs(r.start - S.rendered[i].start) > 1e-6 || Math.abs(r.end - S.rendered[i].end) > 1e-6);
}
function insertsDirty() {
  return S.insertsDraft.some(chipDirty);
}
// captions as the flat word list captions.json stores
function flatCaptions() {
  return S.captions.flatMap((l) => l.words.map((w) => ({
    text: w.text, startMs: Math.round(w.startMs), endMs: Math.round(w.endMs),
  })));
}
function capsDirty() {
  return S.captions.length > 0 && JSON.stringify(flatCaptions()) !== S.capSig;
}
function dirtyCount() {
  // a split that removes nothing is not an adjustment — count the cut only when
  // it really differs from what was rendered
  let n = cutChanged()
    ? Math.max(1, S.draft.filter((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length)
    : 0;
  n += S.insertsDraft.filter(chipDirty).length;
  if (capsDirty()) n += 1; // the caption track is saved as one file
  n += S.notes.length; // each correction marker is an unsaved adjustment too
  if (typeof levelsDirty === 'function' && levelsDirty()) n += 1; // any fader moved
  return n;
}
/* The timeline draws edit-data.json; the player draws the last render. When the
 * data is NEWER, the tracks show inserts the video does not contain yet — which
 * reads as "the images are on the timeline but not in the video". Say it. */
function renderStale() {
  const m = S.mtimes || {};
  const vid = m.finalVideo || m.video;
  return !!(m.editData && vid && m.editData > vid + 1);
}

// staleness.py (via /api/state) measures the whole chain: edl → cut.mp4 →
// segments.json → edit-data → final, plus the EDITOR export. The first item is
// the pill's text; the full list (with the fix for each) is its tooltip.
const STALE_DEFAULT = '⟳ A timeline está à frente do vídeo — as inserções abaixo ainda não foram renderizadas.';
function refreshHeader() {
  const pill = $('stalePill');
  if (pill) {
    const items = S.staleness || [];
    pill.classList.toggle('hidden', !(renderStale() || items.length));
    pill.textContent = items.length ? `⟳ ${items[0].what}${items.length > 1 ? ` (+${items.length - 1})` : ''}` : STALE_DEFAULT;
    pill.title = items.map((it) => `• ${it.what}\n   → ${it.fix}`).join('\n');
  }
  renderAgentStrip();
  const n = dirtyCount();
  $('dirtyPill').classList.toggle('hidden', n === 0);
  $('dirtyCount').textContent = n;
  $('btnSave').classList.toggle('hidden', n === 0);
  $('btnDiscard').classList.toggle('hidden', n === 0);
  $('savedPill').classList.toggle('hidden', !(S.savedPending && n === 0));
}

// ---------- data loading ----------
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    // staleness is in the signature: segments.json and the EDITOR export are not
    // in mtimes, so regenerating them would otherwise never clear the pill
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration, data.staleness, data.agentMarkers]);
    if (sig !== S.lastSig) {
      const hadEdits = dirtyCount() > 0;
      if (!hadEdits) {
        S.lastSig = sig;
        await applyState(data);
      } else {
        toast('Novo estado disponível — salve ou descarte seus ajustes para atualizar', 4000);
      }
    }
  } catch (e) { /* server restarting; keep polling */ }
  setTimeout(poll, 2000);
}

async function applyState(data) {
  S.state = data.state || {};
  S.mtimes = data.mtimes || {};
  S.staleness = data.staleness || [];
  S.agentMarkers = data.agentMarkers || [];
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 24;
  S.savedPending = !!data.hasPendingEdits;

  $('projectName').textContent = S.state.project || 'Prisma';
  $('stateMessage').textContent = S.state.message || '';

  const ranges = (data.edl && data.edl.ranges) || [];
  // J-cut timeline, written by render.py. Under a J-cut the picture of every take
  // after the first starts a few frames into itself, so the rendered clip is
  // SHORTER than end-start and the takes do not simply abut. Without this the
  // filmstrip and the needle drift a little further at each junction.
  S.jcut = (data.edl && data.edl.jcut_timeline) || null;
  S.rendered = ranges.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '' }));
  S.draft = S.rendered.map((r, i) => ({
    ...r, ri: i, g: jcutGeom(i), removed: false, orig: { start: r.start, end: r.end },
  }));
  S.selected = -1;
  S.capSel = -1;
  S.chipSel = -1;
  S.hist = [];
  S.fut = [];

  // style picks: the skill's copy wins, so applying a change (or reopening the
  // session) shows what is actually rendered — not a stale local selection
  // shallow spread would replace the whole `elements` map, so a state.style
  // carrying only some of the checkboxes would silently drop the rest
  const d0 = defaultStyle();
  const s0 = S.state.style || {};
  S.style = { ...d0, ...s0, elements: { ...d0.elements, ...(s0.elements || {}) } };
  S.style.elements = { ...defaultStyle().elements, ...((S.state.style || {}).elements || {}) };
  $('setupNote').value = S.style.note || '';
  // the skill opened the gate → land the user on the Estilo tab
  if (S.state.awaitingStyle) S.tab = 'style';
  else if (S.tab === 1 || S.tab === 2) S.tab = 'editor';

  const hasVideo = S.videoDuration > 0;
  $('playerWrap').classList.toggle('hidden', !hasVideo);
  $('editorCol').classList.toggle('hidden', !hasVideo);

  if (hasVideo) {
    updateVideoSrc();
    loadWave();
    loadThumbsMeta();
  }

  // phase 2 data
  const tab2 = document.querySelector('[data-tab="2"]');
  tab2.disabled = (S.state.phase || 1) < 2;
  // Estilo opens when the catalog applies to this job: the skill asked for a
  // pick, or one is already recorded. Before that there is nothing to choose.
  const tabS = document.querySelector('[data-tab="style"]');
  tabS.disabled = !S.state.awaitingStyle && !S.state.style;
  if (tabS.disabled && S.tab === 'style') S.tab = 'editor';
  document.querySelectorAll('.tab').forEach((x) => {
    x.classList.toggle('active', String(x.dataset.tab) === String(S.tab));
  });
  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  if ((S.state.phase || 1) >= 2) {
    if (S.state.captions) {
      try {
        const caps = await (await fetch(`/media/${S.state.captions}?v=${Date.now()}`)).json();
        S.captions = groupCaptions(caps);
        S.capSig = JSON.stringify(flatCaptions());
      } catch (e) { /* absent yet */ }
    }
    if (S.state.editData) {
      try {
        S.editData = await (await fetch(`/media/${S.state.editData}?v=${Date.now()}`)).json();
        buildInsertsDraft();
      } catch (e) { /* absent yet */ }
    }
  }

  fitZoom();
  renderAll();
  renderSetup();
  refreshHeader();
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  // On Fase 2, prefer the music-free render when it exists: it is what makes the
  // soundtrack slider an actual control instead of a note for the next render.
  const st = S.editData && S.editData.soundtrack;
  // same rule as the music track: a configured soundtrack file is enough. Tying
  // this to `enabled` broke the pairing exactly when Remotion stops mixing the
  // music — which is the correct setup, not an edge case.
  const wantSplit = S.tab === 2 && S.state.videoNoMusic &&
                    (st && (st.enabled || st.file) || (S.state.musicOptions || []).length);
  const rel = wantSplit
    ? S.state.videoNoMusic
    : (S.tab === 2 && S.state.finalVideo) ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const vsrc = `/media/${rel}?v=${(S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || 0}`;

  // pair (or unpair) the separate soundtrack element with the picture
  if (musicEl) {
    // a picked option overrides edit-data's file, and its path is relative to
    // the edit dir rather than to remotion/public
    const opts = (S.state && S.state.musicOptions) || [];
    const picked = opts.find((o) => o.id === (S.musicChoice || (opts[0] && opts[0].id)));
    const msrc = !wantSplit ? ''
      : picked && picked.file ? `/media/${picked.file}`
      : `/media/${S.state.editData.replace(/[^/]+$/, '')}${st.file || 'trilha.mp3'}`;
    if (musicEl.dataset.src !== msrc) {
      musicEl.dataset.src = msrc;
      if (msrc) { musicEl.src = msrc; applyMusicVolume(); }
      else { musicEl.pause(); musicEl.removeAttribute('src'); }
    }
  }

  if (video.dataset.src === vsrc) return;
  const t = video.currentTime;
  const wasPlaying = !video.paused && !video.ended;
  video.dataset.src = vsrc;
  video.src = vsrc;
  video.currentTime = t;
  if (wasPlaying) video.play();
}

function groupCaptions(caps) {
  // mirror the template: lines of ≤3 words, break on punctuation
  const lines = [];
  let cur = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text)) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  // the words ride along: a caption line is EDITABLE now, and what gets saved
  // is the word list captions.json stores, not the grouped display text
  return lines.map((line) => recapLine({ words: line.map((w) => ({ ...w })) }));
}
// derived fields of a caption line, recomputed after every edit
function recapLine(l) {
  l.text = l.words.map((w) => w.text.replace(/[.,!?…]+$/, '')).join(' ');
  l.start = l.words[0].startMs / 1000;
  l.end = l.words[l.words.length - 1].endMs / 1000;
  return l;
}

function buildInsertsDraft() {
  const d = S.editData;
  const list = [];
  if (d.hook && d.hook.enabled) {
    list.push({ kind: 'hook', label: `HOOK — ${(d.hook.lines || []).join(' / ')}`, start: 0, end: d.hook.endSec || 4 });
  }
  (d.inserts || []).forEach((it, i) => {
    list.push({ kind: 'insert', label: (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i });
  });
  // split-layout images (CustomGraphics reads the same array) — they are images
  // like any other insert, so they belong on the image track, not in code
  (d.splitInserts || []).forEach((it, i) => {
    list.push({
      kind: 'split',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  // split-layout VIDEO bands — same seam and geometry as splitInserts, but the
  // band plays a clip (generated b-roll, screen capture). Its own array because
  // the renderer mounts it with a different component; on the timeline it is an
  // image-track element like any other.
  (d.splitVideos || []).forEach((it, i) => {
    list.push({
      kind: 'splitvideo',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  (d.behind || []).forEach((b, i) => {
    list.push({ kind: 'behind', label: `BEHIND ${b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop()}`, start: +b.start, end: +b.start + +b.dur, ref: i });
  });
  // held single words in the caption's own visual language (a keyword the viewer
  // must type, an emphasis beat) — text, so they ride the text track next to the
  // hook rather than the image track
  (d.wordAccents || []).forEach((w, i) => {
    list.push({ kind: 'word', label: w.text, start: +w.start, end: +w.end, ref: i });
  });
  // keyword glass cards (GlassCard.tsx) — text, so they ride the text track;
  // `at` is when the word is said, the card itself enters offsetS later
  ((d.highlights && d.highlights.enabled && d.highlights.items) || []).forEach((h, i) => {
    const dur = h.dur || 3.2;
    list.push({ kind: 'highlight', label: h.text, start: +h.at, end: +h.at + dur, ref: i });
  });
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
}

async function loadWave() {
  try {
    S.wave = await (await fetch('/gen/waveform.json')).json();
    drawWave();
  } catch (e) { S.wave = null; }
}
async function loadThumbsMeta() {
  try {
    const meta = await (await fetch('/gen/thumbs/meta.json')).json();
    S.thumbCount = meta.count || 0;
    renderClips();
  } catch (e) { S.thumbCount = 0; }
}

// ---------- zoom / layout ----------
function contentWidth() { return LABEL_W + Math.max(draftTotal(), S.videoDuration, 1) * S.pps + 14; }
function fitZoom() {
  const avail = panel.clientWidth - LABEL_W - 40;
  const total = Math.max(draftTotal(), S.videoDuration, 1);
  S.minPps = Math.max(1, avail / total);
  S.pps = S.minPps;
  $('zoom').value = 0;
  updateZoomRead();
}
// "Fit" at the fitted scale, otherwise the zoom as a percentage of it
function updateZoomRead() {
  const pct = Math.round((100 * S.pps) / S.minPps);
  $('zoomRead').textContent = pct <= 100 ? 'Fit' : `${pct}%`;
}
const MAX_PPS = 200;

// Zoom keeping `t` (seconds) parked at `anchorX` (px from the panel's left edge).
function applyZoom(pps, t, anchorX) {
  S.pps = Math.min(MAX_PPS, Math.max(S.minPps, pps));
  const span = Math.log(MAX_PPS / S.minPps);
  $('zoom').value = span > 0 ? Math.round((100 * Math.log(S.pps / S.minPps)) / span) : 0;
  updateZoomRead();
  renderAll();
  panel.scrollLeft = Math.max(0, LABEL_W + t * S.pps - anchorX);
  drawRuler();
  drawWave();
  positionNeedle();
}

// Trackpad pinch arrives as a wheel event with ctrlKey set. Anchored on the
// pointer (a direct gesture zooms where the fingers are); the slider stays
// anchored on the needle.
panel.addEventListener('wheel', (e) => {
  if (!e.ctrlKey) return; // plain two-finger scrolling stays untouched
  e.preventDefault();
  const pr = panel.getBoundingClientRect();
  const anchorX = e.clientX - pr.left;
  const t = (panel.scrollLeft + anchorX - LABEL_W) / S.pps;
  applyZoom(S.pps * Math.exp(-e.deltaY * 0.01), Math.max(0, t), anchorX);
}, { passive: false });

function setZoom(v) { // slider 0..100 → minPps..200, anchored on the needle
  const t = renderedToDraft(video.currentTime || 0);
  // viewport x of the needle before the zoom; if it is off-screen, pull it to
  // the middle so zooming always lands on the playhead the user is looking at
  const xBefore = LABEL_W + t * S.pps - panel.scrollLeft;
  const visible = xBefore >= LABEL_W && xBefore <= panel.clientWidth;
  const anchor = visible ? xBefore : LABEL_W + (panel.clientWidth - LABEL_W) / 2;
  applyZoom(S.minPps * Math.pow(MAX_PPS / S.minPps, v / 100), t, anchor);
}
// − / + buttons: halve / double the scale, same needle anchor as the slider
function stepZoom(factor) {
  const span = Math.log(MAX_PPS / S.minPps);
  if (span <= 0) return;
  const next = Math.min(MAX_PPS, Math.max(S.minPps, S.pps * factor));
  setZoom((100 * Math.log(next / S.minPps)) / span);
}

// Lanes are clipped at the gutter (and the divider is positioned) by a
// scroll-driven CSS timeline, so both stay pinned to scrollLeft with zero lag.
// All JS has to publish is the scroll RANGE, which only changes on zoom/resize.
function updateScrollRange() {
  const max = Math.max(0, panel.scrollWidth - panel.clientWidth);
  timelineEl.style.setProperty('--max-scroll', `${max}px`);
}

// ---------- rendering ----------
function renderAll() {
  timelineEl.style.width = `${contentWidth()}px`;
  renderClips();
  renderJcutAudio();
  renderChips();
  renderNotes();
  drawRuler();
  drawWave();
  updateScrollRange();
  positionNeedle();
}

// ---------- correction markers ----------
const AGENT_KINDS = {
  duvida_take: 'dúvida de take', hesitacao: 'hesitação mantida', nota: 'nota não entendida',
  sugestao: 'sugestão', alerta: 'alerta técnico', borda: 'borda a conferir',
};
/* Source time → draft-timeline time, through the same geometry draftLayout()
 * uses (picture starts at start + lead). A moment that is no longer in the cut
 * parks at the nearest surviving edge of that source and says so (inCut=false):
 * a doubt about a take the user just removed is still worth seeing. */
function sourceToDraft(source, st) {
  const dl = draftLayout().filter((d) => !d.removed && d.source === source && d.dur > 0);
  if (!dl.length) return null;
  let best = null;
  for (const d of dl) {
    const ps = d.start + (d.lead || 0);
    if (st >= ps - 1e-6 && st <= ps + d.dur + 1e-6) return { t: d.out + (st - ps), inCut: true };
    const edge = st < ps ? { t: d.out, gap: ps - st } : { t: d.out + d.dur, gap: st - (ps + d.dur) };
    if (!best || edge.gap < best.gap) best = edge;
  }
  return { t: best.t, inCut: false };
}
/* Source time → CUT time (cut.mp4, what the EDITOR shows), via the rendered
 * layout. Same parking rule as sourceToDraft for a moment no longer in the cut. */
function sourceToRendered(source, st) {
  const rl = renderedLayout();
  let best = null;
  for (let k = 0; k < rl.length; k++) {
    if (rl[k].source !== source) continue;
    const ps = renderedPictureStart(k);
    if (st >= ps - 1e-6 && st <= ps + rl[k].dur + 1e-6) return { t: rl[k].out + (st - ps), inCut: true };
    const edge = st < ps ? { t: rl[k].out, gap: ps - st } : { t: rl[k].out + rl[k].dur, gap: st - (ps + rl[k].dur) };
    if (!best || edge.gap < best.gap) best = edge;
  }
  return best ? { t: best.t, inCut: false } : null;
}
function renderAgentStrip() {
  const strip = $('agentStrip');
  if (!strip) return;
  const items = (S.agentMarkers || [])
    .map((m) => ({ m, p: sourceToRendered(m.source, +m.at) }))
    .filter((x) => x.p)
    .sort((a, b) => a.p.t - b.p.t);
  strip.classList.toggle('hidden', items.length === 0);
  strip.innerHTML = '';
  if (!items.length) return;
  el('span', 'agent-lbl', strip).textContent = `Claude · ${items.length} marcaç${items.length > 1 ? 'ões' : 'ão'}`;
  for (const { m, p } of items) {
    const it = el('span', `agent-item k-${m.kind}${p.inCut ? '' : ' out-of-cut'}`, strip);
    it.dataset.agent = m.id;
    const kind = AGENT_KINDS[m.kind] || m.kind;
    const time = el('b', null, it);
    time.textContent = fmt(p.t);
    it.appendChild(document.createTextNode(`${kind}${p.inCut ? '' : ' (fora do corte)'} — ${m.text || ''}`));
    it.title = `${kind} · ${fmt(p.t)} no corte${p.inCut ? '' : ' (o trecho saiu do corte; mostrado na borda mais próxima)'}\n` +
               `${m.source} ${(+m.at).toFixed(2)}s na fonte\n${m.text || ''}`;
  }
}
function renderNotes() {
  const lane = $('laneNotes');
  lane.innerHTML = '';
  for (const n of S.notes) {
    const chip = el('div', 'note-chip', lane);
    chip.style.left = `${n.start * S.pps}px`;
    chip.style.width = `${Math.max((n.end - n.start) * S.pps, 10)}px`;
    chip.textContent = n.text || '(sem descrição)';
    chip.title = `${fmt(n.start)} → ${fmt(n.end)}\n${n.text || ''}\n\nclique para editar`;
    chip.dataset.id = n.id;
  }
  // Claude's own markers (agent_markers.json), anchored in SOURCE time so they
  // follow the take through trims and re-cuts. Blue/yellow, never the user's red,
  // and not clickable as notes — they are information, not a pending edit.
  for (const m of S.agentMarkers || []) {
    const a = sourceToDraft(m.source, +m.at);
    if (!a) continue;
    const b = m.end != null ? sourceToDraft(m.source, +m.end) : null;
    const w = b && b.inCut && a.inCut ? Math.max((b.t - a.t) * S.pps, 6) : 6;
    const chip = el('div', `agent-chip k-${m.kind}${a.inCut ? '' : ' out-of-cut'}`, lane);
    chip.style.left = `${a.t * S.pps}px`;
    chip.style.width = `${w}px`;
    chip.dataset.agent = m.id;
    const label = AGENT_KINDS[m.kind] || m.kind;
    chip.title = `Claude · ${label}${a.inCut ? '' : ' (fora do corte)'}\n${m.source} ${(+m.at).toFixed(2)}s na fonte\n${m.text || ''}`;
  }
  if (S.pendingIn != null) {
    const p = el('div', 'note-pending', lane);
    p.style.left = `${S.pendingIn * S.pps}px`;
  }
  const btn = $('btnMark');
  btn.classList.toggle('armed', S.pendingIn != null);
  $('markText').textContent = S.pendingIn != null ? 'OUT' : 'IN';
}

function toggleMark() {
  const t = renderedToDraft(video.currentTime || 0);
  if (S.pendingIn == null) {
    S.pendingIn = t;
    renderNotes();
    toast('IN marcado — leve a agulha ao fim do trecho e marque o OUT', 2600);
    return;
  }
  const start = Math.min(S.pendingIn, t);
  const end = Math.max(S.pendingIn, t);
  if (end - start < 0.05) {
    toast('Trecho curto demais — afaste a agulha do IN', 2200);
    return;
  }
  S.pendingIn = null;
  const note = { id: `n${Date.now()}`, start, end, text: '' };
  S.notes.push(note);
  S.notes.sort((a, b) => a.start - b.start);
  renderNotes();
  openNoteEditor(note.id, true);
}

function openNoteEditor(id, isNew) {
  const n = S.notes.find((x) => x.id === id);
  if (!n) return;
  S.editingNote = id;
  $('noteRange').textContent = `${fmt(n.start)} → ${fmt(n.end)}`;
  $('noteText').value = n.text || '';
  $('noteDelete').classList.toggle('hidden', !!isNew);
  // centred over the timeline (where the user's eyes are), then clamped so a
  // short timeline panel cannot push the editor off-screen
  const ed = $('noteEditor');
  ed.classList.remove('hidden');
  const p = panel.getBoundingClientRect();
  const h = ed.offsetHeight;
  const w = ed.offsetWidth;
  const cy = Math.min(
    Math.max(p.top + p.height / 2, h / 2 + 12),
    window.innerHeight - h / 2 - 12,
  );
  const cx = Math.min(Math.max(p.left + p.width / 2, w / 2 + 12), window.innerWidth - w / 2 - 12);
  ed.style.left = `${cx}px`;
  ed.style.top = `${cy}px`;
  $('noteText').focus();
}

function closeNoteEditor() {
  // a brand-new marker with no text is not worth keeping
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n && !n.text.trim()) S.notes = S.notes.filter((x) => x.id !== n.id);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
}

// ---------- style setup ----------
/* True when the SOURCE is landscape. `applyOrientation()` sets the body class
 * off the decoded frame, so the gate follows the same signal the player does —
 * one source of truth, and it survives a project switching aspect. Falls back to
 * portrait before the first frame decodes, which is the short-form default. */
const isLandscape = () => !document.body.classList.contains('portrait');

// `name` and `mock` may be strings or (landscape) => string. Resolve on read so
// a catalog entry can describe both aspects without the callers branching.
const forAspect = (v) => (typeof v === 'function' ? v(isLandscape()) : v);

const styleName = (group, id) =>
  forAspect((STYLE_CATALOG[group].find((o) => o.id === id) || {}).name) || '—';
// the accent is a free colour, not a named entry in a list — it names itself
const accentName = (hex) => String(hex || ACCENT_DEFAULT).toUpperCase();
const normHex = (v) => {
  let s = String(v || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join(''); // #abc → #aabbcc
  return /^[0-9a-f]{6}$/i.test(s) ? `#${s.toLowerCase()}` : null;
};

/* Which styles actually paint the accent. Kept as data because the honest UI
 * note depends on it: with `karaoke` + `outline` picked, nothing on screen uses
 * the colour, and saying so beats letting the user wonder why the previews did
 * not move. Mirrors the template — update both together. */
const ACCENT_USERS = {headlines: ['realce', 'misto'], captions: ['stacked']};
const ACCENT_DEFAULT = '#ff5200';

function applyAccent() {
  $('styleSetup').style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
}

/* One spectral swatch (the OS picker) plus a hex field — no preset row. A grid of
 * canned colours competes with the style cards for attention and still never has
 * the brand colour the user actually wants. */
function renderAccents() {
  const host = $('optAccent');
  host.innerHTML = '';
  const cur = normHex(S.style.accent) || ACCENT_DEFAULT;

  const custom = el('label', 'swatch custom', host);
  custom.title = 'Escolher cor';
  custom.style.setProperty('--swatch-fill', cur);
  const inp = el('input', '', custom);
  inp.type = 'color';
  inp.value = cur;

  const field = el('div', 'hex-field', host);
  el('span', 'hex-hash', field).textContent = '#';
  const hex = el('input', 'hex-input', field);
  hex.type = 'text';
  hex.spellcheck = false;
  hex.maxLength = 7;
  hex.value = cur.slice(1).toUpperCase();
  hex.setAttribute('aria-label', 'Cor de destaque em hexadecimal');

  const commit = (v, {fromHexField} = {}) => {
    const n = normHex(v);
    if (!n) return false;
    S.style.accent = n;
    custom.style.setProperty('--swatch-fill', n);
    inp.value = n;
    if (!fromHexField) hex.value = n.slice(1).toUpperCase();
    applyAccent();   // live — no full rebuild, so dragging the picker stays smooth
    updateAccentNote();
    updateSummary();
    return true;
  };

  inp.addEventListener('input', () => commit(inp.value));
  // typing: accept as soon as it parses, but never fight the user mid-keystroke
  hex.addEventListener('input', () => {
    field.classList.toggle('bad', !normHex(hex.value) && hex.value.trim() !== '');
    commit(hex.value, {fromHexField: true});
  });
  // leaving an unparseable value snaps back rather than silently keeping the old
  // colour behind text that says something else
  hex.addEventListener('blur', () => {
    field.classList.remove('bad');
    hex.value = (normHex(S.style.accent) || ACCENT_DEFAULT).slice(1).toUpperCase();
  });
  hex.addEventListener('keydown', (e) => { if (e.key === 'Enter') hex.blur(); });

  updateAccentNote();
}

const accentUsed = () =>
  ACCENT_USERS.headlines.includes(S.style.headline)
  || ACCENT_USERS.captions.includes(S.style.captions);

function updateAccentNote() {
  const where = [
    ACCENT_USERS.headlines.includes(S.style.headline) && 'na headline',
    ACCENT_USERS.captions.includes(S.style.captions) && 'na legenda',
  ].filter(Boolean);
  $('accentNote').textContent = where.length
    ? `aplicada ${where.join(' e ')}`
    : 'os estilos escolhidos não usam destaque';
}

/* Separate from renderSetup so the live colour drag can refresh it without
 * rebuilding every demo. Skipping it there left the footer naming the previous
 * colour while the previews already showed the new one. */
function updateSummary() {
  const on = STYLE_CATALOG.elements.filter((e) => S.style.elements[e.id]);
  const accentBit = accentUsed() ? ` · destaque ${accentName(S.style.accent)}` : '';
  $('setupSummary').textContent =
    `${styleName('edits', S.style.edit)} · headline ${styleName('headlines', S.style.headline)}` +
    ` · legenda ${styleName('captions', S.style.captions)}${accentBit} · ` +
    (on.length ? on.map((e) => e.name).join(', ') : 'sem elementos extras');
}

/* ---------- EDITOR: HyperFrames Studio inside Prisma ----------
 * Prisma decides the edit; this tab is where it is edited by hand, live, with
 * the full HyperFrames Studio (Apache-2.0, heygen-com/hyperframes): every take,
 * caption line, card and image is a clip on its own track. preview_server.py
 * hosts the Studio process; export_hyperframes.py builds its project from the
 * Prisma edit. Nothing here re-implements the Studio — it is embedded as is. */
let editorPoll = null;
async function openEditor() {
  const frame = $('editorFrame');
  const msg = $('editorMsg');
  let st;
  try { st = await (await fetch('/api/studio')).json(); } catch (e) { st = { available: false }; }
  const ex = st.export || {};
  const busy = ex.running;
  $('editorBuild').classList.toggle('hidden', busy || (st.available && st.url));
  $('editorBuild').textContent = st.available ? 'Recriar editor a partir do Prisma' : 'Criar editor desta edição';
  if (st.url) {
    if (frame.dataset.src !== st.url) { frame.dataset.src = st.url; frame.src = st.url; }
    frame.classList.remove('hidden');
    msg.classList.add('hidden');
    $('editorRebuild').classList.remove('hidden');
    return;
  }
  frame.classList.add('hidden');
  msg.classList.remove('hidden');
  $('editorRebuild').classList.add('hidden');
  $('editorMsgText').textContent = busy
    ? 'Gerando o editor: cada take, legenda, card e imagem vira um clipe editável…'
    : ex.ok === false ? `Não consegui gerar o editor:\n${ex.log || ''}`
    : st.available ? 'Abrindo o editor…'
    : 'Esta edição ainda não tem editor. Ele é gerado a partir do corte e da Fase 2.';
  if ((busy || st.available) && !editorPoll) {
    editorPoll = setTimeout(() => { editorPoll = null; if (S.tab === 'editor') openEditor(); }, 1500);
  }
}
async function buildEditor(force) {
  if (force && !confirm('Recriar o editor a partir do Prisma apaga o que foi editado nele. Continuar?')) return;
  await fetch(`/api/studio/export${force ? '?force=1' : ''}`, { method: 'POST' });
  $('editorFrame').dataset.src = '';
  openEditor();
}
$('editorBuild').addEventListener('click', () => buildEditor(false));
$('editorRebuild').addEventListener('click', () => buildEditor(true));

// The Estilo tab. It sits BETWEEN the phases and is always reachable once the
// catalog applies to this job: changing the caption style after Fase 2 exists,
// or ticking one more element and re-rendering, is normal editing — not a
// decision the user gets exactly one shot at.
let wasShowing = false; // gate was up on the previous render (for the re-fit)

function renderSetup() {
  const show = S.tab === 'style';
  const editor = S.tab === 'editor';
  $('styleSetup').classList.toggle('hidden', !show);
  $('editorPane').classList.toggle('hidden', !editor);
  const hasVideo = S.videoDuration > 0;
  $('stage').classList.toggle('hidden', show || editor || !hasVideo);
  $('emptyState').classList.toggle('hidden', hasVideo || show || editor);
  if (editor) openEditor();

  if (!show) {
    capAnims = []; // stop stepping demos that are not on screen
    // the timeline was display:none while the tab was up, so its panel had no
    // width to fit against — re-fit once it is back on screen
    if (wasShowing && hasVideo) requestAnimationFrame(() => { fitZoom(); renderAll(); });
    wasShowing = false;
    return;
  }
  if (!wasShowing) $('styleSetup').scrollTop = 0; // open at the top, always
  wasShowing = true;
  reconcileStyleWithAspect(); // before the cards are built, not after

  /* The label states the OUTCOME, not the mechanism. "Salvar e refazer a Fase 2"
   * named an internal phase and buried the only thing the user cares about: a
   * new video comes out of this. The first pick and a later change are also
   * genuinely different actions — one starts the edit, the other redoes it — so
   * they keep separate wording. */
  $('setupGo').textContent = S.state.awaitingStyle
    ? 'Aplicar estilo e montar o vídeo'
    : 'Aplicar mudanças e regerar o vídeo';

  capAnims = [];
  const radios = (host, group, chosen) => {
    // An option the current aspect cannot render must not be on screen at all.
    // Greying it out would still invite the click; hiding it keeps the gate an
    // honest list of what this project can actually produce.
    const ls = isLandscape();
    const opts = STYLE_CATALOG[group].filter(
      (o) => !(o.portraitOnly && ls) && !(o.landscapeOnly && !ls),
    );
    host.innerHTML = '';
    for (const o of opts) {
      const card = el('div', `opt${o.id === chosen ? ' on' : ''}`, host);
      card.dataset.group = group;
      card.dataset.id = o.id;
      // headline previews are two short lines — they do not need the caption
      // box's height, and with four groups on one screen that height is scarce
      const kind = o.mock ? 'frame' : (o.hl || o.hlbox) ? 'cap hlbox' : 'cap';
      const prev = el('div', `opt-preview ${kind}`, card);
      // a landscape mock is wide and short: without this the CSS keeps sizing it
      // to the portrait box and the frame renders letterboxed inside its own card
      if (o.mock && isLandscape()) prev.classList.add('ls');
      if (o.demo) capAnims.push(CAP_BUILDERS[o.demo](prev));
      else if (o.hl) buildHeadlineDemo(prev, o.hl);
      else if (o.stat) {
        const step = buildStaticDemo(prev, o.stat);
        if (step) capAnims.push(step);
      }
      else if (o.none) prev.innerHTML = NONE_MARK;
      else prev.innerHTML = forAspect(o.mock) || '';
      // Only the abstract mockups get a title. A card that renders the real
      // caption or the real headline is already labelled — by itself.
      if (o.mock || o.none) el('div', 'opt-name', card).textContent = forAspect(o.name);
      el('div', 'opt-mark', card);
    }
    // the ghost only earns its space where there is a single option to explain
    if (opts.length < 2) el('div', 'opt ghost', host).textContent = 'mais estilos em breve';
  };
  // set BEFORE the demos are built: buildHeadlineDemo reads the accent through
  // var(), so the variable has to be in place when the previews first paint
  applyAccent();

  radios($('optEdit'), 'edits', S.style.edit);
  radios($('optHeadline'), 'headlines', S.style.headline);
  radios($('optCaptions'), 'captions', S.style.captions);
  renderAccents();

  const host = $('optElements');
  host.innerHTML = '';
  for (const e of STYLE_CATALOG.elements) {
    const on = !!S.style.elements[e.id];
    const row = el('div', `chk${on ? ' on' : ''}`, host);
    row.dataset.id = e.id;
    el('div', 'chk-box', row);
    el('div', 'chk-ico', row).innerHTML = e.icon || '';
    el('div', 'chk-name', row).textContent = e.name;
  }

  updateSummary();
}

$('styleSetup').addEventListener('click', (e) => {
  // the accent controls manage themselves (live, no rebuild) — keep the card
  // handler off them, or a click in the hex field would count as a style pick
  if (e.target.closest('#optAccent')) return;
  const opt = e.target.closest('.opt:not(.ghost)');
  if (opt) {
    const key = {edits: 'edit', headlines: 'headline', captions: 'captions'}[opt.dataset.group];
    S.style[key] = opt.dataset.id;
    renderSetup();
    return;
  }
  const chk = e.target.closest('.chk');
  if (chk) {
    S.style.elements[chk.dataset.id] = !S.style.elements[chk.dataset.id];
    renderSetup();
  }
});

$('setupGo').addEventListener('click', async () => {
  S.style.note = $('setupNote').value.trim();
  const rerender = !S.state.awaitingStyle;
  const payload = {
    // a save with Fase 2 already on disk is a RE-RENDER request, not a first
    // pick — the skill has to know which of the two it is looking at
    type: 'style-setup',
    rerender,
    edit: S.style.edit,
    editName: styleName('edits', S.style.edit),
    headline: S.style.headline,
    headlineName: styleName('headlines', S.style.headline),
    captions: S.style.captions,
    captionsName: styleName('captions', S.style.captions),
    accent: S.style.accent,
    accentName: accentName(S.style.accent),
    // whether the picked styles actually paint it — so the skill does not go
    // hunting for an accent in a look that has none
    accentUsed: accentUsed(),
    elements: { ...S.style.elements },
    // forAspect: catalog names may be per-aspect functions (the edit layouts
    // are). Elements are plain strings today, but reading them raw would ship a
    // "(ls) => ..." into the payload the day one of them needs both aspects.
    elementNames: STYLE_CATALOG.elements
      .filter((e) => S.style.elements[e.id])
      .map((e) => forAspect(e.name)),
    note: S.style.note,
  };
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if ((await res.json()).ok) {
    S.savedPending = true;
    renderSetup();
    refreshHeader();
  } else {
    toast('Erro ao enviar — o servidor está de pé?', 4000);
  }
});

function renderClips() {
  laneVideo.innerHTML = '';
  const dl = draftLayout();
  const rl = renderedLayout();
  // Both phases: the Fase-2 tab used to lock the picture, so "I want to cut
  // this by hand" had no answer once the overlays existed. A cut edit made there
  // re-runs Phase 1 and the overlays are re-timed by the skill.
  const editable = S.tab === 1 || S.tab === 2;
  $('countVideo').textContent = dl.filter((r) => !r.removed).length || '';
  dl.forEach((r, i) => {
    if (r.removed && r.dur === 0) {
      // removed: show a slim ghost at its slot
      const g = el('div', 'clip removed', laneVideo);
      g.style.left = `${r.out * S.pps}px`;
      g.style.width = `${Math.max((r.end - r.start) * S.pps * 0.4, 34)}px`;
      g.dataset.i = i;
      g.title = 'clique e pressione delete para restaurar';
      return;
    }
    const c = el('div', 'clip', laneVideo);
    c.style.left = `${r.out * S.pps}px`;
    c.style.width = `${Math.max(r.dur * S.pps, 8)}px`;
    c.dataset.i = i;
    if (i === S.selected) c.classList.add('selected');
    if (r.split || r.start !== r.orig.start || r.end !== r.orig.end) c.classList.add('dirty');

    // filmstrip from the rendered cut — positioned through the draft→rendered
    // map, so a trimmed or split piece shows its own frames, not its take's head
    if (S.thumbCount > 0) {
      const strip = el('div', 'thumbs', c);
      const first = Math.floor(draftToRendered(r.out) / THUMB_EVERY);
      const n = Math.ceil(r.dur / THUMB_EVERY) + 1;
      for (let k = 0; k < n; k++) {
        const idx = first + k + 1; // ffmpeg %04d is 1-based
        if (idx > S.thumbCount) break;
        const img = el('img', '', strip);
        img.src = `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = `${THUMB_EVERY * S.pps}px`;
        img.style.objectFit = 'cover';
      }
    }
    const lab = el('div', 'clip-label', c);
    lab.textContent = `${r.beat || r.source} `;
    const dur = el('div', 'clip-dur', c);
    dur.textContent = `${r.dur.toFixed(2)}s`;

    if (editable) {
      el('div', 'handle l', c).dataset.i = i;
      el('div', 'handle r', c).dataset.i = i;
    }
  });
}

/* J-cut audio lanes.
 * The point is legibility, not decoration: on one lane an overlap is invisible,
 * because two blocks that overlap in time just look like one continuous block.
 * Alternating takes across A1/A2 is what makes the "J" readable — exactly how it
 * reads in Premiere. The overlap itself gets a marker on the incoming block, so
 * the user can see how many frames of voice arrive before the picture.
 */
function renderJcutAudio() {
  const t1 = $('trkAudioA1'), t2 = $('trkAudioA2');
  const l1 = $('laneAudioA1'), l2 = $('laneAudioA2');
  const btn = $('jcutToggle');
  l1.innerHTML = ''; l2.innerHTML = '';

  const has = !!(S.jcut && S.jcut.length && S.tab !== 'style');
  // the caret only appears when there is a J-cut to expand; otherwise the chip
  // stays an ordinary track icon
  btn.classList.toggle('disclose', has);
  btn.disabled = !has;
  btn.setAttribute('aria-expanded', String(has && S.jcutOpen));
  btn.title = !has ? 'Áudio (mix)'
    : S.jcutOpen ? 'Áudio (mix) — recolher as faixas do J-cut (A1/A2)'
                 : 'Áudio (mix) — expandir as faixas do J-cut (A1/A2)';

  const on = has && S.jcutOpen;
  t1.classList.toggle('hidden', !on);
  t2.classList.toggle('hidden', !on);
  if (!on) return;

  // drawn off the DRAFT layout so the blocks move with the user's trims
  draftLayout().forEach((r, i) => {
    if (r.removed && r.adur === 0) return;
    const lane = i % 2 === 0 ? l1 : l2;
    const b = el('div', 'ablock', lane);
    b.style.left = `${r.aout * S.pps}px`;
    b.style.width = `${Math.max(r.adur * S.pps, 6)}px`;
    el('div', 'ablock-label', b).textContent = r.beat || r.source || '';

    // the lead: sound already playing while the previous take is still on screen
    if (r.lead > 1e-6) {
      const ov = el('div', 'ablock-lead', b);
      ov.style.width = `${r.lead * S.pps}px`;
    }
    const tf = Math.round(((r.g && r.g.tail) || 0) * (S.fps || 30));
    let tip = `${r.beat || r.source}\náudio ${r.adur.toFixed(2)}s`;
    if (r.lead > 1e-6) {
      tip += `\nJ-cut: ${Math.round(r.lead * S.fps)}f (${Math.round(r.lead * 1000)}ms) `
           + 'de voz antes da imagem';
    }
    if (tf) tip += `\ncauda aparada ${tf}f`;
    b.title = tip;
  });
}

function renderChips() {
  const phase2 = S.tab === 2;
  $('trkCaptions').classList.toggle('hidden', !phase2);
  insertTracksEl.classList.toggle('hidden', !phase2);
  insertTracksEl.innerHTML = '';
  if (!phase2) return;

  laneCaptions.innerHTML = '';
  $('countCaptions').textContent = S.captions.length || '';
  for (const [k, c] of S.captions.entries()) {
    const start = renderedToDraft(c.start);
    const end = renderedToDraft(c.end);
    const chip = el('div', 'chip caption', laneCaptions);
    chip.style.setProperty('--cap', CAPTION_COLORS[k % CAPTION_COLORS.length]);
    chip.style.left = `${start * S.pps}px`;
    chip.style.width = `${Math.max((end - start) * S.pps, 6)}px`;
    chip.dataset.k = k;
    if (k === S.capSel) chip.classList.add('selected');
    el('span', 'cap-text', chip).textContent = c.text;
    chip.title = `${c.text}\n${fmt(c.start)} → ${fmt(c.end)} · duplo clique edita o texto`;
    el('div', 'handle l', chip).dataset.k = k;
    el('div', 'handle r', chip).dataset.k = k;
  }

  // TEXT and IMAGE get their own tracks — a headline and a photo are different
  // kinds of edit, and mixing them on one lane hid the images entirely.
  const isText = (c) => c.kind === 'hook' || c.kind === 'word' || c.kind === 'highlight';
  const groups = [
    { icon: 'text', cls: 'teal', name: 'Texto', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => isText(c)) },
    { icon: 'inserts', cls: 'orange', name: 'Imagens', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => !isText(c)) },
  ];

  for (const g of groups) {
    if (!g.items.length) continue;
    // overlapping elements stack onto extra lanes within the same group
    const order = [...g.items].sort((a, b) => a.c.start - b.c.start || a.c.end - b.c.end);
    const trackEnd = [];
    const assign = new Map();
    for (const { c, i } of order) {
      let t = trackEnd.findIndex((end) => c.start >= end - 1e-6);
      if (t < 0) { t = trackEnd.length; trackEnd.push(0); }
      trackEnd[t] = c.end;
      assign.set(i, t);
    }
    const lanes = [];
    for (let t = 0; t < Math.max(trackEnd.length, 1); t++) {
      const trk = el('div', 'track', insertTracksEl);
      const lab = el('div', 'track-label', trk);
      // only the first lane of a group carries the icon; the rest are continuations
      if (t === 0) {
        el('span', `tl-chip ${g.cls}`, lab).innerHTML = ICON[g.icon];
        el('span', 'tl-name', lab).textContent = g.name;
        el('span', 'tl-count', lab).textContent = g.items.length;
      }
      lanes.push(el('div', 'lane', trk));
    }
    for (const { c, i } of g.items) {
      if (c.deleted) continue;
      const chip = el('div', `chip insert ${isText(c) ? 'hook' : ''} k-${c.kind}`, lanes[assign.get(i) ?? 0]);
      chip.style.left = `${c.start * S.pps}px`;
      chip.style.width = `${Math.max((c.end - c.start) * S.pps, 10)}px`;
      chip.textContent = c.label;
      chip.title = `${c.label}\n${fmt(c.start)} → ${fmt(c.end)}`;
      chip.dataset.i = i;
      if (i === S.chipSel) chip.classList.add('selected');
      if (c.start !== c.orig.start || c.end !== c.orig.end) chip.classList.add('dirty');
      el('div', 'handle l', chip).dataset.i = i;
      el('div', 'handle r', chip).dataset.i = i;
    }
  }

  // The voice track owns the mix everything else sits under, so its fader is
  // mounted onto the existing audio lane rather than given a row of its own.
  if (laneAudio && !laneAudio.querySelector('.lvl-fader')) {
    const strip = el('div', 'lane-strip', laneAudio);
    el('span', 'lvl-name', strip).textContent = 'voz';
    buildFader(strip, LEVELS.find((l) => l.id === 'voice'));
  }

  // SFX: the click/scratch layer the stacked captions bake in. Declared only —
  // it lives inside the Remotion render and takes effect on the next one.
  const capSfx = S.editData && S.editData.captions && S.editData.captions.sfx;
  if (capSfx && capSfx.enabled !== false) {
    const trk = el('div', 'track', insertTracksEl);
    const sfxLab = el('div', 'track-label', trk);
    el('span', 'tl-chip', sfxLab).innerHTML = ICON.audio;
    el('span', 'tl-name', sfxLab).textContent = 'SFX';
    const lane = el('div', 'lane', trk);
    const chip = el('div', 'chip music sfx', lane);
    const dur = (S.editData.durationSec || S.videoDuration || draftTotal());
    chip.style.left = '0px';
    chip.style.width = `${Math.max(dur * S.pps, 10)}px`;
    el('span', 'music-name', chip).textContent = 'efeitos (legenda)';
    el('span', 'music-hint', chip).textContent = 'próximo render:';
    buildFader(chip, LEVELS.find((l) => l.id === 'sfx'));
  }

  // soundtrack → its own track, one chip spanning the whole video, with a
  // volume slider. The mix is baked into the delivered file, so the slider
  // cannot change what you HEAR in the player — it states the value the next
  // render should use, and is saved like any other edit.
  // `enabled` says whether REMOTION mixes the music, and it should normally be
  // false: the soundtrack is mixed in the delivery ffmpeg, where the fader
  // controls it. Showing the track only when Remotion mixes it would hide the
  // fader in exactly the setup that needs it — so the track appears whenever a
  // soundtrack file is configured at all.
  const st = S.editData && S.editData.soundtrack;
  const hasMusic = st && (st.enabled || st.file || (S.state && S.state.musicOptions));
  if (hasMusic) {
    if (S.musicVol == null) S.musicVol = st.volume != null ? st.volume : 0.1;
    const trk = el('div', 'track', insertTracksEl);
    const musLab = el('div', 'track-label', trk);
    el('span', 'tl-chip olive', musLab).innerHTML = ICON.music;
    el('span', 'tl-name', musLab).textContent = 'Trilha';
    const lane = el('div', 'lane', trk);
    const chip = el('div', 'chip music', lane);
    const dur = S.editData.durationSec || S.videoDuration || draftTotal();
    chip.style.left = '0px';
    chip.style.width = `${Math.max(dur * S.pps, 10)}px`;
    const name = (st.file || 'trilha.mp3').split('/').pop();

    const label = el('span', 'music-name', chip);
    label.textContent = name;

    // When the skill renders more than one soundtrack, the user has no way to
    // HEAR the alternatives — telling them "compare the two files" in chat asks
    // them to leave the app and open an mp4 by hand. The options ride here, on
    // the track they belong to, and switching swaps the player source.
    const opts = (S.state && S.state.musicOptions) || [];
    if (opts.length > 1) {
      const pick = el('div', 'music-pick', chip);
      ['pointerdown', 'mousedown', 'click', 'dblclick'].forEach((ev) =>
        pick.addEventListener(ev, (e) => e.stopPropagation()));
      const current = S.musicChoice || opts[0].id;
      opts.forEach((o) => {
        const b = el('button', 'music-opt' + (o.id === current ? ' on' : ''), pick);
        b.type = 'button';
        b.textContent = o.label;
        b.title = `Tocar ${o.label}`;
        b.addEventListener('click', () => {
          S.musicChoice = o.id;
          if (o.video) S.state.finalVideo = o.video;
          const t = video.currentTime;
          const playing = !video.paused;
          video.dataset.src = '';        // force updateVideoSrc to reload
          if (musicEl) musicEl.dataset.src = '';
          updateVideoSrc();
          video.currentTime = t;
          if (playing) video.play().catch(() => {});
          renderAll();
        });
      });
    }
    // With videoNoMusic on disk the slider is audible right now; without it the
    // music is baked into the picture and the value only reaches the next
    // render. Say which one this is — a slider that silently does nothing is
    // worse than no slider.
    el('span', 'music-hint', chip).textContent =
      S.state && S.state.videoNoMusic ? 'ao vivo' : 'próximo render:';

    // one fader, same component as voice and sfx — the music used to have a
    // bespoke slider and the other tracks had none, which is not a mixer
    buildFader(chip, LEVELS.find((l) => l.id === 'music'));
  }

  applyLevels();
}

/* ---------- live soundtrack (real volume control) ----------
 * The delivered file has the music baked in, so a slider over it can only
 * DECLARE a value. When state.videoNoMusic exists, the player switches to that
 * music-free render and plays the soundtrack from its own <audio>, which makes
 * the slider audible on the spot. Sync is one-way: video is the clock, music
 * follows, and it re-seeks whenever they drift more than ~0.3s.
 */
const musicEl = $('musicTrack');

/* ---------- per-track levels ----------
 * Every audio track carries its own fader, and the number on it is the number
 * the next render uses — no rounding, no "about right". A mixer where one
 * channel is adjustable and the rest are fixed is not a mixer.
 *
 * `voice` rides the player directly (audible now). `music` rides the separate
 * <audio> when the music-free render exists. `sfx` is baked into the Remotion
 * output and can only be DECLARED — which is why each fader states its own
 * mode instead of pretending they all behave alike.
 */
const LEVELS = [
  {id: 'voice', label: 'voz', def: 1.0, max: 1.5, live: true},
  // max 0.8: a carved soundtrack (music_carve.py) sits around 0.22–0.55, so a
  // 0.4 ceiling pinned the fader below the value the delivery actually used
  {id: 'music', label: 'trilha', def: 0.1, max: 0.8, live: 'split'},
  {id: 'sfx', label: 'efeitos', def: 0.45, max: 1.0, live: false},
];

function levelValue(id) {
  const slider = document.querySelector(`.lvl-fader[data-id="${id}"] input`);
  if (slider) return +slider.value;
  if (S.levels && S.levels[id] != null) return S.levels[id];
  // No fader on screen (e.g. the Fase 1 tab) and nothing moved: the value is the
  // project's own. Falling back to spec.def here reported a phantom unsaved edit
  // whenever edit-data carried a soundtrack volume other than 0.1.
  return levelBaseline(id);
}

function levelBaseline(id) {
  const ed = S.editData || {};
  if (id === 'music') {
    const st = ed.soundtrack || {};
    return st.volume != null ? st.volume : 0.1;
  }
  if (id === 'sfx') {
    const s = (ed.captions && ed.captions.sfx) || {};
    return s.clickVolume != null ? s.clickVolume : 0.45;
  }
  return (ed.voiceVolume != null) ? ed.voiceVolume : 1.0;
}

function levelsDirty() {
  return LEVELS.some((l) => Math.abs(levelValue(l.id) - levelBaseline(l.id)) > 1e-9);
}

function applyLevels() {
  const v = levelValue('voice');
  if (video) video.volume = Math.max(0, Math.min(1, v));
  applyMusicVolume();
}

/** A fader that reads as a channel strip, not as a range input. */
function buildFader(parent, spec) {
  const wrap = el('div', 'lvl-fader', parent);
  wrap.dataset.id = spec.id;
  ['pointerdown', 'mousedown', 'click', 'dblclick'].forEach((ev) =>
    wrap.addEventListener(ev, (e) => e.stopPropagation()));

  const base = levelBaseline(spec.id);
  const start = (S.levels && S.levels[spec.id] != null) ? S.levels[spec.id] : base;

  const slider = el('input', '', wrap);
  slider.type = 'range';
  slider.min = '0';
  slider.max = String(spec.max);
  slider.step = '0.01';
  slider.value = String(start);
  slider.title = spec.live === true
    ? `Volume de ${spec.label} — audível agora e salvo neste valor`
    : spec.live === 'split'
      ? `Volume de ${spec.label} — audível agora (render sem música) e salvo neste valor`
      : `Volume de ${spec.label} — gravado no vídeo, aplicado no próximo render`;

  const out = el('span', 'lvl-val', wrap);
  const paint = () => {
    const v = +slider.value;
    out.textContent = v.toFixed(2);
    const dirty = Math.abs(v - base) > 1e-9;
    out.classList.toggle('changed', dirty);
    wrap.classList.toggle('dirty', dirty);
  };
  paint();

  slider.addEventListener('input', () => {
    S.levels = S.levels || {};
    S.levels[spec.id] = +slider.value;
    if (spec.id === 'music') S.musicVol = +slider.value;
    paint();
    applyLevels();
    refreshHeader();
  });
  return wrap;
}

function musicLive() {
  return !!(S.state && S.state.videoNoMusic && musicEl && musicEl.src);
}

function applyMusicVolume() {
  if (!musicEl) return;
  const v = S.musicVol != null ? S.musicVol : 0.1;
  // the mix multiplies the source; clamp so a slider at max cannot distort
  musicEl.volume = Math.max(0, Math.min(1, v));
}

function syncMusic() {
  if (!musicLive() || !video) return;
  if (video.paused) {
    if (!musicEl.paused) musicEl.pause();
    return;
  }
  if (Math.abs(musicEl.currentTime - video.currentTime) > 0.3) {
    musicEl.currentTime = video.currentTime;
  }
  if (musicEl.paused) musicEl.play().catch(() => {});
}

// The live slider is the source of truth while it is on screen: re-rendering
// the timeline rebuilds the element, and reading S.musicVol alone let a stale
// value reach the payload (measured: UI showed 0.18, save wrote 0).
function musicVolNow() {
  const slider = document.querySelector('.music-vol input');
  if (slider) return +slider.value;
  return S.musicVol;
}
// the soundtrack volume differs from what was rendered → part of "dirty"
function musicDirty() {
  const st = S.editData && S.editData.soundtrack;
  if (!st || !st.enabled) return false;
  const now = musicVolNow();
  if (now == null) return false;
  return Math.abs(now - (st.volume != null ? st.volume : 0.1)) > 1e-9;
}

// ---------- canvases (viewport-sized, redrawn on scroll) ----------
function canvasSetup(cv, lane) {
  const dpr = window.devicePixelRatio || 1;
  const w = panel.clientWidth;
  const h = lane.clientHeight;
  cv.width = w * dpr;
  cv.height = h * dpr;
  cv.style.width = `${w}px`;
  cv.style.height = `${h}px`;
  cv.style.position = 'absolute';
  // lanes start LABEL_W into the scrolled content — offset the viewport-sized
  // canvas so it covers exactly the visible strip of the lane
  const left = Math.max(0, panel.scrollLeft - LABEL_W);
  cv.style.left = `${left}px`;
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h, x0: left };
}

function drawRuler() {
  const { ctx, w, h, x0 } = canvasSetup(rulerCv, rulerCv.parentElement);
  const laneX0 = x0; // canvas positioned at scrollLeft within lane coords
  const t0 = laneX0 / S.pps;
  const t1 = (laneX0 + w) / S.pps;
  // tick step: nice value ≥ 60px apart
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 64) || 300;
  // HyperFrames Studio ruler: full-height major lines at 10%, 8px minor ticks,
  // labels in 10px mono at +5px — a label hanging off its line, not centred on it
  ctx.font = '10px "JetBrains Mono", "IBM Plex Mono", ui-monospace, Consolas, monospace';
  ctx.fillStyle = 'rgba(255,255,255,0.34)';
  ctx.textBaseline = 'top';
  for (let t = Math.floor(t0 / step) * step; t <= t1; t += step) {
    if (t < 0) continue;
    const x = Math.round(t * S.pps - laneX0) + 0.5;
    ctx.strokeStyle = 'rgba(255,255,255,0.10)';
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.fillText(fmt(t), x + 5, 5);
    const minor = step / 5;
    ctx.strokeStyle = 'rgba(255,255,255,0.16)';
    for (let m = 1; m < 5; m++) {
      const xm = Math.round((t + m * minor) * S.pps - laneX0) + 0.5;
      ctx.beginPath();
      ctx.moveTo(xm, h - 8);
      ctx.lineTo(xm, h);
      ctx.stroke();
    }
  }
}

function drawWave() {
  if (!S.wave) return;
  const { ctx, w, h, x0 } = canvasSetup(waveCv, laneAudio);
  const mid = h / 2;
  // The mix reads as ONE audio clip, drawn the way HyperFrames Studio draws
  // audio: a violet pill spanning the cut, with pale bars inside it. The pill is
  // painted here (not as a DOM clip) because the canvas already covers exactly
  // the visible strip of the lane.
  const x1 = -x0;
  const x2 = draftTotal() * S.pps - x0;
  if (x2 > 0 && x1 < w) {
    const pad = 3;
    const r = Math.min(21, (h - pad * 2) / 2);
    ctx.beginPath();
    ctx.roundRect(x1 + 0.5, pad + 0.5, x2 - x1 - 1, h - pad * 2 - 1, r);
    ctx.fillStyle = 'rgba(167,139,250,0.16)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(167,139,250,0.4)';
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(245,237,255,0.72)';
  const pps = S.wave.peaksPerSec;
  for (let px = 0; px < w; px++) {
    const tDraft = (x0 + px) / S.pps;
    if (tDraft > draftTotal()) break;
    const tRend = draftToRendered(tDraft);
    const idx = Math.floor(tRend * pps);
    if (idx < 0 || idx >= S.wave.max.length) continue;
    const hi = (S.wave.max[idx] / 100) * (mid - 7);
    const lo = (S.wave.min[idx] / 100) * (mid - 7);
    ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
  }
}

// Vertical sources get the split layout (player right, editor left) — stacked,
// a 9:16 clip is tiny above a full-width timeline. Driven off the decoded frame
// size, so it works for cut.mp4 and the Phase-2 render alike.
function applyOrientation() {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return;
  const portrait = h > w;
  // From here the aspect is MEASURED. Before it, the body has no `portrait`
  // class and every project looks landscape — reconcileStyleWithAspect() then
  // snapped portrait-only picks away (measured 2026-11-03: a saved "scatter"
  // reopened as "karaoke" on a 1080×1920 cut). Snapping waits for this flag.
  const firstMeasure = !S.aspectKnown;
  S.aspectKnown = true;
  if (portrait === document.body.classList.contains('portrait')) {
    if (firstMeasure && S.style) renderSetup();
    return;
  }
  document.body.classList.toggle('portrait', portrait);
  syncLabelW(); // the header column is narrower in the portrait split
  // the timeline's width just changed — re-fit after layout settles.
  // renderSetup() too: the gate's layout mockups are drawn per aspect, and the
  // first frame usually decodes AFTER the tab has already been built once.
  // the gate is rebuilt NOW (DOM only); only the timeline fit waits for layout.
  // Inside the rAF it never ran in a pane that throttles frames (measured).
  if (S.style) renderSetup();
  requestAnimationFrame(() => { fitZoom(); renderAll(); });
}
video.addEventListener('loadedmetadata', applyOrientation);

// ---------- needle / playback sync ----------
function positionNeedle() {
  const tDraft = renderedToDraft(video.currentTime || 0);
  const x = LABEL_W + tDraft * S.pps;
  needle.style.left = `${x}px`;
  needle.style.visibility = x < panel.scrollLeft + LABEL_W ? 'hidden' : '';
  $('timeNow').textContent = fmt(tDraft);
  $('timeTotal').textContent = fmt(draftTotal() || S.videoDuration);
}
/* Live preview of an unrendered cut. The player plays the LAST RENDER; without
 * this, deleting a piece changed the drawing and nothing you could see or hear,
 * which reads as "I cut it and it didn't work". While playing, any rendered
 * moment the draft no longer keeps (a removed piece, a trimmed head or tail) is
 * jumped over, so the edit is audible and visible before any render. */
function nextKeptRendered(t) {
  const rl = renderedLayout();
  const dl = draftLayout();
  const t0 = t;
  for (let k = 0; k < rl.length; k++) {
    const a = rl[k].out;
    const b = a + rl[k].dur;
    if (t >= b - 1e-3) continue;
    const ps0 = renderedPictureStart(k);
    const src = ps0 + Math.max(0, t - a);
    const kept = dl.filter((d) => (d.ri ?? -1) === k && !d.removed)
      .map((d) => {
        const s = d.start + (d.g ? d.g.lead : 0);
        return [s, s + d.dur];
      })
      .sort((x, y) => x[0] - y[0]);
    for (const [s, e] of kept) {
      if (src < s - 1e-3) return a + (s - ps0); // jump forward to the next kept bit
      // inside kept material: play on — unless we only got here by skipping a
      // wholly removed take, in which case this IS the jump target
      if (src < e - 1e-3) return t > t0 + 1e-3 ? t : null;
    }
    // nothing kept after this point in take k → try the next take
    t = b;
  }
  return null;
}
function rafLoop() {
  if (capAnims.length) {
    const now = performance.now() / 1000;
    for (const step of capAnims) step(now);
  }
  if (!video.paused && !video.ended && cutChanged()) {
    const jump = nextKeptRendered(video.currentTime);
    if (jump != null && jump > video.currentTime + 0.02) video.currentTime = jump;
  }
  positionNeedle();
  if (!video.paused && !video.ended) {
    // keep needle visible
    const x = LABEL_W + renderedToDraft(video.currentTime) * S.pps;
    const right = panel.scrollLeft + panel.clientWidth;
    if (x > right - 80) panel.scrollLeft = x - panel.clientWidth * 0.25;
  }
  requestAnimationFrame(rafLoop);
}

function seekDraft(tDraft) {
  tDraft = Math.max(0, Math.min(tDraft, draftTotal() || S.videoDuration));
  video.currentTime = draftToRendered(tDraft);
  positionNeedle();
}

// ---------- Etapa 2: direct editing ----------
/* The editing model follows HyperFrames Studio (Apache-2.0, see NOTICE and
 * references/_hf-studio-inventory.md): Select (V) / Razor (B) tools, split at
 * the playhead (S), snap (N, 8px radius, playhead first), and a client-side
 * undo history. Everything below edits the DRAFT; saving is what writes files. */

// ---- undo / redo: whole-draft snapshots ----
function snapshot() {
  return JSON.stringify({ d: S.draft, i: S.insertsDraft, c: S.captions, n: S.notes });
}
function restore(snap) {
  const o = JSON.parse(snap);
  S.draft = o.d; S.insertsDraft = o.i; S.captions = o.c; S.notes = o.n;
  S.selected = -1; S.capSel = -1; S.chipSel = -1;
  renderAll(); refreshHeader();
}
function pushHist() {
  S.hist.push(snapshot());
  if (S.hist.length > 100) S.hist.shift();
  S.fut = [];
  updateToolbar();
}
function undo() {
  if (!S.hist.length) { toast('Nada para desfazer', 1400); return; }
  S.fut.push(snapshot());
  restore(S.hist.pop());
  updateToolbar();
}
function redo() {
  if (!S.fut.length) { toast('Nada para refazer', 1400); return; }
  S.hist.push(snapshot());
  restore(S.fut.pop());
  updateToolbar();
}

// ---- snapping (HyperFrames timelineSnapping: 8px, playhead > edges) ----
const SNAP_PX = 8;
function snapTargets(skip) {
  const out = [{ t: renderedToDraft(video.currentTime || 0), pri: 0 }];
  for (const d of draftLayout()) {
    if (d.removed) continue;
    out.push({ t: d.out, pri: 1 }, { t: d.out + d.dur, pri: 1 });
  }
  S.captions.forEach((c, k) => {
    if (skip === `cap${k}`) return;
    out.push({ t: renderedToDraft(c.start), pri: 1 }, { t: renderedToDraft(c.end), pri: 1 });
  });
  S.insertsDraft.forEach((c, i) => {
    if (skip === `chip${i}` || c.deleted) return;
    out.push({ t: c.start, pri: 1 }, { t: c.end, pri: 1 });
  });
  return out;
}
// Snap the nearer of the given edges; returns the shift to apply (0 = none).
function snapShift(edges, skip) {
  hideSnapGuide();
  if (!S.snap) return 0;
  const thr = SNAP_PX / S.pps;
  let best = null;
  for (const tg of snapTargets(skip)) {
    for (const e of edges) {
      const d = tg.t - e;
      if (Math.abs(d) > thr) continue;
      if (!best || tg.pri < best.pri || (tg.pri === best.pri && Math.abs(d) < Math.abs(best.d))) {
        best = { d, t: tg.t, pri: tg.pri };
      }
    }
  }
  if (!best) return 0;
  showSnapGuide(best.t, best.pri === 0);
  return best.d;
}
function showSnapGuide(t, onNeedle) {
  let g = $('snapGuide');
  if (!g) { g = el('div', 'snap-guide', timelineEl); g.id = 'snapGuide'; }
  g.style.left = `${LABEL_W + t * S.pps}px`;
  g.classList.toggle('on-needle', !!onNeedle);
  g.classList.remove('hidden');
}
function hideSnapGuide() { const g = $('snapGuide'); if (g) g.classList.add('hidden'); }

// ---- video: razor split ----
function clipAt(tDraft) {
  return draftLayout().findIndex((d) => !d.removed && tDraft > d.out + 0.04 && tDraft < d.out + d.dur - 0.04);
}
function splitClip(tDraft) {
  const i = clipAt(tDraft);
  if (i < 0) { toast('Posicione a agulha dentro de um clipe para dividir', 2000); return false; }
  pushHist();
  const d = draftLayout()[i];
  const r = S.draft[i];
  const g = r.g || { lead: 0, tail: 0 };
  const src = r.start + g.lead + (tDraft - d.out); // source time under the playhead
  // the left half keeps the lead (its audio still arrives early), the right half
  // keeps the measured tail trim; the new seam between them is a straight cut
  // each half's baseline is its own span, so trimming or deleting a half reads
  // as that edit — not as "the whole take changed"
  const left = { ...r, end: src, g: { lead: g.lead, tail: 0 }, orig: { start: r.start, end: src }, split: true };
  const right = { ...r, start: src, g: { lead: 0, tail: g.tail }, orig: { start: src, end: r.end }, split: true };
  S.draft.splice(i, 1, left, right);
  S.selected = i + 1;
  renderAll(); refreshHeader();
  return true;
}

// ---- captions ----
function capAt(tDraft) {
  return S.captions.findIndex((c) => tDraft >= renderedToDraft(c.start) && tDraft <= renderedToDraft(c.end));
}
function moveCaption(k, dt, base) {
  const c = S.captions[k];
  const shift = Math.max(dt, -base[0].startMs / 1000);
  c.words.forEach((w, j) => {
    w.startMs = base[j].startMs + shift * 1000;
    w.endMs = base[j].endMs + shift * 1000;
  });
  recapLine(c);
}
// Trimming a caption rescales its words inside the new span — the words keep
// their relative rhythm instead of the first or last one absorbing the change.
function trimCaption(k, side, t, base) {
  const c = S.captions[k];
  const a0 = base[0].startMs / 1000;
  const b0 = base[base.length - 1].endMs / 1000;
  let a = a0, b = b0;
  if (side === 'l') a = Math.min(Math.max(0, t), b0 - 0.15);
  else b = Math.max(t, a0 + 0.15);
  const k2 = (b - a) / Math.max(1e-6, b0 - a0);
  c.words.forEach((w, j) => {
    w.startMs = (a + (base[j].startMs / 1000 - a0) * k2) * 1000;
    w.endMs = (a + (base[j].endMs / 1000 - a0) * k2) * 1000;
  });
  recapLine(c);
}
function splitCaption(k, tDraft) {
  const c = S.captions[k];
  const t = draftToRendered(tDraft) * 1000;
  const cut = c.words.findIndex((w) => (w.startMs + w.endMs) / 2 >= t);
  if (c.words.length < 2 || cut <= 0) {
    toast('Esta legenda tem uma palavra só aqui — nada para dividir', 2000);
    return false;
  }
  pushHist();
  const right = recapLine({ words: c.words.slice(cut) });
  c.words = c.words.slice(0, cut);
  recapLine(c);
  S.captions.splice(k + 1, 0, right);
  S.capSel = k + 1;
  renderChips(); refreshHeader();
  return true;
}
function deleteCaption(k) {
  pushHist();
  S.captions.splice(k, 1);
  S.capSel = -1;
  renderChips(); refreshHeader();
}
// New text keeps the line's span; each word gets time in proportion to its
// length, the same rule a reader's eye follows.
function setCaptionText(k, text) {
  const c = S.captions[k];
  const toks = text.trim().split(/\s+/).filter(Boolean);
  if (!toks.length) { deleteCaption(k); return; }
  const a = c.words[0].startMs;
  const b = c.words[c.words.length - 1].endMs;
  const total = toks.reduce((s, w) => s + w.length + 1, 0);
  let acc = a;
  const words = toks.map((w) => {
    const d = ((w.length + 1) / total) * (b - a);
    const o = { text: w, startMs: acc, endMs: acc + d };
    acc += d;
    return o;
  });
  pushHist();
  c.words = words;
  recapLine(c);
  renderChips(); refreshHeader();
  scheduleAutosave();
}
function openCaptionEditor(k) {
  const chip = laneCaptions.querySelector(`.chip.caption[data-k="${k}"]`);
  if (!chip) return;
  const c = S.captions[k];
  const inp = el('input', 'cap-edit', laneCaptions);
  inp.value = c.words.map((w) => w.text).join(' ');
  inp.style.left = chip.style.left;
  inp.style.minWidth = `${Math.max(180, parseFloat(chip.style.width))}px`;
  inp.focus();
  inp.select();
  let done = false;
  const commit = (save) => {
    if (done) return;
    done = true;
    const v = inp.value;
    inp.remove();
    if (save && v.trim() !== c.words.map((w) => w.text).join(' ')) setCaptionText(k, v);
  };
  inp.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') commit(true);
    if (e.key === 'Escape') commit(false);
  });
  inp.addEventListener('blur', () => commit(true));
}

// ---- toolbar state ----
function setTool(t) {
  S.tool = t;
  panel.classList.toggle('razor', t === 'razor');
  updateToolbar();
}
function toggleSnap() {
  S.snap = !S.snap;
  localStorage.setItem('prisma.snap', S.snap ? '1' : '0');
  updateToolbar();
  toast(S.snap ? 'Snap ligado (N)' : 'Snap desligado (N)', 1200);
}
function updateToolbar() {
  const on = (id, v) => { const b = $(id); if (b) b.classList.toggle('on', !!v); };
  on('btnToolSelect', S.tool === 'select');
  on('btnToolRazor', S.tool === 'razor');
  on('btnSnap', S.snap);
  const u = $('btnUndo'); if (u) u.disabled = !S.hist.length;
  const r = $('btnRedo'); if (r) r.disabled = !S.fut.length;
}
// S: split whatever sits under the playhead — the selected caption if one is
// selected, otherwise the video clip (HyperFrames splits the selected clip)
function splitAtPlayhead() {
  const t = renderedToDraft(video.currentTime || 0);
  if (S.tab === 2 && S.capSel >= 0) { splitCaption(S.capSel, t); return; }
  splitClip(t);
}
function deleteSelection() {
  if (S.tab === 2 && S.capSel >= 0) { deleteCaption(S.capSel); scheduleAutosave(); return; }
  if (S.tab === 2 && S.chipSel >= 0) {
    const c = S.insertsDraft[S.chipSel];
    if (c.kind !== 'highlight') {
      toast('Para remover este elemento, marque o trecho (M) e peça no chat', 2600);
      return;
    }
    pushHist();
    c.deleted = true;
    S.chipSel = -1;
    renderChips(); refreshHeader(); scheduleAutosave();
    return;
  }
  if (S.selected >= 0) {
    pushHist();
    const r = S.draft[S.selected];
    r.removed = !r.removed;
    renderAll(); refreshHeader();
    // a keyboard cut is as final as a dragged one: save it too, so it reaches
    // the skill without a second click on "Salvar ajustes"
    scheduleAutosave();
    if (r.removed) toast('Trecho removido — o play já pula ele; salvando para renderizar', 2600);
  }
}

// ---------- interactions ----------
let drag = null;
// Autosave state — declared here, next to `drag`, because `let` is not hoisted
// and the pointerup handler above references it.
let autosaveTimer = null;
const AUTOSAVE_MS = 700; // {type:'scrub'|'trim'|'chip-trim'|'chip-move', ...}

panel.addEventListener('pointerdown', (e) => {
  // The gutter is chrome, not timeline. Without this guard a pointerdown on a
  // track icon fell through to the scrub branch below, which both yanked the
  // needle to 0 (the gutter is left of t=0, so it computes a negative time) and
  // called setPointerCapture on the panel — retargeting the following click and
  // swallowing it, so a real click on the A1/A2 disclosure never fired while a
  // programmatic .click() did.
  if (e.target.closest('.track-label') || e.target.closest('button')) return;

  if (e.target.closest('.cap-edit') || e.target.closest('.lvl-fader') || e.target.closest('.music-pick')) return;
  const handle = e.target.closest('.handle');
  const clip = e.target.closest('.clip');
  const chip = e.target.closest('.chip.insert');
  const cap = e.target.closest('.chip.caption');
  const capture = () => { try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ } };
  const tAt = (timelineEl.getBoundingClientRect(), (e.clientX - timelineEl.getBoundingClientRect().left - LABEL_W) / S.pps);
  const editTab = S.tab === 1 || S.tab === 2;

  // Razor: a click cuts whatever it lands on, at that exact point
  if (S.tool === 'razor' && editTab) {
    if (cap && S.tab === 2) { splitCaption(+cap.dataset.k, tAt); e.preventDefault(); return; }
    if (clip && !clip.classList.contains('removed')) {
      // ⇧+razor cuts every track at that time (HyperFrames): the take + the caption there
      splitClip(tAt);
      if (e.shiftKey && S.tab === 2) { const k = capAt(tAt); if (k >= 0) splitCaption(k, tAt); }
      e.preventDefault();
      return;
    }
  }

  if (handle && clip && editTab) {
    const i = +handle.dataset.i;
    pushHist();
    drag = { type: 'trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, r: { ...S.draft[i] } };
    capture(); e.preventDefault();
    return;
  }
  if (handle && cap && S.tab === 2) {
    const k = +handle.dataset.k;
    pushHist();
    S.capSel = k; S.chipSel = -1; S.selected = -1;
    drag = { type: 'cap-trim', k, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX,
             base: S.captions[k].words.map((w) => ({ ...w })) };
    capture(); e.preventDefault();
    return;
  }
  if (cap && S.tab === 2) {
    const k = +cap.dataset.k;
    pushHist();
    S.capSel = k; S.chipSel = -1; S.selected = -1;
    drag = { type: 'cap-move', k, x0: e.clientX, moved: false,
             base: S.captions[k].words.map((w) => ({ ...w })) };
    renderChips(); renderClips();
    capture(); e.preventDefault();
    return;
  }
  if (handle && chip && S.tab === 2) {
    const i = +handle.dataset.i;
    pushHist();
    S.chipSel = i; S.capSel = -1; S.selected = -1;
    drag = { type: 'chip-trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, c: { ...S.insertsDraft[i] } };
    capture(); e.preventDefault();
    return;
  }
  if (chip && S.tab === 2) {
    const i = +chip.dataset.i;
    pushHist();
    S.chipSel = i; S.capSel = -1; S.selected = -1;
    drag = { type: 'chip-move', i, x0: e.clientX, c: { ...S.insertsDraft[i] } };
    renderChips(); renderClips();
    capture(); e.preventDefault();
    return;
  }
  if (clip) {
    S.selected = +clip.dataset.i;
    S.capSel = -1; S.chipSel = -1;
    renderClips(); renderChips();
    return;
  }
  // empty space clears the selection before scrubbing
  if (S.selected >= 0 || S.capSel >= 0 || S.chipSel >= 0) {
    S.selected = -1; S.capSel = -1; S.chipSel = -1;
    renderClips(); renderChips();
  }
  // background / ruler → scrub
  const rect = timelineEl.getBoundingClientRect();
  const t = (e.clientX - rect.left - LABEL_W) / S.pps;
  drag = { type: 'scrub' };
  needle.classList.add('scrub'); // the diamond fills while it is being dragged
  seekDraft(t);
  try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
});

panel.addEventListener('pointermove', (e) => {
  if (!drag) return;
  if (drag.type === 'scrub') {
    const rect = timelineEl.getBoundingClientRect();
    seekDraft((e.clientX - rect.left - LABEL_W) / S.pps);
    return;
  }
  const dt = (e.clientX - drag.x0) / S.pps;

  if (drag.type === 'trim') {
    const r = S.draft[drag.i];
    if (drag.side === 'l') {
      r.start = Math.min(Math.max(0, drag.r.start + dt), r.end - MIN_SEG);
    } else {
      r.end = Math.max(drag.r.end + dt, r.start + MIN_SEG);
      const srcDur = (S.state.sourceDurations || {})[r.source];
      if (srcDur) r.end = Math.min(r.end, srcDur);
    }
    renderClips();
    drawWave();
    refreshHeader();
    const d = drag.side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
    showTooltip(e, `${fmt(r.start)} → ${fmt(r.end)} <span class="delta">(${d >= 0 ? '+' : ''}${d.toFixed(2)}s)</span>`);
  } else if (drag.type === 'chip-trim') {
    const c = S.insertsDraft[drag.i];
    const key = `chip${drag.i}`;
    if (drag.side === 'l') {
      let a = drag.c.start + dt;
      a += snapShift([a], key);
      c.start = Math.min(Math.max(0, a), c.end - 0.15);
    } else {
      let b = drag.c.end + dt;
      b += snapShift([b], key);
      c.end = Math.max(b, c.start + 0.15);
    }
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'chip-move') {
    const c = S.insertsDraft[drag.i];
    const dur = drag.c.end - drag.c.start;
    let a = drag.c.start + dt;
    a += snapShift([a, a + dur], `chip${drag.i}`) ;
    c.start = Math.max(0, a);
    c.end = c.start + dur;
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'cap-move') {
    if (Math.abs(e.clientX - drag.x0) < 3 && !drag.moved) return; // a click, not a drag
    drag.moved = true;
    // captions live in rendered time; with the cut untouched the two coincide
    const a0 = drag.base[0].startMs / 1000;
    const b0 = drag.base[drag.base.length - 1].endMs / 1000;
    let shift = dt;
    shift += snapShift([renderedToDraft(a0) + dt, renderedToDraft(b0) + dt], `cap${drag.k}`);
    moveCaption(drag.k, shift, drag.base);
    renderChips();
    refreshHeader();
    const c = S.captions[drag.k];
    showTooltip(e, `“${c.text}” ${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'cap-trim') {
    const edge = drag.side === 'l' ? drag.base[0].startMs : drag.base[drag.base.length - 1].endMs;
    let t = edge / 1000 + dt;
    t += snapShift([renderedToDraft(t)], `cap${drag.k}`);
    trimCaption(drag.k, drag.side, t, drag.base);
    renderChips();
    refreshHeader();
    const c = S.captions[drag.k];
    showTooltip(e, `“${c.text}” ${fmt(c.start)} → ${fmt(c.end)}`);
  }
});

['pointerup', 'pointercancel'].forEach((ev) =>
  panel.addEventListener(ev, () => {
    // A scrub moves the playhead and changes nothing about the edit, so it must
    // not trigger a save; a trim or a move must.
    // a caption press that never moved is a selection, not an edit: drop the
    // undo entry it pre-emptively pushed
    const clickOnly = drag && drag.type === 'cap-move' && !drag.moved;
    if (clickOnly) { S.hist.pop(); updateToolbar(); }
    const wasEdit = drag && drag.type !== 'scrub' && !clickOnly;
    drag = null;
    needle.classList.remove('scrub');
    hideTooltip();
    hideSnapGuide();
    if (wasEdit) scheduleAutosave();
  })
);

// double-click a clip = reset its edges (a split piece keeps its split)
laneVideo.addEventListener('dblclick', (e) => {
  const clip = e.target.closest('.clip');
  if (!clip) return;
  const r = S.draft[+clip.dataset.i];
  if (r.split) { toast('Clipe dividido — use Ctrl+Z para desfazer a divisão', 2200); return; }
  pushHist();
  r.start = r.orig.start; r.end = r.orig.end; r.removed = false;
  renderAll(); refreshHeader();
  scheduleAutosave(); // a reset is an edit like any other
});
// double-click a caption = edit its text in place
laneCaptions.addEventListener('dblclick', (e) => {
  const cap = e.target.closest('.chip.caption');
  if (cap && S.tab === 2) openCaptionEditor(+cap.dataset.k);
});

// keyboard
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'm' || e.key === 'M') {
    e.preventDefault();
    toggleMark();
    return;
  }
  if (e.key === 'Escape' && !$('helpModal').classList.contains('hidden')) {
    toggleHelp(false);
    return;
  }
  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault();
    toggleHelp($('helpModal').classList.contains('hidden'));
    return;
  }
  if (e.key === 'Escape' && S.pendingIn != null) {
    S.pendingIn = null;
    renderNotes();
    toast('IN cancelado', 1600);
    return;
  }
  const mod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();
  // HyperFrames Studio shortcuts (studioShortcuts.ts)
  if (mod && key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return; }
  if (mod && ((key === 'z' && e.shiftKey) || key === 'y')) { e.preventDefault(); redo(); return; }
  if (mod) return; // leave the browser's own shortcuts alone
  if (S.tab === 'style') return;
  if (key === 'v') { setTool('select'); return; }
  if (key === 'b') { setTool(S.tool === 'razor' ? 'select' : 'razor'); return; }
  if (key === 's') { e.preventDefault(); splitAtPlayhead(); return; }
  if (key === 'n') { toggleSnap(); return; }
  if (e.key === 'Escape' && S.tool === 'razor') { setTool('select'); return; }
  if (key === 'j' || key === 'k' || key === 'l') {
    // J/K/L: back a second / stop / play (the browser cannot play in reverse)
    if (key === 'k') video.pause();
    if (key === 'l') video.play();
    if (key === 'j') { video.pause(); seekDraft(renderedToDraft(video.currentTime) - 1); }
    return;
  }
  if (e.key === 'Home') { seekDraft(0); return; }
  if (e.key === 'End') { seekDraft(draftTotal()); return; }
  if (e.code === 'Space') {
    e.preventDefault();
    video.paused ? video.play() : video.pause();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = e.shiftKey ? 10 / S.fps : 1 / S.fps; // ⇧ = 10 frames, as in the Studio
    seekDraft(renderedToDraft(video.currentTime) + (e.key === 'ArrowRight' ? step : -step));
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault();
    deleteSelection();
  } else if (e.key === 'Enter' && S.tab === 2 && S.capSel >= 0) {
    openCaptionEditor(S.capSel);
  }
});

// transport
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
$('btnPlay').addEventListener('click', () => {
  video.paused ? video.play() : video.pause();
});
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; syncMusic(); });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; if (musicEl) musicEl.pause(); });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; if (musicEl) musicEl.pause(); });
// the video is the clock; the soundtrack follows it
video.addEventListener('seeked', () => { if (musicLive()) musicEl.currentTime = video.currentTime; });
video.addEventListener('ratechange', () => { if (musicEl) musicEl.playbackRate = video.playbackRate; });
video.addEventListener('volumechange', () => { if (musicEl) musicEl.muted = video.muted; });
setInterval(syncMusic, 500); // catches drift and any play/pause the events miss
$('btnMute').addEventListener('click', () => {
  video.muted = !video.muted;
  $('btnMute').innerHTML = video.muted ? ICON.mute : ICON.vol;
});
$('zoom').addEventListener('input', (e) => setZoom(+e.target.value));

// ---------- correction markers: button, chips, editor ----------
$('markIcon').innerHTML = ICON.flag;
$('btnMark').addEventListener('click', toggleMark);
$('laneNotes').addEventListener('click', (e) => {
  const chip = e.target.closest('.note-chip');
  if (chip) openNoteEditor(chip.dataset.id, false);
});
$('noteOk').addEventListener('click', () => {
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n) {
    n.text = $('noteText').value.trim();
    if (!n.text) { toast('Escreva o ajuste desejado', 2000); return; }
  }
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
});
$('noteDelete').addEventListener('click', () => {
  S.notes = S.notes.filter((x) => x.id !== S.editingNote);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
});
$('noteClose').addEventListener('click', closeNoteEditor);

// ---------- help modal (the old footer hint strip) ----------
function toggleHelp(open) {
  $('helpModal').classList.toggle('hidden', !open);
  $('helpBackdrop').classList.toggle('hidden', !open);
}
$('btnHelp').addEventListener('click', () => toggleHelp($('helpModal').classList.contains('hidden')));
$('helpClose').addEventListener('click', () => toggleHelp(false));
$('helpBackdrop').addEventListener('click', () => toggleHelp(false));
$('noteText').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeNoteEditor(); }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('noteOk').click(); }
});
// editing toolbar (HyperFrames layout: undo · redo | select · razor · split | snap)
$('btnUndo').innerHTML = ICON.undo;
$('btnRedo').innerHTML = ICON.redo;
$('btnToolSelect').innerHTML = ICON.select;
$('btnToolRazor').innerHTML = ICON.razor;
$('btnSplit').innerHTML = ICON.split;
$('btnSnap').innerHTML = ICON.snap;
$('btnUndo').addEventListener('click', undo);
$('btnRedo').addEventListener('click', redo);
$('btnToolSelect').addEventListener('click', () => setTool('select'));
$('btnToolRazor').addEventListener('click', () => setTool(S.tool === 'razor' ? 'select' : 'razor'));
$('btnSplit').addEventListener('click', splitAtPlayhead);
$('btnSnap').addEventListener('click', toggleSnap);
updateToolbar();
$('btnFit').innerHTML = ICON.fit;
$('btnZoomOut').innerHTML = ICON.zoomOut;
$('btnZoomIn').innerHTML = ICON.zoomIn;
$('btnFit').addEventListener('click', () => { fitZoom(); renderAll(); });
$('btnZoomOut').addEventListener('click', () => stepZoom(0.5));
$('btnZoomIn').addEventListener('click', () => stepZoom(2));
panel.addEventListener('scroll', () => requestAnimationFrame(() => { drawRuler(); drawWave(); positionNeedle(); }));
// renderSetup too: the caption demos bake their scale from the box width, so a
// resize (or the short-pane media query kicking in) has to rebuild them
window.addEventListener('resize', () => { fitZoom(); renderAll(); renderSetup(); });

// tabs
document.querySelectorAll('.tab').forEach((tab) =>
  tab.addEventListener('click', () => {
    if (tab.disabled) return;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    S.tab = tab.dataset.tab === 'style' || tab.dataset.tab === 'editor' ? tab.dataset.tab : +tab.dataset.tab;
    if (S.tab === 'editor') video.pause(); // the Studio has its own player
    S.selected = -1;
    updateVideoSrc(); // Fase 2 plays the Phase-2 render when available
    renderAll();
    renderSetup();
  })
);

// ---------- save / discard ----------
// One save path, two triggers: the button and the autosave that fires when a
// drag ends. Keeping them on the same function is the point — an autosave that
// took a shortcut would drift from what the button does and the two would stop
// agreeing about what "saved" means.
async function saveEdits() {
  const payload = { type: 'timeline-edits' };
  if (cutChanged()) {
    payload.edl = {
      // THE list, in order — splits and removals already applied, touching
      // pieces of one take merged. `removed` and `changes` explain it;
      // `ranges` is what to write into edl.json.
      ranges: effectiveRanges().map((r) => ({
        source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
      })),
      splits: S.draft.filter((r) => r.split).length,
      removed: S.draft.filter((r) => r.removed).map((r) => ({
        source: r.source, beat: r.beat,
        // a removed split piece is only that piece, not its whole original take
        start: r.split ? +r.start.toFixed(3) : r.orig.start,
        end: r.split ? +r.end.toFixed(3) : r.orig.end,
      })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  if (insertsDirty()) {
    payload.editData = {
      inserts: S.insertsDraft.filter((c) => c.kind === 'insert').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      splitInserts: S.insertsDraft.filter((c) => c.kind === 'split').map((c) => ({ ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      splitVideos: S.insertsDraft.filter((c) => c.kind === 'splitvideo').map((c) => ({ ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      hook: S.insertsDraft.filter((c) => c.kind === 'hook').map((c) => ({ endSec: +c.end.toFixed(3) }))[0] || null,
      behind: S.insertsDraft.filter((c) => c.kind === 'behind').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), dur: +(c.end - c.start).toFixed(3) })),
      wordAccents: S.insertsDraft.filter((c) => c.kind === 'word').map((c) => ({ ref: c.ref, text: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      highlights: S.insertsDraft.filter((c) => c.kind === 'highlight').map((c) => (c.deleted
        ? { ref: c.ref, delete: true }
        : { ref: c.ref, text: c.label, at: +c.start.toFixed(3), dur: +(c.end - c.start).toFixed(3) })),
    };
  }
  if (capsDirty()) {
    // the whole word list, as captions.json stores it — the server writes it
    // straight to the file, the same way it applies insert timings
    payload.captions = flatCaptions();
  }
  if (levelsDirty()) {
    // EXACT values, not rounded to a "nice" number: the fader is the decision,
    // and a mixer that saves 0.2 when you set 0.17 is lying about what you did.
    payload.editData = payload.editData || {};
    payload.editData.levels = {};
    LEVELS.forEach((l) => {
      const now = +levelValue(l.id).toFixed(3);
      payload.editData.levels[l.id] = {value: now, was: +levelBaseline(l.id).toFixed(3)};
    });
    // keep the old shape too — the skill already reads it
    payload.editData.soundtrack = {
      volume: +levelValue('music').toFixed(3),
      was: +levelBaseline('music').toFixed(3),
    };
  }
  if (S.notes.length) {
    // written in the draft timeline the user was actually looking at, plus the
    // rendered-timeline equivalent so the skill can find the spot in cut.mp4
    payload.notes = S.notes.map((n) => ({
      start: +n.start.toFixed(3),
      end: +n.end.toFixed(3),
      renderedStart: +draftToRendered(n.start).toFixed(3),
      renderedEnd: +draftToRendered(n.end).toFixed(3),
      phase: S.tab === 2 ? 2 : 1,
      text: n.text,
    }));
  }
  const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if ((await res.json()).ok) {
    S.savedPending = true;
    S.notes = [];
    S.pendingIn = null;
    S.draft.forEach((r) => { r.orig = { start: r.start, end: r.end }; r.split = false; if (r.removed) r.hardRemoved = true; });
    // keep visual state but clear dirty counters
    S.draft = S.draft.filter((r) => !r.removed);
    // the server drops deleted cards from the array, so every later card's ref
    // shifts down — mirror that or the next save would move the wrong card
    S.insertsDraft = S.insertsDraft.filter((c) => !c.deleted);
    S.insertsDraft.filter((c) => c.kind === 'highlight')
      .sort((a, b) => a.ref - b.ref)
      .forEach((c, n) => { c.ref = n; });
    S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
    S.capSig = JSON.stringify(flatCaptions());
    S.chipSel = -1;
    // saved values become the new baseline, so the faders stop reading dirty
    if (levelsDirty()) {
      S.levels = S.levels || {};
      LEVELS.forEach((l) => { S.levels[l.id] = levelValue(l.id); });
      S.musicVol = levelValue('music');
      if (S.editData) {
        S.editData.soundtrack = S.editData.soundtrack || {};
        S.editData.soundtrack.volume = S.musicVol;
        S.editData.voiceVolume = levelValue('voice');
        if (S.editData.captions) {
          S.editData.captions.sfx = S.editData.captions.sfx || {};
          S.editData.captions.sfx.clickVolume = levelValue('sfx');
        }
      }
    }
    renderAll(); refreshHeader();
    return true;
  }
  toast('Erro ao salvar — o servidor está de pé?', 4000);
  return false;
}

$('btnSave').addEventListener('click', () => saveEdits());

// ---------- autosave on drag end ----------
// A manual control that needs a second click on a separate button does not read
// as manual: you move the handle, the drawing moves, and nothing about the edit
// is actually recorded. So a finished drag saves itself.
//
// Debounced because a trim is rarely one gesture — you nudge an edge, look, nudge
// again. Firing per gesture would write the file three times and notify the agent
// three times for one decision.
function scheduleAutosave() {
  if (autosaveTimer) clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(async () => {
    autosaveTimer = null;
    if (dirtyCount() === 0) return;
    // A change to the CUT is not a Phase-2 re-render: it re-runs Phase 1
    // (render.py) and re-times every overlay, which the skill does. Kicking the
    // Phase-2 render here would just redraw the old cut.
    const cutWillChange = cutChanged();
    const ok = await saveEdits();
    if (!ok) return;
    if (cutWillChange) toast('Corte salvo — o Prisma aplica, recorta e renderiza de novo', 3600);
    else requestRender();
  }, AUTOSAVE_MS);
}

// ---------- auto re-render ----------
// Saving only updates the INSTRUCTION; the player shows a rendered file, so
// without this the timeline and the video disagree until someone re-renders by
// hand — which is exactly what "I moved it and nothing happened" looks like.
//
// The server runs one render at a time and lets a newer request supersede the
// running one, so a burst of nudges collapses into the last state rather than
// queueing several minutes of stale work.
async function requestRender() {
  try {
    await fetch('/api/render', { method: 'POST' });
    toast('Ajuste salvo — renderizando o vídeo…', 3200);
    pollRender();
  } catch (err) {
    toast('Ajuste salvo, mas o render não pôde ser iniciado', 4000);
  }
}

let renderPollTimer = null;
function pollRender() {
  if (renderPollTimer) return;
  renderPollTimer = setInterval(async () => {
    let st;
    try { st = await (await fetch('/api/render')).json(); } catch (err) { return; }
    setRenderPill(st);
    if (!st.running) {
      clearInterval(renderPollTimer);
      renderPollTimer = null;
      if (st.ok === false) {
        toast('O render falhou — veja o terminal do preview', 6000);
      } else if (st.ok) {
        toast('Vídeo atualizado', 3000);
        // the poll() loop notices the new mtime and reloads the player by itself
      }
    }
  }, 1500);
}

function setRenderPill(st) {
  let pill = $('renderPill');
  if (!pill) {
    const stale = $('stalePill');
    if (!stale || !stale.parentNode) return;
    pill = document.createElement('span');
    pill.id = 'renderPill';
    pill.className = 'pill stale';
    stale.parentNode.insertBefore(pill, stale);
  }
  pill.classList.toggle('hidden', !st.running);
  if (st.running) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - st.startedAt));
    pill.textContent = `⟳ Renderizando o vídeo… ${s}s`;
  }
}

$('btnDiscard').addEventListener('click', () => {
  pushHist(); // discarding is undoable too — it throws away real work
  S.draft = S.rendered.map((r, i) => ({
    ...r, ri: i, g: jcutGeom(i), removed: false, orig: { start: r.start, end: r.end },
  }));
  buildInsertsDraft();
  if (S.capSig) S.captions = groupCaptions(JSON.parse(S.capSig));
  S.capSel = -1;
  S.chipSel = -1;
  const st0 = S.editData && S.editData.soundtrack;
  if (st0 && st0.enabled) S.musicVol = st0.volume != null ? st0.volume : 0.1;
  S.notes = [];
  S.pendingIn = null;
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  S.selected = -1;
  renderAll(); refreshHeader();
  toast('Ajustes descartados', 2000);
});

// ---------- ui helpers ----------
function showTooltip(e, html) {
  tooltip.innerHTML = html;
  tooltip.style.left = `${e.clientX + 14}px`;
  tooltip.style.top = `${e.clientY - 34}px`;
  tooltip.classList.remove('hidden');
}
function hideTooltip() { tooltip.classList.add('hidden'); }
let toastTimer = null;
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}

// ---------- boot ----------
document.querySelectorAll('.tl-chip[data-icon]').forEach((c) => {
  c.innerHTML = ICON[c.dataset.icon] || '';
});

// A1/A2 accordion, folded into the audio track
$('jcutToggle').addEventListener('click', () => {
  if (!(S.jcut && S.jcut.length)) return;
  S.jcutOpen = !S.jcutOpen;
  localStorage.setItem('prisma.jcutOpen', S.jcutOpen ? '1' : '0');
  renderJcutAudio();
  updateScrollRange();
  positionNeedle();
});

poll();
rafLoop();
// the headline fit is MEASURED, so it is wrong until Poppins is actually
// loaded — rebuild once the fonts land
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { if (S.style) renderSetup(); });
}
