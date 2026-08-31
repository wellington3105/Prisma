# Opus de Evolução — Prisma

**Data:** 2026-08-18 · **Conduzido por:** Maestro (Antigravity)
**Restrição do usuário:** NÃO envolver Adobe Premiere. Trazer capacidades para
dentro do Prisma, que é autônoma e entrega MP4.
**Fonte analisada:** `deep-research-report (1).md` (Editor Premium / Caption Flow /
stack open source)

---

## 1. Veredito sobre o relatório

O relatório responde à pergunta *"como reproduzir Editor Premium e Caption Flow"*.
Com a restrição do usuário, **~50% dele é inaplicável**: AutoSubs, UXP/MOGRT,
Premiere MCP, Raunen e o `SequenceEditor.insertMogrtFromPath()` existem apenas
para falar com o Premiere. Descartados sem perda.

Do que resta, a maior parte **já está construída no Prisma — e por um caminho
melhor**:

| Relatório propõe | Estado real no Prisma | Veredito |
|---|---|---|
| WhisperX (timestamps por palavra) | `transcribe.py` — é o motor, com alinhamento forçado wav2vec2 | ✅ já existe |
| Auto-Editor (corte de silêncio) | `speech_regions.py` + EDL | ✅ **superior** — ver nota abaixo |
| Kinetic captions (AI Video Captions, 6 estilos ASS) | 6 estilos Remotion + `caption_style.py` | ✅ já existe, e editável |
| VideoCaptioner (quebra de frase por LLM) | `caption_style.py` + validação de cues | ✅ já existe |
| Safe zone | `SAFE_WIDTH 720`, verificado contra screenshot real | ✅ já existe |
| JSON intermediário como objeto central | `edl.json` + `edit-data.json` | ✅ já existe |
| Biblioteca visual como ativo real | Template Remotion imutável + data-driven | ✅ já existe |

**Nota sobre Auto-Editor — por que o Prisma é superior, não equivalente:**
o Auto-Editor corta por loudness/inatividade cega. Nesta sessão de produção
(vídeo 1001, TDAH), o pipeline do Prisma identificou 9 silêncios ≥0.45s e
**preservou os 2 maiores** porque eram pausas retóricas antes dos melhores beats
("TDAH interfere demais", "tem nada de modinha"). Um corte por loudness teria
destruído os dois. Essa distinção é editorial, não acústica.

### O que o relatório NÃO menciona e é o diferencial real do Prisma

**Verificação numérica antes da visual.** Nenhum projeto do relatório faz isso.
Evidência da sessão de produção:

- `voice_levels.py` encontrou 19 quedas de nível que o transcript não mostra
  (transcript é level-blind);
- transcrição isolada do range 79.5–87.5s provou que `"devido a"` NÃO era frase
  abandonada — o transcript completo enganava por palavra esticada;
- correlação de áudio em 3 pontos mediu **+42.7ms constante** (sem deriva),
  o que permitiu manter ~130 SFX das legendas que o re-mux teria destruído;
- `verify_cut.py` deu ~350 tokens de texto no lugar de N imagens.

**Conclusão estratégica:** o Prisma não é um wrapper de Whisper. O relatório
descreve o estado da arte de 2026 e o Prisma já está nele ou à frente, exceto
em 3 pontos concretos (seção 3).

---

## 2. Diagnóstico Gemba — o formato horizontal

**Premissa corrigida:** o horizontal NÃO está ausente. Existe
`references/longform.md` (143 linhas) e `assets/longform/`. Mas está
**esquelético**.

### Medição

| | shortform | longform | razão |
|---|---:|---:|---:|
| Arquivos em `src/` | 8 | 3 | 37% |
| Linhas de componente | 1.821 | 200 | **11%** |
| Componentes de legenda | 3 arquivos (720 linhas) | **0** | 0% |

### Os 3 defeitos concretos

**D1 — Longform não queima legenda no vídeo.** `grep -ci caption` no
`Main.tsx` do longform retorna **1**. Ele gera `.srt` (arquivo separado para o
YouTube) mas não tem componente de legenda na tela. O shortform tem
`StackedCaptions.tsx` (286), `ScatterCaptions.tsx` (243), `SimpleCaptions.tsx`
(191). Vídeo de YouTube assistido sem som fica sem legenda.

**D2 — A aba Estilo não abre em longform.** `STYLE_CATALOG` em
`assets/preview/app.js` tem vocabulário 100% vertical. Os mocks são
`viewBox="0 0 66 118"` — retrato. Não existe um único mock 16:9. Consequência
documentada no próprio `shortform.md`: *"on a longform job the gate has nothing
to offer yet, so skip awaitingStyle and ask the layer questions in chat"*.
O usuário escolhe às cegas, exatamente o que o gate visual existe para evitar.

**D3 — Tudo em um arquivo.** Os 182 linhas do `Main.tsx` longform contêm
`BrollEl`, `LowerThird`, `ChapterCard`, `CalloutEl` e `Soundtrack` inline.
O schema (`broll`, `lowerThirds`, `chapters`, `callouts`) está correto — a
arquitetura data-driven foi respeitada — mas cada componente tem ~18 linhas,
contra 286 do equivalente shortform. São stubs funcionais, não acabamento.

---

## 3. As 3 lacunas genuínas (o que o relatório traz de novo)

### L1 — Decupagem automática (OpenShorts)

**Ausente.** Hoje o Prisma corta 1 vídeo por vez. O relatório descreve o pipeline:
vídeo longo → transcrição → LLM pontua momentos → escolhe 3-15 → scene detection
→ reframe 9:16 → legenda → N shorts.

**O Prisma já tem 4 das 6 peças:** transcrição, `face_track.py` (reframe),
`watch_video.py` (scene detection), e todo o pipeline de legenda. **Falta:**
o motor de pontuação de momentos e o loop de múltiplas saídas.

Esta é a lacuna de maior alavancagem: transforma 1 entrega em N.

### L2 — B-roll automático

**Ausente como automação.** Existem `pexels_search.py`, `wikimedia_images.py`,
`google_images.py` — mas a curadoria é 100% manual. Ficou pendente nesta sessão
de produção justamente por isso.

**Nota de qualidade (relevante):** ao mapear candidatos no vídeo 1001, 36 termos
foram detectados e apenas **5-6 mereciam imagem**. "Organização", "planejamento",
"tomada de decisões" são abstrações — banco de imagens devolve clichê corporativo.
A automação certa **não é buscar imagem para todo substantivo**; é filtrar por
concretude e propor curadoria ao humano.

### L3 — Motor de sugestão de edição híbrido

**Parcialmente presente, não formalizado.** O relatório propõe: regras
determinísticas geram candidatos → LLM escolhe apenas entre eles.

O Prisma já faz isso informalmente (`speech_regions` gera candidatos de corte,
o modelo decide). Falta o formato explícito de candidatos para punch-in,
gráfico, B-roll e ênfase.

---

## 4. Dívida técnica — bugs reincidentes (Windows)

Todos observados na sessão de produção 2026-08-18. **Todos vão reincidir.**

| # | Bug | Causa | Correção |
|---|---|---|---|
| B1 | `transcribe.py` crashou | `print()` com `→` em console cp1252 | `PYTHONUTF8=1` no topo dos helpers, ou trocar `→` por `->` |
| B2 | `preview_server.py` não subiu | idem, linha 393 | idem |
| B3 | Download do modelo falhou | HuggingFace tenta symlink; Windows exige privilégio | `HF_HUB_DISABLE_SYMLINKS=1` no ambiente |
| B4 | `detect_color.py` deu confiança baixa | análise de imagem falhou (path/encoding) | investigar — a medição manual funcionou |
| B5 | `caption_style.py` promoveu palavras curtas a SOLO | 3 cues "Então," de 0.16–0.20s < MIN_SOLO_MS 340 | aplicar o filtro que já está documentado |
| B6 | Última cue ultrapassou o fim do vídeo | 153.27s vs 152.82s | clamp na duração |

B1–B3 bloquearam a sessão por ~15 minutos cada. B5–B6 exigiram script de
correção manual — **e o `shortform.md` já documenta a regra do MIN_SOLO_MS**,
ou seja, o helper não implementa o que a referência manda.

**Lei DMAIC (Sigma):** se o mesmo bug aparece duas vezes, o processo tem falha
estrutural. B1 e B2 são o MESMO bug em arquivos diferentes → é estrutural.

---

## 4b. P0 — EXECUTADO em 2026-08-18

| # | Bug | Correção | Evidência |
|---|---|---|---|
| B1+B2 | `UnicodeEncodeError` matava helpers no console cp1252 | guarda `reconfigure(utf-8)` em **25 helpers** — nenhum tinha | `detect_color.py` roda sem `PYTHONIOENCODING`, acentos corretos |
| — | `read_text()`/`write_text()` sem encoding | UTF-8 fixado em **18 arquivos**, ~35 pontos de I/O | 25/25 com sintaxe válida |
| B4 | `detect_color` dava `confidence: low` | caminho do dump quebrava o filtergraph: `C:` é separador de opção do ffmpeg. Escapar não basta (exit 4294967274) — roda com `cwd=temp` e **nome de arquivo puro** | **`confiança high`**, 31 frames, piso 0.047 / teto 0.937 |
| B5 | 5 cues SOLO inválidas | `build_cues` promovia QUALQUER grupo de 1 palavra; agora exige `>= MIN_SOLO_MS` e não-conectivo (nova lista `CONNECTIVES`) | 17 solo → **10**; curtas 3→0, conectivas 5→0 |
| B6 | última cue ultrapassava o vídeo | `--video` mede a duração e limita `endMs` | 153,27s → **152,82s** exato |

Backup em `helpers.bak.20260818/`.

**A lição que vale mais que os bugs:** B1/B2 eram o mesmo defeito em arquivos
diferentes, e B4 era o mesmo *tipo* de defeito (caminho Windows encontrando um
parser) num terceiro lugar. Nenhum era isolado. E B5 estava documentado na
referência sem estar implementado no código — a regra existia, o gerador não a
cumpria, e o custo caiu na inspeção manual.

---

## 5. Plano priorizado

Ordenado por (impacto × frequência) ÷ esforço.

### P0 — Robustez (esforço: baixo · impacto: alto · reincidência: certa)

1. **UTF-8 estrutural.** Preâmbulo em todo helper que imprime, ou varredura
   substituindo caracteres não-ASCII em `print()`. Resolve B1+B2 de uma vez.
2. **`HF_HUB_DISABLE_SYMLINKS=1`** documentado no `install.md` e setado nos
   helpers que baixam modelo.
3. **`caption_style.py`: implementar MIN_SOLO_MS e clamp de duração.** A regra
   já está escrita na referência; o código não a cumpre. Poka-Yoke: o gerador
   deve tornar o defeito impossível, não deixar para a validação.

**Critério de aceite:** rodar o pipeline completo num Windows limpo sem
intervenção manual.

### P1 — Longform ao nível do shortform (esforço: médio · impacto: alto)

4. **Componentes de legenda para 16:9.** Portar os 3 estilos, reajustando
   geometria: 16:9 tem safe-width diferente e não tem action rail lateral.
   **Sem isso o longform não entrega legenda na tela.**
5. **`STYLE_CATALOG` longform.** Mocks 16:9 (`viewBox="0 0 118 66"`), opções de
   layout, lower-thirds, cartões de capítulo, B-roll. Abre a aba Estilo para
   horizontal e elimina a pergunta às cegas no chat.
6. **Extrair componentes do `Main.tsx`** para arquivos dedicados, seguindo a
   estrutura do shortform.

**Critério de aceite:** editar um vídeo horizontal real de ponta a ponta com a
aba Estilo funcionando e legenda queimada.

### P2 — Decupagem automática (esforço: alto · impacto: multiplicador)

7. **`clip_finder.py`** — lê `takes_packed.md`, pontua momentos (gancho, tensão,
   payload, autossuficiência), propõe N janelas com justificativa.
8. **Loop de múltiplas saídas** — cada janela vira um EDL próprio; reusar
   `face_track.py` para reframe 9:16.

**Critério de aceite:** 1 vídeo de 20min → 5 Reels aprovados pelo usuário.

### P3 — B-roll semi-automático (esforço: médio · impacto: médio)

9. **`broll_candidates.py`** — detecta substantivos **concretos** (filtro de
   concretude, não frequência), busca em Wikimedia/Pexels, monta contact sheet
   de candidatos com timestamps sugeridos.
10. **Curadoria humana obrigatória.** A máquina propõe, o usuário aprova.
    Automação total produziria o clichê corporativo descrito em L2.

### P4 — Motor de sugestão formalizado (esforço: médio · impacto: médio)

11. Formalizar o gerador de candidatos (pausa >900ms → corte; início de
    argumento → punch-in; palavra-chave → gráfico; lista → overlay) e restringir
    o LLM a escolher entre candidatos, nunca a inventar timestamps.

---

## 6. O que NÃO fazer

- **Não portar AutoSubs/UXP/MOGRT/Premiere MCP.** Fora de escopo por decisão do
  usuário, e o Prisma é autônoma — não precisa de NLE hospedeiro.
- **Não trocar WhisperX por outro ASR.** O relatório é claro: ganho marginal.
  O gargalo nunca foi o ASR.
- **Não substituir `speech_regions.py` por Auto-Editor.** Seria regressão:
  perderia a distinção entre pausa retórica e dead air.
- **Não automatizar B-roll ponta a ponta.** Ver L2.
- **Não copiar identidade visual de produtos comerciais.** O relatório alerta,
  e está certo: reproduzir mecanismo é legítimo, copiar asset criativo não.

---

## 7. Síntese

O relatório confirma, por caminho independente, que a arquitetura do Prisma está
correta: JSON intermediário, ASR local com alinhamento forçado, biblioteca visual
como ativo, regras determinísticas + LLM restrito a escolher.

**A distância entre o Prisma e os produtos pagos analisados não é de IA. É de
acabamento** — e concentrada em um lugar específico: **o formato horizontal, que
está 11% construído**.

A ordem correta é: **primeiro parar de sangrar** (P0, bugs que bloqueiam toda
sessão em Windows), **depois fechar o buraco do horizontal** (P1, a lacuna real),
**e só então multiplicar** (P2 decupagem, o item de maior alavancagem estratégica).

— Maestro, conduzindo o impossível 🎼
