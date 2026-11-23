# Lyric edit de carro (letra 3D néon na batida)

## O que é
Sobre uma montagem de carro já cortada na batida, as palavras da música estouram uma a uma como títulos 3D:
extrudados, com contorno e brilho néon, em ciclo de ouro, ciano e branco com vermelho, inclinados em volta
do carro. Cada palavra entra em ~0,14 s (escala 1,7 → 1 com desfoque) na sua sílaba e sai crescendo. Nas
viradas de compasso o quadro ganha uma rajada de linhas de velocidade de mangá ou raios de meio-tom
(sunburst) girando, e no drop um flash branco de um quadro. O som é o da própria montagem.
Engenharia reversa de um lyric edit de referência (estudo; F5 em
`Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`). Ficaram de fora os interlúdios
desenhados por IA e os anéis de luz rastreando as rodas.

## Quando usar
- Montagem de carro com música cantada e um refrão de impacto (lançamento, carro esportivo, evento).
- Quando a letra conversa com o carro ("sem freio", "acelera"): a palavra vira o título.

## Quando não usar
- Música instrumental sem palavra que se sustente (use `montagem-na-batida`).
- Peça institucional ou de financiamento: o tom é de clipe, não de oferta.
- Letra com direitos não liberados para o uso: a música tem que estar licenciada (Epidemic etc.).

## Contenção
- Uma palavra por vez na tela (no máximo duas se encostarem); 1 palavra por sílaba forte, não por sílaba.
- Rajadas só nas viradas de compasso; flash só no drop. Conta como 1 acento no limite de 3.

## Aplicar
```
python helpers/transcribe.py musica.mp3 --edit-dir <pasta>/edit      # palavras com tempo (letra)
python helpers/beat_map.py musica.mp3 -o <pasta>/edit/beats.json
python helpers/modelos.py apply lyric-carro <pasta>/edit --param video=<pasta>/hf/out/render.mp4 --param ate=12   --param letra=<pasta>/edit/transcripts/musica.json --param beats=<pasta>/edit/beats.json
python helpers/cenas.py render <pasta>/edit/cenas/lyric-carro
```
