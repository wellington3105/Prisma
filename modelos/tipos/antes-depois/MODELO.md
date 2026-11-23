# Antes × depois (dois celulares + CTA, ou cru → editado)

## O que é
Um formato para mostrar o valor da edição (ou de uma reforma, uma estética automotiva, um polimento).
- **lado:** sobre um fundo escuro com vinheta, dois celulares tocam em sincronia: um "Antes" pequeno à
  esquerda e atrás, um "Depois" grande à direita, cada um com uma pílula branca no topo; embaixo, um CTA
  fixo em duas linhas (cinza pequena + branca forte).
- **sequencia:** tela cheia, o take cru primeiro, um corte seco com flash de um quadro e o editado; uma
  pílula no topo troca o rótulo no corte.
Engenharia reversa de dois Reels de referência (estudo; F1 e F8 em
`Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`).

## Quando usar
- Portfólio e captação: "olha o que a gente faz com o seu vídeo".
- Antes × depois físico: polimento, vitrificação, envelopamento, reforma de banco (gravados do mesmo ângulo).

## Quando não usar
- Quando o antes e o depois não são o mesmo trecho/ângulo: a comparação perde força.
- Vídeo de estoque comum (não há "antes").

## Contenção
- No lado: CTA curto (a linha forte com até ~20 caracteres); o som é um só (o do editado, por padrão).
- Na sequência: um corte só por exemplo; vários exemplos = várias cenas em fila.

## Aplicar
```
python helpers/modelos.py apply antes-depois <pasta>/edit --param antes=<pasta>/edit/cut.mp4   --param depois=<pasta>/edit/final.mp4 --param duracao=8 --param cta="Quer o seu carro assim?|Chama no direct"
python helpers/modelos.py apply antes-depois <pasta>/edit --param layout=sequencia --param corte=1.6 ...
python helpers/cenas.py render <pasta>/edit/cenas/antes-depois
```
