# Ofício de motion — como cada elemento se move

Leia junto com `direction.md`, na Fase 2, antes de escrever inserts, cards,
headline, split ou qualquer cena HyperFrames. Os dois arquivos não se repetem:

| `direction.md` decide | `motion-craft.md` decide |
|---|---|
| **qual** transição entre cenas, por energia, humor e posição narrativa | **como** um elemento entra, assenta, vive e sai **dentro** de uma cena |
| composição do quadro e tipografia | velocidades, curva por papel, cascata, tempo de leitura |
| a regra das 60–70% (uma primária + acentos) | câmera virtual dentro da cena, speed ramp no corte |

**Origem:** adaptado de `LeiteZ/fluxo-de-edicao` (`guias/oficio-motion.md`, MIT).
A fonte diz "medido em referências profissionais", mas não traz dado. **Todo
número aqui é hipótese** (decisão D5) até ser medido num render do Prisma, e
cada seção diz o que já foi medido. Gosto do cliente (quanto overshoot, quanta
vida, quanto zoom) não está aqui: está no estilo do projeto (gate de Estilo) e,
quando existir, no perfil do cliente.

Valores em segundos, com os frames a 30 fps e 24 fps (as duas taxas do Prisma).

---

## Quando este arquivo e o `direction.md` parecem discordar

| Ponto | Resolução |
|---|---|
| `direction.md` regra 1: "a transição É a saída; animar a saída é proibido, salvo na última cena" | Vale para a **cena** que sai por uma transição. Um **elemento** que sai enquanto a cena continua (card sobre o apresentador, etiqueta, legenda de ênfase) tem saída própria — §5 |
| `direction.md`: "ancore às bordas; centralizado-e-flutuante é padrão de web" | A composição decide a âncora. **Se** o bloco é centrado (headline, linha de palavras), ele se mantém centrado enquanto cresce (§5). Se é ancorado numa borda, cresce a partir da borda |
| `direction.md` regra 3: no máximo 2 animações com a mesma curva por cena | A tabela de curva por papel (§2) é o ponto de partida; quando ela repetiria a mesma curva 3×, troque dentro da família (`expo.out` ↔ `power3.out`) |
| `direction.md`: `spring()` para entradas de elemento | Use `spring()` quando o estilo quer overshoot e a duração pode emergir da física. Use bezier (§2) quando a entrada tem de cair **na palavra** com duração exata |

---

## 1. Hierarquia de velocidade

| Camada | Duração | 30 fps | 24 fps |
|---|---|---|---|
| Elemento entrando | ~0,5 s (opacidade e foco mais curtos, 0,2–0,33 s) | 15 f (6–10 f) | 12 f (5–8 f) |
| Elemento saindo | ~0,25 s — **mais rápido que a entrada** | 8 f | 6 f |
| Texto | 0,2–0,4 s por palavra | 6–12 f | 5–10 f |
| Câmera (virtual ou `zoomAuto`) | lenta: 1,5–3,5 s | 45–105 f | 36–84 f |
| Secundário | contínuo | — | — |

O contraste é o que dá fluidez: **entrada rápida sobre câmera lenta**.

## 2. Curva por papel

| Papel | GSAP | Remotion (`Easing.bezier`) | Duração |
|---|---|---|---|
| Entrada: posição/escala | `power3.out` (overshoot, se houver, é do estilo) | `(0.25, 1, 0.5, 1)` | ~0,5 s |
| Entrada: opacidade e foco | `expo.out`, mais curto | `(0.16, 1, 0.3, 1)` | 0,2–0,33 s |
| Saída de elemento | `power3.in`, um movimento só (cai ou encolhe + desfoque + fade) | `(0.5, 0, 0.75, 0)` | ~0,25 s |
| Grupo se reorganizando: palavras / cards | `power3.out` / `power2.out` | `(0.25, 1, 0.5, 1)` / `(0.33, 1, 0.68, 1)` | 0,5 s / 0,7 s |
| Câmera abrindo (aproximação/recuo) | `power2.out` (suave) a `circ.out` (freia cedo) | `(0.33, 1, 0.68, 1)` / `(0, 0.55, 0.45, 1)` | 1,5–3,5 s |
| Câmera depois de assentar (deriva) | linear ou `sine.out` | `Easing.linear` / `(0.61, 1, 0.88, 1)` | até o fim da cena |
| Punch num detalhe | in-out assimétrico, pico em ~30% (`expo.in` curto + `expo.out` longo) | `(0.7, 0, 0.84, 0)` + `(0.16, 1, 0.3, 1)` | 1–1,7 s |
| Passo de carrossel, troca de item | `power4.inOut` | `(0.83, 0, 0.17, 1)` | ~0,43 s + ~0,23 s parado |
| Escurecer/desfocar o fundo | `power1.inOut` | `(0.45, 0, 0.55, 1)` | ~0,47 s |
| Título solene acendendo | opacidade + desfoque, `power2.out` | `(0.33, 1, 0.68, 1)` | ~0,67 s |
| Progresso, rotação, seguir barra | linear | `Easing.linear` | — |

**Nada se move linearmente**, exceto a deriva da câmera e o que segue um progresso.

**Equivalências medidas** (2026-11-03, erro máximo da bezier contra a função
GSAP exata, em % do percurso): `power2.out` 0,3 · `power3.out` 0,6 ·
`power4.out` 1,1 · `expo.out` 1,2 · `circ.out` 0,2 · `sine.out` 0,8 ·
`power2.in` 0,3 · `power3.in` 0,6 · `power4.in` 1,1 · `expo.in` 1,2 ·
`power1.inOut` 0,5 · `power2.inOut` 1,0 · `power4.inOut` 3,2.
Lembrete: no GSAP, `power1` = Quad, `power2` = Cubic, `power3` = Quart,
`power4` = Quint.

> Os presets do `direction.md` (`snappy`, `smooth`, `dramatic`, `luxe`) usavam
> a bezier da curva um nível abaixo — até 16,9% de erro no `dramatic`.
> **Corrigidos em 2026-11-03 (D6)** com as mesmas equivalências desta tabela;
> valem para os próximos vídeos, os entregues ficam como aprovados.

## 3. Câmera virtual (dentro da cena ou do insert)

- **Aproximação e deriva em camadas separadas:** dois contêineres aninhados — o
  de fora faz a aproximação com ease-out, o de dentro a deriva linear a cena
  inteira. Encadear um ease-out que termina parado com um linear depois faz a
  velocidade cair a zero e voltar: o zoom **engasga**.
- **Seguir** o que progride (barra, linha do tempo) em velocidade constante.
- **Três formas de mudar o zoom** (do aberto para o close e de volta), cada uma
  para um momento:
  1. **Corte seco:** o close entra ~5–10% maior e assenta (~0,3 s), com um flash
     no corte;
  2. **Zoom contínuo com speed ramp, sem corte:** acelera (`power4.in`) e freia
     (`expo.out`) com as velocidades casadas (§4), pico em ~30%, flash no pico;
  3. **Corte com speed ramp leve:** o plano que sai acelera na direção do zoom
     nos últimos ~0,2 s (+5%, `power4.in`), corta no frame mais rápido, e o que
     entra já chega andando na mesma direção e freia (~0,42 s, partindo ~6% antes
     do alvo, `expo.out`). Sutil.
  - Num elemento (ícone, card), a aproximação contínua lê melhor; um corte seco
    ali parece troca de cena.
  - O `zoomCuts` do Prisma é a forma 1. As formas 2 e 3 ainda não existem no
    template — ver F7.2 do plano.
- **Câmera fluida:** o que mais parece amador é a câmera "truncada" — vários
  movimentos que começam e terminam parados em sequência. Um movimento emenda no
  outro sem a velocidade chegar a zero. Mais suave não é mais lento. Um recuo que
  revela segue recuando devagar, no mesmo sentido.
- **O conteúdo principal entra centralizado desde o começo**, mesmo com o zoom
  maior; o recuo revela o resto.

## 4. Troca de cena por speed ramp (`beat_edit`, `speed_ramp`, transições HF)

- A cena acelera numa direção (`power4.in`, ~1 s), desfoque direcional no pico,
  **corte no frame mais rápido**, a cena nova chega na mesma direção e velocidade
  e freia (`expo.out`, ~1,5 s). A chegada é mais longa que a saída e **nunca
  para seco**.
- **Casar a velocidade no corte** (matemática exata, não hipótese):
  velocidade final de `power4.in` = **4·D/T** (derivada de t⁴ em 1);
  velocidade inicial de `expo.out` = **10·ln2·D/T ≈ 6,93·D/T** (derivada de
  1−2^(−10t) em 0). Exemplo: 700 px em 1 s → 2.800 px/s; para chegar com a mesma
  velocidade em 1,5 s, D ≈ 2.800 × 1,5 / 6,93 ≈ 606 px.
- **Percurso:** o conteúdo ainda tem de estar no quadro no corte. A fonte cita
  ~700 px na saída e ~560 px na chegada em 1080p; com ~1.300 px o conteúdo some
  antes do corte e sobram frames vazios.
- A cena nova já chega com o conteúdo principal; os detalhes entram em cascata
  ~0,2 s depois.
- **Movimento rápido no mesmo mundo:** um pouco mais longo que ~0,67 s; mais
  curto fica duro.
- **Corte com assentamento:** a cena nova entra ~5% maior e assenta em ~0,2 s.

## 5. Entradas, saídas e leitura

- **Entrada:** ~0,5 s; opacidade e foco antes da posição. Do zero (ou de ~60% da
  escala com opacidade 0) ao tamanho final.
- **Cascata e sobreposição:** 2–4 f entre irmãos; o próximo movimento começa
  antes de o anterior assentar. É isso que faz tudo virar um movimento só.
- **Grupo que chega em sequência fica centrado como um grupo só** (quando a
  composição é centrada): o primeiro nasce no centro; quando o seguinte chega, o
  grupo inteiro desliza para recentrar. Nunca deixar o primeiro sozinho,
  deslocado, esperando o espaço do outro.
- **Linha no ritmo da fala:** palavras entram uma a uma, **no tempo da palavra
  na transcrição**, e a linha desliza a cada palavra para continuar centrada
  (~0,5 s, `power3.out`). Alternativa: a linha toda aparece apagada e cada palavra
  acende quando é dita. Revelar palavra por palavra **sem** recentralizar deixa o
  começo torto: nunca. Títulos curtos entram inteiros, e a palavra-chave ganha
  punch na hora em que é dita.
- **Sincronia:** o elemento que representa uma palavra entra **na palavra**, não
  num intervalo fixo. Quando a borda do insert coincide com um corte, use o
  **tempo do corte** (`jcut_timeline`, exato desde a F0.2 de 2026-11-03; em
  projeto renderizado antes disso, use o `segments.json` medido — ver SKILL.md,
  J-cut), não o da palavra — a folga das bordas põe o
  corte ~0,1–0,3 s antes da 1ª palavra e o insert vazaria no segmento vizinho.
- **Saída do elemento:** ~0,25 s, `power3.in`, um movimento só — ou carregada
  pelo movimento da câmera ou pela troca de cena.
- **Tempo de leitura:** letreiro não sai colado na última palavra. Sem outra
  animação ou corte logo depois, ele segura **~1–1,5 s depois da palavra final**.
- **O herói do fim tem tempo de ser visto** (logo, revelação). Sem nada depois,
  pode avançar um pouco sobre o take seguinte.
- **Alinhamento:** cada elemento alinhado ao que acompanha (etiqueta ao ícone,
  linhas de um bloco entre si). Desalinhamento é o que mais passa amadorismo.

## 6. Texto vivo

- Texto digitado: ~23 caracteres/s; cada letra entra com borda suave (opacidade
  + desfoque); várias linhas em paralelo com 3–4 f de defasagem.

## 7. Camadas e profundidade

- **Profundidade de campo para dar foco:** desfocar o que não é o assunto.
- **Fundo e frente se movem com sutileza, na periferia** (deriva lenta, cantos e
  bordas). Nunca atravessam o quadro em direção à área de interesse nem se
  misturam à animação principal.

## 8. Movimento secundário

- O que continua se movendo depois que tudo entrou tem propósito (fluxo, dados,
  energia). Quanta vida o estilo quer é do estilo.
- Luz ou pulso correndo por um trilho ou conector passa **por trás** dos nós.

## 9. Sobre o apresentador

- Elementos curtos e pontuais (etiqueta, ícone, número, ênfase embaixo) com
  fundo transparente.
- **Flash em sobreposição fica no próprio elemento.** Flash de quadro inteiro
  sobre o apresentador parece bug. (O flash de quadro inteiro do `beat_edit` é
  para montagem sem apresentador — lá está certo.)
- **Sobreposição lateral grande:** o rosto vai para o terço do lado oposto
  enquanto ela está na tela e volta ao centro depois (F7.2).
- **Cards que entram embaixo:** o rosto sobe um pouco, para não ficar atrás.
- Texto: 28 px mínimo em 1080p (56 px em 4K) e dentro de 80% do quadro.

## 10. No render ou na pós — uma vez só

- **No render:** câmera e zoom dentro da animação, profundidade de campo,
  desfoque de movimento, brilho, luz, partículas.
- **No look do vídeo inteiro** (grão, lente, glitch, textura): uma vez, num
  lugar só. No Prisma, `film_look.py` e as camadas de grão do `cinema_edit` são
  esse lugar — não repita grão dentro de uma cena HF que depois passa pelo
  `film_look`, senão soma em dobro.

## 11. Evitar

Tudo entrando com o mesmo fade e deslize; vários protagonistas ao mesmo tempo;
câmera que para e recomeça em sequência; conceito que serviria para qualquer
vídeo.

## 12. Como saber se ficou fluido — e o que fazer quando não ficou

- **Meça o render, não a intenção:** `contact_sheet.py` nos frames de entrada,
  assentamento e saída; conte os frames de cada movimento e compare com §1–§2.
  Ajuste até bater.
- **"Básico", "sem vida", "amador" pede refazer, não retocar.** Releia o
  estilo/referências, diga em uma frase a nova direção de cada insert e construa
  de novo. Retocar um conceito fraco gasta rodada e continua fraco.

---

## O que já foi medido no Prisma

| Item | Status |
|---|---|
| Equivalências GSAP → bezier (§2) | ✅ medido 2026-11-03 (≤1,2%, `power4.inOut` 3,2%) |
| Casamento de velocidade 4·D/T ↔ 6,93·D/T (§4) | ✅ derivação exata |
| Divergência de curvas no `direction.md` | ✅ medida, decisão pendente |
| Durações de §1, cascata, tempo de leitura, percursos de §4 | ⏳ hipótese |
| Troca de layout do split (Cayenne reel_01 entregue) | ✅ medido 2026-11-03: **corte seco, 1 frame**, na entrada e na saída — é corte por design (com flash), então §1/§5 NÃO se aplicam a ela; valem para elementos que entram dentro da cena (card, texto, ícone) |
