# Legenda mista (tamanhos e cores por palavra + risco)

## O que é
Legenda em blocos de 2–3 linhas sobre o peito do apresentador, cada palavra com tamanho e cor próprios:
palavras de ligação pequenas e brancas, a palavra forte do bloco grande e colorida (vermelho, amarelo, lima,
em ciclo de bloco em bloco), o resto médio e branco. Uma negação ganha um risco vermelho que corta "não é…"
no fim da segunda palavra. Se as palavras estiverem em linhas diferentes, cada linha recebe um traço.
As palavras entram no tempo da fala (a forte com mais força). Engenharia reversa
de um Reel de referência (estudo; F7 em `Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`).

## Quando usar
- Reel de fala com energia (andando, opinião, "o que ninguém te conta").
- Frases com contraste ou negação ("não é caro", "não é o motor"): o risco dá o tom.

## Quando não usar
- Vídeo institucional ou depoimento calmo: use `legenda-palavra-chave` ou a karaokê.
- Junto com outra legenda ou título grande no mesmo trecho.

## Contenção
- Uma palavra forte por bloco; números e `destaques` passam na frente.
- Blocos de até 5 palavras; pausa de 0,35 s abre bloco novo.

## Aplicar
```
python helpers/modelos.py apply legenda-mista <pasta>/edit --param video=<pasta>/edit/cut.mp4 --param ate=30   --param legendas=<pasta>/edit/transcripts/cut.json --param destaques="garantia|200 mil"
python helpers/cenas.py render <pasta>/edit/cenas/legenda-mista
```
