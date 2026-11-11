# MULTICAM — vários ângulos sobre o mesmo take (Fase 1)

Leia quando houver **2+ câmeras gravando a mesma fala**, um **master 4K** que pode
render um close-up "de graça" (câmera virtual), ou quando o usuário pedir ângulos
gerados por IA a partir de uma única câmera. Tudo é feito por `helpers/multicam.py`
e **só escreve EDL**: o `render.py` não muda. Cada range passa a ter como `source`
o ângulo escolhido, e o SOM de todos os ranges é roteado (`audio_sources`) para o
áudio do master — a voz nunca troca de microfone entre ângulos.

Valor principal: **cada jump cut do master vira troca de ângulo**, e a troca esconde
o corte. Convenção de tempo (a do `sync_sources.py`): `t_master = t_ângulo + offset`.

## Quando usar

| Situação | Caminho |
|---|---|
| 2+ câmeras (celular + câmera, duas câmeras) | `sync` |
| 1 câmera em **≥ 4K**, saída 1080 | `virtual` (punch-in que segue o rosto, sem upscale) |
| 1 câmera ≤ 1080p, quer variedade | ângulos de IA (`add-ai` → `ai-prep` → geração → `ai-assemble`) |
| Entrevista/podcast | `sync` + `--style content` |

Não serve para: câmeras que não ouvem a mesma cena (sem áudio em comum o `sync` recusa);
fontes com fps diferentes do master; `--keep-resolution` com ângulos de tamanho diferente
(o concat sem reencode exige o mesmo tamanho — renderize no padrão 1080 ou use
`virtual --out-size <WxH do master>` aceitando que o close fica mais macio).

## Gravação

- **Uma palma (ou marcador)** no começo, audível em TODAS as câmeras.
- **Todas as câmeras gravam som**, mesmo o ruim — o áudio dela só serve para medir o offset.
- **Mesmo fps** em todas (30/30). fps diferente = aviso e risco de escorregar.
- Câmeras ligadas antes da fala e desligadas depois; relógios de câmera barata derivam.
- Um master (a câmera principal, melhor som/enquadramento) e a Fase 1 (`transcribe`, corte,
  `edl.json`) feita **só sobre ele**. O EDL do master continua sendo a verdade do corte:
  transcrições, legendas e Fase 2 saem dele (o EDL multicam só troca de onde vem a imagem).

## Os comandos (rode com `uv run python helpers/multicam.py …`)

```
sync       <edit> --master M.mp4 --angles B.mp4 [C.mp4 …] [--roles close alt …]
virtual    <edit> --source M4K.mp4 [--zoom 1.6] [--focus face|center|x,y] [--faces f.json]
add-ai     <edit> <chave> [--rotate 0-360] [--vertical -30..90] [--closeup 0-10]
plan       <edit> [--style alternate|content] [--min-shot 2.5] [--max-shot 7] [--apply]
ai-prep    <edit> [--window 8] [--max-height 720]
ai-assemble <edit> [--size WxH] [--apply]
build / status
```

1. **`sync`** — offset de cada câmera contra o master (reusa `sync_sources.py`: correlação
   na faixa da voz, confiança = pico/2º pico, deriva em 3 janelas). **Confiança baixa →
   recusa e não grava.** Deriva ≥ 40 ms (≈1 frame) → o `plan` ignora o ângulo. Grava
   `<edit>/multicam.json` `{master, angles:[{key, kind, path, offset, confidence, drift_ppm, role}]}`.
2. **`virtual`** — segunda câmera virtual: crop `W/zoom × H/zoom` do master, escalado para
   saída de lado curto 1080. **Nunca sobe resolução**: zoom limitado a `min(W/saída, H/saída)`
   (4K → 2.0); fonte de 1080 recusa. Segue o rosto (YuNet/Haar, `safe_layout.detect_faces`,
   cache em `<edit>/multicam/faces_source.json`) com mediana de 1 s + zona morta de 5 % +
   gaussiana de 0,5 s, linha dos olhos a 38 % do quadro; sem rosto → crop fixo. Registra
   `role: close`, offset 0 e `unsafe`: trechos em que o close **não** é seguro (rosto não
   detectado, rosto saindo do quadro, movimento rápido) — o `plan` usa outro ângulo ali.
   Fonte HDR: o ângulo sai HEVC 10 bits com as tags HDR (**não testado**).
3. **`plan`** — ver regras abaixo. Escreve `edl.multicam.json` + `multicam_plan.json`,
   imprime a tabela (range, tempo, ângulo, motivo; `[IA]` marca trecho de IA). **Nunca
   sobrescreve `edl.json` sem `--apply`**, que guarda `edl.before_multicam.json` e marca o
   novo EDL com `"multicam": true` (um segundo `plan` lê o backup, não o EDL já trocado).

Cada range do EDL novo mantém `quote`/`reason`/`gain_db` e ganha `angle`, `angle_reason`,
`master_source/start/end` (de volta ao master) e, se o planejado não valeu,
`angle_planned`. Chaves de ângulo viram `sources`; cada uma ganha
`audio_sources[<chave>] = {"path": <master>, "offset": -offset}`.

## Regras de troca

1. **Troca em todo jump cut do master** (vão > 80 ms entre ranges); ranges contíguos não trocam.
2. **Plano mínimo** `--min-shot` (padrão 2,5 s; nunca abaixo de 1,5): um corte só acontece se o
   plano em curso já tem o mínimo (conta ~0,12 s perdidos por emenda do J-cut). Um jump cut que
   cai dentro de um plano curto **fica à mostra** ("corte adiado" na tabela) — com ranges de
   ~2 s isso acontece com frequência; baixe `--min-shot` para 1,5 se quiser esconder mais.
3. **Nunca duas trocas em 1,2 s** (garantido pelo mínimo acima).
4. **Abertura e fechamento no master.**
5. **Take longo** (> `--max-shot`, estilo alternate) é partido numa **pausa medida** (≥ 0,30 s,
   piso+6 dB como o `edge_quiet` do render; nunca dentro de palavra da transcrição) para ganhar
   uma troca. Se as duas metades caírem no mesmo ângulo, a divisão é desfeita. Cada emenda
   dessas encurta a pausa pelo lead+cauda do J-cut (~0,1–0,2 s).
6. **Close/virtual em ênfase**: números, unidades, "detalhe/repare/olha…" (`--emphasis` soma
   palavras do produto: "turbo", "couro"…). Sem close seguro, vai para outro ângulo e a
   tabela diz por quê.
7. **Master** quando o close está inseguro (movimento/rosto fora/rosto não detectado) ou o
   ângulo não cobre o trecho.
8. **Diversidade**: a troca nunca repete o ângulo anterior; com 3+ ângulos escolhe o menos
   recente (rodízio). `--style content` só troca em ênfase (e para IA em linhas conectivas).

### Ângulos de IA — heurística (créditos e boca)

Ângulos de IA **regeneram pixels**: a boca pode não casar com a voz. Por isso o `plan` só
dá IA a trechos em que a boca pesa menos:
- plano **≤ 4 s** (`--ai-max-shot`) e **nunca** em ênfase/número/detalhe;
- preferência por linhas **conectivas** (começam com "e/mas/então/que…" ou terminam sem
  ponto final — meio de frase);
- teto de **35 %** do tempo (`--ai-share`) para limitar custo;
- `--ai-max-closeup N` tira IA com `closeup` maior que N (mantém IA longe de rosto em close).

## Fluxo de IA (a geração é feita fora do Python, sem API paga aqui)

1. `add-ai <edit> lado_dir --rotate 35 --closeup 2` (quantos presets quiser; `baixo`, etc.).
2. `plan` — decide quais trechos vão à IA.
3. `ai-prep` — só os trechos do **plano** (não o vídeo todo), adjacentes fundidos, janelas
   ≤ 8 s cortadas em emendas/pausas, **+0,3 s de folga** de cada lado, exportadas do master
   (resolução da fonte, CFR) em `<edit>/ai_angles/` + `jobs.json`
   `[{id, angle, master_start, master_end, file, rotate, vertical, closeup, status:"pending"}]`.
   Imprime segundos por ângulo — estime os créditos **antes** de pedir ao usuário.
4. Gere cada janela com `video_camera_angle`; grave `status: "done"` e `result: <arquivo>`.
5. `ai-assemble` — conforma cada resultado à janela (fps do master, tamanho, **número exato de
   frames**: apara no fim ou repete o último frame; nunca estica fala; resultado > 0,5 s mais
   curto = `failed`), junta o som do master ao arquivo (o render mede o silêncio das emendas nele)
   e refaz o EDL. Janela `pending`/`failed` → o trecho **cai no master**, com aviso e
   `angle_planned` no range. Cada janela vira uma fonte própria (`<ângulo>__w03`), sincronizada
   pelo `file_start` do job (não é um arquivo único de offset 0).

## Verificação (não pule)

1. `sync`: confira `confiança` e a deriva impressas; palavra marcante nas duas fontes se média.
2. `render.py edl.multicam.json -o cut.mp4 --no-subtitles` — o log mostra cada take com a fonte
   e os frames planejados = obtidos (lip sync).
3. `verify_cut.py edl.multicam.json cut.mp4` — flags de emenda.
4. **Lip-sync em AMBOS os ângulos**: correlacione o áudio do render com o de um render só-master
   dos mesmos ranges (deve dar 0 ms) e confira a imagem de 2–3 takes de cada ângulo.
5. **Contact sheet nas trocas** (`contact_sheet.py` em torno de cada troca): close nítido e com
   o rosto enquadrado; a troca cai em pausa, não no meio de palavra.
6. **IA**: contact sheet nos frames de BOCA de cada janela de IA — se a boca descola ou deforma,
   marque o job como `failed` (volta ao master) ou refaça o plano com `--ai-max-closeup` menor.

## Limites conhecidos

- `grade` é único por EDL: câmeras de cores diferentes precisam de LUT/correção própria antes.
- O EDL multicam não tem transcrição por fonte de ângulo: use `--no-subtitles` no render e gere
  legendas/Fase 2 a partir do EDL do master (mesma duração e tempos).
- Deriva de relógio: um offset único; ≥ 40 ms o ângulo é ignorado.
- O "close inseguro" só existe para a câmera virtual; câmeras reais não têm detecção de rosto.
- A divisão de takes longos e as trocas encurtam pausas ~0,1–0,2 s por emenda (J-cut do render).
