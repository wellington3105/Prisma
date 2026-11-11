"""Cinematic SFX kit, synthesised (our own sound — no third-party licence).

Cinema-dynamic edits lean on a small vocabulary: a sub swell (inhale), risers,
sub drops on the hits, whooshes on fast moves, reverse whooshes into a cut,
tiny relay/UI ticks for "something switched on / measured", a damped premium
door "TUM" with its latch, and a soft leather creak. All are built here from
sines, filtered noise and envelopes at 48 kHz stereo, peak-normalised so the
mix sets the level.

Usage:
  python helpers/sfx_synth.py -o assets/sfx_cinema            # whole kit (.wav)
  python helpers/sfx_synth.py -o kit --only sub_drop riser --riser-dur 2.0
  python helpers/sfx_synth.py --room-tone take1.mp4 take2.mp4 -o kit   # + room_tone.wav / cabin_tone.wav
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import subprocess
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
rng = np.random.default_rng(23)


def t_(d):
    return np.arange(int(d * SR)) / SR


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)


def sweep_filter(noise, f0, f1, d, q=0.6, shape=None):
    """noise through a band-pass whose centre moves f0→f1 (log), block-wise with crossfades."""
    n = len(noise); blk = 1024
    out = np.zeros(n)
    win = np.hanning(blk * 2)
    for s in range(0, n, blk):
        u = s / max(n - 1, 1)
        if shape is not None:
            u = shape(u)
        fc = f0 * (f1 / f0) ** u
        lo, hi = max(30, fc * (1 - q / 2)), min(SR / 2 - 100, fc * (1 + q / 2))
        seg = noise[max(0, s - blk // 2): s + blk * 2 - blk // 2]
        y = bp(seg, lo, hi)
        a = max(0, s - blk // 2)
        L = min(len(y), n - a, len(win))
        out[a:a + L] += y[:L] * win[:L]
    return out


def reverb(x, rt=0.35, mix=0.18):
    ir = rng.normal(0, 1, int(rt * SR)) * np.exp(-t_(rt) * 6.9 / rt)
    ir = lp(ir, 5000)
    wet = fftconvolve(x, ir)[: len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    return x + wet * mix * np.max(np.abs(x))


def stereo(x, pan_from=0.0, pan_to=0.0, width=0.0):
    p = np.linspace(pan_from, pan_to, len(x))
    l, r = x * np.sqrt((1 - p) / 2), x * np.sqrt((1 + p) / 2)
    if width > 0:
        d = int(0.011 * SR)
        r = (1 - width) * r + width * np.r_[np.zeros(d), r[:-d]]
    return np.stack([l, r], 1)


def norm(x, peak=0.89):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


# ---------------------------------------------------------------- the kit ----
def sub_swell(d=1.0):
    t = t_(d)
    env = (t / d) ** 2.2
    x = np.sin(2 * np.pi * (34 * t + 6 * t * t / d)) + 0.25 * lp(rng.normal(0, 1, len(t)), 90)
    return stereo(x * env)


def sub_drop(d=1.6):
    t = t_(d)
    f = 35 + 30 * np.exp(-t * 3.5)                                  # 65 → 35 Hz
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6)
    knock = lp(rng.normal(0, 1, len(t)), 180) * np.exp(-t * 28) * 0.9
    click = hp(rng.normal(0, 1, len(t)), 2500) * np.exp(-t * 160) * 0.35
    air = bp(rng.normal(0, 1, len(t)), 3000, 12000) * np.exp(-t * 4.0) * 0.12  # short cymbal-like tail
    x = boom * 1.0 + knock + click + air
    return stereo(x, width=0.35)


def riser(d=1.7):
    t = t_(d)
    n = rng.normal(0, 1, len(t))
    x = sweep_filter(n, 300, 7000, d, q=0.9, shape=lambda u: u ** 1.6)
    tone = np.sin(2 * np.pi * np.cumsum(180 * (4.0 ** (t / d))) / SR) * 0.15
    env = (t / d) ** 2.0
    return stereo((x / (np.max(np.abs(x)) + 1e-9) + tone) * env, -0.3, 0.3, width=0.5)


def whoosh(d=0.5, f_peak=2200, pan=(-0.7, 0.7)):
    t = t_(d)
    n = rng.normal(0, 1, len(t))
    bell = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2.5
    x = sweep_filter(n, 500, f_peak, d, q=1.1, shape=lambda u: np.sin(np.pi * u))
    return stereo(x * bell, *pan, width=0.4)


def whoosh_reverse(d=0.47):
    w = whoosh(d * 1.3, 2600, (0.5, -0.5))
    w = w[::-1]
    w = w[-int(d * SR):]
    env = np.linspace(0.2, 1, len(w)) ** 2
    return w * env[:, None]


def tick_relay():
    t = t_(0.06)
    x = np.sin(2 * np.pi * 2300 * t) * np.exp(-t * 180) + hp(rng.normal(0, 1, len(t)), 3000) * np.exp(-t * 400) * 0.6
    return stereo(x)


def ui_tick():
    t = t_(0.05)
    x = np.sin(2 * np.pi * 3600 * t) * np.exp(-t * 120) * (1 - np.exp(-t * 3000))
    return stereo(x)


def door_tum():
    t = t_(0.9)
    thud = (np.sin(2 * np.pi * 68 * t) + 0.5 * np.sin(2 * np.pi * 131 * t)) * np.exp(-t * 14)
    body = lp(rng.normal(0, 1, len(t)), 260) * np.exp(-t * 22) * 1.2
    latch = np.zeros(len(t))
    s = int(0.018 * SR)
    lt = t_(0.04)
    latch[s:s + len(lt)] = (hp(rng.normal(0, 1, len(lt)), 1800) * np.exp(-lt * 220) * 0.35
                            + np.sin(2 * np.pi * 1450 * lt) * np.exp(-lt * 160) * 0.25)
    x = reverb(thud + body + latch, rt=0.28, mix=0.12)
    return stereo(x, width=0.2)


def leather_creak(d=0.7):
    t = t_(d)
    x = np.zeros(len(t))
    pos = np.sort(rng.uniform(0.05, d - 0.05, 46))
    for p in pos:
        g = t_(0.012)
        s = int(p * SR)
        burst = bp(rng.normal(0, 1, len(g)), 700, 2600) * np.hanning(len(g))
        x[s:s + len(g)] += burst[: len(x) - s] * rng.uniform(0.3, 1.0)
    env = np.sin(np.pi * t / d) ** 0.8
    return stereo(x * env)


# --- Kit "audível no celular" (2026-10-30, projeto Volvo XC60) -------------
# O sub_drop vive abaixo de 80 Hz e o ui_tick dura 50ms: no alto-falante de
# celular — onde Reels é ouvido — o primeiro some e o segundo vira um estalo
# que ninguém registra. Estes têm energia na faixa que o celular reproduz
# (150 Hz–8 kHz) e duração para serem percebidos sem disputar com a fala.

def impact(d=1.1):
    """Pancada para abertura/drop. O grave é REFORÇADO por harmônicos (tanh), que
    é o que um alto-falante pequeno consegue tocar — o ouvido reconstrói o
    fundamental a partir deles (fundamental ausente)."""
    t = t_(d)
    f = 48 + 52 * np.exp(-t * 9)                                    # 100 → 48 Hz
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5)
    thump = np.tanh(thump * 2.6) * 0.8                              # harmônicos 100–300 Hz
    body = bp(rng.normal(0, 1, len(t)), 120, 700) * np.exp(-t * 18) * 0.7
    crack = hp(rng.normal(0, 1, len(t)), 2200) * np.exp(-t * 90) * 0.45
    x = reverb(thump + body + crack, rt=0.45, mix=0.16)
    return stereo(x, width=0.3)


def glass_ping(d=1.6, f0=1318.5):
    """Sino de vidro: parciais inarmônicos (razões de barra/sino), cada um com seu
    decaimento, mais um brilho de ar. Combina com a moldura prisma entrando."""
    t = t_(d)
    x = np.zeros(len(t))
    for ratio, amp, dec in ((1.0, 1.0, 3.2), (2.76, 0.55, 4.5), (5.40, 0.32, 6.5), (8.93, 0.18, 9.0)):
        ph = rng.uniform(0, 2 * np.pi)
        x += amp * np.sin(2 * np.pi * f0 * ratio * t + ph) * np.exp(-t * dec)
    x *= 1 - np.exp(-t * 900)                                       # ataque sem clique
    shimmer = bp(rng.normal(0, 1, len(t)), 6000, 12000) * np.exp(-t * 7) * 0.10
    x = reverb(x + shimmer, rt=0.9, mix=0.28)
    return stereo(x, -0.15, 0.15, width=0.55)


def whoosh_air(d=0.45):
    """Whoosh com corpo (banda baixa) + ar (banda alta) cruzando o estéreo."""
    t = t_(d)
    bell = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2.0
    n = rng.normal(0, 1, len(t))
    hi = sweep_filter(n, 900, 5200, d, q=1.0, shape=lambda u: np.sin(np.pi * u))
    lo = sweep_filter(rng.normal(0, 1, len(t)), 180, 700, d, q=0.8, shape=lambda u: np.sin(np.pi * u)) * 0.6
    return stereo((hi + lo) * bell, -0.8, 0.8, width=0.5)


def whip_hit(d=0.32):
    """Golpe de whip-pan: whoosh muito curto e agudo que termina num estalo."""
    t = t_(d)
    w = sweep_filter(rng.normal(0, 1, len(t)), 1500, 7000, d, q=1.2, shape=lambda u: u ** 0.7)
    env = (t / d) ** 1.5
    snap = np.zeros(len(t)); k = int(0.008 * SR)
    snap[-k:] = hp(rng.normal(0, 1, k), 3000) * np.linspace(1, 0, k)
    return stereo(w * env + snap * 0.8, 0.7, -0.7, width=0.4)


def riser_tonal(d=1.6):
    """Riser que SOBE de tom e corta seco — termina exatamente na batida."""
    t = t_(d)
    f = 220 * (4.0 ** (t / d))
    tone = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR)) * 0.35
    air = sweep_filter(rng.normal(0, 1, len(t)), 500, 9000, d, q=0.9, shape=lambda u: u ** 1.4)
    air = air / (np.max(np.abs(air)) + 1e-9)
    env = (t / d) ** 2.2
    env[-int(0.006 * SR):] *= np.linspace(1, 0, int(0.006 * SR))
    return stereo((tone + air) * env, -0.3, 0.3, width=0.5)


KIT = {"sub_swell": sub_swell, "sub_drop": sub_drop, "riser": riser,
       "whoosh_short": lambda: whoosh(0.5, 2200), "whoosh_wide": lambda: whoosh(0.95, 1600, (-0.9, 0.9)),
       "whoosh_reverse": whoosh_reverse, "tick_relay": tick_relay, "ui_tick": ui_tick,
       "door_tum": door_tum, "leather_creak": leather_creak,
       "impact": impact, "glass_ping": glass_ping, "whoosh_air": whoosh_air,
       "whip_hit": whip_hit, "riser_tonal": riser_tonal}


def write_wav(p: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(x.shape[1] if x.ndim == 2 else 1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def room_tone(takes: list[Path], out_dir: Path) -> None:
    """Showroom ambience from the takes' own audio (diegetic), + a muffled cabin variant."""
    chunks = []
    for p in takes:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"],
                             capture_output=True).stdout
        a = np.frombuffer(raw, "<i2").reshape(-1, 2).astype(np.float32) / 32768
        if len(a) > SR and np.sqrt((a ** 2).mean()) > 1e-4:
            # the quietest 70 % of the take = ambience (handling noise / speech excluded)
            blk = SR // 10
            e = np.array([np.sqrt((a[i:i + blk] ** 2).mean()) for i in range(0, len(a) - blk, blk)])
            keep = np.where(e <= np.quantile(e, 0.7))[0]
            chunks += [a[i * blk:(i + 1) * blk] for i in keep]
    if not chunks:
        print("room tone: no usable audio in the takes"); return
    xf = int(0.01 * SR)
    out = chunks[0]
    for c in chunks[1:]:
        fade = np.linspace(0, 1, xf)[:, None]
        out = np.vstack([out[:-xf], out[-xf:] * (1 - fade) + c[:xf] * fade, c[xf:]])
    out = np.stack([hp(out[:, c], 35) for c in range(2)], 1)
    write_wav(out_dir / "room_tone.wav", norm(out, 0.5))
    cab = np.stack([lp(out[:, c], 240, 4) for c in range(2)], 1)
    write_wav(out_dir / "cabin_tone.wav", norm(cab, 0.5))
    print(f"room_tone.wav / cabin_tone.wav: {len(out) / SR:.1f} s from {len(takes)} takes")


def main() -> None:
    ap = argparse.ArgumentParser(description="Synthesised cinematic SFX kit")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--riser-dur", type=float, default=1.7)
    ap.add_argument("--room-tone", type=Path, nargs="*")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for name, fn in KIT.items():
        if a.only and name not in a.only:
            continue
        x = riser(a.riser_dur) if name == "riser" else fn()
        write_wav(a.out / f"{name}.wav", norm(x))
    print(f"kit → {a.out} ({', '.join(n for n in KIT if not a.only or n in a.only)})")
    if a.room_tone:
        room_tone(a.room_tone, a.out)


if __name__ == "__main__":
    main()
