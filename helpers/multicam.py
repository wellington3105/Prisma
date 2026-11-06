"""Multicam do Prisma: 2+ câmeras, câmera VIRTUAL (punch-in de master 4K) e ângulos de IA.

O `render.py` não muda: este helper só escreve EDL. Cada range do EDL passa a ter
como `source` o ângulo escolhido (tempos já convertidos pelo offset) e o SOM de
TODOS os ranges é roteado, via `audio_sources`, para o áudio do master — a voz
nunca troca de microfone entre ângulos.

Subcomandos:
  sync       offset de cada câmera real contra o master (reusa sync_sources.py)
  virtual    segunda câmera virtual: punch-in que segue o rosto, saída ≤ 1080 sem upscale
  add-ai     registra um preset de ângulo de IA (rotate / vertical / closeup)
  plan       atribui um ângulo a cada range do EDL do master; escreve edl.multicam.json
  build      refaz o EDL a partir de multicam_plan.json (após ai-assemble, p.ex.)
  ai-prep    recorta SÓ os trechos que o plano deu à IA, em janelas ≤ 8 s → ai_angles/jobs.json
  ai-assemble  conforma os resultados da IA (fps, tamanho, duração exata) e refaz o EDL
  status     lista os ângulos registrados

Nada aqui chama API paga: a geração dos ângulos de IA acontece fora, entre
`ai-prep` e `ai-assemble`.

Convenção de tempo (a mesma do sync_sources): t_master = t_ângulo + offset.
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ----------------------------------------------------------------- constantes
MIN_SHOT = 2.5          # s: duração mínima de um plano (ângulo contínuo)
SWITCH_GAP = 1.2        # s: nunca dois cortes de ângulo dentro disto
SEAM_LOSS = 0.12        # s: o J-cut encurta ~isto em cada emenda; entra na conta do min-shot
JUMP_GAP = 0.08         # s: vão no master a partir do qual a emenda é um jump cut
PAUSE_MIN = 0.30        # s: pausa mínima para cortar de ângulo dentro de um take longo
PAUSE_ABOVE_FLOOR_DB = 6.0
MAX_SHOT = 7.0          # s: take contínuo mais longo que isto é partido numa pausa (estilo alternate)
DRIFT_MAX_MS = 40.0     # ~1 frame: câmera cujo relógio escorrega mais que isto não entra no plano
AI_MAX_SHOT = 4.0       # s: IA só em planos curtos
AI_SHARE = 0.35         # fração máxima do tempo em ângulos de IA (limita créditos)
AI_WINDOW = 8.0         # s: janela máxima por job de IA
AI_HANDLE = 0.3         # s: folga de cada lado da janela de IA
FACE_EYE_LINE = 0.38    # linha dos olhos, em fração da altura do enquadramento do close
ROLE_CLOSE = "close"

NUM_WORDS = set("""dois duas tres quatro cinco seis sete oito nove dez onze doze treze quatorze catorze
quinze dezesseis dezessete dezoito dezenove vinte trinta quarenta cinquenta sessenta setenta oitenta
noventa cem cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos
novecentos mil milhao milhoes bilhao bilhoes dobro triplo""".split())
UNIT_WORDS = set("""cv cavalos km quilometros litros metros segundos reais real dolares dolar graus kg quilos
polegadas gigas megas hertz watts volts euros porcento""".split())
CUE_WORDS = set("""detalhe detalhes repare repara olha olhem veja vejam atencao importante principal incrivel
absurdo diferenca novidade exclusivo""".split())
CONNECTIVES = set("e mas entao porque que ai dai ou tipo bom so pois porem tambem enquanto quando onde como se".split())


def die(msg: str, code: int = 2):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(code)


def norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9%]+", "", w)


def safe_key(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_") or "angulo"


# ------------------------------------------------------------------- ffmpeg
def run(cmd: list, cwd: Path | None = None, quiet: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die(f"ffmpeg falhou ({cmd[0]}):\n{r.stderr[-1500:]}", 1)
    return r


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
    except Exception:
        die(f"ffprobe não leu {path}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        die(f"sem vídeo em {path}")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if not rot and (v.get("tags") or {}).get("rotate"):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    if fps <= 0:
        num, _, den = v["r_frame_rate"].partition("/")
        fps = float(num) / float(den or 1)
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    return {"width": w, "height": h, "fps": fps, "duration": dur,
            "audio": any(s.get("codec_type") == "audio" for s in d["streams"]),
            "hdr": (v.get("color_transfer") in ("smpte2084", "arib-std-b67")),
            "color": {k: v.get(k) for k in ("color_primaries", "color_transfer", "color_space")}}


def out_size(w: int, h: int, short: int = 1080) -> tuple[int, int]:
    """Tamanho de saída do render sem --keep-resolution: lado curto 1080, mesma proporção."""
    if w >= h:
        ow, oh = round(short * w / h / 2) * 2, short
    else:
        ow, oh = short, round(short * h / w / 2) * 2
    return min(ow, w), min(oh, h)


# ---------------------------------------------------------------- multicam.json
def mc_file(edit: Path) -> Path:
    return edit / "multicam.json"


def load_mc(edit: Path, must: bool = True) -> dict:
    p = mc_file(edit)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    if must:
        die(f"{p} não existe — rode `multicam.py sync` ou `virtual` primeiro")
    return {"version": 1, "master": None, "angles": []}


def save_mc(edit: Path, mc: dict) -> None:
    edit.mkdir(parents=True, exist_ok=True)
    mc_file(edit).write_text(json.dumps(mc, ensure_ascii=False, indent=1), encoding="utf-8")


def upsert(mc: dict, angle: dict) -> None:
    mc["angles"] = [a for a in mc["angles"] if a["key"] != angle["key"]] + [angle]


def set_master(mc: dict, path: Path) -> None:
    info = probe(path)
    m = {"key": safe_key(path.stem), "path": str(path.resolve()), "duration": round(info["duration"], 3),
         "fps": round(info["fps"], 3), "width": info["width"], "height": info["height"]}
    if mc.get("master") and Path(mc["master"]["path"]).resolve() != path.resolve():
        print("  aviso: master mudou — ângulos antigos foram sincronizados contra outro arquivo")
    mc["master"] = m


# ================================================================== sync
def cmd_sync(a) -> None:
    import sync_sources as ss
    edit = a.edit.resolve()
    master = a.master.resolve()
    mc = load_mc(edit, must=False)
    set_master(mc, master)
    roles = a.roles or []
    bad = 0
    for i, p in enumerate(a.angles):
        p = p.resolve()
        key = safe_key(p.stem)
        if key == mc["master"]["key"]:
            key += "_cam2"
        s = ss.sync(master, p)
        drift = (f" · deriva {s['drift_ppm']:+.0f} ppm (escorrega {s['slip_ms']} ms)"
                 if s["drift_ppm"] is not None else "")
        print(f"  {key}: t_master = t_ângulo {s['offset_s']:+.4f} s · confiança {s['confidence']} "
              f"(pico/2º {s['peak_ratio']}){drift}")
        if s["confidence"] == "baixa":
            print(f"      RECUSADO: confiança baixa (pico/2º {s['peak_ratio']} < {ss.FAIR}). As câmeras ouvem "
                  f"a mesma cena? Bata uma palma no começo de todas, confira o volume do áudio de "
                  f"{p.name} e tente de novo — não vou registrar um offset chutado.")
            bad += 1
            continue
        if s["slip_ms"] is not None and s["slip_ms"] >= DRIFT_MAX_MS:
            print(f"      aviso: relógio deriva ~{s['slip_ms']:.0f} ms — o plano vai ignorar este ângulo "
                  f"(reamostre-o ou use --allow-drift no plan)")
        info = probe(p)
        if abs(info["fps"] - mc["master"]["fps"]) > 0.05:
            print(f"      aviso: fps {info['fps']:.3f} ≠ master {mc['master']['fps']:.3f} — grave tudo no mesmo fps")
        upsert(mc, {"key": key, "kind": "camera", "path": str(p), "offset": s["offset_s"],
                    "confidence": s["confidence"], "peak_ratio": s["peak_ratio"],
                    "drift_ppm": s["drift_ppm"], "slip_ms": s["slip_ms"],
                    "role": roles[i] if i < len(roles) else "alt",
                    "duration": round(info["duration"], 3)})
    if len(mc["angles"]) or not bad:
        save_mc(edit, mc)
        print(f"  gravado {mc_file(edit)}")
    if bad:
        die(f"{bad} ângulo(s) recusado(s) por confiança baixa")


# ================================================================ virtual
def get_faces(edit: Path, src: Path, info: dict, faces_arg: Path | None) -> dict | None:
    if faces_arg:
        return json.loads(faces_arg.read_text(encoding="utf-8"))
    cache = edit / "multicam" / "faces_source.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("source") == str(src) and d.get("w") == info["width"] and d.get("h") == info["height"]:
            print(f"  rostos: cache {cache}")
            return d
    try:
        import safe_layout
    except Exception as e:
        print(f"  aviso: sem detector de rosto ({e}) — enquadramento fixo")
        return None
    print("  detectando rostos no master (YuNet) — o 4K inteiro, pode levar um pouco…")
    try:
        d = safe_layout.detect_faces(src, 5.0)
    except ImportError as e:
        print(f"  aviso: OpenCV indisponível ({e}) — rode com `uv run python` — enquadramento fixo")
        return None
    d["source"] = str(src)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d


def face_path(faces_data: dict, fps: float, dur: float, cw: int, ch: int, W: int, H: int):
    """(x0[], y0[], unsafe[]) por frame: segue o rosto com mediana, zona morta e gaussiana."""
    from scipy.ndimage import gaussian_filter1d, median_filter
    from safe_layout import Faces
    faces = Faces(faces_data)
    n = max(1, int(dur * fps))
    ts = np.arange(n) / fps
    raw = np.full((n, 6), np.nan)           # cx, eyes_y, top, bottom, left, right
    for k, t in enumerate(ts):
        f = faces.at(float(t))
        if f is not None:
            top, bot, left, right = f
            raw[k] = [(left + right) / 2, top + (bot - top) * 0.40, top, bot, left, right]
    have = ~np.isnan(raw[:, 0])
    if not have.any():
        return None
    idx = np.where(have)[0]
    fill = np.stack([np.interp(np.arange(n), idx, raw[idx, c]) for c in range(6)], axis=1)
    k = int(fps) | 1
    cx = median_filter(fill[:, 0], size=k, mode="nearest")
    ey = median_filter(fill[:, 1], size=k, mode="nearest")
    tx, ty = cx, ey + (0.5 - FACE_EYE_LINE) * ch

    def follow(tgt, dz):
        out = np.empty_like(tgt)
        cur = tgt[0]
        for i, v in enumerate(tgt):
            if abs(v - cur) > dz:
                cur = v - math.copysign(dz * 0.5, v - cur)
            out[i] = cur
        return out
    sx = gaussian_filter1d(follow(tx, 0.05 * cw), 0.5 * fps, mode="nearest")
    sy = gaussian_filter1d(follow(ty, 0.05 * ch), 0.5 * fps, mode="nearest")
    x0 = np.clip(sx - cw / 2, 0, W - cw)
    y0 = np.clip(sy - ch / 2, 0, H - ch)

    # trechos em que o close não é seguro: sem rosto, rosto fora do quadro, movimento rápido
    unsafe, step = [], max(1, int(fps / 10))
    speed = np.abs(np.gradient(cx, 1 / fps))
    mgn = 0.04
    flags = []
    for i in range(0, n, step):
        why = None
        if not have[i]:
            why = "rosto não detectado"
        else:
            L, R, T, B = fill[i, 4], fill[i, 5], fill[i, 2], fill[i, 3]
            if (L < x0[i] + mgn * cw or R > x0[i] + cw * (1 - mgn)
                    or T < y0[i] + mgn * ch or B > y0[i] + ch * (1 - mgn)):
                why = "rosto sai do enquadramento do close"
            elif speed[i] > 0.20 * cw:
                why = "movimento rápido"
        flags.append((ts[i], why))
    cur = None
    for t, why in flags + [(dur, None)]:
        if why and cur is None:
            cur = [t, t, why]
        elif why and cur:
            cur[1] = t + step / fps
        elif not why and cur:
            unsafe.append(cur)
            cur = None
    merged = []
    for u in unsafe:
        if merged and u[0] - merged[-1][1] < 0.3:
            merged[-1][1] = u[1]
            if u[2] not in merged[-1][2]:
                merged[-1][2] += " + " + u[2]
        else:
            merged.append(list(u))
    unsafe = [{"t0": round(a, 2), "t1": round(b, 2), "why": w} for a, b, w in merged if b - a >= 0.2]
    return x0, y0, unsafe


def cmd_virtual(a) -> None:
    edit = a.edit.resolve()
    src = a.source.resolve()
    info = probe(src)
    if not info["audio"]:
        die("o master precisa de áudio (o ângulo virtual leva o mesmo som)")
    W, H, fps, dur = info["width"], info["height"], info["fps"], info["duration"]
    ow, oh = (int(x) for x in a.out_size.lower().split("x")) if a.out_size else out_size(W, H, a.out_height)
    zmax = min(W / ow, H / oh)
    zoom = a.zoom
    if zoom > zmax + 1e-6:
        print(f"  zoom {zoom} pediria upscale (fonte {W}x{H} → saída {ow}x{oh}); limitado a {zmax:.2f}")
        zoom = zmax
    if zoom < 1.05:
        die(f"fonte {W}x{H} não tem resolução para um punch-in real sobre uma saída {ow}x{oh} "
            f"(zoom máx {zmax:.2f}). Câmera virtual precisa de master ≥ 4K para saída 1080.")
    cw = int(W / zoom) // 2 * 2
    ch = int(round(cw * H / W)) // 2 * 2
    out_dir = edit / "multicam"
    out_dir.mkdir(parents=True, exist_ok=True)
    mc = load_mc(edit, must=False)
    set_master(mc, src)
    key = a.key or f"{mc['master']['key']}_close"
    out = out_dir / f"{key}.mp4"

    focus = a.focus
    path = None
    unsafe: list = []
    face_data = False
    if focus == "face":
        fd = get_faces(edit, src, info, a.faces)
        if fd:
            try:
                path = face_path(fd, fps, dur, cw, ch, W, H)
            except ImportError as e:
                print(f"  aviso: {e} — enquadramento fixo")
        if path is None:
            print("  aviso: nenhum rosto detectado — enquadramento fixo no centro")
            focus = "center"
        else:
            face_data = True
    vf_crop = None
    if path is not None:
        x0, y0, unsafe = path
        cmds = []
        for k in range(len(x0)):
            t = k / fps
            cmds.append(f"{t:.4f} crop x {int(round(x0[k]))};\n{t:.4f} crop y {int(round(y0[k]))};")
        (edit / "multicam" / f"{key}.cmd").write_text("\n".join(cmds), encoding="utf-8")
        vf_crop = (f"sendcmd=f=multicam/{key}.cmd,crop=w={cw}:h={ch}:x={int(x0[0])}:y={int(y0[0])}:exact=1")
    else:
        if focus == "center":
            fx, fy = 0.5, 0.5
        else:
            try:
                fx, fy = (float(v) for v in focus.split(","))
            except Exception:
                die("--focus: face | center | x,y (frações 0–1, ex.: 0.45,0.4)")
        x0 = int(min(max(fx * W - cw / 2, 0), W - cw)) // 2 * 2
        y0 = int(min(max(fy * H - ch / 2, 0), H - ch)) // 2 * 2
        vf_crop = f"crop=w={cw}:h={ch}:x={x0}:y={y0}:exact=1"
    vf = f"{vf_crop},scale={ow}:{oh}:flags=lanczos"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
    if info["hdr"]:
        c = info["color"]
        vf += ",format=yuv420p10le"
        venc = ["-c:v", "libx265", "-crf", "16", "-preset", "fast", "-tag:v", "hvc1",
                "-color_primaries", c["color_primaries"] or "bt2020",
                "-color_trc", c["color_transfer"] or "smpte2084", "-colorspace", c["color_space"] or "bt2020nc"]
        print("  fonte HDR: o ângulo mantém as tags HDR (HEVC 10 bits) para o render tratar igual ao master — não testado")
    else:
        vf += ",format=yuv420p"
        venc = ["-c:v", "libx264", "-crf", "16", "-preset", "fast"]
    cmd += ["-vf", vf, *venc, "-c:a", "copy", "-movflags", "+faststart", f"multicam/{key}.mp4"]
    t0 = time.time()
    print(f"  gerando {key}: crop {cw}x{ch} de {W}x{H} (zoom {zoom:.2f}) → {ow}x{oh}, foco {focus}…")
    run(cmd, cwd=edit)
    oi = probe(out)
    print(f"  ok em {time.time() - t0:.0f}s · {out} ({oi['width']}x{oi['height']}, {oi['fps']:.2f} fps, {oi['duration']:.2f} s)")
    if abs(oi["duration"] - dur) > 1.5 / fps:
        print(f"  aviso: duração {oi['duration']:.3f} s ≠ master {dur:.3f} s")
    upsert(mc, {"key": key, "kind": "virtual", "path": str(out), "offset": 0.0, "role": ROLE_CLOSE,
                "zoom": round(zoom, 3), "focus": focus, "crop": [cw, ch], "out": [ow, oh],
                "duration": round(oi["duration"], 3), "face_data": face_data, "unsafe": unsafe})
    save_mc(edit, mc)
    if unsafe:
        tot = sum(u["t1"] - u["t0"] for u in unsafe)
        print(f"  close inseguro em {len(unsafe)} trecho(s), {tot:.1f} s — o plan usa o master ali")
    print(f"  registrado em {mc_file(edit)}")


# ================================================================== add-ai
def cmd_add_ai(a) -> None:
    edit = a.edit.resolve()
    mc = load_mc(edit, must=False)
    if not 0 <= a.rotate <= 360 or not -30 <= a.vertical <= 90 or not 0 <= a.closeup <= 10:
        die("limites do video_camera_angle: rotate 0–360, vertical −30..90, closeup 0–10")
    upsert(mc, {"key": safe_key(a.key), "kind": "ai", "role": "ai", "rotate": a.rotate,
                "vertical": a.vertical, "closeup": a.closeup})
    save_mc(edit, mc)
    print(f"  ângulo de IA {safe_key(a.key)}: rotate {a.rotate} · vertical {a.vertical} · closeup {a.closeup}")


def cmd_status(a) -> None:
    mc = load_mc(a.edit.resolve())
    m = mc.get("master")
    print(f"master: {m['key']} ({m['width']}x{m['height']} @ {m['fps']} fps, {m['duration']} s)" if m else "master: —")
    for g in mc["angles"]:
        extra = ""
        if g["kind"] == "ai":
            extra = f"rotate {g['rotate']} vertical {g['vertical']} closeup {g['closeup']}"
        else:
            extra = f"offset {g['offset']:+.4f} · {g.get('confidence', '')}"
            if g.get("unsafe"):
                extra += f" · {len(g['unsafe'])} trecho(s) inseguro(s)"
        print(f"  {g['key']:<28} {g['kind']:<8} {g.get('role', ''):<6} {extra}")


# ============================================================ plan: insumos
def load_words(edit: Path, key: str, explicit: Path | None) -> list[dict]:
    cands = [explicit] if explicit else [edit / "transcripts" / f"{key}.json"]
    for p in cands:
        if p and p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            ws = [{"t0": float(w["start"]), "t1": float(w["end"]), "text": w["text"]}
                  for w in d.get("words", []) if w.get("type", "word") == "word"]
            return ws
    return []


def master_pauses(path: Path) -> list[tuple[float, float]]:
    """Pausas medidas no áudio do master (mesma lógica de piso+6 dB do render.edge_quiet)."""
    sr, hop = 16000, 0.010
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-af",
                        "highpass=f=250,highpass=f=250,lowpass=f=3500", "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout[: len(r.stdout) // 4 * 4], np.float32)
    n = int(hop * sr)
    if len(x) < n * 10:
        return []
    fr = x[: len(x) // n * n].reshape(-1, n).astype(np.float64)
    env = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    thr = np.sort(env)[int(0.15 * (len(env) - 1))] + PAUSE_ABOVE_FLOOR_DB
    quiet = env < thr
    out, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if (j - i) * hop >= PAUSE_MIN:
                out.append((i * hop, j * hop))
            i = j
        else:
            i += 1
    return out


def shot_text(sh: dict, words: list[dict]) -> tuple[list[str], str]:
    ws = [w["text"] for w in words if sh["s"] <= (w["t0"] + w["t1"]) / 2 <= sh["e"]]
    if ws:
        return ws, ws[-1]
    q = (sh["range"].get("quote") or "").split()
    return q, (q[-1] if q else "")


def emphasis_hits(tokens: list[str], extra: set[str]) -> list[str]:
    hits = []
    for t in tokens:
        n = norm(t)
        if not n:
            continue
        if any(c.isdigit() for c in n) or n in NUM_WORDS or n in UNIT_WORDS or n in CUE_WORDS or n in extra:
            hits.append(t.strip(".,!?;:"))
    return hits


# ================================================================ plan: núcleo
def build_shots(ranges: list[dict], master_key: str, words: list[dict], pauses, style: str,
                max_shot: float, min_eff: float) -> list[dict]:
    shots, prev = [], None
    for i, r in enumerate(ranges):
        s, e = float(r["start"]), float(r["end"])
        foreign = r["source"] != master_key
        if prev is None:
            kind = "start"
        elif foreign or prev["foreign"]:
            kind = "jump"
        elif s - prev["e"] > JUMP_GAP or s < prev["e"] - 0.02:
            kind = "jump"
        else:
            kind = "contig"
        sh = {"s": s, "e": e, "range": dict(r), "kind": kind, "foreign": foreign, "orig": None}
        shots.append(sh)
        prev = sh
    if style != "alternate" or max_shot <= 0:
        return shots
    out = []
    for sh in shots:
        if sh["foreign"] or sh["e"] - sh["s"] <= max_shot:
            out.append(sh)
            continue
        a, b = sh["s"], sh["e"]
        parts = math.ceil((b - a) / max_shot)
        cuts, last = [], a
        for j in range(1, parts):
            target = a + j * (b - a) / parts
            best = None
            for (p0, p1) in pauses:
                c = (p0 + p1) / 2
                if c - last < min_eff or b - c < min_eff:
                    continue
                if any(w["t0"] - 0.03 < c < w["t1"] + 0.03 for w in words):
                    continue
                if best is None or abs(c - target) < abs(best - target):
                    best = c
            if best is not None:
                cuts.append(best)
                last = best
        if not cuts:
            out.append(sh)
            continue
        edges = [a] + cuts + [b]
        oid = id(sh)
        orig = dict(sh["range"])
        for j in range(len(edges) - 1):
            rr = dict(sh["range"])
            rr["start"], rr["end"] = round(edges[j], 3), round(edges[j + 1], 3)
            if words:
                rr["quote"] = " ".join(w["text"] for w in words
                                       if edges[j] <= (w["t0"] + w["t1"]) / 2 <= edges[j + 1]) or rr.get("quote", "")
            elif j > 0:
                rr["quote"] = "…"
            out.append({"s": edges[j], "e": edges[j + 1], "range": rr, "foreign": False,
                        "kind": sh["kind"] if j == 0 else "pause", "orig": (oid, orig)})
    return out


def overlap(u: list[dict], s: float, e: float) -> float:
    return sum(max(0.0, min(e, x["t1"]) - max(s, x["t0"])) for x in u)


def plan_angles(shots: list[dict], mc: dict, words: list[dict], o) -> None:
    master = mc["master"]
    angles = [g for g in mc["angles"]
              if not (g["kind"] != "ai" and (not g.get("path") or not Path(g["path"]).exists()))]
    keyed = {g["key"]: g for g in angles}
    mk = master["key"]
    total = sum(sh["e"] - sh["s"] for sh in shots)
    extra = {norm(w) for w in (o.emphasis or []) if norm(w)}
    last_used = {g["key"]: -1 for g in angles}
    last_used[mk] = -1
    ai_used = 0.0
    prev = mk
    m = len(shots)
    n_non_ai = sum(1 for g in angles if g["kind"] != "ai")

    def eligible(g, sh, emph):
        s, e, d = sh["s"], sh["e"], sh["e"] - sh["s"]
        if g["kind"] == "ai":
            if emph:
                return False, "IA não em ênfase/número (pixels regenerados)"
            if d > o.ai_max_shot:
                return False, f"plano {d:.1f}s > {o.ai_max_shot}s (IA só em plano curto)"
            if g.get("closeup", 0) > o.ai_max_closeup:
                return False, "IA em close do rosto desligada (--ai-max-closeup)"
            if ai_used + d > o.ai_share * total:
                return False, "teto de IA atingido (--ai-share)"
            return True, ""
        off = float(g.get("offset", 0.0))
        if (s - off) < -1e-3 or (e - off) > float(g.get("duration", 0)) + 1e-3:
            return False, "ângulo não cobre este trecho"
        if (g.get("slip_ms") or 0) >= DRIFT_MAX_MS and not o.allow_drift:
            return False, f"deriva de {g['slip_ms']:.0f} ms"
        if g["kind"] == "virtual":
            u = overlap(g.get("unsafe", []), s, e)
            if u > 0.25:
                why = next((x["why"] for x in g["unsafe"] if min(e, x["t1"]) > max(s, x["t0"])), "inseguro")
                return False, f"close inseguro ({why})"
        return True, ""

    min_eff = max(o.min_shot, SWITCH_GAP + 0.3)
    run_len = 0.0            # duração efetiva do plano (corrida de mesmo ângulo) em curso
    run_start = 0
    for k, sh in enumerate(shots):
        toks, lastw = shot_text(sh, words)
        sh["emph"] = emphasis_hits(toks, extra)
        first = norm(toks[0]) if toks else ""
        sh["connective"] = (first in CONNECTIVES) or (lastw != "" and lastw[-1] not in ".!?…")
        d = sh["e"] - sh["s"]
        sh["flags"] = []
        if sh["foreign"]:
            sh["angle"], sh["reason"] = sh["range"]["source"], "fonte fora do master: mantida"
            prev = sh["angle"]
            continue
        notes = []
        if k == 0:
            ang, why = mk, "abertura no master"
        elif k == m - 1:
            ang, why = mk, "fechamento no master"
            if prev != mk and run_len < min_eff:     # o fechamento não pode deixar um plano curto para trás
                for x in range(run_start, k):
                    if not shots[x]["foreign"] and shots[x]["angle"] == prev:
                        shots[x]["angle"] = mk
                        shots[x]["reason"] += "; plano < min-shot → fechamento no master o absorve"
                        shots[x]["flags"] = [f for f in shots[x]["flags"] if f != "IA"]
                prev, run_len, run_start = mk, 0.0, run_start
        else:
            cand, rej = [], []
            for g in angles:
                ok, w_ = eligible(g, sh, bool(sh["emph"]))
                (cand if ok else rej).append(g if ok else (g["key"], w_))
            mand = o.style == "alternate" and sh["kind"] in ("jump", "pause")
            pool = [keyed[c["key"]] for c in cand] + [{"key": mk, "kind": "master", "role": "wide"}]
            if o.style == "content":
                det = [g for g in pool if g.get("role") == ROLE_CLOSE and g["kind"] != "ai"]
                ais = [g for g in pool if g["kind"] == "ai"]
                if sh["emph"] and det:
                    pick, why = det[0], f"ênfase ({', '.join(sh['emph'][:3])}) → detalhe"
                elif sh["emph"]:
                    pick, why = pool[-1], "ênfase, mas sem ângulo de detalhe disponível → master"
                elif ais and sh["connective"] and sh["kind"] in ("jump", "pause"):
                    pick, why = ais[0], "linha curta/conectiva (boca pouco exposta) → IA"
                else:
                    pick, why = pool[-1], "conteúdo sem ênfase → master"
                ang = pick["key"]
            elif not mand:
                ang, why = prev, "continua (sem corte seco)"
                if prev != mk and prev in keyed and not eligible(keyed[prev], sh, bool(sh["emph"]))[0]:
                    ang, why = mk, "continuação sem o ângulo anterior disponível → master"
            else:
                pool2 = [g for g in pool if g["key"] != prev] or pool

                def klass(g):
                    if sh["emph"]:
                        return 0 if (g.get("role") == ROLE_CLOSE and g["kind"] != "ai") else (2 if g["kind"] == "master" else 1)
                    if g["kind"] == "ai":
                        return 0 if sh["connective"] else 1
                    if g.get("role") == ROLE_CLOSE:
                        return 1
                    return 0
                pick = min(pool2, key=lambda g: (klass(g), last_used.get(g["key"], -1), pool.index(g)))
                ang = pick["key"]
                tag = "corte seco" if sh["kind"] == "jump" else "pausa em take longo"
                if sh["emph"] and pick.get("role") == ROLE_CLOSE:
                    why = f"{tag}; ênfase ({', '.join(sh['emph'][:3])}) → close"
                elif pick["kind"] == "ai":
                    why = f"{tag}; linha " + ("conectiva" if sh["connective"] else "curta") + " (boca pouco exposta) → IA"
                else:
                    why = f"{tag} → alterna"
            if ang != prev and run_len < min_eff and not (
                    prev != mk and prev in keyed and not eligible(keyed[prev], sh, bool(sh["emph"]))[0]):
                why = f"corte adiado: plano atual {run_len:.1f}s < min-shot (queria {ang}: {why})"
                ang = prev
            if sh["emph"] and not any(keyed.get(c, {}).get("role") == ROLE_CLOSE for c in [ang]):
                bad = [f"{kk}: {w_}" for kk, w_ in rej if keyed[kk].get("role") == ROLE_CLOSE]
                if bad:
                    notes.append("close indisponível (" + "; ".join(bad) + ")")
        if keyed.get(ang, {}).get("kind") == "ai":
            ai_used += d
            sh["flags"].append("IA")
        sh["angle"], sh["reason"] = ang, why + ("; " + "; ".join(notes) if notes else "")
        last_used[ang] = k
        if ang == prev and k > 0:
            run_len += d - SEAM_LOSS
        else:
            run_len, run_start = d - SEAM_LOSS, k
        prev = ang

    # --- rede de segurança: plano (corrida de mesmo ângulo) ainda curto é absorvido pelo vizinho

    def runs():
        rs, i = [], 0
        while i < m:
            j = i
            while j + 1 < m and shots[j + 1]["angle"] == shots[i]["angle"]:
                j += 1
            rs.append([i, j, sum(shots[x]["e"] - shots[x]["s"] - SEAM_LOSS for x in range(i, j + 1))])
            i = j + 1
        return rs
    for _ in range(4 * m + 4):
        rs = runs()
        if len(rs) < 2:
            break
        short = next((r for r in rs if r[2] < min_eff and not any(shots[x]["foreign"] for x in range(r[0], r[1] + 1))), None)
        if short is None:
            break
        ri = rs.index(short)
        nb = []
        if ri > 0:
            nb.append(rs[ri - 1])
        if ri < len(rs) - 1:
            nb.append(rs[ri + 1])
        if ri == 0:
            nb = [rs[1]]
        if ri == len(rs) - 1:
            nb = [rs[ri - 1]]
        tgt = max(nb, key=lambda r: r[2])
        newang = shots[tgt[0]]["angle"]
        for x in range(short[0], short[1] + 1):
            old = shots[x]["angle"]
            shots[x]["angle"] = newang
            shots[x]["reason"] += f"; plano < {min_eff:.1f}s → absorvido por {newang}"
            if "IA" in shots[x]["flags"]:
                shots[x]["flags"].remove("IA")
            shots[x]["reroute"] = old
    # abertura/fechamento sempre no master (pode ter sido sobrescrito pela absorção)
    for x in (0, m - 1):
        if not shots[x]["foreign"] and shots[x]["angle"] != mk:
            shots[x]["angle"] = mk
            shots[x]["reason"] += "; abertura/fechamento no master"


def collapse_splits(shots: list[dict]) -> list[dict]:
    out = []
    for sh in shots:
        p = out[-1] if out else None
        if (p and sh["orig"] and p["orig"] and sh["orig"][0] == p["orig"][0] and sh["angle"] == p["angle"]):
            p["e"] = sh["e"]
            rr = dict(sh["orig"][1])
            rr["start"], rr["end"] = round(p["s"], 3), round(p["e"], 3)
            p["range"] = rr
            continue
        out.append(sh)
    return out


# ============================================================ build do EDL
def master_key_in_edl(edl: dict, master_path: str) -> str:
    mp = Path(master_path).resolve()
    for k, v in edl["sources"].items():
        if Path(v if Path(v).is_absolute() else Path(v)).resolve() == mp:
            return k
    for k, v in edl["sources"].items():
        if Path(v).name == mp.name:
            return k
    die(f"o master {mp} não está em edl['sources'] — o EDL do master tem que ser montado sobre ele")


def jobs_file(edit: Path) -> Path:
    return edit / "ai_angles" / "jobs.json"


def build_edl(edit: Path, plan: dict, mc: dict) -> tuple[dict, list[str]]:
    master = mc["master"]
    mk = plan["master_key"]
    keyed = {g["key"]: g for g in mc["angles"]}
    jobs = json.loads(jobs_file(edit).read_text(encoding="utf-8")) if jobs_file(edit).exists() else []
    edl = json.loads(json.dumps(plan["edl_base"]))
    edl.pop("jcut_timeline", None)
    sources = dict(edl["sources"])
    audio_sources = dict(edl.get("audio_sources") or {})
    warns, ranges = [], []

    def emit(sh, s, e, src_key, src_path, off, ang, extra_reason="", quote=None):
        r = dict(sh["range"])
        r["master_source"], r["master_start"], r["master_end"] = mk, round(s, 3), round(e, 3)
        if src_key == mk:
            r["source"], r["start"], r["end"] = mk, round(s, 3), round(e, 3)
        else:
            sources[src_key] = src_path
            audio_sources[src_key] = {"path": master["path"], "offset": round(-off, 6)}
            r["source"], r["start"], r["end"] = src_key, round(s - off, 6), round(e - off, 6)
        if quote is not None:
            r["quote"] = quote
        r["angle"] = ang
        if ang != sh["angle"]:
            r["angle_planned"] = sh["angle"]
        r["angle_reason"] = sh["reason"] + extra_reason
        if "IA" in sh.get("flags", []):
            r["ai"] = True
        ranges.append(r)

    for sh in plan["shots"]:
        ang = sh["angle"]
        s, e = sh["s"], sh["e"]
        if sh.get("foreign"):
            ranges.append(dict(sh["range"]))
            continue
        if ang == mk:
            emit(sh, s, e, mk, None, 0.0, mk)
            continue
        g = keyed.get(ang)
        if g is None:
            warns.append(f"ângulo {ang} sumiu do multicam.json — master em {s:.2f}–{e:.2f}")
            emit(sh, s, e, mk, None, 0.0, mk, f"; {ang} ausente → master")
            continue
        if g["kind"] != "ai":
            off = float(g["offset"])
            if (s - off) < -1e-3 or (e - off) > float(g["duration"]) + 1e-3 or not Path(g["path"]).exists():
                warns.append(f"{ang} não cobre {s:.2f}–{e:.2f} — master")
                emit(sh, s, e, mk, None, 0.0, mk, f"; {ang} não cobre → master")
            else:
                emit(sh, s, e, ang, g["path"], off, ang)
            continue
        mine = sorted((j for j in jobs if j["angle"] == ang and j.get("conformed")
                       and j["master_end"] > s + 1e-3 and j["master_start"] < e - 1e-3),
                      key=lambda j: j["master_start"])
        pieces, cur = [], s
        for j in mine:
            a_, b_ = max(s, j["master_start"]), min(e, j["master_end"])
            if a_ > cur + 1e-3:
                pieces.append((cur, a_, None))
            pieces.append((a_, b_, j))
            cur = b_
        if e > cur + 1e-3:
            pieces.append((cur, e, None))
        for n, (a_, b_, j) in enumerate(pieces):
            q = sh["range"].get("quote") if n == 0 else "…"
            if j is None:
                warns.append(f"IA {ang} sem resultado para {a_:.2f}–{b_:.2f} — master")
                emit(sh, a_, b_, mk, None, 0.0, mk, "; IA pendente/falhou → master", quote=q)
            else:
                emit(sh, a_, b_, f"{ang}__{j['id']}", j["conformed"], float(j["file_start"]), ang, quote=q)
    edl["sources"], edl["audio_sources"], edl["ranges"] = sources, audio_sources, ranges
    edl["multicam"] = {"master": mk, "style": plan["style"], "min_shot": plan["min_shot"],
                       "angles": sorted({r["angle"] for r in ranges})}
    return edl, warns


def print_table(edl: dict) -> None:
    print(f"\n  {'#':>2}  {'master (s)':<15} {'dur':>5}  {'ângulo':<22} motivo")
    for i, r in enumerate(edl["ranges"]):
        if "master_start" not in r:
            print(f"  {i:>2}  (fonte fora do master) {r['source']}")
            continue
        d = r["master_end"] - r["master_start"]
        ang = r["angle"] + (" [IA]" if r.get("ai") and r["angle"] == r.get("angle_planned", r["angle"]) else "")
        if "angle_planned" in r:
            ang += f" (plan: {r['angle_planned']})"
        print(f"  {i:>2}  {r['master_start']:7.2f}-{r['master_end']:<7.2f} {d:5.1f}  {ang:<22} {r['angle_reason']}")
    sw = [i for i in range(1, len(edl["ranges"]))
          if edl["ranges"][i].get("angle") != edl["ranges"][i - 1].get("angle")]
    print(f"\n  {len(edl['ranges'])} ranges · {len(sw)} trocas de ângulo · ângulos: "
          + ", ".join(f"{k}={sum(1 for r in edl['ranges'] if r.get('angle') == k)}"
                      for k in sorted({r.get('angle', '?') for r in edl['ranges']})))


def write_outputs(edit: Path, plan: dict, mc: dict, apply: bool, out_name: str) -> dict:
    edl, warns = build_edl(edit, plan, mc)
    for w in warns:
        print(f"  AVISO: {w}")
    print_table(edl)
    (edit / "multicam_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    out = edit / out_name
    out.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  EDL: {out}")
    if apply:
        cur = edit / "edl.json"
        if cur.exists():
            cj = json.loads(cur.read_text(encoding="utf-8"))
            if not cj.get("multicam"):
                bak = edit / "edl.before_multicam.json"
                if bak.exists():
                    bak = edit / f"edl.before_multicam.{time.strftime('%Y%m%d-%H%M%S')}.json"
                shutil.copy2(cur, bak)
                print(f"  backup: {bak}")
        cur.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  edl.json agora é o EDL multicam (--apply)")
    else:
        print("  edl.json NÃO foi tocado (use --apply para trocar, com backup)")
    return edl


# ================================================================== plan
def cmd_plan(a) -> None:
    edit = a.edit.resolve()
    mc = load_mc(edit)
    if not mc.get("master"):
        die("multicam.json sem master")
    if not any(g for g in mc["angles"]):
        die("nenhum ângulo registrado — rode sync / virtual / add-ai")
    base = a.edl
    if base is None:
        cur = edit / "edl.json"
        bak = edit / "edl.before_multicam.json"
        base = bak if (cur.exists() and json.loads(cur.read_text(encoding="utf-8")).get("multicam") and bak.exists()) else cur
    if not base.exists():
        die(f"{base} não existe (EDL do master da Fase 1)")
    edl = json.loads(base.read_text(encoding="utf-8"))
    if edl.get("multicam"):
        die(f"{base} já é um EDL multicam — passe o EDL do master em --edl")
    mk = master_key_in_edl(edl, mc["master"]["path"])
    mc["master"]["edl_key"] = mk
    words = load_words(edit, mk, a.transcript)
    if not words:
        print("  aviso: sem transcrição por palavra — ênfase pelo `quote`, pausas só pelo áudio")
    pauses = master_pauses(Path(mc["master"]["path"]))
    style = a.style
    max_shot = a.max_shot if a.max_shot is not None else (MAX_SHOT if style == "alternate" else 0.0)
    min_eff = max(a.min_shot, SWITCH_GAP + 0.3)
    shots = build_shots(edl["ranges"], mk, words, pauses, style, max_shot, min_eff)
    plan_angles(shots, mc, words, a)
    shots = collapse_splits(shots)
    plan = {"version": 1, "master_key": mk, "style": style, "min_shot": a.min_shot,
            "max_shot": max_shot, "edl_source": str(base), "master": mc["master"],
            "edl_base": {k: v for k, v in edl.items() if k not in ("ranges", "jcut_timeline")},
            "shots": [{"s": round(sh["s"], 3), "e": round(sh["e"], 3), "range": sh["range"], "angle": sh["angle"],
                       "reason": sh["reason"], "flags": sh.get("flags", []), "kind": sh["kind"],
                       "foreign": sh["foreign"], "emph": sh.get("emph", [])} for sh in shots]}
    print(f"  estilo {style} · min-shot {a.min_shot}s (efetivo {min_eff:.1f}s) · max-shot {max_shot or 'sem divisão'}"
          f" · {len(pauses)} pausas medidas · EDL base {base.name}")
    write_outputs(edit, plan, mc, a.apply, a.out)
    ai_s = sum(s["e"] - s["s"] for s in plan["shots"] if "IA" in s["flags"])
    if ai_s:
        print(f"  {ai_s:.1f} s planejados em ângulos de IA → `multicam.py ai-prep {edit}` para gerar as janelas")


def cmd_build(a) -> None:
    edit = a.edit.resolve()
    mc = load_mc(edit)
    p = edit / "multicam_plan.json"
    if not p.exists():
        die("multicam_plan.json não existe — rode `plan` primeiro")
    write_outputs(edit, json.loads(p.read_text(encoding="utf-8")), mc, a.apply, a.out)


# ================================================================== ai-prep
def cmd_ai_prep(a) -> None:
    edit = a.edit.resolve()
    mc = load_mc(edit)
    plan = json.loads((edit / "multicam_plan.json").read_text(encoding="utf-8")) \
        if (edit / "multicam_plan.json").exists() else die("rode `plan` primeiro")
    master = mc["master"]
    fps, mdur = float(master["fps"]), float(master["duration"])
    keyed = {g["key"]: g for g in mc["angles"]}
    shots = plan["shots"]
    pauses = master_pauses(Path(master["path"]))
    # 1) trechos de IA adjacentes (mesmo ângulo, vão ≤ 0.5 s no master) viram uma pista
    stretches, cur = [], None
    for i, sh in enumerate(shots):
        g = keyed.get(sh["angle"])
        if sh.get("foreign") or not g or g["kind"] != "ai":
            cur = None
            continue
        if cur and cur["angle"] == sh["angle"] and sh["s"] - cur["e"] <= 0.5:
            cur["e"] = sh["e"]
            cur["shots"].append(i)
            cur["edges"].append(sh["s"])
            cur["edges"].append(sh["e"])
        else:
            cur = {"angle": sh["angle"], "s": sh["s"], "e": sh["e"], "shots": [i], "edges": [sh["s"], sh["e"]]}
            stretches.append(cur)
    if not stretches:
        print("  o plano não deu nenhum trecho a ângulos de IA — nada a gerar")
        return
    # 2) janelas ≤ AI_WINDOW cortadas em emendas/pausas (nunca no meio de palavra)
    jobs = []
    for st in stretches:
        cuts = sorted(set(round(x, 3) for x in st["edges"]) |
                      {round((p0 + p1) / 2, 3) for p0, p1 in pauses if st["s"] + 1.0 < (p0 + p1) / 2 < st["e"] - 1.0})
        c0 = st["s"]
        while c0 < st["e"] - 1e-3:
            if st["e"] - c0 <= a.window:
                c1 = st["e"]
            else:
                ok = [c for c in cuts if c0 + 1.0 <= c <= c0 + a.window]
                if ok:
                    c1 = max(ok)
                else:
                    c1 = c0 + a.window
                    print(f"  aviso: sem pausa para cortar {c0:.2f}–{c0 + a.window:.2f}; corte duro em {c1:.2f}")
            jobs.append({"angle": st["angle"], "master_start": round(c0, 3), "master_end": round(c1, 3),
                         "shots": [i for i in st["shots"] if shots[i]["e"] > c0 + 1e-3 and shots[i]["s"] < c1 - 1e-3]})
            c0 = c1
    # 3) exporta cada janela do master (resolução da fonte, CFR) com folga de 0,3 s
    adir = edit / "ai_angles"
    adir.mkdir(parents=True, exist_ok=True)
    old = json.loads(jobs_file(edit).read_text(encoding="utf-8")) if jobs_file(edit).exists() else []
    for n, j in enumerate(jobs, 1):
        g = keyed[j["angle"]]
        j["id"] = f"w{n:02d}"
        fs = max(0.0, j["master_start"] - AI_HANDLE)
        fe = min(mdur, j["master_end"] + AI_HANDLE)
        k0 = math.floor(fs * fps + 1e-6)
        nfr = max(1, math.ceil((fe - k0 / fps) * fps - 1e-6))
        j["file_start"] = round(k0 / fps, 6)
        j["file_frames"] = nfr
        j["file_duration"] = round(nfr / fps, 6)
        j["handle"] = AI_HANDLE
        j["rotate"], j["vertical"], j["closeup"] = g["rotate"], g["vertical"], g["closeup"]
        j["file"] = str(adir / f"{j['id']}_{j['angle']}_src.mp4")
        same = next((o for o in old if o["angle"] == j["angle"] and abs(o["master_start"] - j["master_start"]) < 1e-3
                     and abs(o["master_end"] - j["master_end"]) < 1e-3 and o.get("rotate") == j["rotate"]
                     and o.get("vertical") == j["vertical"] and o.get("closeup") == j["closeup"]), None)
        if same and same.get("status") in ("done", "failed"):
            for f in ("status", "result", "note"):
                if f in same:
                    j[f] = same[f]
            print(f"  {j['id']}: mantém status '{same['status']}' do jobs.json anterior")
        else:
            j["status"], j["result"] = "pending", None
        vf = []
        if a.max_height:
            vf = ["-vf", f"scale=-2:'min({a.max_height},ih)'"]
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{j['file_start']:.6f}", "-i", master["path"],
               "-frames:v", str(nfr), *vf, "-fps_mode", "cfr", "-r", f"{fps:.6f}",
               "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-t", f"{j['file_duration']:.6f}", j["file"]]
        run(cmd)
    jobs_file(edit).write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  {len(jobs)} janela(s) em {adir} · {jobs_file(edit)}")
    for ang in sorted({j["angle"] for j in jobs}):
        js = [j for j in jobs if j["angle"] == ang]
        print(f"    {ang}: {len(js)} job(s), {sum(j['master_end'] - j['master_start'] for j in js):.1f} s úteis, "
              f"{sum(j['file_duration'] for j in js):.1f} s enviados (com folgas)")
    print(f"    TOTAL {sum(j['file_duration'] for j in jobs):.1f} s enviados · "
          f"{sum(j['master_end'] - j['master_start'] for j in jobs):.1f} s úteis")
    print("  Depois de gerar: preencha `status: done` e `result: <arquivo>` em cada job e rode `ai-assemble`.")


# ============================================================= ai-assemble
def cmd_ai_assemble(a) -> None:
    edit = a.edit.resolve()
    mc = load_mc(edit)
    if not jobs_file(edit).exists():
        die("ai_angles/jobs.json não existe — rode `ai-prep`")
    jobs = json.loads(jobs_file(edit).read_text(encoding="utf-8"))
    master = mc["master"]
    fps = float(master["fps"])
    W, H = (int(x) for x in a.size.lower().split("x")) if a.size else out_size(master["width"], master["height"])
    done = pend = fail = 0
    for j in jobs:
        j.pop("conformed", None)
        if j.get("status") != "done" or not j.get("result"):
            if j.get("status") == "failed":
                fail += 1
            else:
                pend += 1
            continue
        res = Path(j["result"])
        if not res.exists():
            print(f"  {j['id']}: resultado {res} não existe — fica pendente")
            j["status"], j["note"] = "failed", "arquivo do resultado não encontrado"
            fail += 1
            continue
        ri = probe(res)
        n = int(j["file_frames"])
        want = n / fps
        diff = ri["duration"] - want
        if diff < -0.5:
            print(f"  {j['id']}: resultado de {ri['duration']:.2f}s para janela de {want:.2f}s — curto demais, "
                  f"não vou esticar a fala; marcado como failed (master no lugar)")
            j["status"], j["note"] = "failed", f"resultado {ri['duration']:.2f}s < janela {want:.2f}s"
            fail += 1
            continue
        if abs(ri["width"] / ri["height"] - W / H) > 0.02:
            print(f"  {j['id']}: aviso: proporção do resultado {ri['width']}x{ri['height']} ≠ {W}x{H} — "
                  f"encaixado com barras (peça a IA na proporção do master)")
        out = edit / "ai_angles" / f"{j['id']}_{j['angle']}_conf.mp4"
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={fps:.6f},tpad=stop_mode=clone:stop_duration=3,"
              f"format=yuv420p,setsar=1")
        # vídeo do resultado + SOM do master (a janela original), para o render medir
        # o silêncio das emendas no áudio verdadeiro; o áudio final vem do master via audio_sources
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(res), "-i", j["file"], "-map", "0:v:0", "-map", "1:a:0?",
               "-vf", vf, "-frames:v", str(n), "-c:v", "libx264", "-crf", "16", "-preset", "fast",
               "-c:a", "aac", "-b:a", "192k", "-t", f"{want:.6f}", str(out)]
        run(cmd)
        chk = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.strip()
        got = int(chk) if chk.isdigit() else -1
        rf = round(ri["duration"] * fps)
        note = ""
        if rf < n:
            note = f"completado com {n - rf} frame(s) repetidos do último" + (" (!) mais de 3 frames: confira a boca" if n - rf > 3 else "")
        elif rf > n:
            note = f"aparado em {rf - n} frame(s) no fim"
        if got != n:
            print(f"  {j['id']}: ERRO frames {got} ≠ {n}")
            j["status"], j["note"] = "failed", f"conformação deu {got} frames, esperado {n}"
            fail += 1
            continue
        j["conformed"] = str(out)
        j["note"] = note
        done += 1
        print(f"  {j['id']} {j['angle']}: {n} frames exatos ({W}x{H}@{fps:g}) {note}")
    jobs_file(edit).write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    if pend or fail:
        print(f"  AVISO: {pend} job(s) pendente(s) e {fail} falho(s) — esses trechos ficam no master")
    print(f"  {done} janela(s) conformada(s)")
    p = edit / "multicam_plan.json"
    if not p.exists():
        die("multicam_plan.json não existe — rode `plan`")
    write_outputs(edit, json.loads(p.read_text(encoding="utf-8")), mc, a.apply, a.out)


# =================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("sync", help="offset de câmeras reais contra o master")
    s.add_argument("edit", type=Path)
    s.add_argument("--master", type=Path, required=True)
    s.add_argument("--angles", type=Path, nargs="+", required=True)
    s.add_argument("--roles", nargs="+", help="um papel por ângulo (close | alt); padrão alt")
    s.set_defaults(fn=cmd_sync)

    v = sp.add_parser("virtual", help="câmera virtual (punch-in) de um master ≥ 4K")
    v.add_argument("edit", type=Path)
    v.add_argument("--source", type=Path, required=True)
    v.add_argument("--zoom", type=float, default=1.6)
    v.add_argument("--focus", default="face", help="face | center | x,y (frações)")
    v.add_argument("--faces", type=Path, help="faces.json no tempo/dimensão do master (senão detecta e guarda cache)")
    v.add_argument("--key")
    v.add_argument("--out-height", type=int, default=1080, help="lado curto da saída (padrão 1080)")
    v.add_argument("--out-size", help="WxH (use o tamanho do master se for renderizar com --keep-resolution)")
    v.set_defaults(fn=cmd_virtual)

    ai = sp.add_parser("add-ai", help="registra preset de ângulo de IA")
    ai.add_argument("edit", type=Path)
    ai.add_argument("key")
    ai.add_argument("--rotate", type=float, default=0)
    ai.add_argument("--vertical", type=float, default=0)
    ai.add_argument("--closeup", type=float, default=0)
    ai.set_defaults(fn=cmd_add_ai)

    st = sp.add_parser("status")
    st.add_argument("edit", type=Path)
    st.set_defaults(fn=cmd_status)

    p = sp.add_parser("plan", help="atribui ângulos aos ranges do EDL do master")
    p.add_argument("edit", type=Path)
    p.add_argument("--edl", type=Path, help="EDL do master (padrão: edl.json, ou edl.before_multicam.json)")
    p.add_argument("--min-shot", type=float, default=MIN_SHOT)
    p.add_argument("--max-shot", type=float, default=None, help="parte takes contínuos maiores numa pausa (alternate: 7)")
    p.add_argument("--style", choices=("alternate", "content"), default="alternate")
    p.add_argument("--transcript", type=Path)
    p.add_argument("--emphasis", nargs="+", help="palavras extras de ênfase")
    p.add_argument("--allow-drift", action="store_true")
    p.add_argument("--ai-max-shot", type=float, default=AI_MAX_SHOT)
    p.add_argument("--ai-share", type=float, default=AI_SHARE)
    p.add_argument("--ai-max-closeup", type=float, default=10.0, help="ignora ângulos de IA com closeup acima disto")
    p.add_argument("--out", default="edl.multicam.json")
    p.add_argument("--apply", action="store_true", help="troca edl.json (backup em edl.before_multicam.json)")
    p.set_defaults(fn=cmd_plan)

    b = sp.add_parser("build", help="refaz o EDL a partir de multicam_plan.json")
    b.add_argument("edit", type=Path)
    b.add_argument("--out", default="edl.multicam.json")
    b.add_argument("--apply", action="store_true")
    b.set_defaults(fn=cmd_build)

    pr = sp.add_parser("ai-prep", help="janelas dos trechos de IA → ai_angles/jobs.json")
    pr.add_argument("edit", type=Path)
    pr.add_argument("--window", type=float, default=AI_WINDOW)
    pr.add_argument("--max-height", type=int, help="reduz as janelas enviadas (padrão: resolução da fonte)")
    pr.set_defaults(fn=cmd_ai_prep)

    asm = sp.add_parser("ai-assemble", help="conforma resultados da IA e refaz o EDL")
    asm.add_argument("edit", type=Path)
    asm.add_argument("--size", help="WxH das janelas conformadas (padrão: lado curto 1080)")
    asm.add_argument("--out", default="edl.multicam.json")
    asm.add_argument("--apply", action="store_true")
    asm.set_defaults(fn=cmd_ai_assemble)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
