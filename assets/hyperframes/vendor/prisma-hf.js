/* prisma-hf.js — the Remotion math of the Prisma templates, ported 1:1 for HyperFrames.
 *
 * Why this file exists: the Phase-2 layers were designed (and approved, frame by
 * frame) in Remotion. A HyperFrames layer is only "ported" when it draws the SAME
 * picture from the SAME edit-data.json (hf_parity.py, SSIM >= 0.95 in the layer's
 * box). Re-deriving each curve as a GSAP ease drifts; porting `interpolate`,
 * `spring` and `Easing` verbatim does not. Each layer is a GSAP tween on a proxy
 * whose onUpdate draws frame `f` — the pattern HyperFrames documents for charts
 * (references/runtimes.md): everything is a function of timeline time, seekable.
 *
 * Sources (remotion 4.0.482): spring/spring-utils.js, spring/measure-spring.js,
 * spring/index.js, interpolate.js, easing.js, bezier.js. Layer math: the Prisma
 * templates (assets/{shortform,longform}/src/*.tsx) — keep the two in step.
 */
(function () {
  'use strict';
  var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(hi, v)); };

  // ---------- Easing (remotion/src/easing.ts) ----------
  var NEWTON_ITERATIONS = 4, NEWTON_MIN_SLOPE = 0.001, SUBDIVISION_PRECISION = 0.0000001,
    SUBDIVISION_MAX_ITERATIONS = 10, kSplineTableSize = 11, kSampleStepSize = 1.0 / (kSplineTableSize - 1.0);
  function A(a1, a2) { return 1.0 - 3.0 * a2 + 3.0 * a1; }
  function B(a1, a2) { return 3.0 * a2 - 6.0 * a1; }
  function C(a1) { return 3.0 * a1; }
  function calcBezier(t, a1, a2) { return ((A(a1, a2) * t + B(a1, a2)) * t + C(a1)) * t; }
  function getSlope(t, a1, a2) { return 3.0 * A(a1, a2) * t * t + 2.0 * B(a1, a2) * t + C(a1); }
  function bezier(mX1, mY1, mX2, mY2) {
    var sv = new Float32Array(kSplineTableSize);
    if (mX1 !== mY1 || mX2 !== mY2) for (var i = 0; i < kSplineTableSize; ++i) sv[i] = calcBezier(i * kSampleStepSize, mX1, mX2);
    function getTForX(aX) {
      var start = 0.0, cur = 1, last = kSplineTableSize - 1;
      for (; cur !== last && sv[cur] <= aX; ++cur) start += kSampleStepSize;
      --cur;
      var dist = (aX - sv[cur]) / (sv[cur + 1] - sv[cur]);
      var guess = start + dist * kSampleStepSize;
      var slope = getSlope(guess, mX1, mX2);
      if (slope >= NEWTON_MIN_SLOPE) {
        for (var n = 0; n < NEWTON_ITERATIONS; ++n) {
          var s = getSlope(guess, mX1, mX2);
          if (s === 0.0) return guess;
          guess -= (calcBezier(guess, mX1, mX2) - aX) / s;
        }
        return guess;
      }
      if (slope === 0.0) return guess;
      var aA = start, aB = start + kSampleStepSize, cx, ct, k = 0;
      do {
        ct = aA + (aB - aA) / 2.0;
        cx = calcBezier(ct, mX1, mX2) - aX;
        if (cx > 0.0) aB = ct; else aA = ct;
      } while (Math.abs(cx) > SUBDIVISION_PRECISION && ++k < SUBDIVISION_MAX_ITERATIONS);
      return ct;
    }
    return function (x) {
      var cX = Math.min(1, Math.max(0, x));
      if (mX1 === mY1 && mX2 === mY2) return cX;
      if (cX === 0) return 0;
      if (cX === 1) return 1;
      return calcBezier(getTForX(cX), mY1, mY2);
    };
  }
  var Easing = {
    linear: function (t) { return t; },
    cubic: function (t) { return t * t * t; },
    back: function (s) { if (s === undefined) s = 1.70158; return function (t) { return t * t * ((s + 1) * t - s); }; },
    out: function (f) { return function (t) { return 1 - f(1 - t); }; },
    bezier: bezier,
  };

  // ---------- interpolate (remotion/src/interpolate.ts; clamp / extend only) ----------
  function interpolate(input, inR, outR, o) {
    o = o || {};
    var easing = o.easing || Easing.linear;
    var el = o.extrapolateLeft || 'extend', er = o.extrapolateRight || 'extend';
    var i = 1;
    for (; i < inR.length - 1; ++i) if (inR[i] >= input) break;
    var r = i - 1;
    var iMin = inR[r], iMax = inR[r + 1], oMin = outR[r], oMax = outR[r + 1];
    var x = input;
    if (x < iMin) { if (el === 'clamp') x = iMin; }
    if (x > iMax) { if (er === 'clamp') x = iMax; }
    if (oMin === oMax) return oMin;
    x = (x - iMin) / (iMax - iMin);
    x = easing(x);
    return x * (oMax - oMin) + oMin;
  }
  var CL = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
  function clampI(f, a, b, c, d, easing) {
    return interpolate(f, [a, b], [c, d], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easing});
  }

  // ---------- spring (remotion/src/spring/*) ----------
  var DEF = {damping: 10, mass: 1, stiffness: 100, overshootClamping: false};
  function advance(an, now, cfg) {
    var dt = Math.min(now - an.lastTimestamp, 64);
    var c = cfg.damping, m = cfg.mass, k = cfg.stiffness;
    var v0 = -an.velocity, x0 = an.toValue - an.current;
    var zeta = c / (2 * Math.sqrt(k * m)), w0 = Math.sqrt(k / m), w1 = w0 * Math.sqrt(1 - zeta * zeta);
    var t = dt / 1000, s1 = Math.sin(w1 * t), c1 = Math.cos(w1 * t);
    var uEnv = Math.exp(-zeta * w0 * t);
    var uF = uEnv * (s1 * ((v0 + zeta * w0 * x0) / w1) + x0 * c1);
    var uPos = an.toValue - uF;
    var uVel = zeta * w0 * uF - uEnv * (c1 * (v0 + zeta * w0 * x0) - w1 * x0 * s1);
    var cEnv = Math.exp(-w0 * t);
    var cPos = an.toValue - cEnv * (x0 + (v0 + w0 * x0) * t);
    var cVel = cEnv * (v0 * (t * w0 - 1) + t * x0 * w0 * w0);
    return {toValue: an.toValue, prevPosition: an.current, lastTimestamp: now,
      current: zeta < 1 ? uPos : cPos, velocity: zeta < 1 ? uVel : cVel};
  }
  function springCalc(frame, fps, config) {
    var cfg = Object.assign({}, DEF, config || {});
    var an = {lastTimestamp: 0, current: 0, toValue: 1, velocity: 0, prevPosition: 0};
    var fc = Math.max(0, frame), rest = fc % 1;
    for (var f = 0; f <= Math.floor(fc); f++) {
      if (f === Math.floor(fc)) f += rest;
      an = advance(an, (f / fps) * 1000, cfg);
    }
    return an;
  }
  var _measure = {};
  function measureSpring(fps, config, threshold) {
    if (threshold === undefined) threshold = 0.005;
    var key = [fps, config.damping, config.mass, config.overshootClamping, config.stiffness, threshold].join('-');
    if (_measure[key] !== undefined) return _measure[key];
    var frame = 0, finished = 0, an = springCalc(frame, fps, config);
    var diff = Math.abs(an.current - an.toValue);
    while (diff >= threshold) { frame++; an = springCalc(frame, fps, config); diff = Math.abs(an.current - an.toValue); }
    finished = frame;
    for (var i = 0; i < 20; i++) {
      frame++; an = springCalc(frame, fps, config); diff = Math.abs(an.current - an.toValue);
      if (diff >= threshold) { i = 0; finished = frame + 1; }
    }
    _measure[key] = finished;
    return finished;
  }
  function spring(o) {
    var config = o.config || {}, from = o.from === undefined ? 0 : o.from, to = o.to === undefined ? 1 : o.to;
    var dur = o.durationInFrames, delay = o.delay || 0;
    var natural = dur !== undefined ? measureSpring(o.fps, config, o.durationRestThreshold) : undefined;
    var delayed = o.frame - delay;
    var processed = dur === undefined ? delayed : delayed / (dur / natural);
    if (dur && delayed > dur) return to;
    var cur = springCalc(processed, o.fps, config).current;
    var inner = config.overshootClamping ? (to >= from ? Math.min(cur, to) : Math.max(cur, to)) : cur;
    return from === 0 && to === 1 ? inner : interpolate(inner, [0, 1], [from, to]);
  }

  // ---------- driver ----------
  // One tween per layer instance: a proxy runs 0..total frames; draw(f) paints frame f.
  // f is an integer because HyperFrames samples at exactly k/fps (measured on
  // 0.8.93: probe ramp, 2026-11-08) and clip starts carry a 0.1 ms lead.
  // `off`: the clip starts `off` frames into the layer's life (a layer whose first
  // frame is invisible starts one frame late so its <video> needs no media offset:
  // that is how the Remotion VIDEO_LAG is reproduced without a negative seek).
  function drive(tl, fps, total, draw, off) {
    off = off || 0;
    var p = {f: off};
    draw(off);
    tl.to(p, {f: total, duration: (total - off) / fps, ease: 'none', onUpdate: function () { draw(Math.round(p.f)); }}, 0);
    return tl;
  }
  var $ = function (id) { return document.getElementById(id); };

  // ---------- layers ----------
  var easeOutCubic = Easing.out(Easing.cubic);
  var L = {};

  // 16:9 karaoke (longform/src/Captions.tsx LineEl + WordEl)
  L.karaokeLong = function (tl, o) {
    var slide = Easing.bezier(0.25, 1, 0.5, 1), SLIDE = 15;
    function shiftAt(frame) {
      var from = o.targets[0], to = o.targets[0], t0 = 0;
      var pos = function (t) { return from + (to - from) * slide(Math.min(1, Math.max(0, (t - t0) / SLIDE))); };
      for (var j = 1; j < o.starts.length; j++) {
        if (frame < o.starts[j]) break;
        var cur = pos(o.starts[j]);
        from = cur; to = o.targets[j]; t0 = o.starts[j];
      }
      return pos(frame);
    }
    var line = $(o.id), words = o.words.map($);
    return drive(tl, o.fps, o.total, function (f) {
      line.style.translate = (shiftAt(f) * o.fit) + 'px 0px';
      for (var j = 0; j < words.length; j++) {
        var s = o.starts[j], e = o.ends[j];
        var p = clampI(f, s, s + 7, 0, 1, easeOutCubic);
        words[j].style.opacity = p;
        words[j].style.translate = '0px ' + interpolate(p, [0, 1], [o.size * 0.5, 0]) + 'px';
        if (o.highlight) words[j].style.color = (f >= s && f < e) ? o.highlight : 'white';
      }
    }, o.off);
  };

  // 9:16 karaoke (shortform/src/Main.tsx Karaoke + Word + CaptionShell)
  L.karaokeShort = function (tl, o) {
    var shell = $(o.shell), words = o.words.map($);
    return drive(tl, o.fps, o.total, function (f) {
      var g = o.from + f, pb = o.paddingBottom;
      for (var i = 0; i < o.windows.length; i++) {
        var w = o.windows[i];
        if (g >= w[0] && g < w[1]) { pb = w[2]; break; }
      }
      shell.style.paddingBottom = pb + 'px';
      for (var j = 0; j < words.length; j++) {
        var p = clampI(f, o.starts[j], o.starts[j] + 7, 0, 1, easeOutCubic);
        words[j].style.opacity = p;
        words[j].style.translate = '0px ' + interpolate(p, [0, 1], [34, 0]) + 'px';
      }
    }, o.off);
  };

  // headline (longform/src/Hook.tsx, shortform/src/Main.tsx HookInner): fade + rise
  L.hook = function (tl, o) {
    var el = $(o.id);
    return drive(tl, o.fps, o.total, function (f) {
      var enter = clampI(f, 0, 8, 0, 1, easeOutCubic);
      var exit = clampI(f, o.total - 9, o.total, 1, 0);
      el.style.opacity = Math.min(enter, exit);
      el.style.translate = '0px ' + interpolate(enter, [0, 1], [24 * o.k, 0]) + 'px';
    }, o.off);
  };

  // highlight card "prism" (GlassCard.tsx Prism)
  L.prism = function (tl, o) {
    var card = $(o.id), rim = $(o.id + '-rim'), s1 = $(o.id + '-s1'), s2 = $(o.id + '-s2');
    var total = o.total;
    var sweep = function (f, from, len) { return clampI(f, from, from + len, -140, 140); };
    return drive(tl, o.fps, total, function (f) {
      var enter = spring({frame: f, fps: o.fps, config: {damping: 14, mass: 0.6}, durationInFrames: 16});
      var exit = clampI(f, total - 9, total, 1, 0);
      var vis = Math.min(enter, exit);
      var drift = interpolate(f, [0, total], [0, 1], {extrapolateRight: 'clamp'});
      var rotY = -14 + drift * 8 - (1 - enter) * 24 + (1 - exit) * 18;
      var rotX = 7 - drift * 3 - (1 - enter) * 8;
      var scale = 0.86 + 0.14 * vis;
      card.style.transform = 'translate(-50%,-50%) rotateX(' + rotX + 'deg) rotateY(' + rotY + 'deg) rotateZ(' + o.tilt + 'deg) scale(' + scale + ')';
      card.style.opacity = vis;
      var ang = (f * 3.2) % 360;
      rim.style.background = 'conic-gradient(from ' + ang + 'deg, rgba(255,90,130,0.85), rgba(255,220,120,0.75), rgba(120,255,210,0.7), rgba(110,190,255,0.9), rgba(200,130,255,0.8), rgba(255,90,130,0.85))';
      s1.style.left = sweep(f, 5, 16) + '%';
      s2.style.left = sweep(f, Math.round(total * 0.55), 22) + '%';
    }, o.off);
  };

  // highlight card "pill" (GlassCard.tsx One)
  L.pill = function (tl, o) {
    var card = $(o.id), total = o.total;
    return drive(tl, o.fps, total, function (f) {
      var enter = spring({frame: f, fps: o.fps, config: {damping: 15, mass: 0.5}, durationInFrames: 11});
      var exit = clampI(f, total - 8, total, 1, 0);
      var vis = Math.min(enter, exit);
      var desliza = interpolate(enter, [0, 1], [22, 0], {extrapolateRight: 'clamp'});
      card.style.transform = 'translate(-50%,calc(-50% + ' + desliza + 'px)) scale(' + vis + ') rotate(' + o.tilt + 'deg)';
      card.style.opacity = vis;
    }, o.off);
  };

  // 16:9 B-roll cutaway (longform/src/Main.tsx BrollEl)
  L.brollLong = function (tl, o) {
    var el = $(o.id), img = o.image ? $(o.id + '-m') : null, total = o.total;
    return drive(tl, o.fps, total, function (f) {
      var inn = clampI(f, 0, 10, 0, 1), out = clampI(f, total - 10, total, 1, 0);
      var sp = o.spring ? spring({frame: f, fps: o.fps, config: {damping: 14, mass: 0.55}, durationInFrames: 14}) : null;
      el.style.opacity = sp === null ? Math.min(inn, out) : Math.min(clamp(sp, 0, 1), out);
      if (img) {
        var kb = interpolate(f, [0, total], [1, 1.06], {extrapolateRight: 'clamp'});
        var grow = sp === null ? kb : kb * interpolate(sp, [0, 1], [0.985, 1]);
        img.style.transform = 'scale(' + grow + ')';
      }
    }, o.off);
  };

  // 9:16 insert (shortform/src/Main.tsx InsertCard)
  L.insertShort = function (tl, o) {
    var el = $(o.id), total = o.total;
    return drive(tl, o.fps, total, function (f) {
      var sp = spring({frame: f, fps: o.fps, config: {damping: 14, mass: 0.55}, durationInFrames: 14});
      var cu = clampI(f, 0, 9, 0, 1, easeOutCubic);
      var enter = o.spring ? sp : cu;
      var exit = clampI(f, total - 7, total, 1, 0);
      var grow = interpolate(f, [0, total], [o.d0, o.d1], {extrapolateRight: 'clamp'});
      el.style.opacity = Math.min(enter, exit);
      el.style.scale = String(interpolate(enter, [0, 1], [o.full ? 0.985 : 0.92, 1]) * grow);
      el.style.translate = '0px ' + interpolate(enter, [0, 1], [o.full ? 10 : 26, 0]) + 'px';
    }, o.off);
  };

  // split screen: slow Ken-Burns of the art (Split.tsx / CustomGraphics.tsx SplitFrame)
  L.split = function (tl, o) {
    var art = $(o.id);
    return drive(tl, o.fps, o.total, function (f) {
      art.style.scale = String(1 + 0.03 * clamp(f / Math.max(1, o.total), 0, 1));
    }, o.off);
  };

  // ending fade to black (render_phase2 delivery: fade=t=out, linear)
  L.fade = function (tl, o) {
    var el = $(o.id);
    return drive(tl, o.fps, o.total, function (f) { el.style.opacity = clamp(f / Math.max(1, o.total), 0, 1); });
  };

  // A/V probe (build_hyperframes --sync-probe): a white square on each word onset
  L.syncProbe = function (tl, o) {
    var el = $(o.id);
    return drive(tl, o.fps, o.total, function (f) {
      var on = false;
      for (var i = 0; i < o.onsets.length; i++) if (f >= o.onsets[i] && f < o.onsets[i] + 2) { on = true; break; }
      el.style.opacity = on ? 1 : 0;
    }, o.off);
  };

  window.PrismaHF = {interpolate: interpolate, spring: spring, Easing: Easing, drive: drive, layers: L};
})();
