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
import unicodedata

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


VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}


def check_media(ed: dict, pub: pathlib.Path) -> list[str]:
    """Todo vídeo que o edit-data aponta precisa abrir no ffprobe.

    Um clipe copiado enquanto o ffmpeg ainda o gravava não tem o átomo `moov`
    (fica no fim do arquivo). O Remotion só tropeça nele no meio do render, com
    um panic do compositor em Rust que não diz qual arquivo — medido no PPF X6
    (2026-11-03): ~4 min de render perdidos e um still por insert para achar o
    culpado. Aqui custa um ffprobe por arquivo, antes do encode."""
    srcs = ["cut.mp4"]
    for key in ("inserts", "behind", "splitInserts"):
        for it in (ed.get(key) or []):
            for k in ("src", "matte", "fg"):
                if isinstance(it.get(k), str):
                    srcs.append(it[k])
    bad = []
    for s in dict.fromkeys(srcs):
        p = pub / s
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        if not p.exists():
            bad.append(f"{s}: não existe em public/")
            continue
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            err = (r.stderr.strip().splitlines() or ["sem duração"])[-1]
            bad.append(f"{s}: não abre ({err}) — cópia incompleta? recopie depois que o "
                       f"processo que o grava terminar")
            continue
        # Com o índice no começo (+faststart) o ffprobe lê a duração de um arquivo
        # cortado ao meio; só decodificar o FIM mostra que os dados acabam antes.
        # O ffmpeg sai com 0 mesmo assim — o sinal é o stderr em -v error.
        t = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-0.5", "-i", str(p),
                            "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
        if t.stderr.strip():
            bad.append(f"{s}: o fim não decodifica ({t.stderr.strip().splitlines()[0][:90]}) — "
                       f"arquivo truncado")
    return bad


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


def check_direction(ed: dict, pub: pathlib.Path | None = None) -> list[str]:
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

    avisos += check_camadas_vazias(ed, pub)
    return avisos


# Um card se lê num relance ou não se lê. Acima disto ele quebra em quatro
# linhas e vira parágrafo — medido em still, com "ainda não ficou natural".
MAX_PALAVRAS_CARD = 3
# E o teto de CARACTERES, que é o que a pílula realmente impõe: uma palavra só,
# porém longa ("Estabilização", 13), passa no limite de palavras e mesmo assim
# estica o card. O número espelha `MAX_CHARS_CARD` no GlassCard.tsx.
MAX_CHARS_CARD = 12


def check_camadas_vazias(ed: dict, pub: pathlib.Path | None = None) -> list[str]:
    """Camada LIGADA e VAZIA — o defeito que só aparece depois do render.

    Os três avisos daqui vêm de reprovações reais do usuário, e todos os três
    eram legíveis no JSON antes de gastar o render:

      - `brollFull` marcado e `inserts: []` → *"o b-roll está selecionado mas
        nada aconteceu no vídeo"*. O checkbox dá permissão; ninguém forneceu o
        clipe.
      - `highlights.enabled` com item sem `text` → o painel de vidro vazio,
        reprovado com *"horrível"*.
      - card repetindo a palavra que a legenda mostra no mesmo instante → uma
        das duas camadas vira ruído. A regra de ofício é que texto REFORÇA, não
        duplica (PRP 2026-09-01).

    Avisa, não bloqueia: seguem a mesma política dos avisos de direção.
    """
    avisos: list[str] = []

    # --- camada ligada sem conteúdo ----------------------------------------
    hl = ed.get("highlights") or {}
    if hl.get("enabled"):
        itens = [i for i in (hl.get("items") or []) if isinstance(i, dict)]
        if not itens:
            avisos.append(
                "VAZIO: highlights ligado sem nenhum item. O card entra na tela "
                "como retângulo translúcido sem palavra — foi assim que a "
                "primeira versão do glass prism foi reprovada")
        for i in itens:
            txt = str(i.get("text") or "").strip()
            if not txt:
                avisos.append(f"VAZIO: card em {i.get('at')}s sem `text`")
            elif len(txt.split()) > MAX_PALAVRAS_CARD:
                avisos.append(
                    f"CARD LONGO: \"{txt}\" tem {len(txt.split())} palavras. "
                    f"Um card se lê num relance; acima de {MAX_PALAVRAS_CARD} "
                    f"ele quebra em várias linhas e vira parágrafo")
            elif len(txt) > (16 if (hl.get("variant") or "prism") == "prism" else MAX_CHARS_CARD):
                teto = 16 if (hl.get("variant") or "prism") == "prism" else MAX_CHARS_CARD
                avisos.append(
                    f"CARD ESTICADO: \"{txt}\" tem {len(txt)} caracteres "
                    f"(teto {teto}). O card é de UMA linha — o "
                    f"componente encolhe a fonte para caber, mas o termo fica "
                    f"menor que os outros. Prefira um sinônimo curto")

    # O bloco `glass` sozinho é o retângulo que só refrata o vídeo, SEM palavra.
    # Reprovado pelo usuário várias vezes (último: projeto Volvo XC60,
    # 2026-10-30): "Painel de vidro (3D)" no Estilo significa a PALAVRA em
    # destaque numa moldura de vidro-prisma — `highlights` com variant "prism".
    if (ed.get("glass") or {}).get("enabled") and not (ed.get("highlights") or {}).get("enabled"):
        avisos.append(
            "REPROVADO: bloco `glass` sem `highlights` — é o painel vazio que só "
            "refrata o vídeo. 'Painel de vidro (3D)' = palavras em destaque na "
            "moldura prisma: escreva `highlights` (variant prism) e remova `glass`")

    for chave, rotulo in (("tracked", "tracked"), ("text3d", "text3d")):
        bloco = ed.get(chave) or {}
        if bloco.get("enabled") and not (bloco.get("items") or bloco.get("objects")):
            avisos.append(f"VAZIO: {rotulo} ligado sem itens — nada aparecerá")

    # --- b-roll: permissão sem clipe ---------------------------------------
    # O `brollFull` do gate de estilo autoriza a cobertura em tela cheia; os
    # clipes são fornecidos à parte. Marcar um sem o outro produz um vídeo
    # idêntico ao anterior, e o usuário só descobre isso assistindo.
    quer_broll = bool((ed.get("style") or {}).get("brollFull")
                      or ed.get("brollFull"))
    if quer_broll and not (ed.get("inserts") or ed.get("behind")):
        avisos.append(
            "VAZIO: b-roll em tela cheia está selecionado mas `inserts` está "
            "vazio. O checkbox dá permissão, não fornece o clipe — rode "
            "helpers/broll_plan.py para saber ONDE cada cobertura entra e "
            "aponte o arquivo em `src`")

    # --- elemento agendado fora do vídeo ------------------------------------
    # Uma transição depois do último frame não toca nem aparece: o efeito é
    # escrito, contado nas estatísticas e silenciosamente descartado. Achado
    # neste vídeo com uma transição em 41.2s num vídeo de 40.5s — invisível
    # justamente porque não produz nada que se possa ver.
    dur_total = float(ed.get("durationSec") or 0)
    if dur_total > 0:
        for chave in ("transitions", "inserts", "highlights"):
            bloco = ed.get(chave)
            itens = bloco.get("items") if isinstance(bloco, dict) else bloco
            for it in (itens or []):
                if not isinstance(it, dict):
                    continue
                t = it.get("at", it.get("start"))
                if t is not None and float(t) >= dur_total:
                    avisos.append(
                        f"FORA DO VÍDEO: {chave[:-1]} em {t}s, mas o vídeo "
                        f"termina em {dur_total}s. Não vai tocar nem aparecer")

        # `segments.json` é escrito pelo scaffold a partir do EDL e sobrevive a
        # edições no edit-data — um segmento além do fim deixa um zoom órfão que
        # nunca renderiza. Achado em 2026-09-01: segmento em 41.2s num vídeo de
        # 40.5s, resquício de uma transição já removida.
        if pub:
            try:
                segs = json.loads((pub / "segments.json").read_text(encoding="utf-8"))
                for s in (segs.get("segments") or []):
                    if float(s.get("start", 0)) >= dur_total:
                        avisos.append(
                            f"FORA DO VÍDEO: segmento em {s['start']}s (vídeo "
                            f"termina em {dur_total}s) — o zoom desse bloco "
                            f"nunca aparece. Regere segments.json")
            except (OSError, json.JSONDecodeError, AttributeError, TypeError):
                pass

    # --- card duplicando a legenda -----------------------------------------
    # Card e legenda na tela ao mesmo tempo dizendo a MESMA palavra: uma das
    # camadas é redundante. Verificado em still, com "movimento" duas vezes.
    if pub and hl.get("enabled"):
        cap_p = pub / "captions.json"
        try:
            cap = json.loads(cap_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, AttributeError):
            cap = None
        if cap:
            palavras = cap if isinstance(cap, list) else cap.get("captions") or []
            atraso = float(hl.get("offsetS") or 0.8)
            for i in (hl.get("items") or []):
                if not isinstance(i, dict):
                    continue
                ini = float(i.get("at") or 0) + atraso
                fim = ini + float(i.get("dur") or 3.0)
                termos = {_norm_txt(w) for w in str(i.get("text") or "").split()}
                termos.discard("")
                for w in palavras:
                    if not isinstance(w, dict):
                        continue
                    t = float(w.get("startMs", w.get("start", 0) * 1000)) / 1000
                    if ini <= t <= fim and _norm_txt(str(w.get("text", ""))) in termos:
                        avisos.append(
                            f"DUPLICA: o card \"{i.get('text')}\" repete a "
                            f"palavra que a legenda mostra em {t:.1f}s. Texto "
                            f"REFORÇA, não duplica — o card deve dizer o que a "
                            f"palavra significa. Ver references/direction.md")
                        break

    return avisos


def _norm_txt(s: str) -> str:
    """Minúscula, sem acento e sem pontuação — para comparar card com legenda."""
    s = unicodedata.normalize("NFD", s.lower().strip(".,!?;:—-\"'()"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


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
    for aviso in check_direction(ed, pub):
        print(f"[direção] {aviso}", flush=True)

    if not args.skip_render:
        ruins = check_media(ed, pub)
        if ruins:
            raise SystemExit("mídia que o render não vai conseguir ler:\n  " + "\n  ".join(ruins))
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            raise SystemExit("npx não encontrado no PATH")

        # O template copiado decide a composição: shortform = "Reels",
        # longform = "Longform" (legenda queimada 16:9 vive nele também).
        try:
            root_src = (rem / "src" / "Root.tsx").read_text(encoding="utf-8")
        except OSError:
            root_src = ""
        comp = "Longform" if 'id="Longform"' in root_src else "Reels"
        cmd = [npx, "remotion", "render", comp, "out/render.mp4"]

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
    # Ending fade (edit-data.json `fadeOut`, seconds): picture to black and the
    # whole mix to silence over the same span, so the video does not stop dead
    # on its last frame. Applied here, after the render, because it is a
    # property of the delivery — no template code involved.
    fade_out = float(ed.get("fadeOut") or 0)
    fade_out = min(max(fade_out, 0.0), vd / 2) if fade_out else 0.0
    vfade = f",fade=t=out:st={vd - fade_out:.3f}:d={fade_out:.3f}" if fade_out else ""
    parts = [
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv{vfade}[vid]",
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
    # after loudnorm: fading first would lower the measured loudness and the
    # normaliser would push the whole video up to compensate
    afade = (f",afade=t=out:st={vd - fade_out:.3f}:d={fade_out:.3f}" if fade_out else "")
    parts.append(f"{last}loudnorm=I=-14:TP=-1:LRA=11{afade}[out]")

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from deliveries import next_path, publish
    final = next_path(edit)  # final_vNN.mp4 — nunca sobrescreve uma entrega (F6.2)
    run(["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(parts),
         "-map", "[vid]", "-map", "[out]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-color_range", "tv",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-t", str(vd), "-movflags", "+faststart", str(final)],
        label="ffmpeg delivery")
    publish(edit, final, by="render_phase2")

    print(f"pronto: {final} ({vd:.3f}s, {len(sfx_times)} cliques, "
          f"trilha={'sim' if use_music else 'não'})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
