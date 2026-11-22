# Biblioteca de modelos de edição: design

Data: 2026-11-22 · Estado: rascunho para aprovação

## 1. Intenção

Hoje o Prisma já executa 47 dos 57 tipos de edição levantados
(`Prisma-Suite/docs/analises/2026-11-21-tipos-de-edicao.md`), mas eles estão **espalhados**:
speed ramp no `speed_ramp`, velocity edit no `beat_edit`, match cut no `cinema_edit`,
transições nos elementos do preview e no registry do HyperFrames. Não existe um lugar onde se
diga "quero um velocity edit", se **veja** como ele fica e ele seja **aplicado igual** em todo
vídeo.

A biblioteca é esse lugar, com dois níveis:

- **Tipo de edição**: uma técnica nomeada (speed ramp, whip pan, zoom punch…).
- **Estilo**: uma combinação de tipos com regras e "sinais" sem os quais deixa de ser aquele
  estilo (ex.: "montagem na batida", "Reel de fala com B-roll em tela cheia").

Cada modelo tem uma **ficha** (o que é, quando usar, quando não usar), uma **receita** que o
Prisma aplica com um comando e uma **demo** de poucos segundos, renderizada, para escolher
vendo, e para mostrar ao cliente.

## 2. Objetivos, não-objetivos, anti-objetivos

**Objetivos**
- O usuário (ou o agente) pede um modelo pelo nome e o Prisma aplica a mesma receita sempre.
- Uma galeria visual com uma demo por modelo, aberta no navegador.
- O catálogo nunca fica desatualizado: um teste falha se a receita apontar para um campo ou
  preset que não existe.
- Os itens que faltam ou estão pela metade no catálogo de tipos viram a fila de construção,
  cada um como um modelo novo.

**Não-objetivos (v1)**
- Nenhum motor de render novo: a receita só escreve no formato que as ferramentas atuais já
  leem.
- O agente não escolhe o modelo sozinho: quem escolhe é a pessoa. O agente pode sugerir.
- Não substitui os portões de fase: a receita entra na Fase 2, depois do corte aprovado.
- Não copia código do skill-reel (sem licença): as ideias dele entram depois, reimplementadas.

**Anti-objetivos (é falha mesmo que "funcione")**
- Uma receita que empilha transições. A regra já medida vale aqui: uma transição primária
  e **no máximo 3 acentos contados** por vídeo (`cinema-motion.md`, `direction.md`).
- Uma receita que altera em silêncio uma camada já aprovada. Toda aplicação mostra o diff
  e guarda backup.
- Uma demo com material de cliente publicada fora do disco local ou do OneDrive privado.

## 3. Restrições

- Repositório Prisma público: fichas e receitas entram no git; **demos não** (vídeo pesado e,
  possivelmente, material de cliente).
- Windows, ffmpeg, Node, HyperFrames fixo em 0.8.93 (`hfkit/project.py`).
- Perfis de cliente continuam mandando no gosto (ex.: Deocar proíbe grão). A receita não
  sobrescreve regra de perfil.

## 4. Abordagens consideradas

| Abordagem | Troca | Escolha |
|---|---|---|
| Só fichas para consulta | barata; o agente remonta à mão a cada vez, e o "mesmo" modelo sai diferente | não |
| Receitas que aplicam | reproduzível e testável; sem ver antes de escolher | não sozinha |
| **Receitas que aplicam, com demo visual** | um render por modelo; escolha visual e material para o cliente | **escolhida pelo usuário** |

Níveis: o usuário escolheu **tipos e estilos** desde o início (depois da análise do skill-reel).

## 5. Como funciona

### 5.1 Onde mora

```
<prisma>/modelos/
  tipos/<slug>/
    MODELO.md        ficha: nome, família, o que é, quando usar, quando NÃO usar, contenção, origem
    modelo.json      receita (5.2)
  estilos/<slug>/
    MODELO.md        ficha + os "sinais" (sem eles não é este estilo)
    modelo.json      tipos que o compõem + regras + valores-padrão
  _demo/
    demo.json        de onde vem o material das demos (5.5); caminhos ficam FORA do git
```

Galeria (fora do git, privada): `$PRISMA_MODELOS_GALERIA`, senão
`$OneDrive/Prisma/modelos-galeria/` (mesmo padrão do backup dos perfis), com
`<slug>/demo.mp4`, `poster.jpg`, `gates.json` e um `index.html`.

### 5.2 A receita (`modelo.json`)

Cada receita declara **em qual formato** ela escreve (o "anfitrião") e **o quê**:

- `host: "montagem"` → o `plan.json` do `beat_edit` (campos `transition`, `ramp`, `fx`,
  `speed` por plano; `default_*` no plano todo).
- `host: "reel-fala"` → **duas camadas**, porque hoje nenhum helper converte o estilo aprovado
  em `edit-data.json` (o agente escreve à mão, seguindo o `shortform.md`):
  1. `style`: o patch em `state.json.style`, o mesmo objeto que o perfil semeia (`seed`) e que
     a aba Estilo do preview salva (`elements`, `edit`, `headline`, `captions`, `accent`). O
     `apply` marca `awaitingStyle: true`, para a pessoa confirmar no preview.
  2. `edit_data`: o patch concreto, quando o `edit-data.json` já existe. Ex.: `zoomAuto` →
     `camera.pushIn`; `flashCut` → uma entrada em `transitions[]` em cada ponto de corte, lido
     de `segments.json`. O mapeamento de cada elemento é o que o `shortform.md` já descreve; a
     receita só o torna mecânico. *(Decisão minha: sem a camada 2, a receita do Reel de fala
     dependeria de o agente reescrever o edit-data igual toda vez, que é o problema que a
     biblioteca resolve.)*

Exemplo de tipo:

```json
{ "slug": "whip-pan", "nivel": "tipo", "familia": "transicao", "host": "montagem",
  "aplica": { "por_plano": { "transition": "whip-{dir}" } },
  "parametros": { "dir": { "valores": ["left","right","up","down"], "padrao": "left" } },
  "acento": true }
```

Exemplo de estilo:

```json
{ "slug": "montagem-na-batida", "nivel": "estilo", "host": "montagem",
  "tipos": ["transicao-velocidade", "whip-pan", "flash", "zoom-punch"],
  "regras": { "primaria": "transicao-velocidade", "max_acentos": 3 },
  "sinais": ["corte na batida", "velocidade é o padrão, não o efeito", "≤ 3 acentos contados"] }
```

`acento: true` marca as transições que contam para o limite de acentos. No host `montagem`, conta
cada plano com `transition` de acento; no `reel-fala`, cada entrada de `transitions[]` de tipo
acento. A transição primária do estilo não conta.

Um tipo pode mexer em vários campos de um trecho de planos. *(Decisão minha: o `velocity-edit` é
um **tipo** com receita de vários campos (rampas + `flash` + `shake` + `pulse`) aplicada a um
intervalo de planos, e não um estilo, porque não traz regras para o vídeo inteiro.)*

### 5.3 O comando: `helpers/modelos.py`

| Subcomando | O que faz |
|---|---|
| `list [--nivel tipo\|estilo] [--familia …]` | lista com status (✅ pronto · 🧪 sem demo) |
| `show <slug>` | ficha + receita + caminho da demo |
| `apply <slug> <plan.json\|edit-data.json> [--plano N…] [--param k=v]` | escreve a receita no arquivo; **backup** `<arquivo>.antes-<slug>-<data>`; imprime o diff; registra em `state.json.modelos[]`; recusa se passar de `max_acentos`; imprime as regras do perfil do cliente do projeto, se houver, para conferência |
| `demo <slug> [--force]` | renderiza a demo (5.5), roda `motion_gates render` nela e grava na galeria |
| `galeria [--abrir]` | gera o `index.html` (vídeo em loop, nome, família, quando usar, gates) |
| `check` | valida todas as receitas (5.6); também roda dentro do `tests/test_catalog.py` |

### 5.4 Primeiro lote (v1)

**Tipos (host `montagem`, todos com ferramenta pronta hoje):**
`speed-ramp` (`whip-slow`), `transicao-velocidade` (`speed-out` → `speed-in`),
`bullet-time` (`bullet`), `velocity-edit` (rampas + `flash` + `shake` + `pulse`: hoje só existe
em pedaços), `whip-pan`, `flash`, `zoom-through`, `rgb-split`, `shake-impacto`, `zoom-punch`
(`pulse`).

**Tipos (host `reel-fala`):** `zoom-nos-cortes` (`zoomCuts`), `push-in` (`zoomAuto`),
`flash-na-troca` (`flashCut`), `distorcao-na-troca` (`shaderCut`).

**Estilos:**
- `montagem-na-batida` (host `montagem`): o padrão dos reels SVR e Taycan.
- `reel-fala-broll` (host `reel-fala`): o "B-roll em tela cheia" do `shortform.md`, que é o
  padrão dos tours Deocar (headline mista, legenda scatter, zoom nos cortes, B-roll cover).

### 5.5 Demos

- **Montagem:** `beat_edit` com 3–4 takes de 2–4 s e um trecho de música com beat map
  (`beat_map`), renderizado em HyperFrames; 4–6 s, 1080×1920.
- **Reel de fala:** a fixture de 12 s da regressão da Fase 2 (`tests/fixture_phase2`),
  com a receita aplicada ao `edit-data.json` dela, renderizada com
  `render_phase2.py --skip-delivery`.
- O material vem de `modelos/_demo/demo.json`, que aponta para caminhos locais (decisão
  aberta, §7).
- Toda demo passa por `motion_gates.py render` (G0/G2) e o resultado vai para a galeria. Uma
  demo que reprova não entra na galeria.

### 5.6 O que o `check` garante

- Todo `modelo.json` tem `slug` igual ao nome da pasta, `nivel`, `host`, e um `MODELO.md` com
  as seções "O que é", "Quando usar", "Quando não usar", "Contenção".
- Valores de `transition`, `ramp` e `fx` existem no `beat_edit.py`/`speed_ramp.py`; elementos
  do `reel-fala` existem no vocabulário do `shortform.md`.
- Todo tipo citado por um estilo existe.
- O `tool-map.md` ganha a linha **Modelos de edição** (`modelos`).

### 5.7 Relação com perfil e com a Fase 2

- O perfil diz o **gosto** do cliente; o modelo diz a **técnica** ou o **estilo**. Os dois se
  somam: `seed` do perfil → `apply` do estilo → ajustes.
- O `apply` só roda com o corte aprovado (`state.json.phase` ≥ 2). Antes disso, recusa. No host
  `montagem` (um `plan.json` do `beat_edit`, que não passa pela Fase 1), não há essa trava.
- O gate de Estilo do preview pode, numa versão seguinte, listar os estilos da biblioteca. Fica
  fora da v1.

## 6. Fila depois da v1 (do catálogo de tipos)

L-cut alternado com J (no `render.py`), freeze frame, smash cut, mask transition / passar pelo
objeto, morph, recorte congelado com contorno, cross-cut, legenda que segue a boca, peças de
interface (HUD de filmadora, chat digitando, cursor no CTA, barra de progresso, leque, carimbo),
âncora por frase nas cenas HyperFrames e o estilo **VSL com interface animada**, recriado do
zero. Cada um entra como um modelo com demo.

## 7. Decisões do usuário

1. **Material das demos de montagem: clipes livres (Pexels) + uma faixa da Epidemic**
   (2026-11-22), para que as demos possam ser mostradas a qualquer cliente. Os clipes vêm por
   `pexels_search.py` e a faixa por `epidemic_music.py`, os dois registrados no `media_ledger`
   com licença e crédito. Os arquivos ficam em `$OneDrive/Prisma/modelos-galeria/_material/`,
   fora do git; o `modelos/_demo/demo.json` guarda só os IDs (Pexels, Epidemic), não os caminhos.
2. Estado: design aprovado pelo usuário em 2026-11-22.

## 8. Decisões minhas (para conferir)

- Galeria no OneDrive privado (`$OneDrive/Prisma/modelos-galeria/`), fora do git, como o backup
  dos perfis: pesada e talvez com material de cliente; dá para compartilhar um link com o cliente.
- Reel de fala com duas camadas de receita (`style` + `edit_data`), §5.2.
- `velocity-edit` é um tipo de vários campos, não um estilo, §5.2.
- `apply` sempre com backup e diff; recusa passar de 3 acentos.
- A aba Estilo do preview listar os estilos da biblioteca fica para depois da v1.

## 9. Deixado para quem constrói

Nomes internos de funções, formato do diff, o layout do `index.html` da galeria (simples:
grade de vídeos em loop), a ordem de construção dentro da v1.
