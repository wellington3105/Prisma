# PRISMA — identidade

Marca da interface de edição (antes: Edvid). Definida em 2026-08-18.

## O nome

Um prisma decompõe a luz em partes mensuráveis. É o que a ferramenta faz com o
material: separa voz de música (carve), take de take, pausa retórica de dead air,
imagem de som — mede cada parte, e só então recompõe.

## A marca

`assets/preview/prisma-logo.svg` (símbolo + nome) e `prisma-mark.svg` (favicon).

**Uma abertura de câmera**, não um triângulo de refração. A primeira versão foi
literal — prisma com raios coloridos — e lia como ilustração de livro de física.
Um diafragma diz "cinema" antes de você terminar de olhar, que é o trabalho de
um logotipo.

Três coisas que só apareceram renderizando em tamanho grande:

1. **As lâminas precisam ser construídas, não desenhadas à mão.** A segunda
   versão escreveu seis triângulos um a um e eles não ficaram congruentes — as
   lâminas discordavam sobre onde ficava a íris. Hoje UMA lâmina é definida em
   `<defs>` e rotacionada 6× por 60°: a geometria está certa por construção.
2. **Lâmina translúcida some.** Na segunda versão as lâminas de aço estavam em
   opacidade 0.42–0.55 e desapareciam no fundo; a íris virava duas cunhas
   coloridas flutuando num anel. Hoje toda lâmina é metal com gradiente real, em
   dois tons alternados que dão profundidade sem que nenhuma suma.
3. **Cor como reflexo, não como preenchimento.** Cunhas laranja e azul chapadas
   viram gráfico de pizza. O espectro entra como **arco na borda externa** de
   dois lados opostos — duas linhas, e a marca fica dita.

A abertura central é pequena (r=4.6 no logo) com um arco especular no canto
superior esquerdo. Grande demais, o vazio vira o assunto; sem o brilho, é um
buraco em vez de vidro.

## Paleta — espectro sobre neutro

```
--spec-1  #ff8a3d   acento do app, estado ativo
--spec-2  #ffd166   atenção
--spec-3  #5fd6b4   confirmação, salvo
--spec-4  #7aa8ff   informação
--olive   #80cec0   identidade de áudio (fósforo da forma de onda)
```

Superfícies genuinamente neutras (`--bg0 #07080a`, `--bg1 #0d1013`): um cinza
com tinta compete com o espectro; um neutro deixa ele ler.

**A regra:** o cromo é cinza e a cor é reservada para ESTADO. A paleta antiga
punha laranja, teal e verde-oliva com a mesma força e acendia a página com dois
brilhos coloridos vindos de cantos opostos — isso lê como "três cores de marca",
não como refinamento.

O fundo hoje é **uma** dispersão lançada do topo, na ordem do espectro, com cada
parada entre 0.030 e 0.055 de opacidade (era 0.10/0.09). Nessa força você lê
profundidade, não cor.

## Superfícies

Painel de sala de correção é **placa usinada**, não vidro fosco: aresta superior
pegando a luz da sala (`inset 0 1px 0`), corpo fosco, sombra funda o bastante
para descolar do fundo. O realce interno é o que vende — sem ele, blur sozinho lê
como card de site.

Faixas da timeline são **rebaixadas** (`inset 0 1px 2px`), como canal escavado no
console. É como Avid e Resolve desenham.

## Detalhes que valem a regra

- **A agulha é 1px, não 2px.** Ela marca um frame exato; 2px num zoom de
  1px/frame já é ambiguidade. Uma linha de luz com halo lê mais nítida E mais
  visível que 2px de cor chapada.
- **A aba ativa não muda de tamanho.** Antes crescia fonte e padding, o que
  empurrava as outras abas a cada troca. Hoje o estado é um filete espectral na
  borda superior: o layout fica parado e a cor faz o trabalho.
- **Rótulos em caixa alta com tracking largo**, peso 600 e 11.5px — registro de
  painel de instrumento, não de navegação web.
- **A forma de onda é ciano de fósforo**, não verde-limão. Uma forma de onda é
  uma MEDIÇÃO, e todo medidor de áudio de sala real é de tom frio.
- **Botão primário é sólido com aresta acesa**, não gradiente saturado. Gradiente
  laranja é a coisa mais "web app" que existe numa sala de edição.

## Manutenção

Os NOMES das variáveis foram mantidos (`--orange`, `--teal`) como apelidos dos
tokens novos: ~900 referências resolvem por eles, então a repintura foi troca de
token, não reescrita.

**Cuidado com literais.** Depois de repintar os tokens, 30 valores hardcoded
ainda carregavam a marca antiga espalhados pelo CSS. Uma paleta que vive metade
em token e metade em literal não é paleta — quem mudar `--spec-1` move parte da
interface e não o resto. Confira com:

```bash
grep -nE "9, *181, *183|255, *119, *19|168, *194, *43" assets/preview/app.css
```

O servidor precisa de `.svg: image/svg+xml` no dicionário MIME
(`preview_server.py`); sem isso o SVG chega como `application/octet-stream` e o
navegador mostra o texto alternativo no lugar da marca.
