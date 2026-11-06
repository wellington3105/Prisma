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
import os
import shutil
import subprocess
import sys
import time
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


def _ler_lista(p: Path) -> list | None:
    """A lista do arquivo, ou None se ausente/ilegível/não-lista.

    Existe porque `_ler` normaliza qualquer coisa para dict, e `captions.json`
    é um ARRAY — usar `_ler` nele devolveria `{}` mesmo com legendas válidas em
    disco, e o scaffold sobrescreveria o trabalho da transcrição.
    """
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else None
    except (OSError, json.JSONDecodeError):
        return None


# ---- runtime Remotion compartilhado ------------------------------------------
# `npm install` por projeto custava ~4 min e centenas de MB. As dependências dos
# dois templates são as mesmas (pinadas em assets/remotion-runtime/package.json),
# então vivem UMA vez em ~/.prisma/remotion-runtime e cada <edit>/remotion/node_modules
# é um atalho para lá (junction no Windows — não pede admin —, symlink no resto).
RUNTIME = Path(os.environ.get("PRISMA_REMOTION_RUNTIME") or Path.home() / ".prisma" / "remotion-runtime")
RUNTIME_SRC = SKILL / "assets" / "remotion-runtime"


def _runtime_ok(rt: Path = RUNTIME) -> bool:
    nm = rt / "node_modules"
    need = ("remotion/package.json", "@remotion/cli/package.json", "react/package.json", "three/package.json",
            "@react-three/fiber/package.json", "@remotion/three/package.json", "typescript/package.json")
    return all((nm / n).is_file() for n in need)


def _is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    try:
        return bool(os.path.isjunction(p))  # Python 3.12+
    except AttributeError:
        return os.name == "nt" and p.is_dir() and bool(os.stat(p, follow_symlinks=False).st_file_attributes & 0x400)


def _link_dir(link: Path, target: Path) -> None:
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or r.stdout.strip())
    else:
        link.symlink_to(target, target_is_directory=True)


def build_runtime(log=print) -> bool:
    """Instala o runtime uma vez, do lockfile dos templates (`npm ci`)."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        return False
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for f in ("package.json", "package-lock.json"):
        shutil.copy2(RUNTIME_SRC / f, RUNTIME / f)
    log(f"  runtime Remotion ausente/quebrado — instalando UMA vez em {RUNTIME} (npm ci)…")
    t = time.time()
    r = subprocess.run([npm, "ci", "--prefer-offline", "--no-audit", "--no-fund"], cwd=str(RUNTIME))
    log(f"  npm ci: {time.time() - t:.0f}s, código {r.returncode}")
    return r.returncode == 0 and _runtime_ok()


def ensure_node_modules(rem: Path) -> str:
    """`<rem>/node_modules` -> runtime compartilhado; senão `npm install` no projeto."""
    nm = rem / "node_modules"
    if nm.exists() and not (_is_link(nm) and not nm.resolve().exists()):
        return "node_modules já presente (mantido)"
    if _is_link(nm):  # atalho morto
        os.rmdir(nm) if os.name == "nt" else nm.unlink()
    if not _runtime_ok() and not build_runtime():
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            return "SEM runtime e SEM npm — instale o Node"
        t = time.time()
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(rem))
        return f"npm install no projeto ({time.time() - t:.0f}s, código {r.returncode}) — runtime compartilhado indisponível"
    try:
        _link_dir(nm, RUNTIME / "node_modules")
    except OSError as e:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(rem))
        return f"link falhou ({e}); npm install no projeto, código {r.returncode}"
    return f"node_modules -> {RUNTIME / 'node_modules'}"


def scaffold(edit: Path, dur: float, fps: int, width: int, height: int,
             track: str = "shortform", segments: list | None = None) -> list[str]:
    rem = edit / "remotion"
    pub = rem / "public"
    feito = []

    if not (rem / "src").exists():
        src = SKILL / "assets" / track
        rem.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name in ("node_modules", "out", "build"):
                continue
            dst = rem / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        feito.append(f"template {track} copiado")
    feito.append(ensure_node_modules(rem))
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
    #
    # ARRAY, não objeto. O formato é o do `@remotion/captions` e é o que
    # `captions_for_remotion.py` grava; os componentes de legenda fazem
    # `words.forEach` direto sobre ele. Escrever `{"captions": []}` aqui fazia
    # TODA instalação nova morrer no primeiro render com "words.forEach is not
    # a function" — antes de transcrever, que é justamente quando o placeholder
    # deveria estar segurando as pontas.
    #
    # Medido em 2026-09-01 numa instalação limpa vinda do GitHub: o scaffold
    # rodava, o `npm install` passava, e o render quebrava. Os dois arquivos
    # concordavam sobre o NOME e discordavam sobre a FORMA.
    cj = pub / "captions.json"
    if _ler_lista(cj) is None:
        cj.write_text(json.dumps([]), encoding="utf-8")
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
