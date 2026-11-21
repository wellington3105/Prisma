/* prisma-eases.js: the 12 measured eases of motionmaxxing, as named GSAP eases.
 *
 * Source: github.com/Tejashmakwana/motionmaxxing @ 8c8ec0f2a6f6c9a0da15cd24f7b1298ab298368c
 * runtime/motion.js lines 18-41 (Apache-2.0, Copyright Tejas Makwana). The math is copied
 * verbatim. See helpers/vendor/motionmaxxing/PROVENANCE.md.
 *
 * Each curve was fitted to the median of real moves measured frame by frame in 53
 * professional motion moments (n = 3,573 moves; 89 % lie within 0.12 of one curve).
 * The table of shapes, frame counts and uses is in references/motion-craft.md §2.1.
 *
 * Use: load after gsap.min.js, then  ease: "softLand"  in any tween, or call
 * PrismaEase.fn.softLand(t) directly (for example in a Remotion interpolate easing).
 * PrismaEase.frames.<name> is the measured median duration in frames at 30 fps.
 *
 * Seek-safe: every curve is a pure function of t, with f(0) = 0 and f(1) = 1.
 * This file is separate from prisma-hf.js on purpose. prisma-hf.js is held to
 * Remotion parity (hf_parity.py); these curves are for NEW motion only.
 */
(function (root) {
  'use strict';
  var powerOut = function (p) { return function (t) { return 1 - Math.pow(1 - t, p); }; };
  var powerIn = function (p) { return function (t) { return Math.pow(t, p); }; };
  var expoOut = function (k) { var d = 1 - Math.exp(-k); return function (t) { return (1 - Math.exp(-k * t)) / d; }; };
  var snapRamp = function (w, tau) { var n = w * (1 - Math.exp(-1 / tau)) + (1 - w); return function (t) { return (w * (1 - Math.exp(-t / tau)) + (1 - w) * t) / n; }; };
  var snapOver = function (A, ta, td) { var f = function (t) { return (1 + A * Math.exp(-t / td)) * (1 - Math.exp(-t / ta)); }; var n = f(1); return function (t) { return f(t) / n; }; };
  var spring = function (c, om) { var f = function (t) { return 1 - Math.exp(-c * t) * (Math.cos(om * t) + (c / om) * Math.sin(om * t)); }; var n = f(1); return function (t) { return f(t) / n; }; };
  var smoothP = function (p) { return function (t) { var a = Math.pow(t, p), b = Math.pow(1 - t, p); return a / (a + b); }; };
  var guard = function (f) { return function (t) { return t <= 0 ? 0 : t >= 1 ? 1 : f(t); }; };

  var fn = {
    crashIn: guard(snapOver(2.0, 0.19, 0.218)),  // hits and passes its mark at once (peak 1.18 at t~.27)
    popOver: guard(spring(2.67, 4.36)),          // slow late overshoot, 1.08 at t~.72
    bounceHard: guard(spring(1.34, 5.07)),       // big overshoot 1.48: use sparingly
    snapSettle: guard(snapRamp(0.942, 0.118)),   // hero / CTA entry: 54 % of travel in the first 10 % of time
    softLand: guard(expoOut(3.41)),              // firm decelerate: the workhorse for text and panels
    whip: guard(powerOut(2.52)),                 // hard decelerating big move
    glide: guard(powerOut(1.7)),                 // gentle ease-out for medium moves
    cruise: guard(function (t) { return t; }),   // linear: fades, drifts, counters
    softInOut: guard(smoothP(1.42)),             // symmetric S for opacity / blur
    gentleIn: guard(powerIn(2.07)),              // mild acceleration
    accelExit: guard(powerIn(2.6)),              // the leaving curve
    crashOut: guard(powerIn(3.97))               // hard acceleration into a cut
  };
  var frames = { crashIn: 10, popOver: 15, bounceHard: 22, snapSettle: 11, softLand: 12, whip: 7, glide: 10, cruise: 9, softInOut: 9, gentleIn: 9, accelExit: 13, crashOut: 17 };

  root.PrismaEase = { fn: fn, frames: frames, names: Object.keys(fn) };
  if (root.gsap && typeof root.gsap.registerEase === 'function') {
    Object.keys(fn).forEach(function (k) { root.gsap.registerEase(k, fn[k]); });
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = root.PrismaEase;
})(typeof window !== 'undefined' ? window : globalThis);
