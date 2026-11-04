"""O que ficou desatualizado na pasta de edição — e o que refazer.

Cada etapa do Prisma é derivada da anterior: edl.json → cut.mp4 (+ jcut_timeline)
→ segments.json → edit-data.json → final.mp4, e o projeto do EDITOR. Quando uma
peça muda e a seguinte não é refeita, nada quebra com erro: os inserts caem
frames fora do lugar, o preview toca o corte antigo, o EDITOR edita um corte que
não existe mais. Até aqui isso era só um anti-pattern escrito ("Re-rendering
Phase 1 without regenerating segments.json"); este módulo o MEDE pelas datas
dos arquivos. Adaptado de `LeiteZ/fluxo-de-edicao` (alerta "o corte mudou depois
do plano de animação", MIT).

Uso:
    uv run python helpers/staleness.py <edit_dir>        # lista o que refazer
    from staleness import check; check(edit_dir)          # [{"what","fix"}]
O preview mostra a mesma lista no aviso ⟳ do topo.
"""
from __future__ import annotations

import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import sys
from pathlib import Path

SLACK = 1.0  # s — escrever dois arquivos no mesmo passo não é "desatualizado"


def _mt(p: Path | None) -> float | None:
    try:
        return p.stat().st_mtime if p and p.exists() else None
    except OSError:
        return None


def _newer(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and a > b + SLACK


def _measured_starts(edit: Path, n_ranges: int, fps: float) -> list[float] | None:
    """Início real de cada take = soma dos frames dos segmentos de vídeo extraídos.

    Usa o `nb_frames` do contêiner (rápido, sem decodificar). Só confia quando a
    pasta tem exatamente um segmento de vídeo por range — sobra de um render
    anterior com mais ranges invalidaria a soma (shortform.md, receita do
    segments.json)."""
    import subprocess
    segs = sorted((edit / "clips_graded").glob("seg_*_v.mp4")) or sorted((edit / "clips_graded").glob("seg_*.mp4"))
    if not segs or len(segs) != n_ranges:
        return None
    starts, acc = [], 0
    for f in segs:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_frames", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
        try:
            n = int(r.stdout.strip())
        except ValueError:
            return None
        starts.append(acc / fps)
        acc += n
    return starts


def _segments_vs_cut(seg_p: Path, edl_p: Path | None) -> str | None:
    """'' = bate · texto = o que não bate · None = sem como comparar.

    Por CONTEÚDO, não por data: um cut.mp4 re-renderizado só para mudar a cor é
    mais novo que o segments.json e continua com as mesmas posições. Medido nos
    projetos reais em 2026-11-03: a regra por data acusava esse caso à toa.
    """
    try:
        seg = json.loads(seg_p.read_text(encoding="utf-8"))
        edl = json.loads(edl_p.read_text(encoding="utf-8")) if edl_p else None
    except (OSError, json.JSONDecodeError):
        return None
    if not edl:
        return None
    starts = [float(s.get("start", 0)) for s in seg.get("segments") or []]
    fps = float(seg.get("fps") or edl.get("fps") or 30)
    jt = edl.get("jcut_timeline") or []
    measured = _measured_starts(edl_p.parent, len(edl.get("ranges") or []), fps)
    if measured is not None:
        # A verdade é a contagem de frames dos segmentos extraídos — não o
        # jcut_timeline. Medido 2026-11-03: o jcut_timeline do render.py atrasa
        # 1 frame cada vez que a extração sai com um frame a mais (Cayenne
        # reel_01: 9 frames no take 27), e os cortes reais (scdet) caem onde a
        # contagem diz.
        real = measured
    elif jt and all("video_start_in_output" in t for t in jt):
        real = [float(t["video_start_in_output"]) for t in jt]
    elif edl.get("ranges") and edl.get("jcut") is False:
        real, acc = [], 0.0
        for r in edl["ranges"]:
            real.append(acc)
            acc += float(r["end"]) - float(r["start"])
    else:
        return None
    if len(starts) == 1 and len(real) > 1:
        return f"1 bloco para {len(real)} takes"
    if len(starts) != len(real):
        return f"{len(starts)} segmentos para {len(real)} takes"
    tol = 1.0 / fps + 0.002
    for i, (a, b) in enumerate(zip(starts, real)):
        if abs(a - b) > tol:
            return f"segmento {i + 1} em {a:.3f}s, take real em {b:.3f}s"
    return ""


def check(edit: Path, state: dict | None = None) -> list[dict]:
    edit = Path(edit)
    if state is None:
        try:
            state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    def rel(key: str, default: str | None) -> Path | None:
        v = state.get(key) or default
        if not v:
            return None
        p = Path(v)
        return p if p.is_absolute() else edit / p

    edl_p = rel("edl", "edl.json")
    cut_p = rel("video", "cut.mp4")
    ed_p = rel("editData", "remotion/public/edit-data.json")
    seg_p = (ed_p.parent / "segments.json") if ed_p else edit / "remotion/public/segments.json"
    fin_p = rel("finalVideo", "final.mp4")
    hf_p = rel("hyperframes", None)

    edl, cut, seg, ed, fin = _mt(edl_p), _mt(cut_p), _mt(seg_p), _mt(ed_p), _mt(fin_p)
    hf = _mt(hf_p / "index.html") if hf_p else None
    out: list[dict] = []

    if _newer(edl, cut):
        out.append({"what": "o corte (edl.json) mudou depois do cut.mp4",
                    "fix": "render.py edl.json -o cut.mp4 → verify_cut.py"})
    elif edl is not None and cut is not None:
        try:
            if "jcut_timeline" not in json.loads(edl_p.read_text(encoding="utf-8")):
                out.append({"what": "edl.json sem jcut_timeline (as posições reais do corte)",
                            "fix": "render.py edl.json -o cut.mp4 — ele reescreve o jcut_timeline"})
        except (OSError, json.JSONDecodeError):
            pass
    if seg is not None:
        verdict = _segments_vs_cut(seg_p, edl_p)
        if verdict is None:  # sem como comparar conteúdo → cai para a data
            if _newer(cut, seg) or _newer(edl, seg):
                out.append({"what": "segments.json é mais velho que o corte — os inserts da Fase 2 podem cair fora do lugar",
                            "fix": "regenerar segments.json a partir do jcut_timeline e re-renderizar a Fase 2"})
        elif verdict:
            out.append({"what": f"segments.json não bate com o corte atual ({verdict}) — os inserts da Fase 2 caem fora do lugar",
                        "fix": "regenerar segments.json a partir do jcut_timeline e re-renderizar a Fase 2"})
    if fin is not None and _newer(cut, fin):
        out.append({"what": "o cut.mp4 mudou depois da entrega (final)",
                    "fix": "refazer a Fase 2 sobre o corte novo (render_phase2.py → deliver_mix.py)"})
    if fin is not None and _newer(ed, fin):
        out.append({"what": "edit-data.json mudou depois do último render da Fase 2",
                    "fix": "render_phase2.py (o preview mostra inserts que o vídeo ainda não tem)"})
    if hf is not None and (_newer(edl, hf) or _newer(cut, hf)):
        out.append({"what": "o EDITOR foi exportado antes do corte atual",
                    "fix": "export_hyperframes.py <edit> — atenção: ele recusa sobrescrever trabalho feito no Studio sem --force"})
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("uso: staleness.py <edit_dir>")
    items = check(Path(sys.argv[1]))
    if not items:
        print("nada desatualizado")
        return
    for it in items:
        print(f"⟳ {it['what']}\n    → {it['fix']}")


if __name__ == "__main__":
    main()
