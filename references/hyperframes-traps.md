# HyperFrames — armadilhas (o que já está no código, o que falta, o que foi medido)

Leia antes de escrever ou mudar qualquer cena HyperFrames: `beat_edit.py`,
`cinema_edit.py`, `hf_motion_scenes.py`, `export_hyperframes.py` e o EDITOR.
A doutrina de *como* compor está na skill `hyperframes`; aqui ficam só os
modos de falhar que custaram uma rodada a alguém.

**Origem:** lista adaptada de `LeiteZ/fluxo-de-edicao` (`guias/hyperframes.md`,
MIT). Cada item tem um status, e **nenhum vira regra sem medição** (decisão D5 do
`PLANO-FLUXO-EDICAO.md`). Duas medições já desmentiram ou estreitaram o que a
fonte afirmava — por isso a coluna "medido aqui" existe.

Versão de referência: **HyperFrames 0.8.93 · GSAP 3.14.2** (2026-11-03).

---

## 0. Primeiro passo de toda cena: `hyperframes check`

Ao montar o teste das medições abaixo, a cena não animava e o render saiu mesmo
assim — sem erro, com a caixa parada. O `check` dizia o porquê em uma linha
(`missing_gsap_script`). **Render que termina não prova que a animação rodou.**
Ciclo: `check` sem erros → `snapshot` nos momentos-chave → render → conferir
um ou dois quadros do arquivo final.

---

## 1. Tempo e duração

| Armadilha | Status no Prisma | Medido aqui |
|---|---|---|
| **A duração vira frames arredondando PARA CIMA.** A fonte manda escrever a raiz como `(N − 0,5)/fps` porque "o render arredonda `duração × fps` para cima" | `beat_edit.py:226` arredonda os tempos em 4 casas, `:247` em 6 | **Parcialmente verdade.** O 0.8.93 arredonda para cima **com tolerância**: `8,00001 → 8`, `8,001 → 8`, mas `8,016 → 9` e `8,4 → 9`. Os arredondamentos de 4 e 6 casas do Prisma são seguros. **O risco:** 3 casas ou menos, ou somar folga à duração. `(N − 0,5)/fps` também dá N (medido: `0,25 s × 30 → 8`) e é a forma mais segura |
| **Versão fixa por vídeo.** Trocar de versão no meio de um vídeo pode mudar o desenho do que já foi aprovado | ❌ **falta**: `beat_edit.py:67` grava `npx --yes hyperframes@latest` nos scripts do projeto; `export_hyperframes.py:84` e `preview_server.py:275` mandam instalar `@latest` | — Correção pendente (depois da F6.1): gravar a versão instalada no `package.json` do projeto e no `state.json`, e usar sempre ela naquele vídeo |
| **Render não é 100% determinístico** (~1/255 em poucos pixels perto de motion blur) | — | hipótese; é a margem que a F6.1 deve usar ao comparar quadros |

## 2. GSAP dentro do HyperFrames

| Armadilha | Status no Prisma | Medido aqui |
|---|---|---|
| **`fromTo` que começa visível precisa de `immediateRender:false`**, senão o estado inicial aparece desde o tempo 0 | ✅ `beat_edit.py:99,102,103,105`, `cinema_edit.py:240` | — |
| **`transformOrigin` dentro de um tween com `immediateRender:false` não vale quando o quadro é calculado pulando direto** → zoom deslocado. A fonte manda fixar com `tl.set(alvo, {transformOrigin}, início)` | `cinema_edit.py:240` põe a origem no próprio `fromTo` | **Não se reproduz no render.** Duas cenas, origem dentro do `fromTo` × `tl.set` antes: borda esquerda fixa em x=100 nas duas, em t=0,15/0,5/0,95 (origem 0% respeitada). **Snapshot não testado.** O `tl.set` continua sendo o mais seguro para código novo |
| **Partida explícita:** movimento encadeado com `to()` lê a partida da tela, e snapshot e render podem discordar | 29 `tl.to(` em `hf_motion_scenes.py`, 11 em `cinema_edit.py`, 5 em `beat_edit.py` | hipótese; prefira `fromTo` em código novo |
| **`lazy:false` em todo tween novo**, senão o GSAP adia o primeiro quadro | 0 ocorrências | hipótese, não medida |
| **Tweens na mesma propriedade não se sobrepõem**: corte o anterior onde o próximo começa | — | hipótese |
| **Medir layout só dentro de `document.fonts.ready.then(…)`** | não se aplica hoje: nenhum helper mede texto no JS (0 `getBoundingClientRect`/`offsetWidth`) | — |
| **Aleatório com semente fixa** (canvas em `onUpdate`), senão cada render sai diferente | ✅ `cinema_edit.py:569` (`seed` do grão); 0 `Math.random` nos helpers | — |
| **O GSAP vem de CDN** (`cdn.jsdelivr.net/npm/gsap@3.14.2`) | todos os helpers | — Render offline falha no `check`. A versão já está fixa no link, o que é bom |

## 3. CSS e desenho

| Armadilha | Status no Prisma | Medido aqui |
|---|---|---|
| **CSS embutido no `index.html`, nunca por `<link>`** — o link mudou o desenho das letras no render | ✅ todos os helpers escrevem `<style>` (`beat_edit.py:138,183,334,388`) | — |
| **Texto com gradiente corta a última letra** (`background-clip:text` + espaçamento negativo) | ✅ `hf_motion_scenes.py:274-283`; `shortform.md:857` (`text_not_painted`) | — |
| **Motion blur:** use `data-motion-blur-tier="filter"`. Com ele ligado: sem `backdrop-filter` em card com texto animado, sem `drop-shadow` em texto com gradiente; ele só borra o elemento animado mais externo, ignora 3D e elementos maiores que meio quadro | não se aplica hoje: o Prisma não liga o motion blur do HyperFrames | — **Condicional:** `backdrop-filter` está em `hf_motion_scenes.py:26` e `export_hyperframes.py:408`, e o `drop-shadow` de `export_hyperframes.py:489` está num `<img>` (não é texto). Se um dia ligar o motion blur, revise estes três antes |
| **Vinheta de quadro inteiro com `box-shadow: inset`**, não com `background` (o `check` acusa texto encoberto) | — | hipótese |
| **Luz/reflexo dentro de card abaixo do texto** (`z-index`); brilho dentro de `overflow:hidden` recortado só no eixo do movimento | — | regra de desenho, sem medição |

## 4. Saída e composição

| Armadilha | Status no Prisma | Medido aqui |
|---|---|---|
| **Sobreposição com transparência em MOV ProRes 4444** | o CLI confirma: `--format mov` usa sempre ProRes 4444 com alfa | — |
| **Para conferir uma sobreposição sobre a câmera, extraia o quadro do MOV para PNG e só então componha** (compor direto do MOV com `-ss` saiu vazio) | — | hipótese |
| **Compor em 1080p e renderizar na resolução do vídeo** (o desenho é o mesmo; snapshots mais rápidos) | `beat_edit.py:15` compõe direto em `1080x1920` | hipótese; o tempo de render é dominado pelo custo fixo de abrir o navegador (fonte: ~25 s para 7 s em 4K) |
| **A doutrina do próprio HyperFrames chama "aproximação lenta contínua" e "título que continua se movendo" de sinais de vídeo gerado** | o Prisma usa `zoomAuto` (push-in lento) | — Quando o estilo do projeto pede câmera viva, vale o estilo. O resto da doutrina (cortar no frame mais rápido, sobreposição de movimentos, curva por papel) é compatível |

---

## Como as medições foram feitas (para repetir)

Cena mínima de 320×180 ou 400×200, uma caixa `class="clip"`, um tween,
`hyperframes render --fps 30`, depois:
- **duração:** `ffprobe -count_frames … nb_read_frames`;
- **origem:** quadro em t extraído com `ffmpeg -ss t -frames:v 1 -pix_fmt gray` e a
  caixa branca localizada por limiar (coluna/linha mínima e máxima).

Projetos de teste em `%TEMP%\hf-duration-test` e `%TEMP%\hf-origin-test`.
