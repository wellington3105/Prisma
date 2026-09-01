"""Monta o projeto Remotion da Fase 2 com os arquivos que o template exige.

Existe porque montar isto à mão erra em silêncio. No primeiro teste ponta a
ponta desta skill, três arquivos saíram com o formato errado:

  - `segments.json` — o template lê `{segments: [{start, dur}]}`, e a forma
    intuitiva `{boundaries: [...]}` ou `{start, end}` compila e quebra;
  - `caption-cues.json` — importado ESTATICAMENTE por StackedCaptions.tsx, então
    precisa existir mesmo quando o estilo escolhido não é o stacked;
  - `track.json` — idem, mesmo com `elements.tracking` desligado.

Nenhum dos três falha no render: falham no build do webpack, com mensagens que
apontam para o TSX e não para o dado. Este helper os escreve certos.

Uso:
    uv run python helpers/scaffold_phase2.py <edit> --duration 2.0 --fps 30
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = Path(__file__).resolve().parent.parent


def _ler(p: Path) -> dict:
    """JSON do arquivo, ou {} se ausente/ilegível — para decidir se substitui."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def scaffold(edit: Path, dur: float, fps: int, width: int, height: int,
             track: str = "shortform", segments: list | None = None) -> list[str]:
    rem = edit / "remotion"
    pub = rem / "public"
    feito = []

    if not (rem / "src").exists():
        src = SKILL / "assets" / track
        for item in src.iterdir():
            if item.name in ("node_modules", "out", "build"):
                continue
            dst = rem / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        feito.append(f"template {track} copiado")
    pub.mkdir(parents=True, exist_ok=True)

    n = max(1, round(dur * fps))

    # segments.json — {start, dur}. Um bloco só quando não há cortes.
    segs = segments or [{"start": 0.0, "dur": round(dur, 3)}]
    (pub / "segments.json").write_text(
        json.dumps({"fps": fps, "segments": segs}), encoding="utf-8")
    feito.append(f"segments.json ({len(segs)} bloco(s))")

    # Os três abaixo vêm do template como placeholders — compilam, mas com
    # dados vazios ou com contagem errada para ESTE vídeo. Substituir quando o
    # conteúdo não serve é diferente de criar quando falta: um `track.json` com
    # 90 pontos num vídeo de 60 frames não quebra o build, e o resultado é a
    # câmera parando de seguir no meio.

    # track.json — neutro quando o tracking está desligado, mas com a contagem
    # certa. Precisa EXISTIR de qualquer forma: o import é estático.
    tj = pub / "track.json"
    atual = _ler(tj)
    if atual.get("count") != n:
        tj.write_text(json.dumps({
            "fps": fps, "width": width, "height": height, "count": n,
            "points": [[width // 2, int(height * 0.4)]] * n, "neutral": True,
        }), encoding="utf-8")
        feito.append(f"track.json (neutro, {n} pontos)")

    # caption-cues.json — só o estilo stacked usa, mas o import é estático.
    cc = pub / "caption-cues.json"
    if "cues" not in _ler(cc):
        cc.write_text(json.dumps({"fps": fps, "cues": []}), encoding="utf-8")
        feito.append("caption-cues.json (vazio)")

    # captions.json — idem. captions_for_remotion.py o sobrescreve depois.
    cj = pub / "captions.json"
    if "captions" not in _ler(cj):
        cj.write_text(json.dumps({"captions": []}), encoding="utf-8")
        feito.append("captions.json (vazio)")

    return feito


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path, help="o diretório <edit> da sessão")
    ap.add_argument("--duration", type=float, required=True, help="segundos do cut")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--track", choices=["shortform", "longform"], default="shortform")
    args = ap.parse_args()

    feito = scaffold(args.edit.resolve(), args.duration, args.fps,
                     args.width, args.height, args.track)
    print(json.dumps({"ok": True, "criados": feito}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
