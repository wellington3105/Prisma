# Opus `prisma-fluxo-edicao` — Plano (Fluxo da Clareza)

**Data:** 2026-11-03 · **Status:** ✅ CONCLUÍDO (ondas 1–5; Quality Gate PASS) ·
**Base:** `ANALISE-FLUXO-DE-EDICAO.md` (análise de `LeiteZ/fluxo-de-edicao`, MIT).

---

## Fase 1 — Brief

Trazer para o Prisma o que o `fluxo-de-edicao` tem e o Prisma não tem (ofício de
motion, HyperFrames, SFX, gate de plano, memória de gosto, entrada da Fase 1),
**sem** trocar a arquitetura do Prisma (uma skill, phase gate, preview). A dor:
inserts e SFX que hoje saem "no médio" e só se revelam fracos depois do render,
e gosto de cliente que é escolhido do zero a cada projeto.

## Fase 1.5 — Precedente (onde procurei)

- `.omc/out-of-scope/` (vault, Prisma, home): **não existe** → nenhuma recusa anterior.
- `PLANO-PRISMA.md`, `PLANO-TIMELINE.md`, `EVOLUCAO-OPUS.md`, `OPUS-VFX-3D.md`:
  nenhum item deste plano foi planejado ou recusado antes (os acertos de
  "DaVinci/sync" eram falsos positivos do verbo "resolve").
- **Já existe e será estendido, não reconstruído:**
  - o aviso "desatualizado" do preview (`preview_server.py:521`, compara
    `edit-data.json` com o vídeo) → base da F2.3;
  - os marcadores do preview são só da pessoa (`app.js:775`, `notes`) → F2.2
    acrescenta o tipo "do Claude";
  - a skill `media-use` resolve SFX/BGM com ledger (`PLANO-PRISMA.md:113`) →
    **conferir antes** da F3.1, para não duplicar.

## Fase 2 — Decisões (aguardando o Wellington)

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Escopo deste Opus | F1 + F6.1 + F2 + F3 + F4 + F5 (P1, P1.5, P2). F7 fica como backlog, só sob demanda |
| D2 | Material de teste | Cópias do `Videos/Cayenne` (já tem EDL, transcript e 2 fontes). Nunca o original |
| D3 | Quando o plano de inserts (F2.1) é obrigatório | Sempre que a Fase 2 tiver ≥1 insert/hook animado; estilo `limpa` pula |
| D4 | Perfis de cliente (F5.1) | Criar sob demanda, no primeiro projeto de cada cliente — nenhum pré-criado |
| D5 | Números do `fluxo-de-edicao` | Entram como hipótese com origem; viram regra só depois de medidos num render nosso |

---

## Fase 3 — Estruturação

**Objetivo mensurável:** cada story fecha com um teste em material real
(D2) e um critério de aceite verificado em disco, não por autoavaliação.

**Formato de cada story:** o quê · por quê · aceite · teste · depende de ·
esforço (P ≤ 2h · M ≤ 1 dia · G > 1 dia) · arquivos.

### ÉPICO F0 — Correção ✅ CONCLUÍDO (2026-11-03)

**F0.1 — `refine_edges` respeita as bordas da pessoa** ✅
`apply_preview_edits.py` (novo) marca `user_edges`; `refine_edges.py` nunca move
borda travada, só confere e reescreve o `quote`; `+palavras/−palavras` explícito.
Re-teste no Cayenne reel_01: 4/4 edições mantidas.

### ÉPICO F1 — Doutrina (P1) · sem código

**F1.1 — `references/motion-craft.md`** · M
- **O quê:** ofício de elemento e de câmera virtual: hierarquia de velocidade,
  curva por papel, cascata 2–4f, saída mais rápida que a entrada, tempo de leitura
  1–1,5s, grupo recentralizado, linha palavra a palavra, speed ramp com
  velocidades casadas (4·D/T ↔ 6,93·D/T), aproximação + deriva em camadas, três
  formas de zoom, punch assimétrico, flash no elemento sobre o apresentador,
  profundidade de campo, look aplicado uma vez só, "feedback geral = refazer".
- **Por quê:** `direction.md` decide *qual* transição; nada decide *como* o
  elemento se move.
- **Aceite:** dado um insert da Fase 2, quando o agente escreve o `edit-data`,
  então cada entrada/saída cita a regra do arquivo; o arquivo marca o que é
  hipótese (D5) e não contradiz `direction.md` (a regra 60–70% primária vence).
- **Teste:** 1 insert do Cayenne renderizado com e sem a doutrina; `contact_sheet`
  dos dois na entrada/saída; medir duração de entrada/saída em frames no render.
- **Depende de:** — · **Arquivos:** `references/motion-craft.md`, roteamento em `SKILL.md`.

**F1.2 — `references/hyperframes-traps.md`** · P
- **O quê:** as ~14 armadilhas, cada uma marcada "já no código (`arquivo:linha`)"
  ou "falta": duração (N−0,5)/fps, CSS inline, `lazy:false`, `immediateRender`,
  `transformOrigin`, `fonts.ready`, motion blur `tier=filter`, sem
  `backdrop-filter`/`drop-shadow` em texto animado, ProRes 4444 + extrair PNG,
  semente fixa, versão fixa por vídeo, margem de não determinismo, compor 1080p.
- **Aceite:** dado cada item, então há evidência no código ou um "falta" com o
  arquivo onde entraria; `export_hyperframes.py` passa a citar o arquivo.
- **Teste:** 1 cena `hf_motion_scenes` com duração de N frames → `ffprobe`
  confirma N, não N+1.
- **Depende de:** — · **Arquivos:** `references/hyperframes-traps.md`.

**F1.3 — `references/sfx-craft.md`** · P
- **O quê:** som segue o que se vê; camadas (principal/grave/apoio/doce/cauda,
  ≤3); sincronia (impacto no transiente, whoosh com pico na chegada, ±1f);
  respiro de 0,5s antes do impacto; escalada; não repetir em 20s; nível relativo à
  voz; quando usar o kit sintetizado e quando o Epidemic.
- **Aceite:** dado um `sfxCues` escrito pelo agente, então cada cue tem papel e
  alinhamento (pico|início) declarados.
- **Teste:** revisão de um `sfxCues` existente contra as regras; contar violações.
- **Depende de:** — · **Arquivos:** `references/sfx-craft.md`, `soundtrack.md` aponta.

**F1.4 — Regras de corte e revisão no SKILL.md** · P
- **O quê:** desempate de takes (nota > último completo > anterior limpo; buscar
  take perdido antes de descartar); hesitação colada × isolada; "na dúvida não
  corta e marca"; roteiro só para grafia; pendências que não somem; "feedback
  geral = refazer".
- **Aceite:** cada regra aparece uma vez, no lugar certo do SKILL.md, sem
  duplicar "Cut craft".
- **Depende de:** — · **Arquivos:** `SKILL.md`, brief do sub-editor.

### ÉPICO F6 (parte) — Rede de segurança, antes de mexer em mais helpers

**F6.1 — Fixture de regressão** · M
- **O quê:** um clipe curto congelado (≈30s, recortado de uma cópia do Cayenne)
  + saídas esperadas: EDL refinado, durações, `verify_cut` limpo, níveis.
  `helpers/regress.py` roda o pipeline da Fase 1 e compara com tolerância.
- **Por quê:** o Prisma muda helpers com frequência; F3–F4 mexem em `transcribe`,
  `refine_edges` e no inventário. "Mudança que ninguém pediu é bug."
- **Aceite:** dado o Prisma de hoje, quando `regress.py` roda, então passa; dado
  um helper alterado de propósito (ex.: `TRAIL` 0,06→0,20), então falha
  apontando o campo.
- **Teste:** os dois casos acima. · **Depende de:** — ·
  **Arquivos:** `tests/fixture/`, `helpers/regress.py`.

### ÉPICO F2 — Gate de plano na Fase 2 (P1.5)

**F2.1 — Plano de inserts numerado** · M
- **O quê:** depois do gate de Estilo e antes de escrever `edit-data.json`, o
  agente propõe `i01…iNN`: tempo, formato (tela cheia/sobreposição/split),
  conceito em uma frase, palavra-gatilho com tempo, intenção da câmera.
  Storyboard (conceito, camadas, câmera, batidas, herói, vida, saída)
  obrigatório no hook. Autochecagem: "serviria para qualquer vídeo?", "estou
  repetindo a fórmula?". Aprovação por número ("i04 tira", "i02 mais curto").
  Borda de insert que coincide com corte usa o tempo do corte (`jcut_timeline`).
- **Aceite:** dado um projeto com inserts (D3), quando a Fase 2 começa, então
  nenhum `edit-data.json` é escrito antes de o plano ser aprovado; os ids
  `iNN` aparecem no `edit-data` e no preview.
- **Teste:** Cayenne reel_01: plano → aprovar com 1 corte e 1 ajuste → conferir
  que o `edit-data` reflete exatamente isso.
- **Depende de:** F1.1 · **Arquivos:** `SKILL.md` (Fase 2), `shortform.md`,
  `longform.md`, `export_hyperframes.py` (ids).

**F2.2 — Marcadores do Claude no preview** · M
- **O quê:** tipo novo de marcador (dúvida de take, hesitação mantida, nota não
  entendida, sugestão, alerta técnico, borda da pessoa que corta palavra),
  ancorado no tempo da FONTE para sobreviver a novos cortes; cor própria.
- **Aceite:** dado um EDL com 2 dúvidas, quando o preview abre, então os 2
  marcadores aparecem no ponto certo e não se confundem com os da pessoa.
- **Teste:** cortar de novo um range e ver o marcador acompanhar a fonte.
- **Depende de:** — · **Arquivos:** `state.json` (`agentMarkers`), `app.js`,
  `preview_server.py`.

**F2.3 — Alerta de desatualização estendido** · P
- **O quê:** além do vídeo × `edit-data`, avisar quando o `edl.json` é mais novo
  que `segments.json`/`edit-data.json`/`jcut_timeline` e dizer o que refazer.
- **Aceite:** dado um EDL alterado depois da Fase 2, então o aviso aparece com a
  lista do que ficou velho; refazendo, ele some.
- **Depende de:** — · **Arquivos:** `preview_server.py`, `app.js`.

### ÉPICO F3 — Som (P2)

**F3.1 — `sfx_index.py`** · M
- **O quê:** índice do kit `sfx_synth`, de `public/sfx/` e dos downloads do
  Epidemic: duração útil, **tempo até o pico**, forma (seco/crescendo), brilho.
- **Pré-requisito:** ler a `media-use`; se ela já indexa pico, reaproveitar.
- **Aceite:** dado um whoosh com pico conhecido, então o índice acerta o pico em
  ±10ms.
- **Teste:** 5 sons sintetizados com pico em tempo conhecido.
- **Depende de:** F1.3 · **Arquivos:** `helpers/sfx_index.py`.

**F3.2 — Cenas HyperFrames emitem eventos** · M
- **O quê:** `hf_motion_scenes`, `beat_edit`, `cinema_edit` gravam `events.json`
  (tempo, tipo em palavras livres, força, duração, descrição), mais as
  transições, os inserts e os `zoomCuts` do `edit-data`.
- **Aceite:** dado um render, então todo evento visível tem uma linha com id
  estável (não muda se o evento não mudou).
- **Depende de:** F1.2 · **Arquivos:** os 3 helpers.

**F3.3 — `sfx_events.py` → rascunho de `sfxCues`** · M
- **O quê:** lê eventos + índice, escolhe papel e som, alinha
  `at = evento − pico`, aplica respiro de 0,5s, escalada e não-repetição em 20s,
  nível relativo à voz; avisa evento sem principal e som repetido.
- **Aceite:** dado o Cayenne com inserts, então o rascunho tem 0 violações de
  F1.3 e o `deliver_mix` roda com ele sem ajuste manual.
- **Teste:** `deliver_mix --stems` + medir alinhamento de 3 cues no stem de SFX.
- **Depende de:** F1.3, F3.1, F3.2 · **Arquivos:** `helpers/sfx_events.py`.

### ÉPICO F4 — Fase 1: entrada mais confiável (P2)

**F4.1 — Notas faladas** · P
- **O quê:** "nota de edição … fim da nota" (frases combináveis) achadas com
  tolerância no transcript; interpretação + etapa; o trecho sai do EDL; abertura
  sem fechamento termina na próxima pausa ≥1s com confiança baixa.
- **Aceite:** dado um clipe com 1 nota, então ela aparece no `project.md` e o
  trecho não está no `cut.mp4`.
- **Teste:** gravar 30s com uma nota (ou inserir num clipe de teste).
- **Depende de:** F6.1 · **Arquivos:** `pack_transcripts.py` ou helper novo, `SKILL.md`.

**F4.2 — Glossário na transcrição** · P
- **O quê:** `transcribe.py --glossary arquivo.txt` (marcas, modelos, nomes) com
  a armadilha tratada: trechos com energia e sem palavra são retranscritos sem
  contexto.
- **Aceite:** dado "Cayenne", "K&N", "PPF" no glossário, então a grafia sai certa
  e nenhuma frase nova aparece no texto (diff contra a transcrição sem glossário).
- **Depende de:** F6.1 · **Arquivos:** `transcribe.py`.

**F4.3 — Detector de hesitação** · M
- **O quê:** voz sem palavra transcrita, curta, entre silêncios → candidata a
  corte (isolada e longa) ou marcador (colada).
- **Aceite:** dado um clipe com 3 "ééé" conhecidos, então ≥2 detectados e 0 falso
  positivo em fala normal.
- **Depende de:** F6.1, F2.2 · **Arquivos:** helper novo ou `speech_regions.py`.

**F4.4 — Inventário: VFR, data de gravação, GPU** · P
- **O quê:** alerta de VFR (`avg_frame_rate ≠ r_frame_rate`); ordenar fontes por
  `creation_time` (senão nome); checar `torch.cuda` antes de transcrever e avisar
  se cair para CPU.
- **Aceite:** dado uma gravação de tela VFR, então o alerta aparece; dado a RTX
  3060, então o log diz "cuda".
- **Depende de:** — · **Arquivos:** `quality_probe.py`/`transcribe.py`.

**F4.5 — `sync_sources.py` (áudio externo, 2ª câmera, tela)** · G
- **O quê:** correlação cruzada com o áudio da câmera como referência; offset +
  confiança; validação por uma palavra marcante; confiança baixa → pergunta.
- **Aceite:** dado um áudio deslocado artificialmente em 1,234s, então o offset
  medido erra < 1 frame.
- **Depende de:** F6.1 · **Arquivos:** `helpers/sync_sources.py`, `render.py` (fonte de áudio).

### ÉPICO F5 — Memória de gosto (P2)

**F5.1 — Perfil por cliente** · M
- **O quê:** `perfis/<cliente>/` (estilo do gate, grade, trilha, SFX, câmera),
  cada regra com origem; o gate de Estilo abre com os padrões do perfil.
- **Aceite:** dado o 2º projeto de um cliente, então o gate abre com as escolhas
  do 1º e diz de onde vieram.
- **Depende de:** F5.2 · **Arquivos:** `perfis/`, `app.js` (Estilo), `SKILL.md`.

**F5.2 — Caderno de aprendizados** · P
- **O quê:** `edit/aprendizados.md` (`[ ]` / `[x] → onde entrou` / `[-]`),
  anotado durante a revisão; "aplicar aprendizados" separa gosto → perfil e
  ofício → skill, só com aprovação; integra com `*retrospective`.
- **Aceite:** dado 3 correções numa revisão, então 3 linhas no caderno; aplicar
  propõe destino por linha e grava só as aprovadas.
- **Depende de:** — · **Arquivos:** `SKILL.md`, template do caderno.

### ÉPICO F6 (resto) — Entregas

**F6.2 — Versionamento** · P
- **O quê:** `final_vNN.mp4` + `final.mp4` apontando para a última; nunca
  sobrescrever entrega; `state.json` lista as versões.
- **Aceite:** dado 2 renders, então existem `final_v01` e `final_v02` e o preview
  toca a última.
- **Depende de:** — · **Arquivos:** `render_phase2.py`, `deliver_mix.py`, `state.json`.

### ÉPICO F7 — Backlog P3 (só sob demanda)

| Id | Story | Depende de | Esforço |
|---|---|---|---|
| F7.1 | Rota DaVinci Resolve via MCP (timeline, marcadores, render; teste curto primeiro) | — | G |
| F7.2 | Câmera casada com inserts (`exitDir`, aceleração antes, chegada na direção da saída, rosto no terço oposto) | F1.1, F2.1 | M |
| F7.3 | `reference_analyzer.py` (cenas + fluxo óptico + afim RANSAC → curva GSAP) | F5.1 | G |
| F7.4 | Assets SVG (Iconify, logos oficiais, print de site, folha numerada, créditos) | — | M |
| F7.5 | `face_track.py` Haar → YuNet, medido contra o atual | F6.1 | M |
| F7.6 | Render por trecho (longform) | F2.1 | M |
| F7.7 | XML FCP7 para Premiere sem MCP | F7.1 | G |

---

## Sequência e dependências

```
F1.1 ─┬─────────────► F2.1 ──► (F7.2, F7.6)
F1.2 ─┼──► F3.2 ─┐
F1.3 ─┼──► F3.1 ─┴─► F3.3
F1.4  │
F6.1 ─┴─► F4.1 · F4.2 · F4.3(+F2.2) · F4.5 · F7.5
F2.2 · F2.3 · F4.4 · F5.2 ──► F5.1 · F6.2      (independentes)
```

**Ondas:**
1. **Doutrina + rede:** F1.1, F1.2, F1.3, F1.4, F6.1
2. **Gate e visibilidade:** F2.1, F2.2, F2.3, F4.4
3. **Entrada da Fase 1:** F4.1, F4.2, F4.3, F4.5
4. **Som:** F3.1 → F3.2 → F3.3
5. **Memória e entrega:** F5.2 → F5.1, F6.2

**Ensemble:** @Architect (Poka) para F2.1/F3.3/F4.5 (decisão de formato e
contrato) · executor para o resto · @QA (Sigma) no fechamento de cada onda, com
o fixture da F6.1 como gate.

**Critério de done do Opus:** todas as stories aprovadas em D1 com aceite
verificado em disco; `regress.py` passando; relatório de cada onda com o que foi
medido; aprendizados registrados (`*retrospective`).

## Fase 4 — Aprovação

✅ Aprovado em 2026-11-03 ("Aprovar e iniciar"): D1–D5 como recomendado, ondas
na ordem proposta.

---

## Execução — Onda 1 ✅ (2026-11-03)

| Story | Entrega | Aceite / evidência |
|---|---|---|
| F1.1 ✅ | `references/motion-craft.md` + roteamento no SKILL.md | Conflitos com `direction.md` resolvidos por escrito (saída de cena × de elemento; âncora × centro; regra 3; spring × bezier). 13 equivalências GSAP→bezier **medidas** (≤1,2%; `power4.inOut` 3,2%). Casamento de velocidade 4·D/T ↔ 6,93·D/T derivado. **O render com/sem a doutrina passou para a F2.1** (não há plano de inserts real antes dela) |
| F1.2 ✅ | `references/hyperframes-traps.md` + roteamento + nota no `export_hyperframes.py` | Cada armadilha com status no código. **Medido no 0.8.93:** duração→frames arredonda para cima com tolerância (8,001→8; 8,016→9) — os arredondamentos de 4 e 6 casas do Prisma são seguros; `transformOrigin` dentro do `fromTo` **não** desloca no render (borda fixa em x=100 nas duas variantes) |
| F1.3 ✅ | `references/sfx-craft.md` + ponteiros em `soundtrack.md`/`shortform.md` | Auditoria de 21 cues reais (Deocar, PPF X6): 4 picos não descontados, 5 repetições (4 são assinatura legítima), 0 notas de papel. Exceção "assinatura sonora" acrescentada |
| F1.4 ✅ | SKILL.md: escolha de take, hesitação, "na dúvida marca", roteiro só grafia, reordenar só sugerindo, pendências persistentes, "feedback geral = refazer" + brief do sub-editor | Uma ocorrência de cada regra, sem duplicar "Cut craft" |
| F6.1 ✅ | `helpers/regress.py` + `tests/fixture/` (clipe 35 s, EDL de 9 ranges, `expected.json`) | **Passa:** 11/11, 0 ms de desvio entre rodadas. **Falha de propósito:** `TRAIL` 0,06→0,20 → 5/10 FAIL, enquanto o `verify_cut` sozinho dizia `flags: 0` |

### Achados da Onda 1 que viram trabalho

| Id | Achado | Onde entra |
|---|---|---|
| **F3.0 (novo, defeito)** | Todo `transitions[].sfx` começa no frame do corte (`CustomGraphics.tsx:249` e `deliver_mix.py:134`), mas o golpe do `whip_hit.wav` está em 0,29 s → **o som do whip-pan bate ~9 frames depois da imagem**. Visto em 4 transições do PPF X6 | Onda 4, antes da F3.1: descontar o tempo até o pico do arquivo; `regress.py` + 1 render de conferência |
| **F1.2b (novo)** | `beat_edit.py:67` grava `hyperframes@latest`: um projeto reaberto depois pode renderizar diferente do aprovado | Onda 2: gravar a versão instalada no projeto e no `state.json` |
| **D6 (decisão nova, do Wellington)** | `direction.md` mapeia as curvas um nível abaixo (`smooth` = `power2.inOut` usa a bezier da Quad: 7,4% de erro, contra 1,0% com a Cubic; `luxe` 2,6% → 0,5%; `snappy` 4,8% → 3,2%). Corrigir muda o visual de vídeos já aprovados | Corrigir os números, ou manter e renomear a origem GSAP para a curva real |
| **F4.4 (reforço)** | Transcrever 35 s levou 49–86 s; o SKILL.md promete ~tempo real com GPU → indício de CPU, com uma RTX 3060 na máquina | Onda 2: a checagem de GPU da F4.4 sobe de prioridade |

---

## Execução — Onda 2 (em andamento, 2026-11-03)

| Story | Entrega | Aceite / evidência |
|---|---|---|
| F4.4 ✅ (GPU) | `transcribe.py` avisa `⚠ GPU … SEM CUDA` em vez de cair calado na CPU; `install.md` ganhou a seção GPU | Causa medida: a placa é uma **RTX 5070** (o vault diz 3060), o `.venv` tem `torch 2.8.0+cpu`, e o faster-whisper em CUDA falha por falta de `cublas64_12.dll`. **Usar a GPU exige instalar o torch CUDA 12.8 — decisão D7, feita depois (ver "Pendências D7 · D6 · D9")** |
| F4.4 ✅ (inventário) | `helpers/inventory.py` | VFR sintético acusado (37% de variação), CFR limpo; 30 × 29,97 acusa "FPS MISTO", 29,993 × 29,999 (celular) não; fontes do Cayenne em ordem de gravação |
| F1.2b ✅ | `helpers/hf_version.py` + `beat_edit`, `cinema_edit`, `export_hyperframes` gravam a versão; `preview_server` abre o Studio com a versão do projeto via `npx` quando difere | Testes: grava 0.8.93, preserva a de projeto existente, avisa na diferença. Pyflakes: 0 nomes indefinidos (pegou e corrigiu um `sys` não importado antes de ir para produção) |
| F2.3 ✅ | `helpers/staleness.py` + `/api/state` + aviso ⟳ do preview | Sintético: em dia → nada; edl mudado → 2 avisos com correção; cadeia refeita → nada. **UI:** aviso aparece com tooltip e some sozinho após refazer, 0 erros no console. **Projetos reais:** PPF X6 (EDITOR exportado antes do corte) e Deocar (edl mudou depois do cut) — a conferir pelo Wellington. A 1ª versão por data acusava o XC60 à toa → trocada por comparação de conteúdo |
| F2.2 ✅ | `helpers/agent_markers.py` + `/api/state` + **faixa "Claude · N marcações" sob as abas** (D8 = A, decidido pelo Wellington), em tempo do CORTE; azul, alerta/borda amarelo, fora do corte esmaecido; também desenhada na trilha Marcações antiga. `refine_edges` grava sozinho o marcador de borda da pessoa que cai em fala | **Medido:** faixa visível (34 px, acima do EDITOR, captura de tela); 3 marcadores nos tempos exatos (0:12.53 fora do corte · 0:16.08 · 0:22.81); **re-corte renderizado de verdade** (take 2 removido) → 0:14.42 e 0:21.14, idênticos ao calculado à parte pelo `jcut_timeline` novo; o refine criou o marcador na fonte 112,95 s. Console: 0 erro novo com o servidor no ar (um 502 do proxy do Studio na carga, preexistente: a pasta de teste não tem EDITOR) |
| F2.1 ✅ | `helpers/inserts_plan.py` (check/show/approve/strike/set/apply) + gate no SKILL.md, `shortform.md`, `longform.md` + ids do plano nos clipes do EDITOR (`split-i03`, `insert-i01`) | **Teste no Cayenne reel_01 (cópia):** `check` pegou os 2 problemas plantados (storyboard faltando no hook; borda a 150 ms do corte) **e um real** (card do hook a 200 ms do corte); `apply` recusou o plano não aprovado e recusou apagar 5 splits fora do plano sem `--replace`; resposta por número ("i05 tira, i04 até 38 s") → `edit-data` **idêntico ao plano** em 9/9 checagens, nenhuma outra chave alterada; export → EDITOR com `insert-i01`, `split-i02/03/04/06`. **Defeito achado e corrigido:** o export pulava insert sem asset **em silêncio** (o card sumiu do EDITOR) → agora avisa, e o `check` bloqueia "ASSET FALTANDO" |

### F1.1 — medição adiada (feita na F2.1)

No `final.mp4` entregue do Cayenne reel_01, por diferença de frames na faixa da
arte: os splits **entram e saem em corte seco (1 frame)** — a troca de layout é
corte por design (com flash). As duas "entradas de 0,5 s" medidas terminam
exatamente no início do split → movimento do apresentador na mesma região, não
animação: inconclusivo, não vira regra. Conclusão registrada no
`motion-craft.md`: a entrada de ~0,5 s é para elementos DENTRO da cena (card,
texto), não para a troca de layout do split.

**Onda 2 ✅ concluída** (F4.4, F1.2b, F2.3, F2.2, F2.1 + F0.2). Regressão 12/12.

---

## Execução — Onda 3 ✅ (2026-11-03) — entrada da Fase 1

Material de teste: clipes pt-BR sintetizados com a voz Microsoft Maria (local,
sem custo) quando o caso precisava de áudio conhecido; recortes de cópias do
Cayenne para fala real.

| Story | Entrega | Aceite / evidência |
|---|---|---|
| F4.1 ✅ | `helpers/spoken_notes.py` (+ `--strip`) + passo 2 da Fase 1 no SKILL.md | 2/2 notas achadas com texto e etapa certos ("usa o segundo take" → cortes; "coloca o logo" → inserts); a sem fechamento terminou na pausa, confiança baixa + marcador. **Fim a fim:** strip → refine → render → re-transcrição do corte = só as falas, nenhuma palavra das notas. **Ajuste medido:** cortar a 50 ms da palavra deixava a borda COLADA (o refine a empurrou 20 ms para dentro de "Nota") → o corte vai para o meio da pausa; depois disso o refine dá "ok" nas três emendas |
| F4.2 ✅ | `transcribe.py --glossary` (lista neutra em `initial_prompt`; tag `/glossary` no transcript) | Cayenne 14 s real: **"K&N" → "Cayenne" 3/3, 0 palavra inventada**. Mexeu em 2 palavras pequenas: um "de" tirado com razão (a janela isolada confirma que não é dito) e um "já" real perdido na borda final do clipe. Regra: usar quando o vídeo cita marca/nome, e continuar confiando nas janelas isoladas do `refine_edges` (que rodam sem o glossário — "conteúdo difere" em termo do glossário é esperado) |
| F4.3 ✅ | `helpers/hesitations.py` (+ `--markers`) | Pelo áudio: voz vozeada sem palavra, ou escondida DENTRO de palavra esticada, + muletas transcritas. **3/3** num clipe com 3 hesitações — um "éééé" de 2 s que o WhisperX engoliu dentro de "Cayenne." esticada até 5,74 s. **0 falso positivo em 49 s de fala real.** Dois defeitos achados e corrigidos no caminho: silêncio digital (−180 dB) jogava o piso para baixo e juntava frases; e "dono por maior sobreposição" dava o "ééé" para a palavra esticada (agora: dono pelo início da palavra). "é"/"a"/"um" só contam alongados ou isolados (o "é," do Cayenne era o "né" da fala) |
| F4.5 ✅ | `helpers/sync_sources.py` + `render.py` lê `audio_sources` no EDL (J-cut) | Atraso de 1,234 s com outro "microfone" e ruído: **−1,2339 s (erro 0,1 ms)**; tela parcial: +30,0000 s; gravador a 200 ppm: deriva acusada (+170 ppm, escorrega 15 ms). Corte renderizado com a lapela a **0,4 ms** do corte com o som da câmera. Alarme falso de deriva (corte de 23 s, <1 ms) eliminado trocando o critério de ppm para escorregão ≥ 10 ms |

Regressão 12/12 depois da onda.

---

## Execução — Onda 4 ✅ (2026-11-03) — som

| Story | Entrega | Aceite / evidência |
|---|---|---|
| F3.0 ✅ | `helpers/sfx_peak.py`; `deliver_mix.py` alinha `transitions[].sfx` pelo pico (padrão) e aceita `"align"` nos `sfxCues`; `cinema_edit.py` ganhou `align: "peak"` | Cópia do PPF X6, stem de SFX: os 4 whip-pans de **+9,4 frames → +2 ms** do frame do corte. Cues antigos sem `align` não mudam |
| F3.1 ✅ | `helpers/sfx_index.py` → `<prisma>/sfx_index.json` (37 sons de 3 bibliotecas, incluindo a `media-use`) | Picos conhecidos: ±5 ms em 4/5 (riser −20 ms no topo plano — risers alinham pelo fim). **Duas métricas minhas corrigidas pelo teste:** média móvel piorava (revertida); "fração de energia no celular" dava 0% para um impacto audível → trocada por "queda do pico" (impact.wav −12 dB, audível, como o shortform.md já dizia) |
| F3.2+F3.3 ✅ | `helpers/sfx_events.py` (eventos com id estável → rascunho de `sfxCues` pelas regras do sfx-craft) | Cayenne (cópia): **0 violações**; mixado com `deliver_mix --stems`: os cues medíveis caíram a −0,7…+0,8 f do evento. Achado e corrigido: um whoosh na cauda do impacto do hook (dois principais encavalados) → regra "dentro da cauda do anterior" |

**Achados da Onda 4 para decisão:**
- `impact-bass-1.mp3`, o som do flash no `beat_edit`, é um ronco contínuo que
  **cai 21 dB no celular** — num Reel ele quase some. Trocar é decisão de design (D9). *(Corrigido depois: a queda é de caráter, não de audibilidade — ver "Pendências D7 · D6 · D9".)*
- O `beat_edit` usa atrasos de SFX fixos à mão; o índice confirmou o do
  `whoosh-short` (0,16 s). Ficam como estão.

Regressão 12/12.

---

## Execução — Onda 5 ✅ (2026-11-03) — memória e entrega

| Story | Entrega | Aceite / evidência |
|---|---|---|
| F5.2 ✅ | `helpers/learnings.py` + doutrina "anotar não é mudar" no SKILL.md | 3 correções → 3 linhas; a repetida não duplica; a duvidosa entra "(talvez só deste vídeo)"; só as aprovadas são marcadas com destino (`[x] → …`), a só-deste-vídeo vira `[-]`, nada é apagado |
| F5.1 ✅ | `helpers/client_profile.py` (learn/seed/rule/show/list) + passo do gate no SKILL.md | Perfil aprendido do Cayenne reel_01 (os 4 reels tinham o MESMO estilo, escolhido 4 vezes); projeto novo semeado → **a aba Estilo abriu sozinha com split · misto · scatter · #ff5200 · os 10 elementos idênticos** e a origem no topo (captura). Recusa sobrescrever estilo já escolhido. **Defeito antigo achado e corrigido:** a aba trocava `scatter` por `karaoke` ao reabrir qualquer projeto vertical (o formato era tido como paisagem antes de o vídeo carregar) → `S.aspectKnown`; em paisagem o encaixe legítimo continua (`scatter` → `srt`) |
| F6.2 ✅ | `helpers/deliveries.py` + `render_phase2.py` e `deliver_mix.py` gravam `final_vNN.mp4` | 2 entregas → v02, v03; o `final.mp4` legado preservado como v01 (diferente da v02 por hash); `final.mp4` = hardlink da v03; v02 ≠ v03 no disco (o `-y` do ffmpeg não alcança versões antigas); `state.json.deliveries` lista as 3 |

**Defeito MEU achado pela regressão e corrigido:** o primeiro nome do helper de
perfil foi `profile.py` — módulo da stdlib. Como os helpers rodam com `helpers/`
no início do sys.path, ele sombreou o `cProfile` e quebrou o import do
`transformers`: a transcrição inteira parava. Renomeado para
`client_profile.py`, e o `regress.py` ganhou um Poka-Yoke que recusa rodar se
algum helper tiver nome de módulo da stdlib (testado: barra um `profile.py`).

---

## Quality Gate do Opus

- Gates padrão do Maestro (`config/gates.json`, só npm) no Prisma: **exit 1** —
  desencontro de configuração (o Prisma é Python, sem `package.json`), não defeito.
- Gates do Prisma criados em `.omc/gates.json` (lint = nome indefinido via
  `helpers/lint_undefined.py` · ui = `node --check` · test = `regress.py`):
  **✅ PASS, exit 0**. O lint foi provado reprovando um nome indefinido plantado.

## Critério de done do Opus — ✅ atingido

Todas as stories de D1 (F1–F6) com aceite verificado em disco; `regress.py`
12/12; relatório de cada onda neste arquivo. F7 segue como backlog sob demanda.

## Retrospectiva (Kaizen)

- **O que mais rendeu não estava no repositório analisado:** testar as ideias
  dele contra material real revelou defeitos antigos do Prisma — sincronia de
  imagem e voz (até 300 ms), whip-pan 9 frames atrasado, legenda `scatter` que
  voltava a `karaoke`, insert que sumia do EDITOR em silêncio, conflito
  refine_edges × bordas da pessoa. Testar doutrina em produção paga mais que
  ler doutrina.
- **D5 se pagou:** três números do repositório não se confirmaram como regra
  (duração no HyperFrames, `transformOrigin`, entrada de 0,5 s no split).
- **Toda métrica nova precisou de um teste negativo:** a de celular (fração de
  energia) e a de deriva (ppm) davam alarme falso; a suavização do pico piorava.
- **Os testes que mais pegaram erro meu:** `pyflakes` (3 nomes não importados) e
  a regressão (o `profile.py`). Ficaram como gates.
- **Decidido (Wellington, 03/11):** as entregas antigas com atraso de sincronia
  (Cayenne reel_01–04, Deocar) **não serão refeitas** — as correções valem a
  partir dos próximos vídeos. Nada nesses projetos foi alterado.

## Pendências D7 · D6 · D9 — ✅ resolvidas (2026-11-03, "prossiga")

| | Feito | Medido |
|---|---|---|
| **D7** torch CUDA | `torch/torchaudio/torchvision 2.8.0+cu128` no `.venv` (comando em `install.md`). `transcribe.py`: aviso ⚠ distingue "torch sem CUDA" de "GPU invisível ao processo" | RTX 5070 (sm_120) ok. Fixture 35 s, `large-v3`: ASR 25,9 → **3,1 s** (8,4×), alinhamento 10,5 → 5,7 s, `transcribe.py` 52 → **23 s**. `uv sync` volta ao CPU |
| **D7 achado** | `refine_edges.py` **fica em CPU/int8**: no GPU a regressão falhou (range 01: fim em 14,94 cortava 0,6 s de voz). float16 = float32 = int8 CUDA; só o int8 da CPU difere | Causa na regra, não na GPU → **D10** |
| **D6** curvas | `direction.md`: `snappy` (0.83,0,0.17,1), `smooth` (0.65,0,0.35,1), `dramatic` (0.76,0,0.24,1) = `power3.inOut`, `luxe` (0.45,0,0.55,1) + coluna de erro; nota do `motion-craft.md` | Erro máx.: 4,8→3,2 · 7,4→1,0 · **16,9→2,2** · 2,6→0,5 %. Nenhum código tinha as curvas (só docs) |
| **D9** flash | `beat_edit`: flash = `impact.wav` do kit, alinhado pelo **ataque**, `cap` 1,1 s | Premissa corrigida: o `impact-bass-1` não "some no celular" (sobra −20 dBFS, nível de `chime`); é um **drone de sub de 2 s** em −1 dB. Mesmo volume → mesmo ataque no celular (−13,0 vs −13,4 dB). Mix: golpe em 2,000 s no flash de 2,000 s |
| **D9 achados** | `sfx_index`: campo `phone_peak_dbfs`, rótulo "quase some" → "só o ataque" (queda = caráter, não audibilidade); **golpe com sub alinha pelo ataque** quando o pico na banda do celular está a ≤ 30 ms do início | Por `peak` o `impact.wav` soava **50 ms antes** do evento (o `sfx_events` o usa no hook). Mudaram só `impact.wav`, `click`, `click-soft` → `start` |

Gate: `lint` ✅ `ui` ✅ `test` ✅ (regressão 12/12, 0 ms de desvio nas bordas).

### D10 (nova) — borda final numa micro-pausa dentro de vocalização

`refine_edges.quiet_point` aceita o primeiro trecho de 40 ms abaixo do limiar
depois da última palavra. Se a fala continua sem palavra reconhecida (um "hein"
esticado, riso), esse trecho é uma pausa ENTRE sílabas e o corte decapita voz —
na regressão, com a transcrição de GPU, 0,6 s (fala forte de volta em 14,95).
O int8 da CPU escapou por sorte de alinhamento. Correção proposta: depois do
ponto de silêncio, exigir que a voz não volte em ~150–250 ms sem palavra que a
explique; senão, manter a borda antiga e marcar. **Medir em projetos reais
antes de virar regra (D5).** Resolvida, o `refine_edges` volta à GPU (hoje é o
passo lento: ~110 s no fixture).

### Defeito grave encontrado na F2.3

**F0.2 — o `jcut_timeline` do `render.py` diverge do corte real, e a imagem
atrasa em relação à voz.** Cada segmento de vídeo extraído às vezes sai com **1
frame a mais** que o planejado (regressão: takes 4 e 7, de 8); os takes seguintes
começam 1 frame depois do que o `jcut_timeline` diz, e o erro acumula. O áudio é
posicionado pelo plano, então a **imagem também atrasa em relação à fala**.

| Medição | Resultado |
|---|---|
| Cortes reais (`scdet`) × `jcut_timeline`, render de hoje | 0, 0, 0, +1, +1, +1, +2 frames |
| Cortes reais × `segments.json` (contagem de frames) | bate exatamente (Cayenne frames 1628 e 2324) |
| Sincronia áudio × imagem, render de hoje | 0 / +1 / +1 frame (takes 2, 5, 8) |
| Sincronia áudio × imagem, Cayenne reel_01 | **+2 f (take 5), +6 f (13), +9 f = 300 ms (27)**; take 20 inconclusivo (limite da busca) |

Mitigado já (sem mudar render): SKILL.md avisa que o `jcut_timeline` é o
*plano*, não a verdade, e manda usar o `segments.json` medido; `motion-craft.md`
idem; a F2.3 compara com a contagem real de frames.
**✅ F0.2 corrigida (aprovada e feita em 2026-11-03).** `render.py` extrai cada
segmento de vídeo com `-frames:v N` exato (e `-t` com meio frame de folga),
conta os frames depois (Jidoka: avisa se divergir) e grava `video_frames` no
`jcut_timeline`. Medido:

| | Antes | Depois |
|---|---|---|
| Fixture: takes fora do plano | 4 e 7 | nenhum |
| Fixture: cortes reais × `jcut_timeline` | 0,0,0,+1,+1,+1,+2 | 0 em todas |
| Fixture: sincronia (5 instantes) take 5 / 8 | +1 / +1 | 0 / −1 (resíduo de fase, não acumula) |
| Cayenne reel_01 (cópia, 27 takes 4K): cortes visíveis exatos | — | **22/22** |
| Cayenne reel_01: sincronia take 5 / 13 / 27 | +2 / +7 / **+9 f (300 ms)** | **0 / 0 / 0** |

`regress.py` ganhou a checagem absoluta "frames = plano" (desligando a correção
de propósito, ela acusa exatamente os takes 4 e 7) e foi rebaselinado: 12/12.

**Entregas antigas com o atraso** (imagem atrasada no fim do corte): Cayenne
reel_01 +9 f, reel_02 +7 f, reel_04 +4 f, reel_03 +3 f; Deocar +8 f; Volvo XC60
≤1 f; PPF X6 0. Range Rover Sport (não entregue) mede −17 f, outro mecanismo
não verificado — medir antes de entregar. Refazer é decisão do Wellington.
