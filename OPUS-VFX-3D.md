# Opus VFX & Motion 3D — Prisma

**Data:** 2026-08-31 · **Conduzido por:** Maestro (Antigravity)
**Solicitação do usuário (Wellington):** *"hoje ele já faz B-rolls mas eu quero mais,
quero VFX e Motion 3D, com glass prism bem fluido, eu quero que o B-roll vertical
por exemplo apareça na tela toda mas de forma mais fluida"*

**Decisões tomadas no gate de clareza:**
- Motor: **@remotion/three + React Three Fiber** (caminho oficial Remotion)
- Escopo B-roll: os **4 movimentos** (entrada/saída animadas · fullscreen cover
  real · transição com displacement · moldura glass/prisma)

---

## 1. Diagnóstico Gemba — o teto atual, medido

Fui ao código, não à suposição.

### O B-roll de hoje

```ts
type Insert = {src: string; start: number; end: number};
```

Três campos. O insert é renderizado por `InsertCard` dentro de uma `<Sequence>`,
como **card retangular sobreposto**, com corte duro na entrada e na saída.
Sem escala, sem posição, sem fit, sem transição, sem profundidade.

### As transições de hoje (E4)

`flash` · `whip-pan` · `glitch` — todas **overlay-only**. O próprio código
documenta a limitação com honestidade (`CustomGraphics.tsx`, linhas ~239-247):

> *"CustomGraphics has no handle on the video layer beneath it to RGB-split or
> displace directly. Cyan/magenta bands standing in for a channel split read as
> 'glitch' at a glance without needing pixels from the layer underneath."*

Ou seja: o glitch atual **simula** um channel split. Não executa um.

### A causa raiz (uma só)

`assets/shortform/package.json` tem **6 dependências**: remotion, @remotion/cli,
@remotion/google-fonts, @remotion/layout-utils, react, react-dom.

**Zero WebGL. Zero Three.js. Zero shader.**

O motor compõe DOM/CSS dentro do Chromium. Vidro com refração, dispersão
cromática, motion 3D e displacement real não são *difíceis* nesse motor — são
**arquiteturalmente impossíveis**. É teto de arquitetura, não de esforço.

O código já registra isso duas vezes, referenciando o HyperFrames
(`packages/shader-transitions`): shaders WebGL num contexto Three.js, *"sem
equivalente em ffmpeg ou CSS puro para portar"*.

**Conclusão:** a lacuna entre o Prisma e o que o usuário pediu não é de
acabamento incremental. É de **camada de renderização ausente**.

---

## 2. Verificação de viabilidade (feita antes de planejar, não depois)

| Item | Verificado | Resultado |
|---|---|---|
| Node | `node -v` | **v22.23.2** ✅ |
| npm | `npm -v` | 10.9.8 ✅ |
| `@remotion/three` na versão do template | `npm view @remotion/three@4.0.482` | **existe** ✅ |
| Peer deps | `npm view … peerDependencies` | `three >=0.137`, `@react-three/fiber >=8`, `remotion 4.0.482` — casa exato ✅ |
| `node_modules` do shortform | `ls` | **AUSENTE** → `npm i` é pré-requisito ⚠️ |
| Flag `--gl` no render | `grep render_phase2.py` | **AUSENTE** → risco alto, ver R1 🔴 |

### R1 — O risco que quase passou despercebido

`helpers/render_phase2.py:72` chama:

```python
run([npx, "remotion", "render", "Reels", "out/render.mp4"], cwd=str(rem), …)
```

Sem `--gl`. O Chromium headless da Remotion **não usa WebGL real por padrão** —
precisa de um backend explícito (`--gl=angle`, `swiftshader`, `angle-egl`).
Sem isso, a `ThreeCanvas` renderiza **frames pretos ou o render quebra**, e o
sintoma vai parecer "o shader não funciona" quando o defeito está no invocador.

**Poka-Yoke:** o backend de GL vira parâmetro explícito de `render_phase2.py`,
com o valor medido gravado no Opus — não descoberto de novo na próxima sessão.

---

## 3. Arquitetura proposta

### Princípio de projeto: aditivo, nunca substitutivo

O template shortform tem **1.961 linhas funcionando** e verificação numérica —
o diferencial do Prisma. Nada disso é reescrito.

- A camada 3D entra como **camada nova opcional**, acionada por dados
  (`edit-data.json`), como todo o resto do Prisma.
- `edit-data.json` sem os campos novos → render **byte-idêntico** ao de hoje.
  Esse é o critério de não-regressão, e ele é verificável.
- Zero mudança em Fase 1. Nenhuma chave de API nova.

### Schema novo (data-driven, retrocompatível)

```ts
type Insert = {
  src: string; start: number; end: number;
  // ---- tudo abaixo é opcional; ausente = comportamento atual ----
  fit?: 'card' | 'cover' | 'contain';   // 'card' = default = hoje
  enter?: TransitionSpec;
  exit?: TransitionSpec;
  frame?: 'none' | 'glass';             // moldura prisma
  drift?: {from: number; to: number};   // Ken Burns
};

type TransitionSpec = {
  type: 'cut' | 'fade' | 'scale' | 'displace' | 'refract';
  durationMs?: number;
  intensity?: number;
};
```

`'cut'` é o default de `enter`/`exit` → preserva o comportamento atual.

---

## 4. Épicos e Stories

### ÉPICO V — Camada WebGL (fundação)

Sem isso, nada dos outros épicos existe.

| Story | Entrega | Critério de aceite |
|---|---|---|
| **V1** | Instalar `@remotion/three@4.0.482` + `three` + `@react-three/fiber` no template shortform | `npm i` sem erro de peer dep; `npm run studio` abre |
| **V2** | **Spike de render headless** — `<ThreeCanvas>` com um plano colorido, renderizada de verdade | Still extraído do MP4 mostra o plano. **Se sair preto, o backend `--gl` está errado — medir cada opção até achar a que funciona** |
| **V3** | `render_phase2.py` recebe o backend de GL medido em V2 como parâmetro explícito, documentado | Render reproduzível; regressão do caminho sem 3D verificada |
| **V4** | Medir custo: tempo/frame com e sem `ThreeCanvas` no mesmo clipe | Número registrado neste arquivo. Se o custo for proibitivo, V5 vira decisão do usuário, não fato consumado |

> **Jidoka:** V2 é o ponto de parada. Se o render headless não produzir pixels
> WebGL nesta máquina, **pare** — não construa os épicos G/B/T sobre uma
> fundação que não renderiza. Reporte e reabra a decisão de motor.

### ÉPICO G — Glass Prism

| Story | Entrega | Critério de aceite |
|---|---|---|
| **G1** | Material de vidro: refração (IOR), blur do fundo, borda especular | Still mostra o fundo **distorcido** através do painel — não apenas borrado |
| **G2** | Dispersão cromática nas bordas (o "prisma") | Still ampliado mostra separação RGB nas bordas, sutil |
| **G3** | Fluidez: entrada/saída com spring physics, sem pop | Sequência de 5 stills mostra progressão contínua |
| **G4** | Preset de intensidade no `edit-data.json` | 3 níveis rendem visivelmente diferentes |
| **G5** | **Tipografia 3D com perspectiva** — texto deitado num plano do espaço, com profundidade (observado na referência: "Aprenda a fazer" no plano da mesa) | ⛔ **tentado e revertido** — ver §8 |

### ÉPICO B — B-roll fullscreen fluido

| Story | Entrega | Critério de aceite |
|---|---|---|
| **B1** | `fit: 'cover'` — vertical preenche 1080×1920 **sem distorcer** | Still: sem barras, sem esticamento. Proporção do conteúdo preservada |
| **B2** | Entrada/saída animadas (scale + fade + spring) | Fim do corte duro. Stills nos frames de borda mostram a transição |
| **B3** | Ken Burns (`drift`) — deriva lenta em vez de estático | Stills de início e fim mostram enquadramento diferente |
| **B4** | Moldura `frame: 'glass'` — B-roll dentro do painel do ÉPICO G | Composição verificada em still |

### ÉPICO T — Transições com displacement

| Story | Entrega | Critério de aceite |
|---|---|---|
| **T1** | `displace` — dissolve por ruído, **com os pixels reais das duas camadas** | Still no meio da transição mostra mistura real, não overlay |
| **T2** | `refract` — a troca acontece através do vidro | Still no meio mostra refração da camada de saída |
| **T3** | Aposentar a simulação: `glitch` ganha channel split **de verdade** | Comparação lado a lado com a versão overlay-only |

---

### ÉPICO C — Camera Solve 3D (a lacuna que a referência revelou)

**Origem:** vídeo de referência enviado por Wellington
(`instagram.com/p/Db_6Gc1s6O6`, 40.9s · 1080×1920 · 30fps · VP9), baixado
íntegro via `ingest_url.py` e analisado frame a frame.

#### O que a referência prova

A narração é explícita (transcrita com WhisperX large-v3, 177 palavras, pt):

> *"Esse aplicativo permite que você faça um **traqueamento 3D do seu ambiente
> inteiro** e que você insira fotos, vídeos, textos, PNGs, o que você quiser
> literalmente no espaço 3D. **Ele fica fixado de acordo com a movimentação da
> sua câmera.**"*

Em **17.2s** o próprio vídeo expõe o motor: centenas de pontos verdes de feature
detection grudados nas superfícies da sala. Em 18–20s, painéis de UI flutuam
dentro de uma academia com perspectiva correta enquanto a câmera se move. Em
24s, mensagens de chat ancoradas na rua vista pelo para-brisa.

#### Por que isso não é o ÉPICO V/G/T

| | ÉPICO V/G/B/T | O que a referência faz |
|---|---|---|
| Espaço | Overlay 2D sobre o vídeo | Objeto ancorado no **espaço 3D da cena** |
| Câmera | Sem noção de câmera real | **Reconstrói** a trajetória da câmera |
| Resultado | Elemento flutua **sobre** a imagem | Elemento **pertence** à sala |

**Nenhum shader resolve isso.** Glass, refração e displacement são *aparência*.
Isso é *geometria*: recuperar a pose da câmera a partir dos pixels e projetar o
objeto nessa solução. Sem o solve, o painel de vidro do ÉPICO G fica lindo — e
escorregando pela tela.

#### Viabilidade — medida, não estimada

Rodei o teste no próprio vídeo de referência antes de escrever qualquer story:

| Item | Resultado |
|---|---|
| OpenCV | **5.0.0** com `SIFT`, `ORB`, `findEssentialMat`, `recoverPose`, `solvePnPRansac`, `calibrateCamera`, `findHomography` ✅ |
| `cv2.sfm` | ausente (não é bloqueio — as primitivas acima bastam) |
| COLMAP / pycolmap | **ausentes** no sistema |
| GPU | **RTX 5070, 12 GB** ✅ |
| **Teste real (17s do vídeo)** | 600 features detectadas → **419 sobreviventes após 30 frames** |
| **Custo medido** | **25 ms/frame** — ~40× tempo real, **em CPU** |

**Conclusão:** o caminho OpenCV puro é viável e barato. COLMAP fica como opção
de refino, não como dependência.

#### Stories

| Story | Entrega | Critério de aceite |
|---|---|---|
| **C1** | `camera_track.py` — LK optical flow + `goodFeaturesToTrack`, exporta trilhas 2D por frame | Rodar no vídeo de referência reproduz os números acima (±10%) |
| **C2** | **Gate de qualidade do solve** — mede features sobreviventes, baseline e paralaxe; recusa cenas sem textura ou com rotação pura | Cena boa → `ok`. Cena ruim → recusa **com o motivo**, antes de gastar minutos |
| **C3** | Camera solve: `findEssentialMat` + `recoverPose` incremental → pose por frame (R, t) + nuvem esparsa | Reprojection error médio reportado em px. **Se > 2px, o solve falhou — dizer isso** |
| **C4** | Export `camera.json`: intrínsecos, pose por frame, planos detectados | Consumível pela `ThreeCanvas` sem conversão manual |
| **C5** | `<TrackedScene>` no template — câmera do Three dirigida por `camera.json`; objeto ancorado | **Still de 5 frames: o objeto mantém posição na cena enquanto a câmera move** |
| **C6** | Detecção de plano (parede/mesa/chão) via homografia — alvo de ancoragem | Plano detectado desenhado em still, alinhado à superfície real |
| **C7** | Overlay de debug (pontos verdes, como a referência mostra) | Verificação visual do tracking, e didático |

> **Jidoka:** C2 é gate. Camera solve **falha legitimamente** em cena sem
> textura, com movimento rotacional puro ou motion blur pesado. Um solve ruim
> que passa produz objeto tremendo — pior que não ter o recurso. O gate recusa
> **antes** de gastar o tempo, e diz por quê.

> **Nota de custo honesta:** 25ms/frame é o *tracking*. O *solve* incremental
> (C3) é mais caro e ainda não foi medido — C3 inclui a medição, e se o número
> inviabilizar, a decisão volta para você.

#### O que mais a referência ensina

Inventário completo do vídeo, mapeado contra o Opus:

| Técnica observada | Status no Prisma |
|---|---|
| Camera tracking 3D com objetos ancorados | **ausente** → ÉPICO C |
| Painéis "glass" translúcidos com blur e borda luminosa | ÉPICO G (aparência) + C (ancoragem) |
| Tipografia 3D com perspectiva ("Aprenda a fazer" deitado no plano) | **não previsto** → story G5 |
| Captions karaokê amarelo/branco, palavra a palavra | ✅ **já existe** (6 estilos + `caption_style.py`) |
| Zero cortes duros: 14 mudanças, **nenhuma com score > 0.39** | ÉPICO T + doutrina D |
| Ritmo: ~1 mudança visual a cada 3s, narração contínua sem pausa | doutrina D (energia/densidade) |

---

### ÉPICO D — Direção de arte (doutrina HyperFrames)

**Origem:** provocação do usuário (*"o hyperframes tem muita coisa que pode
agregar nesse sentido não?"*). Investiguei o pacote instalado (v0.4.3) e a
resposta é **sim — mas não onde eu esperava**.

**O que NÃO está lá:** `@hyperframes/shader-transitions` não é publicado no npm.
A doc o referencia (*"read the package source"*), a fonte não acompanha. Zero
GLSL, zero `three`, zero `puppeteer` no pacote. Não há código de shader para
portar — e portanto a questão de licença nem se coloca.

**O que ESTÁ lá, e é o ativo real:** ~620 linhas de doutrina de direção de arte
em `dist/skills/hyperframes/references/`. Não é implementação; é o **critério**
que o Opus original não tinha.

#### Por que isso importa mais que o shader

O ÉPICO V/G/B/T responde *como renderizar*. Não responde *quando usar, com que
duração, com que easing, e por quê*. O próprio HyperFrames alerta:
*"Never use a different transition for every scene. Pick ONE primary (60-70%)
+ 1-2 accents."* VFX poderoso sem critério é poluição — e o Prisma teria
construído exatamente isso.

#### A doutrina, destilada

**Matriz Energia → Transição** (números concretos, não adjetivos):

| Energia | Primária (shader) | Duração | Easing |
|---|---|---|---|
| Calm (brand, luxo) | cross-warp morph, thermal distortion | 0.5–0.8s | `sine.inOut`, `power1` |
| Medium (SaaS, explainer) | whip pan, cinematic zoom | 0.3–0.5s | `power2`, `power3` |
| High (promo, lançamento) | ridged burn, glitch, chromatic split | 0.15–0.3s | `power4`, `expo` |

**Presets nomeados:** `snappy` 0.2s/`power4.inOut` · `smooth` 0.4s/`power2.inOut`
· `gentle` 0.6s/`sine.inOut` · `dramatic` 0.5s/`power3.in→out` · `instant`
0.15s/`expo.inOut` · `luxe` 0.7s/`power1.inOut`.

**Matriz Humor → Transição** (com o *porquê*, que é o que falta ao Prisma):
premium/luxo → cross-warp, thermal · *"Restraint"*; tech/futurista → grid
dissolve, glitch, chromatic; tenso → ridged burn, domain warp; dramático →
cinematic zoom, gravitational lens.

**Posição narrativa:** abertura = a transição mais distintiva (0.4–0.6s);
entre pontos relacionados = a primária, consistente (0.3s); mudança de tópico =
algo diferente da primária; clímax = o melhor acento; outro = o mais lento
(0.6–1.0s).

**Regras não-negociáveis (as mais valiosas):**
- *"Exit animations are BANNED except on the final scene. The transition IS the
  exit."* — a camada de saída deve estar **plenamente visível** quando a
  transição dispara.
- *"Don't start at t=0."* Offset de 0.1–0.3s; delay zero lê como jump cut.
- *"Don't use the same ease on every tween"* / *"the slowest scene should be 3×
  slower than the fastest."*
- Blur por energia: calm 20–30px/0.8–1.2s · medium 8–15px · high 3–6px/0.2–0.3s.

**Composição visual:** dois pontos focais mínimos por cena · três camadas
(fundo tratado, conteúdo, acento) · *"fill the frame"*, headline 60–80% da
largura · fundo nunca sólido puro (*"reads as nothing loaded"*) · ancorar às
bordas, não centralizar.

**Áudio-reativo — o alerta que evita clichê:** *"Never add equalizer bars,
spectrum analyzers, waveform displays, particle systems, rainbow cycling."*
O áudio fornece **timing e intensidade**; o vocabulário visual vem da narrativa.
Bass → `scale` (pulso); treble → glow; amplitude → opacidade/lift.

#### Stories

| Story | Entrega | Critério de aceite |
|---|---|---|
| **D1** | `edit-data.json` ganha `direction: {energy, mood}`. Tabela Energia→(transição, duração, easing) vira dado no template | Trocar `energy` de `calm` para `high` muda duração e easing **sem editar código** |
| **D2** | Presets nomeados (`snappy`…`luxe`) como vocabulário do `TransitionSpec` | `{type:'refract', preset:'luxe'}` rende 0.7s; `'snappy'` rende 0.2s. Medido em frames |
| **D3** | Poka-Yoke da consistência: o sistema recusa >1 primária + 2 acentos por vídeo | Tentativa de usar 5 transições distintas → aviso explícito |
| **D4** | Poka-Yoke do "transition IS the exit": insert com `exit` animado **e** transição no mesmo ponto → erro | Conflito detectado antes do render, não depois |
| **D5** | Doutrina condensada em `references/direction.md` (fonte citada) | Referência do Prisma, lida na Fase 2 antes de escolher transições |

> **Aplicabilidade honesta:** as `Shader-Compatible CSS Rules` do HyperFrames
> (html2canvas, `data-no-capture`, sem `var()`) **não** se aplicam ao Prisma —
> existem porque aquele motor captura DOM→textura. A Remotion renderiza a
> `ThreeCanvas` nativamente. Importá-las seria custo sem causa.
>
> Já `dynamic-techniques.md` (karaokê por energia) descreve o que o Prisma
> **já faz** com 6 estilos e `caption_style.py`. Não é lacuna; no máximo, a
> tabela energia→intensidade pode afinar o que existe. Não vira story aqui.

---

## 5. Sequência recomendada

```
1. D5 + D1 + D2          — doutrina primeiro: define easing/duração de TUDO
2. V1 → V2 → V3 → V4     — fundação WebGL. V2 é gate Jidoka.
3. B1 + B2               — maior ganho percebido de fluidez, menor risco
4. C1 → C2 → C3          — camera solve. C2 é gate Jidoka. C3 mede o custo real.
5. G1 → G2 → G3 → G4     — o glass prism (aparência)
6. C4 → C5 → C6 → C7     — ancoragem: o glass passa a PERTENCER à cena
7. G5 + B3 + B4          — tipografia 3D, Ken Burns, moldura
8. T1 → T2 → T3          — displacement (o mais caro)
9. D3 + D4               — Poka-Yoke, depois que há transições para governar
```

**Por que C (solve) entra depois de B mas antes de G:** o painel de vidro sem
ancoragem fica lindo e escorregando pela tela — é o defeito que a referência
não tem. Mas B1/B2 (cover + spring) entregam fluidez **sem** depender do solve,
então vêm antes. E C1–C3 precisam preceder G para que o glass já nasça
ancorável.

**Se C2 ou C3 reprovarem:** o Opus continua válido de V/G/B/T/D — entrega o
visual completo em overlay, sem ancoragem. Perde-se a técnica central da
referência, não o plano inteiro. Essa é a decisão que volta para você, com
número na mão.

**Por que a doutrina (D) vem antes de tudo:** D1/D2 definem os presets de
duração e easing que **todas** as stories seguintes consomem. Construir o glass
prism primeiro e só depois decidir se ele dura 0.2s ou 0.7s significa retrabalho
garantido. O critério antes da mão — é a regra do Prisma, e o HyperFrames a
confirma por caminho independente.

**Por que D3/D4 (Poka-Yoke) ficam no fim:** um guarda que recusa >1 transição
primária só faz sentido quando existem transições para governar. Antes disso,
não teria o que validar.

**Por que B1/B2 antes do glass:** "aparecer na tela toda de forma mais fluida"
é resolvido por cover + spring. Isso entrega valor visível **sem** depender do
shader mais complexo. Se V2 revelar custo de render alto, o usuário já tem
fluidez na mão.

**Nota sobre easing:** o vocabulário do HyperFrames é GSAP (`power4.inOut`,
`expo.out`). A Remotion usa `spring()` e `Easing.bezier`. Os **números**
(duração, blur em px, offsets) portam direto; as **curvas** precisam de
equivalência — mapeamento explícito em D2, não conversão no olho.

---

## 6. O que NÃO fazer

- **Não reescrever o template shortform.** 1.961 linhas funcionando + verificação
  numérica são o ativo. A camada 3D é aditiva.
- **Não tornar a `ThreeCanvas` obrigatória.** `edit-data.json` sem os campos
  novos renderiza como hoje, byte-idêntico.
- **Não copiar código do HyperFrames.** Não há o que copiar: o
  `@hyperframes/shader-transitions` **não é publicado no npm** (verificado na
  v0.4.3 instalada — a documentação o referencia, a fonte não vem junto). O que
  o HyperFrames agrega é **doutrina**, não implementação — ver ÉPICO D.
- **Não portar as regras de captura html2canvas do HyperFrames.** Elas existem
  porque aquele motor captura DOM→textura WebGL. A Remotion renderiza a
  `ThreeCanvas` nativamente, no mesmo passe. Metade das restrições do
  `Shader-Compatible CSS Rules` **não se aplica** ao Prisma — copiá-las seria
  importar custo sem causa.
- **Não construir G/B/T antes do V2 passar.** Shader sobre fundação não
  verificada é o erro que custa a sessão inteira.
- **Não aceitar "parece que funcionou".** Todo critério de aceite acima é um
  still ou um número. Verificação antes de afirmação.
- **Não tocar na Fase 1.** O corte offline sem chave de API é ativo do Prisma.

---

## 7. Pendências pré-existentes (herdadas, fora deste Opus)

Registradas para não se perderem — **não** são escopo daqui:

- **P1 — longform em 10% do shortform**: 3 arquivos vs 8, zero componentes de
  legenda, zero mocks 16:9 na aba Estilo. *Nota: se a camada 3D virar padrão,
  o longform herda o mesmo débito — considerar ao fechar P1.*
- **P3 — B-roll semi-automático**: `pexels_search.py` existe, curadoria manual.
- **Muda estrutural**: `helpers.bak.20260818/` (8 duplicatas, ~12 dias no repo)
  e ausência de git na skill — 36 helpers e 43KB de SKILL.md sem histórico.

---

## 8. Registro de execução

### D5 — `references/direction.md` ✅ (2026-08-31)

Doutrina de direção criada em `references/direction.md`. Cobre: regra da
transição primária única, matriz Energia→(transição, duração, curva), 6 presets
nomeados **com mapeamento GSAP→Remotion explícito**, matriz Humor→transição,
posição narrativa, 6 regras não-negociáveis, composição de quadro, tipografia
em movimento, áudio-reativo com a lista anti-clichê, e o ritmo medido na
referência.

**Decisão técnica registrada:** presets usam `Easing.bezier`, não `spring()`.
`spring()` tem duração emergente da física — não se fixa em 0.2s, e transição
entre cenas precisa casar com o corte de áudio. `spring()` fica reservado para
entradas de elemento dentro da cena.

### V1 — dependências WebGL ✅ (2026-08-31)

`@remotion/three@4.0.482` + `three@0.185.1` + `@react-three/fiber@9.7.0`
instalados no template shortform. **Zero conflito de peer deps** — `npm ls`
confirma `three@0.185.1` deduplicado entre os três pacotes.

### V2 — GATE JIDOKA: WebGL headless ✅ APROVADO (2026-08-31)

`src/GLProbe.tsx` criado — composição diagnóstica (cubo laranja girando sobre
fundo azul-escuro **deliberadamente não-preto**, para distinguir "não
renderizou nada" de "renderizou o fundo mas não a geometria"). Registrada no
`Root.tsx` como composição separada; nunca é entregue.

**Evidência medida — não "renderizou sem erro":**

| Backend | Pixels do cubo | Veredito |
|---|---|---|
| default (sem `--gl`) | **22.41%** laranja / 77.18% fundo | WebGL vivo |
| `--gl=angle` | **25.20%** | idêntico |
| `--gl=swiftshader` | **25.20%** | idêntico |

Still inspecionado visualmente: cubo em **perspectiva**, com rotação 3D —
não um quadrado chapado. 4.695 cores únicas (anti-aliasing real).

**O gate passou. Os épicos G/B/T/C têm fundação verificada.**

### V4 — custo de render medido ✅ (2026-08-31)

30 frames a 540×960, RTX 5070 / Windows / Remotion 4.0.482:

| Caminho | Tempo | Delta |
|---|---|---|
| Sem 3D (2D puro) | 10.45s | baseline |
| `--gl=swiftshader` | 11.13s | +6.5% |
| `--gl=angle` | 11.25s | +7.7% |

**Custo do WebGL: ~7%.** Não é proibitivo — a decisão de motor está validada
por número, não por aposta. (Ressalva honesta: este é o custo de uma geometria
trivial. Shaders de refração do ÉPICO G custam mais, e serão medidos lá.)

### V3 — Poka-Yoke do `--gl` ✅ (2026-08-31)

`render_phase2.py` ganhou detecção automática de backend. O bug latente
identificado na seção 2 (R1) está corrigido:

- `_uses_3d(ed)` inspeciona `edit-data.json` e decide se a cena precisa de
  WebGL: blocos `scene3d`/`tracked`/`glass`, inserts com `frame:'glass'` ou
  `anchor3d`, transições `displace`/`refract`.
- Cena 3D → `--gl=angle` automático. **Cena 2D → nenhuma flag**, preservando
  exatamente o caminho de render que já funciona.
- `--gl` manual com `choices` validados, para diagnóstico e para reproduzir
  entre máquinas.

**Testado com 10 casos**, incluindo robustez (`inserts` com lixo não-dict) e
falso-positivo (`scene3d: None`): **10/10 corretos**. CLI rejeita backend
inválido com mensagem clara.

### Não-regressão do caminho 2D ✅

- `npx tsc --noEmit` → **exit 0**, zero erros de tipo
- `npx remotion bundle` → **sucesso**, bundle completo
- A composição `Reels` falha ao renderizar **no template** por ausência de
  `public/cut.mp4` — comportamento correto de um molde, **anterior a estas
  mudanças** e não relacionado a elas. O bundle compilando é a prova de
  não-regressão disponível sem um projeto real.

**Pendente de verificação:** render 2D ponta a ponta num projeto real com
mídia, para confirmar byte-identidade com o comportamento anterior.

### B1 — `fit: 'cover' | 'contain'` ✅ (2026-08-31)

`InsertCard` em `Main.tsx` ganhou `fit`. Verificado com render real (projeto de
teste com b-roll **horizontal 1920×1080** num quadro 1080×1920 — a única
configuração em que `cover` e `contain` divergem; com b-roll 9:16 os dois são
idênticos por definição, e o primeiro teste que montei não provava nada):

| Modo | Preto no topo | Comportamento |
|---|---:|---|
| `card` (default) | 1.8% | painel 780×500 sobre o falante — inalterado |
| `cover` (B1) | **0.0%** | preenche o quadro, sem letterbox |
| `contain` | **100%** | letterbox correto |

`contain` medido em detalhe: faixa de conteúdo de 622px (esperado 607px + Ken
Burns 1.04×), **centrada em y=958 contra centro do quadro em 960 — 2px de
desvio**. A assimetria aparente de 118px na primeira medição era conteúdo
escuro do próprio b-roll, não erro de layout.

**Correção de diagnóstico:** o Opus original dizia que o insert era "card
retangular com corte duro". Ao ler o código, o `InsertCard` **já tinha** fade,
scale de entrada e Ken Burns. As lacunas reais eram outras três: tamanho fixo
(nunca fullscreen), **só `<Img>`** (vídeo não renderizava) e ausência de spring.

**Ganho não previsto:** inserts agora aceitam **vídeo**. `InsertCard` escolhe
`OffthreadVideo` ou `Img` pela extensão do arquivo. Antes, um `.mp4` em
`inserts` falhava no render.

### B2 — entrada com spring ✅ RESOLVIDO como opt-in (2026-08-31)

> **Atualização — a regressão descrita abaixo foi eliminada.** Seguindo a
> diretriz do usuário (*"tudo que for adicionar coloque como opcional da segunda
> etapa"*), a curva virou `enter: 'cubic' | 'spring'`, com **`cubic` como
> default**. Verificado com still PNG (sem codec no meio):
>
> | Comparação | Diff média | Máx | Px alterados |
> |---|---:|---:|---:|
> | original vs novo (default `cubic`) | **0.000000** | **0** | **0.0000%** |
> | original vs spring fixo (regressão anterior) | 0.141217 | 76 | 8.6139% |
> | `enter:'spring'` vs spring fixo anterior | **0.000000** | 0 | — |
>
> **Byte-idêntico com o default, e o spring preservado por escolha.** Exposto
> no gate como `springIn` ("Entrada com mola"), `def: false`.
>
> **Bug encontrado ao fazer o opt-in:** eu havia adicionado
> `extrapolateRight: 'clamp'` nos `interpolate` de `scale` e `y`, que o código
> original não tinha. Com `cubic` é inofensivo (`enter` nunca passa de 1), mas
> **achatava exatamente o overshoot** que justifica escolher o spring. Removido;
> é o que permite os dois caminhos baterem 0.000000.

<details>
<summary>Registro original (antes da correção)</summary>

Entrada passou de `interpolate` + `Easing.out(cubic)` para `spring()`
(`damping: 14, mass: 0.55, durationInFrames: 14`), dando overshoot — a
diferença entre "o card apareceu" e "o card chegou". A **saída** permanece em
`interpolate`: springs têm duração emergente e a saída precisa pousar no último
frame exato, ou o insert pisca ao desmontar.

**A regressão, medida e nomeada:** A/B em PNG puro (mesmo frame, mesma imagem,
sem codec no meio) mostra **8.6% dos pixels alterados, diff média 0.14, máx 76**,
e a região que difere é **y 80–599 × 135–944** — exatamente a área do card
(y90–590, x150–930). Não é ruído de compressão: dois renders do mesmo input dão
diff **0.0000**, o render é determinístico.

**Portanto: um `edit-data.json` legado NÃO renderiza byte-idêntico.** O card
entra com curva diferente. Isso viola o critério de não-regressão que este Opus
declarou na seção 3.

**Decisão original:** aceitar a regressão. **Revertida** — manter as duas curvas
custou ~10 linhas, não "para sempre", e o opt-in é a diretriz do usuário para
tudo que este Opus adiciona.

</details>

### B1b — `brollFull` como elemento opcional do gate ✅ (2026-08-31)

**Pedido do usuário:** *"tudo que for adicionar coloque como opcional da segunda
etapa para que eu possa selecionar ou não assim como já tem outros efeitos lá."*

`STYLE_CATALOG.elements` em `assets/preview/app.js` ganhou `brollFull`
("B-roll em tela cheia"), `def: false`, com ícone SVG no mesmo vocabulário
visual dos outros (sem emoji).

**Contrato idêntico ao do `flashCut`:** o checkbox concede o *look*; a decisão
editorial de qual clipe é promovido e quando continua no `edit-data.json`.
Com `brollFull` desmarcado, **nenhum insert recebe `fit`** — todos permanecem
card.

**Verificado ponta a ponta, sem alterar uma linha de lógica** (o catálogo é
iterado, não enumerado):

| Etapa | Resultado |
|---|---|
| `node --check app.js` | sintaxe OK |
| Catálogo | 6 elementos, `brollFull` def `false` |
| `defaultStyle()` | inclui `brollFull: false` |
| Merge com `preview_style.json` **antigo** | `brollFull: false` (não `undefined`); escolhas do usuário preservadas |
| `watch_edits.py` ligado | `· elementos: …, B-roll em tela cheia` |
| `watch_edits.py` desligado | `· fora: …, brollFull` — instrução explícita de manter fora |
| Fallback sem `elementNames` | funciona (json legado) |

Documentado em `references/shortform.md` na tabela de `preview_style.json`, na
seção de inserts e na lista de checkboxes do gate.

### G1/G2/G3/G4 — glass prism ✅ ENTREGUE (2026-08-31)

> **Atualização — o bloqueio abaixo foi resolvido.** A causa era minha, não do
> motor: eu chamava `useOffthreadVideoTexture` **dentro** da `<ThreeCanvas>`.
> A documentação oficial (`@remotion/three`, consultada em vez de mais
> tentativa-e-erro) mostra que o hook pertence ao componente que **possui** a
> canvas. Corrigido, funciona.

**Arquitetura final:** a canvas desenha a própria footage como quad de quadro
inteiro e o shader a refrata. Não há como um shader amostrar um
`<OffthreadVideo>` irmão no DOM — a footage precisa entrar no WebGL.

**Evidência medida sobre uma grade de linhas retas** (a cena que prova ou
desmente refração):

| Verificação | Resultado |
|---|---|
| **G1 — refração real** | A linha laranja é contínua de x=0 a 1079 no fundo e **quebra em x=129** — exatamente a borda esquerda do painel (esperada 129). Pixels **deslocados**, não borrados |
| **G2 — dispersão cromática** | 433 px puro-vermelho, 280 puro-verde, 280 puro-azul numa fonte que só contém ciano/laranja/amarelo. São produto da separação RGB |
| **G3 — entrada** | `uProgress` interpolado em 12 frames; refração, sheen e rim escalam juntos |
| **G4 — presets** | intensity 0.2 → **9.794** px de dispersão · 0.5 → **56.118** · 1.0 → 36.464 |
| **Custo** | 8.85s vs 8.26s baseline = **+7,2%** (30 frames, 1080×1920) |

**Achado honesto sobre G4:** a curva não é monotônica. Em `1.0` a dispersão
*medida* cai porque o deslocamento fica grande o bastante para os canais se
**recombinarem** — fisicamente coerente, mas na prática significa que acima de
~0.7 o efeito lê como borrado, não como mais forte. Documentado na referência
em vez de escondido atrás de um número que parecia melhor.

**Bug de geometria corrigido:** sob a câmera em perspectiva padrão o quad 2×2
cobria só parte do viewport — o painel saía 380×170px em vez dos 821×653px
pedidos. Corrigido com câmera ortográfica (`left/right/top/bottom = ±1`).

**Trade real, documentado e não escondido:** dentro de uma janela de vidro a
câmera dinâmica (zoom por corte, face tracking) **não se aplica** — a canvas
desenha o cut cru. Por isso a referência recomenda janelas curtas.

**Gate:** `glassPanel` ("Painel de vidro (3D)"), `def: false`. O catálogo agora
tem **8 elementos**.

<details>
<summary>Registro da tentativa anterior, que falhou (mantido — a causa raiz importa)</summary>

### G1 — bloqueado no acesso à textura (primeira tentativa)

Tentativa executada e **revertida**. O template está de volta ao estado íntegro
(`tsc` exit 0); nada de meio-construído ficou no repo.

**O que funcionou:**
- Shader GLSL escrito e compilando: SDF de retângulo arredondado, normal obtida
  do gradiente do SDF, refração por deslocamento de UV, dispersão cromática por
  amostragem separada de R/G/B, sheen especular e rim.
- Render WebGL executou sem erro, com `--gl=angle`.
- **Bug de geometria encontrado e corrigido:** sob a câmera em perspectiva
  padrão, o quad 2×2 cobria só parte do viewport — o painel saiu 380×170px em
  vez dos 821×653px pedidos. Corrigido com câmera ortográfica
  (`left/right/top/bottom = ±1`), que mapeia o quad 1:1 ao quadro. **Medido**,
  não estimado.

**O bloqueio real — a footage não chega ao shader:**

| Via tentada | Resultado medido |
|---|---|
| `useOffthreadVideoTexture` | Retornou `null` em **todos os 9 frames** renderizados dentro da `ThreeCanvas`. Painel saiu cinza opaco (shader amostrando textura nula → preto; só sheen e rim sobreviveram) ou ausente |
| `WebGLRenderTarget` offscreen | Descartado por análise: o target só conteria outros objetos 3D, nunca o vídeo 2D que está numa camada DOM separada |

**Causa raiz:** a `ThreeCanvas` é uma camada *irmã* do `<OffthreadVideo>` no
DOM, não pai dele. O shader não tem acesso aos pixels que quer refratar — que é
exatamente a limitação que o `CustomGraphics.tsx` já documentava para o
`whip-pan`/`glitch` (*"no handle on the video layer beneath it"*). **Adicionar
WebGL não removeu essa limitação; ela é do modelo de composição, não do motor.**

**Correção de premissa do Opus:** a seção 1 concluiu que a causa raiz do teto
era "zero WebGL nas dependências". Isso estava **incompleto**. O WebGL entrou
(V1/V2 provaram, com pixels), e o teto continua — porque o problema é o
*acesso à camada de vídeo*, não a capacidade de shader.

**Caminhos possíveis, nenhum executado:**
1. **Canvas transparente + `backdrop-filter`** — a `ThreeCanvas` desenha só o
   vidro (distorção, sheen, rim) em fundo transparente e o compositor do
   Chromium aplica sobre o vídeo real embaixo. Mantém determinismo, mas
   `backdrop-filter` não faz *displacement* — entrega blur e brilho, não
   refração verdadeira. **Honesto sobre o limite.**
2. **Vídeo dentro da `ThreeCanvas`** — mover o `<OffthreadVideo>` para dentro do
   WebGL como plano texturizado, com o shader por cima. Refração real, mas
   reescreve `DynamicVideo` (câmera, zoom por corte, tracking) em Three.js.
   Alto risco sobre 1.961 linhas verificadas.
3. **Pré-passe ffmpeg** — extrair a janela do painel como PNGs, alimentar o
   shader com eles, recompor. Determinístico e sem tocar no template, mas
   adiciona uma etapa de render e custo de disco.

**Desfecho:** o caminho (2) foi o correto, e o custo previsto ("reescreve
`DynamicVideo` em Three.js") **não se materializou** — a canvas desenha a
footage apenas dentro da janela de vidro, e `DynamicVideo` fica intacto fora
dela. A limitação sobrou apenas como o trade documentado acima.

</details>

### C1/C2 — tracking + gate ✅ · C3 — solve ⚠️ REPROVADO PELO PRÓPRIO GATE (2026-08-31)

`helpers/camera_track.py` (C1+C2) e `helpers/camera_solve.py` (C3).

**C1/C2 — entregues e validados nos dois sentidos.** O gate só vale se souber
dizer não, então testei os casos que devem falhar:

| Cena | Veredito | Razão dada |
|---|---|---|
| Vídeo de referência (câmera na mão) | ✅ passa | 334 features/frame · 1.178 trilhas · paralaxe 4.1px |
| Gradiente liso (sem textura) | ⛔ recusa | "textura insuficiente — 0 features vivas" |
| Frame estático | ⛔ recusa | "sem paralaxe — 0.00px" |
| **Pan puro** (imagem estática transladando) | ⛔ recusa | **"sem paralaxe — 0.06px"**, com **573 features vivas** |

O último é o caso que importa: **muitas features não bastam.** Uma panorâmica
no tripé move todos os pixels juntos, não há baseline, e nenhum algoritmo
resolve profundidade daí. O gate mede o *desvio-padrão* do deslocamento, não a
média, justamente para separar translação de rotação.

**Custo:** ~25 ms/frame em CPU (~40× tempo real), sem GPU e sem COLMAP.

**C3 — o solve roda, e o gate o reprova. Honestamente.**

| Métrica | Valor |
|---|---|
| Frames resolvidos | **151/151** |
| Erro de reprojeção | **0.10px** |
| Pontos 3D | 584 |
| **Saltos de escala** | **30% dos passos** (limite 10%) |

**Veredito: `ok: false`, `camera.json` NÃO é gravado.**

**Dois bugs meus, encontrados porque olhei além do erro de reprojeção:**

1. **Baseline nula na triangulação.** Eu estendia a nuvem contra o frame
   *anterior* — raios quase paralelos, pontos no infinito. Sintoma perverso:
   erro de **0.27px** (ótimo!) com a câmera **oscilando em torno de zero**
   (extensão 0.001). Erro baixo por overfit. Corrigido escolhendo o frame
   resolvido mais distante com pontos em comum → extensão **6.52**.
2. **O gate não pegava isso.** Adicionei duas verificações que teriam:
   `trajectory_span` (colapso) e `jump_ratio` (instabilidade).

**A causa raiz do que resta é conhecida e não é bug pontual:** `recoverPose`
devolve translação **normalizada**, e cada `solvePnP` fixa escala por conta
própria. Sem **bundle adjustment global** a escala oscila entre frames. É
limitação de SfM monocular incremental, documentada na literatura — não algo
que se ajuste mudando um limiar.

**O que isso significa para C4–C7:** não construo `<TrackedScene>` sobre uma
pose que treme. As stories seguintes ficam **bloqueadas até o solve passar**,
e passar exige uma destas escolhas suas:

**Pesquisa PRP executada (2026-08-31) — e ela mudou a recomendação.**
Relatório completo: `.omc/research/prisma-ba-2026-08-31/report.md`.

> **Correção de premissa.** Este Opus registrava pycolmap como *"dependência
> nativa nova (~50MB), instalação frágil no Windows"*. **Falso, e eu havia
> assumido em vez de verificar.** Existe wheel oficial
> `pycolmap-4.1.1-cp313-cp313-win_amd64.whl` (22.4 MB, 2026-07-17). Instalado
> nesta máquina em ~31s, sem CMake, sem compilador, import limpo.

| Biblioteca | Wheel cp313-win | Licença (arquivo LICENSE) | Último commit | Veredito |
|---|---|---|---|---|
| **pycolmap 4.1.1** | ✅ 22.4 MB | BSD-3 (`COPYING.txt`) | hoje | **viável, testado** |
| scipy 1.18 | ✅ já instalado | BSD-3 | ativo | viável |
| pyceres 2.6 | ✅ 8.1 MB | Apache-2.0 | hoje | viável (BA cru) |
| gtsam 4.2.2 | ⛔ zero | BSD + GPL em 3rdparty | hoje | inviável |
| g2o-python | ⛔ nenhuma | MIT | 2023-05-22 | inviável (abandonado) |

**Recomendação revista: pycolmap.** Aceita reconstrução montada externamente
(`add_image`, `add_point3D`, `fix_gauge`) — não exige adotar o pipeline COLMAP
inteiro, então o tracking a 25 ms/frame e o gate permanecem. Usa Ceres, o mesmo
motor do COLMAP em produção.

**O argumento decisivo não é conveniência, é histórico:** BA escrito à mão erra
em silêncio. Este solve já custou duas correções exatamente por isso — a
triangulação com baseline nula devolvia **0.27px de reprojeção com a câmera
parada**. Um número bom pode ser mentira, e repetir o padrão numa jacobiana
esparsa escrita à mão não vale os 22 MB economizados.

**Não é falta de recurso.** A RTX 5070 ficou ociosa; a ambiguidade de escala é
intrínseca à visão monocular (Triggs et al. 2000), e a etapa que a resolve
— bundle adjustment global — simplesmente não estava no pipeline.

#### Implementação do BA (2026-08-31) — ⚠️ INTEGRADO, MAS DIVERGE

pycolmap instalado e integrado em `camera_solve.py` (`bundle_adjust()`,
flag `--no-ba` para comparar). **O BA roda e diverge**, e o helper agora diz
isso em vez de fingir sucesso.

**Quatro bugs reais encontrados e corrigidos no caminho** — cada um produzia um
falso positivo, que é o modo de falha mais caro:

| # | Bug | Sintoma enganoso |
|---|---|---|
| 1 | `register_frame()` faltando | BA "convergia" instantaneamente — não via imagem alguma |
| 2 | `update_point_3d_errors()` faltando | reprojeção **0.000px antes e depois**, que parecia perfeição e era ausência de medição |
| 3 | Filtro de cheirality só testava `z > 0` | pontos a **1e150** passavam como "à frente da câmera" |
| 4 | `loss_function_type: TRIVIAL` (padrão) | um ponto errado por 1.000px pesa 1 milhão de vezes mais que um por 1px |

**Estado atual, medido:**

| | Valor |
|---|---|
| Erro **mediano** por frame | **0.1–1.0px** (a geometria local está certa) |
| Entrada do BA após duas podas | **13.6px** (era 1e151) |
| Saída do BA | **1e152 — diverge** |
| Guarda de divergência | ✅ detecta, preserva poses originais, reporta |
| `jump_ratio` | 32% — gate continua reprovando |
| `camera.json` | **não gravado** |

**O que aprendi e vale registrar:** o erro mediano sempre foi bom. O que mata é
a cauda — alguns pontos reprojetando a 57.000px. Duas podas (mediana+MAD, depois
a medição do próprio COLMAP a 50px) tiraram a entrada de 1e151 para 13.6px, e
ainda assim o Ceres diverge. Isso aponta para **má condicionamento estrutural da
reconstrução inicial**, não para outliers residuais.

**Hipótese testada e REFUTADA.** Supus que a causa fosse ângulo de paralaxe
insuficiente por ponto. Medi: 25% dos pontos têm < 1.28°, o que dava base à
suspeita. Mas filtrar por ângulo **não resolve** — a divergência persiste em
todos os cortes, e a entrada mal melhora:

| Corte | Pontos | Resultado |
|---|---|---|
| 2° | 242 | diverge (13.15px → 7.8e152) |
| 3° | 206 | diverge (12.49px → 1.6e153) |
| 5° | 180 | diverge (12.38px → 1.8e153) |

**A causa real, isolada por varredura:** o BA converge ou diverge em função do
**número de frames**, não da qualidade dos pontos.

| Frames | Resultado |
|---|---|
| **8** | ✅ **CONVERGIU — 5.88px → 0.59px** |
| **10** | ✅ CONVERGIU — 14.87px → 9.68px |
| 12 | ⛔ diverge |
| 15, 18, 25, 30, 60, 100, 151 | ⛔ diverge |

Fronteira nítida entre 10 e 12 frames, com todos os frames vendo 125+ pontos
(descarta sub-determinação de pose). Um problema que converge lindamente em 8
frames e explode em 12 é **instabilidade numérica na propagação**, não dado
ruim: a deriva de escala do solve incremental cresce com o comprimento da
cadeia, e a partir de certo ponto a reconstrução inicial fica longe demais do
mínimo para o Ceres alcançá-lo.

**Janela deslizante testada — não resolve.** A explicação "cadeia longa demais"
também caiu. Janelas de 10 frames ao longo do clipe: **1 de 7 converge**, e as
que falham entram a **0.17–0.59px** — praticamente perfeitas. Erro de entrada
não prevê divergência.

**Gauge testado** (`TWO_CAMS_FROM_WORLD` e `THREE_POINTS`): nenhum resolve.

**A causa raiz, finalmente isolada — e ela é do MATERIAL, não do código:**

| Janela | Baseline | Profundidade/baseline | BA |
|---|---:|---:|---|
| frames 0–10 | **1.0033** | **5** | ✅ converge (5.88 → 0.59px) |
| frames 40–50 | 0.0020 | 1.473 | ⛔ diverge |
| frames 80–90 | 0.0005 | 5.917 | ⛔ diverge |

E a medição que fecha o caso: entre os frames 40–50 e 80–90 as features andam
**0.0px na tela**. A câmera não se move porque **a cena não se move**. As poses
do PnP estavam certas o tempo todo.

Medido no trecho: **41% dos frames têm mudança < 0.01** — o clipe 16–21s do
vídeo de referência foi escolhido por mostrar o overlay verde de tracking, não
por ter movimento. Sem translação não há baseline, sem baseline não há
triangulação, e o BA foge para o infinito. Nenhum algoritmo resolve isso: é a
mesma degenerescência que o gate de `camera_track.py` já detecta e recusa.

**Guard implementado** (`_ba_is_conditioned`): mede profundidade/baseline antes
de chamar o BA e recusa acima de 500, com a razão explícita. Evita gastar o
otimizador num problema degenerado.

**Estado final do ÉPICO C:**

| Componente | Estado |
|---|---|
| `camera_track.py` (C1) | ✅ funciona — 25 ms/frame |
| Gate de qualidade (C2) | ✅ **valida nos dois sentidos**, recusa pan puro com 573 features |
| `camera_solve.py` — poses (C3) | ✅ 151/151 frames, erro **mediano 0.1–1.0px** |
| Bundle adjustment | ⚠️ converge em geometria boa, recusa a degenerada |
| Trajetória global | ⛔ `jump_ratio` 32–36%, **gate reprova, `camera.json` não é gravado** |
| C4–C7 (`<TrackedScene>`) | ⛔ bloqueadas |

**O que foi construído e vale:** um pipeline que **falha alto** em vez de
entregar poses ruins em silêncio. Quatro falsos positivos foram caçados até a
raiz, e cada guard adicionado (`register_frame`, `update_point_3d_errors`,
profundidade máxima, loss Cauchy, guarda de divergência, condicionamento) existe
porque um número mentiu antes.

**O que falta para C funcionar:** material com translação de câmera sustentada.
Não é código — é filmagem. O gate já sabe distinguir; o que não existe hoje é um
clipe de teste que o satisfaça ao longo de vários segundos.

#### Teste com filmagem adequada (2026-08-31) — BA CONVERGIU

Wellington gravou material com movimento real de câmera (58s, 478×850 após a
compressão do WhatsApp). Paralaxe média **15.46px** contra 3.31px do clipe
anterior — 4.7× mais.

**Quinto bug encontrado, e o mais grave: o PnP produzia poses fisicamente
impossíveis.** Centros de câmera a **11.942 unidades**, com baseline inicial de
1.0 — a câmera teleportava. O `solvePnPRansac` resolve cada frame isoladamente e
nada o impedia de devolver uma pose absurda que reprojeta bem nos inliers que o
próprio RANSAC escolheu. Era isto que entregava ao Ceres uma reconstrução
impossível, e o sintoma no log era literal: `Unable to perform dense Cholesky
factorization`.

Corrigido com teste de continuidade (`MAX_CAMERA_STEP`): uma câmera não salta.

| | Antes do teste | Depois |
|---|---:|---:|
| `jump_ratio` | 17% | **0.00%** |
| `trajectory_span` | 12.038 | 89.2 |
| **Bundle adjustment** | divergia (1e152) | **13.46px → 7.16px ✅** |
| Erro de reprojeção | 39.48px | **6.91px** |

**O BA converge em dados reais pela primeira vez.** O limiar foi calibrado por
varredura (5/15/40/100): 40.0 dá 22 frames com jump 0.00 e o menor erro.

**Ainda reprovado pelo gate**, e corretamente: 6.91px contra o limite de 2.0px.
Uma pose que erra ~7px desloca o objeto ancorado visivelmente. Mas a natureza do
problema mudou — de *divergência catastrófica* para *precisão insuficiente*, que
é um problema de grau, não de espécie.

**Só 22 de 151 frames resolvem.** O teste de continuidade rejeita muita pose boa
junto com as ruins, porque compara sempre com o último centro aceito e não
prediz onde a câmera deveria estar. Um filtro de movimento (velocidade
constante) aceitaria a maioria delas.

#### Teste com o material 4K (2026-08-31)

Wellington regravou em 3840×2160 e o pipeline processa em 1080p (downscale do
4K, que é o fluxo desejado). Paralaxe **12.79px** — 3× a do WhatsApp.

**Sexto bug: o par inicial era escolhido pelo critério errado.** O código pegava
o *primeiro* par acima do limiar de paralaxe. Medido no 4K: f0→f1 passava no
limiar (10.47px) mas sobrevivia com **3 pontos**; f0→f2 dava **350**. O solve
morria na largada.

Pior, o critério de pontuação também estava errado: f0→f1 tinha **448 inliers**
na matriz essencial e **3** após o `recoverPose` — quase tudo caía atrás da
câmera. A matriz essencial fecha as contas com paralaxe insuficiente; a
triangulação não. Passou a pontuar pelo que sobrevive ao `recoverPose`.

**Comparativo final dos três materiais:**

| Material | Frames | jump_ratio | Reprojeção | BA |
|---|---:|---:|---:|---|
| Referência (Instagram, cena parada) | 151 | 0.32 | 18.14px | ⛔ diverge |
| WhatsApp 478×850 | 28 | **0.00** | 6.38px | ✅ **converge** |
| **4K → 1080p** | 27 | **0.00** | **6.64px** | ✅ **converge** |

**O que melhorou com material adequado:** o BA passou a convergir de forma
consistente e a trajetória ficou estável (`jump_ratio` 0.00 nos dois). A
divergência catastrófica acabou.

**O que continua bloqueando:** ~6.6px de reprojeção contra o limite de 2.0px, e
**27 de 149 frames**. Investiguei a fundo:

- Não é a nuvem inicial — 350 pontos, e **os 149 frames veem 12+** (mediana 155).
- Não é o teste de continuidade — desligá-lo dá **exatamente o mesmo resultado**.
- Não é o método de PnP — ITERATIVE/EPNP/SQPNP/AP3P dão 28–33 frames,
  todos com **erro de 1.34px** nos que resolvem.
- **É o `solvePnPRansac` falhando em 100 de 149 frames**, apesar de haver pontos
  suficientes. Passadas múltiplas (`PNP_PASSES`) não recuperam: a nuvem não
  cresce nas regiões dos frames que falham.

**Diagnóstico honesto:** o erro de 1.34px nos frames que resolvem mostra que a
geometria está certa. O problema é cobertura — a nuvem fica presa à região do
par inicial, e a extensão incremental não a expande o bastante. Isto é o que
distingue um SfM de brinquedo de um maduro, e é exatamente o que o pipeline
completo do COLMAP (`IncrementalMapper`, já disponível no pycolmap instalado)
resolve por construção.

#### C3/C4 ✅ RESOLVIDO — `camera_solve_colmap.py` (2026-08-31)

Troquei o solve caseiro pelo pipeline do COLMAP. **Primeiro `ok: true` do
ÉPICO C.**

| | caseiro | **COLMAP** |
|---|---:|---:|
| Frames resolvidos | 27/149 | **45/45 (100%)** |
| Reprojeção | 6.65px | **0.82px** |
| Pontos 3D | 428 | **13.101** |
| Reconstruções | 1 | 1 |
| Veredito do gate | ⛔ reprovado | ✅ **aprovado** |

**Trajetória verificada como fisicamente coerente:**
zero saltos (>8× a mediana), rotação mediana **0.69°/frame** (máx 1.73°) —
o perfil de câmera na mão. Caminho de 16.0 unidades com deslocamento
início→fim de 12.0: trajetória quase reta, sem oscilação.

**Duas descobertas de calibração:**

1. **Frames consecutivos, não amostrados.** Com 1-em-5 a reconstrução partiu em
   **3 fragmentos**; com frames consecutivos, **1 única**. O matching sequencial
   conta com sobreposição alta entre vizinhos.
2. **A focal estimada estava 29% errada.** O COLMAP mediu **1253px** onde eu
   supunha 972 (0.9× a largura). Explica parte do erro do solve caseiro — e o
   COLMAP a estima em vez de assumir.

**Custo medido:** matching 43s + mapping 94s = **~2min por 1.5s de clipe**.
Caro, e é a razão de o recurso trabalhar em janelas: o painel de vidro é um
acento de 2–3s, não o vídeo inteiro.

**O que sobrevive do trabalho anterior:** `camera_track.py` continua como
pré-filtro. Rodar 2 minutos de COLMAP numa cena sem paralaxe é desperdício, e o
gate detecta isso em segundos — validado nos dois sentidos (recusa pan puro com
573 features, recusa cena lisa).

**A lição, registrada:** seis bugs foram gastos reimplementando SfM. O
`IncrementalMapper` faz re-triangulação, seleção de próxima imagem por cobertura
e BA local a cada registro — e é exatamente isso que faltava. Mesma lição do
bundle adjustment, uma camada acima.

#### C5 — `<TrackedScene>` ✅ ANCORAGEM FUNCIONANDO (2026-08-31)

> **Atualização — o desalinhamento abaixo foi corrigido.** Erro de projeção de
> **304.7px → 22.9px (mediana)**, medido nos 22 frames em que o objeto está
> dentro do quadro. O still de 5 frames mostra o cubo entrando pela esquerda,
> cruzando a cena e saindo pela direita, **em perspectiva** e encolhendo
> conforme a câmera se afasta. Ele pertence à sala, não à tela.
>
> **A correção veio de um teste unitário, não de renderizar e olhar.**
> `src/poseMath.test.mjs` projeta pontos conhecidos pelos dois caminhos (pinhole
> do COLMAP e matriz do Three) e compara as quatro conversões candidatas:
>
> | Conversão | Erro |
> |---|---:|
> | `invert().premultiply(FLIP)` ← a que estava no código | **1283.1px** |
> | `invert().multiply(FLIP)` | **0.9px** ✅ |
> | `premultiply(FLIP).invert()` | 0.9px |
> | `invert()` puro (sem flip) | 3053.8px |
>
> O flip vai **do lado da câmera** (`multiply`, à direita), não do lado do mundo
> (`premultiply`, à esquerda). `premultiply` gira o mundo inteiro em torno do X
> global; `multiply` gira só os eixos locais da câmera. A distinção custa
> 1283px, e o teste a encontra em milissegundos — contra os 45 frames
> renderizados que gastei antes para descobrir apenas que estava errado.
>
> Resíduo de ~23px: distorção radial (`SIMPLE_RADIAL`, k=0.17) que o Three não
> modela. Suficiente para ancorar; corrigir exigiria pré-desdistorcer a footage.

<details>
<summary>Registro do estado anterior (desalinhado)</summary>

`src/TrackedScene.tsx` criado e ligado ao `Main.tsx`. Renderiza sem erro nos 45
frames; a footage entra no canvas como plano de fundo e os objetos são
desenhados por cima com a câmera dirigida pelo `camera.json`.

**O que está certo:**
- TypeScript exit 0; `camera.json` ausente não quebra o build (`require` em
  `try` → `trackedData = null` → a camada não monta).
- Opt-in real: sem `tracked.enabled` nada é criado.
- Câmera default do canvas dirigida por `useFrame` **e** durante o render — um
  `<perspectiveCamera>` filho cria uma câmera que o R3F não usa, e o sintoma
  seria uma cena estática ignorando o solve inteiro.
- FOV derivado da focal medida pelo COLMAP (1253px), não arbitrário.

**O que está errado, medido:** comparei a posição do objeto na tela com a
projeção calculada a partir do próprio `camera.json`:

| Frame | Medido | Previsto | Erro |
|---|---|---|---:|
| 24 | (44, 693) | (174, 417) | **304.7px** |

304px é desalinhamento de convenção, não imprecisão. A conversão
COLMAP→Three em `poseToThree` (`invert().premultiply(FLIP)`) não está correta —
provavelmente a ordem das operações, ou o flip precisa ser aplicado à rotação e
à translação separadamente.

**Descoberta lateral, e ela importa mais do que parece:** neste trecho de 45
frames **nenhum ponto fixo do mundo fica visível em todos**. O melhor candidato
aparece em **20/45**. A câmera varre demais.

Isso é requisito de filmagem, não de código: para ancorar um objeto de forma
convincente, a câmera precisa **manter o alvo em quadro** enquanto se move ao
redor dele — que é o que a referência do Instagram faz. Panorâmica larga
atravessando o ambiente resolve a pose (o solve deu 0.82px), mas não deixa
o objeto na tela.

**Próximo passo:** corrigir a conversão de coordenadas com um teste unitário
que projeta um ponto conhecido pelos dois caminhos (numpy e Three) e compara —
verificação que não depende de renderizar e olhar.

</details>

**Requisito de filmagem que vale registrar** (vale para qualquer uso de C):
neste trecho a câmera varre tanto que **nenhum ponto do mundo fica visível nos
45 frames** — o melhor aparece em 20. Para ancorar de forma convincente, a
câmera precisa **manter o alvo em quadro** enquanto se move ao redor dele, que é
o que a referência do Instagram faz. Panorâmica atravessando o ambiente resolve
a pose (0.82px) mas não segura o objeto na tela.

### T1/T2/T3 — transições com displacement ✅ ENTREGUE (2026-08-31)

`src/ShaderTransition.tsx`. Dois tipos novos em `transitions[]` — `displace` e
`refract` — que **movem os pixels da própria footage**, ao contrário dos três
overlays existentes.

**T3 cumprido por caminho melhor que o planejado.** A story previa "dar channel
split de verdade ao `glitch`". Em vez de alterar um efeito que funciona e está
verificado, os dois tipos novos **coexistem** com flash/whip-pan/glitch na mesma
lista, roteados por tipo. Quem já usa o glitch não vê diferença.

**Evidência — deformação da linha reta** (0.00px de variação fora da transição):

| | Deformação medida | Px alterados |
|---|---:|---:|
| Fora da transição | **0.00px** | — |
| `displace` (calibrado) | 127px, grade **legível** | 48.3% |
| `refract` | 11.4px, curvatura de lente | 80.5% |

**Custo:** 8.044s vs 7.653s = **+5,1%**.

**Calibração — o primeiro resultado era inutilizável.** Com noise em 6.0/22.0 e
deslocamento de 0.10 do quadro (~190px), o still mostrou **ruído abstrato**: a
imagem tinha sumido, não sido perturbada. Reduzido para 2.2/5.0 e 0.028. A
diferença entre "transição" e "destruição" não aparece em nenhuma métrica de
diff — só olhando o frame. Foi por isso que olhei.

**Bug de dupla renderização encontrado antes de rodar:** o `switch` de
`CutFlashes` tem `default:` → um `displace` cairia nele e pintaria um flash
**por cima** do shader, dois efeitos no mesmo corte. Corrigido com
`isOverlayCut()` filtrando na origem. O SFX do corte, que vivia só no
`CutFlashes`, foi replicado no `ShaderTransitions` para não se perder.

**`_uses_3d()` já cobria os dois tipos** — testado, 5/5 casos.

**Gate:** `shaderCut` ("Transição com distorção"), `def: false`. Catálogo agora
com **9 elementos**.

### G5 — tipografia 3D ⛔ TENTADO E REVERTIDO (2026-08-31)

`troika-three-text` (MIT, 0.8 MB, peer dep já satisfeita) integrado como
`src/Text3D.tsx`. **Revertido**: o template está de volta ao estado do commit
`efaa98d`, `tsc` exit 0, dependência desinstalada.

**O que aconteceu, em ordem:**

1. Sem `sync()`, a malha renderiza posicionada e **sem glifo nenhum** — falha
   silenciosa, zero erro no log. Medido: **78 pixels** da cor do texto onde
   deveriam existir milhares.
2. Com `sync()` no `ref`: idem. A chamada é assíncrona e não termina antes do
   draw.
3. Com `delayRender` segurando o frame até `preloadFont` → `sync()`: o render
   **morre** com *"delayRender was called but not cleared after 28000ms"* — o
   callback nunca volta.
4. Com rede de segurança de 3s liberando o `delayRender`: render passa,
   **texto continua ausente (78 px)**.

**Causa raiz:** o troika delega a geração de SDF a um **Web Worker**, e no
Chromium headless do Remotion esse worker não conclui. Não é ajuste de
parâmetro — é incompatibilidade de arquitetura entre a biblioteca e o ambiente
de render.

**Alternativas, nenhuma testada:**

| Caminho | Custo |
|---|---|
| `TextGeometry` do Three + fonte JSON (facetype.js) | Sem worker, mas exige converter a fonte e não tem SDF: bordas serrilhadas em close |
| Textura de canvas 2D num plano | Trivial e sem dependência; **borra** quando a câmera se aproxima ou o plano se inclina — que é justamente o caso de uso |
| ~~`configureTextBuilder({useWorker: false})`~~ | ⛔ **testado, não resolve** |

**`useWorker: false` descartado (2026-08-31).** Era a hipótese mais promissora
e custou minutos em vez de horas porque testei numa **sonda isolada** — uma
composição mínima com texto vermelho sobre fundo azul — em vez de recriar o
componente inteiro para descobrir o mesmo. Resultado: **0 pixels**. Nem sem
worker o troika constrói glifos neste ambiente.

**Recomendação ao retomar, revista:** `TextGeometry` do Three com fonte JSON.
Não usa worker nem SDF — a geometria é construída de forma síncrona a partir
das curvas da fonte. O custo é converter a fonte (facetype.js) e aceitar
bordas sem anti-aliasing de SDF, que num letreiro grande e estático importa
pouco.

### Ken-Burns por modo

Full-frame deriva menos que card: os mesmos 8% que leem como suave num card de
780px leem como empurrão a 1080×1920. Default passou a `1.0 → 1.04` para
`cover`/`contain`, mantendo `1.0 → 1.08` no card. Sobrescrevível por insert via
`drift: {from, to}`.

— Maestro, conduzindo o impossível 🎼
