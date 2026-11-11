"""Entregas versionadas — nenhum render sobrescreve um vídeo já entregue (F6.2).

Até aqui `render_phase2.py` e `deliver_mix.py` gravavam sempre `final.mp4`: a
entrega aprovada de ontem sumia no render de hoje. Agora cada render grava num
caminho NOVO, `final_vNN.mp4`, e `final.mp4` passa a apontar para a versão mais
recente (hardlink trocado de forma atômica; cópia se o disco não suportar).

Por que caminho novo e não "copiar depois": o ffmpeg com `-y` TRUNCA o arquivo
de destino — se `final.mp4` fosse um hardlink de uma versão, o próximo render
apagaria aquela versão junto. Gravar sempre num arquivo novo torna isso
impossível por construção. Um `final.mp4` antigo (de antes do versionamento) é
preservado como `final_v01.mp4` na primeira entrega nova.

    from deliveries import next_path, publish
    out = next_path(edit)              # final_vNN.mp4 (preserva o final.mp4 legado)
    ... ffmpeg … out ...
    publish(edit, out, by="deliver_mix")

`<edit>/state.json` ganha `deliveries: [{v, file, by, at, size_mb}]`; o preview
continua tocando `finalVideo` (= final.mp4 = a mais recente).
Adaptado de `LeiteZ/fluxo-de-edicao` (nunca sobrescrever entrega, MIT).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

PAT = re.compile(r"^final_v(\d{2,})\.mp4$")


def versions(edit: Path) -> list[tuple[int, Path]]:
    out = []
    for p in Path(edit).glob("final_v*.mp4"):
        m = PAT.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def _state(edit: Path) -> tuple[Path, dict]:
    sp = Path(edit) / "state.json"
    try:
        return sp, json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sp, {}


def _record(edit: Path, v: int, p: Path, by: str) -> None:
    sp, st = _state(edit)
    if not sp.exists():
        return
    dl = [d for d in st.get("deliveries", []) if d.get("v") != v]
    dl.append({"v": v, "file": p.name, "by": by, "at": time.strftime("%Y-%m-%d %H:%M"),
               "size_mb": round(p.stat().st_size / 1e6, 1)})
    st["deliveries"] = sorted(dl, key=lambda d: d["v"])
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def next_path(edit: Path) -> Path:
    edit = Path(edit)
    vs = versions(edit)
    final = edit / "final.mp4"
    if not vs and final.exists():
        # Entrega de antes do versionamento: vira a v01. VINCULADA, não movida —
        # se o render novo falhar, o final.mp4 continua no lugar (o ffmpeg grava
        # no caminho novo, nunca no final.mp4, então o vínculo é seguro).
        legacy = edit / "final_v01.mp4"
        try:
            os.link(final, legacy)
        except OSError:
            shutil.copy2(final, legacy)
        _record(edit, 1, legacy, "legado (antes do versionamento)")
        vs = [(1, legacy)]
    n = (vs[-1][0] + 1) if vs else 1
    return edit / f"final_v{n:02d}.mp4"


def publish(edit: Path, produced: Path, by: str) -> Path:
    edit, produced = Path(edit), Path(produced)
    m = PAT.match(produced.name)
    if not m:
        raise ValueError(f"{produced.name} não é uma versão final_vNN.mp4")
    final = edit / "final.mp4"
    tmp = edit / "final.mp4.tmp"
    tmp.unlink(missing_ok=True)
    try:
        os.link(produced, tmp)            # mesmo arquivo, sem custo de disco
    except OSError:
        shutil.copy2(produced, tmp)       # FAT/rede: cópia
    os.replace(tmp, final)                # atômico: final.mp4 nunca fica pela metade
    _record(edit, int(m.group(1)), produced, by)
    print(f"  entrega v{int(m.group(1)):02d}: {produced.name} → final.mp4"
          f"{' (hardlink)' if _same_file(produced, final) else ' (cópia)'}", flush=True)
    return final
