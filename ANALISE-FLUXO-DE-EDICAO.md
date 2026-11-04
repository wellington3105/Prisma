# Análise — `LeiteZ/fluxo-de-edicao` × Prisma

**Data:** 2026-11-03 · **Repo analisado:** https://github.com/LeiteZ/fluxo-de-edicao
(commit `7339da3`, 2026-11-02, "Primeira versão", MIT, Lucas Leite) ·
**Prisma de referência:** 63 helpers, 14 referências, estado do disco em 2026-11-03.

Método: os 22 arquivos do repo foram lidos na íntegra (SKILL.md, README, 12 guias,
6 modelos). Cada ideia foi procurada no Prisma por termo (SKILL.md, `references/`,
`helpers/*.py`) e, quando houve resultado, conferida no trecho. "Ausente" significa
zero ocorrências nessa busca; ver a evidência por linha na matriz.

---

## 1. Veredito

O repo **não é uma ferramenta de edição**: é uma *meta-skill* que entrevista a
pessoa e **escreve** skills de 8 etapas para ela. **Não tem nenhum script**: a
doutrina é "os scripts nascem na primeira vez que a etapa roda". Portanto nada
dali se copia como código; o que se aproveita é **doutrina de ofício**, e parte
dela é exatamente o que falta ao Prisma.

- **Onde o Prisma já é superior (não importar):** corte (J-cut medido,
  `refine_edges.py`, `voice_levels.py`, `--window`), transcrição, cor (LOG,
  multi-take), legendas, mix (`music_carve`, `deliver_mix`), compositing,
  beat-sync, preview com timeline e o gate de Estilo. O guia de cortes do repo é
  um subconjunto do que o Prisma já mede.
- **Onde o repo agrega de verdade (6 frentes):**
  1. **ofício de motion no nível do elemento** (velocidades, curva por papel,
     cascata, tempo de leitura, câmera virtual em camadas);
  2. **armadilhas do HyperFrames**, que o Prisma usa no EDITOR e em
     `beat_edit`/`cinema_edit`/`hf_motion_scenes`;
  2b. **um gate de plano na Fase 2** (inserts numerados e storyboard do hook,
     aprovados antes do render) e **marcadores do Claude** na timeline;
  3. **doutrina de SFX** (camadas, sincronia pelo pico, escalada) + índice da
     biblioteca com *tempo até o pico*;
  4. **câmera casada com os inserts** (direção de entrada e saída);
  5. **memória de gosto entre projetos** (perfil por cliente + caderno de
     aprendizados);
  6. **lacunas de preparação e entrega:** notas faladas na gravação,
     sincronia de áudio externo, detecção de VFR, entrega em NLE com volta
     (incluindo DaVinci, que tem MCP instalado aqui e zero menções no Prisma).

A segunda varredura (§2.5) achou mais 22 itens, entre eles **um conflito
interno do Prisma** que o repo ajudou a enxergar: `refine_edges.py` "em todo
EDL" × "a intenção da pessoa vence" nas bordas editadas no preview.

**Ressalva (Jidoka):** os números do repo ("medido em referências
profissionais") não vêm com dado nem método reproduzível. Entram no Prisma como
**hipóteses com origem**, e cada um vira regra só depois de medido num render
nosso, que é o padrão que o Prisma já segue.

---

## 2. Matriz item a item

Legenda: 🟢 agrega (ausente no Prisma) · 🟡 parcial (existe, o repo completa) ·
⚪ redundante (Prisma igual ou melhor).

### 2.1 Motion e HyperFrames

| Ideia do repo | Prisma hoje (evidência) | Status | Destino proposto |
|---|---|---|---|
| Hierarquia de velocidade: entrada ~15f, saída ~8f (mais rápida), texto 6–12f/palavra, câmera 1,5–3,5s | `direction.md` cobre **transição entre cenas** (energia → preset), não entrada/saída de elemento | 🟢 | `references/motion-craft.md` |
| Curva por papel (entrada `expo.out`, saída `power3.in`, carrossel `power4.inOut`, fundo `power1.inOut`…) | presets de transição em `direction.md`; nada por papel de elemento | 🟢 | idem |
| Cascata 2–4f entre irmãos; próximo movimento começa antes do anterior assentar | ausente | 🟢 | idem |
| **Tempo de leitura:** letreiro segura 1–1,5s após a última palavra | ausente (0 ocorrências) | 🟢 | idem + checagem em `edit-data` |
| Grupo que chega em sequência fica sempre recentralizado; linha palavra a palavra recentraliza a cada palavra | ausente | 🟢 | idem (vale para hook/headline e cards) |
| **Speed ramp com velocidades casadas no corte:** v_final(`power4.in`) = 4·D/T; v_inicial(`expo.out`) ≈ 6,93·D/T; percurso ~700/560 px em 1080p | ausente (0 ocorrências) | 🟢 | idem; útil a `beat_edit`/`speed_ramp` |
| Câmera virtual: aproximação (ease-out) e deriva (linear) em **contêineres aninhados**, senão o zoom "engasga" | "deriva" aparece em `direction.md`/`camera_solve.py`, sem a regra das camadas | 🟡 | idem |
| Punch assimétrico, pico em ~30% | ausente | 🟢 | idem |
| Flash em sobreposição fica **no elemento**; flash de quadro inteiro sobre o apresentador parece bug | `beat_edit` tem flash de quadro inteiro (correto para montagem) | 🟡 | regra condicional em `motion-craft.md` |
| Texto ≥28 px em 1080p, área segura 80% | safe area citada em helpers HF/inventário | ⚪/🟡 | só consolidar |
| HF: `fromTo` + `lazy:false`; `immediateRender:false` em fromTo visível; `tl.set(transformOrigin)`; `fonts.ready` antes de medir | **no código** de `beat_edit`/`cinema_edit`/`hf_motion_scenes`; a skill oficial `hyperframes` tem **0** ocorrências de `lazy`/`immediateRender`/`transformOrigin` | 🟡 | `references/hyperframes-traps.md` (doutrina do que hoje só existe no código) |
| HF: duração da raiz = (N − 0,5)/fps (o render arredonda para cima → +1 frame) | ausente (0) | 🟢 | idem + `export_hyperframes.py` |
| HF: CSS embutido, nunca `<link>` (mudou o desenho das letras) | ausente como regra | 🟢 | idem |
| HF: texto com gradiente corta a última letra (padding/margin negativos) | tratado em `hf_motion_scenes.py` + `shortform.md` | ⚪ | — |
| HF: motion blur `tier=filter`; sem `backdrop-filter` em card com texto animado; sem `drop-shadow` em gradiente | ausente nos helpers HF | 🟢 | idem |
| HF: sobreposição em ProRes 4444; extrair PNG do MOV antes de compor (`-ss` direto saiu vazio) | ProRes citado no Prisma em outros contextos | 🟡 | idem |
| HF: versão fixa por vídeo; render não determinístico (~1/255) como margem de regressão | ausente | 🟢 | idem |
| "Peças-base": elemento que ficou bom vira CSS+JS reaproveitável | `hf_motion_scenes.py` já é isso (glass-prism) | ⚪ | — |
| Medir a curva renderizada contra a pretendida | Prisma mede tudo, menos curva de motion | 🟢 | `motion-craft.md` §verificação |

### 2.2 Câmera

| Ideia do repo | Prisma hoje | Status | Destino |
|---|---|---|---|
| Base: plano alterna a cada corte; aproximação lenta numa camada própria | `zoomCuts` (~1.10–1.22, ciclo) + `zoomAuto` (+0.04/seg.) | ⚪ | — |
| O plano do corte é escolhido por onde a câmera **de fato** terminou; aviso se a mudança for <5% | ciclo fixo | 🟡 | regra no template de câmera |
| **Câmera casada com o insert:** acelera para dentro antes (+7–18%, `power4.in`, 0,2s); depois chega na **direção da saída** e freia (`expo.out`, 0,4–0,6s) | ausente | 🟢 | `motion-craft.md` + campo `exitDir` nos inserts |
| Sobreposição lateral: rosto vai ao terço oposto (~140%) e volta | split/behind existem; deslocamento do rosto, não | 🟢 | idem |
| Olhos a ~35% da altura no plano fechado | `face_track.py` fixa a linha dos olhos (valor próprio) | ⚪ | conferir o valor |
| Não inverter a direção no corte; todo movimento parte de onde a câmera está | ausente como regra | 🟢 | `motion-craft.md` |
| Detector YuNet | `face_track.py` usa **Haar** (mais antigo, mais falso positivo de perfil) | 🟡 | avaliar YuNet como upgrade medido |
| Sob tela cheia, não gastar câmera nem som | ausente | 🟢 | regra |

### 2.3 Som (SFX)

| Ideia do repo | Prisma hoje | Status | Destino |
|---|---|---|---|
| **O som segue o que se vê:** jump cut invisível = sem som; sob tela cheia = sem som | `sfxCues` existe sem doutrina de onde pôr | 🟢 | `references/sfx-craft.md` |
| Camadas: principal / grave / apoio / doce / cauda; ≤3 por evento, faixas diferentes | "camada" aparece no Prisma em outro sentido | 🟢 | idem |
| Sincronia: impacto no transiente; **whoosh com o pico na chegada**; pop/clique no evento; ±1f perceptual | ausente | 🟢 | idem |
| Respiro de ~0,5s antes do impacto; escalada (maior impacto no ápice do hook) | ausente | 🟢 | idem |
| Não repetir o mesmo arquivo em ~20s | ausente para SFX | 🟢 | checagem no `deliver_mix` |
| Nível por categoria relativo à loudness da voz | `deliver_mix` calibra trilha pela voz; SFX por volume fixo | 🟡 | estender |
| **Índice da biblioteca:** duração útil, **tempo até o pico**, forma, brilho, favoritos | ausente (sfx_synth gera kit; Epidemic baixa avulsos) | 🟢 | `helpers/sfx_index.py` |
| Lista de eventos com id estável a partir de cortes/câmera/animações | `sfxCues` escrito à mão | 🟢 | `helpers/sfx_events.py` → rascunho de `sfxCues` |
| Busca por texto via CLAP | ausente; o Epidemic já faz busca semântica | ⚪ | usar `epidemic_music.py sfx` |

### 2.4 Preparação, memória e entrega

| Ideia do repo | Prisma hoje | Status | Destino |
|---|---|---|---|
| **Notas faladas:** "nota de edição … fim da nota" → instrução roteada + trecho sai do corte | ausente (0) | 🟢 | Fase 1, passo 2 (pré-scan) |
| Sincronia de áudio externo/tela por correlação cruzada (offset + confiança) | correlação só para A/V do delivery; áudio externo: 0 | 🟢 | `helpers/sync_sources.py` |
| Alerta de **VFR** no inventário | `render.py` lê só `r_frame_rate` (não detecta VFR) | 🟢 | `quality_probe.py`/inventário: `avg ≠ r_frame_rate` |
| Trechos engolidos: energia sem palavra → retranscrever sem contexto | `refine_edges` ("conteúdo difere"), `--window` | ⚪ | — |
| **Caderno de aprendizados** `[ ]/[x]/[-]` + "aplicar aprendizados" (gosto→perfil, ofício→skill) | anti-pattern "corrija a SKILL" existe; mecanismo de captura, não | 🟢 | `edit/aprendizados.md` + rotina |
| **Perfil persistente por cliente** (gosto separado do ofício, cada regra com origem) | Estilo é por projeto; `brand.md` é a marca do próprio Prisma | 🟢 | `perfis/<cliente>/` como padrão do gate |
| Análise de referências (cenas + fluxo óptico + afim RANSAC → curva GSAP mais próxima) | a maquinaria existe (`take_analyzer`, `stabilize`, `camera_track`, `scene_detection`); o uso para estilo, não | 🟡 | `helpers/reference_analyzer.py` reaproveitando |
| Entrega em NLE: arquivo de teste curto primeiro; "copie o que o programa exporta, não chute"; trilhas fixas; marcadores com cor do Claude; **volta** (os ajustes da pessoa valem mais) | `premiere-mcp.md` (mão via MCP, sem volta por XML) | 🟡 | doutrina comum para Premiere **e DaVinci** |
| FCP7 XML (`explodedTracks` p/ estéreo, `transitionitem`, `file://localhost/C:/`, 29,97 = `round(s·30000/1001)`) | ausente | 🟢 (se houver demanda) | `references/nle-xml.md` |
| DaVinci Resolve | **0 menções** no Prisma, com MCP `davinci-resolve` instalado nesta máquina | 🟢 | rota DaVinci (marcadores, timelines, render) |
| Versões nunca sobrescritas (`_v01`); apagar = mover para pasta de espera | `final.mp4` é sobrescrito a cada entrega | 🟢 | `final_vNN.mp4` + `latest` |
| Ids numerados para revisão por chat (`mo04`, `cam07`, `sfx12`) | revisão pela UI (chips, marcações `M`) | 🟡 | ids em `edit-data` (complementa a UI) |
| Assets: Iconify (logos/ícones SVG), print de site headless, folha de contato numerada, arquivo de créditos | Wikimedia/Pexels/Google; `media_ledger` guarda créditos | 🟡 | `helpers/icon_logo.py` + print de site |
| Modelo/esforço por etapa, `/clear` entre etapas | Prisma é uma skill com gate | ⚪ | — |

### 2.5 Segunda varredura — o que a primeira versão omitiu

A primeira passada condensou os guias por tema e perdeu itens no caminho. Esta
tabela é a releitura arquivo por arquivo, com cada item conferido no Prisma.

| Ideia do repo (arquivo) | Prisma hoje (evidência) | Status | Peso |
|---|---|---|---|
| **Nunca rodar o ajuste de bordas sobre cortes que voltaram da pessoa** — desfaria o acerto dela (`etapa-cortes.md`) | SKILL.md:84 manda rodar `refine_edges.py` "on EVERY EDL before render"; SKILL.md:269 diz que, nas edições do preview, "the user's intent wins". As duas regras **colidem**: uma borda que a pessoa arrastou no preview é movida de novo para o silêncio mais próximo | 🔴 conflito | **alto**: risco silencioso de desfazer o ajuste da pessoa |
| **Plano de inserts antes do render** (storyboard: conceito, camadas, câmera, batidas, herói, vida, saída) + autochecagem "esse conceito serviria para qualquer vídeo?" / "estou repetindo a fórmula?" (`etapa-motion-mapa.md`) | `storyboard`: 0 ocorrências. A Fase 2 vai do gate de Estilo direto para o `edit-data.json`; mudar um conceito só aparece depois do render | 🟢 | **alto**: é onde o repo diz que "mais se decide a qualidade" |
| **Marcadores do próprio Claude na timeline** (dúvida de take, hesitação mantida, nota não entendida, sugestão de reordenar, alerta técnico), ancorados no tempo da origem (`etapa-cortes.md`) | o preview recebe marcações **da pessoa** (`M`); marcadores do Claude: 0 | 🟢 | alto: tira as dúvidas do chat e põe no ponto exato |
| **Alerta de desatualização:** o corte mudou depois do plano de inserts/câmera/SFX → avisar o que refazer (`estado-do-video.md`, `skill-mestra.md`) | existe só como anti-pattern em texto (longform.md:104 "segments.json stale"); nenhuma checagem | 🟢 | médio-alto: Poka-Yoke de um erro que hoje só se evita lembrando |
| **Hesitações:** a transcrição que limpa o texto esconde o que precisa sair; corta só a hesitação isolada por silêncio e longa, a colada fica e é marcada (`decisoes.md` §4, `etapa-cortes.md`) | longform.md:38 manda "cut fillers", mas o WhisperX tende a **omitir** "ééé/hum" e não há detector; nenhuma regra de colada × isolada | 🟢 | médio: corte de hesitação hoje depende de ela ter sido transcrita |
| **Glossário de nomes próprios e termos** passado à transcrição, com a armadilha (contexto faz o modelo inventar → retranscrever trechos suspeitos sem contexto) (`decisoes.md` §4, `etapa-iniciar-preparar.md`) | `transcribe.py`: 0 ocorrências de `initial_prompt`/glossário | 🟢 | médio: marcas de cliente (XC60, PPF, nomes) saem erradas na legenda |
| **Roteiro** só para reconhecer takes e conferir a grafia, nunca para trocar o que foi falado (`decisoes.md` §6) | "roteiro" aparece só como gráfico (`ScriptInner`) | 🟢 | médio |
| **Escolha de take:** nota de edição > último take completo (o mais solto) > anterior limpo; antes de descartar uma frase como incompleta, procurar o take que a transcrição perdeu (`etapa-cortes.md`) | o brief do sub-editor diz "best take", sem ordem de desempate | 🟡 | médio |
| **Render por trecho** ("até 3:00", "o gancho"; o item pertence ao trecho em que começa; cada trecho lê os anteriores para não repetir fórmula) (`principios` §2) | ausente (0) | 🟢 | médio, longform |
| **Teste de regressão** em vídeo congelado depois de mexer num script que funciona; "mudança que ninguém pediu é bug" (`principios` §10) | sem fixture congelado no Prisma (os acertos de "regress" eram outro sentido) | 🟢 | médio: o Prisma muda helpers com frequência (o `epidemic_music.py` de hoje inclusive) |
| **Ordenar a mídia pela data de gravação** (`creation_time`; se faltar, pelo nome) (`etapa-iniciar-preparar.md`) | 0 ocorrências | 🟢 | baixo-médio: multi-take de concessionária |
| **Checar se o PyTorch vê a GPU** antes de transcrever (placa nova pede CUDA recente; cair em CPU sem avisar fica muito lento) | checagem de GPU em `diarize`/`person_matte`, não em `transcribe.py` | 🟡 | médio: há uma RTX 3060 nesta máquina |
| **Briefing ditado, salvo sem inventar** (seções por etapa, omitir as vazias) (`etapa-iniciar-preparar.md`) | `project.md` guarda decisões, não o briefing | 🟡 | baixo |
| **Pendências persistentes** que aparecem no status até serem resolvidas; nunca encerrar com revisão não aplicada nem anotada (`principios` §5) | `preview_edits.json` é apagado ao aplicar; pedido de chat não aplicado não tem registro | 🟡 | médio |
| **Feedback geral ("básico", "sem vida") pede refazer, não retocar** — reler as referências e dizer a nova direção em uma frase (`oficio-motion` §12, `etapa-motion-render.md`) | ausente como regra | 🟢 | médio |
| **Três formas de mudar o zoom** (corte seco com flash; zoom contínuo com speed ramp; corte com speed ramp leve) e quando cada uma lê melhor (`oficio-motion` §3) | só `zoomCuts` (corte seco) | 🟢 | médio |
| **Texto digitado** ~23 caracteres/s, borda suave por letra, linhas em paralelo com 3–4f de defasagem (`oficio-motion` §6) | só um exemplo gráfico (`ScriptInner`) | 🟡 | baixo |
| **Profundidade de campo** para dar foco; fundo e frente se movem só na periferia; luz que corre num trilho passa **por trás** dos nós (`oficio-motion` §7–8) | ausente | 🟢 | baixo-médio |
| **Look no lugar certo, uma vez só** (grão, lente, glitch): aplicar no render E na pós soma em dobro (`oficio-motion` §10) | `film_look.py` e as cenas HF podem empilhar grão; nenhuma regra | 🟡 | baixo-médio |
| **Asset: tipo + termo de busca** (logo pelo nome da marca, ícone por palavra em inglês, print pela URL exata); listar a pasta antes; descartar marca-mãe no lugar do produto, logo antigo, print com banner de cookies (`etapa-motion-mapa` §8, `etapa-assets.md`) | busca de imagens existe; o checklist de descarte, não | 🟡 | médio |
| **HyperFrames: compor em 1080p e renderizar na resolução do vídeo**; fila de render em segundo plano (custo fixo ~abrir o navegador) (`hyperframes.md`) | ausente | 🟢 | baixo-médio |
| **HyperFrames: anotar eventos para o som durante a construção** (o que chega, sai, bate, troca, com tipo em palavras livres, força e descrição) (`hyperframes.md`) | as cenas de `hf_motion_scenes`/`beat_edit` não emitem eventos | 🟢 | médio: é a entrada natural do `sfx_events.py` (P2) |

**Um ponto onde o repo contradiz o Prisma, e o Prisma deve ganhar:** o repo
manda "variar o tipo de troca, não repetir em sequência" (`oficio-motion` §4). O
`direction.md` do Prisma manda **uma transição primária em 60–70% das trocas +
1–2 acentos**, com origem documentada na doutrina do HyperFrames v0.4.3.
Manter a regra do Prisma; a "variação" do repo cabe nos acentos e na troca de
tópico (`direction.md:88`).

---

## 3. Recomendação priorizada

Ordem por impacto no vídeo entregue ÷ esforço. P0 é correção; P1 é só doutrina
(sem código, sem risco de regressão); P2 cria helpers pequenos; P3 depende de
demanda.

### P0 — correção (antes de tudo)
0. **Resolver o conflito `refine_edges` × edições da pessoa** (§2.5): as bordas
   vindas de `preview_edits.json` (`edl.changes`) ficam marcadas e o
   `refine_edges.py` não as move — só avisa se cortarem palavra.

   **Confirmado em 2026-11-03** (cópia de `Videos/Cayenne/edit/reel_01`, 4
   edições simuladas, fonte real): com o `quote` antigo mantido no range, **2 de 4
   edições foram desfeitas em silêncio** — o corte de "Preço de carro chinês"
   (fim 39.45 → 40.39) e o de "esse carro" no início (112.05 → 111.30). O log
   mostrou só "COLADO"/"ok", nada que dissesse "edição revertida". Causa:
   `find_seq` acha a palavra do quote antigo a até `MATCH_TOL = 1.0s` da borda
   nova e reancora nela. Sem `quote` (os `ranges` que o preview salva não têm
   esse campo), tudo é mantido, mas sem nenhuma checagem.
   Correção proposta: (a) aplicar `edl.changes` marcando `"user_edges"` no range;
   (b) `refine_edges.py` nunca move uma borda marcada, só a valida (avisa se corta
   palavra) e reescreve o `quote` a partir da janela isolada; (c) qualquer borda
   que mude palavras de lugar passa a gerar um aviso explícito; (d) SKILL.md
   descreve o procedimento de aplicar.

   **✅ Corrigido em 2026-11-03** (sem commit): `helpers/apply_preview_edits.py`
   (novo) + `refine_edges.py` (bordas `user_edges` travadas e conferidas, `quote`
   reescrito, `+palavras`/`−palavras`) + SKILL.md. Re-teste no mesmo material:
   as 4 edições mantidas; uma borda da pessoa que cai em fala foi avisada
   ("confira"); as bordas não editadas continuaram sendo refinadas; e o caminho
   antigo à mão, se alguém usar, agora mostra `+palavras: "Preço de carro
   chinês,"` em vez de passar calado.

### P1 — doutrina (1 opus, sem código)
1. **`references/motion-craft.md`**: ofício de elemento e câmera virtual, com as
   regras da §2.1 e da §2.2 que estão 🟢. Complementa `direction.md`, que decide
   *qual* transição; este arquivo decide *como cada elemento se move*. Roteado em
   SKILL.md junto com `direction.md`.
2. **`references/hyperframes-traps.md`**: as ~12 armadilhas, marcando quais já
   estão no código (`beat_edit`, `cinema_edit`, `hf_motion_scenes`) e quais
   faltam (duração (N−0,5)/fps, CSS inline, tier de motion blur, `backdrop-filter`,
   versão fixa por vídeo, margem de não determinismo).
3. **`references/sfx-craft.md`**: as 10 regras de SFX. Vira o critério para
   escrever `sfxCues` e para escolher entre o kit sintetizado e o Epidemic.
3b. **Regras de corte e revisão no SKILL.md** (§2.5): ordem de desempate de
   takes, hesitação colada × isolada, "na dúvida não corta e marca", roteiro só
   para grafia, "feedback geral = refazer", pendências que não somem.

### P1.5 — gate de plano na Fase 2 (o item de maior alavanca da 2ª varredura)
3c. **Plano de inserts numerado** (`i01`, `i02`…) entre o gate de Estilo e o
   render: conceito, formato, palavra-gatilho com tempo, intenção da câmera;
   storyboard obrigatório no hook. A pessoa aprova ou risca por número; só então
   o `edit-data.json` é escrito. Mudar um conceito custa uma linha, não um render.

### P2 — helpers pequenos, alto retorno
4. **Notas faladas na Fase 1**: busca tolerante no transcript, interpretação,
   exclusão automática do trecho no EDL. É barato e muda a forma de gravar.
5. **`sfx_index.py` + `sfx_events.py`**: índice (tempo até o pico, duração útil,
   brilho) do kit, da pasta `sfx/` e dos downloads do Epidemic; lista de eventos
   com id estável a partir de `edit-data` (transições, inserts, `zoomCuts`, hook).
   Saída: rascunho de `sfxCues` com `at = evento − pico`.
6. **Perfil por cliente + caderno de aprendizados**: `perfis/<cliente>/`
   (padrões do gate de Estilo, grade, gosto de trilha e SFX, cada regra com
   origem) e `edit/aprendizados.md`. Liga com o `*retrospective` do Maestro: o
   aprendizado vira mudança na skill só com aprovação.
7. **Preparação:** alerta de VFR e `sync_sources.py` (lapela, gravador,
   segunda câmera) por correlação cruzada com confiança. Hoje o Prisma não
   cobre podcast e entrevista com áudio separado. Junto: ordenar por
   `creation_time`, checar a GPU antes de transcrever, e `--glossary` no
   `transcribe.py` (com retranscrição sem contexto dos trechos suspeitos).
7b. **Marcadores do Claude no preview** + **alerta de desatualização** (o EDL
   mudou depois do `edit-data`/`segments.json` → o status mostra o que refazer).
7c. **Detector de hesitação** acústico (voz sem palavra transcrita, curta, entre
   silêncios) → candidata a corte quando isolada, marcador quando colada.
7d. **Fixture de regressão:** um clipe curto congelado + saídas esperadas
   (`verify_cut`, durações, níveis) para rodar depois de mexer em helper.

### P3 — sob demanda
8. **Rota DaVinci Resolve** (há MCP aqui) com a doutrina de entrega em NLE:
   teste curto primeiro, trilhas fixas, marcadores, volta.
9. **Câmera casada com inserts** (`exitDir` no insert → chegada da câmera).
   Depende do P1 estar escrito e medido num vídeo.
10. **`reference_analyzer.py`**: medir as referências de que o cliente gosta e
    escrever o perfil com números.
11. **Versionamento de entregas** (`final_vNN.mp4`) e ids de revisão no
    `edit-data`.
12. **Assets SVG** (Iconify, logos oficiais, print de site) com folha numerada.

---

## 4. O que NÃO trazer

- **A arquitetura de 8 skills + entrevista + `/clear` por etapa.** O Prisma é uma
  skill com phase gate, preview e Estilo; fatiar quebraria o gate e a UI. Só a
  *disciplina* (travar o aprovado; avisar o que precisa refazer se o corte
  mudar) já existe no Prisma.
- **"Escrever scripts na primeira vez que a etapa roda".** O Prisma inverteu isso
  de propósito: helpers medidos e versionados. Manter.
- **O guia de cortes e o de transcrição.** São subconjuntos do que o Prisma mede
  (J-cut, `refine_edges`, `voice_levels`, janelas).
- **Números como regra fixa.** Entram como hipótese com origem
  ("fluxo-de-edicao, não medido aqui") até um render do Prisma confirmar.

## 5. Licença

MIT. A doutrina pode ser adaptada; manter a atribuição ("adaptado de
LeiteZ/fluxo-de-edicao, MIT") nos arquivos que nascerem dela.
