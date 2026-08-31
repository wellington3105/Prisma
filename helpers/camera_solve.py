"""Recupera a pose da câmera a partir das trilhas de `camera_track.py`.

OPUS-VFX-3D, stories C3 e C4. Consome `tracks.json` e emite `camera.json`:
intrínsecos + rotação e translação por frame, no formato que a `<TrackedScene>`
consome sem conversão.

Método — solve incremental de dois quadros, propagado:

  1. `findEssentialMat` + `recoverPose` entre o primeiro par com paralaxe
     suficiente, o que fixa a origem e a escala (a translação sai NORMALIZADA:
     visão monocular não recupera escala métrica, e nada aqui finge que sim).
  2. Triangulação dos pontos vistos nesse par → nuvem esparsa.
  3. Para cada frame seguinte, `solvePnPRansac` dos pontos 3D já conhecidos
     contra suas projeções 2D. É mais estável que encadear poses relativas,
     que acumula deriva a cada passo.

**Erro de reprojeção é reportado sempre, em píxeis.** Acima de `MAX_REPROJ_PX`
o solve é declarado falho: uma pose que erra 5px coloca o objeto ancorado no
lugar errado, e "quase certo" aqui vira tremor visível.

Intrínsecos: sem dados EXIF, a distância focal é estimada como ~0.9x a largura
do quadro — aproximação razoável para câmera de celular (FOV horizontal ~55°).
Está documentado porque é uma suposição, não uma medição; `--focal` a substitui.

Uso:
    uv run python helpers/camera_solve.py tracks.json --out camera.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import cv2
import numpy as np

FOCAL_RATIO = 0.9        # f ≈ 0.9 * largura, para lente de celular sem EXIF
MIN_PAIR_PARALLAX = 2.0  # px, para escolher o par inicial
PAIR_SEARCH_DEPTH = 15   # quantos candidatos a par inicial avaliar
MIN_PNP_POINTS = 12      # pontos 3D visíveis mínimos para resolver um frame
MAX_REPROJ_PX = 2.0      # acima disto o solve não serve para ancorar
MAX_JUMP_RATIO = 0.10    # fração de passos que podem ser saltos de escala


# Razão distância-aos-pontos / baseline acima da qual o BA é mal condicionado.
# Medido no vídeo de referência: janela com razão 5 converge (5.88px → 0.59px);
# janelas com razão 1.473 e 5.917 divergem para 1e152, mesmo entrando a 0.37px.
# O erro de entrada não prevê a divergência — a geometria prevê.
MAX_DEPTH_BASELINE_RATIO = 500.0


def _ba_is_conditioned(poses: dict, pts3d: dict, obs: dict) -> tuple[bool, str]:
    """O BA tem geometria para trabalhar?

    Triangulação precisa de baseline: se as câmeras mal se afastam entre si em
    relação à distância dos pontos, o problema é degenerado e o otimizador foge
    para o infinito em vez de convergir. Verificar isto ANTES é a diferença
    entre reportar "geometria insuficiente" e devolver poses lixo.
    """
    if len(poses) < 3:
        return False, "menos de 3 poses"
    cs = np.array([(-np.asarray(R).T @ np.asarray(t).reshape(3, 1)).ravel()
                   for R, t in poses.values()])
    baseline = float(np.linalg.norm(cs.max(axis=0) - cs.min(axis=0)))
    if baseline <= 1e-9:
        return False, "câmeras coincidentes — baseline nula"
    vis = {t for f in poses for t in obs.get(f, ()) if t in pts3d}
    if len(vis) < MIN_PNP_POINTS:
        return False, f"apenas {len(vis)} pontos visíveis"
    X = np.array([pts3d[t] for t in vis])
    depth = float(np.median(np.linalg.norm(X - cs.mean(axis=0), axis=1)))
    ratio = depth / baseline
    if ratio > MAX_DEPTH_BASELINE_RATIO:
        return False, (
            f"geometria degenerada — profundidade/baseline = {ratio:,.0f} "
            f"(limite {MAX_DEPTH_BASELINE_RATIO:,.0f}). As câmeras quase não se "
            f"afastam em relação à cena; não há baseline para triangular")
    return True, f"razão profundidade/baseline = {ratio:.0f}"


def bundle_adjust(poses: dict, pts3d: dict, obs: dict, K: np.ndarray,
                  w: int, h: int) -> tuple[dict, dict, str]:
    """Refina poses e pontos JUNTOS, com escala global consistente.

    Sem esta etapa o solve incremental diverge: `recoverPose` devolve translação
    normalizada e cada `solvePnP` fixa escala por conta própria, então a escala
    passeia entre frames. Medido antes do BA no vídeo de referência: 30% dos
    passos eram saltos, apesar de 0.10px de erro de reprojeção — erro baixo não
    prova trajetória correta, e foi exatamente essa a armadilha aqui.

    Usa pycolmap (Ceres por baixo) em vez de um BA escrito à mão. A escolha está
    documentada em .omc/research/prisma-ba-2026-08-31/report.md: BA manual erra
    em silêncio, e este solve já custou duas correções desse tipo.

    Degrada com honestidade — sem pycolmap, devolve as poses intactas e diz que
    não refinou, em vez de fingir que refinou.
    """
    try:
        import pycolmap as pc
    except ImportError:
        return poses, pts3d, "pycolmap ausente — poses não refinadas (uv pip install pycolmap)"

    rec = pc.Reconstruction()
    rec.add_camera_with_trivial_rig(
        pc.Camera.create_from_model_name(1, "PINHOLE", float(K[0, 0]), w, h))

    # Cada frame vira uma imagem cujos points2D são as observações das trilhas
    # que já têm ponto 3D. `local` mapeia track_id → índice em points2D, que é o
    # que TrackElement referencia.
    local: dict[int, dict[int, int]] = {}
    for f in sorted(poses):
        vis = [t for t in obs[f] if t in pts3d]
        if not vis:
            continue
        im = pc.Image()
        im.image_id = int(f) + 1          # COLMAP trata id 0 como inválido
        im.camera_id = 1
        im.name = f"f{f}"
        im.points2D = [pc.Point2D(np.asarray(obs[f][t], dtype=float)) for t in vis]
        rec.add_image_with_trivial_frame(im)
        local[f] = {t: i for i, t in enumerate(vis)}

        R, t = poses[f]
        frame = rec.image(im.image_id).frame
        frame.rig_from_world = pc.Rigid3d(
            pc.Rotation3d(np.asarray(R, dtype=float)),
            np.asarray(t, dtype=float).ravel())
        # Definir a pose NÃO registra o frame. Sem register_frame o BA não vê
        # imagem nenhuma e "converge" instantaneamente sobre zero resíduos —
        # sintoma: reprojeção 0.000px antes e depois, que parece sucesso.
        rec.register_frame(frame.frame_id)

    # Um ponto 3D só entra se for visto por 2+ imagens: com uma só observação
    # não há o que triangular e o BA o trataria como grau de liberdade livre.
    ids: dict[int, int] = {}
    for tid, xyz in pts3d.items():
        tr = pc.Track()
        n = 0
        for f, loc in local.items():
            if tid in loc:
                tr.add_element(pc.TrackElement(int(f) + 1, loc[tid]))
                n += 1
        if n >= 2:
            ids[tid] = rec.add_point3D(np.asarray(xyz, dtype=float), tr)

    if len(ids) < MIN_PNP_POINTS:
        return poses, pts3d, f"apenas {len(ids)} pontos com 2+ observações — BA não aplicado"

    # Segunda poda, agora com a medição do PRÓPRIO COLMAP. A primeira usa o
    # mesmo `pts3d` que está sendo julgado, então pontos cuja triangulação
    # degenerou de forma consistente escapam dela. Medido: 38 pontos com erro
    # acima de 1e6 px sobreviviam à poda por mediana e sozinhos levavam a média
    # do BA a 1e151 — o Ceres então gastava toda a otimização neles.
    rec.update_point_3d_errors()
    ruins = [tid for tid, pid in ids.items()
             if not np.isfinite(rec.point3D(pid).error)
             or rec.point3D(pid).error > BA_OUTLIER_PX]
    for tid in ruins:
        rec.delete_point3D(ids.pop(tid))
    if len(ids) < MIN_PNP_POINTS:
        return poses, pts3d, (
            f"após remover {len(ruins)} outliers restaram {len(ids)} pontos — "
            f"BA não aplicado")

    opts = pc.BundleAdjustmentOptions()
    # Intrínsecos fixos: a focal é uma ESTIMATIVA (0.9x a largura), não uma
    # medição. Deixá-la variar faria o BA absorver o erro dela na geometria e
    # devolver uma reconstrução que fecha as contas com uma câmera que não é a
    # que filmou.
    opts.refine_focal_length = False
    opts.refine_principal_point = False
    opts.refine_extra_params = False
    opts.refine_points3D = True
    opts.refine_rig_from_world = True
    opts.print_summary = False

    # Loss robusta. O padrão do pycolmap é TRIVIAL (mínimos quadrados puros),
    # em que o resíduo entra ao quadrado: um único ponto errado por 1.000px pesa
    # um milhão de vezes mais que um errado por 1px, e o otimizador destrói a
    # solução inteira tentando agradá-lo. Foi exatamente o observado — entrada a
    # 13.6px divergindo para 1e150.
    # Cauchy cresce logaritmicamente: outliers passam a ter influência limitada
    # em vez de dominante. Escala em px, no tamanho do erro que ainda queremos
    # que conte como sinal.
    opts.ceres.loss_function_type = pc.LossFunctionType.CAUCHY
    opts.ceres.loss_function_scale = 2.0

    cfg = pc.BundleAdjustmentConfig()
    for f in local:
        cfg.add_image(int(f) + 1)
    for pid in ids.values():
        cfg.add_variable_point(pid)
    # Gauge freedom: a solução é única a menos de uma transformação de
    # similaridade. Sem fixar o referencial o otimizador pode derivar livremente.
    cfg.fix_gauge(pc.BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD)

    # `compute_mean_reprojection_error` lê um erro CACHEADO em cada Point3D, que
    # só existe depois de `update_point_3d_errors()`. Sem a chamada ele devolve
    # 0.000px — que parece sucesso e é, na verdade, ausência de medição. Custou
    # uma rodada de depuração; a chamada fica antes de cada leitura.
    rec.update_point_3d_errors()
    before = rec.compute_mean_reprojection_error()
    pc.create_default_bundle_adjuster(opts, cfg, rec).solve()
    rec.update_point_3d_errors()
    after = rec.compute_mean_reprojection_error()

    # Guarda contra divergência. Um otimizador pode piorar a solução, e neste
    # caso ele piora de forma espetacular (13.6px → 1e150). Sem esta guarda o
    # helper devolveria poses lixo com a etiqueta "refinado", que é pior do que
    # não refinar: o gate a jusante teria de adivinhar de quem é a culpa.
    if not np.isfinite(after) or after > before:
        return poses, pts3d, (
            f"BA DIVERGIU ({before:.2f}px → {after:.3g}px) — poses originais "
            f"preservadas. Provável má condicionamento da reconstrução inicial")

    novas = {}
    for f in local:
        # cam_from_world é método nesta versão, não propriedade — chamar.
        cfw = rec.image(int(f) + 1).cam_from_world
        p = cfw() if callable(cfw) else cfw
        novas[f] = (np.asarray(p.rotation.matrix()),
                    np.asarray(p.translation).reshape(3, 1))
    novos_pts = {tid: np.asarray(rec.point3D(pid).xyz) for tid, pid in ids.items()}

    return novas, novos_pts, f"BA: reprojeção {before:.3f}px → {after:.3f}px em {len(ids)} pontos"


# Distância máxima aceitável de um ponto triangulado, em unidades de baseline
# (a translação do recoverPose tem norma 1, então a baseline inicial vale ~1).
# Raios quase paralelos produzem pontos a 1e150 que passam no teste ingénuo
# `z > 0`: são "à frente da câmera" e completamente inúteis. Medido: sem este
# corte a reprojeção do BA saía em 1e150 px.
MAX_POINT_DEPTH = 500.0
OUTLIER_FLOOR_PX = 3.0   # piso da poda: nunca cortar abaixo disto
BA_OUTLIER_PX = 50.0     # corte duro antes do BA, medido pelo próprio COLMAP
# Passo máximo do centro da câmera entre frames consecutivos, em unidades de
# baseline (a translação do par inicial vale ~1). Uma câmera na mão a 30fps
# percorre uma fração da baseline por frame; 5.0 é folgado por design, e mesmo
# assim corta os saltos de 11.942 que o PnP produzia sem esta verificação.
MAX_CAMERA_STEP = 40.0
PNP_PASSES = 6           # passadas de PnP; para sozinho quando não ganha frames
PRED_TOLERANCE = 8.0     # desvio aceitável da predição, em múltiplos do passo
MIN_STEP_SLACK = 0.05    # folga absoluta, para quando a câmera está quase parada


def _valid_point(p: np.ndarray, R: np.ndarray, t: np.ndarray) -> bool:
    """O ponto triangulado é utilizável?

    Três testes, nesta ordem: finito (NaN/inf de raios paralelos), à frente da
    câmera (cheirality), e a uma distância plausível. O terceiro é o que faltava.
    """
    if not np.all(np.isfinite(p)):
        return False
    z = float((R @ p + np.asarray(t).ravel())[2])
    return 0.0 < z < MAX_POINT_DEPTH and float(np.linalg.norm(p)) < MAX_POINT_DEPTH


def _by_frame(tracks: list) -> dict[int, dict[int, tuple[float, float]]]:
    """{frame: {track_id: (x, y)}} — o formato que o PnP quer consultar."""
    out: dict[int, dict[int, tuple[float, float]]] = {}
    for tid, tr in enumerate(tracks):
        for f, x, y in tr:
            out.setdefault(int(f), {})[tid] = (x, y)
    return out


def solve(data: dict, focal: float | None = None, do_ba: bool = True) -> dict:
    w, h = data["width"], data["height"]
    K = np.array([
        [focal or FOCAL_RATIO * w, 0, w / 2.0],
        [0, focal or FOCAL_RATIO * w, h / 2.0],
        [0, 0, 1.0],
    ], dtype=np.float64)

    tracks = data["tracks"]
    obs = _by_frame(tracks)
    frames = sorted(obs)
    if len(frames) < 2:
        return {"ok": False, "reason": "menos de 2 frames com observações"}

    # ---- par inicial: primeiro com paralaxe suficiente ----------------------
    # O par inicial define origem, escala e a nuvem que ancora todo o resto —
    # escolher o PRIMEIRO que passa no limiar é ingênuo. Medido no material 4K:
    # f0→f1 tinha paralaxe suficiente (10.47px) mas só **3 inliers**, enquanto
    # f0→f2 dava **350**. O primeiro par matava o solve na largada.
    # Avaliar candidatos e ficar com o de mais inliers custa milissegundos.
    f0 = frames[0]
    best = None
    for f1 in frames[1:PAIR_SEARCH_DEPTH]:
        common = set(obs[f0]) & set(obs[f1])
        if len(common) < 40:
            continue
        ids = sorted(common)
        a = np.float64([obs[f0][i] for i in ids])
        b = np.float64([obs[f1][i] for i in ids])
        if float(np.hypot(*(b - a).T).mean()) < MIN_PAIR_PARALLAX:
            continue
        E_, mask_ = cv2.findEssentialMat(a, b, K, method=cv2.RANSAC,
                                         prob=0.999, threshold=1.0)
        if E_ is None or E_.shape != (3, 3):
            continue
        # Pontuar pelo que sobrevive ao recoverPose, não ao findEssentialMat.
        # Medido no material 4K: f0→f1 tinha 448 inliers na matriz essencial e
        # apenas **3** depois do recoverPose — quase tudo caía atrás da câmera
        # (falha de cheirality), sinal de paralaxe insuficiente para triangular.
        # A matriz essencial fecha as contas mesmo assim; a triangulação não.
        _, R_, t_, mp_ = cv2.recoverPose(E_, a, b, K, mask=mask_.copy())
        n_in = int((mp_.ravel() > 0).sum())
        if best is None or n_in > best[0]:
            best = (n_in, f1, ids, a, b, R_, t_, mp_)
    if best is None:
        return {"ok": False, "reason": "nenhum par de frames com paralaxe suficiente"}

    _, f1, ids, a, b, R, t, mask_pose = best

    # ---- triangulação: a nuvem esparsa que ancora todo o resto --------------
    P0 = K @ np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = K @ np.hstack([R, t])
    inl = (mask_pose.ravel() > 0)
    if inl.sum() < MIN_PNP_POINTS:
        return {"ok": False, "reason": f"apenas {int(inl.sum())} pontos sobreviveram ao recoverPose"}

    X = cv2.triangulatePoints(P0, P1, a[inl].T, b[inl].T)
    X = (X[:3] / X[3]).T                       # homogéneo → euclidiano
    pts3d = {tid: X[k] for k, tid in enumerate([i for i, m in zip(ids, inl) if m])}

    # Pontos atrás da câmera são reconstruções inválidas (cheirality), não
    # geometria distante — descartar em vez de deixar poluir o PnP. As chaves
    # são ids de trilha e precisam sobreviver ao filtro: reindexá-las
    # desalinharia os pontos 3D das observações 2D no PnP abaixo.
    pts3d = {tid: p for tid, p in pts3d.items() if _valid_point(p, R, t)}

    poses = {
        f0: (np.eye(3), np.zeros((3, 1))),
        f1: (R, t),
    }

    # ---- propagação por PnP, com a nuvem crescendo -------------------------
    # A nuvem do par inicial cobre só o que estava visível ali. Sem estendê-la,
    # o solve morre assim que a câmera se afasta desses pontos: medido no vídeo
    # de referência, 8 de 151 frames resolvidos. Cada frame novo triangula os
    # pontos que já têm pose em outro frame e ainda não estão na nuvem, e é isso
    # que mantém o PnP alimentado ao longo do clipe.
    errs: list[float] = []
    last_solved = f1
    # Centros já aceitos, para o teste de continuidade abaixo.
    _centres: list[np.ndarray] = [
        (-poses[f0][0].T @ poses[f0][1]).ravel(),
        (-poses[f1][0].T @ poses[f1][1]).ravel(),
    ]
    # Várias passadas. Uma só percorre os frames em ordem e descarta em
    # definitivo os que falham — mas um frame falha porque a nuvem ainda não
    # cobre o que ele vê, e a nuvem CRESCE a cada frame resolvido. Medido: com
    # passada única, 27 de 149 frames; os 122 restantes viam 155 pontos em
    # mediana e eram descartados antes de a nuvem chegar até eles.
    # O laço repete enquanto estiver ganhando frames, e para sozinho quando não.
    for _ in range(PNP_PASSES):
        ganhos = 0
        for f in frames:
            if f in poses:
                continue
            vis = [(tid, xy) for tid, xy in obs[f].items() if tid in pts3d]
            if len(vis) < MIN_PNP_POINTS:
                continue
            obj = np.float64([pts3d[tid] for tid, _ in vis])
            img = np.float64([xy for _, xy in vis])
            ok, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj, img, K, None, reprojectionError=3.0,
                flags=cv2.SOLVEPNP_ITERATIVE, confidence=0.999,
            )
            if not ok or inliers is None or len(inliers) < MIN_PNP_POINTS:
                continue
            Rf, _ = cv2.Rodrigues(rvec)

            # Continuidade física. O PnP resolve cada frame isoladamente e nada o
            # impede de devolver uma pose absurda que reprojeta bem nos inliers que
            # o RANSAC escolheu. Medido: centros de câmera a 11.942 unidades, com
            # baseline inicial de 1.0 — a câmera "teleportava", e era isso que fazia
            # o BA receber uma reconstrução impossível e o Ceres reportar
            # "Unable to perform dense Cholesky factorization".
            #
            # Uma câmera não salta. Rejeitar aqui é mais barato e mais honesto do
            # que deixar o otimizador tentar acomodar o impossível.
            centre = (-Rf.T @ tvec).ravel()
            if len(_centres) >= 2:
                # Predição por velocidade constante em vez de limiar fixo. Um limiar
                # absoluto compara com o último centro aceito e não sabe para onde a
                # câmera ia: numa panorâmica rápida ele rejeita poses corretas junto
                # com as absurdas (medido: 22 de 151 frames sobreviviam).
                # Prever onde a câmera DEVERIA estar e medir o desvio distingue
                # "movimento rápido" de "teleporte", que é a distinção que importa.
                pred = _centres[-1] + (_centres[-1] - _centres[-2])
                escala = max(float(np.linalg.norm(_centres[-1] - _centres[-2])), 1e-6)
                if float(np.linalg.norm(centre - pred)) > escala * PRED_TOLERANCE + MIN_STEP_SLACK:
                    continue
            elif _centres:
                if float(np.linalg.norm(centre - _centres[-1])) > MAX_CAMERA_STEP:
                    continue
            _centres.append(centre)
            poses[f] = (Rf, tvec)
            ganhos += 1

            proj, _ = cv2.projectPoints(obj[inliers.ravel()], rvec, tvec, K, None)
            errs.append(float(np.linalg.norm(
                proj.reshape(-1, 2) - img[inliers.ravel()], axis=1).mean()))

            # Estender a nuvem. O par de triangulação NÃO pode ser o frame anterior:
            # frames adjacentes têm baseline quase nula, os raios saem paralelos e o
            # ponto vai para o infinito ou para trás da câmera. Medido: com o frame
            # anterior o solve devolvia 0.27px de reprojeção e uma trajetória que
            # oscilava em torno de zero — erro baixo por overfit, câmera parada.
            # Escolher o frame resolvido MAIS DISTANTE que ainda compartilhe pontos
            # dá baseline real, que é o que triangulação precisa.
            cand = [g for g in poses if g != f and len(set(obs[g]) & set(obs[f])) >= 8]
            if cand:
                ref = max(cand, key=lambda g: abs(g - f))
                Rp, tp = poses[ref]
                novos = [tid for tid in (set(obs[f]) & set(obs[ref])) if tid not in pts3d]
                if len(novos) >= 8:
                    Pa = K @ np.hstack([Rp, tp])
                    Pb = K @ np.hstack([Rf, tvec])
                    pa = np.float64([obs[ref][t] for t in novos]).T
                    pb = np.float64([obs[f][t] for t in novos]).T
                    Xn = cv2.triangulatePoints(Pa, Pb, pa, pb)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        Xn = (Xn[:3] / Xn[3]).T
                    for tid, p in zip(novos, Xn):
                        if _valid_point(p, Rf, tvec):
                            pts3d[tid] = p

        if ganhos == 0:
            break   # a nuvem parou de crescer; mais passadas não ajudam

    if len(poses) < 3:
        return {"ok": False, "reason": f"só {len(poses)} frames resolvidos"}

    # ---- bundle adjustment: a etapa que faltava ----------------------------
    # Roda ANTES das métricas de qualidade, porque são elas que julgam o
    # resultado final — medir o solve cru e depois refinar seria reportar um
    # número que não corresponde ao que foi gravado.
    # Poda de outliers. O erro MEDIANO por frame já era 0.1–1.0px, mas alguns
    # pontos reprojetavam a 57.000px — mal triangulados, e nunca removidos.
    # Média é sensível a eles: bastavam alguns para a métrica global explodir e,
    # pior, para o BA gastar todo o esforço tentando acomodá-los.
    # Mediana + MAD em vez de média + desvio, justamente porque a estatística
    # que decide não pode ser refém do que ela deveria descartar.
    err_por_ponto: dict[int, list[float]] = {}
    for f, (Rf, tf) in poses.items():
        vis = [(t, xy) for t, xy in obs[f].items() if t in pts3d]
        if not vis:
            continue
        objp = np.float64([pts3d[t] for t, _ in vis])
        imgp = np.float64([xy for _, xy in vis])
        rv, _ = cv2.Rodrigues(np.asarray(Rf, dtype=np.float64))
        pr, _ = cv2.projectPoints(objp, rv, np.asarray(tf, dtype=np.float64), K, None)
        for (tid, _), e in zip(vis, np.linalg.norm(pr.reshape(-1, 2) - imgp, axis=1)):
            err_por_ponto.setdefault(tid, []).append(float(e))

    if err_por_ponto:
        med_pt = {t: float(np.median(v)) for t, v in err_por_ponto.items()}
        vals = np.fromiter(med_pt.values(), dtype=float)
        corte = max(float(np.median(vals)) * 5.0, OUTLIER_FLOOR_PX)
        pts3d = {t: p for t, p in pts3d.items() if med_pt.get(t, 0.0) <= corte}

    if len(pts3d) < MIN_PNP_POINTS:
        return {"ok": False, "reason": "poda de outliers deixou pontos demais de fora"}

    ba_note = "BA desativado"
    if do_ba:
        ok_ba, why = _ba_is_conditioned(poses, pts3d, obs)
        if ok_ba:
            poses, pts3d, ba_note = bundle_adjust(poses, pts3d, obs, K, w, h)
        else:
            ba_note = f"BA não aplicado — {why}"

    # Reprojeção recalculada sobre as poses finais, não a média acumulada do PnP.
    errs2: list[float] = []
    for f, (Rf, tf) in poses.items():
        vis = [(t, xy) for t, xy in obs[f].items() if t in pts3d]
        if len(vis) < 4:
            continue
        objp = np.float64([pts3d[t] for t, _ in vis])
        imgp = np.float64([xy for _, xy in vis])
        rv, _ = cv2.Rodrigues(np.asarray(Rf, dtype=np.float64))
        pr, _ = cv2.projectPoints(objp, rv, np.asarray(tf, dtype=np.float64), K, None)
        errs2.append(float(np.linalg.norm(pr.reshape(-1, 2) - imgp, axis=1).mean()))
    if errs2:
        errs = errs2

    reproj = float(np.mean(errs)) if errs else float("nan")

    # Sanidade de trajetória. Erro de reprojeção baixo NÃO basta: uma primeira
    # versão deste solve devolvia 0.27px com a câmera oscilando em torno da
    # origem — poses quase idênticas reprojetam bem localmente e mentem sobre o
    # movimento. Se as features andam na tela (o gate de camera_track garante
    # paralaxe) mas a câmera reconstruída fica parada, a reconstrução colapsou.
    cs = []
    for f in sorted(poses):
        Rf, tf = poses[f]
        cs.append((-Rf.T @ tf).ravel())
    cs = np.asarray(cs)
    steps = np.linalg.norm(np.diff(cs, axis=0), axis=1) if len(cs) > 1 else np.array([0.0])
    path = float(steps.sum())
    span = float(np.linalg.norm(cs.max(axis=0) - cs.min(axis=0)))
    # A translação do recoverPose é unitária, então o par inicial vale ~1.0 de
    # baseline. Um caminho que não chega a 5% disso é colapso, não câmera lenta.
    collapsed = span < 0.05

    # Suavidade. Uma câmera real acelera continuamente; saltos entre frames
    # adjacentes são artefato do solve, não do movimento. Medido no vídeo de
    # referência: 30% dos passos acima de 8x a mediana, o maior 3.86 contra
    # passo mediano de 0.007 — um objeto ancorado nisso tremeria de forma
    # visível, que é pior que não ter o recurso.
    #
    # A causa é conhecida e não é um bug pontual: `recoverPose` devolve
    # translação NORMALIZADA, e cada PnP subsequente fixa escala por conta
    # própria. Sem bundle adjustment global a escala oscila entre frames.
    med = float(np.median(steps)) if len(steps) else 0.0
    jumps = int((steps > max(med * 8.0, 1e-9)).sum()) if med > 0 else 0
    jump_ratio = jumps / len(steps) if len(steps) else 0.0
    jittery = jump_ratio > MAX_JUMP_RATIO

    ok = (reproj <= MAX_REPROJ_PX) and not collapsed and not jittery
    return {
        "ok": ok,
        "reason": (
            f"solve ok — erro de reprojeção {reproj:.2f}px, "
            f"trajetória com extensão {span:.2f}"
            if ok else
            f"trajetória colapsada (extensão {span:.3f}) — as poses ficaram "
            f"praticamente idênticas apesar do movimento na tela; a reconstrução "
            f"não é utilizável para ancorar"
            if collapsed else
            f"trajetória instável — {jump_ratio*100:.0f}% dos passos são saltos "
            f"(limite {MAX_JUMP_RATIO*100:.0f}%). A escala oscila entre frames e um "
            f"objeto ancorado tremeria. Falta bundle adjustment global"
            if jittery else
            f"erro de reprojeção {reproj:.2f}px acima do limite {MAX_REPROJ_PX}px — "
            f"a pose não é confiável para ancorar (o objeto tremeria)"
        ),
        "bundle_adjustment": ba_note,
        "path_length": round(path, 4),
        "trajectory_span": round(span, 4),
        "jump_ratio": round(jump_ratio, 3),
        "reprojection_px": round(reproj, 3),
        "frames_solved": len(poses),
        "frames_total": len(frames),
        "points_3d": len(pts3d),
        "intrinsics": {"fx": K[0, 0], "fy": K[1, 1], "cx": K[0, 2], "cy": K[1, 2],
                       "width": w, "height": h, "estimated": focal is None},
        "poses": {
            str(f): {"R": poses[f][0].tolist(), "t": poses[f][1].ravel().tolist()}
            for f in sorted(poses)
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tracks", help="JSON de camera_track.py --out")
    ap.add_argument("--out", help="grava camera.json")
    ap.add_argument("--focal", type=float, default=None,
                    help="distância focal em px; sem isto é estimada em 0.9x a largura")
    ap.add_argument("--no-ba", action="store_true",
                    help="pula o bundle adjustment (para comparar antes/depois)")
    args = ap.parse_args()

    data = json.loads(Path(args.tracks).read_text(encoding="utf-8"))
    r = solve(data, args.focal, do_ba=not args.no_ba)

    if args.out and r.get("ok"):
        Path(args.out).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        r["out"] = args.out

    resumo = {k: v for k, v in r.items() if k != "poses"}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if not r.get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()
