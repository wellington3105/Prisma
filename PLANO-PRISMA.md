# Opus Prisma — Análise de 9 repositórios + Plano de Renomeação

**Conduzido por:** Maestro (Antigravity) · 2026-08-19
**Lane:** planejamento (BMAD/Clareza). **Nada aqui foi executado** — este é o
artefato de decisão que precede qualquer story.

> **Nota sobre BMAD:** o `OPERATING-CONTRACT` do Maestro manda rotear planejamento
> por BMAD *quando existe uma lane local*. Verifiquei: não há `bmad:sandbox:*`
> neste repo nem squad `bmad` no vault (`~/.aiox-global/squads/`). Segui então a
> cláusula de fallback do próprio contrato — Fluxo da Clareza completo, artefatos
> de planejamento, zero execução. O formato abaixo (Épicos → Stories → Critérios)
> é o de handoff BMAD→AIOX.

---

## 1. Veredito por repositório

Licenças e atividade verificados via API do GitHub em 2026-08-19 (não pelo README).

| Repo | Licença | Stars | Último push | Veredito |
|---|---|---:|---|---|
| **openshorts** | NOASSERTION¹ | 3.2k | 2026-08-19 | 🥇 **EXTRAIR** |
| **hyperframes** | Apache-2.0 | 41.7k | 2026-08-19 | 🥇 **EXTRAIR (ideias)** |
| **auto-subs** | MIT | 4.0k | 2026-08-02 | 🥈 **EXTRAIR (1 peça)** |
| **openreel-video** | MIT | 4.8k | 2026-08-19 | 📖 referência de UI |
| **opencut** | MIT | 85.2k | 2026-08-10 | ⏸️ **imaturo** — ver §2.5 |
| **MoneyPrinterTurbo** | MIT | 110k | 2026-08-19 | ❌ escopo oposto |
| **celery** | NOASSERTION | 28.8k | 2026-08-18 | ⏸️ prematuro |
| **temporal** | MIT | 22.4k | 2026-08-19 | ⏸️ prematuro |
| **postiz-app** | **AGPL-3.0** | 34.9k | 2026-08-19 | ⚠️ só via API |
| **minio** | **AGPL-3.0** | 61.4k | 2026-04-24 | ❌ **ARQUIVADO** |
| **mixpost** | MIT | 3.5k | 2026-03-16 | ⏸️ fora de escopo |

¹ README declara MIT no core, com exceção comercial no diretório `cloud/`.
O GitHub não consegue classificar por causa da exceção. **Extrair apenas de fora
de `cloud/`** — e confirmar arquivo a arquivo antes de copiar código.

### Os dois alertas de licença

**MinIO está ARQUIVADO** (sem commits desde abril) **e é AGPL**. Duplo motivo
para descarte: dependência morta e copyleft. Fica registrado porque "MinIO" ainda
soa como escolha óbvia para storage S3-compatível — não é mais.

**Postiz é AGPL-3.0.** AGPL é copyleft viral e alcança uso em rede. Integrar
código dele obrigaria a abrir o Prisma sob AGPL. **Consumir a API HTTP dele é
seguro; copiar código não é.** Mesma regra vale para Mixpost caso vire opção.

---

## 2. O que extrair — e por quê

O Prisma tem **26 helpers**. A busca por capacidade mostrou os buracos reais:
`scene: 0`, `reframe: 0`, `diariz: 0`. É exatamente aí que os repos entram.

### 🥇 OpenShorts — o alvo principal

Mesma stack do Prisma (Python + FFmpeg + faster-whisper + yt-dlp). Arquivos que
importam, todos na raiz (fora de `cloud/`):

| Arquivo | O que resolve no Prisma | Estado hoje |
|---|---|---|
| `reframe_v2.py` | Reframe 9:16 com MediaPipe + YOLOv8 | **não existe** |
| `scene_detection.py` | Detecção de cortes de cena | **não existe** |
| `punch_in.py` | Zoom de ênfase automatizado | manual |
| `recut.py` | Re-corte de segmentos | manual |
| `quality_probe.py` | Sonda de qualidade | parcial (`verify_cut.py`) |

**A peça mais valiosa é o `reframe_v2.py`.** Ele resolve o P2 do
`EVOLUCAO-OPUS.md` (decupagem automática: 1 longo → N Reels), que está pendente
desde a análise anterior. O Prisma já tem `face_track.py`, mas não sabe
**reenquadrar** 16:9 → 9:16 seguindo o rosto.

**Ressalva honesta:** a detecção de momentos virais deles depende de **Gemini
API**. Isso é dependência externa paga e contraria a soberania local do Prisma
(hoje 100% offline na Fase 1, sem chave obrigatória). A heurística de corte pode
ser portada; a chamada ao Gemini deve ser **opcional**, nunca requisito.

### 🥈 AutoSubs — uma peça só

MIT limpo, 4k estrelas, ativo. O Prisma **já tem** transcrição melhor para o caso
dele (WhisperX com alinhamento forçado). O que ele **não tem**:

- **Diarização de falantes** (~40 MB, modelo selecionável) → permite legenda com
  estilo por falante. Relevante para entrevista/podcast, inútil para talking head
  solo.
- **Silero VAD** → o Prisma usa `silencedetect` do FFmpeg em `speech_regions.py`.
  VAD neural é mais preciso em ruído. **Melhoria incremental, não lacuna.**

### 📖 OpenReel — referência, não código

TypeScript/browser (WebGPU + WebCodecs). Arquitetura incompatível com o pipeline
Python+Remotion do Prisma. **Mas** é a melhor referência disponível de UX de
timeline em navegador — vale estudar as decisões de interação para o preview.
Não copiar código.

### 🥇 HyperFrames (HeyGen) — o segundo alvo

Apache-2.0, 41.7k estrelas, **8.203 arquivos**, commit no mesmo dia da análise.
Motor de render HTML→vídeo (Puppeteer + FFmpeg), a mesma base técnica do Remotion
que o Prisma usa.

**Já colhemos uma ideia dele nesta sessão:** o `music_carve.py` do Prisma nasceu
do conceito de *voiceover carve* do `/hyperframes-audio` — comprimir só a banda
de frequência da voz em vez de baixar a música inteira. Medido no projeto 1001:
−8,7 dB na banda da voz com grave e agudo intactos, permitindo a trilha em 0.22
em vez de 0.10.

O que **ainda** vale colher (por ideia, não por código):

| Skill deles | O que resolve no Prisma |
|---|---|
| `/hyperframes-audio` | Cadeia completa: EQ, compressor, limiter, gate, reverb + **envelopes de automação** |
| `/media-use` | Resolve SFX/BGM/imagem/LUT em arquivo local com **ledger de manifest** — é o P3 (B-roll) do Opus anterior |
| `packages/shader-transitions` | Transições WebGL — o Prisma tem só flash |
| `/hyperframes-keyframes` | Diagnóstico de movimento renderizado (`hyperframes keyframes`) |

**Por que NÃO migrar de motor:** o Prisma tem 1.821 linhas de template Remotion
funcionando, mais o preview e a integração `edit-data.json`. Migrar significaria
reescrever tudo isso e perder o que o HyperFrames não tem: **verificação numérica**
(`verify_cut.py`, medição de deriva de áudio, `voice_levels.py`). A leitura certa
continua sendo garimpar ideias.

**Nota de licença:** Apache-2.0 é permissiva e compatível, mas exige **preservar
avisos de copyright e declarar mudanças**. Se algum código for portado (não só a
ideia), isso vira requisito no `NOTICE`.

### ⏸️ OpenCut — 85k estrelas, mas imaturo

Este é o caso em que a métrica social engana, e vale registrar o número:

| | OpenCut (reescrita) | HyperFrames |
|---|---:|---:|
| Arquivos no repo | **151** | **8.203** |
| Arquivos Rust | 15 | — |
| Último commit | 01/08 (18 dias antes) | 19/08 (mesmo dia) |

O próprio README declara: *"OpenCut is being rewritten from the ground up"*, e
lista o roadmap inteiro como **"what's coming"** — Editor API, plugins, core Rust,
MCP server, headless. Nada disso está pronto.

E a versão que o README aponta como "a de hoje" — `opencut-app/opencut-classic` —
**está ARQUIVADA** (push em maio, 223 estrelas). Ou seja: a versão estável foi
descontinuada e a substituta é um esqueleto de 151 arquivos.

**Revisitar quando:** a reescrita atingir paridade funcional e o MCP server sair
do roadmap. Aí o "headless mode + batch rendering" fica genuinamente interessante.
Hoje, não há o que extrair.

### ❌ MoneyPrinterTurbo — escopo oposto

110k estrelas, mas gera vídeo **do zero** a partir de um tema (stock footage +
TTS). O Prisma **edita material próprio do usuário**. São produtos opostos:
um fabrica conteúdo, o outro respeita e lapida o que foi gravado. Nada a extrair.

### ⏸️ Celery / Temporal — prematuro, não errado

Ambos resolvem orquestração de jobs longos. O Prisma tem esse problema em
potencial (renders de 10+ min), mas hoje roda **um vídeo por vez, em uma
máquina, com um usuário**. Introduzir Celery/Temporal agora é over-engineering
clássico — a Muda que o @Architect deve barrar.

**Gatilho para revisitar:** quando existir fila de múltiplos vídeos simultâneos
ou execução em servidor. Aí Temporal (MIT, Go, durable execution) é a escolha
melhor que Celery para pipelines de vídeo, porque sobrevive a restart no meio de
um render de 40 minutos.

---

## 3. Épicos e Stories

### ÉPICO A — Renomeação Edvid → Prisma ✅ CONCLUÍDO (2026-08-19)

**Executado por completo, incluindo A6.** Tudo abaixo está feito e verificado.
As únicas menções a "edvid" que sobrevivem no repo são deliberadas: este plano
(que precisa nomear o antes/depois) e `references/brand.md` (registro histórico
da marca). Zero menções a "Fill Rocha" em qualquer lugar.

**Verificação pós-execução:**
- `uv sync` trocou `edvid==0.1.0` por `prisma==0.1.0` sem rebaixar torch/whisperx
- `uv run python -c "import whisperx, cv2"` → OK (whisperx + opencv 4.10.0)
- Backup de código em `~/.claude/skills/edvid.code-backup/` (2.9 MB, íntegro)

**Bug de infraestrutura encontrado e corrigido (2026-08-19), fora do escopo
original:** depois do `mv edvid prisma`, `uv sync` sozinho **não** corrige os
executáveis "trampoline" que o `uv` gera em `.venv/Scripts/*.exe` para cada
entry point de pacote (yt-dlp, whisperx, e mais 37 outros). Cada `.exe` embute
o caminho absoluto do diretório em que foi criado; sobrevivem ao `mv` porque
`uv sync` só reconcilia o pacote *raiz* (`prisma`), não as dependências já
instaladas. Sintoma: `error: uv trampoline failed to canonicalize script path`,
disparado sempre que o script chama um desses binários via `subprocess` — o que
`ingest_url.py` faz a cada chamada (`yt-dlp`). Corrigido com
`uv sync --reinstall`, que força a regeneração de todos os 39 trampolines.
**Regra para a próxima renomeação de diretório:** `uv sync --reinstall`, não só
`uv sync`.

**Escopo medido:** 21 arquivos do projeto continham "edvid"
(exclui `.venv/` e `helpers.bak.20260818/`, que não são código vivo).

| Story | Arquivo(s) | Critério de aceite |
|---|---|---|
| A1 | `SKILL.md`, `README.md`, `install.md` | Zero ocorrências de "edvid"; skill continua carregando |
| A2 | `references/*.md` (5 arquivos) | `brand.md` já descreve PRISMA — alinhar os outros 4 |
| A3 | `helpers/*.py` (7 arquivos) | Strings de UI e docstrings; **não** renomear paths que quebrem |
| A4 | `assets/preview/app.js`, `assets/longform/README.md` | UI já mostra PRISMA; limpar resíduo interno |
| A5 | `edvid_install.py` → `prisma_install.py` | Instalação funciona do zero |
| A6 | **Diretório** `~/.claude/skills/edvid/` → `prisma/` | ⚠️ **DECISÃO NECESSÁRIA** — ver abaixo |
| A7 | `EVOLUCAO-OPUS.md`, `PLANO-PRISMA.md` | Consistência de nome |

**⚠️ A6 é a story de risco.** Renomear o diretório da skill:
- quebra o comando `/edvid` (vira `/prisma`)
- invalida `.claude/launch.json` deste projeto (aponta para o path antigo)
- invalida o `.venv` (paths absolutos embutidos) → exige `uv sync` de novo
- `edvid-0.1.0.dist-info` no venv precisa reinstalação

**Recomendação:** fazer A1–A5 e A7 primeiro (baixo risco, alto valor de
consistência) e tratar A6 como decisão separada, com backup antes.

### ÉPICO B — Extração do OpenShorts

| Story | Entrega | Critério de aceite | Status |
|---|---|---|---|
| **B1** | Auditoria de licença arquivo a arquivo | Confirmado que cada arquivo a portar está fora de `cloud/` e sob MIT | ✅ **CONCLUÍDO** — ver abaixo |
| **B2** | `quality_probe.py` — sonda de resolução do YouTube | `ingest_url.py` aborta antes de gastar 20+min num 360p | ✅ **CONCLUÍDO** — ver abaixo |
| **B3** | `reframe.py` — reframe 9:16 com tracking | 16:9 → 9:16 seguindo rosto, verificado em vídeo real | ✅ **CONCLUÍDO** — ver abaixo |
| **B4** | `scene_detection.py` | Cortes detectados batem com inspeção visual | ✅ **CONCLUÍDO** — ver abaixo |
| **B5** | `clip_finder.py` — decupagem (P2 do Opus anterior) | 1 vídeo de 20min → N Reels aprovados pelo usuário | ✅ **CONCLUÍDO** — ver abaixo |
| **B6** | Atribuição de licença | `NOTICE`/`CREDITS` citando OpenShorts + autores | ✅ **CONCLUÍDO** — ver abaixo |

**Regra de ouro em B:** **Gemini opcional, jamais obrigatório.** A Fase 1 do
Prisma não pede chave hoje, e isso é uma qualidade a preservar.

#### B1 — Resultado da auditoria (2026-08-19)

Verificado via API do GitHub, árvore completa do repo (268 arquivos, sem
truncamento) e leitura direta dos dois arquivos `LICENSE`:

- **`LICENSE` raiz = MIT puro**, com uma exceção textual explícita: *"All
  content that resides under the cloud/ directory... is licensed under...
  the OpenShorts Commercial License, not under the MIT License below."*
- **`cloud/LICENSE` = licença comercial separada** (21 arquivos: `billing.py`,
  `auth.py`, `managed_keys.py`, etc.) — permite uso pessoal/interno, **proíbe**
  oferecer como serviço hospedado/pago a terceiros. Não relevante: nenhum
  arquivo-alvo está lá.
- **Os 5 arquivos-alvo estão todos na raiz**, fora de `cloud/`:
  `reframe_v2.py` (562 linhas), `scene_detection.py` (149), `punch_in.py` (187),
  `recut.py` (336), `quality_probe.py` (108).
- **Nenhum importa de `cloud/`** — confirmado por grep no código-fonte de cada
  um. São módulos autocontidos sob MIT.
- Nenhum arquivo carrega cabeçalho de licença próprio divergente do `LICENSE`
  raiz.

**Reordenação decidida a partir da leitura do código, não só do nome do
arquivo:** `quality_probe.py` é o menor (108 linhas, stdlib + subprocess, zero
dependência pesada) e resolve algo que o `ingest_url.py` do Prisma já sente na
prática — sondar a resolução máxima do YouTube **antes** de queimar 20+ minutos
de transcrição/render num vídeo que só existe em 360p. Portar essa peça primeiro
valida o processo de atribuição (B6) num arquivo pequeno antes de investir nos
562 do `reframe_v2.py`.

#### B2 — Resultado (2026-08-19)

- **`helpers/quality_probe.py`** criado — porta adaptada, não colada:
  - removido `load_dotenv()` (nenhuma chave envolvida; o Prisma não tem essa
    dependência)
  - `--cookies` virou flag explícita em vez de hardcoded `/app/cookies.txt`
    (caminho específico do container Docker do OpenShorts, sem sentido aqui)
  - guarda de UTF-8 padrão do Prisma adicionada no topo
- **Testado com vídeos reais**, não só sintaxe: "Me at the zoo" →
  `{"max_height": 240, ...}` (bate com a resolução histórica real do vídeo);
  um vídeo 4K conhecido → `{"max_height": 2160, ...}` em 2,5s, confirmando que
  o `break` ao atingir ≥1080p funciona.
- **Integrado a `ingest_url.py`**: nova flag `--skip-probe` (default: sonda
  roda), aviso em stderr quando a resolução pedida excede o que a fonte
  oferece — nunca bloqueia o download, só avisa antes.

**Achado fora do escopo, descoberto ao testar a integração:** `uv run python
helpers/ingest_url.py <url> ...` falhava com `uv trampoline failed to
canonicalize script path` — não era bug no código novo, era o resíduo do A6
descrito acima (39 executáveis `.venv/Scripts/*.exe` com caminho absoluto
morto). Isolado por eliminação (script sem args → OK; com 1 arg trivial → roda
mas emite o erro no fim; `--help` → OK) até apontar para o subprocesso
`yt-dlp` como a causa. Corrigido com `uv sync --reinstall`.

#### B3 — Resultado (2026-08-19)

- **`helpers/reframe.py`** criado — porta adaptada de `reframe_v2.py` **mais** as
  peças de `main.py` que ele importava e sem as quais o arquivo não roda:
  `SmoothedCameraman`, `SpeakerTracker`, `detect_face_candidates` e
  `analyze_scenes_strategy`. O `reframe_v2.py` sozinho é inútil — 60% da
  inteligência de câmera mora no `main.py` (1714 linhas) do OpenShorts.
- **Arquitetura mantida** (é o que dá o ganho de performance): duas passadas —
  análise num decode ffmpeg a ≤640px alimentando MediaPipe + tracker, e render
  nativo em ffmpeg com `sendcmd` movendo o `crop` quadro a quadro. Sem pipe de
  frames crus, sem segundo decode em resolução cheia.

**O que foi cortado, e por quê:**

- **Layouts SPLIT / SCREENCAST / INSET / ALTERNATE / WIDE** e seus 5 módulos
  (`split_layout`, `screencast_layout`, `camera_inset`, `active_speaker`,
  `punch_in`). Servem a um SaaS de podcast/screen-share; `screencast_layout`
  ainda chama a **API do Gemini**, que esta skill não tem chave para usar por
  princípio. Sobraram TRACK e GENERAL — os dois que importam em talking-head.
- **`crop_overrides` / `force_strategy` por cena**: existiam para servir a UI de
  enquadramento manual do editor web. `--force-strategy` sobreviveu como flag
  global (uma linha, resolve "o tracker errou este clipe"); o mapa de frações
  por cena, não.
- **Fallback YOLO** (`detect_person_yolo`): exige `ultralytics` + download de
  modelo para um caso que o BlazeFace já cobre em talking-head. Sem rosto, a
  câmera simplesmente segura o último alvo.
- **NVENC, normalização de loudness, `DETECT_LOCK`**: o lock serializa
  inferência entre clipes em paralelo; aqui roda um clipe por vez.

**Achado técnico relevante — a API que o OpenShorts usa não existe mais:**
o original chama `mp.solutions.face_detection`, removida no **mediapipe 1.x**
(instalado aqui: 1.0.1, que só expõe `Image`, `ImageFormat` e `tasks`). Portado
para a **Tasks API** (`vision.FaceDetector`), que exige um arquivo de modelo em
disco. Segunda armadilha: existem dois `.tflite` de mesmo nome nos servidores do
Google e **só um funciona** — o de `mediapipe-assets/` falha com
`Input tensor has type float32: it requires specifying NormalizationOptions
metadata`; o correto é o de `mediapipe-models/.../float16/1/`. Fica versionado
em `assets/models/blaze_face_short_range.tflite` (230KB) para o render nunca
depender de rede, com download automático se faltar.

- **`mediapipe` adicionado como extra opcional** `reframe` no `pyproject.toml`
  (padrão do `matting`): `uv sync --extra reframe`. Fallback para cascata Haar
  numa instalação base — pior, mas roda.

**Como foi testado (vídeo real, não só sintaxe):**

1. `D:/1001.mp4` e `D:/edit/cut.mp4` **não servem** para validar reframe: são
   1080x1920 e 2160x3840, **já verticais**. Reframe 9:16 → 9:16 é no-op e não
   prova nada. Buscado material 16:9 real no disco.
2. `D:/Curso TDAH Para pais/20260606_143647.mp4` (3840x2160, talking-head):
   rodou limpo, mas `crop_x_range: 0`. **Não é bug** — instrumentado o
   detector: o rosto oscila numa faixa de 168px, dentro do safe zone de 304px,
   então o "tripé pesado" segura de propósito. Comportamento correto.
3. Para provar o tracking, gerado um clipe 16:9 a partir da **mesma filmagem
   real** com a janela de crop panorâmica (rosto real cruzando o quadro):
   `crop_x_range: 1194px` de 1314px disponíveis — a câmera percorre quase todo
   o curso seguindo o rosto.
4. **Medida objetiva:** deslocamento médio do rosto em relação ao centro caiu de
   **24,7pp (entrada) → 8,9pp (saída)**, com o rosto exatamente em 50,0% em
   quadros onde a entrada o tinha a 20%/21%. Conferido também em contact sheet
   lado a lado.
5. Saída íntegra: 1080x1920 H.264 + AAC, 601 frames, `ffmpeg -f null` sem erros.

Comandos usados:

```
uv sync --extra reframe
uv run python helpers/reframe.py <video.mp4> --edit-dir <dir> --aspect-ratio 9:16
uv run python helpers/reframe.py <video.mp4> -o out.mp4 --force-strategy TRACK
```

#### B4 — Resultado (2026-08-19)

- **`helpers/scene_detection.py`** criado — porta adaptada:
  - motor padrão trocado de TransNetV2 para **PySceneDetect** (`ContentDetector`):
    puro Python + OpenCV, zero download de modelo, instala em segundos. O
    original do OpenShorts inverte essa prioridade (TransNetV2 como padrão,
    PySceneDetect como fallback) porque roda em produção a serviço de muitos
    usuários, onde a precisão extra em cortes rápidos/flashes compensa o peso;
    o Prisma é local e de uso ocasional, então o padrão mais leve é a escolha
    certa aqui.
  - **TransNetV2 mantido como opt-in** (`--engine transnetv2` ou
    `SCENE_ENGINE=transnetv2`), com fallback automático para PySceneDetect em
    qualquer falha — mesma garantia do original ("uma falha de detecção nunca
    derruba o job"). Requer `uv sync --extra scenes-neural` (torch +
    `transnetv2-pytorch`, confirmado publicado no PyPI).
  - `_merge_short_scenes` portado sem alteração de lógica (só docstring/print
    em português) — funde cenas abaixo de `SCENE_MIN_SEC` num vizinho para
    evitar rajadas de "câmera pulando" no reframe.
  - adicionado `main()`/CLI que o original não tinha (é usado só como módulo
    internamente no OpenShorts) — segue o padrão dos outros helpers do Prisma:
    argparse, JSON em stdout.
- **`scenedetect` adicionado à dependência base** do `pyproject.toml` (leve,
  sem modelo); `transnetv2-pytorch` + `torch` como extra opcional
  `scenes-neural`.
- **Bug corrigido durante o teste**: `Fraction` (tipo que `PySceneDetect`
  usa para fps) não é serializável em JSON — `json.dumps` falhava no `main()`.
  Corrigido convertendo para `float` antes de serializar.
- **Testado com vídeo real**: `D:/edit/cut.mp4` (152.8s, 4584 frames,
  confirmado via `open_video().duration` — bate com a EDL do projeto 1001) →
  `{"fps": 30.0, "count": 0, "scenes": []}`. Zero cenas é o resultado correto,
  não uma falha: esse corte é um único take estático (a EDL já documenta isso
  como range única 0.5→153.3s), então não há corte de câmera para detectar.
  Decodificação e serialização confirmadas funcionando; teste positivo (vídeo
  com múltiplos cortes reais) fica pendente para quando B3/B5 precisarem
  encadear este módulo.

#### B6 — Resultado (2026-08-19)

- **`NOTICE`** criado na raiz da skill — texto integral da licença MIT do
  OpenShorts (copyright OpenShorts 2024), com nota explícita de que o
  diretório `cloud/` (licença comercial separada) não foi usado.
- **`CREDITS.md`** criado — tabela arquivo-a-arquivo mapeando cada helper do
  Prisma ao arquivo original do OpenShorts, com a adaptação feita em cada um.
  Atualizado à medida que B3/B5 avançam (a linha do `reframe.py` ainda está
  "em progresso" — será fechada quando o arquivo pousar).

#### B5 — Resultado (2026-08-19)

- **`helpers/clip_finder.py`** criado. Fonte original (`clip_selection.py`) é
  standalone, stdlib-only — mesmo assim a porta não foi um copy-paste:
  - **Cortada a metade dependente de Gemini** (`MODEL_PRICES`,
    `lookup_model_prices`): o original é a metade "pura" de um pipeline que
    depois manda os windows para um LLM julgar "qual é o melhor momento
    viral". O Prisma preserva a regra de ouro de B ("Gemini opcional, jamais
    obrigatório") — este módulo produz o shortlist de janelas candidatas
    (contagem/duração calibradas, snapadas em limite de palavra real) e para
    aí. Ranquear por "viralidade" fica para quem quiser plugar um passo de
    LLM por cima da saída JSON depois — não é obrigatório para o valor
    central (decupagem automática).
  - **Adaptado ao schema real de transcrição do Prisma**: o original espera
    `{"segments": [...]}` e palavras `{"w","s","e"}`; o Prisma grava
    `<edit>/transcripts/<stem>.json` como `{"words": [...]}`, uma lista achatada
    de entradas `{text, start, end, type, speaker_id}` (`type` é "word" ou
    "spacing" — ver `transcribe.py`). `_load_prisma_transcript()` foi escrito
    do zero para essa conversão (agrupa palavras em segmentos por pausa
    ≥0.6s, igual à heurística que `pack_transcripts.py` já usa). A lógica
    portada (`build_transcript_windows`, `snap_clip_to_words`,
    `clip_count_targets`, `clip_duration_bounds`) manteve o comportamento
    original.
  - **Bug corrigido durante o teste**: assumi errado que o transcript do
    Prisma era uma lista no nível raiz do JSON (copiando a descrição de
    memória, não lendo o arquivo real primeiro). `D:/edit/transcripts/cut.json`
    é na verdade um dict com chave `"words"`. Corrigido em
    `_load_prisma_transcript` e na docstring do módulo depois de inspecionar
    o arquivo real com Python.
- **Testado com transcrição real**: `D:/edit/cut.mp4` +
  `D:/edit/transcripts/cut.json` (vídeo de avaliação de TDAH, 152.8s) →
  2 clipes candidatos, 44.8s e 45.0s (dentro do range pedido 20-45s),
  ambos com texto coerente (sem corte no meio de frase) — confirma que o
  snap por palavra e o agrupamento por pausa funcionam no material real do
  projeto, não só em dado sintético.

### ÉPICO C — Diarização (AutoSubs)
| Story | Entrega | Critério de aceite | Status |
|---|---|---|---|
| **C1** | Diarização opcional | Falantes rotulados em áudio com 2+ vozes | ✅ **CONCLUÍDO** — ver abaixo |
| **C2** | Estilo de legenda por falante | Só ativa quando a diarização encontra >1 falante | ✅ **CONCLUÍDO** — ver abaixo |

**Prioridade baixa** até existir um projeto com entrevista/podcast. Para talking
head solo — todo o material desta sessão — não entrega valor direto, mas fica
pronto para quando surgir.

#### C — Desvio de plano decidido em execução (2026-08-19)

O crate de diarização do AutoSubs (`AutoSubs-App/src-tauri/crates/diarize/`) é
**Rust** (Tauri sidecar, com `kaldi-native-fbank` vendorizado em C++ por baixo).
Todo o resto do Épico B portou Python→Python; não há Python para adaptar aqui —
"portar" significaria compilar um crate Rust dentro de uma skill Python ou
reescrever a lógica do zero, nenhum dos dois é uma "porta adaptada" honesta.

**Decisão (perguntada ao usuário, confirmada):** entregar o mesmo resultado que
C1/C2 pedem — falantes rotulados, legenda com estilo por falante — via
**`pyannote.audio`** (MIT, 10.4k estrelas, ativo em 2026-08-04, confirmado via
API do GitHub), a biblioteca Python de fato usada para diarização. Não é uma
porta de código do AutoSubs; é uma integração nova que resolve a mesma lacuna.

#### C1 — Resultado (2026-08-19)

- **`helpers/diarize.py`** criado — módulo novo, não porta. Lê o transcript
  JSON já existente (gerado por `transcribe.py`), roda diarização no áudio do
  vídeo, e reescreve `speaker_id` de cada palavra no lugar. `transcribe.py`
  em si **não foi alterado** — o caminho padrão continua 100% offline, sem
  conta em lugar nenhum.
- **Opt-in por dois motivos, não um**: (1) peso morto para o caso comum
  (talking head solo — todo material desta sessão) já que o transcript
  default já marca tudo como `speaker_0`; (2) o pipeline pré-treinado do
  pyannote é *gated* no HuggingFace — o código é MIT, mas baixar os pesos na
  primeira vez exige conta gratuita e aceitar os termos do modelo. Isso é
  exatamente o tipo de "segunda coisa para se cadastrar" que a skill evita
  tornar obrigatória, então só acontece se o usuário pedir `--diarize`
  explicitamente (extra `uv sync --extra diarize` + token via `--hf-token`
  ou `HF_TOKEN`).
- `pyannote.audio` adicionado como extra opcional `diarize` no
  `pyproject.toml` (puxa torch + modelos pré-treinados, por isso opt-in).

#### C2 — Resultado (2026-08-19)

- **`helpers/captions_for_remotion.py`** estendido (não recriado): ambos os
  caminhos de geração de legenda (`captions_from_transcript` — modo
  preferido, e `build_captions` — fallback via EDL) agora checam se o
  transcript tem 2+ `speaker_id` distintos; só então incluem `speakerId` em
  cada `Caption`. Com 1 falante só (o padrão), a saída é **byte-idêntica** ao
  formato anterior — nada quebra para quem nunca usar diarização.
- **Testado dos dois lados**:
  - Caminho padrão (`D:/edit/transcripts/cut.json`, sem diarização): 402
    captions, `speakerId` ausente em 100% delas — confirma que nada mudou
    para o caso comum.
  - Caminho multi-falante (transcript sintético com 2 `speaker_id`
    alternados, derivado do mesmo arquivo real): 402 captions, `speakerId`
    presente em 100% delas, valores corretos (`speaker_0`/`speaker_1`)
    verificados em amostras específicas do array.

### ÉPICO D — Publicação (Postiz via API)
| Story | Entrega | Critério de aceite | Status |
|---|---|---|---|
| **D1** | Publicação via **API HTTP** do Postiz | Vídeo entregue chega à rede; **zero código AGPL no repo** | ✅ **CONCLUÍDO** — ver abaixo |

#### D1 — Resultado (2026-08-19)

- **`helpers/publish.py`** criado — integração via HTTP, **zero código do
  Postiz copiado**. Postiz (`gitroomhq/postiz-app`) é AGPL-3.0; o arquivo só
  contém chamadas contra o contrato REST público e documentado
  (`docs.postiz.com/public-api`), a mesma superfície que qualquer usuário do
  Postiz chamaria do próprio script.
- **Endpoints confirmados na documentação oficial** (não assumidos): `POST
  /upload` (multipart, retorna `{id, path}`), `GET /integrations`, `GET
  /is-connected`, `POST /posts` (schema `{type, date, shortLink, tags,
  posts: [{integration: {id}, value: [{content, image}], settings}]}`).
  Base URL configurável (`--base-url`/`POSTIZ_BASE_URL`) para diferenciar
  Postiz Cloud de instância self-hosted.
- **Fluxo em 3 passos**: upload do vídeo renderizado → resolução do canal
  (por id, identifier tipo `"instagram"`, ou nome — case-insensitive) →
  criação do post (`now`/`schedule`/`draft`).
- **Chave de API no mesmo padrão** dos outros helpers que chamam serviço
  externo (`pexels_search.py`): `.env` na raiz do repo ou variável de
  ambiente `POSTIZ_API_KEY`, nunca hardcoded.
- **Testado sem precisar de conta Postiz real**: `--help` e erro claro sem
  chave confirmados via CLI; lógica pura (`resolve_integration` nos 3 modos
  de match, e o corpo JSON exato que `create_post` monta) testada com
  `unittest.mock` substituindo `requests.get`/`requests.post` — o corpo
  gerado bate campo a campo com o schema `CreatePostRequest` documentado.
  Uma chamada de ponta a ponta contra a API real fica pendente para quando
  houver uma conta Postiz conectada a um canal de verdade.

### ÉPICO E — Ideias do HyperFrames
Apache-2.0. Portar **conceitos** para o pipeline ffmpeg/Remotion do Prisma —
não migrar de motor.

| Story | Entrega | Critério de aceite | Status |
|---|---|---|---|
| **E1** | Cadeia de áudio completa (EQ/comp/limiter/gate) | Medida antes/depois por banda, como no carve | ✅ **CONCLUÍDO** — ver abaixo |
| **E2** | Envelopes de automação de volume | Volume variável ao longo do tempo, não fixo | ✅ **CONCLUÍDO** — ver abaixo |
| **E3** | `media_ledger.py` — manifest de assets | Reuso entre projetos com proveniência rastreável | ✅ **CONCLUÍDO** — ver abaixo |
| **E4** | Transições além do flash | Ao menos 2 novas, verificadas em still | ✅ **CONCLUÍDO** — ver abaixo |

**Já entregue desta fonte:** `music_carve.py` (voiceover carve) — feito nesta
sessão, com resultado medido.

#### E — Desvio de plano decidido em execução (2026-08-19)

Confirmado ao ler o código-fonte real do HyperFrames: a cadeia de áudio
(`packages/core/src/audio/audioFxGraph.ts` e ~30 arquivos ao redor) e os
envelopes (`packages/engine/src/services/audioVolumeEnvelope.ts`) são
implementados como grafos Web Audio API rodando dentro do runtime Puppeteer
deles — TypeScript sem equivalente ffmpeg para traduzir linha a linha, a
mesma situação do reframe (B3) com o `main.py`, só que aqui não há sequer um
caminho de porta parcial: é outro motor de áudio inteiro. Perguntei e você
confirmou: **implementar do zero em ffmpeg**, inspirado nos alvos numéricos
que a documentação deles descreve (ducking ~12dB sob a voz, trilha abaixo de
-18dB), não no código.

#### E1 — Resultado (2026-08-19)

- **`helpers/audio_chain.py`** criado — cadeia gate → EQ → compressor →
  limiter (+ reverb opcional), ordem fixa documentada (gate antes do
  compressor pra não bombear no ruído de sala; EQ antes da compressão pra
  não competir com os movimentos de ganho dela; limiter sempre por último,
  nunca ferramenta de nível).
  - Filtros nativos do ffmpeg confirmados via `ffmpeg -filters` antes de
    escrever qualquer linha: `agate`, `equalizer` (peaking, dois polos),
    `acompressor`, `alimiter`, `aecho` (para o reverb).
  - **Reverb é deliberadamente `aecho` (slap-echo curto), não convolução
    verdadeira** — o ffmpeg não tem filtro de convolução por IR utilizável
    sem embarcar um arquivo de resposta ao impulso. Documentado no
    docstring como limitação honesta, não escondido.
  - `--measure` reaproveita a mesma disciplina do `music_carve.py`
    (`--measure` dele): mostra nível geral + energia por banda antes de
    confiar em qualquer parâmetro default.
- **Bug real encontrado e corrigido durante o teste** (não só sintaxe):
  com `--reverb`, o nível médio despencava de -17dB para -38dB — um "tail
  sutil" quebrando a mixagem inteira. Isolado sistematicamente (testei
  `aecho` sozinho em janelas de tempo diferentes até notar que o áudio cru
  era uniforme, descartando "é silêncio real no trecho") até achar a causa:
  a assinatura do `aecho` é `in_gain:out_gain:delays:decays`, e eu tinha
  passado `reverb_mix` no lugar de `out_gain` — atenuando o sinal inteiro
  (seco + molhado) em vez de só a cauda do eco. Corrigido fixando
  `in_gain=out_gain=1.0` e movendo o controle de mix para `decays` (que
  escala só os taps do eco). Reverificado: -17.0dB com `--reverb-mix 0.1`
  (igual ao caminho sem reverb) e -16.2dB com `0.4` (mais presente, sem
  quebrar).
- **Testado no áudio real do projeto** (`D:/edit/cut.mp4`): `--measure`
  reproduz exatamente os números já documentados em `music_carve.py`
  (mesma fonte, medição consistente); cadeia completa sem reverb: -17.2dB
  → -17.0dB (limiter respeitando o teto -1dB, `max_volume` de -0.8 para
  -0.2dB).

#### E3 — Resultado (2026-08-19)

- **`helpers/media_ledger.py`** criado — manifest JSON plano (`media_ledger.json`
  na raiz da skill, fora de qualquer diretório de projeto, porque o ponto
  inteiro é reuso ENTRE projetos), uma entrada por arquivo baixado, chaveada
  pelo **SHA-256 do próprio arquivo** (não pela query nem pelo nome) — duas
  buscas diferentes que resolvem pro mesmo asset viram uma entrada só, com
  `used_by` acumulando os projetos que a reusaram.
  - Comandos: `record` (grava/atualiza uso), `find --query`/`find --hash`
    (checa antes de gastar uma chamada de API de novo), `use` (marca reuso
    num projeto sem regravar o arquivo), `list`.
  - Desenhado para plugar nos helpers de asset existentes
    (`pexels_search.py`, `wikimedia_images.py`, `treblo_music.py`, etc.) sem
    reescrevê-los — hoje eles imprimem crédito/licença no console e
    esquecem; `record()` é uma chamada extra depois de salvar o arquivo.
- **Testado com um arquivo real do projeto** (`D:/edit/trilha_v2.mp3` como
  asset de teste): `record` com `--project D:/edit` → entrada criada;
  `record` de novo com `--project D:/outro_projeto` → **mesma entrada**
  (mesmo `hash`, mesmo `first_seen`), `used_by` cresceu para os dois
  projetos sem duplicar — dedupe por conteúdo confirmado, não só aceito
  sem erro. `find --query` e `list` confirmados retornando a entrada
  correta. Dados de teste removidos do ledger antes de finalizar (não é
  para o `media_ledger.json` real do usuário conter entrada fictícia).

#### E4 — Resultado (2026-08-19)

- **`assets/shortform/src/CustomGraphics.tsx`** estendido (não recriado):
  `CutFlash` ganhou um campo opcional `type?: 'flash' | 'whip-pan' | 'glitch'`
  — omitir o campo mantém o flash original exatamente como estava (nenhum
  `edit-data.json` existente quebra). `CutFlashes` despacha por `type` para
  três componentes (`Flash` = o original, extraído sem mudança de lógica;
  `WhipPan` e `Glitch`, novos).
  - **Restrição de arquitetura descoberta e respeitada**: `CustomGraphics`
    é montado como overlay ACIMA da camada de vídeo (`Main.tsx`), sem
    acesso ao `OffthreadVideo` por baixo — não dá para de fato desfocar ou
    deslocar o vídeo a partir daqui. Minha primeira versão de `WhipPan`
    tentava `filter: blur()` + `transform: translateX()` num
    `AbsoluteFill` vazio (sem pixel nenhum debaixo pra manipular) — não
    fazia nada visível além das streak lines. Corrigido para ambas as
    transições serem overlays 100% aditivos (linhas de movimento para o
    whip-pan, bandas ciano/magenta para o glitch), no mesmo espírito do
    flash original, que já funciona dessa forma.
  - **Glitch determinístico**, não aleatório: as bandas usam um seed
    derivado do frame do corte (`Math.round(c)`), não `Math.random()` — a
    mesma transição no mesmo corte renderiza pixel-idêntica em toda run,
    o que um teste de still-frame depende de ser verdade.
  - Créditado como ideia (não porta): o original do HyperFrames
    (`packages/shader-transitions`) é um shader WebGL rodando dentro do
    runtime deles; aqui é CSS/React puro, construído do zero para o que o
    contexto de render Chromium do Remotion oferece.
- **Testado com render still de verdade** (`npx remotion still`), não só
  `tsc --noEmit`: `edit-data.json` de teste com um `transitions[]` de 3
  entradas (uma por tipo) sobre `D:/edit/cut.mp4` copiado temporariamente
  para `public/`. Três frames renderizados e inspecionados visualmente —
  `flash` idêntico ao comportamento pré-existente (regressão zero),
  `whip-pan` mostra linhas de movimento diagonais nítidas cruzando o
  quadro, `glitch` mostra bandas ciano/magenta deslocadas horizontalmente,
  visualmente distinto dos outros dois. `npx tsc --noEmit` também limpo.
  Arquivo de vídeo de teste e `node_modules` temporário removidos, e
  `edit-data.json` revertido ao estado de template original depois do
  teste.

#### E2 — Resultado (2026-08-19)

- **`helpers/volume_envelope.py`** criado — aplica uma curva de volume por
  keyframes `(tempo_s, nível 0-1)` a qualquer trilha de áudio, em vez do
  único número fixo que `editData.soundtrack.volume` guarda hoje
  (`assets/preview/app.js`, fader `S.musicVol`). Um envelope com 1 keyframe
  reproduz exatamente o comportamento fixo atual — não quebra nada em uso.
  - Interpolação linear entre keyframes como **uma única expressão**
    ffmpeg (`if(lt(t,...), ..., if(lt(t,...), ...))`, aninhada do segmento
    mais interno pro mais externo) avaliada por frame (`eval=frame`) — uma
    curva contínua de verdade, não um degrau de `afade`/`enable=between()`
    encadeados.
  - Antes do primeiro keyframe e depois do último: segura o nível da ponta
    (sem fade artificial de/para silêncio que ninguém pediu).
- **Testado com a trilha real do projeto** (`D:/edit/trilha_v2.mp3`,
  153.3s — mesma duração do vídeo): envelope 0s→0.05, 8s→0.22, 140s→0.22,
  153s→0.02 (intro baixa, corpo alto, saída baixa). Medido em 3 janelas
  do arquivo de saída: início -46.8dB, meio -36.1dB (+10.7dB, batendo com
  a razão 0.22/0.05 esperada), fim -47.6dB — a curva foi realmente aplicada,
  não só aceita sem erro. Caso degenerado (1 keyframe = nível fixo) também
  testado e confirmado equivalente ao comportamento atual do fader.

---

## 4. Sequência recomendada

```
1. ÉPICO A (A1–A5, A7)     — consistência de marca, risco baixo
2. B1                       — auditoria de licença ANTES de qualquer código
3. B2 (reframe)             — a maior lacuna real
4. B3 + B4                  — decupagem completa
5. A6                       — renomear diretório (decisão à parte, com backup)
6. C / D                    — quando houver caso de uso concreto
```

**Por que A antes de B:** renomear depois de importar código novo dobra a
superfície da renomeação.

**Por que B1 antes de B2:** copiar código sob licença não verificada é o tipo de
erro que não se desfaz.

---

## 5. O que NÃO fazer

- **Não integrar MinIO** — arquivado (abril/2026) e AGPL.
- **Não copiar código do Postiz ou Mixpost** — AGPL contamina o Prisma. API sim.
- **Não adotar Celery/Temporal agora** — over-engineering para 1 vídeo/vez.
- **Não portar MoneyPrinterTurbo** — gera vídeo do zero; o Prisma edita material
  do usuário. Produtos opostos.
- **Não tornar o Gemini obrigatório** — a Fase 1 offline sem chave é um ativo.
- **Não copiar código do OpenReel** — TypeScript/browser, arquitetura
  incompatível. Só referência de UX.
- **Não adotar OpenCut agora** — 85k estrelas medem a promessa, não o código:
  151 arquivos, reescrita parada há 18 dias, e a versão estável (`opencut-classic`)
  está arquivada.
- **Não migrar o Prisma para HyperFrames** — jogaria fora 1.821 linhas de template
  funcionando e a verificação numérica, que é o diferencial do Prisma. Colher
  ideias, sim; trocar de motor, não.

---

## 6. Pendência herdada (não esquecer)

Do `EVOLUCAO-OPUS.md`, ainda aberto:

- **P1 — longform:** template com 3 arquivos vs 8 do shortform; nunca exercitado
  com material real. O ÉPICO B ajuda (reframe serve à decupagem), mas não fecha.
- **P3 — B-roll semi-automático:** `pexels_search.py` existe, curadoria é manual.

— Maestro, conduzindo o impossível 🎼
