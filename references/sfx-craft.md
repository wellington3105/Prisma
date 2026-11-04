# Ofício de SFX — onde entra som, qual, e como se empilha

Leia antes de escrever `sfxCues` ou `transitions[].sfx` no `edit-data.json`, e
antes de escolher entre o kit sintetizado e o catálogo Epidemic. A mixagem
(ducking, loudnorm, stems) é do `deliver_mix.py` — ver `shortform.md`
"Entrega com mixagem de verdade". Aqui fica a decisão de **onde** e **qual**.

**Origem:** adaptado de `LeiteZ/fluxo-de-edicao` (`guias/etapa-sfx.md`, MIT).
Tendência, não regra, nas escolhas criativas; as regras técnicas (sincronia,
nível, repetição) podem ser firmes. Números são hipótese até medidos (D5).

---

## 0. O que o `at` significa no Prisma (leia primeiro)

`deliver_mix.py` coloca cada cue com `adelay` no **primeiro sample do arquivo**
(`deliver_mix.py:232`). O `at` é **onde o arquivo começa**, não onde o som bate.

> **Escreva o `at` como o tempo do EVENTO e declare o alinhamento** —
> `"align": "peak"` (impacto, whoosh, whip), `"end"` (riser), ou nada (clique,
> pop, ding: começa no evento). `deliver_mix.py` mede o pico/duração do próprio
> arquivo (`helpers/sfx_peak.py`) e adianta o início; `transitions[].sfx` já é
> `peak` por padrão (`sfxAlign` para mudar). `cinema_edit.py` aceita o mesmo
> `align: "peak"`.

Um whoosh com pico em 0,4 s posto em `at = evento` SEM `align` soa 0,4 s
atrasado — 12 frames a 30 fps. Medido 2026-11-03 na cópia do PPF X6: os 4
whip-pans batiam **+9,4 frames** depois do corte; com o alinhamento pelo pico,
**+2 ms nos 4**. Cues antigos sem `align` continuam pelo início (os whooshes do
PPF X6 já estavam compensados à mão e não mudam).

---

## 1. O som segue o que se vê

- **Evento visível pede som; o que não aparece, não.**
- **Jump cut sem mudança de plano é para ser invisível:** em geral, sem som.
- **Corte, zoom ou câmera sob uma tela cheia não aparece:** sem som.
- **Movimento visível de câmera é como uma animação:** whoosh com o pico onde a
  câmera **freia** (chegada) ou no frame mais rápido (speed ramp); impacto no
  punch de ápice. Aproximação lenta (`zoomAuto`) e trava no rosto não pedem som.

## 2. Um protagonista por momento — e as camadas de um momento forte

Cada evento tem **uma** camada principal; no máximo **3 camadas**, cada uma numa
faixa de frequência diferente. Dois sons do mesmo tipo no mesmo frame embolam e
tiram o ataque.

| Camada | Papel | Quando |
|---|---|---|
| **principal** | diz o que aconteceu (impacto, whoosh, pop, clique) | sempre |
| **grave** | sub por baixo do impacto, dá peso | só nos momentos fortes — usado sempre, perde efeito; e some no celular sozinho (ver §8) |
| **apoio** | prepara ou acompanha (whoosh que leva ao impacto, riser que termina no evento) | antecipação |
| **doce** | agudo bem curto que define o ataque, baixo | quando o principal é grave demais para o celular |
| **cauda** | ambiência/reverb que segura o momento | raro |

## 3. Antecipação e resolução

- Riser e som reverso **constroem**; o impacto **resolve**. O riser termina no
  evento e corta seco.
- **Respiro:** nada de outros sons nos ~0,5 s antes do impacto. Às vezes o melhor
  som é tirar o som.

## 4. Escalada

- O **maior** impacto do vídeo vai no ápice do hook (a frase-chave). Antes dele,
  sons menores. No corpo, nada maior que isso.
- Densidade por trecho é do estilo. "Um whoosh em cada corte" cansa em dez
  minutos: varie a intensidade.

## 5. Sincronia

| Som | O que cai no frame do evento |
|---|---|
| impacto | o **transiente** |
| whoosh de elemento ou de troca | o **pico** — no frame da troca ou da chegada (quando o elemento freia), não no 1º frame do movimento |
| whoosh de movimento de câmera | o pico, perto do começo do movimento |
| pop, clique, ding | o **início** do arquivo |
| riser | o **fim** do arquivo (corta seco no evento) |

Para casar com a percepção, um som pode vir **1 frame adiantado**; camadas de
apoio escalonadas em 1–2 frames dão profundidade.

## 6. O som combina com o movimento e com o material

- Grande e lento → whoosh grave e longo. Pequeno e rápido → som curto e agudo.
- Papel pede papel; tecnologia e IA, glitch e interface digital; cursor,
  clique; check, ding; vidro (a moldura prisma), `glass_ping`.

## 7. Variação

- **Não repetir o mesmo arquivo em ~20 s.** Packs com variações existem para isso;
  o Epidemic devolve variações por busca (`epidemic_music.py sfx`).
- **Exceção: assinatura sonora.** Um som que É a marca de um elemento recorrente
  (o `glass_ping` de cada moldura prisma) repete de propósito — é o que faz a
  moldura ser reconhecida. Declare no `note` do cue (`"assinatura"`) para a regra
  não acusar. Só um som por vídeo tem esse direito.

## 8. Nível — e o alto-falante do celular

- Efeito **bem abaixo da voz**. Nada mais alto que a voz, salvo um momento
  intencional.
- Hoje o `volume` de cada cue é **absoluto** (ex.: transições a 0,18). Nivelar
  pela loudness da voz, com alvo por camada, é a F3.3. Até lá: confira no stem
  (`deliver_mix.py --stems`) e no celular.
- **Medido no Prisma (2026-10-30):** `sub_drop` e `ui_tick` sozinhos somem no
  alto-falante do celular; o kit "audível no celular" (`impact`, `glass_ping`,
  `whoosh_air`, `whip_hit`, `riser_tonal`) tem energia em 150 Hz–8 kHz. Grave
  só como camada **sob** um principal audível.

## 9. Kit sintetizado ou catálogo Epidemic?

| Use o kit `sfx_synth.py` quando… | Use o Epidemic quando… |
|---|---|
| o som é do vocabulário do kit (impacto, whoosh, riser, ping, whip) | o **material** pede um som real (papel, porta, motor, teclado, multidão) |
| precisa de licença zero e resultado idêntico em todo render | precisa de **variação** para não repetir em 20 s |
| é cinema-motion com o kit já calibrado | o estilo pede textura que síntese não faz (foley) |

Do Epidemic: `sfx "<descrição em inglês>"` → ouvir o `preview` → `sfx-download`
para `remotion/public/sfx/` → **conferir no alto-falante do celular** antes de
trocar um som do kit (a medição de §8 vale para o kit, não para o catálogo) →
registrar no `media_ledger.py`.

## 10. Faltou som?

Não force um ruim: use o melhor possível ou deixe sem, e anote no `project.md`
qual som faltou (o Epidemic resolve na próxima vez).

## 11. Auditoria de 2026-11-03 (o que estas regras acharam em projetos reais)

Medido lendo `edit-data.json` + o pico de cada arquivo (envelope RMS de 10 ms),
sem alterar nada:

| Projeto | Sons | Pico não descontado | Repetido < 20 s | Observação |
|---|---|---|---|---|
| Deocar | 3 (cliques de transição) | 0 | 1 (`cut-click`, 7 s) | cliques têm pico em 0 s — posicionamento certo |
| PPF X6 | 18 | **4** | 5 (`glass_ping` ×4 = assinatura, `whoosh_air` ×1) | os whooshes dos inserts já estavam compensados à mão (pico 50 ms depois, dentro de 2 f) |

**Defeito real encontrado:** os 4 "picos não descontados" são todos
`transitions[].sfx = whip_hit.wav`. O pico visual do whip-pan é o frame do corte
(`CustomGraphics.tsx`, *whiteout* em `c`), o som começa no mesmo frame
(`CustomGraphics.tsx:249` `CutSfx` e `deliver_mix.py:134`) e o golpe do
`whip_hit.wav` está em **0,29 s** → **o som bate ~9 frames depois da imagem em
todo whip-pan**. Com `cut-click` (pico em 0) não acontece. **✅ Corrigido (F3.0):**
o som de transição desconta o tempo até o pico do próprio arquivo — medido no
stem de SFX da cópia do PPF X6: 4/4 whips a +2 ms do frame do corte.

Os SFX do `beat_edit.py` usam atrasos FIXOS por arquivo (ex.: −0,16 s no
`whoosh-short`), calibrados à mão: certos para aqueles arquivos, errados se o
arquivo mudar. Ao trocar um som ali, use `sfx_peak.peak_time()`.

## 12. Ferramentas (F3.1–F3.3)

- **`sfx_index.py`** mede todas as bibliotecas (pico, duração útil, forma,
  `align` sugerido, brilho, queda no celular). Use o `align` dele no cue.
  Medido 2026-11-03: `whoosh-short` tem pico em 0,16 s — o −0,16 s escrito à mão
  no `beat_edit` estava certo; `whip_hit` 0,30 s.
- **`sfx_events.py <edit>`** faz o rascunho de `sfxCues` a partir dos eventos
  visíveis do `edit-data`, com estas regras já aplicadas. Revise e ajuste por
  gosto; o rascunho só existe para nenhuma regra técnica ser esquecida.
- **Celular, medido no índice:** a queda do pico mede o **caráter** (quanto do
  som o alto-falante joga fora), não se ele é ouvido. `impact-bass-1.mp3` cai
  21 dB, mas o que sobra está a −20 dBFS, no nível de `chime`/`click1`: o grave
  some, o ataque fica ("só o ataque"). Audibilidade é questão de mix — compare
  `phone_peak_dbfs` entre os sons do cue. A fração de energia enganava mais
  ainda: dava "0%" para o `impact.wav` (muito sub) e ele soa.
- **O flash do `beat_edit` agora é o `impact.wav` do kit** (D9, 2026-11-03).
  O `impact-bass-1` não é um golpe: é um drone de sub de 2 s em −1 dB de 0,1 a
  1,0 s — em fone/TV cobre voz e música; no celular vira ataque fino com cauda.
  Mesmo volume, mesmo ataque no celular (−13,0 vs −13,4 dB).
- **Golpe com sub: alinhe pelo ATAQUE, não pelo pico.** O `peak_s` do
  `impact.wav` (0,05 s) é o sub; o transiente está em 0,000–0,015 s. Com
  `align: "peak"` o golpe soou 50 ms ANTES do flash (medido no mix). Áudio
  adiantado se percebe a partir de ~45 ms; atrasado, só a partir de ~125 ms
  (ITU-R BT.1359) — na dúvida, o som chega depois, nunca antes.

## 13. Checklist antes de mostrar

- [ ] cada cue tem **papel** (principal/grave/apoio/doce/cauda) e **alinhamento**
  (pico | início | fim) declarados — no campo `"note"` do cue;
- [ ] `at` já descontou o tempo até o pico nos impactos e whooshes (§0);
- [ ] nenhum evento sem principal; nenhum par de principais colados;
- [ ] nenhum arquivo repetido em 20 s;
- [ ] respiro de 0,5 s antes do maior impacto;
- [ ] nenhum som sob tela cheia nem em jump cut invisível.
