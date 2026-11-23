# Legenda com palavra-chave colorida

## O que é
Legenda discreta, palavra por palavra, pequena e branca no terço de baixo; só a palavra-chave do bloco (um
número, uma palavra pedida em `destaques` ou a mais longa com 8+ letras) cresce e ganha turquesa ("400m²",
"transformar"). Engenharia reversa de um Reel de referência (estudo; F6 em
`Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`).

## Quando usar
- Tour, apresentação de carro, depoimento: a imagem manda e a legenda só guia.
- Quando há números que vendem (preço, km, ano, potência).

## Quando não usar
- Reel de opinião com muita energia: use `legenda-mista`.
- Fundo claro e estourado no terço de baixo sem contraste (suba a `altura` ou escureça o trecho).

## Contenção
- No máximo uma palavra-chave por bloco; o resto não muda de cor.

## Aplicar
```
python helpers/modelos.py apply legenda-palavra-chave <pasta>/edit --param video=<pasta>/edit/cut.mp4 --param ate=30   --param legendas=<pasta>/edit/transcripts/cut.json --param destaques="garantia"
python helpers/cenas.py render <pasta>/edit/cenas/legenda-palavra-chave
```
