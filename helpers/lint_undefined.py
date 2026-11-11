"""Gate de lint: falha só em NOME INDEFINIDO (o erro que quebra em produção).

`pyflakes` puro reprova por avisos antigos sem gravidade (import não usado) em
helpers que funcionam; nome indefinido é o que vira NameError na hora do render.
Neste opus (2026-11-03) ele pegou três antes de qualquer execução: `sys` não
importado no `beat_edit` e no `cinema_edit`, `Path` não importado no
`render_phase2`.

Uso: uv run --no-sync python helpers/lint_undefined.py   (exit 1 se houver)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

r = subprocess.run(["uvx", "pyflakes", str(HELPERS)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
bad = [ln for ln in (r.stdout + r.stderr).splitlines() if "undefined name" in ln]
if r.returncode not in (0, 1) and not bad:  # pyflakes nem rodou
    sys.exit(f"pyflakes não rodou (exit {r.returncode}): {(r.stderr or r.stdout)[-400:]}")
for ln in bad:
    print(ln)
print(f"{len(bad)} nome(s) indefinido(s) em {HELPERS}")
sys.exit(1 if bad else 0)
