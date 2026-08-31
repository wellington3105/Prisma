# Direção de arte — transições, ritmo e movimento

Leia este arquivo na Fase 2, **antes** de escolher qualquer transição ou
animação. Ele responde *quando usar, quanto durar e com que curva* — o que
`shortform.md` e `longform.md` não respondem.

**Origem:** doutrina destilada do HyperFrames v0.4.3
(`dist/skills/hyperframes/references/`, lido em 2026-08-31), traduzida do
vocabulário GSAP/DOM para o modelo de render da Remotion. Ver § Procedência.

---

## A regra que governa todas as outras

> **Escolha UMA transição primária (60–70% das trocas) + 1–2 acentos.**
> Nunca uma transição diferente por cena.

Um vídeo com sete transições diferentes não parece rico — parece indeciso.
Os acentos existem para marcar mudança de tópico e clímax, e só valem porque
o resto é consistente.

---

## Energia → transição, duração, easing

Detecte a energia pelo conteúdo (transcrição + intenção), não pelo gosto.

| Energia | Contexto típico | Primária | Duração | Curva |
|---|---|---|---|---|
| **Calm** | marca, bem-estar, luxo | cross-warp, distorção térmica, blur crossfade | 0.5–0.8s | suave nas duas pontas |
| **Medium** | SaaS, corporativo, explicativo | whip pan, zoom cinematográfico, push slide | 0.3–0.5s | acelerada moderada |
| **High** | promo, lançamento, esporte | glitch, chromatic split, ridged burn, zoom through | 0.15–0.3s | muito acelerada |

**Blur por energia:** calm 20–30px (0.8–1.2s, com hold de 0.3–0.5s no pico) ·
medium 8–15px (0.4–0.6s) · high 3–6px (0.2–0.3s, sem hold).

---

## Presets nomeados

Vocabulário fechado do `TransitionSpec`. Cada preset é duração + curva.

| Preset | Duração | GSAP (origem) | Remotion (implementação) |
|---|---|---|---|
| `instant` | 0.15s | `expo.inOut` | `Easing.bezier(0.87, 0, 0.13, 1)` |
| `snappy` | 0.20s | `power4.inOut` | `Easing.bezier(0.76, 0, 0.24, 1)` |
| `smooth` | 0.40s | `power2.inOut` | `Easing.bezier(0.45, 0, 0.55, 1)` |
| `dramatic` | 0.50s | `power3.in` → out | `Easing.bezier(0.32, 0, 0.67, 1)` |
| `gentle` | 0.60s | `sine.inOut` | `Easing.bezier(0.37, 0, 0.63, 1)` |
| `luxe` | 0.70s | `power1.inOut` | `Easing.bezier(0.37, 0, 0.63, 1)` |

**Por que bezier e não `spring()`:** `spring()` é excelente para entradas de
elemento (overshoot natural), mas sua duração emerge da física — não se fixa em
0.2s. Transição entre cenas precisa de duração **exata** para casar com o corte
de áudio. Use `Easing.bezier` nas transições; reserve `spring()` para entradas
de elementos dentro da cena.

> **Não converta curvas no olho.** Os números de duração portam direto do
> HyperFrames; as curvas estão mapeadas acima. Qualquer curva nova precisa de
> equivalência escrita aqui antes do uso.

---

## Humor → transição (o *porquê*, não só o *quê*)

| Humor | Transições | Por que funciona |
|---|---|---|
| Quente / acolhedor | light leak, blur crossfade, focus pull, distorção térmica | Bordas suaves, lavagem quente. Nada afiado ou mecânico |
| Frio / clínico | squeeze, blinds, shutter, grid dissolve | O conteúdo transforma-se mecanicamente: comprimido, fatiado |
| Editorial | push slide, split diagonal, whip pan | Como virar uma página. Movimento direcional limpo |
| Tech / futurista | grid dissolve, glitch, chromatic split | Grid dissolve é a transição "dado" por excelência |
| Tenso / instável | glitch, VHS, ripple, ridged burn, domain warp | Instabilidade, colapso digital |
| Lúdico | elastic push, flip 3D, circle iris, swirl vortex | Overshoot, rotação, expansão |
| Dramático | zoom through, gravity drop, overexposure, lente gravitacional | Extremos de escala, peso e luz |
| **Premium / luxo** | focus pull, blur crossfade, cross-warp | **Contenção.** Menos é o efeito |
| Retrô / analógico | film burn, light leak, VHS | Imperfeição orgânica |

---

## Posição narrativa

A mesma transição vale coisas diferentes dependendo de onde cai.

| Posição | Uso | Duração |
|---|---|---|
| Abertura | Sua transição mais distintiva. Define a linguagem visual | 0.4–0.6s |
| Entre pontos relacionados | A primária, consistente. Não distraia | ~0.3s |
| Mudança de tópico | Algo **diferente** da primária. Sinaliza "nova seção" | — |
| Clímax / revelação | O melhor acento. O mais rápido ou o mais dramático | — |
| Desaceleração | Volte ao gentil. Deixe o espectador respirar | 0.5–0.7s |
| Encerramento | O mais lento e simples. Não introduza energia nova | 0.6–1.0s |

---

## Regras não-negociáveis

1. **A transição É a saída.** Animações de saída são proibidas, exceto na última
   cena. A camada que sai deve estar **plenamente visível** quando a transição
   dispara. Animar a saída *e* aplicar transição = os dois se anulam.
2. **Não comece em t=0.** Desloque a primeira animação em 0.1–0.3s. Delay zero
   lê como jump cut.
3. **Não use a mesma curva em tudo.** No máximo 2 animações independentes com a
   mesma curva por cena.
4. **Varie a duração deliberadamente.** A cena mais lenta deve ser ~3× mais
   lenta que a mais rápida.
5. **Não entre tudo pela mesma direção.** Alterne: esquerda, direita, escala,
   só opacidade, letter-spacing.
6. **Stillness depois de movimento é poderosa.** Nem toda cena precisa de zoom
   ambiente.

### Direção da curva (erra-se constantemente)

- **Entradas:** rápido → desacelera. Responsivo. É o padrão.
- **Saídas:** lento → acelera para fora.
- **Movimento entre posições:** suave nas duas pontas.

Curva de entrada aplicada a uma saída fica relutante; o inverso fica arrastado.

---

## Composição de quadro

Vídeo não é página web.

- **Dois pontos focais mínimos por cena.** O olho precisa de para onde ir.
- **Preencha o quadro.** Headline em 60–80% da largura.
- **Três camadas mínimo:** fundo tratado (glow, tipo gigante desbotado, painel
  de cor) · conteúdo · acentos (divisores, rótulos, barras).
- **Fundo nunca é vazio.** Preto sólido puro lê como "não carregou".
- **Ancore às bordas.** Centralizado-e-flutuante é padrão de web.
- **Use elementos estruturais.** Réguas e divisores criam caminho para o olho e
  animam bem (escala horizontal a partir de zero).

---

## Tipografia em movimento

- **Não pareie dois sans-serif.** Cruze a fronteira: serifada + sans, ou
  sans + mono.
- **Uma fonte expressiva por cena.** Uma atua, a outra recua.
- **Contraste de peso extremo.** 300 vs 900, não 400 vs 700 — precisa ser
  legível em movimento, num relance.
- **Tamanhos de vídeo, não de web.** Corpo: 20px mínimo. Headline: 60px+.
- **Fundo escuro:** texto claro sobre escuro parece mais pesado e mais junto.
  Compense: peso 350 em vez de 400, entrelinha +0.05–0.1, e ~0.01em de
  espaçamento em tamanhos display.

---

## Áudio-reativo — o alerta anti-clichê

O áudio fornece **timing e intensidade**. O vocabulário visual vem da narrativa.

| Sinal | Propriedade | Efeito |
|---|---|---|
| Graves | escala | Pulso na batida |
| Agudos | brilho / sombra | Intensidade do glow |
| Amplitude geral | opacidade, deslocamento vertical | Respiração, elevação |
| Médios | raio de borda, largura | Morfologia da forma |

**Nunca adicione:** barras de equalizador, analisadores de espectro, formas de
onda, notas musicais, sistemas de partículas genéricos, ciclo de cor arco-íris,
strobe branco nas batidas, orbes pulsantes abstratos.

Em vez disso: deixe o conteúdo guiar o visual e o áudio dirigir o
comportamento dele. Graves fazem o calor **crescer**. Agudos **afiam** o
contraste.

---

## Ritmo — o que a referência de 2026-08-31 mediu

Reel analisado (`instagram.com/p/Db_6Gc1s6O6`, 40.9s):

- **14 mudanças visuais em 41s** — uma a cada ~2.9s
- **Nenhum corte duro.** Score de cena máximo **0.39** (cortes duros passam de
  0.4). Todas as trocas são graduais.
- **Narração contínua**, sem pausa retórica longa.
- **Caption karaokê permanente**, palavra a palavra, amarelo sobre branco.

Densidade de referência para conteúdo de alta energia: **uma mudança visual a
cada ~3s**, sem corte duro visível.

---

## Procedência

Doutrina derivada do HyperFrames v0.4.3 (documentação, não código —
`@hyperframes/shader-transitions` não é publicado no npm). Traduzida de
GSAP/DOM para Remotion.

**Deliberadamente NÃO portado:** as *Shader-Compatible CSS Rules* do
HyperFrames (proibição de `transparent` em gradientes, `data-no-capture`, sem
`var()`). Elas existem porque aquele motor captura DOM→textura via html2canvas.
A Remotion renderiza a ThreeCanvas nativamente, no mesmo passe — essas
restrições não se aplicam ao Prisma.

Ver `OPUS-VFX-3D.md` § ÉPICO D.
