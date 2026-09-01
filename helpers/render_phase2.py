"""Re-render Phase 2 and rebuild the delivery — the whole chain, one command.

Exists so the preview can refresh the picture on its own. Before this, adjusting
an insert on the timeline changed edit-data.json and nothing else: the player
kept showing the previous render and the edit looked like it had not been
applied. A drawing that disagrees with the video is worse than no drawing.

    uv run python helpers/render_phase2.py --edit <edit_dir>

Two steps, in order:
  1. `remotion render` → remotion/out/render.mp4  (the picture)
  2. ffmpeg delivery   → final.mp4               (picture + approved audio)

Step 2 is not optional. Remotion's own audio drifts against the source — measured
on this project at +42.7ms (5s) → +364ms (40s), which is audible lip-sync loss by
the middle of a Reel. The delivery re-muxes cut.mp4's audio (the master approved
in Phase 1), mixes the soundtrack, and re-adds the layout-transition clicks that
the re-mux would otherwise discard.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

FPS_DEFAULT = 30
# Camadas visuais simultâneas toleradas. 4 dá margem sobre o "1-3 elementos"
# da literatura de glassmorphism, porque nem toda camada aqui é vidro — mas
# nove, que foi o caso reprovado, está fora de qualquer leitura.
MAX_CAMADAS = 4


def run(cmd, cwd=None, label=""):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-2500:]
        raise SystemExit(f"{label} falhou:\n{tail}")
    return r


def probe_duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out)


# Campos de edit-data.json que exigem a camada WebGL. Manter em sincronia com
# o schema do template — um campo 3D novo que não entre aqui renderiza preto
# silenciosamente, que é exatamente a falha que o --gl explícito existe para
# impedir.
_KEYS_3D = ("scene3d", "tracked", "glass")


def _uses_3d(ed: dict) -> bool:
    """A composição precisa de WebGL?

    True se houver bloco 3D no topo do edit-data, ou se qualquer insert pedir
    moldura de vidro / ancoragem 3D.
    """
    if any(ed.get(k) for k in _KEYS_3D):
        return True
    for it in (ed.get("inserts") or []):
        if not isinstance(it, dict):
            continue
        if it.get("frame") == "glass" or it.get("anchor3d"):
            return True
    for t in (ed.get("transitions") or []):
        if isinstance(t, dict) and t.get("type") in ("displace", "refract"):
            return True
    return False


def check_direction(ed: dict) -> list[str]:
    """Poka-Yoke da doutrina (OPUS-VFX-3D § D3/D4).

    Avisa, não bloqueia. Estas são regras de direção de arte, e há vídeo em que
    quebrá-las é a escolha certa — o que não pode acontecer é quebrá-las **sem
    perceber**, que é o caso comum quando cada transição é escrita isolada.

    D3 — uma primária (60-70% das trocas) + 1-2 acentos. Um vídeo com sete
         transições diferentes não parece rico, parece indeciso.
    D4 — a transição É a saída. Animar a saída de um insert E aplicar uma
         transição no mesmo instante faz os dois se anularem.
    """
    avisos: list[str] = []
    trs = [t for t in (ed.get("transitions") or []) if isinstance(t, dict)]

    # --- excesso de camadas -------------------------------------------------
    # Duas literaturas independentes convergem: "reserve o vidro para 1-3
    # elementos por tela" (glassmorphism) e "se um elemento desliza, outro gira
    # e outro dá glitch, o estilo vira a mensagem" (motion graphics). O efeito
    # funciona por CONTRASTE com o sóbrio.
    #
    # Este aviso existe porque o gate permitiu marcar nove elementos de uma vez,
    # e o vídeo resultante foi reprovado. A UI oferece as opções; ninguém dizia
    # que somá-las todas é o erro que a literatura descreve.
    pesadas = [
        ("glass", bool((ed.get("glass") or {}).get("enabled"))),
        ("tracked", bool((ed.get("tracked") or {}).get("enabled"))),
        ("highlights", bool((ed.get("highlights") or {}).get("enabled"))),
        ("text3d", bool((ed.get("text3d") or {}).get("enabled"))),
        ("inserts", bool(ed.get("inserts"))),
        ("shader cuts", any(t.get("type") in ("displace", "refract") for t in trs)),
        ("transições overlay", any(t.get("type") in (None, "flash", "whip-pan", "glitch")
                                   for t in trs)),
    ]
    ligadas = [n for n, on in pesadas if on]
    if len(ligadas) > MAX_CAMADAS:
        avisos.append(
            f"EXCESSO: {len(ligadas)} camadas visuais ao mesmo tempo "
            f"({', '.join(ligadas)}). A doutrina pede {MAX_CAMADAS} ou menos — "
            f"o efeito funciona por contraste com o sóbrio, e somar tudo faz o "
            f"estilo virar a mensagem. Ver references/direction.md")

    # --- D3 -----------------------------------------------------------------
    if len(trs) >= 3:
        tipos: dict[str, int] = {}
        for t in trs:
            k = str(t.get("type") or "flash")
            tipos[k] = tipos.get(k, 0) + 1
        ordenados = sorted(tipos.items(), key=lambda kv: -kv[1])
        principal, n = ordenados[0]
        share = n / len(trs)
        if len(tipos) > 3:
            avisos.append(
                f"D3: {len(tipos)} tipos de transição em {len(trs)} cortes "
                f"({', '.join(k for k, _ in ordenados)}). A doutrina pede UMA "
                f"primária + 1-2 acentos — ver references/direction.md")
        elif share < 0.5 and len(trs) >= 4:
            avisos.append(
                f"D3: nenhuma transição domina ('{principal}' em {share*100:.0f}% "
                f"dos cortes). Sem uma primária clara o vídeo lê como indeciso")

    # --- D4 -----------------------------------------------------------------
    # Um insert cuja saída coincide com uma transição: a transição já É a saída,
    # e o fade do insert a esvazia. Meio frame de tolerância, porque os tempos
    # vêm de fontes diferentes (EDL e edição manual).
    fps = float(ed.get("fps") or FPS_DEFAULT)
    tol = 0.5 / fps
    for it in (ed.get("inserts") or []):
        if not isinstance(it, dict) or "end" not in it:
            continue
        for t in trs:
            at = t.get("at")
            if at is None:
                continue
            if abs(float(at) - float(it["end"])) <= tol:
                avisos.append(
                    f"D4: o insert que termina em {it['end']}s coincide com a "
                    f"transição em {at}s. A transição É a saída — os dois no "
                    f"mesmo instante se anulam. Afaste um deles ou remova a "
                    f"transição")
    return avisos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit", required=True, help="the <videos_dir>/edit directory")
    ap.add_argument("--skip-render", action="store_true",
                    help="only rebuild the delivery from the existing render")
    ap.add_argument("--gl", default=None,
                    choices=["angle", "swiftshader", "angle-egl", "vulkan", "swangle"],
                    help="backend WebGL do Chromium. Sem isto, é escolhido "
                         "automaticamente: 'angle' quando a cena usa 3D, "
                         "nenhum quando é 2D. Passe explicitamente só para "
                         "diagnosticar render preto ou diferença entre máquinas")
    args = ap.parse_args()

    edit = pathlib.Path(args.edit).resolve()
    rem = edit / "remotion"
    pub = rem / "public"
    render = rem / "out" / "render.mp4"
    ed_p = pub / "edit-data.json"

    if not ed_p.exists():
        raise SystemExit(f"sem edit-data.json em {pub}")
    ed = json.loads(ed_p.read_text(encoding="utf-8"))
    fps = int(ed.get("fps") or FPS_DEFAULT)
    video_lag_ms = 1000 // fps  # OffthreadVideo draws one frame late

    # Antes do render: um aviso depois de 2 minutos de encode chega tarde.
    for aviso in check_direction(ed):
        print(f"[direção] {aviso}", flush=True)

    if not args.skip_render:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            raise SystemExit("npx não encontrado no PATH")

        cmd = [npx, "remotion", "render", "Reels", "out/render.mp4"]

        # --gl: sem backend explícito o Chromium headless pode não expor WebGL,
        # e a ThreeCanvas rende PRETO — um defeito que se disfarça de "o shader
        # não funciona" e manda você depurar o lugar errado. Só passamos a flag
        # quando a cena de fato usa 3D, para não mudar o caminho 2D que já
        # funciona (ver OPUS-VFX-3D.md § V2/V3).
        #
        # Medido em 2026-08-31 (RTX 5070, Windows, Remotion 4.0.482, 30 frames
        # a 540x960): 'angle' 11.25s · 'swiftshader' 11.13s · sem 3D 10.45s.
        # Os dois backends produzem pixels idênticos (25.20% de cobertura do
        # cubo de prova). O default do Chromium também renderizou WebGL nesta
        # máquina, mas depende de GPU/driver — declarar o backend torna o
        # resultado reprodutível em outra, e é isso que a flag compra.
        gl = args.gl or ("angle" if _uses_3d(ed) else None)
        if gl:
            cmd.append(f"--gl={gl}")

        print(f"[1/2] remotion render…{f' (--gl={gl})' if gl else ''}", flush=True)
        run(cmd, cwd=str(rem), label="remotion render")

    if not render.exists():
        raise SystemExit(f"sem render em {render}")

    print("[2/2] montando entrega…", flush=True)
    vd = probe_duration(render)
    fade_start = max(0.0, vd - 1.5)

    st = ed.get("soundtrack") or {}
    music = pub / (st.get("file") or "trilha.mp3")
    use_music = bool(st.get("enabled")) and music.exists()

    # cut-click reads at -2 dB; click2 in the same pack sits at -25 dB and is
    # inaudible under speech. Verify before trusting a pack file.
    click = pub / "sfx" / "cut-click.mp3"
    sfx_times = [t["at"] for t in (ed.get("transitions") or [])] if click.exists() else []

    inputs = ["-i", str(render), "-i", str(edit / "cut.mp4")]
    if use_music:
        inputs += ["-i", str(music)]
    for _ in sfx_times:
        inputs += ["-i", str(click)]

    # Remotion writes yuvj420p / range=pc / primaries=bt470bg (PAL). Copying that
    # into the delivery shifts hue on a compliant player and crushes blacks on one
    # that ignores the range tag — the Phase-1 grade drifts at the last step.
    parts = [
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]",
        f"[1:a]adelay={video_lag_ms}:all=1[v]",
    ]
    mix = ["[v]"]
    idx = 2
    if use_music:
        vol = st.get("volume", 0.25)
        parts.append(f"[{idx}:a]volume={vol},afade=t=in:st=0:d=0.4,"
                     f"afade=t=out:st={fade_start:.3f}:d=1.5[m]")
        mix.append("[m]")
        idx += 1
    for n, t in enumerate(sfx_times):
        lbl = f"[s{n}]"
        parts.append(f"[{idx+n}:a]adelay={int(round(t*1000))+video_lag_ms}:all=1,"
                     f"volume=0.5{lbl}")
        mix.append(lbl)

    if len(mix) > 1:
        parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[mix]")
        last = "[mix]"
    else:
        last = "[v]"
    parts.append(f"{last}loudnorm=I=-14:TP=-1:LRA=11[out]")

    final = edit / "final.mp4"
    run(["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(parts),
         "-map", "[vid]", "-map", "[out]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-color_range", "tv",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-t", str(vd), "-movflags", "+faststart", str(final)],
        label="ffmpeg delivery")

    print(f"pronto: {final} ({vd:.3f}s, {len(sfx_times)} cliques, "
          f"trilha={'sim' if use_music else 'não'})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
