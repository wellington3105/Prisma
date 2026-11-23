# Card de ficha técnica

## O que é
Uma cena inteira, sem cortes, de 10,5 s (6,5 s sem frase): um card claro no formato 3:4 com a foto
do carro, até três pílulas de ficha (cor, 0–100, câmbio…), o nome, a versão em cinza, uma frase e o @
da loja. Uma câmera contínua conta o card: ele cresce com um flash de exposição, a câmera entra na
foto, desce enquanto as pílulas chegam, para no nome (desfocado → nítido), recua até o card inteiro,
volta a fechar na frase enquanto ela é digitada e anda junto com ela, e recua para descansar.
Engenharia reversa de um reel de referência (estudo; F4 em
`Prisma-Suite/docs/analises/2026-11-22-formatos-de-referencia.md`), refeito com o nosso layout, a
Poppins e as curvas medidas (`softLand`, `whip`, `softInOut`).

## Quando usar
- Apresentar um carro do estoque em 10 s: abre um Reel, fecha uma montagem, vira story ou post.
- Quando a foto é boa e limpa (fundo claro, estúdio, carro inteiro ou 3/4 traseira).
- Série de estoque: o mesmo card para vários carros mantém a página coerente.

## Quando não usar
- Foto de pátio com fundo poluído: o card perde o ar de catálogo (recorte o fundo antes).
- Quando há fala: o card é uma cena muda; use como insert curto, não por cima do apresentador.
- Mais de três dados: o card respira; dado demais vira tabela.

## Contenção
- Até 3 pílulas; frase de até ~70 caracteres (duas linhas).
- Fundo da cena igual (ou muito próximo) ao fundo da foto.
- Nada de trilha ou SFX dentro da cena: o som entra na Fase 2/3 do vídeo que a usa
  (um "click" de obturador no flash e um tic seco por pílula combinam).

## Aplicar
```
python helpers/modelos.py apply card-ficha <pasta>/edit --param foto=carro.png \
  --param titulo="Jeep Compass" --param versao="Limited 2.0 Turbo" \
  --param pilulas="cor:Branco Polar:#f2f2f2|potencia:272 cv|cambio:automático" \
  --param frase="Tecnologia e conforto para qualquer caminho." --param assinatura=@sualoja
python helpers/cenas.py render <pasta>/edit/cenas/card-ficha     # -> out/render.mp4
```
