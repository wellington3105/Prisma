"""The editing-models library: load recipes, validate them, apply them.

A *modelo* is a named editing type (`tipo`: speed ramp, whip pan, zoom punch…) or a style
(`estilo`: a combination of tipos with rules). Each lives in `modelos/<tipos|estilos>/<slug>/`
as `modelo.json` (the recipe) + `MODELO.md` (the sheet). The recipe only writes formats the
current tools already read:
  host "montagem"  -> a beat_edit plan.json
  host "reel-fala" -> state.json `style` + the Phase-2 edit-data.json
Spec: docs/superpowers/specs/2026-11-22-biblioteca-modelos-design.md
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = Path(os.environ.get("PRISMA_MODELOS") or HERE.parent / "modelos")
REEL_ELEMENTS = ("zoomAuto", "zoomCuts", "flashCut", "shaderCut", "tracking", "glassPanel", "springIn",
                 "brollFull", "tracked3d", "musicAI")
REEL_TRANSITIONS = ("flash", "whip-pan", "glitch", "displace", "refract")
SHEET_SECTIONS = ("## O que é", "## Quando usar", "## Quando não usar", "## Contenção")
NIVEIS = {"tipo": "tipos", "estilo": "estilos"}


@dataclass
class Modelo:
    slug: str
    nivel: str
    familia: str
    host: str
    dados: dict
    pasta: Path


def _root() -> Path:
    return Path(os.environ.get("PRISMA_MODELOS") or ROOT)


def load_all() -> dict[str, Modelo]:
    out: dict[str, Modelo] = {}
    for sub in NIVEIS.values():
        for f in sorted((_root() / sub).glob("*/modelo.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            out[f.parent.name] = Modelo(d.get("slug", ""), d.get("nivel", ""), d.get("familia", ""),
                                        d.get("host", ""), d, f.parent)
    return out


def load(slug: str) -> Modelo:
    todos = load_all()
    if slug not in todos:
        raise SystemExit(f"modelo '{slug}' não existe; conhecidos: {', '.join(sorted(todos)) or '(nenhum)'}")
    return todos[slug]


def _expand(valor, params: dict) -> list:
    """All values a templated field can take ("whip-{dir}" x each allowed dir)."""
    if not isinstance(valor, str) or "{" not in valor:
        return [valor]
    vals = [valor]
    for k, spec in params.items():
        opts = spec.get("valores") or [spec.get("padrao")]
        vals = [v.replace("{" + k + "}", str(o)) for v in vals for o in opts]
    return vals


def _check_montagem(m: Modelo) -> list[str]:
    import beat_edit
    import speed_ramp
    probs, ap = [], m.dados.get("aplica", {})
    params = m.dados.get("parametros", {})
    pp = ap.get("por_plano", {})
    for tr in _expand(pp.get("transition"), params) if "transition" in pp else []:
        if tr not in beat_edit.TRANSITIONS:
            probs.append(f"{m.slug}: transition '{tr}' não existe no beat_edit")
    ramps = [pp.get("ramp"), ap.get("ramp_saida"), ap.get("ramp_entrada")] + list(ap.get("ramps", []))
    for r in [r for r in ramps if r]:
        if r not in speed_ramp.PRESETS:
            probs.append(f"{m.slug}: ramp '{r}' não existe no speed_ramp")
    fx = list(ap.get("fx", [])) + list(ap.get("fx_ultimo", [])) + list(ap.get("fx_primeiro", []))
    for e in fx:
        if e.split("@")[0] not in beat_edit.FX:
            probs.append(f"{m.slug}: fx '{e}' não existe no beat_edit")
    for tr in [ap.get("transicao_primeiro")] if ap.get("transicao_primeiro") else []:
        if tr not in beat_edit.TRANSITIONS:
            probs.append(f"{m.slug}: transition '{tr}' não existe no beat_edit")
    return probs


def _check_reel(m: Modelo) -> list[str]:
    probs = []
    style = m.dados.get("style", {}) or m.dados.get("padroes", {}).get("style", {})
    for el in (style.get("elements") or {}):
        if el not in REEL_ELEMENTS:
            probs.append(f"{m.slug}: elemento '{el}' não existe no preview")
    tr = (m.dados.get("edit_data") or {}).get("transitions_em_cada_corte")
    if tr and tr.get("type") not in REEL_TRANSITIONS:
        probs.append(f"{m.slug}: transição '{tr.get('type')}' não existe no edit-data")
    return probs


def check() -> list[str]:
    probs: list[str] = []
    todos = load_all()
    for pasta, m in todos.items():
        if m.slug != pasta:
            probs.append(f"{pasta}: slug '{m.slug}' difere do nome da pasta")
        if m.nivel not in NIVEIS:
            probs.append(f"{pasta}: nivel '{m.nivel}' (use tipo ou estilo)")
        if m.host not in ("montagem", "reel-fala"):
            probs.append(f"{pasta}: host '{m.host}' (use montagem ou reel-fala)")
        sheet = m.pasta / "MODELO.md"
        txt = sheet.read_text(encoding="utf-8") if sheet.exists() else ""
        for sec in SHEET_SECTIONS:
            if sec not in txt:
                probs.append(f"{pasta}: MODELO.md sem a seção '{sec[3:]}'")
        if m.nivel == "estilo":
            for t in m.dados.get("tipos", []):
                if t not in todos:
                    probs.append(f"{pasta}: estilo cita o tipo '{t}', que não existe")
        if m.host == "montagem":
            probs += _check_montagem(m)
        elif m.host == "reel-fala":
            probs += _check_reel(m)
    return probs
