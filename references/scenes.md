# Cenas sob medida (CustomGraphics + kit)

Quando ler: o pedido é uma cena que o `edit-data.json` não descreve — "a palavra
MBUX aparece quando ele diz MBUX", "o logo passa ATRÁS dele", "um objeto 3D gira ao
lado". Tudo o mais (cards, headline, legenda, splits, B-roll) é DADO no edit-data;
só o que não cabe em dado vira cena.

## Onde o código vai

```
<edit>/remotion/src/
  CustomGraphics.tsx      ← o ÚNICO arquivo que se edita; só monta cenas
  scenes/MinhaCena.tsx    ← uma cena por arquivo
  kit/                    ← ferramentas (não editar): speech, safe, tokens, three, person
  Main.tsx                ← NUNCA editar (os dois templates: shortform e longform)
```

`CustomGraphics.tsx` fica vazio por padrão. Montar uma cena é uma linha:
`import {MinhaCena} from './scenes/MinhaCena'` + `<MinhaCena />`. A cena decide a
própria janela de tempo (a partir da fala) e devolve `null`/opacidade 0 fora dela.
Os dois templates têm o mesmo kit com os mesmos nomes; as medidas vêm do quadro
(`useVideoConfig()`), então a mesma cena serve em 1080×1920 e 1920×1080 se for
escrita em razões, não em pixels.

## Tempo vem da FALA, não de segundos

Segundo escrito à mão quebra quando a edição é re-cortada. Ancore na transcrição
(`public/captions.json`, nível de palavra, na linha do cut):

```tsx
import {whenSaid, endOfSaid, windowOf, progress, power3Out} from '../kit';
const t0 = whenSaid('MBUX', 89);         // quando COMEÇA a ser dita (ocorrência mais próxima de 89 s)
const t1 = endOfSaid('MBUX', 89) + 1.3;  // some 1,3 s depois
const env = windowOf(frame, fps, t0, t1, 0.35, 0.25);   // 0 -> 1 -> 0 (entra/segura/sai)
const pop = progress(frame, fps, t0, 0.55, power3Out);  // 0 -> 1 a partir da palavra
```

- `whenSaid(frase, near)` / `endOfSaid`: a frase pode ter várias palavras; `near` (s) escolhe
  entre ocorrências repetidas. Sem achar, devolve `near` e avisa no log — confira o aviso.
- `windowBetweenWords(frame, fps, 'de', 'até', near)`: do começo de uma frase ao fim de outra.
- A cena entra NA palavra ou logo depois (o cartão de destaque entra +0.8 s depois, para não
  duplicar a legenda — ver "Estilo do card 3D"). Nunca ANTES de a palavra ser dita.

## Regras de ofício

1. **Uma ideia por cena**, uma animação de entrada, uma de saída. Entrada: opacidade/foco em
   `expo.out` curto (~0.3 s), posição em `power3.out` (~0.5 s). Saída ~0.25 s `power3.in`.
   Sem bounce na saída.
2. **Mesma língua cromática**: `TOKENS.accent` (o `accent` do edit-data) e `TOKENS.font`. Duas
   cores de destaque no mesmo vídeo leem como dois vídeos colados.
3. **Legível sobre pintura clara**: `inkShadow` no texto, ou `glassStyle()` atrás. Contraste
   conferido em still, não de memória.
4. **Fora do rosto**: use `freeSpot(frame, W, H, fps, x, y, w, h)` para elementos pequenos —
   abaixo do queixo -> acima da cabeça -> ao lado, dentro da área segura. Rode
   `helpers/safe_layout.py <edit> --report` antes para gerar `public/faces.json`. Elemento
   grande que deve ficar ATRÁS da pessoa não precisa fugir do rosto (ver abaixo).
5. **Área segura**: 9:16 respeita as faixas de UI da plataforma (`safeArea`), 16:9 tem 5%.
6. **Pessoa na frente**: `InFrontOfPerson` põe o elemento ENTRE o vídeo-base e o recorte da
   pessoa. Gere o recorte com `person_matte.py cut.mp4 -o public/pessoa-x.mov --start <from>
   --duration <to-from>` (um arquivo por janela; frame 0 = `from`) e passe o mesmo `from`.
7. **3D** (`Scene3D`, three.js): precisa de WebGL — render com `--gl=angle`; ponha
   `"scene3d": true` no edit-data para o `render_phase2.py` passar a flag sozinho. A câmera tem
   1 unidade = 1 px no plano z=0 (`pxToWorld`).
8. Sem fonte/logo de terceiros sem licença; o Poppins do kit é OFL.
9. **Peso**: cena que usa `backdropFilter` ou 3D custa render — mantenha a janela curta.

## Exemplo mínimo

```tsx
// src/scenes/Mbux.tsx
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {InFrontOfPerson, TOKENS, endOfSaid, glow, power3Out, progress, whenSaid, windowOf} from '../kit';

export const Mbux = () => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const t0 = whenSaid('MBUX', 89), t1 = endOfSaid('MBUX', 89) + 1.3;
  const env = windowOf(frame, fps, t0, t1);
  const pop = progress(frame, fps, t0, 0.55, power3Out);
  return (
    <InFrontOfPerson matte="pessoa-mbux.mov" from={t0 - 0.5} to={t1}>
      <AbsoluteFill style={{opacity: env, alignItems: 'center', justifyContent: 'center'}}>
        <div style={{fontFamily: TOKENS.font, fontWeight: 900, fontSize: height * 0.36,
                     color: '#fff', textShadow: glow(), scale: String(0.86 + 0.14 * pop)}}>MBUX</div>
      </AbsoluteFill>
    </InFrontOfPerson>
  );
};
```

Montar: `CustomGraphics.tsx` -> `<Mbux />`.

## Verificar

1. `npx tsc --noEmit` na pasta `remotion/`.
2. Stills, nunca só "compila": um 0.3 s ANTES da palavra (a cena NÃO pode aparecer), um no
   frame da palavra e um ~0.2–0.5 s depois (já entrando/dentro):
   `npx remotion still <Comp> out.png --frame=<round(t*fps)> [--gl=angle]`
   (`Longform` ou `Reels`). Leia as imagens: nada cortado, texto legível, rosto livre, a pessoa
   realmente na frente do elemento.
3. Cena com recorte: confira que a mão/braço passa NA FRENTE do elemento (alinhamento do recorte).

## Runtime compartilhado

`scaffold_phase2.py` liga `<edit>/remotion/node_modules` ao runtime em
`~/.prisma/remotion-runtime` (construído uma vez a partir de `assets/remotion-runtime`), em vez
de um `npm install` por projeto. Se o runtime estiver ausente/quebrado, ele o reconstrói (`npm ci`)
ou, em último caso, roda `npm install` no projeto. `PRISMA_REMOTION_RUNTIME` muda o local.
