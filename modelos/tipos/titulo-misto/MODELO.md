# Título misto (três vozes) + cards voando

## O que é
O gancho de um Reel de fala: um trecho de 3–5 s do apresentador com um título em três vozes por cima.
Duas palavras pequenas em sans emolduram o título; uma **palavra gigante** e pesada na cor de acento nasce
como um brilho borrado com blocos de pixel, anunciada por um risco que cai do topo, e fica nítida; a
linha de baixo entra palavra por palavra, com uma palavra opcional em serifada itálica na cor de acento;
até dois cards de foto voam do canto inferior esquerdo com um flash de luz e param inclinados.
O som do trecho é o do próprio clipe. Engenharia reversa de um Reel de referência (estudo; F3 em
`Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`), com nossas fontes (Poppins 900/600,
Lora itálica) e curvas medidas. A tinta das palavras pequenas (escura ou branca) sai do fundo do trecho.

## Quando usar
- Abrir um Reel de fala com uma promessa forte de uma palavra ("Cayenne", "Financiamento", "Garantia").
- Quando há uma prova visual para mostrar junto (foto do carro, print de avaliação): vira o card.

## Quando não usar
- Palavra gigante longa (mais de ~10 letras) ou frase inteira: perde o impacto e encolhe.
- Fundo muito poluído atrás do título: escolha um trecho com céu/parede ou suba a `altura`.
- Mais de uma vez no mesmo vídeo: é o gancho, não a legenda.

## Contenção
- Uma palavra gigante, no máximo duas pequenas, uma linha de baixo, no máximo um acento itálico e dois cards.
- Conta como 1 acento no limite de 3 do vídeo.
- SFX: um "whoosh" curto no risco e um impacto seco quando a palavra fica nítida (Fase 2/3 do vídeo).

## Aplicar
```
python helpers/modelos.py apply titulo-misto <pasta>/edit --param video=<pasta>/edit/cut.mp4 --param ate=4   --param esquerda="O carro" --param direita=certo --param palavra=Cayenne   --param sub="pela metade do preço" --param acento=metade --param cards=foto.jpg
python helpers/cenas.py render <pasta>/edit/cenas/titulo-misto     # -> out/render.mp4 (troca os 4 s do início)
```
