# Trilha sonora — o que funciona, por formato

Pesquisa de 2026 + o que foi medido em produção. Serve para escrever briefings
de geração (Treblo) que acertem de primeira, em vez de gerar três versões do
mesmo território sonoro.

Fontes: [Musiqueen — gêneros do Reels 2026](https://www.negishut.co.il/blog/top-10-music-genres-instagram-reels-2026) ·
[TunePocket — vídeo instrucional](https://www.tunepocket.com/music-for-instructional-video/) ·
[Voiceovers.com — música sob narração](https://www.voiceovers.com/blog/best-background-music-for-voice-over) ·
[Later — tendências de Reels](https://later.com/blog/instagram-reels-trends/)

---

## A regra que decide tudo: o vídeo TEM FALA?

Essa é a bifurcação. Um Reel de dança e um Reel explicativo pedem músicas
opostas, e é aqui que a maioria dos briefings erra.

| | **Com narração** (talking head, tutorial, explicativo) | **Sem narração** (b-roll, dança, lifestyle) |
|---|---|---|
| Função | sustentar, não competir | ser o protagonista |
| Melodia | mínima ou ausente | forte e memorável |
| BPM | 60–90 (calmo) · 100–120 (energético) | o que a plataforma estiver premiando |
| Instrumentação | poucas camadas, registro fora da voz | cheia |
| Erro clássico | melodia bonita demais — disputa com a fala | trilha genérica demais |

Para conteúdo falado, a orientação é consistente: **instrumental, calmo, não
distrativo**. Letra durante a fala é o pior caso — palavras competindo com
palavras.

**Contraintuitivo, mas documentado:** música contínua nem sempre é a melhor
escolha. Um argumento de produção defende usar a trilha em abertura, transições
e fecho, e deixá-la sair sob os trechos de fala mais densos. "Wall to wall" é
padrão, não é lei.

---

## Gêneros que dominam Reels em 2026

Levantamento de tendências, ordenado pelo que serve a conteúdo falado:

| Gênero | Serve para fala? | Observação |
|---|---|---|
| **Lo-fi / instrumental minimalista** | ✅ **o melhor** | feito para ficar sob voz; tutoriais, "3 dicas", b-roll calmo |
| **Ambient / corporate leve** | ✅ | some no fundo, mas some mesmo — pode ficar apagado demais |
| **Indie-pop etéreo** (Lorde, Lana) | ⚠️ | bonito, mas a melodia chama atenção |
| **Slowed / remix lento** | ⚠️ | dramático; bom para b-roll, atrapalha explicação |
| **Afrobeats** | ❌ para fala | crescimento explosivo em 2026, mas é para dança/viagem |
| **Hyperpop** | ❌ para fala | rápido, glitchy, maximalista |
| **Throwbacks nostálgicos** | ❌ para fala | funciona pelo reconhecimento da letra |

**Nota de alcance:** áudio em alta na plataforma reporta 2-3× mais alcance que
áudio não-trending. Isso vale para música **licenciada do catálogo**, não para
trilha gerada — que é o nosso caso. Trilha própria compra consistência de marca,
não impulso de algoritmo. São objetivos diferentes; escolha sabendo disso.

---

## Como escrever o briefing (Treblo)

O `treblo_music.py` já emoldura como peça instrumental composta e proíbe SFX e
vocais. O que **você** escreve precisa nomear quatro coisas:

```
gênero + instrumentos-chave + BPM + humor
```

### Modelos por tipo de vídeo

**Explicativo / saúde / educação** (o caso do projeto 1001):
```
warm lo-fi instrumental, soft electric piano, muted upright bass,
brushed drums, ~72 BPM, calm and reassuring, minimal melodic movement
```

**Reels energético com fala** (venda, lançamento):
```
modern electronic pop bed, punchy kick and crisp hats, warm analog bass,
short repeating synth figure, ~112 BPM, confident and forward-moving
```

**B-roll / lifestyle sem narração** (aqui a melodia pode brilhar):
```
dreamy indie-pop instrumental, shimmering guitars, wide reverb pads,
memorable lead motif, ~95 BPM, nostalgic and cinematic
```

**Institucional / autoridade:**
```
restrained cinematic score, sustained strings, sparse piano,
slow swell, ~68 BPM, serious and trustworthy
```

### O que NÃO escrever

- **"soft finger-snap and light percussion"** — medido neste projeto: produziu
  algo tímido demais para mudar o caráter. A v1 e a v2 saíram com correlação de
  envelope **0,41** e ambas eram piano com cordas. Se quer groove, peça
  **"punchy kick and hats, bass-forward, piano only as texture"**.
- Adjetivos sem instrumento ("épico", "emocionante") — o modelo precisa de
  substantivos concretos.
- "beat", "bed", "sound design", "risers", "drones" — puxam o gerador para
  efeito sonoro em vez de música.

---

## Verificar antes de aceitar

Gerar e ouvir não basta quando existem duas opções: o ouvido se acostuma. Meça.

```bash
# densidade rítmica: quantos picos em 60s
# 50-70 = contemplativo · 100+ = com groove
# correlação de envelope entre duas trilhas:
#   >0.8 praticamente a mesma · <0.3 realmente distintas
```

Medido neste projeto: v1 = 58 picos, v2 = 104 picos, correlação 0,41. As duas
**eram** diferentes, mas do mesmo território — o usuário percebeu antes de
qualquer número, e tinha razão.

**Bandas que importam:**
- **4–12 kHz** revela percussão. v1 tinha −44,3 dB (sem), v2 −34,3 dB (com).
- **250–2200 Hz** é onde a voz mora — ver o carve em `toolbox.md`.

---

## Mixagem sob fala

Com `music_carve.py` a trilha fica em **~0.22**; sem carve, ~0.10. O carve
esculpe a banda da voz (−8,7 dB medidos) e deixa grave e agudo intactos, então
a música soa presente sem disputar.

**Uma coisa que vai parecer bug e não é:** a trilha em ZERO e ainda se ouve algo
na pausa. Não é a música — é **respiração e ruído de sala**. Medido: o `cut.mp4`,
que nunca teve trilha, marca −30,5 dB no grave e −21,0 no médio durante a pausa
de 133,45s, exatamente os mesmos números do vídeo entregue. Nenhum controle de
trilha remove isso; é a gravação.

**A trilha é mixada no ffmpeg da entrega, NUNCA pelo Remotion**
(`soundtrack.enabled: false`). Mixada nos dois, ela entra em dobro e a cópia do
Remotion fica surda ao fader do preview.
