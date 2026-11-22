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


# ---------------------------------------------------------------- apply
ACCENT_TRANSITIONS = ("flash", "whip-left", "whip-right", "whip-up", "whip-down", "zoom", "rgb-split", "shake")
MAX_ACENTOS = 3


def count_accents(plan: dict) -> list[int]:
    """Shot indices whose incoming transition is an accent (cut and speed are not)."""
    return [i for i, sh in enumerate(plan.get("shots", [])) if sh.get("transition") in ACCENT_TRANSITIONS]


def _params(m: Modelo, given: dict[str, str]) -> dict[str, str]:
    out = {}
    for k, spec in m.dados.get("parametros", {}).items():
        v = given.get(k, spec.get("padrao"))
        if spec.get("valores") and v not in spec["valores"]:
            raise SystemExit(f"{m.slug}: {k}='{v}' não é válido (use {', '.join(spec['valores'])})")
        out[k] = v
    return out


def _fill(v, params: dict[str, str]):
    if isinstance(v, str):
        for k, p in params.items():
            v = v.replace("{" + k + "}", str(p))
    return v


def _add_fx(sh: dict, fx: list[str]) -> None:
    cur = list(sh.get("fx", []))
    for e in fx:
        if e not in cur:
            cur.append(e)
    sh["fx"] = cur


def _apply_tipo_montagem(m: Modelo, shots: list[dict], planos: list[int], params: dict[str, str]) -> None:
    ap = m.dados.get("aplica", {})
    for i in planos:
        if not 0 <= i < len(shots):
            raise SystemExit(f"{m.slug}: o plano {i} não existe (o plano tem {len(shots)} planos, de 0 a {len(shots) - 1})")
    if m.dados.get("intervalo"):
        ramps = ap.get("ramps", [])
        for k, i in enumerate(planos):
            if ramps:
                shots[i]["ramp"] = ramps[k % len(ramps)]
            _add_fx(shots[i], ap.get("fx", []))
        if ap.get("transicao_primeiro"):
            shots[planos[0]]["transition"] = ap["transicao_primeiro"]
        _add_fx(shots[planos[-1]], ap.get("fx_ultimo", []))
        return
    for i in planos:
        for campo, valor in ap.get("por_plano", {}).items():
            shots[i][campo] = _fill(valor, params)
        if ap.get("fx"):
            _add_fx(shots[i], ap["fx"])
        if ap.get("ramp_entrada"):
            shots[i]["ramp"] = ap["ramp_entrada"]
        if ap.get("ramp_saida"):
            if i == 0:
                raise SystemExit(f"{m.slug}: o plano 0 não tem plano anterior para acelerar até o corte")
            shots[i - 1]["ramp"] = ap["ramp_saida"]


def apply_montagem(m: Modelo, plan: dict, planos: list[int] | None, params: dict[str, str]) -> dict:
    new = json.loads(json.dumps(plan))
    shots = new.get("shots", [])
    limite = MAX_ACENTOS
    if m.nivel == "estilo":
        limite = m.dados.get("regras", {}).get("max_acentos", MAX_ACENTOS)
        prim = load(m.dados["regras"]["primaria"])
        alvo = planos if planos is not None else list(range(1, len(shots)))
        _apply_tipo_montagem(prim, shots, alvo, _params(prim, {}))
    else:
        if not planos:
            raise SystemExit(f"{m.slug} é um tipo: diga em quais planos com --plano N (os planos vão de 0 a {len(shots) - 1})")
        _apply_tipo_montagem(m, shots, planos, _params(m, params))
    if len(count_accents(new)) > limite:
        antes = count_accents(plan)
        raise SystemExit(f"{m.slug}: passaria de {limite} acentos. Já há acento nos planos "
                         f"{', '.join(map(str, antes)) or '(nenhum)'}; tire um deles antes.")
    return new


def _edit_dir_of(target: Path) -> Path:
    p = target if target.is_dir() else target.parent
    for c in [p, *p.parents][:4]:
        if (c / "state.json").exists():
            return c
    return p


def _write_with_backup(f: Path, old: dict, new: dict, slug: str) -> Path:
    import difflib
    import time
    a = json.dumps(old, ensure_ascii=False, indent=2).splitlines()
    b = json.dumps(new, ensure_ascii=False, indent=2).splitlines()
    for line in difflib.unified_diff(a, b, f"{f.name} (antes)", f"{f.name} (depois)", lineterm="", n=1):
        print(line)
    bk = f.with_name(f"{f.stem}.antes-{slug}-{time.strftime('%Y%m%d-%H%M%S')}{f.suffix}")
    n = 1
    while bk.exists():
        bk = f.with_name(f"{f.stem}.antes-{slug}-{time.strftime('%Y%m%d-%H%M%S')}-{n}{f.suffix}")
        n += 1
    bk.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    f.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bk


def _record(state_dir: Path, slug: str, f: Path) -> None:
    import time
    sp = state_dir / "state.json"
    if not sp.exists():
        return
    st = json.loads(sp.read_text(encoding="utf-8"))
    st.setdefault("modelos", []).append({"slug": slug, "file": str(f), "when": time.strftime("%Y-%m-%d %H:%M")})
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def apply_file(slug: str, target: Path, planos: list[int] | None, params: dict[str, str]) -> Path:
    """Apply a modelo to a file and return the backup path. Host comes from the recipe, not the file name."""
    m = load(slug)
    target = Path(target)
    if m.host == "montagem":
        old = json.loads(target.read_text(encoding="utf-8"))
        if "shots" not in old:
            raise SystemExit(f"{target} não é um plano do beat_edit (sem 'shots'); {slug} é um modelo de montagem")
        new = apply_montagem(m, old, planos, params)
        if new == old:
            print(f"  {slug}: nada mudou (já aplicado)")
        bk = _write_with_backup(target, old, new, slug)
        _record(target.parent, slug, target)
        return bk
    return apply_reel_file(m, target, planos)
