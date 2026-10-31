"""Entrega de um vídeo da Fase 2 com MIXAGEM de verdade: voz tratada + trilha com
ducking dinâmico + SFX + loudnorm em duas passadas → final.mp4.

Por que existe (projeto Volvo XC60, 2026-10-30): a entrega do render_phase2.py
re-mixa a voz do cut.mp4 crua, a trilha num volume FIXO e só os cliques de
transição. Numa gravação dentro de carro isso deu:
  - voz abafada e com ronco: energia 10–14 dB maior em 80–500 Hz do que em
    2–8 kHz (a faixa das consoantes) e só 8,5 dB entre fala e ruído na pausa;
  - trilha baixa demais sob a fala E baixa demais nas pausas (volume fixo não
    respira);
  - SFX que somem no celular (sub-drop < 80 Hz, tick de 50ms).

O que faz, na ordem:
  1. VOZ (cut.mp4, atrasada 1 frame = VIDEO_LAG): cadeia `--voice-chain`.
     Preset "noisy" (medido nessa gravação: fala/ruído na pausa 8,5 → 27 dB):
     afftdn → highpass 110 → −5 dB @240 (embolado) → +5 dB @3 kHz (presença) →
     +4 dB shelf 7 kHz (ar) → expansor (abaixa o ruído entre frases) →
     compressor 3:1 → de-esser → limiter. "clean" = só EQ+compressor+limiter.
  2. TRILHA: `soundtrack.raw` (a faixa SEM carve), começando em
     `soundtrack.offset` s (use beat_map.py para pôr o drop num corte), com
     ducking em DUAS camadas usando a voz tratada como chave:
       - banda 250–2200 Hz (onde a voz mora): ratio 10 — some sob a fala;
       - espectro inteiro: ratio 2.5 — a trilha recua de leve e volta cheia nas
         pausas, na abertura e no fecho.
     Isso substitui o volume fixo + carve offline; `soundtrack.volume` é o nível
     NAS PAUSAS (≈0.30), não sob a fala.
  3. SFX: `sfxCues` [{src, at, volume}] + o clique de cada `transitions[]`.
     `src` é procurado em <edit>/sfx_cinema, remotion/public/sfx, remotion/public.
  4. loudnorm −14 LUFS / −1 dBTP em DUAS passadas (a 1ª mede, a 2ª aplica
     linear) — passada única "bombeia" quando a trilha sobe nas pausas.

Uso:
    uv run python helpers/deliver_mix.py <edit_dir> [--voice-chain noisy|clean|"<filtros>"]
    uv run python helpers/deliver_mix.py <edit_dir> --stems    # grava voz/trilha/sfx separados para conferir
Lê remotion/out/render.mp4 (rode render_phase2.py antes) e grava <edit_dir>/final.mp4.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHAINS = {
    "noisy": ("afftdn=nr=20:nf=-34:tn=1,highpass=f=110,highpass=f=110,"
              "equalizer=f=240:t=q:w=1.1:g=-5,equalizer=f=3000:t=q:w=1.2:g=5,highshelf=f=7000:g=4,"
              "agate=threshold=0.035:ratio=2.5:range=0.2:attack=5:release=200:knee=4,"
              "acompressor=threshold=-22dB:ratio=3:attack=8:release=140:makeup=3,"
              "deesser=i=0.45,alimiter=limit=0.89"),
    "clean": ("highpass=f=80,equalizer=f=220:t=q:w=1.0:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
              "highshelf=f=9000:g=2,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2,"
              "deesser=i=0.35,alimiter=limit=0.89"),
}


def pcm(src: Path, af: str | None, ss: float, t: float) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", str(src)]
    cmd += (["-af", af] if af else []) + ["-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).copy()


def lufs(src: Path, af: str | None, ss: float, t: float) -> float:
    """Loudness integrado (EBU R128) de um trecho, depois do filtro `af`."""
    chain = (af + "," if af else "") + "ebur128"
    r = subprocess.run(["ffmpeg", "-nostats", "-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", str(src), "-af", chain,
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -70.0


def env_db(x: np.ndarray, n: int = 800) -> np.ndarray:
    k = len(x) // n
    return 20 * np.log10(np.sqrt((x[: k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)


def xcorr_lag(a: np.ndarray, b: np.ndarray) -> int:
    """Atraso de b em relação a a (amostras); >0 = b atrasado."""
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    c = np.fft.irfft(np.fft.rfft(b, 2 * n) * np.conj(np.fft.rfft(a, 2 * n)))
    i = int(np.argmax(c))
    return i if i < n else i - 2 * n


def probe(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=duration", "-of", "default=nw=1:nk=1", str(p)],
                                capture_output=True, text=True).stdout)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--voice-chain", default=None, help="noisy | clean | cadeia ffmpeg sem espaços")
    ap.add_argument("--stems", action="store_true")
    ap.add_argument("--tone-ref", type=Path, default=None,
                    help="vídeo de referência do tom (ex.: a base que entrou no HyperFrames): mede o desvio de "
                         "luminância do --picture contra ela e devolve o tom com a curva inversa (só Y)")
    ap.add_argument("--tone-times", default="", help="tempos (s) sem overlay para medir, separados por vírgula")
    ap.add_argument("--picture", type=Path, default=None,
                    help="imagem final (ex.: render do acabamento HyperFrames); padrão remotion/out/render.mp4")
    a = ap.parse_args()

    edit = a.edit.resolve()
    pub = edit / "remotion" / "public"
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    aud = ed.get("audio") or {}
    chain_key = a.voice_chain or aud.get("voiceChain") or "clean"
    chain = CHAINS.get(chain_key, chain_key)
    render = (a.picture.resolve() if a.picture else edit / "remotion" / "out" / "render.mp4")
    if not render.exists():
        sys.exit("render.mp4 não existe — rode render_phase2.py antes")
    vd = probe(render)
    fps = ed.get("fps", 30)
    lag = round(48000 / fps)

    def find(src: str) -> Path:
        for base in (edit / "sfx_cinema", edit.parent / "sfx_cinema", edit.parent.parent / "sfx_cinema",
                     pub / "sfx", pub):
            if (base / src).exists():
                return base / src
        sys.exit(f"sfx não encontrado: {src}")

    cues = [dict(c) for c in ed.get("sfxCues", [])]
    for t in ed.get("transitions", []):
        if t.get("sfx", "cut-click.mp3") is not None:
            cues.append({"src": t.get("sfx", "cut-click.mp3"), "at": t["at"], "volume": t.get("volume", 0.18)})

    cut = edit / "cut.mp4"
    # Latência da cadeia de voz (afftdn trabalha em janelas FFT): medida, não
    # suposta. Sem isso a voz chegava 30ms atrasada além do VIDEO_LAG (medido no
    # XC60: 63ms em vez de 33ms).
    raw_v = pcm(cut, None, 0, 12)
    proc_v = pcm(cut, chain, 0, 12)
    lat = xcorr_lag(raw_v, proc_v)  # amostras a 16 kHz; >0 = processada atrasada
    lat48 = max(0, round(lat * 3))
    pre_delay = max(0, lag - lat48)
    post_trim = max(0, lat48 - lag) / 48000
    vfilt = f"[1:a]aresample=48000,aformat=channel_layouts=mono,adelay={pre_delay}S,{chain}"
    if post_trim:
        vfilt += f",atrim=start={post_trim:.4f},asetpts=PTS-STARTPTS"

    inputs = ["-i", str(render), "-i", str(cut)]
    # Remotion sai yuvj420p/pc (faixa completa); outro motor (HyperFrames) pode
    # já sair em faixa de TV. Converter uma imagem tv como se fosse pc desbota —
    # a conversão depende do que o arquivo DIZ, medido.
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=pix_fmt,color_range", "-of", "default=nw=1:nk=1", str(render)],
                        capture_output=True, text=True).stdout.split()
    full = any(x in ("pc", "yuvj420p", "yuvj444p") for x in pr)
    rng = "scale=in_range=full:out_range=limited," if full else ""
    tone = ""
    if a.tone_ref:
        # O render do HyperFrames (Chrome) devolve a luma ~2–3% mais escura que a
        # base, neutro nos 3 canais (medido no XC60: hf ≈ 0,98·base − 1). Mede-se
        # Y da referência × Y do render nos tempos sem overlay e aplica-se a inversa.
        ts = [float(x) for x in a.tone_times.split(",") if x.strip()] or [vd * k for k in (.2, .4, .6, .8)]
        def yplane(f, t):
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(f), "-frames:v", "1", "-vf",
                                "scale=270:480,format=gray", "-f", "rawvideo", "-"], capture_output=True)
            return np.frombuffer(r.stdout, np.uint8).astype(float)
        X = np.concatenate([yplane(a.tone_ref, t) for t in ts]); Y = np.concatenate([yplane(render, t) for t in ts])
        g, o = np.polyfit(X, Y, 1)
        ig, io = 1 / g, -o / g
        if abs(ig - 1) > 0.005 or abs(io) > 0.5:
            tone = f"lutyuv=y='clip(val*{ig:.4f}{io:+.2f},16,235)',"
        print(f"  tom: render = {g:.4f}·ref {o:+.2f} → correção {tone or 'nenhuma'}")
    fc = [f"[0:v]{rng}{tone}format=yuv420p,"
          "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]",
          vfilt + ",aformat=channel_layouts=stereo,asplit=3[voz][k1][k2]"]
    mix = ["[voz]"]

    st = ed.get("soundtrack") or {}
    if st.get("enabled"):
        raw = st.get("raw") or st.get("file")
        track = next((p for p in (edit / raw, edit.parent / raw, edit.parent.parent / raw, pub / raw) if p.exists()), None)
        if track is None:
            sys.exit(f"trilha não encontrada: {raw}")
        inputs += ["-i", str(track)]
        k = len(inputs) // 2 - 1
        off = float(st.get("offset", 0.0))
        fade = max(0.0, vd - float(st.get("fadeOut", 1.6)))
        # ---- calibração por LOUDNESS INTEGRADO da faixa inteira (LUFS).
        # v1 calibrava só a banda 250–2200 Hz: a trilha ficou 14 dB abaixo da voz
        # ali, mas só 5,6 LU abaixo no conjunto e MAIS ALTA que a voz nos graves —
        # o usuário ouviu "música alta, as vozes têm que aparecer mais" (XC60,
        # 2026-10-30). Padrão de conteúdo falado: trilha 14–16 LU abaixo da fala NO
        # RESULTADO. `musicBelowVoice` (LU, padrão 9) é medido ANTES do ducking; com
        # fala quase contínua o ducking soma ~6 LU (medido: alvo 15 deu 21 LU). Grave da trilha −3 dB abaixo de 140 Hz,
        # onde ela embolava com a voz.
        MUS_EQ = "lowshelf=f=140:g=-3"
        v_lufs = lufs(cut, chain, 0, vd)
        m_lufs = lufs(track, MUS_EQ, off, vd)
        target = float(st.get("musicBelowVoice", 9.0))  # antes do ducking; com ele a trilha fica ~15 LU abaixo (medido)
        vol = 10 ** ((v_lufs - target - m_lufs) / 20)
        vol = float(st["volume"]) if st.get("autoLevel") is False else min(1.5, max(0.02, vol))
        vf = env_db(pcm(cut, chain, 0, vd))
        v_full = float(np.median(vf[vf > np.percentile(vf, 40)]))
        thr = min(0.5, 10 ** ((v_full - 10) / 20))  # limiar da chave: 10 dB abaixo da fala típica
        st.setdefault("duckBandThr", round(thr, 4)); st.setdefault("duckThr", round(thr, 4))
        st.setdefault("duckBandRatio", 3); st.setdefault("duckRatio", 1.6)
        print(f"  voz {v_lufs:.1f} LUFS · trilha (vol 1) {m_lufs:.1f} LUFS → volume {vol:.3f} "
              f"(trilha {target:.0f} LU abaixo) · limiar de ducking {thr:.3f} · latência {lat48 / 48:.1f} ms")
        fc.append(
            f"[{k}:a]atrim=start={off:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
            f"{MUS_EQ},volume={vol},afade=t=in:st=0:d={st.get('fadeIn', 0.25)},afade=t=out:st={fade:.3f}:d={st.get('fadeOut', 1.6)},"
            f"asplit=3[ml][mb][mh]")
        fc.append("[ml]lowpass=f=250[mlo]")
        fc.append("[mh]highpass=f=2200[mhi]")
        fc.append("[mb]highpass=f=250,lowpass=f=2200[mband]")
        fc.append(f"[mband][k1]sidechaincompress=threshold={st.get('duckBandThr', 0.015)}:ratio={st.get('duckBandRatio', 10)}"
                  f":attack=15:release=320:knee=3[mbd]")
        fc.append("[mlo][mhi][mbd]amix=inputs=3:normalize=0[mcarv]")
        fc.append(f"[mcarv][k2]sidechaincompress=threshold={st.get('duckThr', 0.03)}:ratio={st.get('duckRatio', 2.5)}"
                  f":attack=25:release=450:knee=4[mus]")
        mix.append("[mus]")
    else:
        fc.append("[k1]anullsink;[k2]anullsink")

    sfx_labels = []
    for i, c in enumerate(cues):
        inputs += ["-i", str(find(c["src"]))]
        k = len(inputs) // 2 - 1
        d = max(0, round((float(c["at"]) + 1 / fps) * 48000))
        fc.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={c.get('volume', 0.2)},adelay={d}S:all=1[s{i}]")
        sfx_labels.append(f"[s{i}]")
    if sfx_labels:
        fc.append("".join(sfx_labels) + f"amix=inputs={len(sfx_labels)}:normalize=0[sfx]")
        mix.append("[sfx]")

    fc.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,atrim=0:{vd:.3f}[pre]")

    # ---- passada 1: medir
    m = subprocess.run(["ffmpeg", "-v", "info", "-y", *inputs, "-filter_complex",
                        ";".join(fc[1:]) + ";[pre]loudnorm=I=-14:TP=-1:LRA=11:print_format=json[o]",
                        "-map", "[o]", "-f", "null", "-"], capture_output=True, text=True)
    js = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", m.stderr, re.S)
    if not js:
        sys.exit("loudnorm passada 1 falhou:\n" + m.stderr[-2500:])
    me = json.loads(js.group(0))
    ln = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={me['input_i']}:measured_TP={me['input_tp']}:"
          f"measured_LRA={me['input_lra']}:measured_thresh={me['input_thresh']}:offset={me['target_offset']}:linear=true")

    out = edit / "final.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc) + f";[pre]{ln}[out]",
           "-map", "[vid]", "-map", "[out]", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
           "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{vd:.3f}",
           "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-2500:])

    if a.stems:
        stems = edit / "stems"; stems.mkdir(exist_ok=True)
        for lab in ("voz", "mus", "sfx"):
            if f"[{lab}]" not in mix:
                continue
            # fc[0] é a cadeia de vídeo e fc[-1] a soma final — fora dos stems.
            g = ";".join(fc[1:-1]) + f";{lab_keep(mix, lab)}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", g, "-map", f"[{lab}o]",
                            "-t", f"{vd:.3f}", str(stems / f"{lab}.wav")], capture_output=True)
    print(f"final: {out} ({vd:.2f}s · voz '{chain_key}' · trilha {'sim' if st.get('enabled') else 'não'} · "
          f"{len(cues)} sfx · entrada {me['input_i']} LUFS → -14)")


def lab_keep(mix: list[str], lab: str) -> str:
    """Filtergraph que descarta as outras saídas e expõe só `lab` como [labo]."""
    parts = [f"[{lab}]anull[{lab}o]"]
    for other in mix:
        o = other.strip("[]")
        if o != lab:
            parts.append(f"[{o}]anullsink")
    return ";".join(parts)


if __name__ == "__main__":
    main()
