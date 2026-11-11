# Transcrição: nível adaptativo, engines e segunda escuta

Helpers: `speech_level.py`, `speech_regions.py`, `transcribe.py`, `parakeet_engine.py`, `second_listen.py`.

## 1. Nível da fala adaptativo (`speech_level.py`)

Dois defeitos reais, um em cada ponta:

- **Sala com eco** (CLA200, showroom): `silencedetect` fixo em -33 dB não achou pausa nenhuma; foi calibrado à mão em -23 dB / 0,45 s.
- **Gravação muito baixa** (fala ~-43 dB RMS): tudo vira "silêncio" e o transcritor devolve pouco ou nada.

Medição: RMS em janelas de 50 ms. Fala = percentil 90; piso = percentil 10.

- **Ganho de análise**: só no áudio que o transcritor e o detector escutam (o vídeo cortado nunca muda de volume). Leva a fala a -20 dB, com freios: só se faltarem >= 6 dB (gravação normal fica intocada), nunca acima de -10 dB no p99, máximo 30 dB, com limitador (`alimiter` no ffmpeg / clip suave em numpy).
- **Limiar de silêncio automático**: `piso + 0,5·(fala − piso)`, preso a [-45, -18] dB e pelo menos 8 dB abaixo da fala.

`speech_regions.py` usa `--noise auto` por padrão; `--noise=-33dB` (com `=`, por causa do sinal de menos) continua valendo. `transcribe.py` mede, aplica o ganho antes do modelo, loga e grava `_analysis_gain_db` no JSON. `--no-analysis-gain` desliga (útil para A/B). `voice_levels.py` e `refine_edges.py` já aprendem piso/limiar da própria gravação, então não foram alterados.

### Medido

| Arquivo | fala p90 | piso p10 | limiar auto | regiões auto / -33 / -23 (d=0,10 s) | d=0,45 s auto / -33 / -23 |
|---|---|---|---|---|---|
| CLA200 `cut.mp4` | -12,2 | -34,0 | **-23,1 dB** | 72 / 3 / 72 | 1 / 1 / 1 |
| CLA200 fonte `..._162828 (1).mp4` | -11,6 | -38,5 | **-25,1 dB** | 61 / 10 / 84 | 24 / 2 / 29 |

O automático cai a 2 dB do -23 calibrado à mão e acha as pausas que o -33 não achava (10 → 61 regiões na fonte).

Cópia sintética silenciosa (fonte -24 dB, 60 s), WhisperX sem segunda escuta: p90 -35,9 dB, ganho automático +15,9 dB, 140 palavras com ganho vs 139 sem — o WhisperX é robusto a -24 dB. Com -32 dB (p90 -43,9 dB), Parakeet: ganho +23,9 dB, 140 palavras com ganho vs 135 sem. O ganho ajuda pouco nos dois motores até ~-44 dB; o ganho maior é no silencedetect (o -33 fixo leria o arquivo todo como silêncio) e em gravações ainda mais baixas.

## 2. Engines (`transcribe.py --engine whisperx|parakeet`)

- **whisperx** (padrão): Whisper large-v3 + alinhamento forçado wav2vec2.
- **parakeet** (opcional): NVIDIA Parakeet TDT 0.6B v3, int8 ONNX, via sherpa-onnx (CPU, sem torch). Detecta o idioma sozinho (`--language` só marca o JSON).

Instalação do Parakeet: `uv sync --extra parakeet` (sherpa-onnx). O modelo são 4 arquivos (`encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, `tokens.txt`, ~670 MB) em `$PRISMA_PARAKEET_DIR`, `~/.edvid/modelos/parakeet-tdt-0.6b-v3-int8` ou `~/.prisma/modelos/parakeet-tdt-0.6b-v3-int8`. O Prisma não baixa sozinho; o pacote int8 de `parakeet-tdt-0.6b-v3` fica nas releases do sherpa-onnx no GitHub (`asr-models`) — pedir antes de baixar.

Restrições tratadas: o áudio vai em pedaços de ~60 s cortados em pausas (o v3 "escorrega" de idioma em trecho longo), teto de 120 s por pedaço (o encoder tem limite ~13 min e a memória cresce), tempos somados ao deslocamento do pedaço e checagem de que o tempo nunca volta. Mesmo schema do WhisperX (`words` com `text/start/end/type/speaker_id`, `spacing`), cache e `_transcription_backend` (`parakeet/tdt-0.6b-v3-int8/...`).

### A/B no CLA200 `cut.mp4` (140 s, CPU, sem GPU)

Referência de concordância: o transcrito WhisperX já existente do projeto. "Dentro" = fim da palavra dentro de uma região de fala do `speech_regions` (auto, -23,1 dB).

| | tempo | palavras | concordância (F1 de palavras) | Δ início / fim (mediana) | fins dentro da fala |
|---|---|---|---|---|---|
| WhisperX (novo, +2ª escuta) | 318,7 s | 353 | 0,964 | 0 ms | 95,2 % (98,3 % ±30 ms) |
| Parakeet | 12,8 s | 347 | 0,929 | 75 / 83 ms | 85,3 % (90,2 % ±30 ms) |

Parakeet é ~25× mais rápido nesta máquina (CPU), com texto bem próximo, mas os tempos de palavra são mais frouxos (tokens a cada 80 ms, sem alinhamento forçado): 10 pontos a menos de fins dentro da fala. **Recomendação: manter whisperx como padrão** (os cortes se apoiam em tempo de palavra preciso). Parakeet serve para rascunho/triagem rápida de fontes longas ou quando o WhisperX está lento (sem GPU). Se o corte usar Parakeet, passe por `refine_edges.py` (que já ajusta as bordas ao áudio).

## 3. Segunda escuta (padrão ligado; `--no-second-listen` desliga)

Resolve "um take que a transcrição perdeu". Depois da passada principal: janelas de 50 ms acima do limiar adaptativo e sem palavra viram buracos (voz >= 0,45 s, buraco <= 25 s, expandido até as palavras vizinhas porque a fala some aos poucos nas bordas); cada buraco é re-transcrito com 0,4 s de contexto; **só entram palavras cujo ponto médio cai no buraco**, com duração <= 1,0 s e sem lixo de decodificação. As recuperadas levam `recovered: true`; o log mostra quantos buracos/palavras, e o JSON guarda `_second_listen`.

O WhisperX re-escuta direto no faster-whisper **sem VAD** (o VAD era justamente quem descartava o trecho; com VAD o resultado foi 0 palavras).

### Medido na fonte CLA200 `..._162828 (1).mp4`

- Buracos achados: 111,9–113,1 s e **133,8–139,2 s** (o trecho sem palavras; 133,6 → 139,2 s).
- Resultado real nesses dois: o Whisper devolveu palavras esticadas sobre silêncio (`solar` com 5,4 s, `gente` com 1,4 s) — alinhamento sobre áudio de baixo nível (mediana -26 dB), não fala clara. Com o filtro de duração, **0 palavras** são aceitas aí. A janela anterior à palavra "peto/teto solar" é hesitação, não um take perdido.
- Prova do mecanismo: apagando de propósito as 20 palavras de 150–157 s, a segunda escuta achou 1 buraco (150,3–157,0 s) e **recuperou 19 das 20**; contagem 329 → 348; nenhuma palavra duplicada nas costuras (a única repetição adjacente, "as" em 127,9 s, já existia).
- No `cut.mp4` do CLA200: WhisperX 344 → 353 palavras (5 recuperadas, entre elas 4 frases curtas em 74,2–74,8 s); Parakeet 347 → 351 (recuperações curtas e ruidosas — revisar as marcadas `recovered`).

## 4. Atribuição

- **NVIDIA Parakeet TDT 0.6B v3**: licença **CC-BY-4.0** (NVIDIA). Ao distribuir resultados que dependam do modelo, credite NVIDIA e o modelo `parakeet-tdt-0.6b-v3`.
- **sherpa-onnx**: Apache-2.0 (k2-fsa).
- **WhisperX / Whisper**: BSD-2 / MIT.
