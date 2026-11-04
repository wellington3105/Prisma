"""Versão do HyperFrames fixa por projeto (F1.2b do PLANO-FLUXO-EDICAO.md).

Trocar de versão no meio de um vídeo pode mudar o desenho do que já foi
aprovado (`references/hyperframes-traps.md` §1). Os helpers chamam o CLI GLOBAL
(`shutil.which("hyperframes")`), então "fixar" aqui é: gravar no projeto a
versão com que ele nasceu e avisar quando o CLI instalado for outro.

    from hf_version import installed, stamp, check
    stamp(project_dir)            # ao criar o projeto
    msg = check(project_dir)      # antes de render/preview: None ou um aviso
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

FILE = "package.json"


def installed() -> str | None:
    exe = shutil.which("hyperframes")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    m = re.search(r"\d+\.\d+\.\d+", out or "")
    return m.group(0) if m else None


def pinned_scripts(ver: str | None) -> dict:
    tag = ver or "latest"
    return {"dev": f"npx --yes hyperframes@{tag} preview",
            "check": f"npx --yes hyperframes@{tag} check",
            "render": f"npx --yes hyperframes@{tag} render"}


def stamp(project: Path, ver: str | None = None) -> str | None:
    """Grava a versão no package.json do projeto (cria ou completa)."""
    ver = ver or installed()
    p = Path(project) / FILE
    try:
        pkg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        pkg = {}
    pkg.setdefault("name", "hyperframes")
    pkg.setdefault("private", True)
    pkg.setdefault("type", "module")
    prisma = pkg.setdefault("prisma", {})
    if not prisma.get("hyperframes"):      # nunca reescreve a versão de um projeto existente
        prisma["hyperframes"] = ver
        pkg["scripts"] = pinned_scripts(ver)
    p.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    return prisma["hyperframes"]


def recorded(project: Path) -> str | None:
    p = Path(project) / FILE
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("prisma") or {}).get("hyperframes")
    except Exception:
        return None


def check(project: Path) -> str | None:
    rec, cur = recorded(project), installed()
    if not rec or not cur or rec == cur:
        return None
    return (f"⚠ HyperFrames: este projeto foi criado com {rec} e o CLI instalado é {cur}. "
            f"O desenho pode mudar em relação ao aprovado — renderize com "
            f"`npx --yes hyperframes@{rec} render` ou confirme a troca de versão antes.")
