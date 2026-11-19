"""Rank the clips of a long transcribed video by viral potential.

v2 (2026-11-19), rebuilt after a blind test on 4 videos (Marketing Wellington/
teste-viral-score-gta6.md). The v1 text/audio signals ranked clips
*against* the audience in all 4 videos (Spearman -0.11 to -0.22), and because
they also picked which clips reached the judge, the strongest moments never got
judged. So v2 changes the order of work:

  1. BLOCKS: the whole video is cut into non-overlapping blocks of
     --min/--max-seconds, closed on sentence ends and preferably right before a
     topic opener ("Bom, galera, ..."). Every second of the video reaches the
     judge; nothing is pre-ranked.
  2. NO-SPEECH STRETCHES: where the transcript falls under 1.6 words/s over a
     6 s window for 8 s or more, nobody is really talking (trailer, gameplay,
     music; Whisper fills these with invented words like "Legenda por ..."). The
     invented words are dropped and the packet shows "[25 s sem fala, áudio
     alto]", so the judge can weigh what the speech around it says is on screen.
     In the 4-video test the biggest replay peak of one video was exactly this.
  3. FILTERS (the only job left for signals): sponsor reads, the outro, and
     near-silent blocks are set aside before judging and listed with the reason.
  4. JUDGE (the agent running Prisma, no API key): `--packet` writes
     `<edit>/viral/judge_packet.md`, rubric + blocks as text only, shuffled, with
     random labels and no timestamps or audience data. The judge writes
     `judge.json`; `--judge` merges it. Score = judge total (0-100).
  5. AUDIENCE (answer key, never part of the score): YouTube "most replayed"
     heatmap from the `.info.json` that ingest_url.py saves next to the video.
     The first --heat-skip seconds (default 10) are ignored, because the opening
     of every video replays high. Reported as rank correlation, top-3 lift over
     the average block, and where each of the 3 biggest peaks landed in the rank.

Rubric ideas come from the clipping tools in references/external-video-skills.md
(#28-#33): hook -> self-containment -> payoff ordering (autoclip-artbyjazi, MIT)
and four separate sub-scores instead of one opaque number (the supoclip idea; no
code or text taken from it, as its license is noncommercial).

Usage:
    uv run python helpers/viral_score.py <video> --edit-dir <edit> --packet
    # judge reads <edit>/viral/judge_packet.md and writes <edit>/viral/judge.json
    uv run python helpers/viral_score.py <video> --edit-dir <edit> --judge <edit>/viral/judge.json
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
import random
import re
import subprocess
from pathlib import Path

import numpy as np

sys_path = Path(__file__).resolve().parent
_sys.path.insert(0, str(sys_path))
from clip_finder import _load_prisma_transcript, _probe_duration, clip_duration_bounds  # noqa: E402

END_PUNCT = (".", "!", "?", "…")
MARKER_WORDS = {"bom", "então", "entao", "olha", "só", "so", "beleza", "certo", "ok", "okay",
                "galera", "gente", "pessoal", "cara", "pois", "é", "agora", "vamos", "lá", "la",
                "alright", "okay", "so", "now", "guys"}
# One STRONG phrase marks a sponsor read; WEAK ones need two. A block sitting
# between two sponsor blocks is part of the read (2026-11-19: an English read ran
# across 3 blocks and only the 1st named the sponsor).
SPONSOR_STRONG = ["patrocinador", "patrocínio", "patrocinio", "patrocinado", "sponsor of",
                  "sponsored by", "today's sponsor", "is sponsored", "this video is brought"]
SPONSOR = ["sorteio", "cupom", "link na descrição", "link na descricao", "código", "codigo",
           "desconto", "parceria", "parceiro", "promoç", "promoc", "use code", "giveaway",
           "in the description", "qr code", "download the game", "free of charge", "sign up today"]
OUTRO = ["se inscreve", "se inscreva", "se inscrevam", "inscreva-se", "deixa o like", "deixe o like",
         "deixa seu like", "ativa o sininho", "ative o sininho", "até o próximo", "até a próxima",
         "ate o proximo", "ate a proxima", "subscribe", "see you next", "see you guys",
         "comenta aí", "comenta aqui"]

# No-speech detection: measured 2026-11-19 on 4 GTA 6 videos (~2.8-3.5 words/s
# of speech). Inside a trailer Whisper produced ~0.8 invented words/s.
NOSPEECH_WINDOW_S = 6
NOSPEECH_MAX_WPS = 1.6
NOSPEECH_MIN_S = 8


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _ts(s: float) -> str:
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# --- audio ------------------------------------------------------------------

def audio_db_per_bin(video: Path, bin_s: float = 0.5, sr: int = 8000) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"], check=True, capture_output=True).stdout
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(sr * bin_s)
    nb = len(pcm) // hop
    if nb == 0:
        return np.zeros(1)
    frames = pcm[: nb * hop].reshape(nb, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(rms)


# --- no-speech stretches ----------------------------------------------------

def nospeech_stretches(words: list[dict], duration: float) -> list[tuple[float, float]]:
    """(start, end) of stretches where nobody is really talking: under
    NOSPEECH_MAX_WPS words/s over a NOSPEECH_WINDOW_S window, lasting at least
    NOSPEECH_MIN_S. The video's head and tail before the first / after the last
    word count too."""
    nb = int(duration) + 1
    counts = np.zeros(nb)
    for w in words:
        counts[min(nb - 1, int(w["s"]))] += 1
    k = NOSPEECH_WINDOW_S
    avg = np.convolve(counts, np.ones(k) / k, mode="same")
    low = avg < NOSPEECH_MAX_WPS
    out, i = [], 0
    while i < nb:
        if not low[i]:
            i += 1
            continue
        j = i
        while j < nb and low[j]:
            j += 1
        if j - i >= NOSPEECH_MIN_S:
            out.append((float(i), float(min(j, duration))))
        i = j
    return out


# --- segments and blocks ----------------------------------------------------

def sentence_segments(words: list[dict], gap: float = 0.6) -> list[dict]:
    """Phrases split at a pause >= `gap` OR at a sentence end (. ! ? …).
    A creator who never pauses yields 100 s+ pause-only segments (measured
    2026-11-19), so sentence ends must split too."""
    segs, cur = [], []
    for w in words:
        if cur and w["s"] - cur[-1]["e"] >= gap:
            segs.append(cur); cur = []
        cur.append(w)
        if w["w"].rstrip().endswith(END_PUNCT):
            segs.append(cur); cur = []
    if cur:
        segs.append(cur)
    return [{"start": s[0]["s"], "end": s[-1]["e"], "text": " ".join(x["w"] for x in s),
             "n_words": len(s)} for s in segs]


def _opens_topic(text: str) -> bool:
    """'Bom, galera, ...', 'Olha só, ...', 'Então, gente, ...': on a 32-min pt-BR
    video (2026-11-19) these opened a new topic right before 2 of 3 replay peaks."""
    toks = text.split()[:4]
    n = 0
    for t in toks:
        if re.sub(r"[^\wà-úÀ-Ú]", "", t.lower()) in MARKER_WORDS:
            n += 1
            continue
        break
    return n > 0 and any("," in t for t in toks[:n])


def build_segments(words: list[dict], duration: float, db: np.ndarray, bin_s: float) -> list[dict]:
    """Speech segments plus one pseudo-segment per no-speech stretch (its
    invented words removed), in time order."""
    stretches = nospeech_stretches(words, duration)
    med = float(np.median(db)) if len(db) else -40.0

    def inside(w):
        return any(a <= w["s"] < b for a, b in stretches)

    segs = sentence_segments([w for w in words if not inside(w)])
    for a, b in stretches:
        seg = db[int(a / bin_s): max(int(b / bin_s), int(a / bin_s) + 1)]
        level = float(np.mean(seg)) - med if len(seg) else -99.0
        loud = level > -6
        segs.append({"start": a, "end": b, "n_words": 0, "nospeech": True, "loud": loud,
                     "text": f"[{b - a:.0f} s sem fala, "
                             f"{'áudio alto: trailer, gameplay ou música' if loud else 'silêncio'}]"})
    segs.sort(key=lambda s: s["start"])
    return segs


def build_blocks(segs: list[dict], duration: float, lo: float, hi: float) -> list[dict]:
    """Greedy, non-overlapping blocks covering the whole video. A block closes on
    a sentence end once it reaches `lo`, as soon as it reaches the midpoint of
    the band or right before a topic opener, and always before it would pass
    `hi` (one segment longer than `hi` stays whole). A loud no-speech stretch
    sticks to the speech around it: the lead-in and the reaction belong to the
    same clip."""
    target = (lo + hi) / 2
    blocks, cur = [], []

    def close():
        if cur:
            blocks.append(cur[:])
            cur.clear()

    for sg in segs:
        if cur:
            last = cur[-1]
            dur_now = last["end"] - cur[0]["start"]
            dur_with = sg["end"] - cur[0]["start"]
            visual = sg.get("nospeech") and sg.get("loud")
            after_visual = last.get("nospeech") and last.get("loud")
            ends = last.get("nospeech") or last["text"].rstrip().endswith(END_PUNCT)
            if visual or after_visual:
                if dur_with > hi + 60:
                    close()
            elif dur_with > hi and dur_now >= 5:
                close()
            elif ends and dur_now >= lo and dur_now >= target:
                close()
            elif ends and dur_now >= 10 and _opens_topic(sg["text"]):
                # A new topic starts a new block even if this one is short; a
                # short leftover is folded into the previous block when it fits.
                if dur_now < lo and blocks and cur[-1]["end"] - blocks[-1][0]["start"] <= hi + 5:
                    blocks[-1].extend(cur)
                    cur.clear()
                else:
                    close()
        cur.append(sg)
    close()

    out = []
    prev_end = 0.0
    for i, b in enumerate(blocks, 1):
        s = max(prev_end, b[0]["start"] - 0.15)
        e = min(duration, b[-1]["end"] + 0.25)
        prev_end = e
        out.append({"id": f"b{i:02d}", "start_s": round(s, 3), "end_s": round(e, 3),
                    "duration_s": round(e - s, 3),
                    "text": " ".join(x["text"] for x in b).strip(),
                    "n_words": sum(x["n_words"] for x in b),
                    "nospeech_s": round(sum(x["end"] - x["start"] for x in b if x.get("nospeech")), 1),
                    "visual": any(x.get("nospeech") and x.get("loud") for x in b),
                    "ends_sentence": b[-1].get("nospeech", False) or b[-1]["text"].rstrip().endswith(END_PUNCT)})
    return out


# --- filters (the only job left for text signals) ---------------------------

def apply_filters(blocks: list[dict], duration: float) -> None:
    for b in blocks:
        low = b["text"].lower()
        sponsor = {k for k in SPONSOR if k in low}
        outro = {k for k in OUTRO if k in low}
        strong = {k for k in SPONSOR_STRONG if k in low}
        reason = None
        if strong or len(sponsor) >= 2:
            reason = "patrocínio (" + ", ".join(sorted(strong | sponsor)[:3]) + ")"
        elif outro and (b["start_s"] >= 0.9 * duration or len(outro) >= 2):
            reason = "despedida / pedido de inscrição"
        elif b["n_words"] < 12 and not b["visual"]:
            reason = "quase sem fala"
        b["excluded"] = reason
    is_sp = [bool(b["excluded"] and b["excluded"].startswith("patrocínio")) for b in blocks]
    for i in range(1, len(blocks) - 1):
        if not blocks[i]["excluded"] and is_sp[i - 1] and is_sp[i + 1]:
            blocks[i]["excluded"] = "patrocínio (entre dois blocos de patrocínio)"


# --- audience answer key ----------------------------------------------------

def load_heatmap(video: Path, info_json: Path | None) -> list[dict]:
    path = info_json
    if path is None:
        sibs = sorted(video.parent.glob("*.info.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        path = sibs[0] if sibs else None
    if not path or not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("heatmap") or []


def heat_for(c: dict, heat: list[dict], skip_s: float) -> float | None:
    """Time-weighted heatmap over the clip, ignoring the first `skip_s` seconds."""
    tot = acc = 0.0
    a0 = max(c["start_s"], skip_s)
    for h in heat:
        ov = max(0.0, min(c["end_s"], h["end_time"]) - max(a0, h["start_time"]))
        acc += ov * h["value"]
        tot += ov
    return round(acc / tot, 3) if tot else None


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3)


# --- judge ------------------------------------------------------------------

RUBRIC = """# Pacote do juiz: potencial de viralização

Você é o juiz. Os trechos abaixo cobrem o vídeo inteiro, sem sobreposição. Avalie cada um **só pelo
texto**: não há horários nem dados de audiência, de propósito, e a ordem foi embaralhada. Pense em
alguém rolando o feed sem nunca ter visto o vídeo.

Dê quatro notas de 0 a 25 (somam o total de 0 a 100):

- **gancho**: as primeiras palavras fazem parar de rolar? Pergunta, contradição, número concreto,
  promessa clara ou tensão já em andamento valem muito. Abrir com "então", "e aí", resposta a uma
  pergunta que ninguém ouviu, ou "isso/esse" sem dizer o quê, vale pouco.
- **retencao**: a pessoa assiste até o fim? Precisa se entender sozinho (sem contexto anterior) e ter
  um desfecho que chega: conclusão, virada, conselho concreto, revelação, emoção real.
- **valor**: a pessoa sai sabendo ou sentindo algo que não sabia ou não sentia?
- **compartilhamento**: dá vontade de mandar para alguém, comentar ou discordar?

**Trechos sem fala.** `[25 s sem fala, áudio alto: trailer, gameplay ou música]` quer dizer que o
vídeo mostra alguma coisa nesse intervalo e ninguém fala. Julgue pelo que a fala em volta diz que está
na tela. Se for o que todo mundo quer ver (trailer novo, revelação, cena marcante, reação forte),
o trecho pode valer muito, mesmo com pouco texto. `[… silêncio]` é só uma pausa.

Também informe `tipo_gancho` (pergunta | contradição | número | revelação | conselho | humor |
opinião forte | história | visual | nenhum) e `motivo` (uma frase). Se o trecho não se sustenta
sozinho, `retencao` fica no máximo 8.

Responda gravando `judge.json` nesta pasta, uma lista:
[{"id": "T42", "gancho": 18, "retencao": 15, "valor": 12, "compartilhamento": 14,
  "tipo_gancho": "pergunta", "motivo": "..."}]
"""


def write_packet(blocks: list[dict], out_dir: Path) -> Path:
    """Blind packet: random labels, shuffled order, text only. The label→id map
    goes to `.blind_map.json`, which the judge must not open; merge_judge reads it."""
    rng = random.SystemRandom()
    items = blocks[:]
    rng.shuffle(items)
    labels = rng.sample(range(100, 1000), len(items))
    blind, lines = {}, [RUBRIC, "\n## Trechos\n"]
    for c, n in zip(items, labels):
        tag = f"T{n}"
        blind[tag] = c["id"]
        lines.append(f"### {tag} ({c['duration_s']:.0f} s)\n\n{c['text']}\n")
    (out_dir / ".blind_map.json").write_text(json.dumps(blind), encoding="utf-8")
    p = out_dir / "judge_packet.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def merge_judge(blocks: list[dict], judge_path: Path) -> int:
    raw = json.loads(judge_path.read_text(encoding="utf-8"))
    map_path = judge_path.parent / ".blind_map.json"
    blind = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
    by_id = {blind.get(j["id"], j["id"]): j for j in raw}
    n = 0
    for c in blocks:
        j = by_id.get(c["id"])
        if not j:
            c["judge"] = None
            continue
        n += 1
        parts = {k: _clamp(float(j.get(k, 0)), 0, 25) for k in ("gancho", "retencao", "valor", "compartilhamento")}
        c["judge"] = {**{k: round(v) for k, v in parts.items()}, "total": round(sum(parts.values())),
                      "tipo_gancho": j.get("tipo_gancho"), "motivo": j.get("motivo")}
    return n


# --- main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Rank a long video's clips by viral potential")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--min-seconds", type=float, default=20)
    ap.add_argument("--max-seconds", type=float, default=45)
    ap.add_argument("--info-json", type=Path, default=None,
                    help="yt-dlp .info.json with the 'heatmap' (default: newest next to the video)")
    ap.add_argument("--heat-skip", type=float, default=10,
                    help="seconds at the start ignored in the audience check (default 10)")
    ap.add_argument("--packet", action="store_true", help="write judge_packet.md for the judge")
    ap.add_argument("--judge", type=Path, default=None, help="judge.json to merge")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    tpath = args.edit_dir / "transcripts" / f"{args.video.stem}.json"
    if not tpath.exists():
        raise SystemExit(f"transcrição não encontrada: {tpath}. Rode transcribe.py antes")
    out_dir = args.edit_dir / "viral"
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = _probe_duration(args.video)
    _tr, words = _load_prisma_transcript(tpath)
    lo, hi = clip_duration_bounds(args.min_seconds, args.max_seconds)
    bin_s = 0.5
    db = audio_db_per_bin(args.video, bin_s)
    segs = build_segments(words, duration, db, bin_s)
    blocks = build_blocks(segs, duration, lo, hi)
    apply_filters(blocks, duration)
    kept = [b for b in blocks if not b["excluded"]]
    dropped = [b for b in blocks if b["excluded"]]
    n_vis = sum(1 for b in blocks if b["visual"])

    if args.packet:
        p = write_packet(kept, out_dir)
        print(f"pacote do juiz: {p}")
        print(f"  {len(blocks)} blocos cobrindo {_ts(duration)}; {len(kept)} vão ao juiz, "
              f"{len(dropped)} filtrados; {n_vis} com trecho sem fala e áudio alto")
        for b in dropped:
            print(f"  filtrado {b['id']} ({b['duration_s']:.0f} s): {b['excluded']}")
        print("modo cego: ranking e heatmap só aparecem depois que o juiz gravar judge.json "
              "(rode de novo com --judge)")
        return 0

    if not args.judge:
        print(f"{len(blocks)} blocos, {len(dropped)} filtrados. Sem juiz não há ranking: os sinais de "
              "texto e áudio erraram a ordem nos 4 vídeos do teste de 2026-11-19. Rode --packet.")
        return 0

    n = merge_judge(kept, args.judge)
    if n < len(kept):
        print(f"aviso: o juiz avaliou {n} de {len(kept)} blocos; os que faltam ficam sem nota")
    judged = [b for b in kept if b.get("judge")]
    for b in judged:
        b["score"] = b["judge"]["total"]
    ranked = sorted(judged, key=lambda c: c["score"], reverse=True)

    heat = load_heatmap(args.video, args.info_json)
    for b in blocks:
        b["heat"] = heat_for(b, heat, args.heat_skip) if heat else None

    (out_dir / "candidates.json").write_text(json.dumps(
        {"video": str(args.video), "duration_s": duration, "version": 2, "heat_skip_s": args.heat_skip,
         "has_heatmap": bool(heat), "clips": ranked, "excluded": dropped},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(blocks)} blocos | {len(judged)} julgados | {len(dropped)} filtrados")
    print(f"{'#':>2} {'id':4} {'início':>7} {'dur':>4} {'nota':>4} {'heat':>5}  tipo / motivo")
    for i, c in enumerate(ranked[: args.top], 1):
        hv = f"{c['heat']:.2f}" if c.get("heat") is not None else "  -  "
        j = c["judge"]
        print(f"{i:>2} {c['id']:4} {_ts(c['start_s']):>7} {c['duration_s']:>4.0f} {c['score']:>4} {hv:>5}  "
              f"{(j.get('tipo_gancho') or '')[:12]:12} {(j.get('motivo') or '')[:64]}")

    if heat:
        pairs = [(c["score"], c["heat"]) for c in ranked if c.get("heat") is not None]
        hs = [h for _, h in pairs]
        print(f"\naudiência real (heatmap do YouTube sem os primeiros {args.heat_skip:.0f} s, fora da nota):")
        print(f"  correlação de ranking nota × heatmap: {spearman([s for s, _ in pairs], hs)}")
        top3 = [c["heat"] for c in ranked[:3] if c.get("heat") is not None]
        if top3 and hs and np.mean(hs) > 0:
            print(f"  lift do top 3: heat médio {np.mean(top3):.3f} vs média dos blocos {np.mean(hs):.3f} "
                  f"= {np.mean(top3) / np.mean(hs):.2f}x  (1.0 = escolher ao acaso)")
        bins = [h for h in heat if h["start_time"] >= args.heat_skip]
        peaks = sorted(bins, key=lambda h: -h["value"])[:3]
        for pk in sorted(peaks, key=lambda h: h["start_time"]):
            mid = (pk["start_time"] + pk["end_time"]) / 2
            blk = next((b for b in blocks if b["start_s"] <= mid < b["end_s"]), None)
            if blk is None:
                where = "fora dos blocos"
            elif blk["excluded"]:
                where = f"{blk['id']}, filtrado ({blk['excluded']})"
            elif blk in ranked:
                where = f"{blk['id']}, posição {ranked.index(blk) + 1} de {len(ranked)}"
            else:
                where = f"{blk['id']}, sem nota do juiz"
            # Peaks right where a sponsor read ends are people landing after a
            # skip (2026-11-19: the biggest peak of 2 of 7 videos), not a clip.
            if blk is not None:
                k = blocks.index(blk)
                nb = blocks[k + 1] if k + 1 < len(blocks) else None
                near_sp = any(x is not None and (x["excluded"] or "").startswith("patrocínio")
                              for x in (blocks[k - 1] if k else None, nb))
                if near_sp:
                    where += "  [vizinho de patrocínio: provável pouso de quem pulou]"
            print(f"  pico {_ts(pk['start_time'])} (valor {pk['value']:.2f}): {where}")
    else:
        print("\n(sem heatmap: rode ingest_url.py, que salva o .info.json, ou passe --info-json)")
    print(f"\nsaída: {out_dir / 'candidates.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
