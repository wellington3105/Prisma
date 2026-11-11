"""QA do MIX final: loudness, pico real, nível de cada SFX contra a voz, silêncios, trilha sob a fala.

Uso (rode DEPOIS do deliver_mix e ANTES de entregar):
    uv run python helpers/qa_mix.py <edit_dir> [--final final.mp4] [--fix]

Mede (sem escrever nada em <edit_dir>, exceto com --fix):
  1. streams e duração do final contra o cut.mp4;
  2. loudness integrado e PICO REAL (ebur128=peak=true): alvo -14 ±1 LUFS e TP ≤ -1,0 dBTP;
  3. cada SFX (sfxCues + clique de transição) nos STEMS: o pico real do golpe no stem de sfx,
     junto de `at` (respeitando `align`), contra o pico p95 da voz numa janela em volta.
     Marca  > +1,5 dB sobre a voz ("alto demais"), < -22 dB ("inaudível") e golpe DENTRO da
     fala com pico a menos de 3 dB da voz (mascara palavra); imprime o nível relativo de cada um;
  4. silêncios > 0,8 s DENTRO da fala (devia ter sido cortado) — medido no stem da voz, porque
     no final a trilha tapa o silêncio;
  5. trilha sob a fala: RMS do stem da trilha / RMS da voz nas janelas de fala (esperado -15 a -20 dB).
--fix: se TP > -1,0, grava final_vNN.mp4 (deliveries.py) só com limiter de pico — NUNCA soma ganho
       (ganho desfaria o equilíbrio SFX/voz) —, remede e imprime antes/depois.
Código de saída 1 quando algo é marcado.

Stems: usa <edit>/stems/ (deliver_mix.py --stems) se existir; senão gera numa pasta temporária
(deliver_mix.py --stems-only), SEM tocar no edit. `--voice-chain` repassa a cadeia (padrão: voice_chain.txt).

Portado de kurbaitaev/ghost-editor (MIT) scripts/qa.py + references/sound-and-memes.md:
checagem de TP, nível de cada SFX contra o p95 da voz, silêncios dentro da fala, --fix só com limiter.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
SR = 48000
LUFS_T, LUFS_TOL, TP_MAX = -14.0, 1.0, -1.0
LOUD_DB, QUIET_DB, MASK_DB = 1.5, -22.0, -3.0
MUSIC_OK = (-26.0, -12.0)  # dB trilha/voz sob a fala (esperado -15 a -20)


def db(x: float) -> float:
    return 20 * np.log10(max(float(x), 1e-9))


def measure(p: Path) -> tuple[float, float]:
    """(LUFS integrado, pico real dBTP) do áudio de um arquivo."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-vn", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    t = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return (float(i[-1]) if i else -70.0, float(t[-1]) if t else 0.0)


def probe(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(p)],
                       capture_output=True, text=True)
    st = json.loads(r.stdout or "{}").get("streams", [])
    d = lambda k: next((float(s["duration"]) for s in st if s["codec_type"] == k and "duration" in s), 0.0)
    return {"v": sum(s["codec_type"] == "video" for s in st), "a": sum(s["codec_type"] == "audio" for s in st),
            "vd": d("video"), "ad": d("audio")}


def load(p: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def win_peaks(x: np.ndarray, w: float = 0.05) -> np.ndarray:
    n = int(SR * w)
    k = len(x) // n
    return np.abs(x[: k * n]).reshape(k, n).max(1)


def get_stems(edit: Path, chain: str | None, keep: list) -> Path:
    sd = edit / "stems"
    if (sd / "voz.wav").exists():
        print(f"stems: {sd} (existentes)")
        return sd
    td = tempfile.TemporaryDirectory(prefix="qa_mix_stems_")
    keep.append(td)
    cmd = [sys.executable, str(HERE / "deliver_mix.py"), str(edit), "--stems-only", "--stems-dir", td.name]
    if chain:
        cmd += ["--voice-chain", chain]
    print("stems: gerando numa pasta temporária (deliver_mix --stems-only)...")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode or not (Path(td.name) / "voz.wav").exists():
        sys.exit("falha ao gerar stems:\n" + (r.stdout + r.stderr)[-1500:])
    return Path(td.name)


def build_cues(edit: Path) -> list[dict]:
    """Os mesmos cues que o deliver_mix mixa, com `at` já descontado pelo `align` (= início do arquivo)."""
    pub = edit / "remotion" / "public"
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    fps = ed.get("fps", 30)
    sys.path.insert(0, str(HERE))
    from sfx_peak import shift

    def find(src: str) -> Path | None:
        for b in (edit / "sfx_cinema", edit.parent / "sfx_cinema", edit.parent.parent / "sfx_cinema", pub / "sfx", pub):
            if (b / src).exists():
                return b / src
        return None

    cues = [dict(c) for c in ed.get("sfxCues", [])]
    for t in ed.get("transitions", []):
        if t.get("sfx", "cut-click.mp3") is not None:
            cues.append({"src": t.get("sfx", "cut-click.mp3"), "at": t["at"], "volume": t.get("volume", 0.18),
                         "align": t.get("sfxAlign", "peak"), "kind": "transição"})
    for c in cues:
        f = find(c["src"])
        c["file"] = f
        sh = shift(f, c.get("align")) if f else 0.0
        c["hit"] = float(c["at"]) + 1 / fps                 # onde o golpe deve soar
        c["start"] = float(c["at"]) - (sh or 0.0) + 1 / fps  # onde o arquivo começa
    return cues


def audit_sfx(cues: list[dict], voz: np.ndarray, sfx: np.ndarray, flags: list[str]) -> None:
    vp = win_peaks(voz)
    act_all = vp[vp > 10 ** (-40 / 20)]
    if not len(act_all):
        flags.append("stem da voz vazio")
        return
    g95 = float(np.percentile(act_all, 95))
    thr = g95 * 10 ** (-18 / 20)  # janela "com fala" = a menos de 18 dB do p95
    print(f"\nSFX x voz (p95 global da voz {db(g95):.1f} dBFS) — {len(cues)} golpes")
    print("   t(s)  arquivo                    vol   sfx dBFS  voz dBFS  rel dB")
    for c in cues:
        s0 = int(max(0.0, c["start"]) * SR)
        s1 = s0 + int(min(0.8, 0.8) * SR)
        seg = sfx[s0:s1]
        pk = float(np.abs(seg).max()) if len(seg) else 0.0
        a, b = int(max(0, c["hit"] - 1.5) / 0.05), int((c["hit"] + 1.5) / 0.05)
        loc = vp[a:b]
        loc = loc[loc > thr]
        if len(loc) >= 3:
            vref, note = float(np.percentile(loc, 95)), ""
        else:
            vref, note = g95, " (sem fala perto: ref. global)"
        rel = db(pk) - db(vref)
        a2, b2 = int(c["hit"] / 0.05), int((c["hit"] + 0.3) / 0.05) + 1
        on_speech = bool(len(vp[a2:b2]) and vp[a2:b2].max() > thr)
        msgs = []
        if pk < 1e-4:
            msgs.append("SEM SOM no stem (arquivo não achado / volume 0?)")
        elif rel > LOUD_DB:
            msgs.append(f"alto demais (+{rel:.1f} dB sobre a voz)")
        elif rel < QUIET_DB:
            msgs.append(f"inaudível ({rel:.1f} dB sob a voz)")
        elif on_speech and rel > MASK_DB:
            msgs.append("mascara palavra (golpe sobre a fala a <3 dB da voz)")
        if c["file"] is None:
            msgs.append("sfx não encontrado")
        tag = ("  ⚠ " + "; ".join(msgs)) if msgs else ""
        print(f"  {c['hit']:6.2f}  {c['src'][:24]:<24} {float(c.get('volume', .2)):5.2f}  {db(pk):8.1f}  "
              f"{db(vref):8.1f}  {rel:+6.1f}{note}{tag}")
        for m in msgs:
            flags.append(f"sfx {c['src']} @{c['hit']:.2f}s: {m}")


def audit_silence(voz: np.ndarray, flags: list[str]) -> None:
    vp = win_peaks(voz)
    act = np.where(vp > 10 ** (-40 / 20))[0]
    if not len(act):
        return
    first, last = act[0] * 0.05, (act[-1] + 1) * 0.05
    gaps, run0 = [], None
    for i in range(int(first / 0.05), int(last / 0.05)):
        quiet = vp[i] <= 10 ** (-40 / 20)
        if quiet and run0 is None:
            run0 = i
        elif not quiet and run0 is not None:
            if (i - run0) * 0.05 > 0.8:
                gaps.append((run0 * 0.05, (i - run0) * 0.05))
            run0 = None
    print(f"\nsilêncios > 0,8 s dentro da fala (voz {first:.1f}–{last:.1f}s): {len(gaps)}")
    for t, d in gaps:
        print(f"  {t:.2f}s por {d:.2f}s")
        flags.append(f"silêncio de {d:.2f}s em {t:.2f}s dentro da fala (devia ter sido cortado)")


def audit_music(voz: np.ndarray, mus: np.ndarray, flags: list[str]) -> None:
    n = min(len(voz), len(mus))
    w = int(SR * 0.1)
    k = n // w
    v = voz[: k * w].reshape(k, w)
    m = mus[: k * w].reshape(k, w)
    vr = np.sqrt((v ** 2).mean(1))
    act = vr > 10 ** (-40 / 20)
    if act.sum() < 5:
        return
    rel = db(np.sqrt((m[act] ** 2).mean())) - db(np.sqrt((v[act] ** 2).mean()))
    ok = MUSIC_OK[0] <= rel <= MUSIC_OK[1]
    print(f"\ntrilha sob a fala: {rel:+.1f} dB vs voz (esperado -15 a -20) {'OK' if ok else '⚠'}")
    if rel > MUSIC_OK[1]:
        flags.append(f"trilha alta sob a fala ({rel:+.1f} dB vs voz; esperado -15 a -20)")
    elif rel < MUSIC_OK[0]:
        flags.append(f"trilha quase inaudível sob a fala ({rel:+.1f} dB vs voz)")


def fix_peak(edit: Path, final: Path) -> Path | None:
    sys.path.insert(0, str(HERE))
    from deliveries import next_path, publish
    i0, t0 = measure(final)
    for ceil in (-1.5, -2.0, -2.5):
        out = next_path(edit)
        lim = 10 ** (ceil / 20)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-c:v", "copy", "-af",
                            f"alimiter=limit={lim:.4f}:level=disabled:attack=3:release=40,aresample=48000",
                            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(out)],
                           capture_output=True, text=True)
        if r.returncode:
            out.unlink(missing_ok=True)
            print("  --fix falhou:", r.stderr[-400:])
            return None
        i1, t1 = measure(out)
        if t1 <= TP_MAX:
            publish(edit, out, by="qa_mix --fix")
            print(f"  --fix (teto {ceil} dB, sem ganho): LUFS {i0:.1f} → {i1:.1f} · TP {t0:.1f} → {t1:.1f} dBTP · {out.name}")
            return out
        out.unlink(missing_ok=True)
    print("  --fix: não chegou a ≤ -1,0 dBTP em 3 tentativas")
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--final", type=Path, default=None, help="padrão <edit>/final.mp4")
    ap.add_argument("--fix", action="store_true", help="se TP > -1,0: grava final_vNN só com limiter de pico")
    ap.add_argument("--voice-chain", default=None, help="cadeia usada na entrega (padrão: <edit>/voice_chain.txt)")
    a = ap.parse_args()
    edit = a.edit.resolve()
    final = (a.final if a.final and a.final.is_absolute() else edit / (a.final or "final.mp4")).resolve()
    if not final.exists():
        sys.exit(f"{final} não existe — rode deliver_mix.py antes")
    flags: list[str] = []
    print(f"QA do mix: {final}")

    # 1. streams / duração
    pf = probe(final)
    cut = edit / "cut.mp4"
    pc = probe(cut) if cut.exists() else None
    fd = pf["vd"] or pf["ad"]
    print(f"streams: {pf['v']} vídeo + {pf['a']} áudio · duração vídeo {pf['vd']:.2f}s / áudio {pf['ad']:.2f}s"
          + (f" · cut.mp4 {pc['vd']:.2f}s" if pc else ""))
    if pf["v"] != 1 or pf["a"] != 1:
        flags.append(f"streams inesperados ({pf['v']} vídeo, {pf['a']} áudio)")
    if abs(pf["vd"] - pf["ad"]) > 0.1:
        flags.append(f"áudio e vídeo com durações diferentes ({pf['ad']:.2f}s vs {pf['vd']:.2f}s)")
    if pc and abs(fd - pc["vd"]) > 0.25:
        flags.append(f"duração {fd:.2f}s difere do cut.mp4 ({pc['vd']:.2f}s) em {fd - pc['vd']:+.2f}s")

    # 2. loudness + TP
    li, tp = measure(final)
    print(f"loudness {li:.1f} LUFS (alvo {LUFS_T:.0f} ±{LUFS_TOL:.0f}) · pico real {tp:.1f} dBTP (alvo ≤ {TP_MAX:.1f})")
    if abs(li - LUFS_T) > LUFS_TOL:
        flags.append(f"loudness {li:.1f} LUFS fora de {LUFS_T:.0f} ±{LUFS_TOL:.0f}")
    tp_bad = tp > TP_MAX
    if tp_bad:
        flags.append(f"pico real {tp:.1f} dBTP > {TP_MAX:.1f}")

    # 3-5. stems
    keep: list = []
    chain = a.voice_chain
    vc = edit / "voice_chain.txt"
    if chain is None and vc.exists():
        chain = vc.read_text(encoding="utf-8").strip() or None
    sd = get_stems(edit, chain, keep)
    voz = load(sd / "voz.wav")
    sfx = load(sd / "sfx.wav") if (sd / "sfx.wav").exists() else None
    mus = load(sd / "mus.wav") if (sd / "mus.wav").exists() else None
    cues = build_cues(edit)
    if cues and sfx is not None:
        audit_sfx(cues, voz, sfx, flags)
    else:
        print("\nSFX: nenhum cue (ou sem stem de sfx)")
    audit_silence(voz, flags)
    if mus is not None:
        audit_music(voz, mus, flags)

    # --fix
    if a.fix and tp_bad:
        print("\n--fix:")
        out = fix_peak(edit, final)
        if out:
            flags = [f for f in flags if not f.startswith("pico real")]
    for k in keep:
        k.cleanup()

    print("\n" + ("MARCAS (%d):\n  - " % len(flags) + "\n  - ".join(flags) if flags else "mix OK"))
    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
