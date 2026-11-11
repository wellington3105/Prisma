# Crítico independente (Gauntlet)

Crédito: método adaptado de `echris6/motion-video-kit` (licença MIT, Copyright (c) 2026 echris6; `business-motion-film/references/gauntlet.md` e `critic-prompts.md`, commit e4b1c00), que por sua vez adapta o "Gauntlet Loop" (somethingbig.ai/gauntlet-loop). O texto abaixo é uma reescrita para o vocabulário do Prisma; o aviso MIT do original vale para as ideias e prompts derivados: *Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction ... provided the above copyright notice and this permission notice are included.*

## Quando usar

- **Opcional**: depois do render final da Fase 2 (ou da Fase 3 com mix), **antes** de mostrar à pessoa. Vale a pena quando o vídeo tem inserts, cards 3D ou SFX; num corte seco da Fase 1, o `verify_cut.py` basta.
- **Obrigatório** quando a pessoa reclama de qualidade geral ("básico", "genérico", "amador", "tá sem graça"): essa queixa não aponta um defeito, então quem construiu não sabe o que consertar. Rode o crítico ANTES de mexer em qualquer coisa e conserte a partir da lista dele.
- **Nunca** substitui os portões do Prisma (aprovação do `cut.mp4`, plano de inserts por número, Estilo). O crítico encontra defeitos; quem decide o que muda continua sendo a pessoa.

## A regra: quem construiu não julga

O construtor (esta conversa) enxerga o que pretendia, não o que está nos pixels. Por isso o crítico é um **subagente novo** (ferramenta Agent, sem herdar contexto) a cada rodada. Ele recebe só:

1. o **render** (caminho do MP4, `<edit>/final.mp4` ou o que `state.json` aponta em `finalVideo`) e o corte limpo para comparação;
2. as **medidas**: saída do `verify_cut.py`, `qa_mix.py`/loudness quando houver áudio mixado;
3. o **briefing aprovado**: as palavras da pessoa (literais), a estratégia confirmada, o plano de inserts aprovado (`i01…`), os picks do Estilo (`state.style`), o perfil do cliente se existir;
4. na rodada de verificação: o relatório da rodada anterior (`critica.md`).

Nunca entregue: a conversa de construção, a lista do que você acha que consertou, justificativas ("ficou assim porque..."). Ele tem de achar sozinho. O crítico extrai os quadros ele mesmo:

```
uv run python helpers/watch_video.py <final.mp4>                 # o que existe no vídeo, em folhas
uv run python helpers/contact_sheet.py <final.mp4> --times ... -o <scratch>/folha.png   # janelas densas
```

Janelas densas (1/30 s) em volta de cada transição, de cada insert `iNN` e do hook; folhas a cada 0,25 s no resto. Ele julga **pixels e medidas**, não intenções, e escreve o relatório num arquivo que você lê.

## Prompt: crítico do render (rodada 1)

```
Você é um crítico independente e duro. NÃO construiu este vídeo; julgue pixels e áudio medido, não intenções.

Artefato: <final.mp4> (<dur>s, <WxH>, <fps>fps, com áudio). Corte limpo para comparar: <cut.mp4>.
O que é: <formato: reel 9:16 / longform 16:9; assunto em 1 frase>. Cliente/perfil: <nome ou "nenhum">.
Pedido da pessoa (literal, obrigatório): <cole as palavras dela, inclusive a queixa>.
Plano de inserts aprovado: <lista iNN → tempo → o que mostra>. Estilo escolhido: <legenda, card 3D, trilha, transição>.
Medidas já feitas: <saída resumida do verify_cut.py / loudness>. Não repita; confirme ou conteste.

Método: ferramentas em helpers/ (watch_video.py, contact_sheet.py); quadros em <scratch>. Olhe: legendas (corte de palavra, cobrem o rosto, fora da área segura), inserts iNN (entram no tempo da fala? cobrem informação? repetem o mesmo layout?), cards (legíveis, colisão com legenda ou rosto), transições (pop, quadro em branco, texto sobre texto), trechos parados (diferença de quadro), vazios de composição, mix (voz sempre à frente, SFX no evento, trilha não some antes do fim).
Padrão-ouro: o que um editor profissional entregaria sem retrabalho; "genérico" conta como defeito se todos os inserts/cards tiverem a mesma cara.

Escreva em <edit>/critica_r1.txt (máx. 700 palavras):
1. Veredito por item, no formato `item | OK/REVISAR/REJEITAR | evidência (tempo, região, medida) | correção sugerida`. Itens: hook, cada iNN, legendas, cards, transições, mix, ritmo geral.
2. As 3 a 6 correções de maior impacto, concretas.
Seja direto, sem enrolação.
```

## Prompt: crítico de verificação (rodadas seguintes)

```
Você é um crítico independente; NÃO construiu este vídeo. Artefato novo: <final.mp4>. Relatório anterior: <edit>/critica_rN.txt. Os tempos podem ter se deslocado cerca de <x>s.
Para CADA item daquele relatório: CORRIGIDO / PARCIAL / AINDA PRESENTE, com tempo e evidência. Depois liste defeitos NOVOS (correções criam regressões: elemento coberto, z-order, texto cruzando legenda, quadro em branco). Confira o áudio em <tempo>.
Escreva em <edit>/critica_r(N+1).txt (máx. 450 palavras), terminando com ENTREGAR ou MAIS UMA RODADA (no máx. 3 correções).
```

Para uma rodada só de plano (antes de renderizar), use o mesmo formato sobre o plano de inserts: cronologia fiel à fala, cada insert com função distinta, nada que a pessoa não disse, o que é enchimento.

## Ledger `<edit>/critica.md` (somente acréscimo)

Nunca reescreva linhas antigas; cada rodada acrescenta. Uma linha por item:

```
| rodada | item | veredito | evidência | correção |
| 1 | i03 | REVISAR | 12,4-14,1 s: card cobre a boca; legenda colide | mover card (edit-data: highlights[2].y) |
| 2 | i03 | CORRIGIDO | 12,4-14,1 s sem colisão | - |
```

Vereditos: OK, REVISAR, REJEITAR (rodada 1); CORRIGIDO, PARCIAL, AINDA PRESENTE (verificação). Quem escreve o ledger é o orquestrador, copiando o relatório do crítico, sem adoçar.

## Rodadas e parada

- **Máximo 3 rodadas** de crítico por pedido (1 achados + 2 verificações). Parou antes se o veredito for ENTREGAR, se o que sobra for sub-quadro/cosmético, ou se a pessoa mandar parar.
- Corrija o **maior** defeito primeiro; um hook fraco não é compensado por um final bom.
- Depois da 3ª rodada, o que ainda estiver aberto vai à pessoa como limite honesto, com o ledger.
- O crítico mede o que lhe pedem: "ENTREGAR" não substitui a revisão da pessoa. Cada reclamação dela depois da entrega vira item novo na lista de checagem do prompt.

## Para onde cada correção volta

| Tipo de defeito | Destino |
|---|---|
| Posição, tempo, cor, texto de legenda/card/insert | `public/edit-data.json` (campos existentes), re-render da Fase 2 |
| Insert errado, repetido ou ausente | plano de inserts: `inserts_plan.py` (`strike`/`set`), nova aprovação por número; nada de editar `inserts[]` direto |
| Escolha de Estilo/trilha/SFX | Estilo (`state.style`) e `sfx_events.py`; aprovação humana se mudar o look |
| Corte, pausa, take | volta à Fase 1 (EDL), com novo `verify_cut.py` e novo gate |
| Defeito que se repetiria em outros vídeos | `uv run python helpers/learnings.py add <edit> --phase <fase> --text "<o que o crítico pegou>"`; só vira regra da skill/perfil quando a pessoa pedir "aplica os aprendizados" |

Anotar no `learnings.py` não muda a skill. Mudar a skill ou o perfil continua exigindo pedido da pessoa.
