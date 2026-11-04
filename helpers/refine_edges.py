"""Refina as bordas de um EDL contra a fala REAL — nenhum corte no meio de palavra.

Existe porque o transcript da fonte inteira erra o tempo das palavras justamente
onde importa. Medido no projeto Volvo XC60 (2026-10-30): numa fonte de 7min com
4 vozes num carro em movimento, o WhisperX alinhado sobre o arquivo inteiro pôs
"cavalos" 0,7s adiantado e "Integral" 0,5s adiantado. As bordas foram ajustadas
pelas palavras, com folga, e mesmo assim decapitaram as duas — `verify_cut.py`
passou limpo, porque ele mede junção, silêncio e nível, não se a palavra está
inteira. O mesmo transcript também INVENTOU falas ("Oi", "O que é que ela tem,
Isa?") que não existem no áudio.

O que acertou, nas duas vezes: transcrever a janela ISOLADA. Sem o contexto do
arquivo inteiro o modelo não completa frase por inferência, e o alinhamento
forçado trabalha sobre poucos segundos. Este helper faz isso para todas as
bordas de uma vez, com o modelo carregado uma única vez:

  1. para cada range, extrai [start-1.2s, end+1.2s] da fonte e transcreve;
  2. acha a 1ª e a última palavra do `quote` do range nessa transcrição local
     (a ocorrência mais perto da borda atual);
  3. empurra cada borda até o SILÊNCIO medido mais próximo (envelope RMS de 10ms,
     limiar = piso local + 6 dB, silêncio = 40ms seguidos abaixo dele) — nunca
     para dentro de outra palavra;
  4. funde ranges consecutivos da mesma fonte que passaram a se tocar.

Bordas sem silêncio entre a palavra querida e a vizinha (fala colada, ou outra
pessoa falando por cima) são marcadas COLADA — essas não têm corte limpo: mude a
borda para uma pausa de verdade (fim de frase) em vez de aceitar o corte.

**Bordas da pessoa (`"user_edges": ["start"|"end"]` no range) nunca se movem.**
São as que ela ajustou no preview (marcadas por `apply_preview_edits.py`). Aqui
elas só são CONFERIDAS — avisa se cortam palavra no meio ou caem em fala — e o
`quote` do range é reescrito a partir da janela isolada, porque o antigo
descreve o range de antes da edição. Medido em 2026-11-03 (cópia do Cayenne
reel_01): sem essa trava, o quote antigo reancorava a borda e 2 de 4 edições da
pessoa foram desfeitas em silêncio ("Preço de carro chinês" e "esse carro"
voltaram ao corte). Range sem `quote` recebe o mesmo tratamento: não há palavra
para ancorar, então a borda fica e é só conferida.

Toda borda que se move e faz palavras entrarem ou saírem do range é dita no
relatório (`+palavras` / `−palavras`) — mover borda é decisão, não detalhe.

Uso:
    uv run python helpers/refine_edges.py reels/*/edl.json --language pt
    uv run python helpers/refine_edges.py edl.json --dry-run      # só relatório

Grava `edl.before_refine.json` ao lado de cada EDL antes de alterar.
Depois: render.py → verify_cut.py como sempre.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import WHISPERX_MODEL, _whisperx_device  # noqa: E402
try:
    import agent_markers as _markers  # noqa: E402
except Exception:  # o refine funciona sem o preview
    _markers = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SR = 16000
PAD_WIN = 1.2          # s de contexto de cada lado da janela isolada
HOP = 0.010            # envelope RMS
QUIET_RUN = 0.040      # silêncio mínimo para valer como ponto de corte
ABOVE_FLOOR_DB = 6.0   # limiar de fala = piso local + isto
LEAD = 0.03            # folga antes do onset (dentro do silêncio)
TRAIL = 0.06           # folga depois do offset — o decaimento da palavra
MAX_REACH = 0.45       # quanto uma borda pode andar até achar silêncio
MATCH_TOL = 1.0        # distância máx. entre a borda atual e a palavra achada


def norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w)


def load_pcm(src: str, t0: float, dur: float, voice_band: bool = False) -> np.ndarray:
    af = ["-af", "highpass=f=250,highpass=f=250,lowpass=f=3500"] if voice_band else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", src,
                        *af, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def envelope_db(x: np.ndarray) -> np.ndarray:
    n = int(HOP * SR)
    k = len(x) // n
    if k == 0:
        return np.zeros(0)
    fr = x[: k * n].reshape(k, n)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)


class Engine:
    def __init__(self, language: str | None, model_name: str):
        import whisperx
        self.wx = whisperx
        # CPU/int8 de propósito, mesmo com GPU (D7, medido 2026-11-03 na
        # regressão): float16, float32 e até int8 no CUDA alinham "hein?" do
        # range 01 em 14,58–14,72 e o quiet_point acha uma pausa de 40 ms ENTRE
        # sílabas (14,88) — a fala volta forte em 14,95 e o fim cortava 0,6 s de
        # voz. Só o int8 da CPU dá o resultado validado. O defeito real é da
        # regra (micro-pausa dentro de vocalização não transcrita), pendência
        # D10 no PLANO-FLUXO-EDICAO.md; até ela ser medida, a borda não muda.
        _whisperx_device()  # mantém o aviso de GPU coerente
        self.device, ct = "cpu", "int8"
        try:
            self.model = whisperx.load_model(model_name, self.device, compute_type=ct, language=language,
                                             vad_options={"vad_onset": 0.200, "vad_offset": 0.250})
        except TypeError:
            self.model = whisperx.load_model(model_name, self.device, compute_type=ct, language=language)
        self.language = language
        self.align = {}

    def words(self, audio: np.ndarray) -> list[dict]:
        res = self.model.transcribe(audio, batch_size=8, language=self.language)
        lang = res.get("language") or self.language
        if lang not in self.align:
            self.align[lang] = self.wx.load_align_model(language_code=lang, device=self.device)
        am, meta = self.align[lang]
        res = self.wx.align(res["segments"], am, meta, audio, self.device, return_char_alignments=False)
        out = []
        for seg in res.get("segments", []):
            for w in seg.get("words") or []:
                if w.get("start") is None or not norm(w.get("word", "")):
                    continue
                out.append({"w": norm(w["word"]), "raw": w["word"].strip(),
                            "s": float(w["start"]), "e": float(w["end"])})
        return out


def find_seq(local: list[dict], targets: list[str], near: float, first: bool) -> int | None:
    """Índice da palavra (1ª do trecho se first, senão a última) que casa com
    `targets` em sequência, na ocorrência mais perto de `near`."""
    best, best_d = None, 1e9
    k = len(targets)
    for i in range(len(local) - k + 1):
        if all(local[i + j]["w"] == targets[j] for j in range(k)):
            idx = i if first else i + k - 1
            t = local[idx]["s"] if first else local[idx]["e"]
            d = abs(t - near)
            if d < best_d:
                best, best_d = idx, d
    return best if best_d <= MATCH_TOL else None


def quiet_point(env: np.ndarray, thr: float, t_rel: float, direction: int) -> float | None:
    """Primeiro instante, andando a partir de t_rel na direção dada, em que há
    QUIET_RUN de silêncio. Devolve a borda do silêncio colada à fala."""
    need = int(round(QUIET_RUN / HOP))
    i = int(round(t_rel / HOP))
    reach = int(round(MAX_REACH / HOP))
    run = 0
    for step in range(reach + 1):
        j = i + direction * step
        if j < 0 or j >= len(env):
            return None
        run = run + 1 if env[j] < thr else 0
        if run >= need:
            first_quiet = j - direction * (need - 1)
            return first_quiet * HOP
    return None


def check_kept_edge(local: list[dict], env: np.ndarray, thr: float, t_rel: float,
                    label: str) -> str:
    """Confere uma borda que NÃO pode mudar (da pessoa, ou sem quote)."""
    for w in local:
        if w["s"] + 0.02 < t_rel < w["e"] - 0.02:
            return f"{label} corta \"{w['raw']}\" no meio (mantido — confira)"
    i = int(round(t_rel / HOP))
    if 0 <= i < len(env) and env[i] >= thr:
        return f"{label} cai em fala, sem silêncio (mantido — confira)"
    return f"{label} ok (mantido)"


def words_between(local: list[dict], a_rel: float, b_rel: float) -> list[int]:
    return [i for i, w in enumerate(local) if w["s"] >= a_rel - 0.02 and w["e"] <= b_rel + 0.02]


def refine(edl_path: Path, eng: Engine, dry: bool) -> None:
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    ranges = edl["ranges"]
    print(f"\n== {edl_path.parent.name}/{edl_path.name}  ({len(ranges)} ranges)")
    if not dry and _markers is not None:
        _markers.clear(edl_path.parent, "borda")  # avisos da rodada anterior saem; os atuais voltam abaixo
    for n, r in enumerate(ranges):
        src = edl["sources"][r["source"]]
        q = [norm(w) for w in (r.get("quote") or "").split() if norm(w)]
        t0 = max(0.0, r["start"] - PAD_WIN)
        dur = (r["end"] + PAD_WIN) - t0
        audio = load_pcm(src, t0, dur)
        local = eng.words(audio)
        # Silêncio medido na FAIXA DA VOZ (250–3500 Hz). Em banda larga o ronco
        # de estrada tem a energia de uma voz baixa e "segundos" lia como
        # silêncio (medido no XC60, 2026-10-30).
        env = envelope_db(load_pcm(src, t0, dur, voice_band=True))
        floor = float(np.percentile(env, 15)) if len(env) else -60
        thr = floor + ABOVE_FLOOR_DB
        old = (r["start"], r["end"])
        flags = []
        locked = set(r.get("user_edges") or [])
        # Sem quote não há palavra para ancorar: a borda fica e é conferida.
        keep_start = "start" in locked or not q
        keep_end = "end" in locked or not q

        # ---- início
        i0 = None
        if not keep_start:
            i0 = find_seq(local, q[:2] or q[:1], r["start"] + 0.08 - t0, True)
            if i0 is None:
                i0 = find_seq(local, q[:1], r["start"] + 0.08 - t0, True)
        if keep_start:
            s_new = r["start"]
            flags.append(check_kept_edge(local, env, thr, s_new - t0,
                                         "início da pessoa" if "start" in locked else "início (sem quote)"))
        elif i0 is None:
            flags.append("início: 1ª palavra não achada (mantido)")
            s_new = r["start"]
        else:
            ws = local[i0]["s"]
            qp = quiet_point(env, thr, ws - HOP, -1)
            prev_e = local[i0 - 1]["e"] if i0 > 0 else None
            if qp is None or (prev_e is not None and qp < prev_e):
                flags.append(f"início COLADO em \"{local[i0 - 1]['raw'] if i0 else '?'}\"")
                s_rel = (prev_e + ws) / 2 if prev_e is not None else ws - LEAD
            else:
                s_rel = max(qp - LEAD, prev_e + 0.01 if prev_e is not None else 0.0)
                s_rel = min(s_rel, ws - 0.01)
            s_new = t0 + s_rel

        # ---- fim
        i1 = None
        if not keep_end:
            i1 = find_seq(local, q[-2:] or q[-1:], r["end"] - 0.06 - t0, False)
            if i1 is None:
                i1 = find_seq(local, q[-1:], r["end"] - 0.06 - t0, False)
        if keep_end:
            e_new = r["end"]
            flags.append(check_kept_edge(local, env, thr, e_new - t0,
                                         "fim da pessoa" if "end" in locked else "fim (sem quote)"))
        elif i1 is None:
            flags.append("fim: última palavra não achada (mantido)")
            e_new = r["end"]
        else:
            we = local[i1]["e"]
            qp = quiet_point(env, thr, we + HOP, +1)
            next_s = local[i1 + 1]["s"] if i1 + 1 < len(local) else None
            if qp is None or (next_s is not None and qp > next_s):
                flags.append(f"fim COLADO em \"{local[i1 + 1]['raw'] if i1 + 1 < len(local) else '?'}\"")
                e_rel = (we + next_s) / 2 if next_s is not None else we + TRAIL
            else:
                e_rel = qp + TRAIL
                if next_s is not None:
                    e_rel = min(e_rel, next_s - 0.02)
                e_rel = max(e_rel, we + 0.02)
            e_new = t0 + e_rel

        # ---- palavras que a mudança de borda pôs ou tirou do range
        new_idx = words_between(local, s_new - t0, e_new - t0)
        old_idx = words_between(local, old[0] - t0, old[1] - t0)
        added = [local[i]["raw"] for i in new_idx if i not in old_idx]
        dropped = [local[i]["raw"] for i in old_idx if i not in new_idx]
        if added:
            flags.append(f"+palavras: \"{' '.join(added)}\"")
        if dropped:
            flags.append(f"−palavras: \"{' '.join(dropped)}\"")

        # ---- conteúdo: o que a janela diz entre as bordas novas vs o quote
        inside_raw = " ".join(local[i]["raw"] for i in new_idx)
        if locked or not q:
            # O quote antigo descreve o range de ANTES da edição; o novo vem da
            # janela isolada, e é ele que a próxima rodada usa para conferir.
            if inside_raw:
                r["quote"] = inside_raw
                flags.append(f"quote reescrito: \"{inside_raw}\"")
        else:
            import difflib
            ratio = difflib.SequenceMatcher(None, q, [local[i]["w"] for i in new_idx]).ratio()
            if ratio < 0.8:
                flags.append(f"conteúdo difere do quote ({ratio:.2f}): \"{inside_raw}\"")
        r["start"], r["end"] = round(s_new, 3), round(e_new, 3)
        # Uma borda da pessoa que corta palavra vira marcador amarelo no preview,
        # no ponto exato — a intenção dela vale, mas ela precisa ver o aviso.
        if not dry and _markers is not None:
            for f in flags:
                if "da pessoa" in f and "confira" in f:
                    at = r["start"] if f.startswith("início") else r["end"]
                    try:
                        _markers.add(edl_path.parent, r["source"], at, "borda", f)
                    except Exception:
                        pass
        mv = f"{old[0]:.2f}→{r['start']:.2f}  {old[1]:.2f}→{r['end']:.2f}"
        print(f"  [{n:02d}] {mv}  " + ("; ".join(flags) if flags else "ok"))

    # funde vizinhos da mesma fonte que passaram a se tocar
    merged = [ranges[0]]
    for r in ranges[1:]:
        p = merged[-1]
        if r["source"] == p["source"] and 0 <= r["start"] - p["end"] < 0.08:
            p["end"] = r["end"]
            p["quote"] = f"{p.get('quote', '')} {r.get('quote', '')}".strip()
            p["gain_db"] = round(((p.get("gain_db") or 0) + (r.get("gain_db") or 0)) / 2, 1)
            # o range fundido herda a trava do início de um e a do fim do outro
            locks = [x for x in (p.get("user_edges") or []) if x == "start"] + \
                    [x for x in (r.get("user_edges") or []) if x == "end"]
            if locks:
                p["user_edges"] = locks
            else:
                p.pop("user_edges", None)
            print(f"  fundidos: …{p['end']:.2f} (pausa < 80ms entre eles)")
        else:
            merged.append(r)
    edl["ranges"] = merged
    edl.pop("jcut_timeline", None)
    edl["total_duration_s"] = round(sum(x["end"] - x["start"] for x in merged), 2)
    if not dry:
        bak = edl_path.with_name("edl.before_refine.json")
        if not bak.exists():
            shutil.copy2(edl_path, bak)
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  gravado ({len(merged)} ranges, ~{edl['total_duration_s']}s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edls", nargs="+", type=Path)
    ap.add_argument("--language", default="pt")
    ap.add_argument("--model", default=WHISPERX_MODEL)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    eng = Engine(a.language, a.model)
    for p in a.edls:
        refine(p, eng, a.dry_run)


if __name__ == "__main__":
    main()
