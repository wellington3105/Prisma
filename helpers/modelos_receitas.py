"""The editing-models library: load recipes, validate them, apply them.

A *modelo* is a named editing type (`tipo`: speed ramp, whip pan, zoom punch…) or a style
(`estilo`: a combination of tipos with rules). Each lives in `modelos/<tipos|estilos>/<slug>/`
as `modelo.json` (the recipe) + `MODELO.md` (the sheet). The recipe only writes formats the
current tools already read:
  host "montagem"  -> a beat_edit plan.json
  host "reel-fala" -> state.json `style` + the Phase-2 edit-data.json
  host "cena"      -> a self-contained HyperFrames scene (cenas.py) in <edit>/cenas/<slug>/
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
    for e in [x for f in fx for x in _expand(f, params)]:
        if not beat_edit.valid_fx(e):
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
        if m.host not in ("montagem", "reel-fala", "corte", "cena"):
            probs.append(f"{pasta}: host '{m.host}' (use montagem, reel-fala, corte ou cena)")
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
        elif m.host == "cena":
            import cenas
            if m.dados.get("cena") not in cenas.CENAS:
                probs.append(f"{m.slug}: cena '{m.dados.get('cena')}' não existe (use {', '.join(cenas.CENAS)})")
        elif m.host == "corte":
            import render
            mode = (m.dados.get("edl", {}).get("jcut") or {}).get("mode")
            if mode is not None and mode not in render.JCUT_MODES:
                probs.append(f"{m.slug}: jcut.mode '{mode}' não existe no render (use {', '.join(render.JCUT_MODES)})")
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


def _set_ramp(sh: dict, new: str) -> None:
    """A shot between two speed cuts needs both ramps: speed-in then speed-out = speed-inout."""
    cur = sh.get("ramp")
    if {cur, new} == {"speed-in", "speed-out"} or (cur == "speed-inout" and new in ("speed-in", "speed-out")):
        sh["ramp"] = "speed-inout"
    else:
        sh["ramp"] = new


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
            if planos[0] == 0:
                raise SystemExit(f"{m.slug}: o plano 0 não tem corte de entrada; comece o intervalo no plano 1")
            shots[planos[0]]["transition"] = ap["transicao_primeiro"]
        _add_fx(shots[planos[-1]], ap.get("fx_ultimo", []))
        return
    if 0 in planos and "transition" in ap.get("por_plano", {}):
        raise SystemExit(f"{m.slug}: o plano 0 não tem corte de entrada (a transição entra NO plano); use 1 ou mais")
    for i in planos:
        for campo, valor in ap.get("por_plano", {}).items():
            shots[i][campo] = _fill(valor, params)
        if ap.get("fx"):
            _add_fx(shots[i], [_fill(e, params) for e in ap["fx"]])
        if ap.get("ramp_entrada"):
            _set_ramp(shots[i], ap["ramp_entrada"])
        if ap.get("ramp_saida"):
            if i == 0:
                raise SystemExit(f"{m.slug}: o plano 0 não tem plano anterior para acelerar até o corte")
            _set_ramp(shots[i - 1], ap["ramp_saida"])


def apply_montagem(m: Modelo, plan: dict, planos: list[int] | None, params: dict[str, str]) -> dict:
    new = json.loads(json.dumps(plan))
    shots = new.get("shots", [])
    limite = MAX_ACENTOS
    if m.nivel == "estilo":
        limite = m.dados.get("regras", {}).get("max_acentos", MAX_ACENTOS)
        prim = load(m.dados["regras"]["primaria"])
        alvo = planos if planos is not None else list(range(1, len(shots)))
        mantidos = [k for k in alvo if shots[k].get("transition") in ACCENT_TRANSITIONS]
        if mantidos:
            print(f"  {m.slug}: mantidos os acentos feitos à mão nos planos {', '.join(map(str, mantidos))}")
            alvo = [k for k in alvo if k not in mantidos]
        _apply_tipo_montagem(prim, shots, alvo, _params(prim, {}))
    else:
        if not planos:
            raise SystemExit(f"{m.slug} é um tipo: diga em quais planos com --plano N (os planos vão de 0 a {len(shots) - 1})")
        _apply_tipo_montagem(m, shots, planos, _params(m, params))
    if len(count_accents(new)) > limite and len(count_accents(new)) > len(count_accents(plan)):
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


def apply_file(slug: str, target: Path, planos: list[int] | None, params: dict[str, str]) -> list[Path]:
    """Apply a modelo and return the backup paths. Host comes from the recipe, not the file name."""
    m = load(slug)
    target = Path(target)
    if m.host == "montagem":
        old = json.loads(target.read_text(encoding="utf-8"))
        if "shots" not in old:
            raise SystemExit(f"{target} não é um plano do beat_edit (sem 'shots'); {slug} é um modelo de montagem")
        new = apply_montagem(m, old, planos, params)
        if new == old:
            print(f"  {slug}: nada mudou (já aplicado); nada foi gravado")
            return []
        bk = _write_with_backup(target, old, new, slug)
        _record(target.parent, slug, target)
        return [bk]
    if m.host == "corte":
        return apply_corte_file(m, target)
    if m.host == "cena":
        return apply_cena_file(m, target, params)
    return apply_reel_file(m, target, planos)


def cena_dados(m: Modelo, base: dict, params: dict[str, str]) -> dict:
    """The recipe's default data, then a dados.json (base), then --param k=v on top.
    pilulas=icone:texto[:cor]|icone:texto…  (ex.: cor:Branco Polar:#f2f2f2|potencia:185 cv)"""
    dados = {**m.dados.get("dados", {}), **base}
    for k, v in params.items():
        if k == "pilulas":
            pills = []
            for item in filter(None, v.split("|")):
                parts = item.split(":")
                p = {"icone": parts[0], "texto": parts[1] if len(parts) > 1 else ""}
                if len(parts) > 2:
                    p["cor"] = ":".join(parts[2:])
                pills.append(p)
            dados["pilulas"] = pills
        else:
            dados[k] = v
    return dados


def apply_cena_file(m: Modelo, target: Path, params: dict[str, str]) -> list[Path]:
    """Host "cena": build the scene project in <edit>/cenas/<slug>/ (target = the edit folder, or a
    dados.json beside it). Rendering is a separate step: cenas.py render <pasta>."""
    import cenas
    target = Path(target)
    base = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    edit = target.parent if target.is_file() else target
    out = cenas.build(m.dados["cena"], cena_dados(m, base, params), edit / "cenas" / m.slug)
    print(f"  cena {m.slug} → {out}")
    print(f'  render: python helpers/cenas.py render "{out}"')
    return []


def apply_corte_file(m: Modelo, target: Path) -> list[Path]:
    """Host "corte": the Phase-1 EDL (edl.json). Allowed before the cut is approved — it IS the cut."""
    edit = _edit_dir_of(Path(target))
    f = Path(target) if Path(target).is_file() else edit / "edl.json"
    if not f.exists():
        raise SystemExit(f"{m.slug}: não achei {f}")
    old = json.loads(f.read_text(encoding="utf-8"))
    new = _merge(json.loads(json.dumps(old)), m.dados.get("edl", {}))
    if new == old:
        print(f"  {m.slug}: nada mudou (já aplicado); nada foi gravado")
        return []
    bk = _write_with_backup(f, old, new, m.slug)
    _record(edit, m.slug, f)
    print(f"  {m.slug}: re-renderize o corte (render.py) para ver o efeito")
    return [bk]


# ---------------------------------------------------------------- reel-fala
REEL_ACCENTS = REEL_TRANSITIONS


def _edit_data_path(edit: Path) -> Path | None:
    for c in (edit / "remotion" / "public" / "edit-data.json", edit / "edit-data.json"):
        if c.exists():
            return c
    return None


def _merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = json.loads(json.dumps(v))
    return dst


def _cut_times(ed_path: Path) -> list[float]:
    sp = ed_path.parent / "segments.json"
    if not sp.exists():
        raise SystemExit(f"falta {sp} (os pontos de corte vêm dele); rode o scaffold da Fase 2 antes")
    segs = json.loads(sp.read_text(encoding="utf-8")).get("segments", [])
    return [round(float(s["start"]), 3) for s in segs[1:]]


def _reel_tipos(m: Modelo) -> list[Modelo]:
    return [load(t) for t in m.dados.get("tipos", [])] if m.nivel == "estilo" else [m]


def apply_reel(m: Modelo, edit: Path, planos: list[int] | None = None) -> tuple[dict, dict | None]:
    """New state.json and new edit-data.json (None when the edit-data does not exist yet). Pure: writes nothing."""
    sp = edit / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    if int(st.get("phase", 1) or 1) < 2:
        raise SystemExit(f"{m.slug}: só depois do corte aprovado (state.json phase ≥ 2; está em {st.get('phase', 1)})")
    st = json.loads(json.dumps(st))
    style = st.setdefault("style", {})
    if m.nivel == "estilo":
        _merge(style, m.dados.get("padroes", {}).get("style", {}))
    for t in _reel_tipos(m):
        _merge(style, t.dados.get("style", {}))
    st["awaitingStyle"] = True

    ed_path = _edit_data_path(edit)
    if ed_path is None:
        return st, None
    ed = json.loads(ed_path.read_text(encoding="utf-8"))
    limite = m.dados.get("regras", {}).get("max_acentos", MAX_ACENTOS)
    for t in _reel_tipos(m):
        patch = t.dados.get("edit_data", {})
        if "camera" in patch:
            ed.setdefault("camera", {})
            _merge(ed["camera"], patch["camera"])
        tr = patch.get("transitions_em_cada_corte")
        if tr:
            cuts = _cut_times(ed_path)
            if planos:
                bad = [i for i in planos if not 0 <= i < len(cuts)]
                if bad:
                    raise SystemExit(f"{t.slug}: cortes {bad} não existem (há {len(cuts)}, de 0 a {len(cuts) - 1})")
                cuts = [cuts[i] for i in planos]
            existentes = [x for x in ed.get("transitions", []) if round(float(x.get("at", -1)), 3) not in cuts]
            novas = existentes + [dict(tr, at=c) for c in cuts]
            n_novas = sum(1 for x in novas if x.get("type", "flash") in REEL_ACCENTS)
            n_antes = sum(1 for x in ed.get("transitions", []) if x.get("type", "flash") in REEL_ACCENTS)
            if n_novas > limite and n_novas > n_antes:
                ja = [x for x in existentes if x.get("type", "flash") in REEL_ACCENTS]
                todos = ", ".join(f"{i}: {c}s" for i, c in enumerate(_cut_times(ed_path)))
                if ja:
                    lista = ", ".join(f"{x['at']}s {x.get('type', 'flash')}" for x in ja)
                    raise SystemExit(f"{t.slug}: passaria de {limite} acentos. Já existem {len(ja)} transições de acento "
                                     f"no edit-data ({lista}); tire alguma antes, ou escolha menos cortes com --plano "
                                     f"(cortes: {todos}).")
                raise SystemExit(f"{t.slug}: passaria de {limite} acentos. Escolha até {limite} cortes com --plano "
                                 f"(cortes: {todos}).")
            ed["transitions"] = sorted(novas, key=lambda x: x["at"])
    return st, ed


def _print_profile_rules(st: dict) -> None:
    cli = st.get("client")
    if not cli:
        return
    import importlib
    import client_profile
    cp = importlib.reload(client_profile)
    if not cp.ppath(cli).exists():
        return
    prof = cp.load(cli)
    print(f"  regras do perfil '{cli}' (confira contra o modelo):")
    for r in prof.get("rules", []):
        print(f"    - {r['text']}")


def apply_reel_file(m: Modelo, target: Path, planos: list[int] | None) -> list[Path]:
    """Edit-data first, then state.json (with the modelo record folded in): if the edit-data is locked
    (open in the Studio), nothing is written; if state.json then fails, the edit-data is restored."""
    import time
    edit = _edit_dir_of(Path(target))
    sp = edit / "state.json"
    if not sp.exists():
        raise SystemExit(f"{m.slug}: não achei state.json em {edit} (passe a pasta edit/ do Reel)")
    old_st = json.loads(sp.read_text(encoding="utf-8"))
    new_st, new_ed = apply_reel(m, edit, planos)
    ed_path0 = _edit_data_path(edit)
    old_ed = json.loads(ed_path0.read_text(encoding="utf-8")) if ed_path0 else None
    if new_st == old_st and new_ed == old_ed:
        print(f"  {m.slug}: nada mudou (já aplicado); nada foi gravado")
        return []
    new_st.setdefault("modelos", []).append({"slug": m.slug, "file": str(target), "when": time.strftime("%Y-%m-%d %H:%M")})
    _print_profile_rules(old_st)
    bks: list[Path] = []
    if new_ed is None:
        print(f"  {m.slug}: ainda não há edit-data.json; a camada concreta entra quando a Fase 2 for montada")
    else:
        ed_path = _edit_data_path(edit)
        bks.append(_write_with_backup(ed_path, json.loads(ed_path.read_text(encoding="utf-8")), new_ed, m.slug))
    try:
        bks.append(_write_with_backup(sp, old_st, new_st, m.slug))
    except OSError:
        if bks:
            _edit_data_path(edit).write_text(bks[0].read_text(encoding="utf-8"), encoding="utf-8")
        raise
    return bks
